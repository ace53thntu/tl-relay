import os
import shutil
import tempfile
import unittest

import stage_publish as sp


def page(kind, title, body=""):
    return "---\ntype: %s\ntitle: \"%s\"\n---\n\n# %s\n\n%s\n" % (kind, title, title, body)


class StagePublishTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.set = os.path.join(self.tmp, "set")
        self.out = os.path.join(self.tmp, "publish")
        files = {
            "index.md": "# set\n<!-- tl-design:state -->\n",
            "overview.md": page("HLD", "Overview", "[UC-1](use-cases/uc-1.md) and [LLD](lld/bk.md#rules)"),
            "use-cases/index.md": page("HLD", "Use cases", "[Overview](../overview.md#terms)"),
            "use-cases/uc-1.md": page("HLD", "UC-1", "[API](../lld/bk-api.md)"),
            "lld/index.md": page("LLD", "LLDs", "[BK](bk.md)"),
            "lld/bk.md": page("LLD", "BK LLD", "[logic](bk/execution-logic.md)"),
            "lld/bk-api.md": page("LLD", "BK API", "[4.1](bk/api/4-1-post-bookings.md)"),
            "lld/bk/execution-logic.md": page("LLD", "BK logic", "[parent](../bk.md)"),
            "lld/bk/api/4-1-post-bookings.md": page("LLD", "API 4.1", "[API page](../../bk-api.md)"),
            "decisions.md": page("Note", "ledger"),
            "implementation-notes.md": page("Notes", "notes"),
            "audits/drift.md": page("Audit", "drift"),
            "rounds/hla-r1/x.md": page("HLD", "x"),
        }
        for rel, text in files.items():
            path = os.path.join(self.set, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

    def staged(self):
        root = os.path.join(self.out, "_knowledge")
        return sorted(os.path.relpath(os.path.join(d, f), root)
                      for d, _, fs in os.walk(root) for f in fs if f.endswith(".md"))

    def read(self, rel):
        with open(os.path.join(self.out, "_knowledge", rel), encoding="utf-8") as f:
            return f.read()

    def test_stages_only_published_pages_as_a_tree(self):
        sp.stage(self.set, self.out)
        self.assertEqual(self.staged(), [
            "index.md", "lld/bk/api/4-1-post-bookings.md", "lld/bk/api/index.md",
            "lld/bk/execution-logic.md", "lld/bk/index.md", "lld/index.md",
            "use-cases/index.md", "use-cases/uc-1.md"])
        self.assertIn("title: \"Overview\"", self.read("index.md"))

    def test_skips_publish_and_runs_and_does_not_nest(self):
        for rel in ("publish/x.md", "runs/r1/run-state.md"):
            path = os.path.join(self.set, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(page("HLD", "x"))
        sp.stage(self.set, os.path.join(self.set, "publish"))
        sp.stage(self.set, os.path.join(self.set, "publish"))
        self.assertEqual(sp.published(self.set).count("publish/x.md"), 0)
        self.assertFalse([p for p in sp.published(self.set) if p.startswith(("publish/", "runs/"))])
        self.assertFalse(os.path.exists(os.path.join(self.set, "publish", "_knowledge", "publish")))
        self.assertFalse(os.path.exists(os.path.join(self.set, "publish", "_knowledge", "runs")))

    def test_rewrites_links_to_the_moved_pages(self):
        sp.stage(self.set, self.out)
        self.assertIn("(lld/bk/index.md#rules)", self.read("index.md"))
        self.assertIn("(../index.md#terms)", self.read("use-cases/index.md"))
        self.assertIn("(../lld/bk/api/index.md)", self.read("use-cases/uc-1.md"))
        self.assertIn("(bk/index.md)", self.read("lld/index.md"))
        self.assertIn("(execution-logic.md)", self.read("lld/bk/index.md"))
        self.assertIn("(index.md)", self.read("lld/bk/execution-logic.md"))
        self.assertIn("(index.md)", self.read("lld/bk/api/4-1-post-bookings.md"))

    def test_a_restage_keeps_the_confluence_block_of_a_pushed_page(self):
        sp.stage(self.set, self.out)
        path = os.path.join(self.out, "_knowledge", "index.md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace("---\n\n", "confluence:\n  page_id: 42\n  version: 3\n---\n\n", 1))
        sp.stage(self.set, self.out)
        self.assertIn("confluence:\n  page_id: 42\n  version: 3\n", self.read("index.md"))


if __name__ == "__main__":
    unittest.main()
