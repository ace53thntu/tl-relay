import os
import pathlib
import sys
import tempfile

os.environ.pop("CLAUDE_CODE_SESSION_ID", None)

REAL_HOME = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REAL_HOME))


def _can_symlink() -> bool:
    with tempfile.TemporaryDirectory() as d:
        try:
            os.symlink("target", os.path.join(d, "link"))
        except (OSError, NotImplementedError):
            return False
    return True


CAN_SYMLINK = _can_symlink()
