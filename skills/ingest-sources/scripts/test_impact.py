import os
import sys
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
