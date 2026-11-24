import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def read(rel):
    return (ROOT / rel).read_text()


class FinalFixes(unittest.TestCase):
    def test_review_change_falls_back_without_code_review(self):
        text = read("skills/review-change/SKILL.md")
        self.assertIn("When `/code-review` is unavailable", text)
        self.assertIn("the main session does that review", text)

    def test_run_plan_and_tl_implement_state_the_no_subagent_fallback(self):
        self.assertIn("With no subagent tool, each role runs in the main session, in order, whichever routing source applies.",
                      read("skills/run-plan/SKILL.md"))
        self.assertIn("With no subagent tool, the main session runs the gate.", read("skills/tl-implement/SKILL.md"))

    def test_tl_design_resolves_state_dir_to_absolute(self):
        self.assertIn("`state_dir` resolved against the workspace root to an absolute path", read("skills/tl-design/SKILL.md"))

    def test_tl_design_steps_12_and_13(self):
        text = read("skills/tl-design/SKILL.md")
        self.assertIn("or a reported skip | Approves the filing |", text)
        self.assertIn("a dry run without `publish.confirm_flag`, then the confirm run after approval", text)
        self.assertIn("When the operator rejects the dry run output", text)

    def test_temporal_review_values(self):
        text = read("skills/tl-implement/SKILL.md")
        self.assertIn("one of `proceed` or `stop`; blank means not asked", text)
        self.assertIn("names `temporal_review` as the reason", text)
        template = read("skills/tl-implement/templates/run-state.md")
        self.assertIn("`temporal_review:`", template)
        self.assertIn("`skips:`", template)

    def test_bootstrap_override_variable_is_renamed(self):
        self.assertIn("TL_RELAY_BOOTSTRAP_SKILL", read("hooks/session-start-skills.sh"))
        self.assertNotIn("AI_SDLC_BOOTSTRAP_SKILL", read("hooks/session-start-skills.sh"))


if __name__ == "__main__":
    unittest.main()
