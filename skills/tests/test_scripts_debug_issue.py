import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILLS = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = SKILLS / "debug-issue" / "find-polluter.sh"


def _can_symlink() -> bool:
    with tempfile.TemporaryDirectory() as d:
        try:
            os.symlink("target", os.path.join(d, "link"))
        except (OSError, NotImplementedError):
            return False
    return True


CAN_SYMLINK = _can_symlink()

STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_LOG"
echo "runner stdout noise"
echo "runner stderr noise" >&2
for p in $STUB_POLLUTERS; do
  if [ "$2" = "$p" ]; then
    if [ "$STUB_KIND" = dir ]; then mkdir -p "$STUB_TARGET"; elif [ "$STUB_KIND" = link ]; then ln -s missing-target "$STUB_TARGET"; else : > "$STUB_TARGET"; fi
  fi
done
exit 3
"""

HEADER = "\U0001F50D Searching for test that creates: {check}\nTest pattern: {pattern}\n\n"
USAGE = "Usage: {s} <file_to_check> <test_pattern>\nExample: {s} 'packages/engine/.git' 'src/**/*.test.ts'\n"
CLEAN = "\n✅ No polluter found - all tests clean!\n"
PREEXISTING = "⚠️  pollution.flag already exists before any test runs. Pick a target that is absent before the run.\n"


class Run:
    def __init__(self, args, files=(), polluters=(), preexisting=False, kind="file", no_npm=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp) / "work"
            root.mkdir()
            bindir = pathlib.Path(tmp) / "bin"
            bindir.mkdir()
            if not no_npm:
                npm = bindir / "npm"
                npm.write_text(STUB)
                npm.chmod(0o755)
            self.log_path = pathlib.Path(tmp) / "npm.log"
            for f in files:
                p = root / f
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("")
            if preexisting:
                if kind == "dir":
                    (root / "pollution.flag").mkdir()
                elif kind == "link":
                    (root / "pollution.flag").symlink_to("missing-target")
                else:
                    (root / "pollution.flag").write_text("")
            before = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
            env = {k: v for k, v in os.environ.items() if k not in ("BASH_ENV", "ENV")}
            env["PATH"] = f"{bindir}:/bin:/usr/bin" if no_npm else f"{bindir}:{env['PATH']}"
            env["STUB_KIND"] = kind
            env["STUB_LOG"] = str(self.log_path)
            env["STUB_POLLUTERS"] = " ".join(polluters)
            env["STUB_TARGET"] = str(root / "pollution.flag")
            self.script = str(SCRIPT)
            proc = subprocess.run(
                ["bash", self.script, *args],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
            )
            self.out = proc.stdout
            self.err = proc.stderr
            self.code = proc.returncode
            self.calls = self.log_path.read_text().splitlines() if self.log_path.exists() else []
            after = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
            self.created = sorted(set(after) - set(before))
            self.removed = sorted(set(before) - set(after))


class FindPolluterTests(unittest.TestCase):
    def test_wrong_argument_count_prints_usage_on_stdout_and_exits_1(self):
        for args in ([], ["pollution.flag"], ["pollution.flag", "a.test.ts", "extra"]):
            with self.subTest(args=args):
                r = Run(args, files=["a.test.ts"])
                self.assertEqual(r.out, USAGE.format(s=r.script))
                self.assertEqual(r.err, "")
                self.assertEqual(r.code, 1)
                self.assertEqual(r.calls, [])

    def test_header_prints_check_and_pattern_as_given_before_stripping(self):
        r = Run(["pollution.flag", "./a.test.ts"], files=["a.test.ts"])
        self.assertTrue(r.out.startswith(HEADER.format(check="pollution.flag", pattern="./a.test.ts")))

    def test_leading_dot_slash_is_stripped_from_pattern(self):
        r = Run(["pollution.flag", "./a.test.ts"], files=["a.test.ts"])
        self.assertIn("Found 1 test files\n", r.out)
        self.assertIn("[1/1] Testing: ./a.test.ts\n", r.out)
        self.assertEqual(r.calls, ["test ./a.test.ts"])

    def test_discovery_matches_nested_and_top_level_files_via_both_alternatives(self):
        r = Run(
            ["pollution.flag", "src/**/*.test.ts"],
            files=["src/top.test.ts", "src/a/deep.test.ts", "src/a/b/deeper.test.ts", "src/skip.js", "other/x.test.ts"],
        )
        self.assertIn("Found 3 test files\n", r.out)
        self.assertEqual(
            r.calls,
            ["test ./src/a/b/deeper.test.ts", "test ./src/a/deep.test.ts", "test ./src/top.test.ts"],
        )

    def test_literal_alternative_matches_files_the_collapsed_form_cannot_reach(self):
        r = Run(["pollution.flag", "src/**/unit/*.test.ts"], files=["src/a/unit/x.test.ts", "src/unit/y.test.ts", "src/a/other/z.test.ts"])
        self.assertIn("Found 2 test files\n", r.out)
        self.assertEqual(r.calls, ["test ./src/a/unit/x.test.ts", "test ./src/unit/y.test.ts"])

    def test_single_star_matches_files_at_every_depth(self):
        r = Run(["pollution.flag", "src/*.test.ts"], files=["src/top.test.ts", "src/deep/nested.test.ts"])
        self.assertIn("Found 2 test files\n", r.out)
        self.assertEqual(r.calls, ["test ./src/deep/nested.test.ts", "test ./src/top.test.ts"])

    def test_file_matched_by_both_alternatives_runs_once(self):
        r = Run(["pollution.flag", "src/**/*.test.ts"], files=["src/a/deep.test.ts"])
        self.assertIn("Found 1 test files\n", r.out)
        self.assertEqual(r.out.count("Testing: ./src/a/deep.test.ts\n"), 1)
        self.assertEqual(r.calls.count("test ./src/a/deep.test.ts"), 1)

    def test_files_run_in_sorted_order(self):
        r = Run(["pollution.flag", "src/**/*.test.ts"], files=["src/z.test.ts", "src/m.test.ts", "src/a.test.ts"])
        self.assertEqual(
            r.calls,
            ["test ./src/a.test.ts", "test ./src/m.test.ts", "test ./src/z.test.ts"],
        )

    def test_clean_run_prints_found_count_progress_lines_and_final_line(self):
        r = Run(["pollution.flag", "src/**/*.test.ts"], files=["src/a.test.ts", "src/b.test.ts"])
        expected = (
            HEADER.format(check="pollution.flag", pattern="src/**/*.test.ts")
            + "Found 2 test files\n\n"
            + "[1/2] Testing: ./src/a.test.ts\n"
            + "[2/2] Testing: ./src/b.test.ts\n"
            + CLEAN
        )
        self.assertEqual(r.out, expected)
        self.assertEqual(r.err, "")
        self.assertEqual(r.code, 0)

    def test_runner_is_called_with_test_and_the_file_argument(self):
        r = Run(["pollution.flag", "a.test.ts"], files=["a.test.ts"])
        self.assertEqual(r.calls, ["test ./a.test.ts"])

    def test_missing_npm_is_swallowed_and_run_continues_to_clean_exit(self):
        if shutil.which("npm", path="/bin:/usr/bin"):
            self.skipTest("npm present in /bin or /usr/bin")
        r = Run(["pollution.flag", "src/*.test.ts"], files=["src/a.test.ts", "src/b.test.ts"], no_npm=True)
        self.assertIn("[2/2] Testing: ./src/b.test.ts\n", r.out)
        self.assertTrue(r.out.endswith(CLEAN))
        self.assertEqual(r.err, "")
        self.assertEqual(r.code, 0)

    def test_runner_output_and_nonzero_exit_are_ignored(self):
        r = Run(["pollution.flag", "a.test.ts"], files=["a.test.ts"])
        self.assertNotIn("runner stdout noise", r.out)
        self.assertNotIn("runner stderr noise", r.out)
        self.assertEqual(r.err, "")
        self.assertEqual(r.code, 0)
        self.assertTrue(r.out.endswith(CLEAN))

    def test_preexisting_target_exits_2_without_running_npm(self):
        for kind in ("file", "dir", "link"):
            with self.subTest(kind=kind):
                if kind == "link" and not CAN_SYMLINK:
                    self.skipTest("cannot create symlinks")
                r = Run(["pollution.flag", "src/*.test.ts"], files=["src/a.test.ts"], preexisting=True, kind=kind)
                self.assertEqual(r.out, HEADER.format(check="pollution.flag", pattern="src/*.test.ts") + PREEXISTING)
                self.assertEqual((r.calls, r.err, r.code), ([], "", 2))

    def test_polluter_found_prints_block_stops_and_exits_1(self):
        r = Run(
            ["pollution.flag", "src/*.test.ts"],
            files=["src/a.test.ts", "src/b.test.ts", "src/c.test.ts"],
            polluters=["./src/b.test.ts"],
        )
        head = (
            HEADER.format(check="pollution.flag", pattern="src/*.test.ts")
            + "Found 3 test files\n\n"
            + "[1/3] Testing: ./src/a.test.ts\n"
            + "[2/3] Testing: ./src/b.test.ts\n"
            + "\n\U0001F3AF FOUND POLLUTER!\n"
            + "   Test: ./src/b.test.ts\n"
            + "   Created: pollution.flag\n"
            + "\n"
            + "Pollution details:\n"
        )
        tail = (
            "\nTo investigate:\n"
            "  npm test ./src/b.test.ts    # Run just this test\n"
            "  cat ./src/b.test.ts         # Review test code\n"
        )
        self.assertTrue(r.out.startswith(head))
        self.assertTrue(r.out.endswith(tail))
        details = r.out[len(head):-len(tail)]
        self.assertTrue(any(re.match(r"^[-d][rwxsStT-]{9}", ln) and ln.endswith("pollution.flag") for ln in details.splitlines()), details)
        self.assertEqual(r.calls, ["test ./src/a.test.ts", "test ./src/b.test.ts"])
        self.assertNotIn("c.test.ts", r.out)
        self.assertEqual(r.err, "")
        self.assertEqual(r.code, 1)

    def test_zero_matches_print_exact_output_and_never_call_npm(self):
        r = Run(["pollution.flag", "nothing/**/*.test.ts"], files=["src/a.test.ts"])
        expected = (
            HEADER.format(check="pollution.flag", pattern="nothing/**/*.test.ts")
            + "Found 0 test files\n\n"
            + CLEAN
        )
        self.assertEqual(r.out, expected)
        self.assertEqual(r.calls, [])
        self.assertEqual(r.err, "")
        self.assertEqual(r.code, 0)

    def test_directory_polluter_is_found_and_stops_at_first(self):
        r = Run(
            ["pollution.flag", "src/*.test.ts"],
            files=["src/a.test.ts", "src/b.test.ts"],
            polluters=["./src/a.test.ts"],
            kind="dir",
        )
        head = (
            HEADER.format(check="pollution.flag", pattern="src/*.test.ts")
            + "Found 2 test files\n\n"
            + "[1/2] Testing: ./src/a.test.ts\n"
            + "\n\U0001F3AF FOUND POLLUTER!\n"
            + "   Test: ./src/a.test.ts\n"
            + "   Created: pollution.flag\n"
            + "\n"
            + "Pollution details:\n"
        )
        tail = (
            "\nTo investigate:\n"
            "  npm test ./src/a.test.ts    # Run just this test\n"
            "  cat ./src/a.test.ts         # Review test code\n"
        )
        self.assertTrue(r.out.startswith(head))
        self.assertTrue(r.out.endswith(tail))
        details = r.out[len(head):-len(tail)]
        self.assertTrue(any(re.match(r"^d[rwxsStT-]{9}", ln) for ln in details.splitlines()), details)
        self.assertEqual(r.calls, ["test ./src/a.test.ts"])
        self.assertEqual(r.err, "")
        self.assertEqual(r.code, 1)

    @unittest.skipUnless(CAN_SYMLINK, "cannot create symlinks")
    def test_dangling_symlink_created_by_a_test_is_found_as_polluter(self):
        r = Run(["pollution.flag", "src/*.test.ts"], files=["src/a.test.ts"], polluters=["./src/a.test.ts"], kind="link")
        self.assertIn("FOUND POLLUTER!", r.out)
        self.assertEqual((r.calls, r.err, r.code), (["test ./src/a.test.ts"], "", 1))

    def test_script_creates_and_removes_no_files(self):
        r = Run(["pollution.flag", "src/**/*.test.ts"], files=["src/a.test.ts", "src/b/c.test.ts"])
        self.assertEqual(r.created, [])
        self.assertEqual(r.removed, [])

    def test_stderr_is_empty_on_polluter_path(self):
        r = Run(["pollution.flag", "a.test.ts"], files=["a.test.ts"], polluters=["./a.test.ts"])
        self.assertEqual(r.err, "")
        self.assertEqual(r.code, 1)
        self.assertEqual(r.created, ["pollution.flag"])


class ImportTests(unittest.TestCase):
    def test_symlink_tests_skip_without_symlink_rights(self):
        here = pathlib.Path(__file__).resolve().parent
        names = [
            "test_scripts_debug_issue.FindPolluterTests.test_dangling_symlink_created_by_a_test_is_found_as_polluter",
            "test_scripts_debug_issue.FindPolluterTests.test_preexisting_target_exits_2_without_running_npm",
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
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        self.assertEqual((proc.returncode, proc.stdout), (0, "2 2 0 0\n"), proc.stderr)


if __name__ == "__main__":
    unittest.main()
