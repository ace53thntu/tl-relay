import io
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

import run_tests

OK_SRC = "import unittest\n\n\nclass {name}(unittest.TestCase):\n    def test_a(self):\n        self.assertTrue(True)\n"
BAD_SRC = "import unittest\n\n\nclass BadCase(unittest.TestCase):\n    def test_a(self):\n        self.fail('nope')\n"
TWO_OK = OK_SRC.format(name="One") + "\n\n" + OK_SRC.split("\n\n\n", 1)[1].format(name="Two")
HEAVY_BAD_SRC = BAD_SRC.replace("self.fail('nope')", "self.fail('planted-heavy-failure')")
GIT_IDENT = ["-c", "user.name=Tester", "-c", "user.email=tester@example.invalid"]


def write(directory, name, text):
    path = pathlib.Path(directory) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def git(repo, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(["git", "-C", str(repo)] + GIT_IDENT + list(args), check=True, env=env,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def make_repo(root, files):
    git(root, "init", "-q")
    for name, text in files.items():
        write(root, name, text)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")


class NeedsHeavyTest(unittest.TestCase):
    def test_trigger_paths(self):
        for path in ("maintainer/skills/write-skill/scripts/final_run.py", "maintainer/runtime/x.py", "hooks/pre-push",
                     "maintainer/hooks/block-env-dump.sh", "skills/tests/test_skills.py", "maintainer/sdlc.py",
                     "skills/using-tl-relay/SKILL.md"):
            self.assertTrue(run_tests.needs_heavy([path]), path)

    def test_other_paths(self):
        for path in ("skills/tests/prompts/x.txt", "maintainer/skills/write-skill/gates.md", "skills/brainstorm/SKILL.md"):
            self.assertFalse(run_tests.needs_heavy([path]), path)
        self.assertFalse(run_tests.needs_heavy([]))


class ChangedPathsTest(unittest.TestCase):
    def test_not_a_repo(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(run_tests.changed_paths(pathlib.Path(d)))

    def test_union_of_committed_unstaged_untracked_and_rename_source(self):
        with tempfile.TemporaryDirectory() as d:
            make_repo(d, {"a.txt": "1\n", "skills/write-skill/scripts/old.py": "x = 1\n"})
            (pathlib.Path(d) / "lib").mkdir()
            git(d, "mv", "skills/write-skill/scripts/old.py", "lib/new.py")
            git(d, "commit", "-q", "-m", "rename")
            write(d, "a.txt", "2\n")
            write(d, "u.txt", "u\n")
            result = run_tests.changed_paths(pathlib.Path(d))
            for expected in ("a.txt", "u.txt", "lib/new.py", "skills/write-skill/scripts/old.py"):
                self.assertIn(expected, result)


class DecodeTest(unittest.TestCase):
    def test_non_utf8_path_does_not_raise(self):
        real = run_tests.git_output

        def fake(repo, *args):
            if args[0] == "merge-base":
                return b"abc\n"
            if args[0] == "diff":
                return b"bad\xff.py\0ok.py\0"
            return b""

        run_tests.git_output = fake
        try:
            result = run_tests.changed_paths(pathlib.Path("."))
        finally:
            run_tests.git_output = real
        self.assertEqual(len(result), 2)
        self.assertIn("ok.py", result)


class RunTest(unittest.TestCase):
    def run_dir(self, directory, skip=()):
        out = io.StringIO()
        code = run_tests.run(pathlib.Path(directory), set(skip), 2, out)
        return code, out.getvalue()

    def test_all_pass(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "test_ok.py", TWO_OK)
            code, text = self.run_dir(d)
            self.assertEqual(code, 0)
            self.assertEqual(text.strip().splitlines()[-1], "OK (2 units)")

    def test_one_failure(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "test_ok.py", TWO_OK)
            write(d, "test_bad.py", BAD_SRC)
            code, text = self.run_dir(d)
            self.assertEqual(code, 1)
            self.assertIn("test_bad.BadCase", text)
            self.assertEqual(text.strip().splitlines()[-1], "FAILED (1 of 3 units)")
            self.assertEqual(self.run_dir(d, skip={"test_bad"})[0], 0)

    def test_import_errors(self):
        for name, body in (("test_broken", "raise RuntimeError('boom')\n"), ("test_imp", "import nosuchmod_xyz\n")):
            with tempfile.TemporaryDirectory() as d:
                write(d, name + ".py", body)
                code, text = self.run_dir(d)
                self.assertEqual(code, 1)
                self.assertIn(name, text)

    def test_module_exiting_at_import_fails_its_unit(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "test_ok.py", OK_SRC.format(name="One"))
            write(d, "test_exits.py", "import sys\nsys.exit(0)\n")
            code, text = self.run_dir(d)
            self.assertEqual(code, 1)
            self.assertIn("test_exits", text)

    def test_collection_keeps_modules_from_outside_tests_dir(self):
        sys.modules.pop("colorsys", None)
        try:
            with tempfile.TemporaryDirectory() as d:
                write(d, "test_ok.py", "import colorsys\n" + OK_SRC.format(name="One"))
                run_tests.collect_units(pathlib.Path(d), set())
                self.assertIn("colorsys", sys.modules)
                self.assertNotIn("test_ok", sys.modules)
        finally:
            sys.modules.pop("colorsys", None)

    def test_collection_restores_cached_module_from_other_dir(self):
        import importlib
        previous = sys.modules.get("test_final_run")
        sys.modules.pop("test_final_run", None)

        def restore():
            sys.modules.pop("test_final_run", None)
            if previous is not None:
                sys.modules["test_final_run"] = previous

        self.addCleanup(restore)
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            write(a, "test_final_run.py", OK_SRC.format(name="FromA"))
            write(b, "test_final_run.py", OK_SRC.format(name="FromB"))
            sys.path.insert(0, a)
            try:
                loaded = importlib.import_module("test_final_run")
            finally:
                sys.path.remove(a)
            run_tests.collect_units(pathlib.Path(b), set())
            self.assertIs(sys.modules["test_final_run"], loaded)

    def test_consecutive_dirs_do_not_leak_modules(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            write(d1, "test_ok.py", OK_SRC.format(name="First"))
            write(d2, "test_ok.py", OK_SRC.format(name="Second"))
            self.assertEqual(self.run_dir(d1)[0], 0)
            code, text = self.run_dir(d2)
            self.assertEqual(code, 0)
            self.assertEqual(text.strip().splitlines()[-1], "OK (1 units)")
            self.assertNotIn("First", text)


class MainTest(unittest.TestCase):
    def setup_dirs(self, repo, tests):
        make_repo(repo, {"skills/brainstorm/SKILL.md": "a\n"})
        write(repo, "skills/brainstorm/SKILL.md", "b\n")
        git(repo, "commit", "-q", "-am", "change")
        write(tests, "test_ok.py", OK_SRC.format(name="One"))
        write(tests, "test_final_run.py", HEAVY_BAD_SRC)
        write(tests, "test_triggers.py", HEAVY_BAD_SRC.replace("planted-heavy-failure", "planted-triggers-failure"))

    def test_skips_heavy_for_text_only_diff(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as tests:
            self.setup_dirs(repo, tests)
            out = io.StringIO()
            code = run_tests.main([], repo=pathlib.Path(repo), tests_dir=pathlib.Path(tests), out=out)
            self.assertEqual(code, 0)
            self.assertTrue(out.getvalue().startswith("skipped: test_final_run, test_triggers (diff touches no write-skill scripts, skills/tests, runtime, hooks, sdlc.py or using-tl-relay)\n"))

    def test_all_flag_runs_heavy(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as tests:
            self.setup_dirs(repo, tests)
            out = io.StringIO()
            code = run_tests.main(["--all"], repo=pathlib.Path(repo), tests_dir=pathlib.Path(tests), out=out)
            self.assertEqual(code, 1)
            self.assertIn("planted-heavy-failure", out.getvalue())
            self.assertIn("planted-triggers-failure", out.getvalue())

    def test_not_a_repo_falls_back_to_running_everything(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as tests:
            write(tests, "test_ok.py", OK_SRC.format(name="One"))
            write(tests, "test_final_run.py", HEAVY_BAD_SRC)
            out = io.StringIO()
            code = run_tests.main([], repo=pathlib.Path(repo), tests_dir=pathlib.Path(tests), out=out)
            self.assertEqual(code, 1)
            self.assertIn("planted-heavy-failure", out.getvalue())
            self.assertNotIn("skipped:", out.getvalue())

    def test_unknown_flag_exits_2(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as tests:
            write(tests, "test_ok.py", OK_SRC.format(name="One"))
            with self.assertRaises(SystemExit) as ctx:
                run_tests.main(["--bogus"], repo=pathlib.Path(repo), tests_dir=pathlib.Path(tests), out=io.StringIO())
            self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
