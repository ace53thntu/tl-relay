import json
import os
import pathlib
import signal
import subprocess
import time
import uuid
import tempfile
import unittest
from unittest import mock

import triggers

HERE = pathlib.Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"


def load(name):
    return (FIXTURES / name).read_text().splitlines()


class Parser(unittest.TestCase):
    def test_a_read_before_the_skill_still_grades_on_the_skill(self):
        ok, _ = triggers.grade(load("read-then-skill.jsonl"), "debug-issue")
        self.assertTrue(ok)

    def test_the_bootstrap_skill_is_skipped(self):
        lines = load("bootstrap-then-skill.jsonl")
        self.assertEqual(triggers.first_skill(lines), "debug-issue")
        self.assertTrue(triggers.grade(lines, "debug-issue")[0])

    def test_no_skill_call_fails(self):
        ok, reason = triggers.grade(load("no-skill.jsonl"), "debug-issue")
        self.assertFalse(ok)
        self.assertIn("debug-issue", reason)

    def test_a_no_skill_fail_quotes_the_first_answer(self):
        ok, reason = triggers.grade(load("no-skill.jsonl"), "debug-issue")
        self.assertFalse(ok)
        self.assertEqual(reason, "no Skill call, expected debug-issue; answered: I will just fix it.")

    def test_watch_writes_the_lines_it_saw(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "seen.jsonl")
            lines = [l + "\n" for l in load("no-skill.jsonl")]
            triggers.watch("debug-issue", iter(lines), None, path)
            self.assertEqual(open(path).read(), "".join(lines))

    def test_a_subagent_text_is_not_the_first_answer(self):
        lines = [
            '{"type":"assistant","parent_tool_use_id":"t1","message":{"content":[{"type":"text","text":"sub"}]}}',
            '{"type":"assistant","message":{"content":[{"type":"text","text":"top\\nline"}]}}',
        ]
        self.assertEqual(triggers.first_text(lines), "top line")
        self.assertIsNone(triggers.first_text(lines[:1]))

    def test_a_superpowers_call_fails_even_after_the_right_skill(self):
        lines = load("plugin-after-skill.jsonl")
        self.assertEqual(triggers.plugin_calls(lines), ["superpowers:systematic-debugging"])
        self.assertFalse(triggers.grade(lines, "debug-issue")[0])

    def test_a_wrong_first_skill_fails_with_both_names_in_the_reason(self):
        ok, reason = triggers.grade(load("wrong-skill.jsonl"), "debug-issue")
        self.assertFalse(ok)
        self.assertIn("brainstorm", reason)
        self.assertIn("debug-issue", reason)
    def test_an_error_result_is_an_error(self):
        self.assertEqual(triggers.classify(load("error-result.jsonl"), "debug-issue")[0], "ERROR")

    def test_a_stream_with_no_result_is_an_error(self):
        self.assertEqual(triggers.classify(load("no-result.jsonl"), "debug-issue")[0], "ERROR")

    def test_a_clean_result_with_no_skill_stays_a_fail(self):
        self.assertEqual(triggers.classify(load("no-skill.jsonl"), "debug-issue")[0], "FAIL")

    def test_a_damaged_line_before_a_clean_result_is_an_error(self):
        lines = ["{not json"] + load("no-skill.jsonl")
        self.assertEqual(triggers.classify(lines, "debug-issue")[0], "ERROR")

    def test_grade_skips_a_damaged_line(self):
        ok, reason = triggers.grade(["not json"] + load("wrong-skill.jsonl"), "debug-issue")
        self.assertFalse(ok)
        self.assertIn("brainstorm", reason)

    def test_a_damaged_line_before_the_first_skill_is_an_error(self):
        for fixture in ("read-then-skill.jsonl", "wrong-skill.jsonl", "plugin-after-skill.jsonl"):
            with self.subTest(fixture):
                lines = ["{not json"] + load(fixture)
                self.assertEqual(triggers.classify(lines, "debug-issue")[0], "ERROR")

    def test_watch_stops_at_a_clean_result(self):
        stream = iter(load("no-skill.jsonl") + ["after"])
        self.assertEqual(triggers.watch("debug-issue", stream)[0], "FAIL")
        self.assertEqual(next(stream), "after")

    def test_watch_stops_at_an_error_result(self):
        stream = iter(load("error-result.jsonl") + load("read-then-skill.jsonl"))
        self.assertEqual(triggers.watch("debug-issue", stream)[0], "ERROR")

    def test_a_skill_call_decides_before_an_error_result(self):
        lines = load("read-then-skill.jsonl") + load("error-result.jsonl")
        self.assertEqual(triggers.classify(lines, "debug-issue")[0], "PASS")

    def test_a_subagent_skill_call_is_not_graded(self):
        lines = load("subagent-skill.jsonl")
        self.assertEqual(triggers.first_skill(lines), "debug-issue")


def alive(marker):
    return subprocess.run(["pgrep", "-f", marker], capture_output=True).returncode == 0


class KillPaths(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.marker = "tl-relay-stub-" + uuid.uuid4().hex
        self.addCleanup(lambda: subprocess.run(["pkill", "-9", "-f", self.marker]))
        self.prompts = pathlib.Path(self.root.name) / "prompts"
        self.prompts.mkdir()
        (self.prompts / "only.txt").write_text("expect: debug-issue\nwhy does this fail\n")
        self.tmpdir = pathlib.Path(self.root.name) / "tmp"
        self.tmpdir.mkdir()

    def start(self, mode, timeout=None, pgid_file=None, script=None, stderr=None, bash="bash"):
        extra = {"TL_RELAY_TRIGGER_TIMEOUT": str(timeout)} if timeout else {}
        if pgid_file:
            extra["TL_RELAY_TRIGGER_PGID_FILE"] = str(pgid_file)
        env = dict(
            os.environ,
            TL_RELAY_TRIGGER_AGENT=str(FIXTURES / "stub-agent.sh"),
            TL_RELAY_TRIGGER_PROMPTS=str(self.prompts),
            TL_RELAY_STUB_MODE=mode,
            TL_RELAY_STUB_MARKER=self.marker,
            TMPDIR=str(self.tmpdir),
            **extra,
        )
        return subprocess.Popen(
            [bash, str(script or HERE / "run-triggers.sh")],
            env=env,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            start_new_session=True,
        )

    def assert_clean(self):
        self.assertFalse(alive(self.marker))
        self.assertEqual(list(self.tmpdir.iterdir()), [])

    def test_children_of_the_agent_die_when_the_skill_is_seen(self):
        started = time.time()
        proc = self.start("linger")
        out, _ = proc.communicate(timeout=30)
        self.assertLess(time.time() - started, 15)
        self.assertEqual(out.splitlines(), ["PASS only", "1/1"])
        self.assert_clean()

    def test_an_agent_that_ignores_term_is_killed(self):
        started = time.time()
        proc = self.start("ignore-term")
        out, _ = proc.communicate(timeout=30)
        self.assertLess(time.time() - started, 15)
        self.assertEqual(out.splitlines(), ["PASS only", "1/1"])
        self.assert_clean()

    # macOS bash 3.2 also prints a racy "child setpgid" line; only job notices are ours.
    def test_killing_an_agent_that_ignores_term_prints_no_job_notice(self):
        proc = self.start("ignore-term", stderr=subprocess.PIPE, bash="/bin/bash")
        out, err = proc.communicate(timeout=30)
        self.assertEqual(out.splitlines(), ["PASS only", "1/1"])
        self.assertNotRegex(err, "Terminated|Killed")

    def test_a_timed_out_agent_prints_no_job_notice(self):
        proc = self.start("silent", timeout=2, stderr=subprocess.PIPE, bash="/bin/bash")
        out, err = proc.communicate(timeout=30)
        self.assertEqual(out.splitlines()[-1], "0/1")
        self.assertNotRegex(err, "Terminated|Killed")

    def assert_times_out(self, mode):
        started = time.time()
        proc = self.start(mode, timeout=2)
        out, _ = proc.communicate(timeout=30)
        self.assertLess(time.time() - started, 12)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("ERROR only: timeout after 2s"), lines[0])
        self.assertEqual(lines[-1], "0/1")
        self.assertEqual(proc.returncode, 3)
        self.assert_clean()

    def test_a_lingering_agent_after_a_clean_result_is_a_fail(self):
        started = time.time()
        proc = self.start("clean-linger", timeout=20)
        out, _ = proc.communicate(timeout=40)
        self.assertLess(time.time() - started, 12)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("FAIL only: no Skill call"), lines[0])
        self.assertEqual(lines[-1], "0/1")
        self.assertEqual(proc.returncode, 1)
        self.assert_clean()

    def test_a_clean_result_written_during_timeout_shutdown_is_an_error(self):
        self.assert_times_out("clean-on-term")

    def test_a_silent_agent_that_ignores_term_times_out(self):
        self.assert_times_out("silent-ignore-term")

    def test_a_child_holding_the_pipe_after_the_agent_exits_times_out(self):
        self.assert_times_out("orphan-holds-pipe")

    def test_an_interrupted_run_leaves_no_process_or_temp_dir(self):
        proc = self.start("silent")
        deadline = time.time() + 10
        while not alive(self.marker) and time.time() < deadline:
            time.sleep(0.1)
        self.assertTrue(alive(self.marker))
        proc.send_signal(signal.SIGINT)
        proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 130)
        self.assert_clean()

    def test_the_agent_group_is_written_to_the_pgid_file(self):
        path = pathlib.Path(self.root.name) / "agent.pgid"
        proc = self.start("silent", pgid_file=path)
        self.addCleanup(self.interrupt, proc)
        deadline = time.time() + 10
        while not (path.exists() and path.read_text().strip()) and time.time() < deadline:
            time.sleep(0.05)
        pgid = int(path.read_text())
        self.assertNotEqual(pgid, proc.pid)
        self.assertEqual(os.getpgid(pgid), pgid)
        proc.send_signal(signal.SIGINT)
        proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 130)
        self.assert_clean()

    def test_the_pgid_file_is_empty_after_a_normal_run(self):
        path = pathlib.Path(self.root.name) / "agent.pgid"
        proc = self.start("", pgid_file=path)
        out, _ = proc.communicate(timeout=30)
        self.assertEqual(out.splitlines(), ["PASS only", "1/1"])
        self.assertEqual(path.read_text(), "")

    def test_the_pgid_file_is_empty_after_an_interrupted_run(self):
        path = pathlib.Path(self.root.name) / "agent.pgid"
        proc = self.start("silent", pgid_file=path)
        self.addCleanup(self.interrupt, proc)
        deadline = time.time() + 10
        while not (path.exists() and path.read_text().strip()) and time.time() < deadline:
            time.sleep(0.05)
        self.assertTrue(path.read_text().strip())
        proc.send_signal(signal.SIGINT)
        proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 130)
        self.assertEqual(path.read_text(), "")

    def interrupt(self, proc):
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                subprocess.run(["pkill", "-9", "-f", self.marker])
                proc.kill()
                proc.communicate(timeout=30)

    def test_the_watchdog_runs_before_the_pgid_file_is_written(self):
        path = pathlib.Path(self.root.name) / "agent.pgid"
        os.mkfifo(str(path))
        shadow = pathlib.Path(self.root.name) / "bin"
        shadow.mkdir()
        mark = pathlib.Path(self.root.name) / "dog.started"
        (shadow / "sleep").write_text('#!/bin/bash\n[ "$1" = 77 ] && : >"%s"\n'
                                      'exec -a "$TL_RELAY_STUB_MARKER" /bin/sleep "$@"\n' % mark)
        (shadow / "sleep").chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": "%s:%s" % (shadow, os.environ["PATH"])}):
            proc = self.start("silent", timeout=77, pgid_file=path)
        self.addCleanup(self.interrupt, proc)
        deadline = time.time() + 10
        while not mark.exists() and time.time() < deadline:
            time.sleep(0.05)
        started = mark.exists()
        fd = os.open(str(path), os.O_RDONLY | os.O_NONBLOCK)
        text = b""
        deadline = time.time() + 10
        while not text.endswith(b"\n") and time.time() < deadline:
            try:
                text += os.read(fd, 64)
            except BlockingIOError:
                pass
            time.sleep(0.05)
        os.close(fd)
        path.unlink()
        self.assertTrue(started)
        self.assertTrue(text.endswith(b"\n"), text)
        pgid = int(text)
        self.assertEqual(os.getpgid(pgid), pgid)
        proc.send_signal(signal.SIGINT)
        proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 130)
        self.assertEqual(path.read_text(), "")
        self.assert_clean()

    def patched_runner(self, name, after):
        root = pathlib.Path(self.root.name) / name
        tests = root / "skills" / "tests"
        tests.mkdir(parents=True)
        (tests / "triggers.py").symlink_to(HERE / "triggers.py")
        (tests / "fixtures").symlink_to(FIXTURES)
        (root / "skills" / "alpha").mkdir()
        (root / "skills" / "alpha" / "SKILL.md").write_text("---\nname: alpha\n---\n")
        (root / "hooks").mkdir()
        (root / "hooks" / "session-start-skills.sh").write_text("exit 0\n")
        text = (HERE / "run-triggers.sh").read_text()
        self.assertEqual(text.count(after), 1)
        script = tests / "run-triggers.sh"
        script.write_text(text.replace(after, after + "  kill -INT $$\n"))
        return script

    def test_an_interrupt_before_a_pid_is_recorded_stops_every_job(self):
        forks = {"agent": ') >"$tmp/stream" 2>>"$tmp/err" &\n', "watchdog": '2>/dev/null) &\n'}
        for name, after in forks.items():
            with self.subTest(fork=name):
                script = self.patched_runner(name, after)
                self.addCleanup(subprocess.run, ["pkill", "-9", "-f", str(script)])
                proc = self.start("silent", timeout=40, script=script)
                self.addCleanup(self.interrupt, proc)
                proc.communicate(timeout=30)
                self.assertEqual(proc.returncode, 130)
                left = subprocess.run(["pgrep", "-f", str(script)], stdout=subprocess.PIPE, text=True)
                self.assertEqual(left.returncode, 1, left.stdout)
                self.assert_clean()

    def test_a_child_left_by_an_exited_agent_is_killed(self):
        ready = pathlib.Path(self.root.name) / "child.ready"
        with mock.patch.dict(os.environ, {"TL_RELAY_STUB_READY": str(ready)}):
            proc = self.start("leave-child")
        self.addCleanup(self.interrupt, proc)
        out, _ = proc.communicate(timeout=30)
        self.assertEqual(out.splitlines(), ["PASS only", "1/1"])
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(ready.exists())
        self.assert_clean()

    def test_a_closed_pipe_leaves_no_temp_dir(self):
        (self.prompts / "two.txt").write_text("expect: debug-issue\nwhy does this fail\n")
        proc = self.start("")
        proc.stdout.readline()
        proc.stdout.close()
        proc.wait(timeout=30)
        self.assertFalse(alive(self.marker))
        self.assertEqual(list(self.tmpdir.iterdir()), [])

    def test_an_empty_prompt_dir_fails(self):
        (self.prompts / "only.txt").unlink()
        proc = self.start("")
        out, _ = proc.communicate(timeout=30)
        self.assertEqual(out.splitlines(), ["0/0"])
        self.assertEqual(proc.returncode, 1)


class Workspace(unittest.TestCase):
    def run_dump(self):
        with tempfile.TemporaryDirectory() as tmp:
            dump = pathlib.Path(tmp) / "dump.json"
            result = Runner.run_runner(
                self,
                {"a-dump.txt": "expect: debug-issue\nstub:dump\n"},
                extra_env={"TL_RELAY_STUB_DUMP": str(dump)},
            )
            self.assertIn("PASS a-dump", result.stdout)
            return json.loads(dump.read_text())

    def test_the_agent_runs_pinned_inside_the_fixture_workspace(self):
        dump = self.run_dump()
        self.assertTrue(dump["cwd"].endswith("/ws"))
        self.assertIn("src/orders/order_service.py", dump["files"])
        self.assertNotIn("err", dump["files"])
        self.assertNotIn("verdict", dump["files"])
        i = dump["args"].index("--setting-sources")
        self.assertEqual(dump["args"][i + 1], "project")
        self.assertEqual(dump["args"][dump["args"].index("--model") + 1], "opus")
        skills = sorted(p.parent.name for p in list(HERE.parent.glob("*/SKILL.md"))
                        + list(HERE.parents[1].glob("maintainer/skills/*/SKILL.md")))
        linked = sorted(f.split("/")[-1] for f in dump["files"] if f.startswith(".claude/skills/") and f.count("/") == 2)
        self.assertEqual(linked, skills)
        self.assertIn("hooks/session-start-skills.sh", json.dumps(dump["settings"]))
        self.assertEqual(dump["links"]["write-skill"], str((HERE.parents[1] / "maintainer/skills/write-skill").resolve()))


class Runner(unittest.TestCase):
    def run_runner(self, prompts_by_name, script=None, extra_env=None, with_skill=True):
        with tempfile.TemporaryDirectory() as tmp:
            prompts = pathlib.Path(tmp) / "prompts"
            prompts.mkdir()
            for name, body in prompts_by_name.items():
                (prompts / name).write_text(body)
            env = dict(
                os.environ,
                TL_RELAY_TRIGGER_AGENT=str(FIXTURES / "stub-agent.sh"),
                TL_RELAY_TRIGGER_PROMPTS=str(prompts),
                TMPDIR=tmp,
                **(extra_env or {}),
            )
            runner = HERE / "run-triggers.sh"
            if script is not None:
                tree = pathlib.Path(tmp) / "tree"
                copy = tree / "skills" / "tests"
                copy.mkdir(parents=True)
                (tree / "hooks").mkdir()
                (tree / "hooks" / "session-start-skills.sh").write_text("")
                if with_skill:
                    (tree / "skills" / "alpha").mkdir()
                    (tree / "skills" / "alpha" / "SKILL.md").write_text("")
                (copy / "run-triggers.sh").write_text(runner.read_text())
                (copy / "triggers.py").write_text(script)
                (copy / "fixtures").symlink_to(FIXTURES)
                runner = copy / "run-triggers.sh"
            result = subprocess.run(
                ["bash", str(runner)], env=env, capture_output=True, text=True, timeout=60
            )
            self.leftover = [p.name for p in pathlib.Path(tmp).glob("trigger.*")]
            return result

    def test_a_workspace_that_cannot_be_built_is_an_error_and_leaves_nothing(self):
        script = (HERE / "triggers.py").read_text()
        result = self.run_runner(
            {"a-nobuild.txt": "expect: debug-issue\nwhy does this fail\n"},
            script=script,
            with_skill=False,
        )
        self.assertIn("ERROR a-nobuild: could not build the trigger workspace", result.stdout)
        self.assertEqual(result.stdout.splitlines()[-1], "0/1")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(self.leftover, [])

    def test_a_fail_keeps_its_stream(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep = pathlib.Path(tmp) / "keep" / "x"
            result = self.run_runner(
                {"a-fail.txt": "expect: debug-issue\nstub:clean\n"},
                extra_env={"TL_RELAY_TRIGGER_KEEP": str(keep)},
            )
            files = list(keep.glob("a-fail.*.jsonl"))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_text().splitlines(), load("no-skill.jsonl"))
            self.assertIn("; answered: I will just fix it.", result.stdout)

    def test_a_pass_keeps_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            keep = pathlib.Path(tmp) / "keep"
            self.run_runner(
                {"a-pass.txt": "expect: debug-issue\nwhy does this fail\n"},
                extra_env={"TL_RELAY_TRIGGER_KEEP": str(keep)},
            )
            self.assertEqual(list(keep.glob("*")), [])

    def test_a_keep_failure_warns_and_stays_a_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocker = pathlib.Path(tmp) / "blocker"
            blocker.write_text("")
            result = self.run_runner(
                {"a-fail.txt": "expect: debug-issue\nstub:clean\n"},
                extra_env={"TL_RELAY_TRIGGER_KEEP": str(blocker)},
            )
            lines = result.stdout.splitlines()
            self.assertTrue(any(l.startswith("FAIL a-fail") for l in lines), lines)
            self.assertTrue(any(l.startswith("  keep: ") for l in lines), lines)
            self.assertEqual(result.returncode, 1)

    def test_a_failure_outranks_an_error_in_the_exit_code(self):
        result = self.run_runner({
            "a-error.txt": "expect: debug-issue\nstub:error\n",
            "b-fail.txt": "expect: debug-issue\nstub:wrong\n",
        })
        self.assertIn("ERROR a-error: ", result.stdout)
        self.assertIn("FAIL b-fail: ", result.stdout)
        self.assertEqual(result.returncode, 1)

    def test_only_errors_exit_three(self):
        result = self.run_runner({
            "a-pass.txt": "expect: debug-issue\nwhy does this fail\n",
            "b-error.txt": "expect: debug-issue\nstub:no-result\n",
        })
        self.assertEqual(result.stdout.splitlines()[-1], "1/2")
        self.assertEqual(result.returncode, 3)

    def test_invalid_utf8_in_the_stream_is_not_a_fail(self):
        result = self.run_runner({"a-bytes.txt": "expect: debug-issue\nstub:bad-utf8\n"})
        self.assertIn("ERROR a-bytes: ", result.stdout)
        self.assertEqual(result.returncode, 3)

    def test_a_crashed_watcher_is_an_error(self):
        result = self.run_runner(
            {"a-crash.txt": "expect: debug-issue\nwhy does this fail\n"},
            script="import sys\nsys.exit(1)\n",
        )
        self.assertIn("ERROR a-crash: ", result.stdout)
        self.assertEqual(result.returncode, 3)

    def test_a_marker_created_after_a_clean_result_stays_a_fail(self):
        script = (
            "import glob, os, sys\n"
            "sys.path.insert(0, %r)\n"
            "import triggers\n"
            "code = triggers.main(sys.argv)\n"
            "sys.stdout.flush()\n"
            "run = glob.glob(os.path.join(os.environ['TMPDIR'], 'trigger.*'))[0]\n"
            "open(os.path.join(run, 'timeout'), 'w').close()\n"
            "sys.exit(code)\n"
        ) % str(HERE)
        result = self.run_runner({"a-clean.txt": "expect: debug-issue\nstub:clean\n"}, script=script)
        self.assertTrue(result.stdout.startswith("FAIL a-clean: no Skill call"), result.stdout)
        self.assertEqual(result.returncode, 1)

    def test_agent_and_watcher_stderr_both_survive(self):
        result = self.run_runner(
            {"a-both.txt": "expect: debug-issue\nstub:stderr\n"},
            script="import sys\nsys.stderr.write('watcher-trace\\n')\nsys.stderr.flush()\nsys.stdin.read()\nsys.exit(1)\n",
        )
        self.assertIn("agent-stderr-line", result.stdout)
        self.assertIn("watcher-trace", result.stdout)

    def test_the_runner_grades_each_prompt_and_counts_passes(self):
        result = self.run_runner({
            "a-pass.txt": "expect: debug-issue\nwhy does this fail\n",
            "b-fail.txt": "expect: debug-issue\nstub:wrong\n",
        })
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], "PASS a-pass")
        self.assertTrue(lines[1].startswith("FAIL b-fail: "), lines[1])
        self.assertIn("brainstorm", lines[1])
        self.assertEqual(lines[-1], "1/2")
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
