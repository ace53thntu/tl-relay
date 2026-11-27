import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_register as g
from xlsx2md import cell_md, read_sheet

COLS = {"number": "No.", "title": "Title", "impact": "Change impact", "scenario": "Scenario", "rule": "Rule and message"}
MINT_ROWS = [["No.", "Title", "Change impact", "Scenario", "Rule and message"],
             ["1", "T1", "Low", "s1\nline2", "r|1"],
             ["1", "T1 variant", "Medium", "s2", ""],
             ["2", "T2", "Medium", "s3", "r3"],
             ["4", "T4", "Low", "s4", "r4"],
             ["", "", "", "", ""]]
ID_ROWS = [["No.", "Old ID", "Title", "Change impact", "Criterion", "Scenario", "Rule and message"],
           ["1", "**US-01**", "A", "Low", "US-01-AC1a", "x", "y"],
           ["2", "US-01", "A", "Low", "US-01-AC2a", "x2", "y2"],
           ["3", "US-05", "B", "Low", "", "", ""]]


class MintTest(unittest.TestCase):
    def setUp(self):
        self.blocks, self.criteria, self.skipped = g.build(MINT_ROWS, COLS, mint="S")

    def test_story_ids_keep_the_workbook_numbering_gap(self):
        self.assertEqual([b["story"] for b in self.blocks], ["S-01", "S-02", "S-04"])

    def test_criteria_number_in_row_order_and_the_first_title_wins(self):
        self.assertEqual([c["id"] for c in self.criteria], ["S-01-AC1", "S-01-AC2", "S-02-AC1", "S-04-AC1"])
        self.assertEqual(self.blocks[0]["title"], "T1")
        self.assertEqual(self.skipped, [6])

    def test_page_escapes_text_marks_an_empty_rule_and_takes_the_highest_impact(self):
        page = g.render_page(self.blocks)
        self.assertIn('<a id="s-01"></a>\n\n## S-01 — T1\n\nChange impact: **Medium**\n', page)
        self.assertIn("| `S-01-AC1` | Low | s1<br>line2 | r\\|1 |", page)
        self.assertIn("| `S-01-AC2` | Medium | s2 | — |", page)
        self.assertNotIn("S-03", page)

    def test_mint_and_id_column_are_exclusive(self):
        with self.assertRaises(SystemExit):
            g.build(MINT_ROWS, COLS, mint="S", id_col="Criterion", story_col="Old ID")


class IdColumnTest(unittest.TestCase):
    def test_groups_by_story_column_and_skips_rows_without_a_criterion(self):
        blocks, criteria, skipped = g.build(ID_ROWS, COLS, id_col="Criterion", story_col="Old ID")
        self.assertEqual([(b["story"], len(b["rows"])) for b in blocks], [("US-01", 2), ("US-05", 0)])
        self.assertEqual([c["id"] for c in criteria], ["US-01-AC1a", "US-01-AC2a"])
        self.assertEqual(skipped, [4])
        self.assertIn("This story carries no acceptance criteria in this revision.", g.render_page(blocks))


class RepeatTest(unittest.TestCase):
    H5 = MINT_ROWS[0]
    DUP_STORY = [H5, ["1", "T1", "Low", "a", "r"], ["2", "T2", "Low", "b", "r"], ["01", "T1b", "Low", "c", "r"]]
    DUP_ID = ID_ROWS + [["4", "US-09", "C", "Low", "US-01-AC1a", "x3", "y3"]]
    STORY_ERR = "gen_register: No. '01' at sheet row 4 and '1' at sheet row 2 both mint story S-01"
    ID_ERR = "gen_register: id 'US-01-AC1a' at sheet row 5 repeats sheet row 2"

    def assert_rejects(self, text, rows, **kw):
        with self.assertRaises(SystemExit) as cm:
            g.build(rows, COLS, **kw)
        self.assertEqual(cm.exception.code, text)

    def test_mint_rejects_two_numbers_that_mint_one_story(self):
        self.assert_rejects(self.STORY_ERR, self.DUP_STORY, mint="S")

    def test_mint_keeps_one_story_across_non_adjacent_rows(self):
        rows = [self.H5, ["1", "T1", "Low", "a", "r"], ["2", "T2", "Low", "b", "r"], ["1", "T1", "Low", "c", "r"]]
        _, criteria, _ = g.build(rows, COLS, mint="S")
        self.assertEqual([c["id"] for c in criteria], ["S-01-AC1", "S-02-AC1", "S-01-AC2"])

    def test_id_column_rejects_a_repeated_id(self):
        self.assert_rejects(self.ID_ERR, self.DUP_ID, id_col="Criterion", story_col="Old ID")

    def test_id_column_drops_bold_marks_from_an_id(self):
        rows = ID_ROWS + [["4", "US-01", "A", "Low", "**US-01-AC3a**", "x3", "y3"]]
        _, criteria, _ = g.build(rows, COLS, id_col="Criterion", story_col="Old ID")
        self.assertEqual([c["id"] for c in criteria], ["US-01-AC1a", "US-01-AC2a", "US-01-AC3a"])

    def test_id_column_catches_a_bold_repeat(self):
        rows = ID_ROWS + [["4", "US-09", "C", "Low", "**US-01-AC1a**", "x3", "y3"]]
        self.assert_rejects(self.ID_ERR, rows, id_col="Criterion", story_col="Old ID")

    def test_id_column_reports_the_first_repeat_only(self):
        rows = ID_ROWS + [["4", "US-01", "A", "Low", "US-01-AC2a", "x3", "y3"],
                          ["5", "US-01", "A", "Low", "US-01-AC1a", "x4", "y4"]]
        self.assert_rejects("gen_register: id 'US-01-AC2a' at sheet row 5 repeats sheet row 3", rows,
                            id_col="Criterion", story_col="Old ID")

    def test_id_column_reports_the_second_of_three(self):
        rows = ID_ROWS + [["4", "US-01", "A", "Low", "US-01-AC1a", "x3", "y3"],
                          ["5", "US-01", "A", "Low", "US-01-AC1a", "x4", "y4"]]
        self.assert_rejects(self.ID_ERR, rows, id_col="Criterion", story_col="Old ID")

    def assert_main_writes_nothing(self, text, rows, mode):
        with tempfile.TemporaryDirectory() as tmp:
            jsonl, page = os.path.join(tmp, "r.jsonl"), os.path.join(tmp, "r.md")
            argv = ["x.xlsx", *mode, "--jsonl", jsonl, "--page", page, "--page-title", "T",
                    "--page-description", "D", "--source-rel", "s.xlsx", "--generated-at", "2026-11-27"]
            with mock.patch.object(g, "read_sheet", return_value=("Sheet1", rows)):
                with self.assertRaises(SystemExit) as cm:
                    g.main(argv)
            self.assertEqual(cm.exception.code, text)
            self.assertFalse(os.path.exists(jsonl))
            self.assertFalse(os.path.exists(page))

    def test_main_writes_nothing_on_a_repeated_story(self):
        self.assert_main_writes_nothing(self.STORY_ERR, self.DUP_STORY, ["--mint", "S"])

    def test_main_writes_nothing_on_a_repeated_id(self):
        self.assert_main_writes_nothing(self.ID_ERR, self.DUP_ID, ["--id-col", "Criterion", "--story-col", "Old ID"])


@unittest.skipUnless(os.environ.get("INGEST_LIVE_DIR"), "set INGEST_LIVE_DIR to read the story workbooks")
class RealWorkbookTest(unittest.TestCase):
    raw = os.environ.get("INGEST_LIVE_DIR", "")

    def test_eight_september_revision(self):
        _, rows = read_sheet(os.path.join(self.raw, "stories-part1.xlsx"))
        blocks, criteria, _ = g.build(rows, COLS, mint="S")
        self.assertEqual((len(blocks), len(criteria)), (62, 229))
        self.assertNotIn("S-24", [b["story"] for b in blocks])
        page = g.render_page(blocks)
        for c in criteria:
            self.assertIn(cell_md(c["scenario"]), page)

    def test_thirty_one_august_revision(self):
        _, rows = read_sheet(os.path.join(self.raw, "stories-s5.xlsx"), "User stories")
        blocks, criteria, skipped = g.build(rows, COLS, id_col="Criterion", story_col="Old ID")
        self.assertEqual((len(criteria), len(skipped)), (214, 3))


if __name__ == "__main__":
    unittest.main()
