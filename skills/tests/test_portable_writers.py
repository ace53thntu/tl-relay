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

    def body(self, name):
        return (SKILLS / name / "SKILL.md").read_text().split("\n---\n", 1)[1]

    def test_writers_use_the_shared_config(self):
        for name in self.NAMES:
            text = self.body(name)
            self.assertIn("../using-tl-relay/config.md", text, name)
            self.assertNotIn("a missing file or key means `_knowledge`", text, name)
            self.assertNotIn("<knowledge_dir>/designs/", text, name)

    def test_ingest_impact_scans_the_set_dir(self):
        text = self.body("ingest-sources")
        self.assertIn('--root "$K/designs/$H"', text)
        self.assertNotIn('--root "<design root>"', text)

    def test_hub_steps_need_knowledge_dir(self):
        lld = self.body("write-lld")
        hla = self.body("write-hla")
        self.assertIn("when `knowledge_dir` is set and the file exists", lld)
        self.assertIn("type: LLD", lld)
        self.assertIn("<runtime>/plans/lld/YYYY-MM-DD-<slug>.md", lld)
        self.assertIn("<runtime>/hlds/<slug>.md", hla)
        for text in (lld, hla):
            self.assertIn("only when the page sits under `knowledge_dir`", text)


if __name__ == "__main__":
    unittest.main()
