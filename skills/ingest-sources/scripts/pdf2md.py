#!/usr/bin/env python3
"""Extract the text of a PDF page by page into Markdown. Run it with a Python that has the skill's requirements installed."""
import argparse
import hashlib
import os
import sys

try:
    from pypdf import PdfReader
except ImportError as e:
    if isinstance(e, ModuleNotFoundError) and e.name == "pypdf":
        d = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.exit(f"pdf2md: pypdf is missing; run `python3 -m venv {d}/.venv && {d}/.venv/bin/python -m pip install -r {d}/requirements.txt` and use that Python")
    sys.exit(f"pdf2md: pypdf failed to import: {e}")


def convert(path):
    reader = PdfReader(path)
    parts = [f"## Page {n}\n\n{(page.extract_text() or '').strip()}\n" for n, page in enumerate(reader.pages, 1)]
    return len(reader.pages), "\n".join(parts)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pdf")
    p.add_argument("--out")
    a = p.parse_args(argv)
    pages, md = convert(a.pdf)
    with open(a.pdf, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    base = os.path.basename(a.pdf)
    text = f"# {os.path.splitext(base)[0]}\n\nConverted from `{base}`, {pages} pages, sha256 `{digest}`.\n\n{md}"
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
