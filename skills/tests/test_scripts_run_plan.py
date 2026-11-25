import os
import pathlib
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

SKILLS = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = SKILLS / "run-plan" / "scripts"
BASH = shutil.which("bash")
IS_ROOT = getattr(os, "geteuid", lambda: -1)() == 0


def _can_symlink() -> bool:
    with tempfile.TemporaryDirectory() as d:
        try:
            os.symlink("target", os.path.join(d, "link"))
        except (OSError, NotImplementedError):
            return False
    return True


CAN_SYMLINK = _can_symlink()

SDD_PREFIX = "SDD scripts must run from inside the git working tree you're executing in"
SDD_MESSAGE = (
    "SDD scripts must run from inside the git working tree you're executing in, "
    "with at least one commit (current directory: {cwd}). "
    "If this is a new project, run 'git init' and make a first commit, then rerun.\n"
)

PLAN = """# Plan title

## Task 1: one
one body

### Task 2: two
two body

#### Task 2.1: sub
sub body

### Task 3: three
three body

### Task 6: six
six body

### Task 6b: six b
six b body

## Task A1 - alpha
alpha body
"""

USAGE_WORKSPACE = "usage: sdd-workspace [-C DIR] --runs-dir DIR PLAN_FILE\n"
USAGE_BRIEF = "usage: task-brief [-C DIR] [--runs-dir DIR] PLAN_FILE TASK_NUMBER [OUTFILE]\n"
USAGE_REVIEW = "usage: review-package [-C DIR] [--runs-dir DIR] PLAN_FILE BASE HEAD [OUTFILE]\n"


class Result:
    def __init__(self, proc):
        self.code = proc.returncode
        self.out = proc.stdout
        self.err = proc.stderr


class Case(unittest.TestCase):
    def setUp(self):
        if BASH is None:
            self.skipTest("no bash on PATH")
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = pathlib.Path(os.path.realpath(holder.name))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.plain = self.tmp / "plain"
        self.plain.mkdir()
        self.runs = self.tmp / "runs"
        old_umask = os.umask(0o022)
        self.addCleanup(os.umask, old_umask)
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith("GIT_") and k not in ("XDG_CONFIG_HOME", "CDPATH", "BASH_ENV", "ENV")
        }
        env.update(
            HOME=str(self.home),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_AUTHOR_NAME="T",
            GIT_AUTHOR_EMAIL="t@example.com",
            GIT_COMMITTER_NAME="T",
            GIT_COMMITTER_EMAIL="t@example.com",
            GIT_CEILING_DIRECTORIES=str(self.tmp),
            LC_ALL="C",
        )
        self.env = env
        self.bash = BASH
        self.copies = 0
        self.repos = []
        self.addCleanup(self.assert_core_worktree_unset)

    def assert_core_worktree_unset(self):
        for repo in self.repos:
            proc = subprocess.run(
                ["git", "-C", str(repo), "config", "--get", "core.worktree"],
                env=self.env, capture_output=True, text=True,
            )
            self.assertEqual(proc.stdout, "")

    def copy_scripts(self, mode=None):
        self.copies += 1
        dest = self.tmp / f"skill{self.copies}" / "scripts"
        shutil.copytree(SCRIPTS, dest)
        if mode is not None:
            for p in dest.iterdir():
                p.chmod(mode)
        return dest

    def run_script(self, name, args, cwd=None, relative=False, scripts=None, path_prefix=None, bare=False, timeout=None, runs=True):
        args = list(args)
        if runs and name in ("sdd-workspace", "task-brief", "review-package"):
            at = 2 if args[:1] == ["-C"] else 0
            args[at:at] = ["--runs-dir", self.runs]
        if bare:
            scripts = scripts or self.copy_scripts()
            cwd = scripts
            target = name
        elif relative:
            scripts = scripts or self.copy_scripts()
            cwd = scripts.parent
            target = f"{scripts.name}/{name}"
        else:
            cwd = pathlib.Path(cwd) if cwd else self.plain
            target = str((scripts or SCRIPTS) / name)
        env = dict(self.env, PWD=str(cwd))
        if path_prefix:
            env["PATH"] = f"{path_prefix}:{env['PATH']}"
        proc = subprocess.run(
            [self.bash, target, *[str(a) for a in args]],
            cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
        )
        return Result(proc)

    def assert_sdd_failure(self, r, cwd, exact=False, said="git said: "):
        lines = r.err.splitlines(keepends=True)
        self.assertEqual((r.code, r.out), (2, ""))
        self.assertEqual(len(lines), 2, r.err)
        if exact:
            self.assertEqual(lines[0], SDD_MESSAGE.format(cwd=cwd))
        else:
            self.assertTrue(lines[0].startswith(SDD_PREFIX), lines[0])
            self.assertIn(f"(current directory: {cwd})", lines[0])
        self.assertTrue(lines[1].startswith(said), lines[1])
        return lines

    def git(self, repo, *args, raw=False):
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout if raw else proc.stdout.strip()

    def write(self, path, text):
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode())
        return path

    def init(self, name="repo"):
        repo = self.tmp / name
        repo.mkdir()
        self.git(repo, "init", "-q")
        self.git(repo, "config", "user.name", "T")
        self.git(repo, "config", "user.email", "t@example.com")
        self.git(repo, "config", "commit.gpgsign", "false")
        self.repos.append(repo)
        return repo

    def commit(self, repo, files, message="c"):
        for rel, text in files.items():
            self.write(repo / rel, text)
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", message)
        return self.git(repo, "rev-parse", "HEAD")

    def repo(self, name="repo", commit=True):
        repo = self.init(name)
        if commit:
            self.commit(repo, {"seed.txt": "seed\n"}, "seed")
        return repo

    def sdd(self, repo):
        return self.runs

    def tree(self, root):
        return sorted(str(p.relative_to(root)) for p in pathlib.Path(root).rglob("*"))


class ScriptFileTests(unittest.TestCase):
    NAMES = ("sdd-repo", "sdd-workspace", "task-brief", "review-package")

    def test_scripts_use_env_bash_shebang_and_strict_options(self):
        for name in self.NAMES:
            with self.subTest(name=name):
                text = (SCRIPTS / name).read_text()
                self.assertEqual(text.splitlines()[0], "#!/usr/bin/env bash")
                self.assertIn("\nset -euo pipefail\n", text)

    def test_git_records_the_scripts_as_executable(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        probe = subprocess.run(
            ["git", "-C", str(SCRIPTS), "rev-parse", "--show-toplevel"],
            env=env, capture_output=True, text=True,
        )
        if probe.returncode != 0:
            self.skipTest("the scripts are not inside a git checkout")
        for name in self.NAMES:
            with self.subTest(name=name):
                proc = subprocess.run(
                    ["git", "-C", str(SCRIPTS), "ls-files", "-s", "--", name],
                    env=env, capture_output=True, text=True,
                )
                self.assertTrue(proc.stdout.startswith("100755 "), proc.stdout)


class ImportTests(unittest.TestCase):
    def test_module_imports_without_os_geteuid(self):
        code = (
            "import os, sys\n"
            "os.__dict__.pop('geteuid', None)\n"
            f"sys.path.insert(0, {str(pathlib.Path(__file__).parent)!r})\n"
            "import test_scripts_run_plan as m\n"
            "print(m.IS_ROOT)\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual((proc.returncode, proc.stdout), (0, "False\n"), proc.stderr)

    def test_symlink_tests_skip_without_symlink_rights(self):
        here = pathlib.Path(__file__).resolve().parent
        names = [
            "test_scripts_run_plan.SddRepoTests.test_failure_message_shows_the_logical_current_directory",
            "test_scripts_run_plan.SddWorkspaceTests.test_failure_message_shows_the_c_directory_as_spelled_through_a_symlink",
            "test_scripts_run_plan.SddWorkspaceTests.test_symlinked_repository_path_prints_the_physical_workspace",
            "test_scripts_run_plan.SddWorkspaceTests.test_gitignore_symlink_is_never_written_through",
            "test_scripts_run_plan.SddWorkspaceTests.test_candidate_that_is_a_dangling_symlink_falls_through_to_the_next",
            "test_scripts_run_plan.SddWorkspaceTests.test_symlinked_marker_is_never_written_or_trusted",
            "test_scripts_run_plan.SddWorkspaceTests.test_symlinked_candidate_directory_is_never_adopted",
            "test_scripts_run_plan.SddWorkspaceTests.test_claim_skips_a_stem_candidate_that_is_a_symlink",
            "test_scripts_run_plan.SddWorkspaceTests.test_candidate_swapped_for_a_symlink_before_the_write_is_skipped",
            "test_scripts_run_plan.SddWorkspaceTests.test_symlinked_workspace_of_this_plan_is_reported",
            "test_scripts_run_plan.SddWorkspaceTests.test_symlinked_workspace_of_another_plan_is_skipped_silently",
            "test_scripts_run_plan.SddWorkspaceTests.test_symlinked_workspace_with_a_symlinked_marker_is_skipped_silently",
            "test_scripts_run_plan.TaskBriefTests.test_missing_task_with_a_symlink_outfile_keeps_the_link",
            "test_scripts_run_plan.TaskBriefTests.test_unclosed_fence_with_a_symlink_outfile_keeps_the_link",
        ]
        code = (
            "import os, sys, unittest\n"
            "def deny(*a, **k):\n"
            "    raise OSError(1314, 'A required privilege is not held by the client')\n"
            "os.symlink = deny\n"
            f"sys.path[:0] = [{str(here)!r}]\n"
            f"suite = unittest.defaultTestLoader.loadTestsFromNames({names!r})\n"
            "r = unittest.TextTestRunner(stream=open(os.devnull, 'w')).run(suite)\n"
            "print(r.testsRun, len(r.skipped), len(r.errors), len(r.failures))\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
        self.assertEqual((proc.returncode, proc.stdout), (0, "14 14 0 0\n"), proc.stderr)


def stock_bash3():
    path = "/bin/bash"
    if not os.path.exists(path):
        return None
    proc = subprocess.run([path, "--version"], capture_output=True, text=True)
    return path if proc.stdout.startswith("GNU bash, version 3.") else None


@unittest.skipUnless(stock_bash3(), "/bin/bash is absent or not bash 3.x")
class Bash3Tests(Case):
    def setUp(self):
        super().setUp()
        self.bash = stock_bash3()

    def test_every_script_runs_its_happy_path_under_bash_3(self):
        repo = self.repo()
        self.write(repo / "plan.md", PLAN)
        self.commit(repo, {"n.txt": "n\n"}, "next")
        runs = [
            ("sdd-repo", ["--with-commit"], f"{repo}\n"),
            ("sdd-workspace", ["plan.md"], f"{self.sdd(repo) / 'plan'}\n"),
            ("task-brief", ["plan.md", "3"], f"wrote {self.sdd(repo) / 'plan' / 'task-3-brief.md'}: 3 lines\n"),
        ]
        for name, args, expected in runs:
            with self.subTest(name=name):
                r = self.run_script(name, args, cwd=repo)
                self.assertEqual((r.code, r.out, r.err), (0, expected, ""))
        r = self.run_script("task-brief", ["plan.md", "3", "given.md"], cwd=repo)
        self.assertEqual((r.code, r.out, r.err), (0, "wrote given.md: 3 lines\n", ""))
        r = self.run_script("review-package", ["plan.md", "HEAD~1", "HEAD"], cwd=repo)
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertTrue(r.out.startswith("wrote "))
        self.assertIn(": 1 commit(s), ", r.out)


class SddRepoTests(Case):
    def test_extra_arguments_print_usage_and_exit_2(self):
        repo = self.repo()
        for args in (["--help"], ["foo"], ["--with-commit", "--with-commit"], ["foo", "--with-commit"]):
            with self.subTest(args=args):
                r = self.run_script("sdd-repo", args, cwd=repo)
                self.assertEqual((r.code, r.out, r.err), (2, "", "usage: sdd-repo [--with-commit]\n"))

    def test_prints_toplevel_with_newline_and_nothing_on_stderr(self):
        repo = self.repo()
        r = self.run_script("sdd-repo", [], cwd=repo)
        self.assertEqual((r.code, r.out, r.err), (0, f"{repo}\n", ""))

    def test_prints_toplevel_from_a_subdirectory(self):
        repo = self.repo()
        sub = repo / "a" / "b"
        sub.mkdir(parents=True)
        r = self.run_script("sdd-repo", [], cwd=sub)
        self.assertEqual((r.code, r.out, r.err), (0, f"{repo}\n", ""))

    def test_repository_without_commit_succeeds_without_flag(self):
        repo = self.repo(commit=False)
        r = self.run_script("sdd-repo", [], cwd=repo)
        self.assertEqual((r.code, r.out, r.err), (0, f"{repo}\n", ""))

    def test_with_commit_succeeds_when_head_exists(self):
        repo = self.repo()
        r = self.run_script("sdd-repo", ["--with-commit"], cwd=repo)
        self.assertEqual((r.code, r.out, r.err), (0, f"{repo}\n", ""))

    def test_outside_a_repository_exits_2_with_shared_message(self):
        r = self.run_script("sdd-repo", [], cwd=self.plain)
        self.assert_sdd_failure(r, self.plain, said="git said: fatal: not a git repository")

    def test_with_commit_in_repository_without_commit_exits_2(self):
        repo = self.repo(commit=False)
        r = self.run_script("sdd-repo", ["--with-commit"], cwd=repo)
        lines = self.assert_sdd_failure(r, repo, exact=True, said="git said: fatal:")
        self.assertIn("Needed a single revision", lines[1])

    def test_inside_dot_git_exits_2_with_shared_message(self):
        repo = self.repo()
        r = self.run_script("sdd-repo", [], cwd=repo / ".git")
        self.assert_sdd_failure(r, repo / ".git", said="git said: fatal:")

    def test_only_the_first_line_of_a_multi_line_git_error_is_quoted(self):
        repo = self.repo()
        self.git(repo, "config", "core.repositoryformatversion", "1")
        self.git(repo, "config", "extensions.zzzunknown", "true")
        self.addCleanup(self.drop_unknown_extension, repo)
        probe = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
            env=self.env, capture_output=True, text=True,
        )
        git_lines = probe.stderr.splitlines()
        if probe.returncode == 0 or len(git_lines) < 2:
            self.skipTest("git does not print a multi-line error for an unknown extension")
        r = self.run_script("sdd-repo", [], cwd=repo)
        lines = self.assert_sdd_failure(r, repo, said="git said: fatal:")
        self.assertEqual(lines[1], f"git said: {git_lines[0]}\n")

    def drop_unknown_extension(self, repo):
        for args in (
            ["config", "core.repositoryformatversion", "0"],
            ["config", "--unset", "extensions.zzzunknown"],
        ):
            subprocess.run(["git", "-C", str(repo), *args], env=self.env, capture_output=True)

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_failure_message_shows_the_logical_current_directory(self):
        link = self.tmp / "link"
        link.symlink_to(self.plain, target_is_directory=True)
        r = self.run_script("sdd-repo", [], cwd=link)
        self.assert_sdd_failure(r, link, said="git said: fatal:")

    def test_creates_no_files(self):
        repo = self.repo()
        before = self.tree(repo)
        self.run_script("sdd-repo", ["--with-commit"], cwd=repo)
        self.assertEqual(self.tree(repo), before)


class SddWorkspaceTests(Case):
    def plan(self, repo, rel, text="plan\n"):
        return self.write(repo / rel, text)

    def ws(self, repo, rel, *flags):
        r = self.run_script("sdd-workspace", [*flags, rel], cwd=repo)
        self.assertEqual((r.code, r.err), (0, ""), r.err)
        return pathlib.Path(r.out.rstrip("\n"))

    def test_wrong_argument_count_prints_usage_and_exits_2(self):
        repo = self.repo()
        self.plan(repo, "plan.md")
        cases = [[], ["plan.md", "plan.md"], ["-C", str(repo)], ["plan.md", "-C", str(repo)]]
        for args in cases:
            with self.subTest(args=args):
                r = self.run_script("sdd-workspace", args, cwd=repo)
                self.assertEqual((r.code, r.out, r.err), (2, "", USAGE_WORKSPACE))

    def test_bad_c_directory_exits_2(self):
        a_file = self.write(self.tmp / "afile", "x")
        for given, shown in (("/no/such/dir", "/no/such/dir"), ("", ""), (str(a_file), str(a_file))):
            with self.subTest(given=given):
                r = self.run_script("sdd-workspace", ["-C", given, "plan.md"])
                self.assertEqual((r.code, r.out, r.err), (2, "", f"bad -C directory: {shown}\n"))

    def test_c_without_value_is_a_bad_directory(self):
        r = self.run_script("sdd-workspace", ["-C"], runs=False)
        self.assertEqual((r.code, r.out, r.err), (2, "", "bad -C directory: \n"))

    def test_missing_plan_file_exits_2(self):
        repo = self.repo()
        r = self.run_script("sdd-workspace", ["nope.md"], cwd=repo)
        self.assertEqual((r.code, r.out, r.err), (2, "", "no such plan file: nope.md\n"))

    def test_directory_as_plan_file_exits_2(self):
        repo = self.repo()
        (repo / "docs").mkdir()
        r = self.run_script("sdd-workspace", ["docs"], cwd=repo)
        self.assertEqual((r.code, r.out, r.err), (2, "", "no such plan file: docs\n"))

    def test_plan_error_wins_over_missing_repository(self):
        r = self.run_script("sdd-workspace", ["nope.md"], cwd=self.plain)
        self.assertEqual((r.code, r.out, r.err), (2, "", "no such plan file: nope.md\n"))

    def test_outside_a_repository_exits_2_with_shared_message(self):
        self.write(self.plain / "plan.md", "x")
        r = self.run_script("sdd-workspace", ["plan.md"], cwd=self.plain)
        self.assert_sdd_failure(r, self.plain, said="git said: fatal:")
        self.assertEqual(self.tree(self.plain), ["plan.md"])

    def test_c_directory_is_where_the_repository_is_looked_up(self):
        repo = self.repo()
        self.plan(repo, "plan.md")
        r = self.run_script("sdd-workspace", ["-C", repo, "plan.md"], cwd=self.plain)
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertEqual(r.out, f"{self.sdd(repo) / 'plan'}\n")

    def test_failure_message_names_the_c_directory_as_current_directory(self):
        self.write(self.plain / "plan.md", "x")
        r = self.run_script("sdd-workspace", ["-C", self.plain, "plan.md"], cwd=self.tmp)
        self.assert_sdd_failure(r, self.plain, said="git said: fatal:")

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_failure_message_shows_the_c_directory_as_spelled_through_a_symlink(self):
        link = self.tmp / "link"
        link.symlink_to(self.plain, target_is_directory=True)
        self.write(self.plain / "plan.md", "x")
        r = self.run_script("sdd-workspace", ["-C", link, "plan.md"], cwd=self.tmp)
        self.assert_sdd_failure(r, link, said="git said: fatal:")

    def test_script_directory_is_taken_before_c_changes_directory(self):
        repo = self.repo()
        self.plan(repo, "plan.md")
        r = self.run_script("sdd-workspace", ["-C", repo, "plan.md"], relative=True)
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertEqual(r.out, f"{self.sdd(repo) / 'plan'}\n")

    def test_children_run_through_the_interpreter_without_exec_bits(self):
        repo = self.repo()
        self.write(repo / "plan.md", PLAN)
        self.commit(repo, {"n.txt": "n\n"}, "next")
        scripts = self.copy_scripts(mode=0o644)
        runs = [
            ("sdd-workspace", ["-C", repo, "plan.md"]),
            ("task-brief", ["-C", repo, "plan.md", "3"]),
            ("review-package", ["-C", repo, "plan.md", "HEAD~1", "HEAD"]),
        ]
        for name, args in runs:
            with self.subTest(name=name):
                r = self.run_script(name, args, scripts=scripts, cwd=self.plain)
                self.assertEqual((r.code, r.err), (0, ""))

    def test_bare_script_name_resolves_siblings_from_the_scripts_directory(self):
        repo = self.repo()
        self.write(repo / "plan.md", PLAN)
        self.commit(repo, {"n.txt": "n\n"}, "next")
        scripts = self.copy_scripts()
        runs = [
            ("sdd-workspace", ["-C", repo, "plan.md"]),
            ("task-brief", ["-C", repo, "plan.md", "3"]),
            ("review-package", ["-C", repo, "plan.md", "HEAD~1", "HEAD"]),
        ]
        for name, args in runs:
            with self.subTest(name=name):
                r = self.run_script(name, args, scripts=scripts, bare=True)
                self.assertEqual((r.code, r.err), (0, ""))

    def test_cygpath_output_replaces_the_printed_path_but_not_the_marker(self):
        repo = self.repo()
        self.plan(repo, "plan.md")
        stub = self.tmp / "stubbin"
        stub.mkdir()
        calls = self.tmp / "cygpath.calls"
        self.write(stub / "cygpath", f'#!/bin/sh\necho "$*" >> {calls}\necho C:/x\n')
        (stub / "cygpath").chmod(0o755)
        r = self.run_script("sdd-workspace", ["plan.md"], cwd=repo, path_prefix=stub)
        self.assertEqual((r.code, r.out, r.err), (0, "C:/x\n", ""))
        self.assertEqual(calls.read_text(), f"-m {self.sdd(repo) / 'plan'}\n")
        self.assertEqual((self.sdd(repo) / "plan" / "plan-path").read_bytes(), f"{repo / 'plan.md'}\n".encode())

    def test_linked_worktree_workspace_sits_in_the_runs_dir(self):
        repo = self.repo()
        plan = self.plan(repo, "docs/plan.md", PLAN)
        wt = self.tmp / "wt"
        self.git(repo, "worktree", "add", "-q", str(wt), "-b", "wtb")
        r = self.run_script("sdd-workspace", ["-C", wt, plan], cwd=self.plain)
        self.assertEqual((r.code, r.err), (0, ""))
        workspace = self.runs / "plan"
        self.assertEqual(r.out, f"{workspace}\n")
        self.assertEqual((workspace / "plan-path").read_bytes(), f"{plan}\n".encode())
        self.assertFalse((repo / ".tl-relay").exists())
        self.assertFalse((wt / ".tl-relay").exists())
        r = self.run_script("task-brief", ["-C", wt, plan, "3"], cwd=self.plain)
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertTrue((workspace / "task-3-brief.md").is_file())

    def test_prints_workspace_path_and_writes_marker_with_repo_relative_plan(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo)
        workspace = self.sdd(repo) / "plan"
        self.assertEqual((r.code, r.out, r.err), (0, f"{workspace}\n", ""))
        self.assertEqual((workspace / "plan-path").read_bytes(), f"{repo / 'docs/alpha/plan.md'}\n".encode())

    def test_marker_is_mode_0644_and_directories_0755(self):
        repo = self.repo()
        self.plan(repo, "plan.md")
        workspace = self.ws(repo, "plan.md")
        self.assertEqual(stat.S_IMODE((workspace / "plan-path").stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(workspace.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(self.sdd(repo).stat().st_mode), 0o755)

    def test_creates_only_the_workspace_marker_and_gitignore(self):
        repo = self.repo()
        self.plan(repo, "plan.md")
        self.ws(repo, "plan.md")
        self.assertEqual(self.tree(self.runs), [".gitignore", "plan", "plan/plan-path"])
        self.assertFalse((repo / ".tl-relay").exists())

    def test_plan_outside_the_repository_is_recorded_as_absolute_path(self):
        repo = self.repo()
        outside = self.write(self.tmp / "elsewhere" / "plan.md", "x")
        r = self.run_script("sdd-workspace", [outside], cwd=repo)
        self.assertEqual((r.code, r.err), (0, ""))
        marker = pathlib.Path(r.out.rstrip("\n")) / "plan-path"
        self.assertEqual(marker.read_bytes(), f"{outside}\n".encode())

    def test_every_spelling_of_one_plan_resolves_to_one_workspace(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        spellings = [
            (repo, ["docs/alpha/plan.md"]),
            (repo, [repo / "docs/alpha/plan.md"]),
            (repo, ["docs/../docs/alpha/plan.md"]),
            (self.plain, ["-C", repo / "docs", "alpha/plan.md"]),
        ]
        outputs = set()
        for cwd, args in spellings:
            with self.subTest(args=args):
                r = self.run_script("sdd-workspace", args, cwd=cwd)
                self.assertEqual((r.code, r.err), (0, ""))
                outputs.add(r.out)
        self.assertEqual(outputs, {f"{self.sdd(repo) / 'plan'}\n"})
        self.assertEqual(
            (self.sdd(repo) / "plan" / "plan-path").read_bytes(), f"{repo / 'docs/alpha/plan.md'}\n".encode()
        )
        self.assertEqual(sorted(p.name for p in self.sdd(repo).iterdir()), [".gitignore", "plan"])

    def test_runs_from_a_subdirectory_and_uses_the_repository_root(self):
        repo = self.repo()
        self.plan(repo, "docs/p.md")
        (repo / "src").mkdir()
        r = self.run_script("sdd-workspace", ["../docs/p.md"], cwd=repo / "src")
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertEqual(r.out, f"{self.sdd(repo) / 'p'}\n")
        self.assertEqual((self.sdd(repo) / "p" / "plan-path").read_bytes(), f"{repo / 'docs/p.md'}\n".encode())

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_symlinked_repository_path_prints_the_physical_workspace(self):
        repo = self.repo()
        self.plan(repo, "docs/p.md")
        link = self.tmp / "link"
        link.symlink_to(repo, target_is_directory=True)
        r = self.run_script("sdd-workspace", ["-C", link, "docs/p.md"], cwd=self.plain)
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertEqual(r.out, f"{self.sdd(repo) / 'p'}\n")
        self.assertEqual((self.sdd(repo) / "p" / "plan-path").read_bytes(), f"{repo / 'docs/p.md'}\n".encode())

    def test_slug_strips_only_a_trailing_md_extension(self):
        repo = self.repo()
        cases = (("plan.md", "plan"), ("plan.txt", "plan.txt"), ("my plan.md", "my plan"), (".md", ".md"))
        for rel, slug in cases:
            with self.subTest(rel=rel):
                self.plan(repo, rel)
                self.assertEqual(self.ws(repo, rel), self.sdd(repo) / slug)

    def test_same_filename_in_other_directories_gets_distinct_workspaces(self):
        repo = self.repo()
        expected = [
            ("docs/alpha/plan.md", "plan"),
            ("docs/beta/plan.md", "plan-beta"),
            ("x/alpha/plan.md", "plan-alpha"),
            ("y/alpha/plan.md", "plan-alpha-2"),
            ("z/alpha/plan.md", "plan-alpha-3"),
        ]
        for rel, name in expected:
            self.plan(repo, rel)
            with self.subTest(rel=rel):
                self.assertEqual(self.ws(repo, rel), self.sdd(repo) / name)
        for rel, name in expected:
            with self.subTest(rerun=rel):
                self.assertEqual(self.ws(repo, rel), self.sdd(repo) / name)
                self.assertEqual(
                    (self.sdd(repo) / name / "plan-path").read_bytes(), f"{repo / rel}\n".encode()
                )

    def test_marker_comparison_ignores_trailing_newlines(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        self.write(self.sdd(repo) / "plan" / "plan-path", f"{repo / 'docs/alpha/plan.md'}\n\n\n")
        self.assertEqual(self.ws(repo, "docs/alpha/plan.md"), self.sdd(repo) / "plan")

    def test_workspace_without_marker_is_adopted_and_keeps_its_files(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        self.write(self.sdd(repo) / "plan" / "progress.md", "ledger\n")
        workspace = self.ws(repo, "docs/alpha/plan.md")
        self.assertEqual(workspace, self.sdd(repo) / "plan")
        self.assertEqual((workspace / "progress.md").read_text(), "ledger\n")
        self.assertEqual((workspace / "plan-path").read_bytes(), f"{repo / 'docs/alpha/plan.md'}\n".encode())

    def test_gitignore_is_written_as_a_star_when_absent(self):
        repo = self.repo()
        self.plan(repo, "plan.md")
        self.ws(repo, "plan.md")
        self.assertEqual((self.sdd(repo) / ".gitignore").read_bytes(), b"*\n")

    def test_existing_gitignore_is_never_overwritten(self):
        repo = self.repo()
        self.plan(repo, "plan.md")
        self.write(self.sdd(repo) / ".gitignore", "custom\n")
        self.ws(repo, "plan.md")
        self.assertEqual((self.sdd(repo) / ".gitignore").read_text(), "custom\n")

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_gitignore_symlink_is_never_written_through(self):
        repo = self.repo()
        self.plan(repo, "plan.md")
        target = self.tmp / "outside-gitignore"
        self.sdd(repo).mkdir(parents=True)
        link = self.sdd(repo) / ".gitignore"
        link.symlink_to(target)
        self.assertEqual(self.ws(repo, "plan.md"), self.sdd(repo) / "plan")
        self.assertFalse(target.exists())
        self.assertTrue(link.is_symlink())

    def test_repository_stays_clean(self):
        repo = self.repo()
        self.commit(repo, {"docs/plan.md": "x\n"}, "plan")
        self.ws(repo, "docs/plan.md")
        self.assertEqual(self.git(repo, "status", "--ignored", "--short"), "")

    def test_missing_runs_dir_prints_usage_and_exits_2(self):
        repo = self.repo()
        self.write(repo / "plan.md", "# p\n")
        r = self.run_script("sdd-workspace", ["plan.md"], cwd=repo, runs=False)
        self.assertEqual((r.code, r.out, r.err), (2, "", USAGE_WORKSPACE))

    def test_relative_runs_dir_exits_2_and_creates_nothing(self):
        repo = self.repo()
        self.write(repo / "plan.md", "# p\n")
        r = self.run_script("sdd-workspace", ["--runs-dir", "rel", "plan.md"], cwd=repo, runs=False)
        self.assertEqual((r.code, r.out, r.err), (2, "", "sdd-workspace: --runs-dir must be an absolute path: rel\n"))
        self.assertFalse((repo / "rel").exists())

    def test_works_in_a_repository_without_commit(self):
        repo = self.repo(commit=False)
        self.plan(repo, "plan.md")
        r = self.run_script("sdd-workspace", ["plan.md"], cwd=repo)
        self.assertEqual((r.code, r.out, r.err), (0, f"{self.sdd(repo) / 'plan'}\n", ""))

    def test_runs_dir_and_missing_parents_are_created(self):
        repo = self.repo()
        self.plan(repo, "plan.md")
        deep = self.tmp / "a" / "b"
        r = self.run_script("sdd-workspace", ["--runs-dir", deep, "plan.md"], cwd=repo, runs=False)
        self.assertEqual((r.code, r.out, r.err), (0, f"{deep / 'plan'}\n", ""))
        self.assertTrue((deep / "plan").is_dir())

    def test_runs_dir_that_is_a_regular_file_exits_1(self):
        repo = self.repo()
        self.plan(repo, "plan.md")
        self.write(self.runs, "x\n")
        r = self.run_script("sdd-workspace", ["plan.md"], cwd=repo, timeout=10)
        self.assertEqual((r.code, r.out, r.err), (1, "", f"sdd-workspace: cannot create {self.runs}\n"))

    @unittest.skipIf(IS_ROOT, "root ignores directory modes")
    def test_read_only_sdd_directory_exits_1_with_or_without_gitignore(self):
        for i, gitignore in enumerate((False, True)):
            with self.subTest(gitignore=gitignore):
                self.runs = self.tmp / f"runs-{i}"
                repo = self.repo(f"ro-{gitignore}")
                self.plan(repo, "plan.md")
                sdd = self.sdd(repo)
                sdd.mkdir(parents=True)
                if gitignore:
                    self.write(sdd / ".gitignore", "*\n")
                sdd.chmod(0o555)
                self.addCleanup(sdd.chmod, 0o755)
                r = self.run_script("sdd-workspace", ["plan.md"], cwd=repo, timeout=10)
                self.assertEqual((r.code, r.out), (1, ""))
                self.assertTrue(r.err.endswith(f"sdd-workspace: cannot create {sdd / 'plan'}\n"), r.err)
                self.assertIn("Permission denied", r.err)

    def test_candidate_that_is_a_regular_file_falls_through_to_the_next(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        self.write(self.sdd(repo) / "plan", "not a dir\n")
        r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, timeout=10)
        self.assertEqual((r.code, r.out), (0, f"{self.sdd(repo) / 'plan-alpha'}\n"))
        self.assertEqual(r.err, "")

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_candidate_that_is_a_dangling_symlink_falls_through_to_the_next(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        self.sdd(repo).mkdir(parents=True)
        (self.sdd(repo) / "plan").symlink_to(self.tmp / "nowhere", target_is_directory=True)
        r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, timeout=10)
        self.assertEqual(r.code, 0, r.err)
        self.assertEqual(r.err, "")

    @unittest.skipIf(IS_ROOT, "root ignores directory modes")
    def test_unwritable_new_candidate_exits_1_and_leaves_no_directory(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        old = os.umask(0o222)
        try:
            r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, timeout=10)
        finally:
            os.umask(old)
        sdd = self.sdd(repo)
        self.assertEqual((r.code, r.out), (1, ""))
        self.assertTrue(r.err.endswith(f"sdd-workspace: cannot write {sdd / 'plan' / 'plan-path'}\n"), r.err)
        self.assertIn("Permission denied", r.err)
        self.assertEqual(sorted(p.name for p in sdd.iterdir()), [])
        r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, timeout=10)
        self.assertEqual((r.code, r.out, r.err), (0, f"{sdd / 'plan'}\n", ""))

    @unittest.skipIf(IS_ROOT, "root ignores directory modes")
    def test_unwritable_existing_candidate_still_falls_through_to_the_next(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        stem = self.sdd(repo) / "plan"
        stem.mkdir(parents=True)
        stem.chmod(0o555)
        self.addCleanup(stem.chmod, 0o755)
        r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, timeout=10)
        self.assertEqual((r.code, r.out, r.err), (0, f"{self.sdd(repo) / 'plan-alpha'}\n", ""))
        self.assertTrue(stem.is_dir())

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_symlinked_marker_is_never_written_or_trusted(self):
        for i, live in enumerate((False, True)):
            with self.subTest(live=live):
                self.runs = self.tmp / f"runs-{i}"
                repo = self.repo(f"link-{live}")
                self.plan(repo, "docs/alpha/plan.md")
                target = self.tmp / f"outside-{live}"
                if live:
                    self.write(target, f"{repo / 'docs/alpha/plan.md'}\n")
                stem = self.sdd(repo) / "plan"
                stem.mkdir(parents=True)
                (stem / "plan-path").symlink_to(target)
                r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, timeout=10)
                self.assertEqual((r.code, r.out, r.err), (0, f"{self.sdd(repo) / 'plan-alpha'}\n", ""))
                self.assertTrue((stem / "plan-path").is_symlink())
                if live:
                    self.assertEqual(target.read_text(), f"{repo / 'docs/alpha/plan.md'}\n")
                else:
                    self.assertFalse(target.exists())

    @unittest.skipIf(IS_ROOT, "root ignores directory modes")
    def test_workspace_stays_put_after_the_stem_directory_becomes_writable(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        stem = self.sdd(repo) / "plan"
        stem.mkdir(parents=True)
        stem.chmod(0o555)
        self.addCleanup(stem.chmod, 0o755)
        r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, timeout=10)
        self.assertEqual((r.code, r.out), (0, f"{self.sdd(repo) / 'plan-alpha'}\n"))
        stem.chmod(0o755)
        self.assertEqual(self.ws(repo, "docs/alpha/plan.md"), self.sdd(repo) / "plan-alpha")
        self.assertFalse((stem / "plan-path").exists())

    @unittest.skipIf(IS_ROOT, "root ignores directory modes")
    def test_glob_characters_in_the_plan_name_are_not_expanded(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/p[1].md")
        stem = self.sdd(repo) / "p[1]"
        stem.mkdir(parents=True)
        stem.chmod(0o555)
        self.addCleanup(stem.chmod, 0o755)
        self.write(self.sdd(repo) / "p1-alpha" / "plan-path", "other.md\n")
        r = self.run_script("sdd-workspace", ["docs/alpha/p[1].md"], cwd=repo, timeout=10)
        self.assertEqual((r.code, r.out), (0, f"{self.sdd(repo) / 'p[1]-alpha'}\n"))
        stem.chmod(0o755)
        self.assertEqual(self.ws(repo, "docs/alpha/p[1].md"), self.sdd(repo) / "p[1]-alpha")

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_symlinked_candidate_directory_is_never_adopted(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        outside = self.tmp / "outside"
        self.write(outside / "plan-path", f"{repo / 'docs/alpha/plan.md'}\n")
        sdd = self.sdd(repo)
        sdd.mkdir(parents=True)
        (sdd / "plan-alpha-2").symlink_to(outside, target_is_directory=True)
        r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, timeout=10)
        self.assertEqual(
            (r.code, r.out, r.err),
            (0, f"{sdd / 'plan'}\n", f"sdd-workspace: skipping {sdd / 'plan-alpha-2'}: it is a symlink\n"),
        )
        self.assertEqual(sorted(p.name for p in outside.iterdir()), ["plan-path"])

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_claim_skips_a_stem_candidate_that_is_a_symlink(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        outside = self.tmp / "outside"
        outside.mkdir()
        self.sdd(repo).mkdir(parents=True)
        (self.sdd(repo) / "plan").symlink_to(outside, target_is_directory=True)
        r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, timeout=10)
        self.assertEqual((r.code, r.out, r.err), (0, f"{self.sdd(repo) / 'plan-alpha'}\n", ""))
        self.assertEqual(list(outside.iterdir()), [])

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_candidate_swapped_for_a_symlink_before_the_write_is_skipped(self):
        found = shutil.which("mkdir")
        if found is None:
            self.skipTest("no mkdir on PATH")
        real = shlex.quote(found)
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        outside = self.tmp / "outside"
        outside.mkdir()
        flag = self.tmp / "swapped"
        stub = self.tmp / "stubbin"
        stub.mkdir()
        self.write(
            stub / "mkdir",
            f'#!/bin/sh\nif [ ! -e {shlex.quote(str(flag))} ] && [ "$1" = -p ]'
            f' && case "$2" in */runs*/plan) true ;; *) false ;; esac; then\n'
            f'  : > {shlex.quote(str(flag))}\n  rmdir -- "$2"\n'
            f'  ln -s {shlex.quote(str(outside))} "$2"\n  exit 0\nfi\nexec {real} "$@"\n',
        )
        (stub / "mkdir").chmod(0o755)
        r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, path_prefix=stub, timeout=10)
        self.assertEqual((r.code, r.out, r.err), (0, f"{self.sdd(repo) / 'plan-alpha'}\n", ""))
        self.assertTrue((self.sdd(repo) / "plan").is_symlink())
        self.assertEqual(list(outside.iterdir()), [])
        self.assertTrue(flag.exists())

    def test_non_numeric_suffix_copy_is_not_resumed(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        self.write(self.sdd(repo) / "plan-alpha-old" / "plan-path", f"{repo / 'docs/alpha/plan.md'}\n")
        self.assertEqual(self.ws(repo, "docs/alpha/plan.md"), self.sdd(repo) / "plan")

    def test_suffixes_the_claim_loop_never_creates_are_not_resumed(self):
        for i, suffix in enumerate(("0", "1", "02")):
            with self.subTest(suffix=suffix):
                self.runs = self.tmp / f"runs-{i}"
                repo = self.repo(f"suffix-{suffix}")
                self.plan(repo, "docs/alpha/plan.md")
                self.write(self.sdd(repo) / f"plan-alpha-{suffix}" / "plan-path", f"{repo / 'docs/alpha/plan.md'}\n")
                self.assertEqual(self.ws(repo, "docs/alpha/plan.md"), self.sdd(repo) / "plan")

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_symlinked_workspace_of_this_plan_is_reported(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        outside = self.tmp / "outside"
        self.write(outside / "plan-path", f"{repo / 'docs/alpha/plan.md'}\n")
        self.sdd(repo).mkdir(parents=True)
        link = self.sdd(repo) / "plan"
        link.symlink_to(outside, target_is_directory=True)
        r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, timeout=10)
        self.assertEqual(
            (r.code, r.out, r.err),
            (0, f"{self.sdd(repo) / 'plan-alpha'}\n", f"sdd-workspace: skipping {link}: it is a symlink\n"),
        )
        self.assertEqual(sorted(p.name for p in outside.iterdir()), ["plan-path"])

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_symlinked_workspace_of_another_plan_is_skipped_silently(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        outside = self.tmp / "outside"
        self.write(outside / "plan-path", f"{repo / 'docs/beta/plan.md'}\n")
        self.sdd(repo).mkdir(parents=True)
        (self.sdd(repo) / "plan").symlink_to(outside, target_is_directory=True)
        r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, timeout=10)
        self.assertEqual((r.code, r.out, r.err), (0, f"{self.sdd(repo) / 'plan-alpha'}\n", ""))
        self.assertEqual(sorted(p.name for p in outside.iterdir()), ["plan-path"])

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_symlinked_workspace_with_a_symlinked_marker_is_skipped_silently(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        real = self.write(self.tmp / "real-marker", f"{repo / 'docs/alpha/plan.md'}\n")
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "plan-path").symlink_to(real)
        self.sdd(repo).mkdir(parents=True)
        (self.sdd(repo) / "plan").symlink_to(outside, target_is_directory=True)
        r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, timeout=10)
        self.assertEqual((r.code, r.out, r.err), (0, f"{self.sdd(repo) / 'plan-alpha'}\n", ""))
        self.assertEqual(real.read_text(), f"{repo / 'docs/alpha/plan.md'}\n")

    @unittest.skipIf(IS_ROOT, "root ignores directory modes")
    def test_candidate_created_by_another_run_is_left_alone_when_the_write_fails(self):
        found = shutil.which("mkdir")
        if found is None:
            self.skipTest("no mkdir on PATH")
        real = shlex.quote(found)
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        stub = self.tmp / "stubbin"
        stub.mkdir()
        raced = self.tmp / "raced"
        self.write(
            stub / "mkdir",
            f'#!/bin/sh\nif [ ! -e {shlex.quote(str(raced))} ] && [ "$1" = -- ]; then\n'
            f'  : > {shlex.quote(str(raced))}\n  {real} -m 555 -- "$2"\n  exit 1\nfi\nexec {real} "$@"\n',
        )
        (stub / "mkdir").chmod(0o755)
        stem = self.sdd(repo) / "plan"
        self.addCleanup(lambda: stem.exists() and stem.chmod(0o755))
        r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, path_prefix=stub, timeout=10)
        self.assertEqual((r.code, r.out, r.err), (0, f"{self.sdd(repo) / 'plan-alpha'}\n", ""))
        self.assertTrue(stem.is_dir())
        self.assertTrue(raced.exists())

    def test_marker_written_by_another_run_is_never_overwritten(self):
        found = shutil.which("mkdir")
        if found is None:
            self.skipTest("no mkdir on PATH")
        real = shlex.quote(found)
        for foreign, expected in ((True, "plan-alpha"), (False, "plan")):
            with self.subTest(foreign=foreign):
                self.runs = self.tmp / f"runs-{expected}"
                repo = self.repo(f"race-{expected}")
                other = "/other/plan.md\n" if foreign else f"{repo / 'docs/alpha/plan.md'}\n"
                self.plan(repo, "docs/alpha/plan.md")
                stub = self.tmp / f"stub-{expected}"
                stub.mkdir()
                flag = self.tmp / f"flag-{expected}"
                self.write(
                    stub / "mkdir",
                    f'#!/bin/sh\nif [ ! -e {shlex.quote(str(flag))} ] && [ "$1" = -p ]'
                    f' && case "$2" in */runs*/plan) true ;; *) false ;; esac; then\n'
                    f'  : > {shlex.quote(str(flag))}\n  {real} -p -- "$2"\n'
                    f'  printf %s {shlex.quote(other)} > "$2/plan-path"\n  exit 0\nfi\nexec {real} "$@"\n',
                )
                (stub / "mkdir").chmod(0o755)
                r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, path_prefix=stub, timeout=10)
                self.assertEqual((r.code, r.out, r.err), (0, f"{self.sdd(repo) / expected}\n", ""))
                self.assertEqual((self.sdd(repo) / "plan" / "plan-path").read_text(), other)
                self.assertTrue(flag.exists())

    @unittest.skipIf(IS_ROOT, "root ignores directory modes")
    def test_marker_is_written_under_umask_0222_in_an_existing_candidate(self):
        repo = self.repo()
        self.plan(repo, "docs/alpha/plan.md")
        (self.sdd(repo) / "plan").mkdir(parents=True)
        old = os.umask(0o222)
        try:
            r = self.run_script("sdd-workspace", ["docs/alpha/plan.md"], cwd=repo, timeout=10)
        finally:
            os.umask(old)
        self.assertEqual((r.code, r.out, r.err), (0, f"{self.sdd(repo) / 'plan'}\n", ""))
        self.assertEqual((self.sdd(repo) / "plan" / "plan-path").read_text(), f"{repo / 'docs/alpha/plan.md'}\n")


class TaskBriefTests(Case):
    def plan(self, text=PLAN, name="plan.md"):
        return self.write(self.plain / name, text)

    def brief(self, task, text=PLAN, name="plan.md"):
        plan = self.plan(text, name)
        out = self.plain / "out.md"
        if out.exists():
            out.unlink()
        r = self.run_script("task-brief", [plan, task, out], cwd=self.plain)
        return plan, out, r

    def assert_brief(self, task, expected, text=PLAN):
        plan, out, r = self.brief(task, text)
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertEqual(out.read_bytes(), expected.encode())
        self.assertEqual(r.out, f"wrote {out}: {expected.count(chr(10))} lines\n")

    def assert_not_found(self, task, text, plan_name="plan.md"):
        plan, out, r = self.brief(task, text, plan_name)
        self.assertEqual(r.code, 3, r.err)
        self.assertEqual(r.out, "")
        self.assertTrue(
            r.err.endswith(f"task {task} not found in {plan} (no heading matching 'Task {task}')\n"),
            r.err,
        )
        self.assertFalse(out.exists())
        return r

    def test_missing_task_removes_the_default_workspace_brief(self):
        repo = self.repo()
        self.write(repo / "plan.md", PLAN)
        r = self.run_script("task-brief", ["plan.md", "9"], cwd=repo)
        self.assertEqual(r.code, 3, r.err)
        self.assertFalse((self.sdd(repo) / "plan" / "task-9-brief.md").exists())

    def test_missing_task_with_a_dash_outfile_exits_3_and_removes_it(self):
        plan = self.plan()
        r = self.run_script("task-brief", [plan, "9", "-out.md"], cwd=self.plain)
        self.assertEqual(r.code, 3, r.err)
        self.assertNotIn("rm:", r.err)
        self.assertFalse((self.plain / "-out.md").exists())

    def run_to_file(self, args):
        stdout = self.plain / "stdout.txt"
        with open(stdout, "w") as fh:
            proc = subprocess.run(
                [self.bash, str(SCRIPTS / "task-brief"), *args],
                cwd=self.plain, env=dict(self.env, PWD=str(self.plain)),
                stdout=fh, stderr=subprocess.PIPE, text=True,
            )
        return proc

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_missing_task_with_a_symlink_outfile_keeps_the_link(self):
        plan = self.plan()
        link = self.plain / "link.md"
        target = self.plain / "target.md"
        target.write_text("keep")
        link.symlink_to(target)
        r = self.run_script("task-brief", [plan, "9", str(link)], cwd=self.plain)
        self.assertEqual(r.code, 3, r.err)
        self.assertNotIn("rm:", r.err)
        self.assertTrue(link.is_symlink())

    def test_missing_task_with_dev_fd_outfile_exits_3_without_rm(self):
        proc = self.run_to_file([self.plan(), "9", "/dev/fd/1"])
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertNotIn("rm:", proc.stderr)

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_unclosed_fence_with_a_symlink_outfile_keeps_the_link(self):
        plan = self.plain / "fence.md"
        plan.write_text("### Task 3: three\nbody\n```\n### Task 99: hidden\n")
        link = self.plain / "link.md"
        target = self.plain / "target.md"
        target.write_text("keep")
        link.symlink_to(target)
        r = self.run_script("task-brief", [plan, "3", str(link)], cwd=self.plain)
        self.assertEqual(r.code, 4, r.err)
        self.assertTrue(link.is_symlink())

    def test_unclosed_fence_with_dev_fd_outfile_exits_4_without_rm(self):
        plan = self.plain / "fence.md"
        plan.write_text("### Task 3: three\nbody\n```\n### Task 99: hidden\n")
        proc = self.run_to_file([str(plan), "3", "/dev/fd/1"])
        self.assertEqual(proc.returncode, 4, proc.stderr)
        self.assertNotIn("rm:", proc.stderr)

    def test_wrong_argument_count_prints_usage_and_exits_2(self):
        plan = self.plan()
        cases = [[], [plan], [plan, "1", "out.md", "extra"]]
        for args in cases:
            with self.subTest(args=args):
                r = self.run_script("task-brief", args, cwd=self.plain)
                self.assertEqual((r.code, r.out, r.err), (2, "", USAGE_BRIEF))

    def test_bad_c_directory_exits_2(self):
        a_file = self.write(self.tmp / "afile", "x")
        for given in ("/no/such/dir", "", str(a_file)):
            with self.subTest(given=given):
                r = self.run_script("task-brief", ["-C", given, "plan.md", "1"])
                self.assertEqual((r.code, r.out, r.err), (2, "", f"bad -C directory: {given}\n"))

    def test_c_without_value_is_a_bad_directory(self):
        r = self.run_script("task-brief", ["-C"], runs=False)
        self.assertEqual((r.code, r.out, r.err), (2, "", "bad -C directory: \n"))

    def test_missing_plan_file_exits_2_before_any_repository_lookup(self):
        r = self.run_script("task-brief", ["nope.md", "1"], cwd=self.plain)
        self.assertEqual((r.code, r.out, r.err), (2, "", "no such plan file: nope.md\n"))

    def test_extracts_task_3(self):
        self.assert_brief("3", "### Task 3: three\nthree body\n\n")

    def test_extracts_task_6b_without_task_6(self):
        self.assert_brief("6b", "### Task 6b: six b\nsix b body\n\n")

    def test_extracts_task_a1_to_end_of_file(self):
        self.assert_brief("A1", "## Task A1 - alpha\nalpha body\n")

    def test_extracts_dotted_task_2_1(self):
        self.assert_brief("2.1", "#### Task 2.1: sub\nsub body\n\n")

    def test_extracts_task_6_without_task_6b(self):
        self.assert_brief("6", "### Task 6: six\nsix body\n\n")

    def test_task_2_keeps_its_deeper_sub_task_2_1(self):
        self.assert_brief(
            "2", "### Task 2: two\ntwo body\n\n#### Task 2.1: sub\nsub body\n\n"
        )

    def test_plan_with_no_matching_task_exits_3(self):
        r = self.assert_not_found("9", PLAN)
        self.assertEqual(r.err.count("\n"), 1)

    def test_task_id_is_matched_as_a_whole_case_sensitive_string(self):
        cases = [
            ("6", "### Task 6b: x\nbody\n"),
            ("1", "### Task 1.1: x\nbody\n"),
            ("a1", "### Task A1: x\nbody\n"),
            ("6.", "### Task 6: x\nbody\n"),
            ("6.", "### Task 6b: x\nbody\n"),
        ]
        for task, text in cases:
            with self.subTest(task=task, text=text):
                self.assert_not_found(task, text)

    def test_task_id_is_the_leading_alphanumeric_dotted_token(self):
        self.assert_brief("1", "### Task 1:x\nbody\n", "### Task 1:x\nbody\n")
        self.assert_brief("P1", "### Task P1: p\nbody\n", "### Task P1: p\nbody\n")

    def test_headings_without_a_digit_in_the_id_are_not_task_boundaries(self):
        text = "### Task 3: three\n#### Task notes\n#### Task\nlast\n"
        self.assert_brief("3", text, text)

    def test_shallower_or_same_level_heading_ends_the_capture(self):
        cases = [
            ("3", "### Task 3: three\nbody\n## Notes\nnotes\n"),
            ("3", "### Task 3: three\nbody\n### Verification\nv\n"),
            ("3", "### Task 3: three\nbody\n### Task Overview\nv\n"),
            ("A1", "## Task A1 - alpha\nbody\n## Notes\nnotes\n"),
        ]
        for task, text in cases:
            first = text.split("\n")[0]
            with self.subTest(text=text):
                self.assert_brief(task, first + "\nbody\n", text)

    def test_deeper_non_task_heading_stays_in_the_brief(self):
        text = "### Task 3: three\nbody\n#### Notes\nnotes\n"
        self.assert_brief("3", text, text)

    def test_hash_lines_inside_a_fence_do_not_end_the_capture(self):
        text = "### Task 3: three\n```bash\n# comment\n## also\n```\nafter\n"
        self.assert_brief("3", text, text)

    def test_a_later_same_id_task_after_a_section_still_concatenates(self):
        text = "### Task 3: a\nx\n## Notes\nn\n### Task 3: b\ny\n"
        self.assert_brief("3", "### Task 3: a\nx\n### Task 3: b\ny\n", text)

    def test_hash_lines_inside_a_nested_fence_do_not_end_the_capture(self):
        text = "### Task 3: t\n````markdown\n```bash\n# comment\n```\n````\nafter\n"
        self.assert_brief("3", text, text)

    def test_task_heading_inside_a_nested_fence_is_not_a_task(self):
        text = "### Task 3: t\n````md\n```\n### Task 4: hidden\n```\n````\nafter\n"
        self.assert_brief("3", text, text)
        self.assert_not_found("4", text)

    def test_heading_grammar_is_case_sensitive_and_needs_whitespace_after_hashes(self):
        text = "### Task 3: three\n#Task 7\nlast\n"
        self.assert_brief("3", text, text)
        self.assert_not_found("7", "#Task 7\nbody\n")
        self.assert_not_found("4", "### task 4\nbody\n")

    def test_tab_separators_in_the_heading_are_accepted(self):
        text = "###\tTask\t5: tab\nbody\n"
        self.assert_brief("5", text, text)

    def test_deeper_heading_extending_the_id_stays_in_the_brief(self):
        text = (
            "### Task 3: three\nbody\n#### Task 3a: a\na\n#### Task 3.2: b\nb\n"
            "### Task 4: four\nfour\n"
        )
        self.assert_brief("3", text.split("### Task 4")[0], text)

    def test_other_task_headings_end_the_capture(self):
        cases = [
            "### Task 3: three\nbody\n### Task 3a: same level\nz\n",
            "### Task 3: three\nbody\n#### Task 4x: deeper unrelated\nz\n",
            "### Task 1: one\nbody\n### Task 1.1: same level\nz\n",
            "### Task 3: three\nbody\n#### Task 31: digit continuation\nz\n",
        ]
        for text in cases:
            first = text.split("\n")[0]
            task = first.split()[2].rstrip(":")
            with self.subTest(text=text):
                self.assert_brief(task, first + "\nbody\n", text)

    def test_fence_lines_and_fenced_text_stay_in_the_brief(self):
        text = (
            "### Task 3: three\ntext\n```python\n### Task 99: fenced\n```\nmore\n"
            "### Task 4: four\n"
        )
        self.assert_brief("3", text.split("### Task 4")[0], text)

    def test_task_heading_inside_a_fence_is_not_a_task(self):
        text = "### Task 3: three\n```\n### Task 99: fenced\n```\n### Task 4: four\nx\n"
        self.assert_not_found("99", text)

    def test_tilde_fence_does_not_hide_task_headings(self):
        text = "### Task 3: three\n~~~\n### Task 4: four\n~~~\n"
        self.assert_brief("3", "### Task 3: three\n~~~\n", text)

    def test_indented_backticks_do_not_toggle_a_fence(self):
        text = "### Task 3: three\n  ```\n### Task 4: four\n"
        self.assert_brief("3", "### Task 3: three\n  ```\n", text)

    def test_brief_keeps_lines_verbatim_including_trailing_spaces_and_blank_lines(self):
        text = "## Task 3: x  \nline\t \n\n\n"
        self.assert_brief("3", text, text)

    def test_last_line_without_newline_gets_one_appended(self):
        self.assert_brief("3", "### Task 3: x\nlast\n", "### Task 3: x\nlast")

    def test_unclosed_fence_hiding_a_task_heading_during_capture_exits_4(self):
        plan, out, r = self.brief("3", "### Task 3: three\nbody\n```\n### Task 99: hidden\n")
        self.assertEqual(r.code, 4)
        self.assertEqual(r.out, "")
        self.assertEqual(
            r.err,
            f"task-brief: the code fence opened at line 3 of {plan} never closes, so no Task "
            "heading after it can be seen; close that fence in the plan and rerun\n",
        )
        self.assertFalse(out.exists())

    def test_unclosed_fence_hiding_the_requested_heading_reports_it_then_not_found(self):
        plan, out, r = self.brief("99", "## Intro\n```\n### Task 99: hidden\n")
        self.assertEqual((r.code, r.out), (3, ""))
        self.assertEqual(
            r.err,
            f"task-brief: the code fence opened at line 2 of {plan} never closes, so no Task "
            "heading after it can be seen; close that fence in the plan and rerun\n"
            f"task 99 not found in {plan} (no heading matching 'Task 99')\n",
        )

    def test_unclosed_fence_after_the_task_ended_is_silent(self):
        plan, out, r = self.brief(
            "3", "### Task 3: three\nbody\n### Task 4: four\n```\n### Task 99: x\n"
        )
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertEqual(out.read_text(), "### Task 3: three\nbody\n")
        self.assertEqual(r.out, f"wrote {out}: 2 lines\n")

    def test_stray_trailing_fence_after_a_closed_one_that_hid_a_heading_only_warns(self):
        text = "### Task 3: three\nbody\n```\n### Task 99: x\n```\ntail\n```\n"
        plan, out, r = self.brief("3", text)
        self.assertEqual(r.code, 0)
        self.assertEqual(
            r.err,
            f"task-brief: warning: the code fence opened at line 7 of {plan} never closes; "
            "it hides no Task heading, so this brief is complete\n",
        )
        self.assertEqual(out.read_text(), text)

    def test_plan_path_in_messages_is_verbatim_including_backslashes(self):
        plan, out, r = self.brief("3", "### Task 3: three\nbody\n```\nplain\n", "pl\\tan.md")
        self.assertEqual(r.code, 0)
        self.assertIn(f"line 3 of {plan} never closes", r.err)

    def test_hint_is_omitted_when_an_unclosed_fence_hid_a_heading(self):
        plan, out, r = self.brief("1", "## Tarea 1: a\n```\n### Task 99: hidden\n")
        self.assertEqual((r.code, r.out), (3, ""))
        self.assertEqual(
            r.err,
            f"task-brief: the code fence opened at line 2 of {plan} never closes, so no Task "
            "heading after it can be seen; close that fence in the plan and rerun\n"
            f"task 1 not found in {plan} (no heading matching 'Task 1')\n",
        )

    def test_unclosed_fence_hiding_nothing_warns_and_keeps_the_brief(self):
        plan, out, r = self.brief("3", "### Task 3: three\nbody\n```\nplain\n")
        self.assertEqual(r.code, 0)
        self.assertEqual(
            r.err,
            f"task-brief: warning: the code fence opened at line 3 of {plan} never closes; "
            "it hides no Task heading, so this brief is complete\n",
        )
        self.assertEqual(out.read_text(), "### Task 3: three\nbody\n```\nplain\n")
        self.assertEqual(r.out, f"wrote {out}: 4 lines\n")

    def test_plan_without_task_headings_lists_up_to_five_task_shaped_headings(self):
        text = (
            "## A B 4\n## Tarea 1: a\n### Paso 2\n## Step 3.1x\n#### Tarea 5\n"
            "## Tarea 6\n## Tarea 7\n"
        )
        plan, out, r = self.brief("1", text)
        self.assertEqual((r.code, r.out), (3, ""))
        self.assertEqual(
            r.err,
            'task-brief: no task headings found. Task headings must use the English word '
            '"Task" ("### Task 1: ..."), even when the rest of the plan is in another '
            "language. Headings shaped like tasks:\n"
            "  ## Tarea 1: a\n  ### Paso 2\n  ## Step 3.1x\n  #### Tarea 5\n  ## Tarea 6\n"
            f"task 1 not found in {plan} (no heading matching 'Task 1')\n",
        )

    def test_hint_is_omitted_when_a_task_heading_exists(self):
        r = self.assert_not_found("9", "### Task 1: x\n## Tarea 2\n")
        self.assertEqual(r.err.count("\n"), 1)

    def test_hint_is_omitted_when_no_heading_is_task_shaped(self):
        r = self.assert_not_found("1", "## Overview\nfoo\n")
        self.assertEqual(r.err.count("\n"), 1)

    def test_outfile_given_works_outside_a_repository_and_creates_no_workspace(self):
        plan, out, r = self.brief("3")
        self.assertEqual(r.code, 0)
        self.assertEqual(self.tree(self.plain), ["out.md", "plan.md"])

    def test_relative_outfile_resolves_against_the_c_directory(self):
        repo = self.repo()
        self.write(repo / "plan.md", PLAN)
        r = self.run_script("task-brief", ["-C", repo, "plan.md", "3", "brief.md"], cwd=self.plain)
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertEqual(r.out, "wrote brief.md: 3 lines\n")
        self.assertEqual((repo / "brief.md").read_text(), "### Task 3: three\nthree body\n\n")

    def test_default_outfile_is_task_brief_in_the_plan_workspace(self):
        repo = self.repo()
        self.write(repo / "docs" / "plan.md", PLAN)
        r = self.run_script("task-brief", ["-C", repo, "docs/plan.md", "6b"], cwd=self.plain)
        out = self.sdd(repo) / "plan" / "task-6b-brief.md"
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertEqual(r.out, f"wrote {out}: 3 lines\n")
        self.assertEqual(out.read_text(), "### Task 6b: six b\nsix b body\n\n")
        self.assertEqual((out.parent / "plan-path").read_bytes(), f"{repo / 'docs/plan.md'}\n".encode())

    def test_default_outfile_without_runs_dir_exits_2(self):
        repo = self.repo()
        self.write(repo / "plan.md", PLAN)
        r = self.run_script("task-brief", ["plan.md", "3"], cwd=repo, runs=False)
        self.assertEqual((r.code, r.out, r.err), (2, "", "task-brief: --runs-dir DIR is required without OUTFILE\n"))

    def test_outfile_without_runs_dir_works_outside_a_repository(self):
        plan = self.plan()
        out = self.plain / "brief.md"
        r = self.run_script("task-brief", [plan, "3", out], cwd=self.plain, runs=False)
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertTrue(out.is_file())
        self.assertFalse(self.runs.exists())

    def test_default_outfile_works_in_a_repository_without_commit(self):
        repo = self.repo(commit=False)
        self.write(repo / "plan.md", PLAN)
        r = self.run_script("task-brief", ["plan.md", "3"], cwd=repo)
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertTrue((self.sdd(repo) / "plan" / "task-3-brief.md").is_file())

    def test_default_outfile_outside_a_repository_exits_2_with_shared_message(self):
        self.plan()
        r = self.run_script("task-brief", ["plan.md", "3"], cwd=self.plain)
        self.assert_sdd_failure(r, self.plain, said="git said: fatal:")

    def test_relative_script_path_with_c_resolves_the_workspace_script(self):
        repo = self.repo()
        self.write(repo / "plan.md", PLAN)
        r = self.run_script("task-brief", ["-C", repo, "plan.md", "3"], relative=True)
        out = self.sdd(repo) / "plan" / "task-3-brief.md"
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertEqual(r.out, f"wrote {out}: 3 lines\n")

    def test_outfile_in_a_missing_parent_directory_exits_1(self):
        plan = self.plan()
        out = self.plain / "missing" / "brief.md"
        r = self.run_script("task-brief", [plan, "3", out], cwd=self.plain)
        self.assertEqual((r.code, r.out), (1, ""))
        self.assertIn("No such file or directory", r.err)
        self.assertFalse(out.exists())


class ReviewPackageTests(Case):
    def history(self):
        repo = self.repo()
        self.write(repo / "docs" / "plan.md", "plan\n")
        lines = "".join(f"line {i}\n" for i in range(1, 31))
        base = self.commit(repo, {"a.txt": lines}, "add a")
        changed = lines.replace("line 15\n", "line fifteen\n")
        mid = self.commit(repo, {"a.txt": changed}, "change a")
        head = self.commit(repo, {"b.txt": "b\n"}, "add b")
        return repo, base, mid, head

    def package(self, repo, base, head, *extra, plan="docs/plan.md", flags=(), cwd=None):
        return self.run_script(
            "review-package", [*flags, plan, base, head, *extra], cwd=cwd or repo
        )

    def test_wrong_argument_count_prints_usage_and_exits_2(self):
        repo, base, mid, head = self.history()
        for args in ([], ["docs/plan.md", base], ["docs/plan.md", base, head, "o", "extra"]):
            with self.subTest(args=args):
                r = self.run_script("review-package", args, cwd=repo)
                self.assertEqual((r.code, r.out, r.err), (2, "", USAGE_REVIEW))

    def test_bad_c_directory_exits_2(self):
        a_file = self.write(self.tmp / "afile", "x")
        for given in ("/no/such/dir", "", str(a_file)):
            with self.subTest(given=given):
                r = self.run_script("review-package", ["-C", given, "p.md", "a", "b"])
                self.assertEqual((r.code, r.out, r.err), (2, "", f"bad -C directory: {given}\n"))

    def test_c_without_value_is_a_bad_directory(self):
        r = self.run_script("review-package", ["-C"], runs=False)
        self.assertEqual((r.code, r.out, r.err), (2, "", "bad -C directory: \n"))

    def test_missing_plan_file_exits_2_before_any_repository_lookup(self):
        r = self.run_script("review-package", ["nope.md", "a", "b"], cwd=self.plain)
        self.assertEqual((r.code, r.out, r.err), (2, "", "no such plan file: nope.md\n"))

    def test_outside_a_repository_exits_2_with_shared_message(self):
        self.write(self.plain / "plan.md", "x")
        r = self.run_script("review-package", ["plan.md", "a", "b"], cwd=self.plain)
        self.assert_sdd_failure(r, self.plain, said="git said: fatal:")

    def test_repository_without_commit_exits_2_even_with_an_outfile(self):
        repo = self.repo(commit=False)
        self.write(repo / "plan.md", "x")
        for extra in ([], [repo / "out.diff"]):
            with self.subTest(extra=extra):
                r = self.run_script("review-package", ["plan.md", "a", "b", *extra], cwd=repo)
                lines = self.assert_sdd_failure(r, repo, exact=True, said="git said: fatal:")
                self.assertIn("Needed a single revision", lines[1])

    def test_unknown_base_exits_2(self):
        repo, base, mid, head = self.history()
        r = self.package(repo, "nope", head)
        self.assertEqual((r.code, r.out, r.err), (2, "", "bad BASE: nope\n"))
        self.assertFalse((repo / ".tl-relay").exists())

    def test_unknown_head_exits_2(self):
        repo, base, mid, head = self.history()
        r = self.package(repo, base, "nope")
        self.assertEqual((r.code, r.out, r.err), (2, "", "bad HEAD: nope\n"))
        self.assertFalse((repo / ".tl-relay").exists())

    def test_bad_base_is_reported_before_bad_head(self):
        repo, base, mid, head = self.history()
        r = self.package(repo, "nope1", "nope2")
        self.assertEqual(r.err, "bad BASE: nope1\n")

    def test_head_that_does_not_descend_from_base_exits_3(self):
        repo, base, mid, head = self.history()
        self.git(repo, "checkout", "-q", "-b", "side", base)
        side = self.commit(repo, {"s.txt": "s\n"}, "side")
        r = self.package(repo, head, side)
        self.assertEqual((r.code, r.out), (3, ""))
        self.assertEqual(r.err, f"HEAD is not a descendant of BASE: {head}..{side}\n")
        self.assertFalse((repo / ".tl-relay").exists())

    def test_empty_range_exits_3(self):
        repo, base, mid, head = self.history()
        r = self.package(repo, head, head)
        self.assertEqual((r.code, r.out), (3, ""))
        self.assertEqual(r.err, f"empty commit range: {head}..{head}\n")
        self.assertFalse((repo / ".tl-relay").exists())

    def test_plan_content_is_never_read(self):
        repo, base, mid, head = self.history()
        if IS_ROOT:
            self.skipTest("root reads files regardless of mode")
        plan = repo / "docs" / "plan.md"
        plan.chmod(0)
        r = self.package(repo, base, head, "given.diff")
        self.assertEqual((r.code, r.err), (0, ""))
        r = self.package(repo, base, head)
        self.assertEqual((r.code, r.err), (0, ""))

    def test_relative_script_path_with_c_resolves_the_workspace_script(self):
        repo, base, mid, head = self.history()
        short_base = self.git(repo, "rev-parse", "--short", base)
        short_head = self.git(repo, "rev-parse", "--short", head)
        r = self.run_script(
            "review-package", ["-C", repo, "docs/plan.md", base, head], relative=True
        )
        out = self.sdd(repo) / "plan" / f"review-{short_base}..{short_head}.diff"
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertTrue(r.out.startswith(f"wrote {out}: 2 commit(s), "))

    def test_ancestry_is_checked_before_emptiness(self):
        repo, base, mid, head = self.history()
        r = self.package(repo, head, base)
        self.assertEqual(r.code, 3)
        self.assertTrue(r.err.startswith("HEAD is not a descendant of BASE:"))

    def test_default_output_is_named_per_range_in_the_plan_workspace(self):
        repo, base, mid, head = self.history()
        short_base = self.git(repo, "rev-parse", "--short", base)
        short_head = self.git(repo, "rev-parse", "--short", head)
        out = self.sdd(repo) / "plan" / f"review-{short_base}..{short_head}.diff"
        r = self.package(repo, base, head)
        self.assertEqual((r.code, r.err), (0, ""))
        size = len(out.read_bytes())
        self.assertEqual(r.out, f"wrote {out}: 2 commit(s), {size} bytes\n")
        self.assertEqual((out.parent / "plan-path").read_bytes(), f"{repo / 'docs/plan.md'}\n".encode())

    def test_default_output_without_runs_dir_exits_2(self):
        repo, base, mid, head = self.history()
        r = self.run_script("review-package", ["docs/plan.md", "HEAD~1", "HEAD"], cwd=repo, runs=False)
        self.assertEqual((r.code, r.out, r.err), (2, "", "review-package: --runs-dir DIR is required without OUTFILE\n"))

    def test_outfile_without_runs_dir_works(self):
        repo, base, mid, head = self.history()
        out = self.tmp / "given.diff"
        r = self.run_script("review-package", ["docs/plan.md", base, head, out], cwd=repo, runs=False)
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertTrue(out.is_file())
        self.assertFalse(self.runs.exists())

    def test_distinct_ranges_get_distinct_default_files(self):
        repo, base, mid, head = self.history()
        self.assertEqual(self.package(repo, base, head).code, 0)
        self.assertEqual(self.package(repo, base, mid).code, 0)
        names = sorted(p.name for p in (self.sdd(repo) / "plan").glob("review-*.diff"))
        self.assertEqual(len(names), 2)

    def test_file_has_exact_headers_and_sections_in_order(self):
        repo, base, mid, head = self.history()
        out = self.tmp / "package.diff"
        r = self.package(repo, base, head, out)
        self.assertEqual((r.code, r.err), (0, ""))
        log = self.git(repo, "log", "--oneline", f"{base}..{head}", raw=True)
        stat_out = self.git(repo, "diff", "--stat", f"{base}..{head}", raw=True)
        diff = self.git(repo, "diff", "-U10", f"{base}..{head}", raw=True)
        expected = (
            f"# Review package: {base}..{head}\n\n## Commits\n{log}\n"
            f"## Files changed\n{stat_out}\n## Diff\n{diff}"
        )
        self.assertEqual(out.read_text(), expected)

    def test_commits_are_listed_newest_first(self):
        repo, base, mid, head = self.history()
        out = self.tmp / "package.diff"
        self.package(repo, base, head, out)
        commits = out.read_text().split("## Commits\n")[1].split("\n\n## Files changed")[0]
        self.assertEqual(
            [line.split(" ", 1)[1] for line in commits.splitlines()], ["add b", "change a"]
        )

    def test_merge_and_merged_in_commits_are_listed(self):
        repo, base, mid, head = self.history()
        self.git(repo, "checkout", "-q", "-b", "side", base)
        self.commit(repo, {"s.txt": "s\n"}, "side")
        self.git(repo, "checkout", "-q", "-")
        self.git(repo, "merge", "-q", "--no-ff", "-m", "merge", "side")
        out = self.tmp / "package.diff"
        r = self.package(repo, base, "HEAD", out)
        self.assertEqual(r.code, 0)
        self.assertTrue(r.out.endswith(": 4 commit(s), " + r.out.rsplit(", ", 1)[1]))
        commits = out.read_text().split("## Commits\n")[1].split("\n\n## Files changed")[0]
        subjects = [line.split(" ", 1)[1] for line in commits.splitlines()]
        self.assertEqual(subjects[0], "merge")
        self.assertEqual(sorted(subjects), ["add b", "change a", "merge", "side"])

    def test_diff_carries_ten_lines_of_context(self):
        repo, base, mid, head = self.history()
        out = self.tmp / "package.diff"
        self.package(repo, base, mid, out)
        diff = out.read_text().split("## Diff\n")[1]
        context = [line for line in diff.splitlines() if line.startswith(" ")]
        self.assertEqual(len(context), 20)
        self.assertIn("@@ -5,21 +5,21 @@", diff)

    def test_diff_is_the_net_change_of_the_range(self):
        repo, base, mid, head = self.history()
        lines = "".join(f"line {i}\n" for i in range(1, 31))
        tip = self.commit(repo, {"a.txt": lines, "c.txt": "c\n"}, "revert a, add c")
        out = self.tmp / "package.diff"
        r = self.package(repo, base, tip, out)
        self.assertEqual(r.code, 0)
        text = out.read_text()
        files = text.split("## Files changed\n")[1].split("\n\n## Diff")[0]
        self.assertNotIn("a.txt", files)
        self.assertIn("b.txt", files)
        self.assertIn("c.txt", files)
        self.assertEqual(text.split("## Commits\n")[1].split("\n\n")[0].count("\n"), 2)

    def test_base_and_head_are_shown_as_given(self):
        repo, base, mid, head = self.history()
        out = self.tmp / "package.diff"
        r = self.package(repo, "HEAD~2", "HEAD", out)
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertTrue(out.read_text().startswith("# Review package: HEAD~2..HEAD\n\n## Commits\n"))
        bad = self.package(repo, "HEAD", "HEAD", out)
        self.assertEqual(bad.err, "empty commit range: HEAD..HEAD\n")
        bad = self.package(repo, "HEAD~9", "HEAD", out)
        self.assertEqual(bad.err, "bad BASE: HEAD~9\n")

    def test_outfile_is_used_as_given_and_creates_no_workspace(self):
        repo, base, mid, head = self.history()
        r = self.package(repo, base, head, "given.diff")
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertTrue(r.out.startswith("wrote given.diff: 2 commit(s), "))
        self.assertTrue((repo / "given.diff").is_file())
        self.assertFalse((repo / ".tl-relay").exists())

    def test_existing_outfile_is_overwritten(self):
        repo, base, mid, head = self.history()
        out = self.write(self.tmp / "package.diff", "stale\n" * 1000)
        self.package(repo, base, head, out)
        self.assertTrue(out.read_text().startswith("# Review package: "))
        self.assertNotIn("stale", out.read_text())

    def test_c_directory_selects_the_repository(self):
        repo, base, mid, head = self.history()
        r = self.package(repo, base, head, "given.diff", flags=["-C", repo], cwd=self.plain)
        self.assertEqual((r.code, r.err), (0, ""))
        self.assertTrue((repo / "given.diff").is_file())

    def test_outfile_in_a_missing_parent_directory_exits_1(self):
        repo, base, mid, head = self.history()
        r = self.package(repo, base, head, self.tmp / "missing" / "o.diff")
        self.assertEqual((r.code, r.out), (1, ""))
        self.assertIn("No such file or directory", r.err)


if __name__ == "__main__":
    unittest.main()
