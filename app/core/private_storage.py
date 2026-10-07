"""Small POSIX storage primitives for private cache and diagnostic directories."""

import os
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def private_directory(path: Path) -> Iterator[int]:
    """Pin an owned, non-symlink directory before accessing any child files.

    Legacy owned 0755 directories are made private; directories another user
    could already have populated (group/world writable) are refused. A pinned
    directory descriptor prevents subsequent path swaps redirecting file I/O.
    """
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise PermissionError("storage directory must be owned and not writable by other users")
        os.fchmod(descriptor, 0o700)
        yield descriptor
    finally:
        os.close(descriptor)


def _validate_name(name: str) -> None:
    if name in {"", ".", ".."} or "/" in name or "\\" in name:
        raise ValueError("storage filename must be a basename")


def read_private_file(directory: int, name: str, *, max_bytes: int) -> bytes:
    """Read one owned regular file with bounded size, refusing links and FIFOs."""
    _validate_name(name)
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1 or info.st_mode & 0o022:
            raise PermissionError("storage file must be an owned regular file without external writers or links")
        if info.st_size > max_bytes:
            raise ValueError("storage file exceeds size limit")
        data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("storage file exceeds size limit")
        return data


def write_private_file(directory: int, name: str, data: bytes, *, replace: bool = False) -> None:
    """Create a 0600 file exclusively; replace cache entries via unique scratch files."""
    _validate_name(name)
    scratch = f".{name}.{secrets.token_hex(16)}.tmp" if replace else name
    descriptor = os.open(scratch, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        if replace:
            os.replace(scratch, name, src_dir_fd=directory, dst_dir_fd=directory)
    except BaseException:
        os.unlink(scratch, dir_fd=directory)
        raise
