#!/usr/bin/env python3
"""List the page sections that cite given identifiers, after collapsing whitespace and line-broken hyphens."""
import argparse
import json
import os
import re
import sys

HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")


def sections(text):
    current, buf, out, in_fence = "(top)", [], [], False
    for line in text.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
        m = None if in_fence else HEADING.match(line)
        if m:
            out.append((current, "\n".join(buf)))
            current, buf = m.group(1), [line]
        else:
            buf.append(line)
    out.append((current, "\n".join(buf)))
    return out


def pattern(ids):
    alternatives = "|".join(re.escape(i) + (r"(?!\*)" if i.endswith("*") else "") for i in sorted(ids, key=len, reverse=True))
    return re.compile(r"(?<![\w-])(" + alternatives + r")(?![\w-])")


def flatten(text):
    return re.sub(r"\s+", " ", re.sub(r"-[ \t]*\n\s*", "-", text))


def scan(root, ids):
    pat, hits = pattern(ids), []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in ("node_modules", ".git") and not (dirpath == root and d in ("publish", "runs")))
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for heading, body in sections(text):
                found = sorted(set(pat.findall(flatten(body))))
                if found:
                    hits.append((os.path.relpath(path, root), heading, found))
    return hits


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--ids-file", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    with open(a.ids_file, encoding="utf-8") as fh:
        ids = [line.strip() for line in fh if line.strip()]
    if not ids:
        raise SystemExit("impact: the ids file is empty")
    hits = scan(a.root, ids)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write("page\tsection\tids\n")
        fh.write("".join(f"{page}\t{section}\t{','.join(found)}\n" for page, section, found in hits))
    print(json.dumps({"sections": len(hits), "pages": len({h[0] for h in hits})}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
