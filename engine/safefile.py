# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Diego Bergonsi. Part of steam-case-covers: https://github.com/diegobergonsi/steam-case-covers
"""The one way the app reads a small file that the user, or anything else, controls (a game list, a saved page, the settings, the groups).
A named pipe would block for ever, a device such as /dev/zero never ends, and a huge file fills the memory: so only a regular file of at most
`limit` bytes is read, and it is checked again on the open file, because the folder may change between a look and the open."""
import errno, os, stat


class UnsafeFile(OSError):
    """The file is not one to read. An OSError, so a caller that already catches those needs no change."""


class NotRegularFile(UnsafeFile):
    """A folder, a named pipe, a device, or (unless links are followed) a link."""


class FileTooBig(UnsafeFile):
    pass


def open_regular(path, limit, follow_links=False):
    """The open binary file at `path` (the caller closes it), once it is checked on the open descriptor: a regular file of at most `limit` bytes.
    Raises NotRegularFile, FileTooBig, or the OSError of the open. A link is refused unless `follow_links`; even then what it leads to must be a regular file."""
    if not follow_links and not stat.S_ISREG(os.lstat(path).st_mode):
        raise NotRegularFile("not a regular file: %s" % path)
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0) | (0 if follow_links else getattr(os, "O_NOFOLLOW", 0))
    try:
        fd = os.open(path, flags)
    except OSError as e:
        if e.errno == errno.ELOOP:                               # O_NOFOLLOW met a link
            raise NotRegularFile("not a regular file: %s" % path) from e
        raise
    f = os.fdopen(fd, "rb")
    try:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise NotRegularFile("not a regular file: %s" % path)
        if info.st_size > limit:
            raise FileTooBig("more than %d bytes: %s" % (limit, path))
    except BaseException:
        f.close()
        raise
    return f


def read_small_file(path, limit, follow_links=False):
    """The bytes of the regular file at `path`, at most `limit` of them.
    Raises NotRegularFile, FileTooBig, or the OSError of the open (missing file, no permission...). A link is refused unless `follow_links`;
    even then what it leads to must be a regular file, so a link to /dev/zero is refused."""
    with open_regular(path, limit, follow_links) as f:
        raw = f.read(limit + 1)                                  # a file that grew since the check is caught here
    if len(raw) > limit:
        raise FileTooBig("more than %d bytes: %s" % (limit, path))
    return raw
