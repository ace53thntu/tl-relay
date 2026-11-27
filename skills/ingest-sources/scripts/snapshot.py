#!/usr/bin/env python3
"""Copy a design input into raw/projects/<handle>/<date>/<kind>/ and record it in the tl-design state."""
import argparse
import json
import os
import shutil
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tl-design", "scripts"))
import state as st  # noqa: E402
sys.path.insert(0, HERE)
import digest as dg  # noqa: E402


def snapshot(knowledge_root, handle, kind, src, received, state, check=False):
    digest = dg.file_sha256(src)
    content = dg.content_sha256(src)
    for s in state["sources"]:
        if s["sha256"] == digest or s.get("content_sha256", s["sha256"]) == content:
            return {"duplicate_of": s["path"], "sha256": digest,
                    "content_sha256": content, "path": None}
    rel = "/".join(["raw", "projects", handle, received, kind, os.path.basename(src)])
    if not st.ARCHIVE.match(rel):
        raise st.StateError(f"cannot archive as {rel!r}: a path segment is empty, . or .., or holds a newline, DEL, a C1 control other than U+0085, U+FFFE or U+FFFF")
    dest = os.path.join(knowledge_root, rel)
    if os.path.exists(dest):
        if dg.file_sha256(dest) != digest:
            raise st.StateError(f"{rel} already exists with different content")
    if check:
        return {"duplicate_of": None, "sha256": digest, "content_sha256": content, "path": None}
    if not os.path.exists(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)
    return {"duplicate_of": None, "sha256": digest, "content_sha256": content, "path": rel}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--knowledge-root", required=True)
    p.add_argument("--handle", required=True)
    p.add_argument("--kind", required=True, choices=sorted(st.KINDS))
    p.add_argument("--label", required=True)
    p.add_argument("--received", required=True)
    p.add_argument("--check", action="store_true")
    p.add_argument("source")
    a = p.parse_args(argv)
    try:
        if not st.DATE.match(a.received):
            raise st.StateError(f"--received must be YYYY-MM-DD, got {a.received}")
        if "\n" in a.label or st.UNPRINTABLE.search(a.label):
            raise st.StateError(f"label must be one line with no DEL, C1 control other than U+0085, U+FFFE or U+FFFF, got {a.label!r}")
        path = st.index_path(a.knowledge_root, a.handle)
        state = st.load(path)
        out = snapshot(a.knowledge_root, a.handle, a.kind, a.source, a.received, state, check=a.check)
        out["baseline"] = None
        if out["duplicate_of"] is None and not a.check:
            out["baseline"] = st.add_source(state, a.kind, a.label, a.received, out["sha256"],
                                            out["path"], out["content_sha256"])
            st.save(path, state)
        print(json.dumps(out, ensure_ascii=False))
        return 0
    except (st.StateError, OSError, zipfile.BadZipFile) as e:
        print(f"snapshot: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
