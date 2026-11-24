import pathlib
import unittest

SKILLS = pathlib.Path(__file__).resolve().parents[1]


class PortableTlImplementTest(unittest.TestCase):
    text = (SKILLS / "tl-implement/SKILL.md").read_text()

    def test_run_dir_in_state_dir(self):
        self.assertIn("<state_dir>/designs/<handle>/runs/<row>/", self.text)

    def test_tracker_comment_is_optional(self):
        for needle in ("tracker.comment` is unset", "{target}", "{body_file}", "tracker.confirm_flag"):
            self.assertIn(needle, self.text)

    def test_claude_md_defaults(self):
        for needle in ("remote `origin`", "git's own config", "<ticket>-<row slug>"):
            self.assertIn(needle, self.text)

    def test_agents_fallback(self):
        self.assertIn("tl-relay:qa-conformance", self.text)
        self.assertIn("lens-qa-conformance", self.text)

    def test_no_home_coupling(self):
        for needle in ("AI_SDLC_HOME", "ai-sdlc.yaml", "ai-sdlc/skills/"):
            self.assertNotIn(needle, self.text)

    def test_comment_waits_for_approval(self):
        for needle in ("Run the command once without `tracker.confirm_flag` and show the output",
                       "stop and wait for the operator to approve that output",
                       "When `tracker.confirm_flag` is unset, first show the `{body_file}` text and the full command",
                       "run it once after the operator approves"):
            self.assertIn(needle, self.text)
        self.assertNotIn("One approval covers three acts", self.text)

    def test_step9_operator_approves_comment(self):
        row = next(l for l in self.text.splitlines() if l.startswith("| 9 |"))
        self.assertIn("Approves the comment output", row)

    def test_step7_lint_on_knowledge_dir(self):
        row = next(l for l in self.text.splitlines() if l.startswith("| 7 |"))
        self.assertIn("`<knowledge_dir>` pages", row)
        self.assertIn("hub lint on `<worktree>/<knowledge_dir>`", self.text)
        self.assertNotIn("<worktree>/_knowledge", self.text)

    def test_temporal_review_asked_once(self):
        for needle in ("once per run", "`run-state.md` field `temporal_review:`",
                       "Later step 5 rounds read `temporal_review:` and do not ask again",
                       "A `stop` answer ends the run with a `BLOCKED` head"):
            self.assertIn(needle, self.text)
        row = next(l for l in self.text.splitlines() if l.startswith("| 5 |"))
        self.assertIn("Temporal review", row)
        ask = self.text.split("## Ask rule")[1].split("\n## ")[0]
        self.assertIn("Temporal review", ask)

    def test_run_state_fields_named(self):
        self.assertIn("`run-state.md` field `skips:`", self.text)
        gaps = next(l for l in self.text.splitlines() if l.startswith("- `## Known gaps`"))
        for field in ("`skips:`", "`temporal_review:`"):
            self.assertIn(field, gaps)
        state = (SKILLS / "tl-implement/templates/run-state.md").read_text()
        for field in ("\nskips:", "\ntemporal_review:"):
            self.assertIn(field, state)

    def test_none_mode_carries_agent_bodies(self):
        for name in ("qa-conformance", "temporal-code-reviewer"):
            body = (SKILLS.parent / "agents" / (name + ".md")).read_text().split("---\n", 2)[2]
            section = self.text.split("## Running without agents or Workflows")[1].split("\n## ")[0]
            for para in body.strip().split("\n\n"):
                self.assertIn(" ".join(para.split()), " ".join(section.split()))

    def test_sibling_list_has_tl_design(self):
        self.assertIn("`tl-design`", self.text.split("## Sibling skills")[1].split("##")[0])

    def test_temporal_skip_asks_operator(self):
        for needle in ("asks the operator before the gate whether to proceed without the Temporal review or stop",):
            self.assertIn(needle, self.text)

    def test_skip_notes_in_run_state(self):
        self.assertIn("note that in `run-state.md`", self.text)
        self.assertIn("reads them from the `run-state.md` fields", self.text)
        self.assertNotIn("in `head.md` under Known gaps", self.text)

    def test_state_dir_absolute(self):
        self.assertIn("`state_dir` is resolved against the workspace root to an absolute path", self.text)

    def test_step7_uses_knowledge_dir(self):
        self.assertIn("`<knowledge_dir>` pages the change moved", self.text)

    def test_worktree_default(self):
        self.assertIn("`$WORKTREE_ROOT`, else `$HOME/worktrees`", self.text)


if __name__ == "__main__":
    unittest.main()
