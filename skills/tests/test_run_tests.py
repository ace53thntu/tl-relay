import io
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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


class RelativePathsTest(unittest.TestCase):
    def test_paths_are_relative_to_a_repo_below_the_git_top_level(self):
        with tempfile.TemporaryDirectory() as parent:
            make_repo(parent, {"sub/README.md": "a\n"})
            write(parent, "sub/maintainer/x.txt", "x\n")
            git(parent, "add", "-A")
            git(parent, "commit", "-q", "-m", "change")
            self.assertIn("maintainer/x.txt", run_tests.changed_paths(pathlib.Path(parent) / "sub"))


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
        code = run_tests.run(run_tests.suite_units(pathlib.Path(directory), run_tests.Suite(".", "py", None), set(skip)), 2, out)
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

    def test_units_are_test_methods(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "test_ok.py", TWO_OK + "\n\nclass Three(unittest.TestCase):\n    def test_a(self):\n        pass\n\n    def test_b(self):\n        pass\n")
            units = run_tests.collect_units(pathlib.Path(d), set())
            self.assertEqual(sorted(units), ["test_ok.One.test_a", "test_ok.Three.test_a", "test_ok.Three.test_b",
                                             "test_ok.Two.test_a"])

    def test_a_module_attribute_that_raises_does_not_stop_collection(self):
        for failure in ("raise RuntimeError(name)", "sys.exit(3)"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as d:
                write(d, "test_odd.py", "import sys\n" + OK_SRC.format(name="Case")
                      + "\n\nseen = []\n\n\ndef __dir__():\n    return ['Aaa', 'Case']\n\n\ndef __getattr__(name):\n"
                      "    if name != 'Aaa':\n        raise AttributeError(name)\n    if seen:\n        %s\n"
                      "    seen.append(name)\n" % failure)
                self.assertEqual(run_tests.collect_units(pathlib.Path(d), set()), ["test_odd"])

    def test_an_imported_testcase_is_named_by_the_importing_module(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "test_base.py", OK_SRC.format(name="Shared"))
            write(d, "test_user.py", "from test_base import Shared\n")
            units = run_tests.collect_units(pathlib.Path(d), {"test_base"})
            self.assertEqual(units, ["test_user.Shared.test_a"])

    def test_an_imported_testcase_runs_through_the_importing_module(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "test_base.py", OK_SRC.format(name="Shared"))
            write(d, "test_user.py", "from test_base import Shared\n")
            out = io.StringIO()
            units = run_tests.suite_units(pathlib.Path(d), run_tests.Suite(".", "py", None), {"test_base"})
            self.assertEqual(run_tests.run(units, 2, out), 0)
            self.assertEqual(out.getvalue().strip().splitlines()[-1], "OK (1 units)")

    def test_an_aliased_testcase_is_named_by_its_alias(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "test_base.py", OK_SRC.format(name="Shared"))
            write(d, "test_user.py", "from test_base import Shared as Alias\n")
            units = run_tests.collect_units(pathlib.Path(d), {"test_base"})
            self.assertEqual(units, ["test_user.Alias.test_a"])
            out = io.StringIO()
            suite = run_tests.suite_units(pathlib.Path(d), run_tests.Suite(".", "py", None), {"test_base"})
            self.assertEqual(run_tests.run(suite, 2, out), 0)
            self.assertEqual(out.getvalue().strip().splitlines()[-1], "OK (1 units)")

    def test_two_classes_sharing_a_name_keep_both_units(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "test_dup.py", "import unittest\n\n\ndef make():\n    class T(unittest.TestCase):\n"
                  "        def test_b(self):\n            pass\n    return T\n\n\n"
                  "class T(unittest.TestCase):\n    def test_a(self):\n        pass\n\n\nB = make()\n")
            units = run_tests.collect_units(pathlib.Path(d), set())
            self.assertEqual(units, ["test_dup.B.test_b", "test_dup.T.test_a"])

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

    def state_src(self, other, tail=""):
        return (
            "# at import: drop RUN_TESTS_KEEP, set RUN_TESTS_LEAK, chdir elsewhere, extend sys.path\n"
            "import os\nimport sys\n"
            "os.environ.pop('RUN_TESTS_KEEP')\n"
            "os.environ['RUN_TESTS_LEAK'] = '1'\n"
            "os.chdir(%r)\n"
            "sys.path.append('/run-tests-leak')\n" % str(other)
        ) + tail

    def check_state_restored(self, src_tail, expected):
        self.addCleanup(os.chdir, os.getcwd())
        self.addCleanup(sys.path.__setitem__, slice(None), list(sys.path))
        with mock.patch.dict(os.environ, {"RUN_TESTS_KEEP": "1"}), \
                tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
            write(d, "test_state.py", self.state_src(pathlib.Path(other).resolve(), src_tail))
            before_cwd, before_path = os.getcwd(), list(sys.path)
            units = run_tests.collect_units(pathlib.Path(d), set())
            with self.subTest("units"):
                self.assertEqual(units, expected)
            with self.subTest("kept"):
                self.assertEqual(os.environ.get("RUN_TESTS_KEEP"), "1")
            with self.subTest("leak"):
                self.assertNotIn("RUN_TESTS_LEAK", os.environ)
            with self.subTest("cwd"):
                self.assertEqual(os.getcwd(), before_cwd)
            with self.subTest("path"):
                self.assertEqual(sys.path, before_path)

    def test_collection_restores_environment_cwd_and_path(self):
        self.check_state_restored(OK_SRC.format(name="State"), ["test_state.State.test_a"])

    def test_collection_restores_state_after_a_failed_import(self):
        self.check_state_restored("raise RuntimeError('boom')\n", ["test_state"])

    def test_collection_works_from_a_deleted_cwd(self):
        self.addCleanup(os.chdir, os.getcwd())
        with tempfile.TemporaryDirectory() as d:
            write(d, "test_gone.py", OK_SRC.format(name="Gone"))
            gone = tempfile.mkdtemp()
            os.chdir(gone)
            os.rmdir(gone)
            units = run_tests.collect_units(pathlib.Path(d), set())
        self.assertEqual(units, ["test_gone.Gone.test_a"])

    def test_collection_restores_modules_when_the_recorded_cwd_vanishes(self):
        self.addCleanup(os.chdir, os.getcwd())
        self.addCleanup(sys.modules.pop, "test_vanish", None)
        with tempfile.TemporaryDirectory() as d:
            doomed = tempfile.mkdtemp()
            os.chdir(doomed)
            write(d, "test_vanish.py", "import shutil\nshutil.rmtree(%r)\n" % doomed)
            run_tests.collect_units(pathlib.Path(d), set())
        self.assertNotIn("test_vanish", sys.modules)


class MainTest(unittest.TestCase):
    SUITES = (run_tests.Suite("skills/tests", "py", None),)

    def setup_dirs(self, repo):
        make_repo(repo, {"skills/brainstorm/SKILL.md": "a\n",
                         "skills/tests/test_ok.py": OK_SRC.format(name="One"),
                         "skills/tests/test_final_run.py": HEAVY_BAD_SRC,
                         "skills/tests/test_triggers.py": HEAVY_BAD_SRC.replace("planted-heavy-failure", "planted-triggers-failure")})
        write(repo, "skills/brainstorm/SKILL.md", "b\n")
        git(repo, "commit", "-q", "-am", "change")

    def test_skips_heavy_for_text_only_diff(self):
        with tempfile.TemporaryDirectory() as repo:
            self.setup_dirs(repo)
            out = io.StringIO()
            code = run_tests.main([], repo=pathlib.Path(repo), suites=self.SUITES, out=out)
            self.assertEqual(code, 0)
            self.assertTrue(out.getvalue().startswith("skipped: test_final_run, test_triggers (diff touches no write-skill scripts, skills/tests, runtime, hooks, sdlc.py or using-tl-relay)\n"))

    def test_all_flag_runs_heavy(self):
        with tempfile.TemporaryDirectory() as repo:
            self.setup_dirs(repo)
            out = io.StringIO()
            code = run_tests.main(["--all"], repo=pathlib.Path(repo), suites=self.SUITES, out=out)
            self.assertEqual(code, 1)
            self.assertIn("planted-heavy-failure", out.getvalue())
            self.assertIn("planted-triggers-failure", out.getvalue())

    def test_not_a_repo_falls_back_to_running_everything(self):
        with tempfile.TemporaryDirectory() as repo:
            write(repo, "skills/tests/test_ok.py", OK_SRC.format(name="One"))
            write(repo, "skills/tests/test_final_run.py", HEAVY_BAD_SRC)
            out = io.StringIO()
            code = run_tests.main([], repo=pathlib.Path(repo), suites=self.SUITES, out=out)
            self.assertEqual(code, 1)
            self.assertIn("planted-heavy-failure", out.getvalue())
            self.assertNotIn("skipped:", out.getvalue())

    def test_unknown_flag_exits_2(self):
        with tempfile.TemporaryDirectory() as repo:
            write(repo, "skills/tests/test_ok.py", OK_SRC.format(name="One"))
            with self.assertRaises(SystemExit) as ctx:
                run_tests.main(["--bogus"], repo=pathlib.Path(repo), suites=self.SUITES, out=io.StringIO())
            self.assertEqual(ctx.exception.code, 2)


class SuitesTest(unittest.TestCase):
    def test_two_python_suites_and_a_shell_suite_share_one_run(self):
        with tempfile.TemporaryDirectory() as repo:
            write(repo, "a/test_ok.py", OK_SRC.format(name="InA"))
            write(repo, "b/test_ok.py", OK_SRC.format(name="InB"))
            write(repo, "s.sh", "exit 0\n")
            suites = (run_tests.Suite("a", "py", None), run_tests.Suite("b", "py", None), run_tests.Suite("s.sh", "sh", None))
            out = io.StringIO()
            self.assertEqual(run_tests.main(["--all"], repo=pathlib.Path(repo), suites=suites, out=out), 0)
            self.assertEqual(out.getvalue().strip().splitlines()[-1], "OK (3 units)")

    def test_a_shell_suite_fails_on_exit_code_alone(self):
        with tempfile.TemporaryDirectory() as repo:
            write(repo, "s.sh", "echo OK\necho 'FAIL planted-sh-cause'\necho OK >&2\nexit 1\n")
            out = io.StringIO()
            code = run_tests.main(["--all"], repo=pathlib.Path(repo), suites=(run_tests.Suite("s.sh", "sh", None),), out=out)
            self.assertEqual(code, 1)
            self.assertIn("\nFAIL s.sh\n", "\n" + out.getvalue())
            self.assertIn("planted-sh-cause", out.getvalue())

    def test_final_run_units_run_first(self):
        with tempfile.TemporaryDirectory() as repo:
            write(repo, "t/test_aaa.py", OK_SRC.format(name="A"))
            write(repo, "t/test_final_run.py", OK_SRC.format(name="F"))
            units = run_tests.order(run_tests.suite_units(pathlib.Path(repo), run_tests.Suite("t", "py", None), set()))
            self.assertIn("test_final_run", units[0].argv[-1])

    def test_final_run_and_shell_units_run_before_other_units(self):
        with tempfile.TemporaryDirectory() as repo:
            write(repo, "t/test_aaa.py", OK_SRC.format(name="A"))
            write(repo, "t/test_final_run.py", OK_SRC.format(name="F"))
            write(repo, "s.sh", "exit 0\n")
            units = run_tests.suite_units(pathlib.Path(repo), run_tests.Suite("t", "py", None), set())
            units += run_tests.suite_units(pathlib.Path(repo), run_tests.Suite("s.sh", "sh", None), set())
            first = {u.suite if u.kind == "sh" else u.argv[-1].split(".")[0] for u in run_tests.order(units)[:2]}
            self.assertEqual(first, {"s.sh", "test_final_run"})

    WARM_SUITES = (run_tests.Suite("skills/write-contract/scripts", "py", None), run_tests.Suite("t", "py", None))

    def warm_calls(self, suites):
        with tempfile.TemporaryDirectory() as repo:
            write(repo, "skills/write-contract/scripts/test_a.py", OK_SRC.format(name="A"))
            write(repo, "t/test_b.py", OK_SRC.format(name="B"))
            calls = []
            code = run_tests.main(["--all"], repo=pathlib.Path(repo), suites=suites, out=io.StringIO(),
                                  warmup=lambda: calls.append(1))
            self.assertEqual(code, 0)
            return len(calls)

    def test_the_npx_cache_warms_once_when_a_write_contract_unit_is_queued(self):
        self.assertEqual(self.warm_calls(self.WARM_SUITES), 1)

    def test_a_stalled_npx_warm_up_prints_one_line_and_returns(self):
        spec = run_tests.redocly_spec(pathlib.Path(run_tests.__file__).resolve().parents[2])

        def stall(*args, **kwargs):
            self.assertEqual(kwargs["timeout"], 120)
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

        real = run_tests.subprocess.run
        run_tests.subprocess.run = stall
        try:
            out = io.StringIO()
            run_tests.npx_warmup(pathlib.Path(run_tests.__file__).resolve().parents[2], out)
        finally:
            run_tests.subprocess.run = real
        self.assertEqual(out.getvalue(), "warmup: npx --yes %s --version timed out after 120s\n" % spec)

    LEAK_SET = "import os\nimport unittest\nos.environ['RUN_TESTS_LEAK'] = '1'\n\nclass T(unittest.TestCase):\n    def test_it(self):\n        pass\n"
    LEAK_CHECK = "import os\nimport unittest\n\nclass T(unittest.TestCase):\n    def test_it(self):\n        self.assertNotIn('RUN_TESTS_LEAK', os.environ)\n"
    ENV_CHECK = ("import os\nimport unittest\n\nclass T(unittest.TestCase):\n    def test_it(self):\n"
                 "        self.assertEqual(os.environ.get('RUN_TESTS_LEAK'), 'given')\n"
                 "        self.assertNotIn('HOME', os.environ)\n")

    def test_an_import_time_env_change_does_not_reach_another_suite(self):
        with mock.patch.dict(os.environ, {}), tempfile.TemporaryDirectory() as repo:
            write(repo, "a/test_set.py", self.LEAK_SET)
            write(repo, "b/test_check.py", self.LEAK_CHECK)
            suites = (run_tests.Suite("a", "py", None), run_tests.Suite("b", "py", None))
            out = io.StringIO()
            code = run_tests.main(["--all"], repo=pathlib.Path(repo), suites=suites, out=out)
            text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertEqual(text.strip().splitlines()[-1], "OK (2 units)")

    def test_run_passes_the_given_env_to_each_child(self):
        with tempfile.TemporaryDirectory() as repo:
            write(repo, "t/test_env.py", self.ENV_CHECK)
            env = {k: v for k, v in os.environ.items() if k != "HOME"}
            env["RUN_TESTS_LEAK"] = "given"
            units = run_tests.suite_units(pathlib.Path(repo), run_tests.Suite("t", "py", None), set())
            out = io.StringIO()
            code = run_tests.run(units, 2, out, env=env)
        self.assertEqual(code, 0, out.getvalue())

    def test_npx_warmup_builds_its_child_env_from_the_given_env(self):
        recorded = {}

        def record(*args, **kwargs):
            recorded.update(kwargs)

        real = run_tests.subprocess.run
        run_tests.subprocess.run = record
        repo = pathlib.Path(run_tests.__file__).resolve().parents[2]
        try:
            run_tests.npx_warmup(repo, io.StringIO(), {"X": "y"})
        finally:
            run_tests.subprocess.run = real
        self.assertEqual(recorded["env"], {"X": "y", "REDOCLY_TELEMETRY": "off"})
        self.assertEqual(recorded["cwd"], str(repo))

    def test_main_hands_run_the_environment_from_before_collection(self):
        recorded = {}

        def record(units, jobs, out, env=None):
            recorded["env"] = env
            return 0

        real = run_tests.run
        with mock.patch.dict(os.environ, {}), tempfile.TemporaryDirectory() as repo:
            write(repo, "a/test_set.py", self.LEAK_SET)
            expected = {k: v for k, v in os.environ.items() if k not in run_tests.GIT_ENV_DROP}
            run_tests.run = record
            try:
                run_tests.main(["--all"], repo=pathlib.Path(repo), suites=(run_tests.Suite("a", "py", None),), out=io.StringIO())
            finally:
                run_tests.run = real
        self.assertNotIn("RUN_TESTS_LEAK", recorded["env"])
        self.assertEqual(recorded["env"], expected)

    def test_main_drops_git_location_vars_from_the_child_env(self):
        recorded = {}

        def record(units, jobs, out, env=None):
            recorded["env"] = env
            return 0

        planted = {name: "/run-tests-leak" for name in run_tests.GIT_ENV_DROP}
        real = run_tests.run
        with mock.patch.dict(os.environ, dict(planted, RUN_TESTS_KEEP="1")), tempfile.TemporaryDirectory() as repo:
            write(repo, "a/test_ok.py", OK_SRC.format(name="One"))
            run_tests.run = record
            try:
                run_tests.main(["--all"], repo=pathlib.Path(repo), suites=(run_tests.Suite("a", "py", None),), out=io.StringIO())
            finally:
                run_tests.run = real
        self.assertEqual([name for name in run_tests.GIT_ENV_DROP if name in recorded["env"]], [])
        self.assertEqual(recorded["env"].get("RUN_TESTS_KEEP"), "1")

    def test_the_redocly_spec_is_read_from_the_real_contract_script(self):
        repo = pathlib.Path(run_tests.__file__).resolve().parents[2]
        self.assertTrue(run_tests.redocly_spec(repo).startswith("@redocly/cli@"))

    def test_the_npx_cache_stays_cold_without_a_write_contract_unit(self):
        self.assertEqual(self.warm_calls(self.WARM_SUITES[1:]), 0)

    def test_default_suites_exist_in_the_repo(self):
        repo = pathlib.Path(run_tests.__file__).resolve().parents[2]
        for suite in run_tests.SUITES:
            self.assertTrue((repo / suite.path).exists(), suite.path)

    SKIP_SUITES = (run_tests.Suite("t", "py", None), run_tests.Suite("c", "py", "c/"))
    SKIP_FILES = {"README.md": "a\n", "c/old.txt": "x\n", "t/test_ok.py": OK_SRC.format(name="One"),
                  "c/test_bad.py": BAD_SRC.replace("self.fail('nope')", "self.fail('planted-c-failure')")}

    def run_main(self, repo, argv, suites=None):
        out = io.StringIO()
        code = run_tests.main(argv, repo=pathlib.Path(repo), suites=suites or self.SKIP_SUITES, out=out)
        return code, out.getvalue()

    def main_with_change(self, name, *argv):
        with tempfile.TemporaryDirectory() as repo:
            make_repo(repo, self.SKIP_FILES)
            write(repo, name, "changed\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "change")
            return self.run_main(repo, list(argv))

    def main_with_rename(self, old, new):
        with tempfile.TemporaryDirectory() as repo:
            make_repo(repo, self.SKIP_FILES)
            (pathlib.Path(repo) / new).parent.mkdir(parents=True, exist_ok=True)
            git(repo, "mv", old, new)
            git(repo, "commit", "-q", "-m", "rename")
            return self.run_main(repo, [])

    def main_without_base(self):
        with tempfile.TemporaryDirectory() as repo:
            git(repo, "init", "-q")
            for name, text in self.SKIP_FILES.items():
                write(repo, name, text)
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "base")
            return self.run_main(repo, [])

    def main_with_heavy_and_change(self, name):
        files = dict(self.SKIP_FILES)
        files["skills/tests/test_final_run.py"] = HEAVY_BAD_SRC
        suites = (run_tests.Suite("skills/tests", "py", None), run_tests.Suite("c", "py", "c/"))
        with tempfile.TemporaryDirectory() as repo:
            make_repo(repo, files)
            write(repo, name, "changed\n")
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", "change")
            return self.run_main(repo, [], suites)

    def test_a_suite_skips_when_the_diff_misses_its_prefix(self):
        code, text = self.main_with_change("README.md")
        self.assertEqual(code, 0)
        self.assertIn("skipped: c (diff touches nothing under c/)\n", text)

    def test_a_suite_runs_when_the_diff_touches_its_prefix(self):
        code, text = self.main_with_change("c/x.txt")
        self.assertEqual(code, 1)
        self.assertIn("planted-c-failure", text)

    def test_a_rename_out_of_the_prefix_still_runs_the_suite(self):
        code, text = self.main_with_rename("c/old.txt", "lib/new.txt")
        self.assertEqual(code, 1)
        self.assertIn("planted-c-failure", text)
        self.assertNotIn("skipped: c", text)

    def test_a_runner_change_runs_every_skippable_suite(self):
        code, text = self.main_with_change("skills/tests/run_tests.py")
        self.assertEqual(code, 1)
        self.assertIn("planted-c-failure", text)
        self.assertNotIn("skipped: c", text)

    def test_all_runs_a_skippable_suite(self):
        code, text = self.main_with_change("README.md", "--all")
        self.assertEqual(code, 1)
        self.assertNotIn("skipped: c", text)

    def test_no_origin_main_skips_nothing(self):
        code, text = self.main_without_base()
        self.assertEqual(code, 1)
        self.assertNotIn("skipped:", text)

    def test_default_skip_prefixes(self):
        rules = {s.path: s.skip_unless for s in run_tests.SUITES}
        self.assertEqual(rules["skills/write-contract/scripts"], "skills/write-contract/")
        self.assertEqual(rules["maintainer/runtime/tests"], "maintainer/")
        self.assertEqual([p for p, r in rules.items() if r], ["maintainer/runtime/tests", "skills/write-contract/scripts"])

    def test_the_heavy_line_prints_before_suite_skip_lines(self):
        code, text = self.main_with_heavy_and_change("README.md")
        self.assertEqual(code, 0)
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("skipped: test_final_run, test_triggers"))
        self.assertEqual(lines[1], "skipped: c (diff touches nothing under c/)")


if __name__ == "__main__":
    unittest.main()
