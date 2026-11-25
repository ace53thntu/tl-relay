import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class LayoutTest(unittest.TestCase):
    def test_internal_tooling_sits_under_maintainer(self):
        for rel in ("maintainer/sdlc.py", "maintainer/runtime/install.py",
                    "maintainer/skills/write-skill/SKILL.md", "maintainer/skills/retro/SKILL.md",
                    "maintainer/hooks/block-env-dump.sh", "maintainer/hooks/user-fragment.json"):
            self.assertTrue((ROOT / rel).is_file(), rel)
        for rel in ("sdlc.py", "runtime", "skills/write-skill", "skills/retro", "hooks/block-env-dump.sh"):
            self.assertFalse((ROOT / rel).exists(), rel)
        self.assertTrue((ROOT / "hooks/session-start-skills.sh").is_file())

    def test_install_renders_maintainer_hook_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            home, claude, work = tmp / "home", tmp / "claude-a", tmp / "work"
            for d in (home, work):
                d.mkdir()
            (home / "tl-relay.yaml").write_text(
                "apiVersion: tl-relay/v1\nkind: Config\nproject:\n  name: t\n  root: %s\n"
                "install:\n  claude_config_dirs: [\"%s\"]\n" % (work, claude))
            env = {"PATH": "/usr/bin:/bin", "TL_RELAY_HOME": str(home), "TL_RELAY_REPO": str(ROOT)}
            proc = subprocess.run(
                [sys.executable, str(ROOT / "maintainer/sdlc.py"), "install", "--dry-run"],
                capture_output=True, text=True, env=env)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            commands = [l for l in proc.stdout.splitlines() if str(ROOT) in l and "hooks/" in l]
            self.assertTrue(commands, proc.stdout)
            plugin = ("session-start-skills.sh", "inject-lesson.sh")
            for name in plugin:
                lines = [l for l in commands if name in l]
                self.assertTrue(lines, proc.stdout)
                for l in lines:
                    self.assertIn(str(ROOT / "hooks" / name), l)
                    self.assertNotIn("/maintainer/hooks/", l)
            for l in commands:
                if not any(name in l for name in plugin):
                    self.assertIn(str(ROOT / "maintainer/hooks/"), l)

    def test_bootstrap_skill_is_using_tl_relay(self):
        text = (ROOT / "skills/using-tl-relay/SKILL.md").read_text()
        self.assertIn("name: using-tl-relay", text)
        self.assertNotIn("ai-sdlc", text)
        self.assertNotIn("write-skill", text)
        self.assertIn("$TL_RELAY_LESSONS/<skill>.md", text)
        self.assertFalse((ROOT / "skills/using-ai-sdlc").exists())
        self.assertIn("skills/using-tl-relay/SKILL.md", (ROOT / "hooks/session-start-skills.sh").read_text())


if __name__ == "__main__":
    unittest.main()
