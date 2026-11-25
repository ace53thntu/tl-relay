import pathlib
import subprocess
import tempfile
import unittest

SKILLS = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = SKILLS / "run-plan" / "scripts" / "sdd-workspace"


class PortableRunPlanTest(unittest.TestCase):
    def test_workspace_lives_in_the_runs_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp).resolve() / "repo"
            runs = pathlib.Path(tmp).resolve() / "runs"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "plan.md").write_text("# plan\n")
            out = subprocess.run(["bash", str(SCRIPT), "-C", str(repo), "--runs-dir", str(runs), "plan.md"],
                                 capture_output=True, text=True, check=True)
            path = pathlib.Path(out.stdout.strip())
            self.assertTrue(str(path).startswith(str(runs) + "/"), path)
            status = subprocess.run(["git", "-C", str(repo), "status", "--ignored", "--short"],
                                    capture_output=True, text=True, check=True).stdout
            self.assertNotIn(".tl-relay", status)

    def test_route_subagents_holds_the_role_table(self):
        text = (SKILLS / "route-subagents/SKILL.md").read_text()
        for role in ("Scout", "Plan gate", "Implementer", "Code reviewer", "Design-doc lane"):
            self.assertIn(role, text)

    def test_routing_reference_is_gone(self):
        self.assertFalse((SKILLS.parent / "routing.md").exists())
        self.assertFalse((SKILLS / "run-plan/references/routing.md").exists())

    def test_fix_loop_routes_through_route_subagents(self):
        text = (SKILLS / "run-plan/references/fix-loop.md").read_text()
        self.assertIn("route-subagents", text)
        cap = next(line for line in text.splitlines() if "sets the same limit" in line)
        self.assertIn("review-change", cap)
        self.assertIn("at most three rounds", (SKILLS / "review-change/SKILL.md").read_text())

    def test_skills_route_through_route_subagents(self):
        for name in ("run-plan", "write-plan", "review-change"):
            text = (SKILLS / name / "SKILL.md").read_text()
            self.assertIn("route-subagents", text, name)
            self.assertNotIn("routing.md", text, name)

    def test_no_ai_sdlc_check_remains(self):
        for name in ("run-plan", "verify-done"):
            self.assertNotIn("sdlc.py", (SKILLS / name / "SKILL.md").read_text(), name)

    def test_worktree_location_has_a_default(self):
        text = (SKILLS / "run-plan/SKILL.md").read_text()
        self.assertIn('the `CLAUDE.md` section "Worktree location", else `$WORKTREE_ROOT`, else `worktree_dir`, else `<state_dir>/worktrees`', text)
        self.assertNotIn("$HOME/worktrees", text)

    def test_scripts_get_the_plan_runs_dir(self):
        for rel in ("run-plan/SKILL.md", "run-plan/references/fix-loop.md", "run-plan/references/final-review.md"):
            text = (SKILLS / rel).read_text()
            self.assertNotIn(".tl-relay/sdd", text, rel)
            for line in text.splitlines():
                if any(f"scripts/{n}" in line for n in ("sdd-workspace", "task-brief", "review-package")):
                    self.assertIn("--runs-dir <runtime>/plan-runs", line, rel)

    def test_workspace_placeholder_is_disambiguated(self):
        self.assertIn("In this skill, `<workspace>` is the directory `sdd-workspace` prints, not the workspace name of config.md.",
                      (SKILLS / "run-plan/SKILL.md").read_text())

    def test_output_paths_use_the_runtime(self):
        for name, path in (("brainstorm", "<runtime>/specs/YYYY-MM-DD-<slug>.md"), ("write-plan", "<runtime>/plans/YYYY-MM-DD-<slug>.md")):
            text = (SKILLS / name / "SKILL.md").read_text()
            self.assertIn(path, text, name)
            self.assertIn("../using-tl-relay/config.md", text, name)
            self.assertIn("Skill output targets", text, name)
            self.assertNotIn("default `_knowledge`", text, name)
        text = (SKILLS / "technical-writing/SKILL.md").read_text()
        self.assertIn("<runtime>/audits/", text)
        self.assertIn("with `knowledge_dir` unset, skip the ADR and glossary writes and say so in one line", text)


if __name__ == "__main__":
    unittest.main()
