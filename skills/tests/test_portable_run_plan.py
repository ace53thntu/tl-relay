import pathlib
import subprocess
import tempfile
import unittest

SKILLS = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = SKILLS / "run-plan" / "scripts" / "sdd-workspace"


class PortableRunPlanTest(unittest.TestCase):
    def test_workspace_lives_in_tl_relay_sdd(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp).resolve() / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "plan.md").write_text("# plan\n")
            out = subprocess.run(["bash", str(SCRIPT), "-C", str(repo), "plan.md"],
                                 capture_output=True, text=True, check=True)
            path = pathlib.Path(out.stdout.strip())
            self.assertTrue(str(path).startswith(str(repo / ".tl-relay" / "sdd") + "/"), path)
            status = subprocess.run(["git", "-C", str(repo), "status", "--ignored", "--short"],
                                    capture_output=True, text=True, check=True).stdout
            self.assertIn("!! .tl-relay/", status)

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
        self.assertIn("$HOME/worktrees", (SKILLS / "run-plan/SKILL.md").read_text())

    def test_output_paths_read_knowledge_dir(self):
        for name in ("brainstorm", "write-plan"):
            self.assertIn("knowledge_dir", (SKILLS / name / "SKILL.md").read_text(), name)


if __name__ == "__main__":
    unittest.main()
