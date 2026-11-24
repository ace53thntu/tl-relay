#!/usr/bin/env python3
"""Two digests for a design input: its bytes, and its content ignoring volatile metadata."""
import hashlib
import zipfile

# An Office package stamps the save moment into this part, so two runs of the same
# decrypt-and-save over one arriving file differ here and nowhere else.
VOLATILE = ("docProps/core.xml",)


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def content_sha256(path):
    if not zipfile.is_zipfile(path):
        return file_sha256(path)
    h = hashlib.sha256()
    with zipfile.ZipFile(path) as z:
        for name in sorted(z.namelist()):
            if name in VOLATILE:
                continue
            h.update(name.encode("utf-8"))
            h.update(b"\0")
            h.update(hashlib.sha256(z.read(name)).digest())
    return h.hexdigest()
