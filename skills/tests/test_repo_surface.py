import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class RepoSurfaceTest(unittest.TestCase):
    def test_the_story_skill_is_gone(self):
        self.assertFalse((ROOT / "skills/ai-sdlc").exists())

    def test_no_skill_imports_the_runtime(self):
        for path in (ROOT / "skills").rglob("*.py"):
            if path.name == "test_repo_surface.py":
                continue
            text = path.read_text()
            for needle in ("from runtime.", "import sdlc", "design_fixture", "from runtime import design"):
                self.assertNotIn(needle, text, str(path))

    def test_verify_done_names_no_runtime_check(self):
        text = (ROOT / "skills/verify-done/SKILL.md").read_text()
        self.assertNotIn("the runtime checks", text)
        self.assertNotIn('read "the runtime"', text)
        core = (ROOT / "skills/verify-done/core.md").read_text()
        self.assertNotIn("The runtime accepted", core)
        self.assertNotIn("No scan hit", core)

    def test_no_skill_says_the_runtime_sends_core(self):
        for name in ("test-first", "review-change"):
            self.assertNotIn("ai-sdlc runtime", (ROOT / "skills" / name / "SKILL.md").read_text(), name)

    def test_no_task_hook_remains(self):
        fragment = (ROOT / "maintainer/hooks/settings-fragment.json").read_text()
        for name in ("block-test-edit.sh", "warn-out-of-scope.sh", "validate-evidence.sh"):
            self.assertFalse((ROOT / "maintainer" / "hooks" / name).exists(), name)
            self.assertNotIn(name, fragment)

    def test_only_the_kept_runtime_remains(self):
        import subprocess
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files"], stdout=subprocess.PIPE,
                                 check=True).stdout.decode().splitlines()
        kept = {"__init__.py", "neutral.py", "install.py", "config.py", "yamlio.py"}
        self.assertEqual({p.split("/")[2] for p in tracked if p.startswith("maintainer/runtime/")
                          and p.count("/") == 2 and p.endswith(".py")}, kept)
        for gone in ("design/", "evals/", "workflows/", "lessons/", "repos/"):
            self.assertEqual([p for p in tracked if p.startswith(gone)], [], gone)
        self.assertEqual([p for p in tracked if p.startswith("agents/") and p.endswith(".yaml")], [])

    def test_sdlc_lists_only_install_and_check_neutral(self):
        import subprocess, sys
        out = subprocess.run([sys.executable, str(ROOT / "maintainer" / "sdlc.py"), "--help"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, check=True).stdout.decode()
        commands = out.split("{", 1)[1].split("}", 1)[0].split(",")
        self.assertEqual(commands, ["install", "check-neutral"])

    def test_no_kept_file_names_a_removed_path(self):
        removed = ("evals/", "workflows/story.yaml", "workflows/design.yaml", "design/gates", "skills/ai-sdlc",
                   "permit-push", "sdlc.py design", "sdlc.py status", "sdlc.py retro", "/ai-sdlc start",
                   "repos/example.yaml", "ai-sdlc runtime")
        files = [ROOT / "README.md", ROOT / "maintainer" / "sdlc.py"]
        files += [p for d in ("skills", "agents", "hooks", "maintainer/skills", "maintainer/hooks") for p in (ROOT / d).rglob("*")
                  if p.is_file() and p.suffix in (".md", ".py", ".sh", ".json") and "__pycache__" not in p.parts]
        for path in files:
            if path.name == "test_repo_surface.py":
                continue
            text = path.read_text(errors="ignore")
            for needle in removed:
                self.assertNotIn(needle, text, "%s names %s" % (path, needle))

    def test_no_legacy_names_outside_the_allowlist(self):
        old = re.compile(r"AI_SDLC_|ai-sdlc|ai_sdlc|AiSdlc")
        guards = {"skills/tests/test_package.py", "skills/tests/test_portable_tl_design.py",
                  "skills/tests/test_portable_tl_implement.py", "skills/tests/test_repo_surface.py",
                  "skills/tests/test_layout.py", "maintainer/runtime/tests/test_config.py",
                  "maintainer/runtime/tests/test_install.py", "skills/tests/test_final_run.py",
                  "maintainer/hooks/tests/test_require_guardrails.sh", "skills/tests/test_portable_run_plan.py"}
        listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, check=True).stdout
        bad = []
        for rel in listed.decode().split("\0"):
            if not rel or rel in guards:
                continue
            try:
                text = (ROOT / rel).read_bytes().decode("utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for n, line in enumerate(text.splitlines(), 1):
                if old.search(line) and not re.search(r"assertNotIn\(", line):
                    bad.append("%s:%d: %s" % (rel, n, line.strip()[:100]))
        self.assertEqual(bad, [], "legacy names outside the allowlist:\n" + "\n".join(bad))
