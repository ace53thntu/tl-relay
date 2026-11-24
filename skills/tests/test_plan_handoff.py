import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class PlanHandoffTest(unittest.TestCase):
    def test_write_plan_returns_the_plan_to_a_gating_caller(self):
        text = (ROOT / "skills/write-plan/SKILL.md").read_text()
        self.assertIn("Implementation waits until they approve it.", text)
        self.assertIn("Once the human approves: **REQUIRED SUB-SKILL:** `run-plan`.", text)
        self.assertIn("the caller gates the plan itself", text)
        self.assertIn("return the saved plan path to the caller", text)
        self.assertIn("The caller decides when `run-plan` starts.", text)
        self.assertNotIn("verdict file", text)
        self.assertNotIn("have reviewed it", text)
        self.assertLess(text.index("the caller gates the plan itself"), text.index("Otherwise, hand off after saving and self-review"))
        self.assertLess(text.index("Otherwise, hand off after saving and self-review"), text.index("Once the human approves: **REQUIRED SUB-SKILL:**"))

    def test_run_plan_ruling_may_carry_a_key_class(self):
        text = (ROOT / "skills/run-plan/SKILL.md").read_text()
        self.assertIn("Ruling: <what you decided> — <why> — <what it costs if wrong>", text)
        self.assertIn("Ruling: [<key_class>] <what you decided>", text)
        self.assertIn("Every ruling starts with `Ruling:`", text)

    def test_run_plan_skips_its_gate_on_a_caller_note_or_its_own_marker(self):
        text = (ROOT / "skills/run-plan/SKILL.md").read_text()
        self.assertIn("When the ledger header holds `Plan gate passed by caller: <path>`", text)
        self.assertIn("When the header holds `Own plan gate: ran`, skip the gate; it already ran.", text)
        self.assertIn("Otherwise run the gate the routing section prescribes", text)
        self.assertIn("Whoever revises a plan after its gate removes `Own plan gate: ran` before resume.", text)
        self.assertIn("Ruling: plan gate skipped — caller gate record <path>", text)
        self.assertLess(text.index("When the ledger header holds `Plan gate passed by caller"),
                        text.index("When the header holds `Own plan gate: ran`"))
        self.assertLess(text.index("When the header holds `Own plan gate: ran`"),
                        text.index("Otherwise run the gate the routing section prescribes"))

    def test_final_review_keeps_the_workspace_on_the_caller_note(self):
        text = (ROOT / "skills/run-plan/references/final-review.md").read_text()
        self.assertIn("rm -rf <workspace>", text)
        self.assertIn("When the ledger header holds `Keep workspace`, skip the delete.", text)
        self.assertIn("The caller reads the ledger there and removes the workspace.", text)

    def test_resume_adds_missing_caller_notes(self):
        text = (ROOT / "skills/run-plan/references/resuming.md").read_text()
        self.assertIn("add each caller note the ledger header lacks", text)
        self.assertIn("only when the ledger records no plan gate of its own", text)

    def test_run_plan_defines_the_header_and_records_its_own_gate(self):
        text = (ROOT / "skills/run-plan/SKILL.md").read_text()
        self.assertIn("Header notes start at line 2.", text)
        self.assertIn("The first blank line ends the header; with no notes, line 2 is that blank line.", text)
        self.assertIn("Write each caller note there, and find each later by its prefix.", text)
        self.assertIn("then write `Own plan gate: ran` in the ledger header.", text)

    def test_resume_keeps_the_gate_and_keep_workspace_notes_current(self):
        text = (ROOT / "skills/run-plan/references/resuming.md").read_text()
        self.assertIn("inserting it in the header and never at the end", text)
        self.assertIn("the header lacks `Own plan gate: ran`", text)
        self.assertIn("A note already present keeps its value, except `Keep workspace`.", text)
        self.assertIn("add it when passed, remove it when not.", text)

    def test_final_review_scopes_the_history_record_and_keeps_tags(self):
        text = (ROOT / "skills/run-plan/references/final-review.md").read_text()
        self.assertIn("5. After the delete, git history holds the record.", text)
        self.assertIn("the kept ledger holds it until the caller removes it.", text)
        self.assertIn("A ruling keeps its `[<key_class>]` tag.", text)

    def test_run_plan_names_the_five_key_classes(self):
        import re
        text = (ROOT / "skills/run-plan/SKILL.md").read_text()
        line = re.search(r"five key classes \(([^)]*)\)", text).group(1)
        self.assertEqual(tuple(re.findall(r"`(\w+)`", line)), ("contract", "data_model", "architecture", "security_release", "timeline"))


if __name__ == "__main__":
    unittest.main()
