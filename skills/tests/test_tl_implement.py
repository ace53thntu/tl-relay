import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills/tl-implement/SKILL.md"


class TlImplementTest(unittest.TestCase):
    def test_frontmatter_names_the_skill(self):
        self.assertIn("name: tl-implement", SKILL.read_text())

    def test_ten_steps_in_order(self):
        text = SKILL.read_text()
        steps = ["Start", "Plan", "Plan gate", "Build", "Conformance", "Fix loop",
                 "Knowledge refresh", "Gate", "Publish", "Retro"]
        positions = [text.index("| %d | %s |" % (i + 1, s)) for i, s in enumerate(steps)]
        self.assertEqual(positions, sorted(positions))

    def test_start_refusals(self):
        text = SKILL.read_text()
        for phrase in ["no ticket key", "more than one repo", "Depends on", "merged"]:
            self.assertIn(phrase, text)
        self.assertLess(text.index("no ticket key"), text.index("more than one repo"))
        self.assertLess(text.index("more than one repo"), text.index("Depends on row"))
        self.assertIn("before any worktree, branch or run directory exists", text)

    def test_build_hands_run_plan_the_caller_notes(self):
        text = SKILL.read_text()
        self.assertIn("the caller gates the plan itself", text)
        self.assertIn("Plan gate passed by caller:", text)
        self.assertIn("Keep workspace", text)
        self.assertIn("Ruling: [<key_class>]", text)

    def test_conformance_and_temporal_dispatch(self):
        text = SKILL.read_text()
        self.assertIn("qa-conformance", text)
        self.assertIn("temporal-code-reviewer", text)
        self.assertIn("imports a Temporal SDK package", text)
        self.assertIn("the run's `base:` commit", text)
        self.assertNotIn("`temporal-reviewer`", text)

    def test_gate_and_publish(self):
        head = (ROOT / "skills/tl-implement/templates/head.md").read_text()
        self.assertIn("READY|FAIL|BLOCKED <row> r<n>", head)
        for section in ["## Summary", "## Conformance", "## Decided for veto", "## Test evidence",
                        "## Known gaps", "## PR title", "## PR body", "## Ticket comment"]:
            self.assertIn(section, head)
        text = SKILL.read_text()
        self.assertIn("tracker.comment", text)
        self.assertIn("tracker.confirm_flag", text)
        self.assertIn("never changes the ticket status", text)
        for path in [SKILL, ROOT / "skills/tl-implement/templates/head.md",
                     ROOT / "skills/tl-implement/templates/run-state.md"]:
            self.assertNotIn("Jira", path.read_text())

    def test_loop_rules(self):
        text = SKILL.read_text()
        self.assertIn("blocks the gate until the operator answers", text)
        self.assertIn("A veto becomes a fix, and the run returns to step 6", text)
        self.assertIn("**Refresh**", text)

    def test_run_state_lives_in_the_home(self):
        self.assertIn("<runtime>/designs/<handle>/runs/<row>/", SKILL.read_text())
        state = (ROOT / "skills/tl-implement/templates/run-state.md").read_text()
        for field in ["step:", "round:", "repo:", "base:", "branch:", "worktree:", "plan:", "depends:",
                      "open questions:", "pr:", "comment:"]:
            self.assertIn(field, state)

    def test_fix_round_one_rules(self):
        text = SKILL.read_text()
        for phrase in ["<remote>/<default branch>", "merged state", "on both exits", "steps 3, 5, 6 and 8",
                       "`base:`..HEAD", "approved `READY` head",
                       "a module a worker registers as activities", "worktree path", "`verdict` and `reason`", "the lint that rule names"]:
            self.assertIn(phrase, text)

    def test_fix_round_two_rules(self):
        text = SKILL.read_text()
        for phrase in ["returns the run to step 6", "pass_start:", "--no-track",
                       "git push -u <remote> <branch>", "any PR found", "the operator overrode",
                       "after step 10"]:
            self.assertIn(phrase, text)
        state = (ROOT / "skills/tl-implement/templates/run-state.md").read_text()
        self.assertIn("pass_start:", state)

    def test_post_cap_rules(self):
        text = SKILL.read_text()
        for phrase in ["any PR found in these sources", "after a veto, or after an answer that needs a code change",
                       "`<run dir>/fixes.md`", "`plan-gate.md`, `fixes.md` and",
                       "an answer that needs a code change becomes a blocking item",
                       "skip opening the PR when `pr:` is set", "`round:` increments when that rerun starts"]:
            self.assertIn(phrase, text)
        self.assertNotIn("Never remove it after step 9", text)
        self.assertLess(text.index("A `FAIL` head returns the run to step 6"), text.index("### Step 9, publish"))

    def test_final_review_rules(self):
        text = SKILL.read_text()
        for phrase in ["decline its push and PR", "`lens-qa-conformance` § Rules", "the breakdown",
                       "`round:` starts at 1", "`pass_start:` at 2", "workspace `CLAUDE.md`",
                       "`minor (deferred)`", "it reads `BLOCKED`", "at most 4", "rejected:"]:
            self.assertIn(phrase, text)
        self.assertIn("`plan-gate.md`, `fixes.md`, `head.md`", text)
        self.assertNotIn("after a `FAIL` head", text)

    def test_final_rereview_rules(self):
        text = SKILL.read_text()
        self.assertIn("goes into `<run dir>/fixes.md` as a `Decision: [<key_class>] …` line.", text)
        self.assertNotIn("`<run dir>/fixes.md` as `Ruling:", text)
        self.assertIn("each such `<why>` names the rejected option", text)
        self.assertIn("A failing command stays a blocking item when a `BLOCKED` head hides the `FAIL`.", text)
        self.assertIn("`<remote>` is the push remote the workspace `CLAUDE.md` names.", text)
        self.assertNotIn("origin/", text)
