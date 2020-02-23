import pytest
import json
from io import StringIO
from asciinema_edit import Recording


@pytest.fixture(scope="session")
def recording():
    infile = StringIO()
    for entry in [
          [{"version": 2, "width": 87, "height": 43, "timestamp": 1582450376,
            "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"}}],
          [1.0, "o", "one"],
          [2.0, "o", "two"],
          [3.0, "i", "d"],
          [3.1, "i", "e"],
          [3.2, "i", "l"],
          [4.0, "o", "three"],
          ]:
        infile.write(json.dumps(entry)+'\n')
    infile.seek(0)
    ret = Recording(infile)
    yield ret


def test_delete_word(recording):
    recording.del_in_word('del')
    assert recording.body[2][2] == "three"
