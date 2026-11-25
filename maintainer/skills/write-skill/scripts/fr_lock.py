from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))
from runtime import config


class LockHeld(Exception):
    pass


class LockError(Exception):
    pass


class HomeError(LockError):
    pass


def _home() -> pathlib.Path:
    value = os.environ.get("TL_RELAY_HOME")
    if not value:
        raise LockError("TL_RELAY_HOME is not set")
    home = pathlib.Path(value)
    if not any((home / name).is_file() for name in config.HOME_FILES):
        raise HomeError("%s has no tl-relay.yaml, so it is not a tl-relay home" % home)
    return home


def lock_path() -> pathlib.Path:
    return _home() / "locks" / "final-run.lock"


def _open_lock() -> int:
    path = lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        return os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as exc:
        raise LockError("cannot open %s: %s" % (path, exc))


def _try_flock(fd: int, where: pathlib.Path) -> bool:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
            return False
        raise LockError("cannot lock %s: %s" % (where, exc))
    return True


@contextlib.contextmanager
def machine_lock():
    fd = _open_lock()
    try:
        if not _try_flock(fd, lock_path()):
            raise LockHeld("another final-run command holds %s" % lock_path())
        yield
    finally:
        os.close(fd)
