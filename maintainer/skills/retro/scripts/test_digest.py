import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from digest import main, normalise

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = "2026-11-23T15:00:00Z"
TOKEN = "ghp_" + "a" * 36


def user(uuid, ts, text, session="s1"):
    return {"type": "user", "uuid": uuid, "sessionId": session, "timestamp": ts, "entrypoint": "cli",
            "isSidechain": False, "isMeta": False, "message": {"role": "user", "content": text}}


def assistant(uuid, ts, text="Done."):
    return {"type": "assistant", "uuid": uuid, "sessionId": "s1", "timestamp": ts,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def corrected():
    return [user("u0", "2026-11-23T09:59:58Z", "start the work on the digest"),
            assistant("a0", "2026-11-23T09:59:59Z"),
            user("u1", "2026-11-23T10:00:00Z", "không, dùng cách khác cho phần này")]


def write(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")


def read_lines(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class DigestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cfg = self.tmp / "cfg"
        self.home = self.tmp / "home"
        self.retro = self.home / "retro"
        self.transcript = self.cfg / "projects" / "proj" / "t1.jsonl"
        self.retro.mkdir(parents=True)
        (self.retro / "patterns.json").write_text(json.dumps({"correction_prefix": ["không"]}), encoding="utf-8")

    def run_cli(self, *extra):
        argv = ["run", "--config-dir", str(self.cfg), "--home", str(self.home), "--now", NOW] + list(extra)
        with contextlib.redirect_stdout(io.StringIO()):
            return main(argv)

    def commit(self):
        return main(["commit", "--home", str(self.home)])

    def records(self):
        return read_lines(self.retro / "digest.next.jsonl")

    def history(self):
        return read_lines(self.retro / "instructions.next.jsonl")

    def seed_history(self, lines):
        self.retro.mkdir(parents=True, exist_ok=True)
        with open(self.retro / "instructions.jsonl", "w", encoding="utf-8") as handle:
            for line in lines:
                handle.write(json.dumps(line) + "\n")

    def test_normalise_strips_ids_numbers_paths_code_and_branch_names(self):
        self.assertEqual(
            normalise("PR #176 merge rồi, pull main về repo và xoá worktree rule4-anchor-precedence"),
            normalise("PR #177 merge rồi, pull main về repo và xoá worktree merge-prompt-tail"))
        self.assertEqual(normalise("open /a/b and `x`"), normalise("open /c/d and `y z`"))

    def test_third_sighting_in_seven_days_emits_a_repeat(self):
        text = "please rebase the branch onto main now"
        self.seed_history([
            {"key": normalise(text), "ts": "2026-11-20T10:00:00Z", "session": "s0"},
            {"key": normalise(text), "ts": "2026-11-17T16:00:00Z", "session": "s0"},
        ])
        write(self.transcript, [user("u1", "2026-11-23T10:00:00Z", text)])
        self.assertEqual(self.run_cli(), 0)
        repeats = [r for r in self.records() if r["kind"] == "repeat"]
        self.assertEqual(len(repeats), 1)
        self.assertEqual((repeats[0]["count"], repeats[0]["key"]), (3, normalise(text)))
        self.assertEqual(repeats[0]["id"], "s1:u1:repeat:0")
        self.assertEqual((repeats[0]["project"], repeats[0]["excerpt"]), ("proj", text))
        self.assertEqual(len(self.history()), 3)

    def test_two_sightings_emit_no_repeat(self):
        text = "please rebase the branch onto main now"
        self.seed_history([{"key": normalise(text), "ts": "2026-11-20T10:00:00Z", "session": "s0"}])
        write(self.transcript, [user("u1", "2026-11-23T10:00:00Z", text)])
        self.run_cli()
        self.assertEqual(self.records(), [])

    def test_instructions_older_than_seven_days_drop(self):
        text = "please rebase the branch onto main now"
        self.seed_history([
            {"key": normalise(text), "ts": "2026-11-20T10:00:00Z", "session": "s0"},
            {"key": normalise(text), "ts": "2026-11-15T14:59:59Z", "session": "s0"},
            {"key": "old", "ts": "2026-11-01T10:00:00Z", "session": "s0"},
        ])
        write(self.transcript, [user("u1", "2026-11-23T10:00:00Z", text)])
        self.run_cli()
        self.assertEqual(self.records(), [])
        self.assertEqual([h["ts"] for h in self.history()], ["2026-11-20T10:00:00Z", "2026-11-23T10:00:00Z"])

    def test_short_answers_and_decision_answers_stay_out_of_history(self):
        question = {"type": "assistant", "uuid": "a1", "sessionId": "s1", "timestamp": "2026-11-23T10:00:01Z",
                    "message": {"role": "assistant", "content": [
                        {"type": "text", "text": "Options:\nA. keep it (recommended)\nB. drop it\nWhich option?"}]}}
        write(self.transcript, [
            user("u0", "2026-11-23T10:00:00Z", "start the work on the digest"),
            question,
            user("u2", "2026-11-23T10:00:02Z", "go with option A as you suggested"),
            user("u3", "2026-11-23T10:00:03Z", "ok"),
            user("u4", "2026-11-23T10:00:04Z", "chọn A"),
            user("u5", "2026-11-23T10:00:05Z", "/run-plan some long argument with words"),
        ])
        self.run_cli()
        self.assertEqual([h["ts"] for h in self.history()], ["2026-11-23T10:00:00Z"])
        self.assertEqual([r["answer"] for r in self.records() if r["kind"] == "decision"],
                         ["go with option A as you suggested"])

    def test_run_then_commit_reads_each_line_once(self):
        write(self.transcript, corrected())
        self.run_cli()
        self.assertEqual(len(self.records()), 1)
        self.assertEqual(self.commit(), 0)
        self.assertFalse((self.retro / "digest.next.jsonl").exists())
        self.assertEqual([r["kind"] for r in read_lines(self.retro / "digest.jsonl")], ["correction"])
        self.assertTrue((self.retro / "state.json").exists())
        self.assertTrue((self.retro / "instructions.jsonl").exists())
        self.run_cli()
        self.assertEqual(self.records(), [])

    def test_run_without_commit_rereads(self):
        write(self.transcript, corrected())
        self.run_cli()
        first = self.records()
        self.run_cli()
        self.assertEqual(self.records(), first)
        self.assertEqual(len(first), 1)

    def test_shrunk_file_emits_nothing_twice(self):
        entries = corrected() + [assistant("a1", "2026-11-23T10:00:01Z", "Understood, " * 20)]
        write(self.transcript, entries)
        self.run_cli()
        self.commit()
        write(self.transcript, entries[:3])
        self.run_cli()
        self.assertEqual(self.records(), [])

    def test_skipped_files_stay_skipped(self):
        self.transcript.parent.mkdir(parents=True)
        shutil.copy(FIXTURES / "headless.jsonl", self.transcript)
        self.run_cli()
        self.assertEqual(self.records(), [])
        self.commit()
        state = json.loads((self.retro / "state.json").read_text(encoding="utf-8"))
        entry = state["files"][str(self.transcript.resolve())]
        self.assertEqual(entry["skip"], "headless")
        with open(self.transcript, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(user("u9", "2026-11-23T11:00:00Z", "không, dùng cách khác cho phần này")) + "\n")
        self.run_cli()
        self.assertEqual(self.records(), [])

    def test_retro_session_is_skipped_and_never_read_again(self):
        skill = {"type": "assistant", "uuid": "a5", "sessionId": "s1", "timestamp": "2026-11-23T10:00:30Z",
                 "message": {"role": "assistant", "content": [
                     {"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "retro"}}]}}
        write(self.transcript, [user("u0", "2026-11-23T09:59:58Z", "run the daily review for me please"),
                                skill,
                                user("u1", "2026-11-23T10:01:00Z", "không, dùng cách khác cho phần này")])
        self.run_cli()
        self.assertEqual(self.records(), [])
        self.assertEqual(self.history(), [])
        self.commit()
        state = json.loads((self.retro / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["files"][str(self.transcript.resolve())]["skip"], "retro")
        with open(self.transcript, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(user("u9", "2026-11-23T11:00:00Z", "không, dùng cách khác cho phần này")) + "\n")
        self.run_cli()
        self.assertEqual(self.records(), [])
        self.assertEqual(self.history(), [])

    def test_history_is_redacted(self):
        write(self.transcript, [user("u1", "2026-11-23T10:00:00Z", "use this token " + TOKEN + " for the push")])
        self.run_cli()
        text = (self.retro / "instructions.next.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(TOKEN, text)
        self.assertEqual(len(text.splitlines()), 1)

    def test_state_next_records_last_run_and_keeps_untouched_files(self):
        write(self.transcript, [user("u1", "2026-11-23T10:00:00Z", "start the work on the digest")])
        self.run_cli()
        self.commit()
        state = json.loads((self.retro / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["last_run"], NOW)
        self.transcript.unlink()
        self.run_cli()
        state = json.loads((self.retro / "state.next.json").read_text(encoding="utf-8"))
        self.assertEqual(len(state["files"]), 1)

    def test_escaped_secrets_leave_valid_json_with_strings_intact(self):
        quoted = 'echo "API_KEY=[REDACTED]" now please run it'
        auth = "write the config line //reg/:_authToken=[REDACTED]"
        write(self.transcript, [user("u1", "2026-11-23T10:00:00Z", quoted), user("u2", "2026-11-23T10:00:01Z", auth)])
        self.run_cli()
        self.assertEqual([h["key"] for h in self.history()], [normalise(quoted), normalise(auth)])
        state = json.loads((self.retro / "state.next.json").read_text(encoding="utf-8"))
        self.assertEqual(len(state["files"]), 1)

    def test_pending_question_is_redacted_everywhere(self):
        question = 'Use API_KEY="supersecret1" then?'
        asked = assistant("a1", "2026-11-23T10:00:01Z", "Options:\nA. yes\nB. no\n" + question)
        write(self.transcript, [user("u0", "2026-11-23T10:00:00Z", "start the work on the digest"), asked])
        self.run_cli()
        for path in self.retro.iterdir():
            self.assertNotIn("supersecret1", path.read_text(encoding="utf-8"), path.name)
        state = json.loads((self.retro / "state.next.json").read_text(encoding="utf-8"))
        pending = next(iter(state["files"].values()))["pending"]
        self.assertEqual(pending["question"], 'Use API_KEY="[REDACTED]" then?')

    def test_candidates_before_the_window_are_not_counted_or_stored(self):
        text = "please rebase the branch onto main now"
        write(self.transcript, [
            user("u1", "2026-11-13T10:00:00Z", text),
            user("u2", "2026-11-13T11:00:00Z", text),
            user("u3", "2026-11-23T10:00:00Z", text),
        ])
        self.run_cli()
        self.assertEqual(self.records(), [])
        self.assertEqual([h["ts"] for h in self.history()], ["2026-11-23T10:00:00Z"])

    def test_commit_without_run_exits_2(self):
        self.assertEqual(self.commit(), 2)


    def test_without_a_patterns_file_only_english_words_mark_a_correction(self):
        (self.retro / "patterns.json").unlink()
        write(self.transcript, corrected())
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual([r for r in read_lines(self.retro / "digest.next.jsonl") if r["kind"] == "correction"], [])

    def test_a_bad_patterns_file_exits_2_and_writes_nothing(self):
        (self.retro / "patterns.json").write_text("{not json", encoding="utf-8")
        write(self.transcript, corrected())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.run_cli(), 2)
        self.assertFalse((self.retro / "digest.next.jsonl").exists())


    def test_commit_replaces_the_previous_digest(self):
        write(self.transcript, corrected())
        self.run_cli()
        self.commit()
        self.run_cli()
        self.commit()
        self.assertTrue((self.retro / "digest.jsonl").exists())
        self.assertEqual(read_lines(self.retro / "digest.jsonl"), [])


if __name__ == "__main__":
    unittest.main()
