import pathlib
import unittest

SKILLS = pathlib.Path(__file__).resolve().parents[1]


class PortableWritersTest(unittest.TestCase):
    NAMES = ("ingest-sources", "write-contract", "write-lld", "write-hla", "write-task-breakdown", "write-design")

    def test_no_home_skill_paths(self):
        for name in self.NAMES:
            for path in (SKILLS / name).rglob("*"):
                if path.is_file() and path.suffix in (".md", ".py", ".sh", ".js"):
                    self.assertNotIn("~/.claude/skills", path.read_text(), str(path))

    def test_drift_adjudicate_runs_by_script_path(self):
        text = (SKILLS / "ingest-sources/SKILL.md").read_text()
        self.assertNotIn('Workflow({name: "drift-adjudicate"', text)
        self.assertIn("<skill dir>/workflows/drift-adjudicate.js", text)

    def test_ingest_sources_names_its_dependency_install(self):
        text = (SKILLS / "ingest-sources/SKILL.md").read_text()
        self.assertIn("requirements.txt", text)
        self.assertIn("python3 -m venv <skill dir>/.venv && <skill dir>/.venv/bin/python -m pip install -r <skill dir>/requirements.txt", text)
        self.assertNotIn("~/.claude/skills", text)

    def test_pdf_check_precedes_step_one(self):
        text = (SKILLS / "ingest-sources/SKILL.md").read_text()
        check = text.index("only when the input is a PDF")
        self.assertLess(check, text.index("## 1. Snapshot"))

    def test_fallback_names_both_slice_files(self):
        text = (SKILLS / "ingest-sources/SKILL.md").read_text()
        self.assertIn("slice-<name>.md", text)
        self.assertIn("findings-<name>.md", text)

    def test_write_design_sibling_stop_precedes_writing(self):
        text = (SKILLS / "write-design/SKILL.md").read_text()
        stop = text.index("--skill tl-design")
        self.assertLess(stop, text.index("## Overview"))

    def test_sibling_stops(self):
        for name, sibling in (("write-task-breakdown", "write-contract"), ("write-design", "tl-design"), ("ingest-sources", "tl-design")):
            text = (SKILLS / name / "SKILL.md").read_text()
            self.assertIn(f"npx skills add ace53thntu/tl-relay --skill {sibling}", text, name)
        self.assertNotIn("$SK/write-task-breakdown/", (SKILLS / "write-task-breakdown/SKILL.md").read_text())
        self.assertIn("<skill dir>/../tl-design/scripts/doc_budget.py", (SKILLS / "write-design/SKILL.md").read_text())

    def test_writers_read_knowledge_dir(self):
        for name in ("write-design", "write-hla", "write-lld", "write-contract", "write-task-breakdown"):
            self.assertIn("knowledge_dir", (SKILLS / name / "SKILL.md").read_text(), name)


if __name__ == "__main__":
    unittest.main()
