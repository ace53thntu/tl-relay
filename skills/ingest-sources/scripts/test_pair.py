import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pair as pr

OLD = [{"id": "US-01-AC1a", "story": "US-01", "scenario": "Given a visitor\nWhen they open the app", "rule": "Only SSO."},
       {"id": "US-01-AC2a", "story": "US-01", "scenario": "Given a signed in user When the role is missing",
        "rule": "Show pending role screen."},
       {"id": "US-16-AC1a", "story": "US-16", "scenario": "Given a quote near expiry When the nightly sweep runs",
        "rule": "Send a reminder."}]
NEW = [{"id": "S-01-AC1", "story": "S-01", "scenario": "Given a visitor<br>When they open the app",
        "rule": "Only SSO, see [policy](x.md)."},
       {"id": "S-02-AC1", "story": "S-02", "scenario": "Given a user who signed in When the role is missing",
        "rule": "Show pending role screen."},
       {"id": "S-03-AC1", "story": "S-03", "scenario": "Import fails on bad rows", "rule": "Log it."}]


class PairTest(unittest.TestCase):
    def test_norm_drops_links_breaks_punctuation_and_case(self):
        self.assertEqual(pr.norm("See [the Policy](x.md),<br>NOW!"), "see the policy now")

    def test_exact_scenario_first_then_similarity_then_nothing(self):
        rows, unclaimed = pr.pair(OLD, NEW)
        self.assertEqual([(r["new_id"], r["old_id"], r["kind"]) for r in rows],
                         [("S-01-AC1", "US-01-AC1a", "scenario"), ("S-02-AC1", "US-01-AC2a", "similar"),
                          ("S-03-AC1", "", "")])
        self.assertEqual([r["rule_changed"] for r in rows], ["yes", "no", ""])
        self.assertEqual(unclaimed, ["US-16-AC1a"])

    def test_an_old_criterion_is_claimed_once(self):
        twin = dict(NEW[0], id="S-09-AC1")
        rows, _ = pr.pair(OLD[:1], [NEW[0], twin])
        self.assertEqual([r["old_id"] for r in rows], ["US-01-AC1a", ""])

    def test_below_the_threshold_stays_unpaired(self):
        rows, unclaimed = pr.pair(OLD[2:], NEW[2:])
        self.assertEqual((rows[0]["old_id"], unclaimed), ("", ["US-16-AC1a"]))


if __name__ == "__main__":
    unittest.main()
