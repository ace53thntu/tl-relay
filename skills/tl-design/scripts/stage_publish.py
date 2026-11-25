"""Stage the published pages of a design set as a `conf push` page tree.

Usage: stage_publish.py <set dir> <publish dir>

Writes the tree under <publish dir>/_knowledge, because `conf push` keeps links
inside the nearest `_knowledge` ancestor. A restage keeps each page's
`confluence:` block, so the next push updates the same pages.
"""
import os
import posixpath
import re
import sys

LOCAL_TYPES = {"Note", "Notes", "Audit"}
LOCAL_DIRS = {"audits", "rounds", "sources", "specs", "_archived", "_diagrams", "publish", "runs"}
LINK = re.compile(r"(\]\()([^)#\s]+\.md)(#[^)\s]*)?(\))")
TYPE = re.compile(r"^type:\s*(.+?)\s*$", re.M)
CONFLUENCE = re.compile(r"^confluence:\n(?:[ \t]+.*\n)+", re.M)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def published(set_dir):
    pages = []
    for dirpath, dirnames, filenames in os.walk(set_dir):
        dirnames[:] = sorted(d for d in dirnames if d not in LOCAL_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            rel = posixpath.relpath(os.path.join(dirpath, name), set_dir).replace(os.sep, "/")
            if not name.endswith(".md") or rel == "index.md":
                continue
            m = TYPE.search(_read(os.path.join(set_dir, rel)))
            if m and m.group(1).strip("\"'") in LOCAL_TYPES:
                continue
            pages.append(rel)
    return pages


def placement(set_dir, pages):
    moves = {"overview.md": "index.md"}
    for rel in pages:
        m = re.fullmatch(r"lld/([^/]+)\.md", rel)
        if not m or rel == "lld/index.md":
            continue
        module = m.group(1)
        if module.endswith("-api") and os.path.isdir(os.path.join(set_dir, "lld", module[:-4], "api")):
            moves[rel] = "lld/%s/api/index.md" % module[:-4]
        elif os.path.isdir(os.path.join(set_dir, "lld", module)):
            moves[rel] = "lld/%s/index.md" % module
    return {rel: moves.get(rel, rel) for rel in pages}


def _relink(text, rel, where):
    here, there = posixpath.dirname(rel), posixpath.dirname(where[rel])

    def fix(m):
        target = posixpath.normpath(posixpath.join(here, m.group(2)))
        if target not in where:
            return m.group(0)
        return m.group(1) + posixpath.relpath(where[target], there or ".") + (m.group(3) or "") + m.group(4)

    return LINK.sub(fix, text)


def _keep_confluence(text, old):
    kept = CONFLUENCE.search(old)
    if not kept or CONFLUENCE.search(text):
        return text
    return re.sub(r"^---\n(.*?)\n---\n", lambda m: "---\n%s\n%s---\n" % (m.group(1), kept.group(0)),
                  text, count=1, flags=re.S)


def stage(set_dir, publish_dir):
    where = placement(set_dir, published(set_dir))
    root = os.path.join(publish_dir, "_knowledge")
    for rel, dest in where.items():
        text = _relink(_read(os.path.join(set_dir, rel)), rel, where)
        out = os.path.join(root, dest)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if os.path.exists(out):
            text = _keep_confluence(text, _read(out))
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
    return root


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(stage(sys.argv[1], sys.argv[2]))
