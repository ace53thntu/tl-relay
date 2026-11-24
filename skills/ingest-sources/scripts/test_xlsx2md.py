import os
import sys
import tempfile
import unittest
import zipfile
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xlsx2md as x

NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
RNS = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"


def make_xlsx(path, sheets):
    """sheets is a list of (name, rows). A tuple cell becomes a rich-text entry of several runs."""
    strings, index = [], {}

    def sid(value):
        if isinstance(value, tuple):
            xml = "".join(f"<r><t>{escape(t)}</t></r>" for t in value)
        else:
            xml = f'<t xml:space="preserve">{escape(value)}</t>'
        if xml not in index:
            index[xml] = len(strings)
            strings.append(xml)
        return index[xml]

    with zipfile.ZipFile(path, "w") as z:
        sheet_tags, rels = [], []
        for i, (name, rows) in enumerate(sheets, 1):
            rels.append(f'<Relationship Id="rId{i}" Type="{REL}" Target="worksheets/sheet{i}.xml"/>')
            sheet_tags.append(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>')
            body = []
            for r, row in enumerate(rows, 1):
                cells = "".join(f'<c r="{chr(65 + c)}{r}" t="s"><v>{sid(v)}</v></c>'
                                for c, v in enumerate(row) if v != "")
                body.append(f'<row r="{r}">{cells}</row>')
            z.writestr(f"xl/worksheets/sheet{i}.xml",
                       f'<?xml version="1.0"?><worksheet {NS}><sheetData>{"".join(body)}</sheetData></worksheet>')
        z.writestr("xl/workbook.xml",
                   f'<?xml version="1.0"?><workbook {NS} {RNS}><sheets>{"".join(sheet_tags)}</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
                   'relationships">' + "".join(rels) + "</Relationships>")
        z.writestr("xl/sharedStrings.xml",
                   f'<?xml version="1.0"?><sst {NS}>' + "".join(f"<si>{s}</si>" for s in strings) + "</sst>")


class Xlsx2MdTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "w.xlsx")
        make_xlsx(self.path, [
            ("Summary", [["x"]]),
            ("User stories", [["No.", "Scenario", "Rule"],
                              ["1", "Given a\nWhen b", "a | b"],
                              ["2", ("rich ", "text"), ""]]),
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_a_named_sheet_with_gaps_newlines_pipes_and_rich_runs(self):
        name, rows = x.read_sheet(self.path, "User stories")
        self.assertEqual(name, "User stories")
        self.assertEqual(rows, [["No.", "Scenario", "Rule"], ["1", "Given a\nWhen b", "a | b"], ["2", "rich text", ""]])

    def test_reads_the_first_sheet_by_default_and_fails_on_an_unknown_one(self):
        self.assertEqual(x.read_sheet(self.path)[0], "Summary")
        with self.assertRaises(SystemExit):
            x.read_sheet(self.path, "Nope")

    def test_markdown_escapes_cells_drops_blank_rows_and_uses_the_spaced_delimiter(self):
        md = x.to_markdown([["No.", "Scenario"], ["1", "Given a\nWhen b | c"], ["", ""]])
        self.assertEqual(md, "| No. | Scenario |\n| --- | --- |\n| 1 | Given a<br>When b \\| c |\n")

    @unittest.skipUnless(os.environ.get("INGEST_LIVE_DIR"), "set INGEST_LIVE_DIR to read the story workbooks")
    def test_real_workbooks(self):
        raw = os.environ["INGEST_LIVE_DIR"]
        name, rows = x.read_sheet(os.path.join(raw, "stories-part1.xlsx"))
        self.assertEqual((name, len(rows)), ("User stories (2)", 230))
        self.assertEqual(rows[0][:5], ["No.", "Title", "Change impact", "Scenario", "Rule and message"])
        self.assertEqual(rows[0][5:], [""])
        name, rows = x.read_sheet(os.path.join(raw, "stories-s5.xlsx"), "User stories")
        self.assertEqual((name, len(rows), rows[0][4]), ("User stories", 218, "Criterion"))


if __name__ == "__main__":
    unittest.main()
