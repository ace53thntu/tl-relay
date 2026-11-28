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

    def build(self, *extra):
        return g.build(ID_ROWS + list(extra), COLS, id_col="Criterion", story_col="Old ID")

    def test_keeps_a_trailing_star_in_a_criterion(self):
        _, criteria, _ = self.build(["4", "US-01", "A", "Low", "US-01-AC1*", "x3", "y3"])
        self.assertEqual(criteria[-1]["id"], "US-01-AC1*")

    def test_keeps_a_star_inside_a_story(self):
        blocks, criteria, _ = self.build(["4", "US*01", "C", "Low", "US-09-AC1", "x3", "y3"])
        self.assertEqual([b["story"] for b in blocks], ["US-01", "US-05", "US*01"])
        self.assertEqual(criteria[-1]["story"], "US*01")

    def test_keeps_bold_marks_that_do_not_wrap_the_whole_cell(self):
        _, criteria, _ = self.build(["4", "US-01", "A", "Low", "**US-01**-AC1", "x3", "y3"])
        self.assertEqual(criteria[-1]["id"], "**US-01**-AC1")

    def test_a_starred_and_a_plain_id_are_two_ids(self):
        _, criteria, _ = self.build(["4", "US-01", "A", "Low", "US-01-AC1", "x3", "y3"],
                                    ["5", "US-01", "A", "Low", "US-01-AC1*", "x4", "y4"])
        self.assertEqual([c["id"] for c in criteria[-2:]], ["US-01-AC1", "US-01-AC1*"])

    def test_strips_spaces_inside_a_bold_wrapper(self):
        blocks, criteria, _ = self.build(["4", "** US-07 **", "D", "Low", " ** US-07-AC1 ** ", "x3", "y3"])
        self.assertEqual((blocks[-1]["story"], criteria[-1]["id"]), ("US-07", "US-07-AC1"))

    def test_skips_star_only_cells_as_blank(self):
        blocks, criteria, skipped = self.build(["4", "US-01", "A", "Low", "*", "x3", "y3"],
                                               ["5", "US-01", "A", "Low", "*", "x4", "y4"],
                                               ["6", "***", "E", "Low", "US-08-AC1", "x5", "y5"])
        self.assertEqual([c["id"] for c in criteria], ["US-01-AC1a", "US-01-AC2a"])
        self.assertEqual([b["story"] for b in blocks], ["US-01", "US-05"])
        self.assertEqual(skipped, [4, 5, 6, 7])

    def test_skips_star_and_whitespace_cells_as_blank(self):
        _, criteria, _ = self.build(["4", "US-01", "A", "Low", "* *", "x3", "y3"],
                                    ["5", "US-01", "A", "Low", "* *", "x4", "y4"],
                                    ["6", "US-01", "A", "Low", "*\t*", "x5", "y5"])
        self.assertEqual([c["id"] for c in criteria], ["US-01-AC1a", "US-01-AC2a"])


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


class InvisibleCharTest(unittest.TestCase):
    def test_id_col_refuses_a_tab_inside_a_criterion(self):
        rows = [r[:] for r in ID_ROWS]
        rows[2][4] = "US-01-AC2\ta"
        with self.assertRaises(SystemExit) as cm:
            g.build(rows, COLS, id_col="Criterion", story_col="Old ID")
        self.assertEqual(cm.exception.code, "gen_register: id at sheet row 3 holds U+0009")

    def test_id_col_refuses_a_bom_in_a_story(self):
        rows = [r[:] for r in ID_ROWS]
        rows[3][1] = "\ufeffUS-05"
        with self.assertRaises(SystemExit) as cm:
            g.build(rows, COLS, id_col="Criterion", story_col="Old ID")
        self.assertEqual(cm.exception.code, "gen_register: story at sheet row 4 holds U+FEFF")

    def test_id_col_accepts_non_ascii_letters(self):
        rows = [r[:] for r in ID_ROWS]
        rows[1][4] = "US-01-Tiếng-Việt"
        _, criteria, _ = g.build(rows, COLS, id_col="Criterion", story_col="Old ID")
        self.assertEqual(criteria[0]["id"], "US-01-Tiếng-Việt")


class MintCheckTest(unittest.TestCase):
    H5 = MINT_ROWS[0]

    def rows(self, *numbers):
        return [self.H5] + [[num, "T", "Low", "s", "r"] for num in numbers]

    def assert_rejects(self, text, rows, mint="S"):
        with self.assertRaises(SystemExit) as cm:
            g.build(rows, COLS, mint=mint)
        self.assertEqual(cm.exception.code, text)

    def test_mint_reads_a_bold_number(self):
        _, criteria, _ = g.build(self.rows("**1**"), COLS, mint="S")
        self.assertEqual(criteria[0]["id"], "S-01-AC1")
        self.assertEqual(criteria[0]["number"], "1")

    def test_mint_reads_bold_and_plain_as_one_story(self):
        blocks, criteria, _ = g.build(self.rows("1", "**1**"), COLS, mint="S")
        self.assertEqual([b["story"] for b in blocks], ["S-01"])
        self.assertEqual([c["id"] for c in criteria], ["S-01-AC1", "S-01-AC2"])

    def test_mint_refuses_a_number_that_is_not_whole(self):
        for cell in ("1a", "1.0", "-1", "0", "**1", "****", "\u0661"):
            with self.subTest(cell=cell):
                self.assert_rejects(f"gen_register: No. {cell!r} at sheet row 2 is not a whole number of 1 or more",
                                    self.rows(cell))

    def test_mint_reads_a_very_long_number_without_a_traceback(self):
        _, criteria, _ = g.build(self.rows("1" * 5000), COLS, mint="S")
        self.assertEqual(criteria[0]["id"], "S-" + "1" * 5000 + "-AC1")

    def test_mint_refuses_a_bom_in_a_number(self):
        self.assert_rejects("gen_register: No. at sheet row 2 holds U+FEFF", self.rows("\ufeff1"))

    def test_mint_refuses_surrounding_whitespace_in_the_prefix(self):
        self.assert_rejects("gen_register: --mint ' S' must not carry surrounding whitespace", self.rows("1"), mint=" S")

    def test_mint_refuses_an_empty_prefix(self):
        self.assert_rejects("gen_register: --mint must not be empty", self.rows("1"), mint="")

    def test_mint_refuses_a_zero_width_space_in_the_prefix(self):
        self.assert_rejects("gen_register: --mint holds U+200B", self.rows("1"), mint="S\u200b")

    def test_main_checks_the_prefix_before_reading_the_workbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit) as cm:
                g.main([os.path.join(tmp, "missing.xlsx"), "--mint", " S", "--jsonl", os.path.join(tmp, "out.jsonl")])
        self.assertEqual(cm.exception.code, "gen_register: --mint ' S' must not carry surrounding whitespace")


if __name__ == "__main__":
    unittest.main()
