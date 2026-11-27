import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slices as sl

NEW = [{"id": f"S-{s:02d}-AC{i}", "story": f"S-{s:02d}"} for s in range(1, 11) for i in range(1, 4)]
PAIRED = {"S-01-AC1": "US-01-AC1a", "S-09-AC1": "US-09-AC1a"}
PAIRS = [{"new_id": n["id"], "old_id": PAIRED.get(n["id"], "")} for n in NEW]
OLD = [{"id": "US-01-AC1a", "story": "US-01"}, {"id": "US-01-AC9z", "story": "US-01"},
       {"id": "US-09-AC1a", "story": "US-09"}, {"id": "US-77-AC1a", "story": "US-77"}]
UNCLAIMED = ["US-01-AC9z", "US-77-AC1a"]


class SlicesTest(unittest.TestCase):
    def setUp(self):
        self.slices = sl.make_slices(NEW, PAIRS, OLD, UNCLAIMED, 3)

    def test_every_new_criterion_lands_in_exactly_one_slice_and_no_story_splits(self):
        self.assertEqual([s["name"] for s in self.slices], ["A", "B", "C"])
        ids = [i for s in self.slices for i in s["new_ids"]]
        self.assertEqual(sorted(ids), sorted(n["id"] for n in NEW))
        for s in self.slices:
            for story in s["stories"]:
                self.assertTrue(all(i in s["new_ids"] for i in (n["id"] for n in NEW if n["story"] == story)))

    def test_an_unpaired_old_criterion_follows_its_story_or_goes_to_the_smallest_slice(self):
        where = {i: s["name"] for s in self.slices for i in s["rule_on"]}
        self.assertEqual(where["US-01-AC9z"], "A")
        self.assertEqual(where["US-77-AC1a"], "B")

    def test_count_is_bounded(self):
        with self.assertRaises(SystemExit):
            sl.make_slices(NEW, PAIRS, OLD, UNCLAIMED, 9)


class SlicesMainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = tmp.name
        self.new, self.old = os.path.join(d, "new.jsonl"), os.path.join(d, "old.jsonl")
        self.pairs, self.unc = os.path.join(d, "pairs.tsv"), os.path.join(d, "unclaimed.txt")
        self.out = os.path.join(d, "slices.json")
        self.write_jsonl(self.new, NEW)
        self.write_jsonl(self.old, OLD)
        with open(self.pairs, "w", encoding="utf-8") as fh:
            fh.write("new_id\told_id\tkind\trule_changed\tratio\n")
            for p in PAIRS:
                fh.write(f"{p['new_id']}\t{p['old_id']}\t\t\t\n")
        with open(self.unc, "w", encoding="utf-8") as fh:
            fh.write("".join(i + "\n" for i in UNCLAIMED))

    def write_jsonl(self, path, rows):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in rows))

    def run_main(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sl.main(["--new", self.new, "--old", self.old, "--pairs", self.pairs,
                            "--unclaimed", self.unc, "--count", "3", "--out", self.out])
        return code, out.getvalue(), err.getvalue()

    def test_main_rejects_a_missing_register(self):
        os.remove(self.new)
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(len(err.splitlines()), 1)
        self.assertTrue(err.startswith(f"slices: cannot read {self.new}: "))

    def test_main_rejects_a_line_that_is_not_json(self):
        with open(self.old, "w", encoding="utf-8") as fh:
            fh.write('{"id": "US-01-AC1a"')
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(len(err.splitlines()), 1)
        self.assertTrue(err.startswith(f"slices: cannot read {self.old}: "))

    def test_main_rejects_a_list_story(self):
        rows = [dict(o) for o in OLD]
        rows[2]["story"] = ["US-09"]
        self.write_jsonl(self.old, rows)
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(err, f"slices: cannot read {self.old}: row 3: 'story' must be a non-empty string\n")

    def test_main_rejects_a_null_new_id(self):
        rows = [dict(n) for n in NEW]
        rows[0]["id"] = None
        self.write_jsonl(self.new, rows)
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(err, f"slices: cannot read {self.new}: row 1: 'id' must be a non-empty string\n")

    def test_main_rejects_a_missing_unclaimed_file(self):
        os.remove(self.unc)
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(len(err.splitlines()), 1)
        self.assertTrue(err.startswith(f"slices: cannot read {self.unc}: "))

    def test_main_rejects_a_malformed_pairs_tsv(self):
        with open(self.pairs, "wb") as fh:
            fh.write(b"new_id\told_id\n" + b"x" * 200000 + b"\n")
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(len(err.splitlines()), 1)
        self.assertTrue(err.startswith(f"slices: cannot read {self.pairs}: "))

    def test_main_rejects_a_repeated_new_id(self):
        rows = [dict(n) for n in NEW]
        rows[5]["id"] = rows[4]["id"]
        self.write_jsonl(self.new, rows)
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(err, f"slices: cannot read {self.new}: row 6: id 'S-02-AC2' repeats row 5\n")
        self.assertFalse(os.path.exists(self.out))

    def test_main_rejects_a_repeated_old_id(self):
        rows = [dict(o) for o in OLD]
        rows[2]["id"] = "US-01-AC9z"
        self.write_jsonl(self.old, rows)
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(err, f"slices: cannot read {self.old}: row 3: id 'US-01-AC9z' repeats row 2\n")
        self.assertFalse(os.path.exists(self.out))

    def test_main_reports_the_first_repeat_only(self):
        rows = [dict(n) for n in NEW]
        rows[4]["id"] = rows[5]["id"] = rows[3]["id"]
        self.write_jsonl(self.new, rows)
        code, _, err = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(err, f"slices: cannot read {self.new}: row 5: id 'S-02-AC1' repeats row 4\n")
        self.assertFalse(os.path.exists(self.out))

    def test_main_accepts_an_id_in_both_registers(self):
        self.write_jsonl(self.old, OLD + [{"id": "S-01-AC1", "story": "US-50"}])
        code, _, _ = self.run_main()
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
