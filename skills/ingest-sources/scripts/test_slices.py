import os
import sys
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


if __name__ == "__main__":
    unittest.main()
