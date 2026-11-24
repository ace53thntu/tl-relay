from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import pathlib


class LockHeld(Exception):
    pass


class LockError(Exception):
    pass


class HomeError(LockError):
    pass


def _home() -> pathlib.Path:
    value = os.environ.get("AI_SDLC_HOME")
    if not value:
        raise LockError("AI_SDLC_HOME is not set")
    home = pathlib.Path(value)
    if not (home / "ai-sdlc.yaml").is_file():
        raise HomeError("%s has no ai-sdlc.yaml, so it is not an ai-sdlc home" % home)
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
