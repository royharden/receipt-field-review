"""Owner-private local files and a batch mutex, acquired before the decision journal lock."""

import math
import os
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class BatchError(RuntimeError):
    """Closed diagnostic codes, never underlying paths or private contents."""


def plain(path: Path, *, directory=False):
    info = path.lstat()
    if (
        stat.S_ISLNK(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
        or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        or (not directory and info.st_nlink != 1)
    ):
        raise BatchError("nonplain_private_path")


def read(path: Path, maximum: int):
    plain(path)
    if path.stat().st_size > maximum:
        raise BatchError("private_file_limit")
    with path.open("rb") as handle:
        data = handle.read(maximum + 1)
    if len(data) > maximum:
        raise BatchError("private_file_limit")
    return data


def immutable(path: Path, data: bytes):
    if os.path.lexists(path):
        if read(path, len(data)) != data:
            raise BatchError("immutable_file_conflict")
        return
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def atomic(path: Path, data: bytes):
    if os.path.lexists(path):
        plain(path)
    temporary = path.parent / ("pending-" + uuid.uuid4().hex)
    # A failed temporary file is preserved for diagnosis; no automatic repair/truncation.
    immutable(temporary, data)
    os.replace(temporary, path)


@contextmanager
def batch_mutex(root: Path, deadline_s=5.0):
    if type(deadline_s) not in (int, float) or not math.isfinite(deadline_s) or deadline_s <= 0:
        raise ValueError("bounded_positive_lock_deadline_required")
    plain(root, directory=True)
    path = root / "batch.lock"
    if os.path.lexists(path):
        plain(path)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    acquired = False
    try:
        plain(path)
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"\0")
        end = time.monotonic() + deadline_s
        while not acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError:
                if time.monotonic() >= end:
                    raise BatchError("batch_lock_deadline") from None
                time.sleep(0.01)
        yield
    finally:
        if acquired:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
