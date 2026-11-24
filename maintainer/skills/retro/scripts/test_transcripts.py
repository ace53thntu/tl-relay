import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from transcripts import (
    BUILTINS,
    config_dir,
    list_transcripts,
    operator_text,
    read_new,
    skip_reason,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(name):
    with open(FIXTURES / name, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class ConfigDirTest(unittest.TestCase):
    def test_argument_wins_then_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp, "a")
            b = Path(tmp, "b")
            a.mkdir()
            b.mkdir()
            with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(b)}):
                self.assertEqual(config_dir(str(a)), a.resolve())
                self.assertEqual(config_dir(None), b.resolve())
            env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
            env["HOME"] = str(a)
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(config_dir(None), (a / ".claude").resolve())


class ListTest(unittest.TestCase):
    def test_lists_only_depth_two_transcripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "projects" / "p" / "s1" / "subagents").mkdir(parents=True)
            (root / "projects" / "p" / "a.jsonl").write_text("{}\n")
            (root / "projects" / "p" / "s1" / "subagents" / "b.jsonl").write_text("{}\n")
            self.assertEqual(list_transcripts(root), [(root / "projects" / "p" / "a.jsonl").resolve()])

    def test_symlinked_config_dirs_give_one_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "shared" / "p").mkdir(parents=True)
            (root / "shared" / "p" / "a.jsonl").write_text("{}\n")
            for name in ("c1", "c2"):
                (root / name).mkdir()
                (root / name / "projects").symlink_to(root / "shared")
            self.assertEqual(list_transcripts(root / "c1"), list_transcripts(root / "c2"))
            self.assertEqual(len(list_transcripts(root / "c1")), 1)


class ReadNewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name, "t.jsonl")

    def test_stops_at_the_last_newline(self):
        first = b'{"n": 1}\n{"n": 2}\n'
        self.path.write_bytes(first + b'{"n": 3')
        entries, offset = read_new(self.path, 0)
        self.assertEqual([e["n"] for e in entries], [1, 2])
        self.assertEqual(offset, len(first))

    def test_resumes_from_the_offset(self):
        self.path.write_bytes(b'{"n": 1}\n{"n": 2}\n')
        _, offset = read_new(self.path, 0)
        with open(self.path, "ab") as handle:
            handle.write(b'{"n": 3}\n')
        entries, new_offset = read_new(self.path, offset)
        self.assertEqual([e["n"] for e in entries], [3])
        self.assertEqual(new_offset, self.path.stat().st_size)

    def test_restarts_at_zero_when_the_file_shrank(self):
        self.path.write_bytes(b'{"n": 1}\n')
        entries, offset = read_new(self.path, 9999)
        self.assertEqual([e["n"] for e in entries], [1])
        self.assertEqual(offset, 9)

    def test_skips_a_line_that_is_not_json(self):
        self.path.write_bytes(b'{"n": 1}\nnot json\n{"n": 2}\n')
        entries, _ = read_new(self.path, 0)
        self.assertEqual([e["n"] for e in entries], [1, 2])


class SkipTest(unittest.TestCase):
    def test_headless_is_skipped(self):
        self.assertEqual(skip_reason(load("headless.jsonl")), "headless")

    def test_own_retro_session_after_clear_is_skipped(self):
        self.assertEqual(skip_reason(load("retro-own.jsonl")), "retro")

    def test_interactive_is_kept(self):
        self.assertEqual(skip_reason(load("interactive.jsonl")), "")

    def test_desktop_entrypoint_is_kept(self):
        entries = load("interactive.jsonl")
        for entry in entries:
            entry["entrypoint"] = "claude-desktop"
        self.assertEqual(skip_reason(entries), "")

    def test_undecided_without_an_operator_message(self):
        self.assertIsNone(skip_reason(load("interactive.jsonl")[:2]))


class OperatorTextTest(unittest.TestCase):
    def test_only_real_operator_messages_count(self):
        texts = [t for t in map(operator_text, load("interactive.jsonl")) if t]
        self.assertEqual(texts, ["Please outline the next step.", "/write-plan a.md"])

    def test_builtins_include_clear(self):
        self.assertIn("clear", BUILTINS)

    def test_sidechain_interrupt_and_assistant_are_not_operator_text(self):
        base = {"type": "user", "message": {"content": "hello"}}
        self.assertEqual(operator_text(base), "hello")
        self.assertIsNone(operator_text(dict(base, isSidechain=True)))
        self.assertIsNone(operator_text({"type": "user", "message": {"content": "[Request interrupted by user]"}}))
        self.assertIsNone(operator_text({"type": "assistant", "message": {"content": "hello"}}))


if __name__ == "__main__":
    unittest.main()
