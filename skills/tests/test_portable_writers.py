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

    def test_fallback_dispatches_a_subagent_per_slice(self):
        text = (SKILLS / "ingest-sources/SKILL.md").read_text()
        workflow = text.index("Workflow({scriptPath:")
        subagent = text.index("With no Workflow tool and a subagent tool")
        alone = text.index("With no subagent tool")
        self.assertLess(workflow, subagent)
        self.assertLess(subagent, alone)
        tier = text[subagent:alone]
        self.assertIn("`prompt(a, s)`", tier)
        self.assertIn("verbatim", tier)
        self.assertIn("`opus` where the tool takes a model", tier)
        self.assertIn("redispatch", tier)
        self.assertIn("Wait until every subagent finishes", tier)
        self.assertIn("Step 5 starts only after", tier)
        self.assertIn("--pending", tier)
        self.assertLess(alone, text.index("5. Assemble."))

    def test_script_commands_set_no_shell_variable(self):
        for name in ("ingest-sources", "write-contract"):
            text = (SKILLS / name / "SKILL.md").read_text()
            self.assertNotIn("$SK", text, name)
            self.assertNotIn("SK=", text, name)
            self.assertIn("Set no shell variable in a command, because Claude Code asks before every command that sets one.",
                          " ".join(text.split()), name)

    def test_readers_and_record_follow_the_digest(self):
        text = " ".join((SKILLS / "ingest-sources/SKILL.md").read_text().split())
        for sentence in ('python3 "<skill dir>/scripts/assemble.py" --ws "$WS" --pending',
                         "args: {kind, ws, oldSource, newSource, slices, digest}",
                         "Step 5 starts only after `--pending` lists no slice.",
                         "A stamp error goes back to step 4 for the slice it names, never to the operator.",
                         "Keep line 1 of both files unchanged when you write the ruling.",
                         "Read the findings only from the files that `$WS/adjudication.json` lists under `findings`."):
            self.assertIn(sentence, text)
        self.assertNotIn("check that `$WS/slice-<name>.md` and `$WS/findings-<name>.md` exist", text)

    def test_digest_names_the_three_drift_inputs(self):
        text = " ".join((SKILLS / "ingest-sources/SKILL.md").read_text().split())
        self.assertIn("It prints `inputs_sha256`, the digest of `slices.json`, `new.jsonl` and `old.jsonl`, and `pending`", text)
        self.assertIn("`digest` is `inputs_sha256`.", text)

    def test_pending_checks_the_registers(self):
        text = " ".join((SKILLS / "ingest-sources/SKILL.md").read_text().split())
        self.assertIn("It first checks that `new.jsonl` and `old.jsonl` parse and hold the ids that `slices.json` and `pairs.tsv` name.", text)
        self.assertIn("A nonzero exit from `--pending` goes to the operator as a question, and no reader runs.", text)

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
            self.assertNotIn("<knowledge_dir>/designs/", (SKILLS / name / "SKILL.md").read_text(), name)

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

    def test_workspace_and_register_follow_the_caller(self):
        text = " ".join((SKILLS / "ingest-sources/SKILL.md").read_text().split())
        for sentence in ("WS=<the directory the caller names, else a fresh directory in the session scratchpad>",
                         "The workspace may be gone after this run, so the record must hold everything the readers found.",
                         "the caller runs `set-baseline` and `add-impact` with `$WS/impact.tsv`, then regenerates `$K/designs/$H/specs/user-stories.md` from the revision.",
                         "Run alone, this skill presents G-ingest and then stops: it moves no baseline and leaves the register as it is.",
                         "For a revision, the caller writes the page after G-ingest, as step 4.8 says."):
            self.assertIn(sentence, text)
            self.assertNotIn("tl-design", sentence)
        step8 = text[text.index("8. Stop at G-ingest."):text.index("## Rules")]
        self.assertNotIn("tl-design", step8)
        self.assertNotIn("Run alone, this skill does.", text)
        self.assertNotIn("For a revision, write the page only after G-ingest.", text)
        self.assertNotIn("does not survive", text)
        self.assertNotIn("this skill regenerates", text)


if __name__ == "__main__":
    unittest.main()
