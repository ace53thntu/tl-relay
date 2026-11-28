import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pair as pr

WS = "must not carry surrounding whitespace"

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


def run_main(old_rows, new_rows, raw_new=None, drop_old=False):
    with tempfile.TemporaryDirectory() as d:
        old, new = os.path.join(d, "old.jsonl"), os.path.join(d, "new.jsonl")
        out, unc = os.path.join(d, "pairs.tsv"), os.path.join(d, "unclaimed.txt")
        if not drop_old:
            with open(old, "w", encoding="utf-8") as fh:
                fh.write("".join(json.dumps(r) + "\n" for r in old_rows))
        with open(new, "w", encoding="utf-8") as fh:
            fh.write(raw_new if raw_new is not None else "".join(json.dumps(r) + "\n" for r in new_rows))
        so, se = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(so), contextlib.redirect_stderr(se):
            code = pr.main(["--old", old, "--new", new, "--out", out, "--unclaimed", unc])
        tsv = open(out, encoding="utf-8").read() if os.path.exists(out) else ""
        return code, se.getvalue(), old, new, tsv


class MainReadErrorTest(unittest.TestCase):
    def test_main_rejects_a_missing_register(self):
        code, err, old, _, _ = run_main(OLD, NEW, drop_old=True)
        self.assertEqual(code, 1)
        self.assertEqual(len(err.splitlines()), 1)
        self.assertTrue(err.startswith(f"pair: cannot read {old}: "))

    def test_main_rejects_a_line_that_is_not_json(self):
        code, err, _, new, _ = run_main(OLD, NEW, raw_new='{"id": "S-01-AC1"')
        self.assertEqual(code, 1)
        self.assertEqual(len(err.splitlines()), 1)
        self.assertTrue(err.startswith(f"pair: cannot read {new}: "))

    def test_main_rejects_a_bad_id(self):
        new_rows = [NEW[0], dict(NEW[1], id=["S-02-AC1"]), NEW[2]]
        code, err, _, new, _ = run_main(OLD, new_rows)
        self.assertEqual(code, 1)
        self.assertEqual(err, f"pair: cannot read {new}: row 2: 'id' must be a non-empty string\n")

    def test_main_rejects_a_leading_space_in_a_new_id(self):
        new_rows = [NEW[0], dict(NEW[1], id=" S-02-AC1"), NEW[2]]
        code, err, _, new, _ = run_main(OLD, new_rows)
        self.assertEqual(code, 1)
        self.assertEqual(err, f"pair: cannot read {new}: row 2: 'id' {WS}\n")

    def test_main_rejects_a_trailing_space_in_an_old_id(self):
        old_rows = OLD[:2] + [dict(OLD[2], id="US-16-AC1a ")]
        code, err, old, _, _ = run_main(old_rows, NEW)
        self.assertEqual(code, 1)
        self.assertEqual(err, f"pair: cannot read {old}: row 3: 'id' {WS}\n")

    def test_main_rejects_a_trailing_tab_in_a_new_id(self):
        new_rows = [NEW[0], dict(NEW[1], id="S-02-AC1\t"), NEW[2]]
        code, err, _, new, _ = run_main(OLD, new_rows)
        self.assertEqual(code, 1)
        self.assertEqual(err, f"pair: cannot read {new}: row 2: 'id' {WS}\n")

    def test_main_rejects_an_lf_inside_a_new_id(self):
        new_rows = [NEW[0], dict(NEW[1], id="S-02\nAC1"), NEW[2]]
        code, err, _, new, _ = run_main(OLD, new_rows)
        self.assertEqual(code, 1)
        self.assertEqual(err, f"pair: cannot read {new}: row 2: 'id' holds U+000A\n")

    def test_main_rejects_an_nbsp_inside_a_new_id(self):
        new_rows = [NEW[0], dict(NEW[1], id="S-02\u00a0AC1"), NEW[2]]
        code, err, _, new, _ = run_main(OLD, new_rows)
        self.assertEqual(code, 1)
        self.assertEqual(err, f"pair: cannot read {new}: row 2: 'id' holds U+00A0\n")

    def test_main_accepts_a_space_inside_an_id(self):
        new_rows = [NEW[0], dict(NEW[1], id="S 02-AC1"), NEW[2]]
        code, _, _, _, _ = run_main(OLD, new_rows)
        self.assertEqual(code, 0)

    def test_main_rejects_a_null_scenario(self):
        old_rows = OLD[:2] + [dict(OLD[2], scenario=None)]
        code, err, old, _, _ = run_main(old_rows, NEW)
        self.assertEqual(code, 1)
        self.assertEqual(err, f"pair: cannot read {old}: row 3: 'scenario' must be a string\n")

    def test_main_accepts_an_empty_rule(self):
        new_rows = NEW[:2] + [dict(NEW[2], rule="")]
        code, _, _, _, tsv = run_main(OLD, new_rows)
        self.assertEqual(code, 0)
        self.assertEqual(len(tsv.splitlines()), 4)

    def test_main_rejects_a_repeated_old_id(self):
        old_rows = OLD[:2] + [dict(OLD[2], id="US-01-AC1a")]
        code, err, old, _, tsv = run_main(old_rows, NEW)
        self.assertEqual(code, 1)
        self.assertEqual(err, f"pair: cannot read {old}: row 3: id 'US-01-AC1a' repeats row 1\n")
        self.assertEqual(tsv, "")

    def test_main_rejects_a_repeated_new_id(self):
        new_rows = [NEW[0], dict(NEW[1], id="S-01-AC1"), NEW[2]]
        code, err, _, new, tsv = run_main(OLD, new_rows)
        self.assertEqual(code, 1)
        self.assertEqual(err, f"pair: cannot read {new}: row 2: id 'S-01-AC1' repeats row 1\n")
        self.assertEqual(tsv, "")

    def test_main_reports_the_first_repeat_only(self):
        new_rows = [NEW[0], dict(NEW[1], id="S-01-AC1"), dict(NEW[2], id="S-01-AC1")]
        code, err, _, new, tsv = run_main(OLD, new_rows)
        self.assertEqual(code, 1)
        self.assertEqual(err, f"pair: cannot read {new}: row 2: id 'S-01-AC1' repeats row 1\n")
        self.assertEqual(tsv, "")

    def test_main_skips_blank_lines_when_numbering_a_repeat(self):
        raw_new = json.dumps(NEW[0]) + "\n\n" + json.dumps(dict(NEW[1], id="S-01-AC1")) + "\n"
        code, err, _, new, tsv = run_main(OLD, NEW, raw_new=raw_new)
        self.assertEqual(code, 1)
        self.assertEqual(err, f"pair: cannot read {new}: row 2: id 'S-01-AC1' repeats row 1\n")
        self.assertEqual(tsv, "")

    def test_main_reports_a_field_error_before_a_repeat(self):
        new_rows = [NEW[0], dict(NEW[1], id="S-01-AC1"), dict(NEW[2], id=None)]
        code, err, _, new, tsv = run_main(OLD, new_rows)
        self.assertEqual(code, 1)
        self.assertEqual(err, f"pair: cannot read {new}: row 3: 'id' must be a non-empty string\n")
        self.assertEqual(tsv, "")

    def test_main_accepts_an_id_in_both_registers(self):
        new_rows = [dict(NEW[0], id="US-01-AC1a"), NEW[1], NEW[2]]
        code, _, _, _, tsv = run_main(OLD, new_rows)
        self.assertEqual(code, 0)
        self.assertEqual(len(tsv.splitlines()), 4)


if __name__ == "__main__":
    unittest.main()
