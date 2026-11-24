import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from ledger import main


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = main(list(argv))
    return code, out.getvalue().strip()


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name
        self.retro = Path(self.home) / "retro"
        self.lessons = Path(self.home) / "lessons.md"
        patcher = mock.patch.dict(os.environ, {"RETRO_NO_NOTIFY": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def cli(self, *argv):
        return run(argv[0], "--home", self.home, *argv[1:])

    def record_lessons(self, ids):
        for n in ids:
            self.cli("record", "--id", "L-%d" % n, "--kind", "lesson", "--target", str(self.lessons), "--text", "t%d" % n)

    def test_second_lock_by_another_owner_exits_4(self):
        self.assertEqual(self.cli("lock", "--owner", "a", "--now", "2026-11-23T10:00:00Z")[0], 0)
        self.assertEqual(self.cli("lock", "--owner", "b", "--now", "2026-11-23T10:30:00Z")[0], 4)

    def test_same_owner_lock_is_reentrant(self):
        self.cli("lock", "--owner", "a", "--now", "2026-11-23T10:00:00Z")
        self.assertEqual(self.cli("lock", "--owner", "a", "--now", "2026-11-23T10:01:00Z")[0], 0)

    def test_stale_lock_is_taken_over(self):
        self.cli("lock", "--owner", "a", "--now", "2026-11-23T07:00:00Z")
        self.assertEqual(self.cli("lock", "--owner", "b", "--now", "2026-11-23T10:00:00Z")[0], 0)
        self.assertEqual(json.loads((self.retro / "lock").read_text())["owner"], "b")

    def make_lock(self, body, age_hours):
        self.retro.mkdir(parents=True, exist_ok=True)
        path = self.retro / "lock"
        path.write_text(body)
        stamp = time.time() - age_hours * 3600
        os.utime(path, (stamp, stamp))

    def test_empty_stale_lock_is_taken_over_by_mtime(self):
        self.make_lock("", 3)
        self.assertEqual(self.cli("lock", "--owner", "b")[0], 0)

    def test_empty_fresh_lock_still_blocks(self):
        self.make_lock("", 0)
        self.assertEqual(self.cli("lock", "--owner", "b")[0], 4)

    def test_future_dated_lock_is_taken_over(self):
        self.make_lock(json.dumps({"owner": "a", "ts": "2999-01-01T00:00:00Z"}), 0)
        self.assertEqual(self.cli("lock", "--owner", "b")[0], 0)

    def test_unlock_removes_ownerless_lock(self):
        self.make_lock("", 0)
        self.assertEqual(self.cli("unlock", "--owner", "b")[0], 0)
        self.assertFalse((self.retro / "lock").exists())

    def test_unlock_by_other_owner_exits_4_and_owner_removes(self):
        self.cli("lock", "--owner", "a")
        self.assertEqual(self.cli("unlock", "--owner", "b")[0], 4)
        self.assertEqual(self.cli("unlock", "--owner", "a")[0], 0)
        self.assertFalse((self.retro / "lock").exists())

    def test_sight_counts_distinct_sources(self):
        self.assertEqual(self.cli("sight", "--key", "k", "--source", "s1")[1], "1")
        self.assertEqual(self.cli("sight", "--key", "k", "--source", "s1")[1], "1")
        self.assertEqual(self.cli("sight", "--key", "k", "--source", "s2")[1], "2")
        self.assertEqual(self.cli("sight", "--key", "other", "--source", "s2")[1], "1")

    def test_next_id_never_reuses_a_deleted_id(self):
        self.lessons.write_text("".join("- L-%d · text\n" % n for n in (1, 2, 3)))
        self.record_lessons([1, 2, 3])
        self.lessons.write_text("- L-1 · text\n- L-2 · text\n")
        self.assertEqual(self.cli("next-id", "--kind", "lesson", "--target", str(self.lessons))[1], "L-4")

    def test_next_id_resolves_equivalent_target_paths(self):
        dotted = str(Path(self.home) / "." / "lessons.md")
        self.cli("record", "--id", "L-1", "--kind", "lesson", "--target", dotted, "--text", "t")
        self.assertEqual(self.cli("next-id", "--kind", "lesson", "--target", str(self.lessons))[1], "L-2")
        self.assertEqual(self.cli("drop", "--id", "L-1", "--target", str(self.lessons))[0], 0)

    def test_next_id_reads_ids_present_in_file(self):
        self.lessons.write_text("- L-7 · text\n")
        self.assertEqual(self.cli("next-id", "--kind", "lesson", "--target", str(self.lessons))[1], "L-8")

    def test_next_id_first_lesson_and_memory(self):
        self.assertEqual(self.cli("next-id", "--kind", "lesson", "--target", str(self.lessons))[1], "L-1")
        self.cli("record", "--id", "M-2", "--kind", "memory", "--target", "/x/m.md", "--text", "t")
        self.assertEqual(self.cli("next-id", "--kind", "memory", "--target", "/x/other.md")[1], "M-3")

    def test_deleted_lesson_becomes_one_veto_while_a_longer_id_remains(self):
        self.lessons.write_text("- L-3 · a\n- L-30 · b\n")
        self.record_lessons([3, 30])
        self.lessons.write_text("- L-30 · b\n")
        code, out = self.cli("sync-vetoes")
        self.assertEqual((code, out), (0, "L-3"))
        self.assertEqual(self.cli("sync-vetoes")[1], "")
        rows = [json.loads(line) for line in self.cli("vetoed")[1].splitlines()]
        self.assertEqual([r["id"] for r in rows], ["L-3"])

    def test_tilde_target_is_stored_expanded_and_not_vetoed(self):
        with mock.patch.dict(os.environ, {"HOME": self.home}):
            (Path(self.home) / "lessons").mkdir()
            target = Path(self.home).resolve() / "lessons" / "x.md"
            target.write_text("- L-1 · a\n")
            self.cli("record", "--id", "L-1", "--kind", "lesson", "--target", "~/lessons/x.md", "--text", "t")
            rows = [json.loads(l) for l in (self.retro / "written.jsonl").read_text().splitlines()]
            self.assertEqual(rows[0]["target"], str(target))
            self.assertEqual(self.cli("sync-vetoes")[1], "")

    def test_deleted_memory_file_becomes_a_veto(self):
        mem = Path(self.home) / "mem.md"
        mem.write_text("---\nretro_id: M-1\n---\n")
        self.cli("record", "--id", "M-1", "--kind", "memory", "--target", str(mem), "--text", "t")
        self.assertEqual(self.cli("sync-vetoes")[1], "")
        mem.unlink()
        self.assertEqual(self.cli("sync-vetoes")[1], "M-1")

    def test_dropped_lesson_is_not_a_veto(self):
        self.lessons.write_text("- L-2 · a\n")
        self.record_lessons([2])
        self.assertEqual(self.cli("drop", "--id", "L-2", "--target", str(self.lessons))[0], 0)
        self.lessons.write_text("")
        self.assertEqual(self.cli("sync-vetoes")[1], "")

    def test_drop_unknown_record_exits_2(self):
        self.assertEqual(self.cli("drop", "--id", "L-9", "--target", str(self.lessons))[0], 2)

    def test_count_adds_to_the_day_row(self):
        for _ in range(2):
            self.cli("count", "--date", "2026-11-23", "--important", "1", "--routine", "2", "--avoidable", "3",
                     "--corrections", "4", "--repeats", "5", "--lessons", "6")
        self.cli("count", "--date", "2026-11-22", "--important", "1", "--routine", "0", "--avoidable", "0",
                 "--corrections", "0", "--repeats", "0", "--lessons", "0")
        rows = [json.loads(line) for line in (self.retro / "decisions.jsonl").read_text().splitlines()]
        self.assertEqual([r["date"] for r in rows], ["2026-11-22", "2026-11-23"])
        self.assertEqual(rows[1], {"date": "2026-11-23", "important": 2, "routine": 4, "avoidable": 6,
                                   "corrections": 8, "repeats": 10, "lessons_written": 12})

    def test_record_notifies_unless_disabled(self):
        with mock.patch("ledger.subprocess.run") as runner:
            self.cli("record", "--id", "L-1", "--kind", "lesson", "--target", str(self.lessons), "--text", 'say "hi"')
            runner.assert_not_called()
            with mock.patch.dict(os.environ, {"RETRO_NO_NOTIFY": ""}):
                self.cli("record", "--id", "L-2", "--kind", "lesson", "--target", str(self.lessons), "--text", 'say "hi"')
            args = runner.call_args[0][0]
            self.assertEqual(args[:2], ["osascript", "-e"])
            self.assertIn('say \\"hi\\"', args[2])
            self.assertIn("retro: lessons.md", args[2])

    def test_record_redacts_text(self):
        token = "ghp_" + "a" * 36
        self.cli("record", "--id", "L-1", "--kind", "lesson", "--target", str(self.lessons), "--text", "key " + token)
        self.assertNotIn(token, (self.retro / "written.jsonl").read_text())

    def test_bad_arguments_exit_2(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            main(["bogus", "--home", self.home])
        self.assertEqual(ctx.exception.code, 2)


    def test_new_owner_is_unique_per_call(self):
        first = self.cli("new-owner", "--kind", "listen", "--now", "2026-11-23T10:00:00Z")
        second = self.cli("new-owner", "--kind", "listen", "--now", "2026-11-23T10:00:00Z")
        self.assertEqual((first[0], second[0]), (0, 0))
        self.assertRegex(first[1], r"^listen-\d{4}-\d{2}-\d{2}-[0-9a-f]{6}$")
        self.assertNotEqual(first[1], second[1])

    def test_two_listen_owners_do_not_share_the_lock(self):
        a = self.cli("new-owner", "--kind", "listen")[1]
        b = self.cli("new-owner", "--kind", "listen")[1]
        self.assertEqual(self.cli("lock", "--owner", a)[0], 0)
        self.assertEqual(self.cli("lock", "--owner", b)[0], 4)


    def scratch(self, owner):
        folder = self.retro / "scratch" / owner / "pages"
        folder.mkdir(parents=True)
        (folder / "page1.txt").write_text("x")
        return self.retro / "scratch" / owner

    def test_unlock_removes_the_owner_scratch_folder(self):
        self.cli("lock", "--owner", "a")
        folder = self.scratch("a")
        self.assertEqual(self.cli("unlock", "--owner", "a")[0], 0)
        self.assertFalse(folder.exists())
        self.assertFalse((self.retro / "scratch").exists())

    def test_unlock_keeps_another_owner_scratch_folder(self):
        self.cli("lock", "--owner", "a")
        other = self.scratch("b")
        self.cli("unlock", "--owner", "a")
        self.assertTrue(other.exists())

    def test_refused_unlock_keeps_its_scratch_folder(self):
        self.cli("lock", "--owner", "a")
        folder = self.scratch("b")
        self.assertEqual(self.cli("unlock", "--owner", "b")[0], 4)
        self.assertTrue(folder.exists())

    def test_unlock_never_leaves_the_scratch_folder(self):
        self.cli("lock", "--owner", "..")
        keep = self.retro / "keep.txt"
        keep.write_text("x")
        self.cli("unlock", "--owner", "..")
        self.assertTrue(keep.exists())


if __name__ == "__main__":
    unittest.main()
