import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assemble as asm

HEADER = "| New criterion | Old criterion | Continuity |\n| --- | --- | --- |\n"
SLICE_A = HEADER + "| `S-01-AC1` | `US-01-AC1a` | identical |\n| `S-01-AC2` | `US-01-AC2a` | changed |\n"
SLICE_B = HEADER + "| `S-02-AC1` | — | new |\n| — | `US-16-AC1a` | withdrawn |\n| — | `US-16-AC1b` | withdrawn |\n"
OLD = ["US-01-AC1a", "US-01-AC2a", "US-16-AC1a", "US-16-AC1b"]
NEW = ["S-01-AC1", "S-01-AC2", "S-02-AC1"]
OLD_STORY = {"US-01-AC1a": "US-01", "US-01-AC2a": "US-01", "US-16-AC1a": "US-16", "US-16-AC1b": "US-16"}


class AssembleTest(unittest.TestCase):
    def rows(self, a=SLICE_A, b=SLICE_B):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for name, text in (("slice-A.md", a), ("slice-B.md", b)):
                paths.append(os.path.join(d, name))
                with open(paths[-1], "w", encoding="utf-8") as fh:
                    fh.write(text)
            return asm.read_slices(paths)

    def test_clean_slices_count_every_verdict(self):
        counts, errors = asm.check(self.rows(), NEW, OLD)
        self.assertEqual(errors, [])
        self.assertEqual(counts, {"changed": 1, "identical": 1, "new": 1, "reworded": 0, "withdrawn": 2})

    def test_ids_to_scan_add_a_story_whose_criteria_were_all_withdrawn(self):
        self.assertEqual(asm.ids_to_scan(self.rows(), OLD_STORY), ["US-01-AC2a", "US-16", "US-16-AC1a", "US-16-AC1b"])

    def test_a_missing_ruling_is_an_error(self):
        _, errors = asm.check(self.rows(b=SLICE_B.rsplit("| — | `US-16-AC1b`", 1)[0]), NEW, OLD)
        self.assertIn("old US-16-AC1b ruled 0 times", errors)

    def test_a_double_ruling_is_an_error(self):
        _, errors = asm.check(self.rows(a=SLICE_A + "| `S-02-AC1` | `US-16-AC1a` | reworded |\n"), NEW, OLD)
        self.assertIn("new S-02-AC1 ruled 2 times", errors)
        self.assertIn("old US-16-AC1a ruled 2 times", errors)

    def test_a_new_verdict_naming_an_old_criterion_is_an_error(self):
        bad = SLICE_B.replace("| `S-02-AC1` | — | new |", "| `S-02-AC1` | `US-16-AC1a` | new |")
        _, errors = asm.check(self.rows(b=bad), NEW, OLD)
        self.assertTrue(any("new verdict must name only a new criterion" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
