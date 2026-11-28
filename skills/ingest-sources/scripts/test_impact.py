import contextlib
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import impact as im

PAGE = """# Documents

## Decision 19

The reminder sweep rests on US-16-AC1a, US-16-
  AC1b and on `US-160-AC1a`.

## Unrelated

US-13 is cited here.

```text
## Not a heading, and US-16-AC1b is cited in code
```
"""
STORY = "## US-16 — reminder\n\nThe story itself.\n"


class ImpactTest(unittest.TestCase):
    def test_finds_ids_across_line_breaks_and_code_but_not_inside_longer_ids(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "sub"))
            with open(os.path.join(d, "page.md"), "w", encoding="utf-8") as fh:
                fh.write(PAGE)
            with open(os.path.join(d, "sub", "story.md"), "w", encoding="utf-8") as fh:
                fh.write(STORY)
            hits = im.scan(d, ["US-16-AC1a", "US-16-AC1b", "S-13", "US-16"])
        self.assertEqual(hits, [
            ("page.md", "Decision 19", ["US-16-AC1a", "US-16-AC1b"]),
            ("page.md", "Unrelated", ["US-16-AC1b"]),
            (os.path.join("sub", "story.md"), "US-16 — reminder", ["US-16"]),
        ])

    BOTH = ["US-01-AC1*", "US-01-AC1"]

    def test_a_bold_plain_id_does_not_hit_the_starred_id(self):
        find = im.matcher(self.BOTH)
        self.assertEqual(find("see **US-01-AC1** here"), ["US-01-AC1"])
        self.assertEqual(find("see US-01-AC1* here"), ["US-01-AC1*"])

    def test_a_bold_starred_id_still_matches_the_starred_id(self):
        self.assertEqual(im.matcher(self.BOTH)("see **US-01-AC1*** here"), ["US-01-AC1*"])
        self.assertEqual(im.matcher(["US-01-AC1*"])("see **US-01-AC1*** here"), ["US-01-AC1*"])
        self.assertEqual(im.matcher(self.BOTH)("see **US-01-AC1**."), ["US-01-AC1"])

    def test_counts_stars_on_both_sides(self):
        find = im.matcher(self.BOTH)
        self.assertEqual(find("***US-01-AC1***"), ["US-01-AC1"])
        self.assertEqual(find("*US-01-AC1**"), ["US-01-AC1*"])
        self.assertEqual(find("*US-01-AC1*"), ["US-01-AC1"])
        self.assertEqual(find("`US-01-AC1*`"), ["US-01-AC1*"])
        self.assertEqual(im.matcher(["US-01-AC1*"])("*US-01-AC1**"), ["US-01-AC1*"])

    def test_falls_back_to_the_listed_sibling(self):
        self.assertEqual(im.matcher(["US-01-AC1*"])("US-01-AC1"), ["US-01-AC1*"])
        self.assertEqual(im.matcher(["US-01-AC1"])("US-01-AC1* here"), ["US-01-AC1"])

    def test_reports_every_sibling_when_no_spelling_matches(self):
        self.assertEqual(im.matcher(["US-01-AC1*", "US-01-AC1**"])("US-01-AC1"), ["US-01-AC1*", "US-01-AC1**"])
        self.assertEqual(im.matcher(self.BOTH)("**see US-01-AC1**"), ["US-01-AC1", "US-01-AC1*"])

    def test_skips_publish_and_runs_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            for rel in ("publish/x.md", "runs/r1/run-state.md"):
                os.makedirs(os.path.join(d, os.path.dirname(rel)))
                with open(os.path.join(d, rel), "w", encoding="utf-8") as fh:
                    fh.write(STORY)
            self.assertEqual(im.scan(d, ["US-16"]), [])

    def test_keeps_nested_publish_and_runs_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            for rel in ("lld/runs/api/index.md", "lld/publish/x.md", "runs/r1/y.md"):
                os.makedirs(os.path.join(d, os.path.dirname(rel)))
                with open(os.path.join(d, rel), "w", encoding="utf-8") as fh:
                    fh.write(STORY)
            pages = sorted(h[0] for h in im.scan(d, ["US-16"]))
        self.assertEqual(pages, [os.path.join("lld", "publish", "x.md"), os.path.join("lld", "runs", "api", "index.md")])

    def run_main(self, ids_text, page_text=None):
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, "root")
            os.makedirs(root)
            if page_text is not None:
                with open(os.path.join(root, "story.md"), "w", encoding="utf-8") as fh:
                    fh.write(page_text)
            ids = os.path.join(d, "ids.txt")
            with open(ids, "w", encoding="utf-8") as fh:
                fh.write(ids_text)
            out = os.path.join(d, "impact.tsv")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = im.main(["--root", root, "--ids-file", ids, "--out", out])
            with open(out, encoding="utf-8") as fh:
                return code, fh.read(), buf.getvalue()

    def test_main_ignores_a_stars_only_id_line(self):
        code, tsv, _ = self.run_main("*\nUS-16\n", STORY + "\nThe gateway drops it.\n")
        self.assertEqual(code, 0)
        self.assertEqual(tsv, "page\tsection\tids\nstory.md\tUS-16 — reminder\tUS-16\n")

    def assert_header_only(self, ids_text):
        with mock.patch.object(im, "scan", side_effect=AssertionError("scan called")):
            code, tsv, out = self.run_main(ids_text, STORY)
        self.assertEqual((code, tsv, out), (0, "page\tsection\tids\n", '{"sections": 0, "pages": 0}\n'))

    def test_main_writes_a_header_only_tsv_for_an_empty_ids_file(self):
        self.assert_header_only("")

    def test_main_writes_a_header_only_tsv_for_an_ids_file_of_only_stars(self):
        self.assert_header_only("*\n**\n")


if __name__ == "__main__":
    unittest.main()
