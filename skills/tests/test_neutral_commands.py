import os
import pathlib
import re
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
PAGES = ("maintainer/skills/write-skill/gates.md",)
WORD = "LEAK" + "WORD"


def command(page):
    text = (REPO / page).read_text()
    found = [c for c in re.findall(r"`([^`]*)`", text) if "sdlc.py check-neutral" in c]
    if len(found) != 1:
        raise AssertionError("%s holds %d check-neutral commands" % (page, len(found)))
    return found[0]


class NeutralCommands(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="neutral-command.")
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name).resolve()
        self.repo = root / "repo"
        home = root / "home"
        home.mkdir()
        (home / "tl-relay.yaml").write_text(
            "neutrality:\n  patterns:\n    - LEAK[W]ORD\n  identity_allow:\n    - dev@example.invalid\n"
        )
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "AI_SDLC_", "TL_RELAY_"))}
        self.env["TL_RELAY_HOME"] = str(home)
        self.git("init", "-q", "-b", "main", str(self.repo), cwd=root)
        self.commit("clean\n")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("checkout", "-q", "-b", "work")

    def git(self, *args, cwd=None):
        subprocess.run(
            ["git", "-c", "user.name=Dev", "-c", "user.email=dev@example.invalid", *args],
            cwd=str(cwd or self.repo), env=self.env, check=True, capture_output=True,
        )

    def commit(self, text):
        (self.repo / "file.txt").write_text(text)
        self.git("add", "file.txt")
        self.git("commit", "-q", "--allow-empty", "-m", "change")

    def run_page(self, page):
        line = command(page).replace("<repo>/maintainer/sdlc.py", str(REPO / "maintainer" / "sdlc.py"))
        line = line.replace("export TL_RELAY_HOME='<home>'; ", "").replace("<repo>", str(self.repo))
        return subprocess.run(["/bin/sh", "-c", line], env=self.env, capture_output=True, text=True).returncode

    def test_a_clean_branch_passes(self):
        self.commit("still clean\n")
        for page in PAGES:
            with self.subTest(page):
                self.assertEqual(self.run_page(page), 0)

    def test_a_leak_added_then_removed_is_caught(self):
        self.commit(WORD + "\n")
        self.commit("clean\n")
        for page in PAGES:
            with self.subTest(page):
                self.assertEqual(self.run_page(page), 1)

    def test_a_leak_with_an_empty_range_is_caught(self):
        self.commit(WORD + "\n")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        for page in PAGES:
            with self.subTest(page):
                self.assertEqual(self.run_page(page), 1)

    def test_a_missing_origin_main_does_not_pass(self):
        self.commit("still clean\n")
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        for page in PAGES:
            with self.subTest(page):
                self.assertNotEqual(self.run_page(page), 0)


if __name__ == "__main__":
    unittest.main()
