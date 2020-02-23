#!/usr/bin/env python3
import argparse
import bisect
import json
import logging
from pprint import pprint
import sys

logger = logging.getLogger(__file__)

logger.setLevel(logging.INFO)

class Recording:
    def __init__(self, infile, outfname=None):
        self.infile = infile
        self.outfname = outfname
        self.header = None
        self.body = None

        lines = self.infile.readlines()
        self.header = lines[0].strip()
        self.body = [json.loads(line) for line in lines[1:]]
        print("Body lines: ", len(self.body))

    def write(self, startidx=0, endidx=None):
        if not endidx:
            endidx = len(self.body)

        # round timestamp decimal points
        for event in self.body:
            event[0] = float(round(event[0], 7))

        outlines = [json.dumps(ln) for ln in self.body[startidx:endidx]]
        outlines = "\n".join(outlines)

        if self.outfname:
            out = open(self.outfname, "wt+")
        else:
            out = sys.stdout
        out.write(self.header + "\n")
        out.write(outlines)
        out.close()

    def renormalize(self):
        # re-normalize timestamps to begin at 0
        first_start = self.body[0][0]
        for line in self.body:
            line[0] = line[0] - first_start

    def parse_ranges_to_indices(self, ranges):
        idx_ranges = []
        timestamps = [elem[0] for elem in self.body]
        for rng in ranges:
            starttime, endtime = rng
            startidx = bisect.bisect_left(timestamps, starttime)
            endidx = bisect.bisect_left(timestamps, endtime)
            idx_ranges.append((startidx, endidx))

        idx_ranges = sorted(idx_ranges, key=lambda tup: tup[0])
        return idx_ranges

    def quantize(self, max_delay=1):
        """
        This function reduces the maximum gap between events
        """

        timestamps = [elem[0] for elem in self.body]

        # array of timestamp deltas to previous event
        deltas = [0]
        for i in range(len(timestamps) - 1):
            new_delta = min(max_delay, timestamps[i + 1] - timestamps[i])
            deltas.append(new_delta)

        # Adjust all timestamps with new deltas
        for idx in range(1, len(self.body)):
            self.body[idx][0] = self.body[idx - 1][0] + deltas[idx]

    def speed(self, ranges, factor=2):
        """
        This function increases speed within provided ranges by some factor
        """

        speedup = 1.0 / factor
        timestamps = [elem[0] for elem in self.body]

        deltas = [0]
        for i in range(len(timestamps) - 1):
            new_delta = timestamps[i + 1] - timestamps[i]
            deltas.append(new_delta)

        # convert timestamp ranges to idx ranges
        idx_ranges = self.parse_ranges_to_indices(ranges)

        for idx_range in idx_ranges:
            startidx, endidx = idx_range
            deltas[startidx:endidx] = map(
                lambda delt: delt * speedup, deltas[startidx:endidx]
            )

        # Adjust all timestamps with new deltas
        for idx in range(1, len(self.body)):
            self.body[idx][0] = self.body[idx - 1][0] + deltas[idx]

    def smush(self, start):
        """
        Compresses beginning of cast 
        (useful for TUI apps where you want to start in the middle of a cast without losing TUI elements loaded at the beginning)
        """

        for ln in self.body:
            if ln[0] < start:
                ln[0] = 0

        self.quantize()

    def keep(self, ranges):
        """
        Keeps a certain range of cast, discards the rest
        """

        assert len(ranges == 1), "Keep only takes one range"
        starttime, endtime = ranges[0]

        timestamps = [elem[0] for elem in self.body]
        startidx = bisect.bisect_left(timestamps, starttime)
        endidx = bisect.bisect_left(timestamps, endtime)

        self.body = self.body[startidx : endidx + 1]

        self.renormalize()
        self.quantize()

    def del_in_word(self, to_delete):
        """ Delete a word """

        word = ''
        word_start_i = 0
        for i, e in enumerate(self.body):
            c = e[2]
            if e[1] == 'i' and c.isalnum():
                if not word:
                    word_start = i
                word += c
                continue
            # it's not an input or not alphanumberic char
            if word:
                if word == to_delete:
                    for j in range(len(word)):
                        del self.body[word_start]
                word = ''

    def print_stdin(self, range):
        """ Prints the recorded stdin """

        word = ''
        word_start_time = 0
        for e in self.body:
            if e[1] == 'i':
                c = e[2]
                if c.isalnum():
                    word += c
                    if not word_start_time:
                        word_start_time = e[0]
                    continue
                # it's not an alphanumberic char
                if word:
                    print(f"{word_start_time}: {word}")
                    word = ''
                    word_start_time = 0
                else:
                    pprint(f"{e[0]}: {e[2]}")

    def excise(self, ranges):
        """
        Removes 1 or more ranges of cast
        """

        timestamps = [elem[0] for elem in self.body]

        # convert timestamp ranges to idx ranges
        idx_ranges = self.parse_ranges_to_indices(ranges)

        # walk idx_ranges and exclude each one
        new_body = self.body[
            : idx_ranges[0][0]
        ]  # include everything before start of first range
        for i in range(len(idx_ranges) - 1):
            # include end of this range to start of next range
            new_body += self.body[idx_ranges[i][1] : idx_ranges[i + 1][0]]

        # add last range to end
        new_body += self.body[idx_ranges[-1][1] :]

        self.body = new_body

        # renormalize, then adjust timestamps in body, just use quantize!
        self.renormalize()
        self.quantize()


def range_t(s):
    try:
        start, end = map(int, s.split(","))
        return start, end
    except:
        raise argparse.ArgumentTypeError("Range must be start,end")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--keep", action="store_true")
    group.add_argument("--excise", action="store_true")
    group.add_argument("--smush", action="store_true")
    group.add_argument("--quantize", action="store_true")
    group.add_argument("--speed", action="store_true")
    group.add_argument('-p', "--print-stdin", action="store_true")
    group.add_argument("--delete-stdin-word", type=str, default='',
                        help="Delete a word form stding, e.g. password")

    # Timestamp arguments
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float, default=float("inf"))
    parser.add_argument("--range", action="append", type=range_t)

    # Configuration arguments
    parser.add_argument("--delay", type=float, default=1)
    parser.add_argument("--factor", type=float, default=1)
    parser.add_argument("--out", help="Output file, default is stdout")
    parser.add_argument('-d', "--dry-run", action="store_true", help="Don't write the output file")
    parser.add_argument("inputfile", help="Input .cast file")

    args = parser.parse_args()
    print(args)

    if args.range and (args.start or args.end):
        assert "Must supply either --range or start/end!"

    with open(args.inputfile) as infile:
        r = Recording(infile, args.out)

    ranges = []
    if args.range:
        ranges = args.range
    else:
        ranges = [(args.start, args.end)]

    if args.smush:
        r.smush(start)
    elif args.keep:
        r.keep(ranges)
    elif args.excise:
        r.excise(ranges)
    elif args.quantize:
        r.quantize(args.delay)
    elif args.speed:
        r.speed(ranges, args.factor)
    elif args.print_stdin:
        r.print_stdin(ranges)
    elif args.delete_stdin_word:
        r.del_in_word(to_delete=args.delete_stdin_word)

    if not args.dry_run:
        r.write()
