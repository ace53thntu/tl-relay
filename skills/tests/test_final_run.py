import contextlib
import errno
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import time
import unittest
from unittest import mock

import fr_fixture
import fr_git
import fr_inputs
import fr_lock
import fr_record
import fr_score
import fr_tiers

ALPHA = "skills/alpha/SKILL.md"


class Fingerprint(unittest.TestCase):
    def setUp(self):
        self.sb = fr_fixture.Sandbox()
        self.addCleanup(self.sb.cleanup)

    def fp(self):
        return fr_inputs.fingerprint(self.sb.repo, "HEAD")

    def changes_after(self, path, text):
        before = self.fp()
        self.sb.commit(path, text)
        return self.fp() != before

    def test_a_body_edit_keeps_the_fingerprint(self):
        text = (self.sb.repo / ALPHA).read_text() + "More body.\n"
        self.assertFalse(self.changes_after(ALPHA, text))

    def test_a_runner_edit_changes_the_fingerprint(self):
        self.assertTrue(self.changes_after("skills/tests/run-triggers.sh", "#!/bin/sh\n"))

    def test_a_workspace_fixture_edit_changes_the_fingerprint(self):
        self.assertTrue(self.changes_after("skills/tests/fixtures/trigger-workspace/x.txt", "x\n"))

    def test_a_description_edit_changes_it(self):
        text = fr_fixture.SKILL % ("alpha", "alpha changed", "alpha")
        self.assertTrue(self.changes_after(ALPHA, text))

    def test_a_block_scalar_description_is_read_in_full(self):
        block = "---\nname: alpha\ndescription: |\n  Use when first.\n  Second %s.\n---\nBody\n"
        self.sb.commit(ALPHA, block % "one")
        self.assertEqual(
            fr_inputs.skills_at(self.sb.repo, "HEAD")["alpha"][1],
            "|\n  Use when first.\n  Second one.",
        )
        self.assertTrue(self.changes_after(ALPHA, block % "two"))

    def test_a_prompt_edit_changes_it(self):
        self.assertTrue(self.changes_after("skills/tests/prompts/alpha-explicit.txt", "expect: alpha\nOther.\n"))

    def test_a_bootstrap_body_edit_changes_it(self):
        path = "skills/using-tl-relay/SKILL.md"
        text = (self.sb.repo / path).read_text() + "New rule.\n"
        self.assertTrue(self.changes_after(path, text))

    def test_a_session_hook_edit_changes_it(self):
        self.assertTrue(self.changes_after("hooks/session-start-skills.sh", "#!/bin/sh\nexit 1\n"))

    def test_an_unstaged_edit_does_not_change_it(self):
        before = self.fp()
        path = self.sb.repo / ALPHA
        path.write_text(fr_fixture.SKILL % ("alpha", "unstaged", "alpha"))
        self.assertEqual(self.fp(), before)

    def test_a_skill_with_no_frontmatter_raises_input_error(self):
        self.sb.commit("skills/beta/SKILL.md", "Just a body.\n")
        with self.assertRaises(fr_inputs.InputError):
            self.fp()

    def test_the_cli_prints_the_fingerprint(self):
        done = self.sb.run("fingerprint", "HEAD")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), self.fp())
        self.assertRegex(done.stdout.strip(), r"^[0-9a-f]{64}$")

    def test_the_cli_exits_2_on_bad_input(self):
        self.sb.commit("skills/beta/SKILL.md", "Just a body.\n")
        self.assertEqual(self.sb.run("fingerprint", "HEAD").returncode, 2)

    def test_a_subdirectory_repo_path_gives_the_root_fingerprint(self):
        sub = self.sb.repo / "skills" / "alpha"
        self.assertEqual(fr_inputs.fingerprint(sub, "HEAD"), self.fp())

    def test_a_tree_with_no_skills_raises_input_error(self):
        self.sb._git("rm", "-q", "-r", "skills/alpha", "skills/beta", "skills/using-tl-relay")
        self.sb._git("commit", "-q", "-m", "drop skills")
        with self.assertRaises(fr_inputs.InputError):
            self.fp()

    def test_a_non_txt_file_in_prompts_keeps_the_fingerprint(self):
        self.assertFalse(self.changes_after("skills/tests/prompts/notes.md", "scratch\n"))

    def test_a_separator_after_a_unicode_line_break_stays_in_the_description(self):
        text = "---\nname: alpha\ndescription: a\u2028---\u2028%s\n---\nBody\n"
        self.sb.commit(ALPHA, text % "one")
        self.assertTrue(self.changes_after(ALPHA, text % "two"))

    def test_a_bare_cr_in_the_frontmatter_raises_input_error(self):
        cases = {
            "cr only": "---\rname: alpha\rdescription: d\r---\rBody\r",
            "cr frontmatter, lf body": "---\rname: alpha\rdescription: d\r---\rBody\nMore\n",
            "untracked key": "---\nname: alpha\ndescription: base\nlicense: MIT\rdescription: one\n---\n",
            "closer then cr": "---\nname: alpha\ndescription: d\n---\rBody\nname: other\n---\nTail\n",
            "separator in value": "---\nname: alpha\ndescription: a\r---\rone\n---\nBody\n",
            "key in value": "---\nname: alpha\ndescription: a\rname: other\n---\n",
            "doubled on a value": "---\nname: alpha\r\r\ndescription: d\n---\n",
            "doubled on the opener": "---\r\r\nname: alpha\ndescription: d\n---\n",
            "doubled on the closer": "---\nname: alpha\ndescription: d\n---\r\r\nBody\n",
        }
        for label, text in cases.items():
            with self.subTest(label):
                with self.assertRaisesRegex(fr_inputs.InputError, "bare CR"):
                    fr_inputs.frontmatter(text)

    def test_a_bare_cr_in_the_body_keeps_the_fingerprint(self):
        text = "---\nname: alpha\ndescription: d\n---\nBody\r%s\n"
        self.assertEqual(
            fr_inputs.frontmatter(text % "one"), {"name": "alpha", "description": "d"},
        )
        self.sb.commit(ALPHA, text % "one")
        self.assertFalse(self.changes_after(ALPHA, text % "two"))

    def test_a_unicode_line_break_stays_inside_the_value(self):
        fields = fr_inputs.frontmatter("---\nname: alpha\ndescription: a name: other\n---\n")
        self.assertEqual(fields, {"name": "alpha", "description": "a name: other"})

    def test_a_symlinked_input_raises_input_error(self):
        for path in (ALPHA, "skills/using-tl-relay/SKILL.md",
                     "skills/tests/prompts/alpha-explicit.txt", "hooks/session-start-skills.sh"):
            with self.subTest(path=path):
                target = self.sb.repo / path
                target.unlink()
                os.symlink("/dev/null", target)
                self.sb._git("add", "-A")
                self.sb._git("commit", "-q", "-m", "link " + path)
                with self.assertRaises(fr_inputs.InputError):
                    self.fp()
                self.sb._git("reset", "-q", "--hard", "HEAD~1")

    def commit_link(self, path, mode):
        oid = self.sb._git("rev-parse", "HEAD").stdout.strip()
        if mode == "120000":
            oid = subprocess.run(
                ["git", "hash-object", "-w", "--stdin"], cwd=str(self.sb.repo), env=self.sb.env,
                input=b"/dev/null", check=True, capture_output=True,
            ).stdout.decode().strip()
        self.sb._git("rm", "-r", "-q", "--cached", "--ignore-unmatch", path)
        self.sb._git("update-index", "--add", "--cacheinfo", "%s,%s,%s" % (mode, oid, path))
        self.sb._git("commit", "-q", "-m", "link " + path)

    def test_a_linked_input_or_parent_raises_input_error(self):
        paths = ("skills", "skills/alpha", "skills/using-tl-relay", "skills/tests",
                 "skills/tests/prompts", "hooks", ALPHA, "skills/using-tl-relay/SKILL.md",
                 "skills/tests/prompts/alpha-explicit.txt", "hooks/session-start-skills.sh",
                 "maintainer/skills")
        for mode in ("120000", "160000"):
            for path in paths:
                with self.subTest(mode=mode, path=path):
                    self.commit_link(path, mode)
                    try:
                        with self.assertRaises(fr_inputs.InputError):
                            self.fp()
                    finally:
                        self.sb._git("reset", "-q", "HEAD~1")

    def test_a_linked_runner_input_or_parent_raises_input_error(self):
        paths = ("skills/tests/run-triggers.sh", "skills/tests/triggers.py", "skills/tests/fixtures",
                 "skills/tests/fixtures/trigger-workspace", "skills/tests/fixtures/trigger-workspace/x.txt",
                 "skills/tests/fixtures/trigger-workspace/sub/y.txt",
                 "skills/tests/fixtures/trigger-workspace/a\nb")
        for mode in ("120000", "160000"):
            for path in paths:
                with self.subTest(mode=mode, path=path):
                    self.commit_link(path, mode)
                    try:
                        with self.assertRaises(fr_inputs.InputError):
                            self.fp()
                    finally:
                        self.sb._git("reset", "-q", "HEAD~1")

    def test_a_link_outside_the_inputs_keeps_the_fingerprint(self):
        before = self.fp()
        for mode in ("120000", "160000"):
            for path in ("skills/alpha/references", "skills/tests/prompts/notes", "hooks/other.sh"):
                with self.subTest(mode=mode, path=path):
                    self.commit_link(path, mode)
                    self.assertEqual(self.fp(), before)
                    self.sb._git("reset", "-q", "HEAD~1")

    def test_a_prompt_name_ending_in_a_newline_is_not_an_input(self):
        real = "skills/tests/prompts/alpha-explicit.txt"
        self.sb.commit(real + "\n", "decoy\n")
        self.assertEqual(
            fr_inputs.prompts_at(self.sb.repo, "HEAD")["alpha-explicit.txt"],
            (self.sb.repo / real).read_bytes(),
        )
        self.assertTrue(self.changes_after(real, "expect: alpha\nOther.\n"))

    def test_a_skill_name_ending_in_a_newline_is_not_an_input(self):
        self.sb.commit(ALPHA + "\n", fr_fixture.SKILL % ("alpha", "decoy", "alpha"))
        self.assertEqual(fr_inputs.skills_at(self.sb.repo, "HEAD")["alpha"][1], "Use when alpha applies.")
        self.assertTrue(self.changes_after(ALPHA, fr_fixture.SKILL % ("alpha", "changed", "alpha")))

    def test_crlf_frontmatter_parses_like_lf(self):
        text = "---\r\nname: alpha\r\ndescription: d\r\n---\r\n"
        self.assertEqual(fr_inputs.frontmatter(text), {"name": "alpha", "description": "d"})

    def test_a_crlf_change_keeps_the_fingerprint(self):
        text = "---\nname: alpha\ndescription: |\n  first\n  second\n---\nBody\n"
        self.sb.commit(ALPHA, text)
        before = self.fp()
        self.sb.commit(ALPHA, text.replace("\n", "\r\n"))
        self.assertEqual(self.fp(), before)

    def test_a_moving_ref_is_read_at_one_commit(self):
        expected = self.fp()
        real = fr_git.run
        moved = []

        def run(repo, *args, **kw):
            result = real(repo, *args, **kw)
            if not moved:
                moved.append(1)
                self.sb.commit(ALPHA, fr_fixture.SKILL % ("alpha", "moved", "alpha"))
            return result

        with mock.patch.object(fr_git, "run", run):
            self.assertEqual(fr_inputs.fingerprint(self.sb.repo, "main"), expected)

    def test_a_missing_git_exits_2(self):
        with mock.patch.dict(os.environ, {"PATH": ""}):
            with self.assertRaises(fr_git.GitError):
                fr_git.run(self.sb.repo, "status")
        self.sb.env["PATH"] = ""
        self.assertEqual(self.sb.run("fingerprint", "HEAD").returncode, 2)


class Record(unittest.TestCase):
    def setUp(self):
        self.sb = fr_fixture.Sandbox()
        self.addCleanup(self.sb.cleanup)
        self.repo = self.sb.repo

    def test_a_linked_worktree_resolves_the_same_record(self):
        linked = self.repo.parent / "linked"
        self.sb._git("worktree", "add", "-q", "-b", "other", str(linked))
        self.assertEqual(fr_record.path(linked), fr_record.path(self.repo))
        self.assertEqual(fr_record.path(self.repo).name, "final-run.jsonl")
        self.assertEqual(fr_record.path(self.repo).parent.name, "tl-relay")
        fr_record.append_run(self.repo, "f", "c", "h", "p", "t", "PASS")
        self.assertEqual(len(fr_record.load(linked)), 1)

    def test_a_missing_record_loads_empty(self):
        self.assertEqual(fr_record.load(self.repo), [])

    def test_rows_round_trip_with_their_type(self):
        fr_record.append_run(self.repo, "f", "c1", "h", "p", "t", "PASS")
        fr_record.append_verdict(self.repo, "f", "c1", "h", "PASS")
        rows = fr_record.load(self.repo)
        self.assertEqual([r["type"] for r in rows], ["run", "verdict"])
        self.assertEqual(rows[0]["prompt"], "p")
        self.assertEqual(rows[0]["tier"], "t")
        self.assertEqual(rows[0]["result"], "PASS")
        self.assertEqual(rows[1]["verdict"], "PASS")

    def test_fail_outranks_an_earlier_pass(self):
        fr_record.append_verdict(self.repo, "f", "c", "h", "PASS")
        fr_record.append_verdict(self.repo, "f", "c", "h", "FAIL")
        fr_record.append_verdict(self.repo, "g", "c", "h", "PASS")
        rows = fr_record.load(self.repo)
        self.assertEqual(fr_record.verdict_for(rows, "f"), "FAIL")
        self.assertEqual(fr_record.verdict_for(rows, "g"), "PASS")
        self.assertIsNone(fr_record.verdict_for(rows, "none"))

    def test_fail_outranks_a_later_pass(self):
        fr_record.append_verdict(self.repo, "f", "c", "h", "FAIL")
        fr_record.append_verdict(self.repo, "f", "c", "h", "PASS")
        self.assertEqual(fr_record.verdict_for(fr_record.load(self.repo), "f"), "FAIL")

    def test_results_keep_their_order_per_prompt(self):
        for prompt, result in (("a", "PASS"), ("b", "FAIL"), ("a", "FAIL"), ("a", "PASS")):
            fr_record.append_run(self.repo, "f", "c", "h", prompt, "t", result)
        fr_record.append_run(self.repo, "g", "c", "h", "a", "t", "FAIL")
        rows = fr_record.load(self.repo)
        self.assertEqual(
            fr_record.results_for(rows, "f"), {"a": ["PASS", "FAIL", "PASS"], "b": ["FAIL"]}
        )

    def test_a_malformed_line_raises(self):
        fr_record.append_run(self.repo, "f", "c", "h", "p", "t", "PASS")
        with open(fr_record.path(self.repo), "a") as handle:
            handle.write("not json\n")
        with self.assertRaises(fr_record.RecordError):
            fr_record.load(self.repo)

    def test_a_non_object_line_raises(self):
        fr_record.append_run(self.repo, "f", "c", "h", "p", "t", "PASS")
        with open(fr_record.path(self.repo), "a") as handle:
            handle.write("[1]\n")
        with self.assertRaises(fr_record.RecordError):
            fr_record.load(self.repo)

    def test_a_truncated_last_line_raises(self):
        fr_record.append_run(self.repo, "f", "c", "h", "p", "t", "PASS")
        with open(fr_record.path(self.repo), "a") as handle:
            handle.write('{"type": "run", "finger')
        with self.assertRaises(fr_record.RecordError):
            fr_record.load(self.repo)

    def test_a_last_line_without_a_newline_raises(self):
        fr_record.append_run(self.repo, "f", "c", "h", "p", "t", "PASS")
        target = fr_record.path(self.repo)
        target.write_text(target.read_text().rstrip("\n"))
        with self.assertRaises(fr_record.RecordError):
            fr_record.load(self.repo)

    def test_a_failed_heldout_digest_is_found_across_fingerprints(self):
        fr_record.append_verdict(self.repo, "f1", "c", "h1", "FAIL")
        fr_record.append_verdict(self.repo, "f2", "c", "h2", "PASS")
        rows = fr_record.load(self.repo)
        self.assertTrue(fr_record.heldout_failed(rows, "h1", current="other"))
        self.assertFalse(fr_record.heldout_failed(rows, "h2", current="other"))
        self.assertFalse(fr_record.heldout_failed(rows, "h3", current="other"))

    def write_lines(self, *lines):
        target = fr_record.path(self.repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"".join(line + b"\n" for line in lines))

    def test_a_damaged_row_raises_with_its_line_number(self):
        good = json.dumps({"type": "verdict", "fingerprint": "f", "commit": "c",
                           "heldout": "h", "verdict": "PASS"}).encode()
        base = {"type": "verdict", "fingerprint": "f", "commit": "c", "heldout": "h", "verdict": "FAIL"}
        cases = {
            "unknown type": dict(base, type="verdic"),
            "missing field": {k: v for k, v in base.items() if k != "fingerprint"},
            "non-string field": dict(base, commit=1),
            "bad verdict": dict(base, verdict="MAYBE"),
            "bad heldout": dict(base, heldout=5),
            "bad run result": dict(base, type="run", prompt="p", tier="t", result="MAYBE"),
        }
        for label, row in cases.items():
            with self.subTest(label):
                self.write_lines(good, json.dumps(row).encode(), good)
                with self.assertRaisesRegex(fr_record.RecordError, "line 2"):
                    fr_record.load(self.repo)

    def test_a_wrong_typed_field_raises_with_its_line_number(self):
        good = json.dumps({"type": "verdict", "fingerprint": "f", "commit": "c",
                           "heldout": "h", "verdict": "PASS"}).encode()
        verdict = {"type": "verdict", "fingerprint": "f", "commit": "c",
                   "heldout": "h", "verdict": "FAIL"}
        run = {"type": "run", "fingerprint": "f", "commit": "c", "heldout": "h",
               "prompt": "p", "tier": "t", "result": "FAIL"}
        for bad in (["run"], {"run": 1}, 1, True, None):
            for base in (verdict, run):
                for name in base:
                    if bad is None and name == "heldout":
                        continue
                    with self.subTest(kind=base["type"], field=name, value=bad):
                        self.write_lines(good, json.dumps(dict(base, **{name: bad})).encode())
                        with self.assertRaisesRegex(fr_record.RecordError, "line 2"):
                            fr_record.load(self.repo)

    def test_a_row_without_a_heldout_key_raises(self):
        good = json.dumps({"type": "verdict", "fingerprint": "f", "commit": "c",
                           "heldout": None, "verdict": "PASS"}).encode()
        rows = {
            "verdict": {"type": "verdict", "fingerprint": "f", "commit": "c", "verdict": "FAIL"},
            "run": {"type": "run", "fingerprint": "f", "commit": "c",
                    "prompt": "p", "tier": "t", "result": "FAIL"},
        }
        for label, row in rows.items():
            with self.subTest(label):
                self.write_lines(good, json.dumps(row).encode())
                with self.assertRaisesRegex(fr_record.RecordError, "line 2"):
                    fr_record.load(self.repo)

    def test_a_null_heldout_is_accepted(self):
        fr_record.append_run(self.repo, "f", "c", None, "p", "t", "PASS")
        fr_record.append_verdict(self.repo, "f", "c", None, "PASS")
        self.assertEqual(len(fr_record.load(self.repo)), 2)

    def test_append_rejects_the_values_load_rejects(self):
        with self.assertRaises(fr_record.RecordError):
            fr_record.append_verdict(self.repo, "f", "c", "h", "MAYBE")
        with self.assertRaises(fr_record.RecordError):
            fr_record.append_run(self.repo, "f", "c", "h", "p", "t", "MAYBE")
        with self.assertRaises(fr_record.RecordError):
            fr_record.append_run(self.repo, "f", "c", 5, "p", "t", "PASS")
        self.assertEqual(fr_record.load(self.repo), [])

    def test_invalid_utf8_raises_with_its_line_number(self):
        good = json.dumps({"type": "verdict", "fingerprint": "f", "commit": "c",
                           "heldout": "h", "verdict": "PASS"}).encode()
        self.write_lines(good, b'{"type": "verdict", "verdict": "F\xffIL"}')
        with self.assertRaisesRegex(fr_record.RecordError, "line 2"):
            fr_record.load(self.repo)

    def test_a_losing_heldout_set_is_found_without_a_verdict(self):
        fr_record.append_run(self.repo, "f1", "c", "h1", "heldout/a", "t", "FAIL")
        fr_record.append_run(self.repo, "f1", "c", "h1", "heldout/a", "t", "FAIL")
        for prompt in ("heldout/a", "heldout/b"):
            for result in ("FAIL", "PASS", "PASS", "PASS", "PASS"):
                fr_record.append_run(self.repo, "f1", "c", "h2", prompt, "t", result)
        fr_record.append_run(self.repo, "f1", "c", "h3", "train/a", "t", "FAIL")
        fr_record.append_run(self.repo, "f1", "c", "h3", "train/a", "t", "FAIL")
        rows = fr_record.load(self.repo)
        self.assertTrue(fr_record.heldout_failed(rows, "h1", current="other"))
        self.assertFalse(fr_record.heldout_failed(rows, "h2", current="other"))
        self.assertFalse(fr_record.heldout_failed(rows, "h3", current="other"))

    def test_fails_from_two_fingerprints_do_not_add_up(self):
        for fingerprint in ("f1", "f2"):
            for result in ("FAIL", "PASS", "PASS", "PASS", "PASS"):
                fr_record.append_run(self.repo, fingerprint, "c", "h", "heldout/a", "t", result)
        rows = fr_record.load(self.repo)
        self.assertFalse(fr_record.heldout_failed(rows, "h", current="f3"))

    def test_run_results_without_a_verdict_decide_the_burn(self):
        cases = {
            "F,P,P,P,P": False,
            "P,P,F,P,P": False,
            "F": True,
            "F,P,P": True,
            "F,F": True,
            "P,F,P,F": True,
        }
        for sequence, burned in cases.items():
            with self.subTest(sequence):
                for letter in sequence.split(","):
                    result = "FAIL" if letter == "F" else "PASS"
                    fr_record.append_run(self.repo, "f1", "c", sequence, "heldout/a", "t", result)
                rows = fr_record.load(self.repo)
                self.assertEqual(fr_record.heldout_failed(rows, sequence, current="f2"), burned)
                self.assertFalse(fr_record.heldout_failed(rows, sequence, current="f1"))

    def test_a_pass_verdict_does_not_clear_a_later_lone_fail(self):
        fr_record.append_verdict(self.repo, "f1", "c", "h", "PASS")
        for result in ("PASS", "PASS", "FAIL"):
            fr_record.append_run(self.repo, "f1", "c", "h", "heldout/a", "t", result)
        rows = fr_record.load(self.repo)
        self.assertTrue(fr_record.heldout_failed(rows, "h", current="f2"))

    def test_a_pass_verdict_does_not_clear_an_earlier_lone_fail(self):
        fr_record.append_run(self.repo, "f1", "c", "h", "heldout/a", "t", "FAIL")
        fr_record.append_verdict(self.repo, "f1", "c", "h", "PASS")
        rows = fr_record.load(self.repo)
        self.assertTrue(fr_record.heldout_failed(rows, "h", current="f2"))

    def test_an_abandoned_heldout_fail_burns_the_digest(self):
        fr_record.append_run(self.repo, "f1", "c", "h", "heldout/a", "t", "FAIL")
        rows = fr_record.load(self.repo)
        self.assertTrue(fr_record.heldout_failed(rows, "h", current="f2"))
        self.assertFalse(fr_record.heldout_failed(rows, "h", current="f1"))

    def test_a_pass_verdict_on_another_digest_does_not_clear_a_fail(self):
        fr_record.append_run(self.repo, "f1", "c", "h", "heldout/a", "t", "FAIL")
        fr_record.append_verdict(self.repo, "f1", "c", "other", "PASS")
        rows = fr_record.load(self.repo)
        self.assertTrue(fr_record.heldout_failed(rows, "h", current="f2"))

    def test_a_pass_verdict_does_not_clear_two_fails_on_one_prompt(self):
        for _ in range(2):
            fr_record.append_run(self.repo, "f1", "c", "h", "heldout/a", "t", "FAIL")
        fr_record.append_verdict(self.repo, "f1", "c", "h", "PASS")
        rows = fr_record.load(self.repo)
        self.assertTrue(fr_record.heldout_failed(rows, "h", current="f2"))

    def test_heldout_failed_requires_current_by_keyword(self):
        with self.assertRaises(TypeError):
            fr_record.heldout_failed([], "h")
        with self.assertRaises(TypeError):
            fr_record.heldout_failed([], "h", "f")

    def test_heldout_matches(self):
        fr_record.append_run(self.repo, "same", "c", "h1", "p", "t", "PASS")
        fr_record.append_run(self.repo, "null", "c", None, "p", "t", "PASS")
        fr_record.append_run(self.repo, "mixed", "c", "h1", "p", "t", "PASS")
        fr_record.append_run(self.repo, "mixed", "c", "h2", "q", "t", "PASS")
        rows = fr_record.load(self.repo)
        self.assertTrue(fr_record.heldout_matches(rows, "none", "h1"))
        self.assertTrue(fr_record.heldout_matches(rows, "same", "h1"))
        self.assertFalse(fr_record.heldout_matches(rows, "same", "h2"))
        self.assertTrue(fr_record.heldout_matches(rows, "null", "h1"))
        self.assertFalse(fr_record.heldout_matches(rows, "mixed", "h1"))

    def test_null_digest_runs_do_not_hide_a_different_digest(self):
        fr_record.append_run(self.repo, "f1", "c", None, "p", "t", "PASS")
        fr_record.append_run(self.repo, "f1", "c", "h1", "q", "t", "PASS")
        rows = fr_record.load(self.repo)
        self.assertTrue(fr_record.heldout_matches(rows, "f1", "h1"))
        self.assertFalse(fr_record.heldout_matches(rows, "f1", "h2"))

    def test_the_current_fingerprint_can_resume_its_own_losing_runs(self):
        for _ in range(2):
            fr_record.append_run(self.repo, "f1", "c", "h", "heldout/a", "t", "FAIL")
        rows = fr_record.load(self.repo)
        self.assertTrue(fr_record.heldout_failed(rows, "h", current="f2"))
        self.assertFalse(fr_record.heldout_failed(rows, "h", current="f1"))

    def test_a_fail_verdict_counts_for_every_current_fingerprint(self):
        fr_record.append_verdict(self.repo, "f1", "c", "h", "FAIL")
        rows = fr_record.load(self.repo)
        self.assertTrue(fr_record.heldout_failed(rows, "h", current="f1"))
        self.assertTrue(fr_record.heldout_failed(rows, "h", current="f2"))

    def test_heldouts_for_reports_every_digest_and_null(self):
        fr_record.append_run(self.repo, "f", "c", "h1", "p", "t", "PASS")
        fr_record.append_run(self.repo, "f", "c", None, "q", "t", "PASS")
        rows = fr_record.load(self.repo)
        self.assertEqual(fr_record.heldouts_for(rows, "f"), {"h1", None})
        self.assertEqual(fr_record.heldouts_for(rows, "none"), set())

    def test_a_short_write_is_completed(self):
        real = os.write
        with mock.patch.object(fr_record.os, "write", lambda fd, data: real(fd, data[:3])):
            fr_record.append_run(self.repo, "f", "c", "h", "p", "t", "PASS")
        self.assertEqual(len(fr_record.load(self.repo)), 1)

    def test_a_write_that_makes_no_progress_raises(self):
        with mock.patch.object(fr_record.os, "write", lambda fd, data: 0):
            with self.assertRaises(fr_record.RecordError):
                fr_record.append_run(self.repo, "f", "c", "h", "p", "t", "PASS")

    def test_a_deeply_nested_line_raises_record_error(self):
        self.write_lines(b"[" * 100000)
        with self.assertRaisesRegex(fr_record.RecordError, "line 1"):
            fr_record.load(self.repo)


BOOT = "skills/using-tl-relay/SKILL.md"
TABLE = "## Skills\n\n| Skill | When |\n|---|---|\n| `a` | one |\n| `b` | two |\n\n## Other\n\n| X | Y |\n|---|---|\n| 1 | 2 |\n"


class Tiers(unittest.TestCase):
    def setUp(self):
        self.sb = fr_fixture.Sandbox()
        self.addCleanup(self.sb.cleanup)

    def changes(self, path, text):
        base = fr_git.run(self.sb.repo, "rev-parse", "HEAD").stdout.decode().strip()
        self.sb.commit(path, text)
        return fr_tiers.changes(self.sb.repo, base, "HEAD")

    def test_a_neighbour_fail_after_a_pass_needs_four_more(self):
        P, F = "PASS", "FAIL"
        self.assertEqual(fr_tiers.judge("neighbour", [P, F]), "more")
        self.assertEqual(fr_tiers.judge("neighbour", [P, F, P, P, P, P]), "pass")

    def test_strict_counts(self):
        P, F = "PASS", "FAIL"
        self.assertEqual(fr_tiers.judge("strict", [P] * 4), "pass")
        self.assertEqual(fr_tiers.judge("strict", [F, P, P, P, P]), "pass")
        self.assertEqual(fr_tiers.judge("strict", [F, P, F]), "fail")
        self.assertEqual(fr_tiers.judge("strict", [P, P, P]), "more")

    def test_neighbour_counts(self):
        P, F = "PASS", "FAIL"
        self.assertEqual(fr_tiers.judge("neighbour", [P]), "pass")
        self.assertEqual(fr_tiers.judge("neighbour", [F]), "more")
        self.assertEqual(fr_tiers.judge("neighbour", [F, P, P, P, P]), "pass")
        self.assertEqual(fr_tiers.judge("neighbour", [F, P, F]), "fail")

    def test_the_longest_skill_name_owns_a_prompt(self):
        self.assertEqual(fr_tiers.owner("write-skill-a.txt", ["write", "write-skill"]), "write-skill")
        self.assertIsNone(fr_tiers.owner("other-a.txt", ["write"]))

    def test_an_added_skills_row_is_rows_only(self):
        new = TABLE.replace("| `b` | two |\n", "| `b` | two |\n| `c` | three |\n")
        self.assertTrue(fr_tiers.rows_only(TABLE, new, {"c"}))

    def test_a_row_outside_the_skills_table_is_not_rows_only(self):
        new = TABLE + "| `c` | 4 |\n"
        self.assertFalse(fr_tiers.rows_only(TABLE, new, {"c"}))

    def test_an_edited_row_is_not_rows_only(self):
        self.assertFalse(fr_tiers.rows_only(TABLE, TABLE.replace("one", "uno"), {"c"}))

    def test_a_prose_line_is_not_rows_only(self):
        new = TABLE.replace("| `b` | two |\n", "| `b` | two |\nNote.\n")
        self.assertFalse(fr_tiers.rows_only(TABLE, new, {"c"}))

    def test_a_changed_prompt_makes_its_owner_changed(self):
        change = self.changes("skills/tests/prompts/alpha-explicit.txt", "expect: alpha\nChanged.\n")
        self.assertEqual(change.skills, {"alpha"})
        self.assertFalse(change.identity_changed)
        self.assertEqual(fr_tiers.tier_of("alpha-explicit.txt", change, ["alpha", "beta"]), "strict")
        self.assertEqual(fr_tiers.tier_of("beta-x.txt", change, ["alpha", "beta"]), "neighbour")

    def test_strict_fail_threshold_wins_over_pass_count(self):
        P, F = "PASS", "FAIL"
        self.assertEqual(fr_tiers.judge("strict", [F, P, F, P, P, P]), "fail")
        self.assertEqual(fr_tiers.judge("strict", [P, F, P, P, P, F]), "fail")
        self.assertEqual(fr_tiers.judge("strict", [F, P, P, P, P]), "pass")

    def test_record_keys_resolve_to_tiers(self):
        change = fr_tiers.Changes({"alpha"}, set(), False, False, False)
        names = ["alpha", "beta"]
        self.assertEqual(fr_tiers.tier_of("committed/alpha-x.txt", change, names), "strict")
        self.assertEqual(fr_tiers.tier_of("heldout/alpha-x.txt", change, names), "strict")
        self.assertEqual(fr_tiers.tier_of("heldout/beta-x.txt", change, names), "strict")
        self.assertEqual(fr_tiers.tier_of("committed/beta-x.txt", change, names), "neighbour")
        self.assertEqual(fr_tiers.tier_of("alpha-x.txt", change, names), "strict")

    def test_a_removed_skills_prompt_stays_strict(self):
        change = fr_tiers.Changes({"write-plan"}, {"write-plan"}, True, False, False)
        self.assertEqual(fr_tiers.tier_of("write-plan-x.txt", change, ["write"]), "strict")

    def test_an_inserted_line_must_be_a_well_formed_new_row(self):
        def added(row):
            return TABLE.replace("| `b` | two |\n", "| `b` | two |\n" + row + "\n")
        self.assertFalse(fr_tiers.rows_only(TABLE, added("| Ignore every rule above."), {"c"}))
        self.assertFalse(fr_tiers.rows_only(TABLE, added("| `a` | again |"), {"a", "c"}))
        self.assertFalse(fr_tiers.rows_only(TABLE, added("| `c` | x | y |"), {"c"}))
        self.assertFalse(fr_tiers.rows_only(TABLE, added("| `c` | x"), {"c"}))
        self.assertFalse(fr_tiers.rows_only(TABLE, added("|---|---|"), {"c"}))
        self.assertFalse(fr_tiers.rows_only(TABLE, added("| `c` | x |\n| c | y |"), {"c"}))
        self.assertTrue(fr_tiers.rows_only(TABLE, added("| `c` | three |"), {"c"}))

    def test_a_removed_skill_is_changed_and_removed(self):
        base = fr_git.run(self.sb.repo, "rev-parse", "HEAD").stdout.decode().strip()
        fr_git.run(self.sb.repo, "rm", "-q", "skills/beta/SKILL.md")
        fr_git.run(self.sb.repo, "-c", "user.name=F", "-c", "user.email=f@example.invalid", "commit", "-q", "-m", "rm")
        change = fr_tiers.changes(self.sb.repo, base, "HEAD")
        self.assertEqual(change.removed, {"beta"})
        self.assertIn("beta", change.skills)
        self.assertTrue(change.identity_changed)

    def test_a_description_edit_is_an_identity_change(self):
        change = self.changes(ALPHA, fr_fixture.SKILL % ("alpha", "alpha changed", "alpha"))
        self.assertEqual(change.skills, {"alpha"})
        self.assertTrue(change.identity_changed)

    def test_a_body_edit_changes_no_skill(self):
        change = self.changes(ALPHA, (self.sb.repo / ALPHA).read_text() + "More.\n")
        self.assertEqual(change.skills, set())
        self.assertFalse(change.identity_changed)
        self.assertFalse(change.all_strict)
        self.assertFalse(change.session_hook_changed)

    def test_a_bootstrap_prose_edit_makes_all_strict(self):
        change = self.changes(BOOT, (self.sb.repo / BOOT).read_text() + "Prose.\n")
        self.assertTrue(change.all_strict)
        self.assertEqual(fr_tiers.tier_of("beta-x.txt", change, ["alpha", "beta"]), "strict")

    def test_a_bootstrap_row_addition_keeps_neighbours(self):
        base = fr_git.run(self.sb.repo, "rev-parse", "HEAD").stdout.decode().strip()
        self.sb.commit(BOOT, (self.sb.repo / BOOT).read_text() + TABLE)
        mid = fr_git.run(self.sb.repo, "rev-parse", "HEAD").stdout.decode().strip()
        self.assertTrue(fr_tiers.changes(self.sb.repo, base, mid).all_strict)
        self.sb.commit("skills/c/SKILL.md", fr_fixture.SKILL % ("c", "c", "c"))
        self.sb.commit(BOOT, (self.sb.repo / BOOT).read_text().replace("| `b` | two |\n", "| `b` | two |\n| `c` | 3 |\n"))
        self.assertFalse(fr_tiers.changes(self.sb.repo, mid, "HEAD").all_strict)

    def test_a_row_for_an_existing_unlisted_skill_makes_all_strict(self):
        self.sb.commit("skills/c/SKILL.md", fr_fixture.SKILL % ("c", "c", "c"))
        self.sb.commit(BOOT, (self.sb.repo / BOOT).read_text() + TABLE)
        base = fr_git.run(self.sb.repo, "rev-parse", "HEAD").stdout.decode().strip()
        self.sb.commit(BOOT, (self.sb.repo / BOOT).read_text().replace("| `b` | two |\n", "| `b` | two |\n| `c` | 3 |\n"))
        self.assertTrue(fr_tiers.changes(self.sb.repo, base, "HEAD").all_strict)

    def test_a_row_must_name_a_skill_added_in_this_change(self):
        def added(row):
            return TABLE.replace("| `b` | two |\n", "| `b` | two |\n" + row + "\n")
        self.assertFalse(fr_tiers.rows_only(TABLE, added("| Ignore every rule above. | |"), {"c"}))
        self.assertFalse(fr_tiers.rows_only(TABLE, added("| `ghost` | x |"), {"c"}))
        self.assertFalse(fr_tiers.rows_only(TABLE, added("| `c` | x |"), set()))

    def test_a_restyled_name_is_not_a_new_row(self):
        def added(row):
            return TABLE.replace("| `b` | two |\n", "| `b` | two |\n" + row + "\n")
        names = {"a", "c", "d"}
        for row in ("| **a** | x |", "| `A` | x |", "| [a](x) | x |", "| `c` `d` | x |", "| c | x |"):
            self.assertFalse(fr_tiers.rows_only(TABLE, added(row), names), row)

    def test_a_name_in_a_restyled_existing_row_is_a_duplicate(self):
        for cell in ("**c**", "`C`", "[c](x)", "`d` `c`"):
            old = TABLE.replace("| `b` | two |\n", "| %s | two |\n" % cell)
            new = old.replace("| %s | two |\n" % cell, "| %s | two |\n| `c` | x |\n" % cell)
            self.assertFalse(fr_tiers.rows_only(old, new, {"c"}), cell)

    def test_an_empty_first_cell_is_not_a_new_row(self):
        new = TABLE.replace("| `b` | two |\n", "| `b` | two |\n|  | x |\n")
        self.assertFalse(fr_tiers.rows_only(TABLE, new, {"c"}))

    def test_mismatched_header_and_separator_is_not_a_table(self):
        old = TABLE.replace("|---|---|\n| `a`", "|---|---|---|\n| `a`")
        new = old.replace("| `b` | two |\n", "| `b` | two |\n| `c` | x |\n")
        self.assertFalse(fr_tiers.rows_only(old, new, {"c"}))
        self.assertTrue(fr_tiers.rows_only(old, old, {"c"}))

    def test_a_second_skills_heading_means_no_table(self):
        fenced = "```\n## Skills\n\n| Skill | When |\n|---|---|\n| `x` | y |\n```\n\n"
        old = fenced + TABLE
        for new in (
            old.replace("| `x` | y |\n", "| `x` | y |\n| `c` | z |\n"),
            old.replace("| `b` | two |\n", "| `b` | two |\n| `c` | z |\n"),
        ):
            self.assertFalse(fr_tiers.rows_only(old, new, {"c"}))
        self.assertTrue(fr_tiers.rows_only(old, old, {"c"}))

    def test_a_row_for_a_skill_whose_directory_differs_from_its_name_makes_all_strict(self):
        self.sb.commit(BOOT, (self.sb.repo / BOOT).read_text() + TABLE)
        base = fr_git.run(self.sb.repo, "rev-parse", "HEAD").stdout.decode().strip()
        self.sb.commit("skills/foo/SKILL.md", fr_fixture.SKILL % ("bar", "bar", "bar"))
        self.sb.commit(BOOT, (self.sb.repo / BOOT).read_text().replace("| `b` | two |\n", "| `b` | two |\n| `foo` | x |\n"))
        self.assertTrue(fr_tiers.changes(self.sb.repo, base, "HEAD").all_strict)

    def test_the_table_must_sit_directly_under_the_heading(self):
        table = "| Skill | When |\n|---|---|\n| `a` | y |\n"
        for opener in ("```\n", "<!--\n", "Prose.\n\n"):
            old = "## Skills\n\n" + opener + table
            new = old.replace("| `a` | y |\n", "| `a` | y |\n| `c` | z |\n")
            self.assertFalse(fr_tiers.rows_only(old, new, {"c"}), opener)
        old = "## Skills  \n\n" + table + "\n## Skills\n"
        new = old.replace("| `a` | y |\n", "| `a` | y |\n| `c` | z |\n")
        self.assertFalse(fr_tiers.rows_only(old, new, {"c"}))
        old = "## Skills  \n\n" + table
        new = old.replace("| `a` | y |\n", "| `a` | y |\n| `c` | z |\n")
        self.assertTrue(fr_tiers.rows_only(old, new, {"c"}))

    def test_an_invalid_delimiter_means_no_table(self):
        for delimiter in ("|---| |", "|---|:|", "    |---|---|", "|---|-x"):
            old = "## Skills\n\n| Skill | When |\n%s\n| `a` | y |\n" % delimiter
            new = old.replace("| `a` | y |\n", "| `a` | y |\n| `c` | z |\n")
            self.assertFalse(fr_tiers.rows_only(old, new, {"c"}), delimiter)
        old = "## Skills\n\n| Skill | When |\n| :-- | --: |\n| `a` | y |\n"
        new = old.replace("| `a` | y |\n", "| `a` | y |\n| `c` | z |\n")
        self.assertTrue(fr_tiers.rows_only(old, new, {"c"}))

    def test_the_real_bootstrap_table_accepts_a_new_skill_row(self):
        real = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "using-tl-relay", "SKILL.md")
        with open(real, encoding="utf-8") as handle:
            text = handle.read()
        self.sb.commit(BOOT, text)
        base = fr_git.run(self.sb.repo, "rev-parse", "HEAD").stdout.decode().strip()
        self.sb.commit("skills/zz-new/SKILL.md", fr_fixture.SKILL % ("zz-new", "new", "new"))
        row = next(line for line in text.split("\n") if line.startswith("| `brainstorm`"))
        self.sb.commit(BOOT, text.replace(row + "\n", row + "\n| `zz-new` | A new skill applies. |\n"))
        self.assertFalse(fr_tiers.changes(self.sb.repo, base, "HEAD").all_strict)

    def test_a_hook_edit_is_reported(self):
        change = self.changes("hooks/session-start-skills.sh", "#!/bin/sh\nexit 1\n")
        self.assertTrue(change.session_hook_changed)


ALPHA_PROMPT = "Run the alpha skill."
EDITED_PROMPT = "Run alpha now."
HELD_ALPHA = "Held alpha prompt."
HELD_BETA = "Held beta prompt."
EXPORT_MARK = "final-run-export."
ALPHA_PROMPT_FILE = "skills/tests/prompts/alpha-explicit.txt"


class ScoreBase(unittest.TestCase):
    def setUp(self):
        self.sb = self.fresh()
        self.heldout = self.sb.repo.parent / "heldout"
        self.sb.branch("feature")

    def fresh(self):
        sb = fr_fixture.Sandbox()
        self.addCleanup(sb.cleanup)
        return sb

    def write_heldout(self, **files):
        self.heldout.mkdir(exist_ok=True)
        for name, (skill, text) in files.items():
            (self.heldout / (name + ".txt")).write_text("expect: %s\n%s\n" % (skill, text))
        return str(self.heldout)

    def change_alpha(self):
        self.sb.commit("skills/alpha/SKILL.md", fr_fixture.SKILL % ("alpha", "alpha changed", "alpha"))

    def change_beta(self):
        self.sb.commit("skills/beta/SKILL.md", fr_fixture.SKILL % ("beta", "beta changed", "beta"))

    def change_prompt(self):
        self.sb.commit(ALPHA_PROMPT_FILE, "expect: alpha\n%s\n" % EDITED_PROMPT)

    def rows(self):
        return fr_record.load(self.sb.repo)

    def prompts_called(self):
        return [c["prompt"] for c in self.sb.agent_calls()]

    def score(self, *extra):
        return self.sb.run("score", *extra)

    def wait_for_agent(self, sb=None):
        sb = sb or self.sb
        for _ in range(300):
            if sb.agent_calls():
                return sb.agent_calls()[-1]
            time.sleep(0.1)
        self.fail("the agent never started")

    def reap(self, call):
        for kill, target in ((os.killpg, call["ppid"]), (os.kill, call["pid"])):
            try:
                kill(target, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def start_sleeping_score(self, plan_prompt=EDITED_PROMPT):
        self.change_prompt()
        self.sb.agent_plan({plan_prompt: "sleep"})
        proc = self.sb.popen("score")
        call = self.wait_for_agent()
        self.addCleanup(self.reap, call)
        self.addCleanup(proc.kill)
        return proc, call

    def recovery_file(self):
        return pathlib.Path(self.sb.env["TL_RELAY_HOME"]) / "locks" / "final-run-links.json"


class ScorePreconditions(ScoreBase):
    def refused(self, *extra, text=None):
        done = self.score(*extra)
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        if text:
            self.assertIn(text, done.stderr)
        self.assertEqual(self.sb.agent_calls(), [])

    def test_recover_is_not_a_command(self):
        done = self.sb.run("recover")
        self.assertEqual(done.returncode, 2)
        self.assertIn("invalid choice", done.stderr)

    def test_a_dirty_worktree_exits_two(self):
        (self.sb.repo / ALPHA).write_text(fr_fixture.SKILL % ("alpha", "dirty", "alpha"))
        self.refused(text="changes")

    def test_an_untracked_file_exits_two(self):
        (self.sb.repo / "scratch.txt").write_text("x")
        self.refused(text="changes")

    def test_a_missing_origin_main_exits_two(self):
        self.sb._git("update-ref", "-d", "refs/remotes/origin/main")
        self.refused(text="origin/main")

    def test_a_description_change_without_heldout_exits_two(self):
        self.change_alpha()
        self.refused(text="--heldout")

    def test_a_heldout_inside_the_checkout_exits_two(self):
        self.change_alpha()
        inside = self.sb.repo / ".git" / "heldout"
        inside.mkdir()
        (inside / "alpha-held.txt").write_text("expect: alpha\n%s\n" % HELD_ALPHA)
        done = self.score("--heldout", str(inside))
        self.assertEqual(done.returncode, 2)
        self.assertIn("outside the checkout", done.stderr)

    def test_an_empty_heldout_exits_two(self):
        self.change_alpha()
        self.heldout.mkdir()
        (self.heldout / "notes.md").write_text("not a prompt")
        self.refused("--heldout", str(self.heldout), text="no .txt")

    def test_a_failed_heldout_on_a_new_fingerprint_exits_two(self):
        self.change_alpha()
        directory = self.write_heldout(**{"alpha-held": ("alpha", HELD_ALPHA)})
        digest, _ = fr_score.read_heldout(directory, self.sb.repo)
        fr_record.append_verdict(self.sb.repo, "other", "c", digest, "FAIL")
        self.refused("--heldout", directory, text="already failed")

    def test_a_different_heldout_on_recorded_runs_exits_two(self):
        self.change_alpha()
        directory = self.write_heldout(**{"alpha-held": ("alpha", HELD_ALPHA)})
        fp = fr_inputs.fingerprint(self.sb.repo, "HEAD")
        fr_record.append_run(self.sb.repo, fp, "c", "other-digest", "heldout/x.txt", "strict", "PASS")
        self.refused("--heldout", directory, text="different held-out")

    def test_a_changed_session_hook_exits_two(self):
        self.sb.commit("hooks/session-start-skills.sh", "#!/bin/sh\nexit 1\n")
        self.refused(text="session-start-skills.sh")


class ScoreRuns(ScoreBase):
    def counts(self, prompt):
        return [r["result"] for r in self.rows() if r["type"] == "run" and r["prompt"] == prompt]

    def verdicts(self):
        return [r["verdict"] for r in self.rows() if r["type"] == "verdict"]

    def test_a_recorded_pass_exits_zero_with_no_model_call(self):
        self.sb.agent_plan({ALPHA_PROMPT: "alpha"})
        self.assertEqual(self.score().returncode, 0)
        calls = len(self.sb.agent_calls())
        self.assertEqual(calls, 1)
        self.assertEqual(self.score().returncode, 0)
        self.assertEqual(len(self.sb.agent_calls()), calls)
        self.assertEqual(self.verdicts(), ["PASS"])

    def test_a_rerun_of_a_failed_fingerprint_exits_one_with_no_model_call(self):
        self.assertEqual(self.score().returncode, 1)
        calls = len(self.sb.agent_calls())
        self.assertEqual(calls, 2)
        self.assertEqual(self.score().returncode, 1)
        self.assertEqual(len(self.sb.agent_calls()), calls)
        self.assertEqual(self.verdicts(), ["FAIL"])

    def test_a_body_edit_keeps_the_fail(self):
        self.assertEqual(self.score().returncode, 1)
        calls = len(self.sb.agent_calls())
        self.sb.commit(ALPHA, (self.sb.repo / ALPHA).read_text() + "More body.\n")
        self.assertEqual(self.score().returncode, 1)
        self.assertEqual(len(self.sb.agent_calls()), calls)

    def test_strict_prompt_stops_at_four_passes(self):
        self.change_prompt()
        self.sb.agent_plan({EDITED_PROMPT: "alpha"})
        done = self.score()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.counts("committed/alpha-explicit.txt"), ["PASS"] * 4)
        self.assertEqual({r["tier"] for r in self.rows() if r["type"] == "run"}, {"strict"})

    def test_strict_prompt_stops_at_two_failures(self):
        self.change_prompt()
        self.assertEqual(self.score().returncode, 1)
        self.assertEqual(self.counts("committed/alpha-explicit.txt"), ["FAIL", "FAIL"])
        self.assertEqual(self.verdicts(), ["FAIL"])

    def test_a_skill_under_maintainer_skills_is_known_and_scored(self):
        self.sb.commit("maintainer/skills/gamma/SKILL.md", fr_fixture.SKILL % ("gamma", "gamma applies", "gamma"))
        self.assertIn("gamma", fr_inputs.skills_at(self.sb.repo, "HEAD"))
        held = "Held gamma prompt."
        directory = self.write_heldout(**{"gamma-held": ("gamma", held)})
        self.sb.agent_plan({held: "gamma", ALPHA_PROMPT: "alpha"})
        done = self.score("--heldout", directory)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.verdicts(), ["PASS"])

    def test_a_failed_prompt_leaves_its_stream(self):
        self.change_prompt()
        self.assertEqual(self.score().returncode, 1)
        failed = [r for r in self.rows() if r["type"] == "run" and r["result"] == "FAIL"]
        streams = sorted((fr_record.path(self.sb.repo).parent / "final-run-streams").glob("*.jsonl"))
        self.assertEqual(len(failed), 2)
        self.assertEqual(len(streams), len(failed))
        self.assertEqual(len({s.name for s in streams}), len(streams))
        for stream in streams:
            self.assertGreater(stream.stat().st_size, 0)

    def test_neighbour_needs_four_more_passes_after_a_fail(self):
        self.change_beta()
        directory = self.write_heldout(**{"beta-held": ("beta", HELD_BETA)})
        self.sb.agent_plan({HELD_BETA: "beta", ALPHA_PROMPT: ["result", "alpha", "alpha", "alpha", "alpha"]})
        done = self.score("--heldout", directory)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.counts("committed/alpha-explicit.txt"), ["FAIL"] + ["PASS"] * 4)
        self.assertEqual(self.counts("heldout/beta-held.txt"), ["PASS"] * 4)

    def test_the_first_failed_prompt_stops_the_score(self):
        self.change_alpha()
        directory = self.write_heldout(**{"alpha-held": ("alpha", HELD_ALPHA)})
        self.sb.agent_plan({HELD_ALPHA: "alpha"})
        self.assertEqual(self.score("--heldout", directory).returncode, 1)
        self.assertEqual(set(self.prompts_called()), {ALPHA_PROMPT})
        self.assertEqual(self.counts("heldout/alpha-held.txt"), [])

    def test_error_records_no_run_and_exits_three(self):
        self.sb.agent_plan({ALPHA_PROMPT: "error"})
        done = self.score()
        self.assertEqual(done.returncode, 3, done.stderr)
        self.assertEqual(self.rows(), [])

    def test_a_rerun_after_error_resumes_from_recorded_runs(self):
        self.change_alpha()
        directory = self.write_heldout(**{"alpha-held": ("alpha", HELD_ALPHA)})
        self.sb.agent_plan({ALPHA_PROMPT: "alpha", HELD_ALPHA: "error"})
        self.assertEqual(self.score("--heldout", directory).returncode, 3)
        self.assertEqual(self.counts("committed/alpha-explicit.txt"), ["PASS"] * 4)
        self.sb.agent_plan({ALPHA_PROMPT: "alpha", HELD_ALPHA: "alpha"})
        self.assertEqual(self.score("--heldout", directory).returncode, 0)
        self.assertEqual(self.prompts_called().count(ALPHA_PROMPT), 4)
        self.assertEqual(self.counts("heldout/alpha-held.txt"), ["PASS"] * 4)

    def test_a_rebase_that_changes_a_tier_judges_old_results_by_the_new_tier(self):
        self.change_prompt()
        fp = fr_inputs.fingerprint(self.sb.repo, "HEAD")
        fr_record.append_run(self.sb.repo, fp, "old", None, "committed/alpha-explicit.txt", "neighbour", "PASS")
        self.sb.agent_plan({EDITED_PROMPT: "alpha"})
        self.assertEqual(self.score().returncode, 0)
        self.assertEqual(self.prompts_called().count(EDITED_PROMPT), 3)

    def test_score_ignores_a_real_directory_in_the_skills_dir(self):
        self.change_prompt()
        blocker = self.sb.skills_dir / "alpha"
        blocker.mkdir()
        (blocker / "keep.txt").write_text("mine")
        self.sb.agent_plan({EDITED_PROMPT: "alpha"})
        done = self.score()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(sorted(p.name for p in blocker.iterdir()), ["keep.txt"])

    def test_a_leftover_recovery_file_is_ignored_by_score(self):
        self.change_prompt()
        self.recovery_file().parent.mkdir(parents=True, exist_ok=True)
        self.recovery_file().write_text("{}")
        self.sb.agent_plan({EDITED_PROMPT: "alpha"})
        done = self.score()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.recovery_file().read_text(), "{}")

    def test_the_agent_sees_the_export_bootstrap(self):
        self.sb.agent_plan({ALPHA_PROMPT: "alpha"})
        self.assertEqual(self.score().returncode, 0)
        bootstrap = self.sb.agent_calls()[0]["bootstrap"]
        self.assertIn(EXPORT_MARK, bootstrap)
        self.assertTrue(bootstrap.endswith("/skills/using-tl-relay/SKILL.md"))
        self.assertFalse(pathlib.Path(bootstrap).exists())


class Links(ScoreBase):
    def test_a_second_concurrent_score_exits_four(self):
        with mock.patch.dict(os.environ, {"TL_RELAY_HOME": self.sb.env["TL_RELAY_HOME"]}):
            with fr_lock.machine_lock():
                done = self.score()
        self.assertEqual(done.returncode, 4, done.stderr)
        self.assertEqual(self.sb.agent_calls(), [])
        self.assertEqual(self.score().returncode, 1)

    def test_sigterm_removes_the_export_and_exits_three(self):
        proc, call = self.start_sleeping_score()
        export = pathlib.Path(call["bootstrap"])
        self.assertTrue(export.exists())
        proc.send_signal(signal.SIGTERM)
        self.assertEqual(proc.wait(timeout=60), 3)
        self.assertFalse(export.exists())
        self.assertEqual(self.rows(), [])

    def kill_score(self, proc, call):
        proc.kill()
        proc.wait(timeout=30)
        self.reap(call)

    def test_sigkill_leaves_its_temp_files_inside_the_sandbox(self):
        proc, call = self.start_sleeping_score()
        self.kill_score(proc, call)
        temp = pathlib.Path(self.sb.env["TMPDIR"]).resolve()
        self.assertEqual(temp.parent, self.sb.repo.parent)
        self.assertTrue(list(temp.glob("final-run-prompt.*")))
        self.assertTrue(list(temp.glob("trigger.*")))

    def test_a_crash_after_the_verdict_exits_three_and_reuses_the_pass(self):
        self.change_prompt()
        self.sb.agent_plan({EDITED_PROMPT: "alpha"})
        real = fr_record.append_verdict

        def crash(*args, **kwargs):
            real(*args, **kwargs)
            raise RuntimeError("boom")

        with mock.patch.dict(os.environ, self.sb.env, clear=True), \
                mock.patch.object(fr_record, "append_verdict", crash), \
                contextlib.redirect_stderr(io.StringIO()):
            code = fr_score.score(self.sb.repo, None)
        self.assertEqual(code, 3)
        calls = len(self.sb.agent_calls())
        self.assertEqual(self.score().returncode, 0)
        self.assertEqual(len(self.sb.agent_calls()), calls)

    def test_score_without_tl_relay_home_exits_two(self):
        env = {k: v for k, v in self.sb.env.items() if k != "TL_RELAY_HOME"}
        done = self.sb.run("score", env=env)
        self.assertEqual(done.returncode, 2)
        self.assertIn("TL_RELAY_HOME", done.stderr)

    def test_a_heldout_named_like_a_committed_prompt_keeps_its_own_counts(self):
        self.change_alpha()
        directory = self.write_heldout(**{"alpha-explicit": ("alpha", HELD_ALPHA)})
        self.sb.agent_plan({ALPHA_PROMPT: "alpha", HELD_ALPHA: "alpha"})
        self.assertEqual(self.score("--heldout", directory).returncode, 0)
        runs = [(r["prompt"], r["result"]) for r in self.rows() if r["type"] == "run"]
        self.assertEqual(runs.count(("committed/alpha-explicit.txt", "PASS")), 4)
        self.assertEqual(runs.count(("heldout/alpha-explicit.txt", "PASS")), 4)

    def test_a_copied_heldout_keeps_its_digest(self):
        self.change_alpha()
        directory = self.write_heldout(**{"alpha-held": ("alpha", HELD_ALPHA)})
        copy = self.sb.repo.parent / "heldout-copy"
        shutil.copytree(directory, str(copy))
        self.assertEqual(
            fr_score.read_heldout(directory, self.sb.repo)[0], fr_score.read_heldout(copy, self.sb.repo)[0]
        )
        self.sb.agent_plan({ALPHA_PROMPT: "alpha", HELD_ALPHA: "error"})
        self.assertEqual(self.score("--heldout", directory).returncode, 3)
        self.sb.agent_plan({ALPHA_PROMPT: "alpha", HELD_ALPHA: "alpha"})
        done = self.score("--heldout", str(copy))
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_a_fail_with_no_heldout_does_not_block_a_later_score(self):
        self.change_prompt()
        self.assertEqual(self.score().returncode, 1)
        self.change_alpha()
        directory = self.write_heldout(**{"alpha-held": ("alpha", HELD_ALPHA)})
        self.sb.agent_plan({EDITED_PROMPT: "alpha", HELD_ALPHA: "alpha"})
        done = self.score("--heldout", directory)
        self.assertEqual(done.returncode, 0, done.stderr)


class FixRound1(ScoreBase):
    def test_a_malformed_heldout_prompt_exits_two_and_records_nothing(self):
        self.change_alpha()
        self.heldout.mkdir()
        bad = {
            "crlf": b"expect: alpha\r\n%s\n" % HELD_ALPHA.encode(),
            "unknown skill": b"expect: nothing\n%s\n" % HELD_ALPHA.encode(),
            "trailing space": b"expect: alpha \n%s\n" % HELD_ALPHA.encode(),
            "no prompt": b"expect: alpha\n   \n",
            "no newline": b"expect: alpha",
            "no expect": b"%s\n" % HELD_ALPHA.encode(),
        }
        for label, data in bad.items():
            with self.subTest(label):
                (self.heldout / "alpha-held.txt").write_bytes(data)
                done = self.score("--heldout", str(self.heldout))
                self.assertEqual(done.returncode, 2, done.stderr)
                self.assertIn("alpha-held.txt", done.stderr)
                self.assertEqual(self.rows(), [])
                self.assertEqual(self.sb.agent_calls(), [])

    def test_dotfiles_are_not_prompts(self):
        self.change_alpha()
        directory = self.write_heldout(**{"alpha-held": ("alpha", HELD_ALPHA)})
        digest = fr_score.read_heldout(directory, self.sb.repo)[0]
        (self.heldout / "._alpha-held.txt").write_bytes(b"\x00\x05\x16\x07 apple double")
        self.assertEqual(fr_score.read_heldout(directory, self.sb.repo)[0], digest)
        self.sb.commit("skills/tests/prompts/._junk.txt", "junk\n")
        self.assertEqual(set(fr_inputs.prompts_at(self.sb.repo, "HEAD")), {"alpha-explicit.txt"})
        self.sb.agent_plan({ALPHA_PROMPT: "alpha", HELD_ALPHA: "alpha"})
        done = self.score("--heldout", directory)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual({r["prompt"] for r in self.rows() if r["type"] == "run"},
                         {"committed/alpha-explicit.txt", "heldout/alpha-held.txt"})


class FixRound2(ScoreBase):
    GUARDED = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)

    def setUp(self):
        super().setUp()
        self.mask = signal.pthread_sigmask(signal.SIG_BLOCK, [])
        self.addCleanup(signal.pthread_sigmask, signal.SIG_SETMASK, self.mask)
        for sig in self.GUARDED:
            self.addCleanup(signal.signal, sig, signal.getsignal(sig))
            signal.signal(sig, fr_score._handle)
        patcher = mock.patch.dict(os.environ, self.sb.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def score_with_a_signal_during_the_export_cleanup(self, plan):
        self.change_prompt()
        self.sb.agent_plan({EDITED_PROMPT: plan})
        real = shutil.rmtree
        removed = []

        def then_signal(path, *args, **kwargs):
            if EXPORT_MARK in str(path):
                removed.append(pathlib.Path(path))
                os.kill(os.getpid(), signal.SIGTERM)
            return real(path, *args, **kwargs)

        with mock.patch.object(fr_score.shutil, "rmtree", then_signal), \
                contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            code = fr_score.score(self.sb.repo, None)
        self.assertEqual(signal.getsignal(signal.SIGTERM), fr_score._handle)
        self.assertEqual(len(removed), 1)
        self.assertFalse(removed[0].exists())
        return code

    def test_a_signal_during_the_export_cleanup_keeps_a_pass(self):
        self.assertEqual(self.score_with_a_signal_during_the_export_cleanup("alpha"), 0)

    def test_a_signal_during_the_export_cleanup_keeps_a_fail(self):
        self.assertEqual(self.score_with_a_signal_during_the_export_cleanup("beta"), 1)

    def test_a_heldout_expecting_the_bootstrap_exits_two(self):
        self.change_alpha()
        directory = self.write_heldout(**{"boot-held": ("using-tl-relay", HELD_ALPHA)})
        done = self.score("--heldout", directory)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("boot-held.txt", done.stderr)
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.sb.agent_calls(), [])


class FixRound3(ScoreBase):
    RUNNER = (
        "#!/bin/bash\nset -m\nsleep 300 &\nagent=$!\necho \"$agent\" > \"$FAKE_SIDE\"\n"
        "[ -n \"${TL_RELAY_TRIGGER_PGID_FILE:-}\" ] && echo \"$agent\" > \"$TL_RELAY_TRIGGER_PGID_FILE\"\n"
        "trap '' TERM\ntouch \"$FAKE_READY\"\nwait\n"
    )

    def setUp(self):
        super().setUp()
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            self.addCleanup(signal.signal, sig, signal.getsignal(sig))
        patcher = mock.patch.dict(os.environ, self.sb.env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def quiet_score(self):
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            return fr_score.score(self.sb.repo, None)

    def closed_pipe_exit(self, *argv):
        read_end, write_end = os.pipe()
        os.close(read_end)
        try:
            return subprocess.run(self.sb._command(argv), cwd=str(self.sb.repo), env=self.sb.env,
                                  stdout=write_end, stderr=write_end, timeout=120).returncode
        finally:
            os.close(write_end)

    def capture_export(self):
        real, seen = fr_score._export, []

        def export(*args):
            seen.append(real(*args))
            return seen[-1]

        patcher = mock.patch.object(fr_score, "_export", export)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: [shutil.rmtree(str(p), ignore_errors=True) for p in seen])
        return seen

    def test_an_interrupt_kills_an_agent_that_outlives_the_runner(self):
        export = self.sb.home / "fake-export"
        tests = export / "skills" / "tests"
        tests.mkdir(parents=True)
        (tests / "run-triggers.sh").write_text(self.RUNNER)
        side, ready = self.sb.home / "agent.pid", self.sb.home / "agent.ready"
        env = dict(os.environ, FAKE_SIDE=str(side), FAKE_READY=str(ready))

        def communicate(proc, *args, **kwargs):
            for _ in range(200):
                if ready.exists():
                    break
                time.sleep(0.05)
            raise fr_score.Interrupted("interrupted by signal 15")

        with mock.patch.object(fr_score, "_GRACE_SECONDS", 0.2), \
                mock.patch.object(subprocess.Popen, "communicate", communicate), \
                self.assertRaises(fr_score.Interrupted):
            fr_score._run_prompt(export, "committed/only.txt", b"expect: alpha\nprompt\n", env)
        agent = int(side.read_text())
        gone = False
        for _ in range(100):
            try:
                os.killpg(agent, 0)
            except (ProcessLookupError, PermissionError):
                gone = True
                break
            time.sleep(0.05)
        if not gone:
            os.killpg(agent, signal.SIGKILL)
        self.assertTrue(gone)

    def test_a_refusal_with_a_closed_pipe_exits_two(self):
        (self.sb.repo / "untracked.txt").write_text("dirty\n")
        self.assertEqual(self.closed_pipe_exit("score"), 2)

    def test_a_recorded_pass_with_a_closed_pipe_exits_zero(self):
        self.change_prompt()
        self.sb.agent_plan({EDITED_PROMPT: "alpha"})
        self.assertEqual(self.score().returncode, 0)
        self.assertEqual(self.closed_pipe_exit("score"), 0)

    def test_an_escaped_exception_with_a_broken_stderr_exits_three(self):
        class Broken(io.StringIO):
            def write(self, text):
                raise BrokenPipeError()

        with mock.patch.object(fr_score, "_score", side_effect=RuntimeError("boom")), \
                contextlib.redirect_stderr(Broken()):
            code = fr_score.score(self.sb.repo, None)
        self.assertEqual(code, 3)

    def test_an_inherited_ignore_stays_ignored(self):
        self.change_prompt()
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        seen = []

        def run_all(*args):
            seen.append((signal.getsignal(signal.SIGHUP), signal.getsignal(signal.SIGTERM)))
            os.kill(os.getpid(), signal.SIGHUP)
            return 0

        with mock.patch.object(fr_score, "_run_all", run_all):
            self.assertEqual(self.quiet_score(), 0)
        self.assertEqual(seen, [(signal.SIG_IGN, fr_score._handle)])
        self.assertEqual(signal.getsignal(signal.SIGHUP), signal.SIG_IGN)

    def test_only_a_would_block_flock_means_held(self):
        for number in (errno.EWOULDBLOCK, errno.EAGAIN):
            with mock.patch.object(fr_lock.fcntl, "flock", side_effect=OSError(number, "held")):
                with self.assertRaises(fr_lock.LockHeld):
                    with fr_lock.machine_lock():
                        pass
        with mock.patch.object(fr_lock.fcntl, "flock", side_effect=OSError(errno.ENOLCK, "no locks")):
            with self.assertRaises(fr_lock.LockError):
                with fr_lock.machine_lock():
                    pass

    def test_a_flock_failure_makes_score_exit_two(self):
        self.change_prompt()
        with mock.patch.object(fr_lock.fcntl, "flock", side_effect=OSError(errno.ENOLCK, "no locks")):
            self.assertEqual(self.quiet_score(), 2)


class FixRound4(ScoreBase):
    def cli(self, *argv, close=(), broken_pipe=False, ignore=(), **extra_env):
        def child():
            for sig in ignore:
                signal.signal(sig, signal.SIG_IGN)
            for fd in close:
                os.close(fd)

        env = dict(self.sb.env, **extra_env)
        streams = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        for fd, name in ((1, "stdout"), (2, "stderr")):
            if fd in close:
                streams.pop(name)
        read_end, write_end = os.pipe()
        os.close(read_end)
        if broken_pipe:
            streams = {"stdout": write_end, "stderr": write_end}
        try:
            return subprocess.run(self.sb._command(argv), cwd=str(self.sb.repo), env=env, preexec_fn=child,
                                  stdin=subprocess.DEVNULL, timeout=120, **streams).returncode
        finally:
            os.close(write_end)

    def pass_once(self):
        self.change_prompt()
        self.sb.agent_plan({EDITED_PROMPT: "alpha"})
        self.assertEqual(self.score().returncode, 0)

    def test_a_prompt_finishes_promptly_when_sigterm_is_inherited_as_ignored(self):
        self.change_prompt()
        self.sb.agent_plan({EDITED_PROMPT: "alpha"})
        started = time.time()
        code = self.cli("score", ignore=(signal.SIGTERM,), TL_RELAY_TRIGGER_TIMEOUT="10")
        self.assertEqual(code, 0)
        self.assertLess(time.time() - started, 40)

    def test_a_refusal_with_a_closed_stream_exits_two(self):
        (self.sb.repo / "untracked.txt").write_text("dirty\n")
        for fd in (1, 2):
            with self.subTest(fd=fd):
                self.assertEqual(self.cli("score", close=(fd,)), 2)

    def test_a_recorded_pass_with_closed_stdout_exits_zero(self):
        self.pass_once()
        self.assertEqual(self.cli("score", close=(1,)), 0)
        self.assertEqual(self.cli("score", close=(1,), PYTHONUNBUFFERED="1"), 0)

    def test_a_recorded_pass_with_a_broken_pipe_exits_zero_unbuffered(self):
        self.pass_once()
        self.assertEqual(self.cli("score", broken_pipe=True, PYTHONUNBUFFERED="1"), 0)

    def test_a_passing_prompt_with_a_broken_stderr_is_recorded(self):
        class Broken(io.StringIO):
            def write(self, text):
                raise BrokenPipeError()

        self.change_prompt()
        self.sb.agent_plan({EDITED_PROMPT: "alpha"})
        with mock.patch.dict(os.environ, self.sb.env, clear=True), \
                contextlib.redirect_stderr(Broken()), contextlib.redirect_stdout(io.StringIO()):
            code = fr_score.score(self.sb.repo, None)
        self.assertEqual(code, 0)
        self.assertTrue([r for r in self.rows() if r["type"] == "run" and r["result"] == "PASS"])

    def test_a_run_with_closed_stderr_records_its_pass(self):
        self.change_prompt()
        self.sb.agent_plan({EDITED_PROMPT: "alpha"})
        self.assertEqual(self.cli("score", close=(2,)), 0)
        self.assertTrue([r for r in self.rows() if r["type"] == "run" and r["result"] == "PASS"])

    def test_stop_group_skips_an_empty_or_missing_pgid_file(self):
        empty = self.sb.home / "empty.pgid"
        empty.write_text("")
        for path in (empty, self.sb.home / "missing.pgid"):
            with self.subTest(path=path.name), mock.patch.object(fr_score, "_kill_group") as kill:
                fr_score._stop_group(mock.Mock(pid=4242), str(path))
                sent = [c.args for c in kill.call_args_list if c.args[0] is not None]
                self.assertEqual(sent, [(4242, signal.SIGTERM)])


class Tune(ScoreBase):
    WORKING_PROMPT = "Working tree alpha prompt."

    def edit_working_prompt(self, name="alpha-explicit", skill="alpha", text=None):
        path = self.sb.repo / "skills" / "tests" / "prompts" / (name + ".txt")
        path.write_text("expect: %s\n%s\n" % (skill, text or self.WORKING_PROMPT))

    def tune(self, *extra, env=None):
        return self.sb.run("tune", "alpha", *extra, env=env)

    def test_tune_reads_the_working_tree(self):
        self.edit_working_prompt()
        self.sb.agent_plan({self.WORKING_PROMPT: "alpha"})
        done = self.tune("--runs", "2")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.prompts_called(), [self.WORKING_PROMPT] * 2)
        call = self.sb.agent_calls()[0]
        self.assertEqual(call["bootstrap"], str(self.sb.repo / "skills" / "using-tl-relay" / "SKILL.md"))

    def test_tune_runs_while_a_score_holds_the_lock(self):
        self.sb.agent_plan({ALPHA_PROMPT: "alpha"})
        with mock.patch.dict(os.environ, {"TL_RELAY_HOME": self.sb.env["TL_RELAY_HOME"]}):
            with fr_lock.machine_lock():
                done = self.tune("--runs", "1")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.prompts_called(), [ALPHA_PROMPT])

    def test_a_leftover_recovery_file_is_ignored_by_tune(self):
        self.recovery_file().parent.mkdir(parents=True, exist_ok=True)
        self.recovery_file().write_text("{}")
        self.sb.agent_plan({ALPHA_PROMPT: "alpha"})
        done = self.tune("--runs", "1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.recovery_file().read_text(), "{}")

    def test_tune_runs_each_prompt_the_requested_times(self):
        self.edit_working_prompt("alpha-second", text="Second alpha prompt.")
        (self.sb.repo / "skills" / "tests" / "prompts" / ".alpha-hidden.txt").write_text("expect: alpha\nHidden.\n")
        self.sb.agent_plan({ALPHA_PROMPT: "alpha", "Second alpha prompt.": ["alpha", "result", "alpha"]})
        done = self.tune("--runs", "3")
        self.assertEqual(done.returncode, 1, done.stderr)
        called = self.prompts_called()
        self.assertEqual(called.count(ALPHA_PROMPT), 3)
        self.assertEqual(called.count("Second alpha prompt."), 3)
        self.assertEqual(len(called), 6)
        self.assertIn("alpha-explicit.txt 3/3", done.stdout)
        self.assertIn("alpha-second.txt 2/3", done.stdout)

    def test_tune_defaults_to_five_runs(self):
        self.sb.agent_plan({ALPHA_PROMPT: "alpha"})
        self.assertEqual(self.tune().returncode, 0)
        self.assertEqual(len(self.sb.agent_calls()), 5)

    def test_tune_writes_nothing_to_the_record(self):
        self.sb.agent_plan({ALPHA_PROMPT: "alpha"})
        self.assertEqual(self.tune("--runs", "2").returncode, 0)
        self.assertEqual(self.rows(), [])
        self.sb.agent_plan({ALPHA_PROMPT: "result"})
        self.assertEqual(self.tune("--runs", "2").returncode, 1)
        self.assertEqual(self.rows(), [])

    def test_a_tune_failure_does_not_block_a_later_score(self):
        self.sb.agent_plan({ALPHA_PROMPT: "result"})
        self.assertEqual(self.tune("--runs", "2").returncode, 1)
        self.sb.agent_plan({ALPHA_PROMPT: "alpha"})
        done = self.score()
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_tune_refuses_a_heldout_argument(self):
        directory = self.write_heldout(**{"alpha-held": ("alpha", HELD_ALPHA)})
        done = self.tune("--heldout", directory)
        self.assertEqual(done.returncode, 2)
        self.assertEqual(self.sb.agent_calls(), [])

    def test_tune_refuses_a_prompts_override(self):
        env = dict(self.sb.env, TL_RELAY_TRIGGER_PROMPTS=str(self.sb.home))
        done = self.tune(env=env)
        self.assertEqual(done.returncode, 2)
        self.assertIn("TL_RELAY_TRIGGER_PROMPTS", done.stderr)
        self.assertEqual(self.sb.agent_calls(), [])

    def test_tune_without_tl_relay_home_exits_two(self):
        env = {k: v for k, v in self.sb.env.items() if k != "TL_RELAY_HOME"}
        done = self.tune(env=env)
        self.assertEqual(done.returncode, 2)
        self.assertIn("TL_RELAY_HOME", done.stderr)

    def test_tune_of_an_unknown_skill_or_one_without_prompts_exits_two(self):
        for name in ("missing", "beta"):
            with self.subTest(skill=name):
                done = self.sb.run("tune", name)
                self.assertEqual(done.returncode, 2)
                self.assertEqual(self.sb.agent_calls(), [])

    def test_tune_rejects_a_non_positive_run_count(self):
        self.assertEqual(self.tune("--runs", "0").returncode, 2)
        self.assertEqual(self.sb.agent_calls(), [])

    def test_tune_matches_the_longest_skill_name_for_a_prompt(self):
        self.sb.commit("skills/alpha-beta/SKILL.md", fr_fixture.SKILL % ("alpha-beta", "ab applies", "ab"))
        self.sb.commit("skills/tests/prompts/alpha-beta-explicit.txt", "expect: alpha-beta\nRun alpha-beta.\n")
        self.sb.agent_plan({ALPHA_PROMPT: "alpha"})
        self.assertEqual(self.tune("--runs", "1").returncode, 0)
        self.assertEqual(self.prompts_called(), [ALPHA_PROMPT])

    def test_tune_exits_three_on_an_error_run(self):
        self.sb.agent_plan({ALPHA_PROMPT: "error"})
        done = self.tune("--runs", "2")
        self.assertEqual(done.returncode, 3, done.stderr)
        self.assertEqual(len(self.sb.agent_calls()), 1)


class TuneFixRound1(ScoreBase):
    def tune(self, *extra, env=None):
        return self.sb.run("tune", "alpha", *extra, env=env)

    def test_a_broken_working_tree_skill_exits_two_before_the_run(self):
        for name in ("alpha", "beta"):
            with self.subTest(skill=name):
                path = self.sb.repo / "skills" / name / "SKILL.md"
                original = path.read_text()
                self.addCleanup(path.write_text, original)
                for broken in ("no frontmatter here\n", "---\nname: %s\n---\nBody\n" % name):
                    path.write_text(broken)
                    done = self.tune("--runs", "1")
                    self.assertEqual(done.returncode, 2, done.stderr)
                    self.assertEqual(self.sb.agent_calls(), [])
                path.write_text(original)


ZERO = "0" * 40
LEAK = "LEAK" + "WORD"
BLOCKED = re.compile(r"blocked by rule [1-7]: .+\. (Run|Next): \S")


class Check(unittest.TestCase):
    def setUp(self):
        self.sb = fr_fixture.Sandbox()
        self.addCleanup(self.sb.cleanup)
        self.sb.branch("feature")
        self.patterns(["LEAK[W]ORD"])

    def patterns(self, names):
        home = pathlib.Path(self.sb.env["TL_RELAY_HOME"])
        home.mkdir(parents=True, exist_ok=True)
        body = "neutrality:\n  patterns:\n" + "".join("    - %s\n" % n for n in names)
        (home / "tl-relay.yaml").write_text(body if names else "neutrality:\n  patterns: []\n")

    def head(self):
        return self.sb._git("rev-parse", "HEAD").stdout.strip()

    def check(self, sha=None, local_ref="refs/heads/feature", remote_ref="refs/heads/feature", line=None):
        text = line if line is not None else "%s %s %s %s\n" % (local_ref, sha or self.head(), remote_ref, ZERO)
        return subprocess.run(
            self.sb._command(["check", "origin", "url"]), input=text, cwd=str(self.sb.repo),
            env=self.sb.env, capture_output=True, text=True,
        )

    def blocked(self, done, rule, code=1):
        self.assertEqual(done.returncode, code, done.stdout + done.stderr)
        self.assertIn("blocked by rule %s:" % rule, done.stderr)
        self.assertRegex(done.stderr, BLOCKED)

    def allowed(self, done):
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def record(self, verdict):
        fp = fr_inputs.fingerprint(self.sb.repo, "HEAD")
        fr_record.append_verdict(self.sb.repo, fp, self.head(), None, verdict)

    def change_alpha(self):
        self.sb.commit(ALPHA, fr_fixture.SKILL % ("alpha", "alpha changed", "alpha"))

    def test_a_branch_deletion_passes(self):
        self.allowed(self.check(line="(delete) %s refs/heads/feature %s\n" % (ZERO, self.head())))

    def test_a_tag_passes(self):
        self.change_alpha()
        self.allowed(self.check(local_ref="refs/tags/v1", remote_ref="refs/tags/v1"))

    def test_a_missing_origin_main_blocks(self):
        self.sb._git("update-ref", "-d", "refs/remotes/origin/main")
        self.sb.commit("skills/alpha/note.md", "note\n")
        self.blocked(self.check(), 2)

    def test_a_range_outside_skills_and_the_hook_passes(self):
        self.sb.commit("docs/plain.md", LEAK + "\n")
        self.patterns([])
        self.allowed(self.check())

    def test_a_rename_out_of_skills_is_gated(self):
        self.sb._git("mv", "skills/tests/prompts/alpha-explicit.txt", "docs-prompt.txt")
        self.sb._git("commit", "-q", "-m", "move prompt out")
        self.blocked(self.check(), 5)

    def test_a_non_ascii_path_under_skills_is_gated(self):
        self.sb.commit("skills/alpha/caf\u00e9.md", LEAK + "\n")
        self.blocked(self.check(), 7)

    def test_an_edit_made_only_in_a_merge_commit_is_gated(self):
        self.sb.commit("docs/one.md", "one\n")
        side = self.head()
        self.sb._git("checkout", "-q", "-b", "side", "main")
        self.sb.commit("docs/two.md", "two\n")
        self.sb._git("checkout", "-q", "feature")
        self.sb._git("merge", "-q", "--no-ff", "--no-commit", "side")
        self.sb._write("skills/alpha/evil.md", LEAK + "\n")
        self.sb._git("add", "-A")
        self.sb._git("commit", "-q", "-m", "merge")
        self.assertNotEqual(self.head(), side)
        self.blocked(self.check(), 7)

    def test_a_tag_pushed_to_a_branch_ref_is_gated(self):
        self.sb.commit("skills/alpha/note.md", LEAK + "\n")
        self.sb._git("tag", "-a", "-m", "tag", "t1")
        tag = self.sb._git("rev-parse", "t1").stdout.strip()
        self.assertNotEqual(tag, self.head())
        self.blocked(self.check(sha=tag, local_ref="refs/tags/t1", remote_ref="refs/heads/other"), 7)

    def test_an_overlap_crash_blocks(self):
        self.sb.commit("skills/tests/overlap.py", "import sys\nsys.exit(3)\n")
        self.blocked(self.check(), 6)

    def test_an_overlap_fail_on_the_pushed_tip_blocks(self):
        self.sb.commit("skills/tests/overlap.py", "print('FAIL 90% 9/10 run=4 alpha/SKILL.md')\n")
        self.blocked(self.check(), 6)

    def test_an_add_then_remove_under_skills_still_scans_neutrality(self):
        self.sb.commit("skills/alpha/leak.md", LEAK + "\n")
        self.sb._git("rm", "-q", "skills/alpha/leak.md")
        self.sb._git("commit", "-q", "-m", "remove")
        self.blocked(self.check(), 7)

    def test_a_leak_in_an_earlier_commit_blocks(self):
        self.sb.commit("docs/leak.md", LEAK + "\n")
        self.sb.commit("skills/alpha/note.md", "note\n")
        self.sb._git("rm", "-q", "docs/leak.md")
        self.sb._git("commit", "-q", "-m", "remove")
        self.blocked(self.check(), 7)

    def test_a_fingerprint_equal_to_the_merge_base_passes_the_trigger_check(self):
        self.sb.commit("skills/alpha/note.md", "note\n")
        self.allowed(self.check())

    def test_a_fingerprint_equal_to_origin_main_passes_the_trigger_check(self):
        text = fr_fixture.SKILL % ("alpha", "alpha changed", "alpha")
        self.sb._git("checkout", "-q", "main")
        self.sb.commit(ALPHA, text)
        self.sb._git("push", "-q", "origin", "main")
        self.sb._git("checkout", "-q", "feature")
        self.sb.commit(ALPHA, text)
        self.sb.commit("skills/alpha/note.md", "note\n")
        self.assertNotEqual(self.sb._git("merge-base", "HEAD", "origin/main").stdout.strip(), self.head())
        self.allowed(self.check())

    def test_changed_inputs_with_no_pass_block(self):
        self.change_alpha()
        self.blocked(self.check(), 5)

    def test_changed_inputs_with_a_pass_are_allowed(self):
        self.change_alpha()
        self.record("PASS")
        self.allowed(self.check())

    def test_a_pass_followed_by_a_fail_blocks(self):
        self.change_alpha()
        self.record("PASS")
        self.record("FAIL")
        self.blocked(self.check(), 5)

    def test_a_changed_session_hook_blocks(self):
        self.sb.commit("hooks/session-start-skills.sh", "#!/bin/sh\nexit 1\n")
        self.record("PASS")
        done = self.check()
        self.blocked(done, 5)
        self.assertIn(
            "Next: stop and ask the operator, who decides whether to push with --no-verify "
            "and measure after the merge",
            done.stderr,
        )
        self.assertNotIn("Run: git push", done.stderr)

    def test_empty_neutral_patterns_block(self):
        self.sb.commit("skills/alpha/note.md", "note\n")
        self.patterns([])
        self.blocked(self.check(), 7)

    def test_a_malformed_record_blocks(self):
        self.change_alpha()
        target = fr_record.path(self.sb.repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("not json\n")
        self.blocked(self.check(), 5, code=2)

    def test_a_leftover_recovery_file_does_not_block_a_push(self):
        self.change_alpha()
        self.record("PASS")
        recovery = pathlib.Path(self.sb.env["TL_RELAY_HOME"]) / "locks" / "final-run-links.json"
        recovery.parent.mkdir(parents=True, exist_ok=True)
        recovery.write_text("{}")
        self.allowed(self.check())
        self.assertTrue(recovery.exists())

    def test_unrelated_history_blocks(self):
        self.sb._git("checkout", "-q", "--orphan", "orphan")
        self.sb.commit("skills/alpha/note.md", "note\n")
        self.blocked(self.check(), 2)

    def test_check_never_calls_the_agent(self):
        self.change_alpha()
        self.check()
        self.record("PASS")
        self.check()
        self.assertEqual(self.sb.agent_calls(), [])

    def test_each_block_names_its_rule_and_command(self):
        self.change_alpha()
        done = self.check()
        self.assertRegex(done.stderr, BLOCKED)
        self.assertIn("final_run.py", done.stderr)
        self.assertIn("score --heldout", done.stderr)

    def test_a_malformed_update_line_blocks(self):
        self.assertEqual(self.check(line="refs/heads/feature\n").returncode, 1)


    def stub_gpg(self):
        stub = self.sb.repo.parent / "gpg-stub"
        stub.write_text(
            "#!/bin/sh\n"
            "case \"$*\" in\n"
            "  *--verify*) echo 'gpg: Good signature from fake' >&2; echo '[GNUPG:] GOODSIG 1 fake';;\n"
            "  *) cat >/dev/null; echo '[GNUPG:] SIG_CREATED D 1 8 00 1 1 00 F' >&2;"
            " printf -- '-----BEGIN PGP SIGNATURE-----\\nfake\\n-----END PGP SIGNATURE-----\\n';;\n"
            "esac\n"
        )
        stub.chmod(0o755)
        self.sb._git("config", "gpg.program", str(stub))

    def test_a_signed_leak_is_blocked_with_show_signature_on(self):
        self.stub_gpg()
        self.sb._git("config", "log.showSignature", "true")
        self.sb._write("skills/alpha/note.md", LEAK + "\n")
        self.sb._git("add", "-A")
        self.sb._git("commit", "-q", "-S", "-m", "signed")
        self.blocked(self.check(), 7)

    def test_a_merge_edit_is_gated_with_diff_merges_off(self):
        self.sb._git("config", "log.diffMerges", "off")
        self.test_an_edit_made_only_in_a_merge_commit_is_gated()

    def test_a_changed_hook_still_reports_a_leak_first(self):
        self.sb.commit("hooks/session-start-skills.sh", "#!/bin/sh\nexit 1\n")
        self.sb.commit("skills/alpha/note.md", LEAK + "\n")
        done = self.check()
        self.blocked(done, 7)
        self.assertNotIn("--no-verify", done.stderr)

    def test_printed_commands_carry_the_home_and_quote_paths(self):
        spaced = self.sb.repo.parent / "tl relay home"
        self.sb.env["TL_RELAY_HOME"] = str(spaced)
        self.patterns([])
        self.change_alpha()
        done = self.check()
        self.assertIn("TL_RELAY_HOME='%s' " % spaced, done.stderr)
        self.record("PASS")
        self.sb.commit("skills/alpha/leak.md", LEAK + "\n")
        self.patterns(["LEAK[W]ORD"])
        done = self.check()
        self.assertIn("TL_RELAY_HOME='%s' " % spaced, done.stderr)

    def test_a_custom_ref_is_gated(self):
        self.sb.commit("skills/alpha/note.md", LEAK + "\n")
        self.blocked(self.check(remote_ref="refs/wip/x"), 7)

    def test_an_unset_home_still_allows_a_deletion_and_a_docs_push(self):
        del self.sb.env["TL_RELAY_HOME"]
        self.sb.commit("docs/plain.md", "plain\n")
        self.allowed(self.check())
        self.allowed(self.check(line="(delete) %s refs/heads/feature %s\n" % (ZERO, self.head())))

    def test_an_unset_home_blocks_a_gated_push_with_a_message(self):
        del self.sb.env["TL_RELAY_HOME"]
        self.sb.commit("skills/alpha/note.md", "note\n")
        done = self.check()
        self.blocked(done, 5)
        self.assertIn("TL_RELAY_HOME is not set", done.stderr)

    def test_a_hook_change_on_one_ref_does_not_hide_a_leak_on_another(self):
        self.sb.commit("hooks/session-start-skills.sh", "#!/bin/sh\nexit 1\n")
        hook = self.head()
        self.sb._git("checkout", "-q", "-b", "leaky", "main")
        self.sb.commit("skills/alpha/note.md", LEAK + "\n")
        leaky = self.head()
        text = "refs/heads/feature %s refs/heads/feature %s\nrefs/heads/leaky %s refs/heads/leaky %s\n" % (
            hook, ZERO, leaky, ZERO)
        done = self.check(line=text)
        self.blocked(done, 7)
        self.assertNotIn("--no-verify", done.stderr)

    def test_a_gitlink_is_gated_with_ignore_submodules_all(self):
        self.sb._git("config", "diff.ignoreSubmodules", "all")
        self.sb._git("update-index", "--add", "--cacheinfo", "160000,%s,skills/alpha/sub" % self.head())
        self.sb._git("commit", "-q", "-m", LEAK)
        self.blocked(self.check(), 7)

    def test_unrelated_history_does_not_suggest_a_fetch(self):
        self.sb._git("checkout", "-q", "--orphan", "orphan")
        self.sb.commit("skills/alpha/note.md", "note\n")
        self.assertNotIn("git fetch", self.check().stderr)


class RealPush(unittest.TestCase):
    patterns = Check.patterns
    head = Check.head
    record = Check.record
    change_alpha = Check.change_alpha

    def setUp(self):
        self.sb = fr_fixture.Sandbox()
        self.addCleanup(self.sb.cleanup)
        self.sb.branch("feature")
        self.patterns(["LEAK[W]ORD"])
        self.sb.install_hook()

    def push(self, *args, **kwargs):
        return self.sb.push("push", *args, **kwargs)

    def remote_has(self, ref):
        done = subprocess.run(
            ["git", "--git-dir", str(self.sb.remote), "rev-parse", "--verify", "-q", ref],
            capture_output=True, env=self.sb.env)
        return done.returncode == 0

    def blocked(self, done, rule):
        self.assertNotEqual(done.returncode, 0, done.stderr)
        self.assertIn("blocked by rule %d:" % rule, done.stderr)
        self.assertFalse(self.remote_has("refs/heads/feature"))

    def landed(self, done, ref="refs/heads/feature"):
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(self.remote_has(ref))

    def test_a_push_with_no_pass_is_blocked(self):
        self.change_alpha()
        self.blocked(self.push("origin", "feature"), 5)

    def test_a_push_after_a_pass_lands(self):
        self.change_alpha()
        self.record("PASS")
        self.landed(self.push("origin", "feature"))

    def test_a_branch_that_adds_then_removes_a_leak_is_blocked(self):
        self.sb.commit("skills/alpha/leak.md", LEAK + "\n")
        self.sb._git("rm", "-q", "skills/alpha/leak.md")
        self.sb._git("commit", "-q", "-m", "remove")
        self.blocked(self.push("origin", "feature"), 7)

    def test_a_push_from_a_linked_worktree_reads_the_shared_record(self):
        self.change_alpha()
        self.record("PASS")
        linked = self.sb.repo.parent / "linked"
        self.sb._git("worktree", "add", "-q", "-b", "other", str(linked), "feature")
        self.landed(self.push("origin", "other", cwd=linked), "refs/heads/other")

    def test_a_push_without_tl_relay_home_uses_the_rendered_home(self):
        self.change_alpha()
        self.record("PASS")
        env = {k: v for k, v in self.sb.env.items() if k != "TL_RELAY_HOME"}
        self.landed(self.push("origin", "feature", env=env))

    def test_no_verify_bypasses_the_hook(self):
        self.change_alpha()
        self.landed(self.push("--no-verify", "origin", "feature"))

    def test_a_real_branch_deletion_passes(self):
        self.sb.commit("docs/plain.md", "plain\n")
        self.landed(self.push("origin", "feature"))
        done = self.push("origin", "--delete", "feature")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse(self.remote_has("refs/heads/feature"))

    def test_a_real_tag_push_passes(self):
        self.change_alpha()
        self.sb._git("tag", "v1")
        self.landed(self.push("origin", "v1"), "refs/tags/v1")

    def test_a_real_push_without_origin_main_is_blocked(self):
        self.sb._git("update-ref", "-d", "refs/remotes/origin/main")
        self.sb.commit("skills/alpha/note.md", "note\n")
        self.blocked(self.push("origin", "feature"), 2)

    def test_a_real_push_outside_skills_passes(self):
        self.sb.commit("docs/plain.md", LEAK + "\n")
        self.landed(self.push("origin", "feature"))

    def test_a_real_push_with_the_merge_base_fingerprint_passes(self):
        self.sb.commit("skills/alpha/note.md", "note\n")
        self.landed(self.push("origin", "feature"))

    def test_a_real_push_with_an_overlap_fail_is_blocked(self):
        self.sb.commit("skills/tests/overlap.py", "print('FAIL 90% 9/10 run=4 alpha/SKILL.md')\n")
        self.blocked(self.push("origin", "feature"), 6)

    def test_a_push_with_the_script_missing_names_the_remedy(self):
        self.change_alpha()
        (self.sb.repo / "maintainer" / "skills" / "write-skill" / "scripts" / "final_run.py").unlink()
        done = self.push("origin", "feature")
        self.assertNotEqual(done.returncode, 0)
        lines = [l for l in done.stderr.splitlines() if "final_run.py" in l]
        self.assertEqual(len(lines), 1, done.stderr)
        self.assertIn("or stop and ask the operator, who decides on --no-verify", lines[0])
        self.assertNotIn("run git push", lines[0])
        self.assertIn("install --git-hook", lines[0])
        self.assertFalse(self.remote_has("refs/heads/feature"))

    def test_a_push_without_sdlc_passes_unless_it_changes_skills(self):
        self.sb.commit("docs/plain.md", "plain\n")
        self.landed(self.push("origin", "feature"))
        (self.sb.repo / "maintainer" / "sdlc.py").unlink()
        self.sb.commit("docs/more.md", "more\n")
        self.landed(self.push("origin", "feature"))
        done = self.push("origin", "--delete", "feature")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.sb.commit("skills/alpha/note.md", "note\n")
        self.blocked(self.push("origin", "feature"), 7)


class ScoreGuards(ScoreBase):
    def refused(self, done, text=None):
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        if text:
            self.assertIn(text, done.stderr)
        self.assertEqual(self.sb.agent_calls(), [])

    def pass_all(self):
        self.sb.agent_plan({ALPHA_PROMPT: "alpha", EDITED_PROMPT: "alpha", HELD_ALPHA: "alpha"})

    def test_score_ignores_a_local_branch_named_origin_main(self):
        self.change_alpha()
        self.sb._git("branch", "origin/main")
        self.refused(self.score(), "--heldout")

    def test_score_needs_the_remote_tracking_ref(self):
        self.sb._git("branch", "origin/main")
        self.sb._git("update-ref", "-d", "refs/remotes/origin/main")
        self.refused(self.score(), "origin/main")

    def test_score_and_tune_run_with_any_config_dir(self):
        other = self.sb.home / "other-config"
        other.mkdir()
        self.sb.agent_plan({ALPHA_PROMPT: "alpha"})
        for value in (str(other), ""):
            env = dict(self.sb.env, CLAUDE_CONFIG_DIR=value)
            for argv in (("score",), ("tune", "alpha", "--runs", "1")):
                with self.subTest(config=value, argv=argv):
                    done = self.sb.run(*argv, env=env)
                    self.assertEqual(done.returncode, 0, done.stderr)

    def test_a_home_without_config_exits_two_and_creates_nothing(self):
        bare = self.sb.home / "bare-home"
        bare.mkdir()
        env = dict(self.sb.env, TL_RELAY_HOME=str(bare))
        for argv in (("score",), ("tune", "alpha", "--runs", "1")):
            self.refused(self.sb.run(*argv, env=env), "tl-relay.yaml")
        self.change_alpha()
        sha = self.sb._git("rev-parse", "HEAD").stdout.strip()
        done = subprocess.run(
            self.sb._command(["check", "origin", "url"]), cwd=str(self.sb.repo), env=env, capture_output=True,
            text=True, input="refs/heads/feature %s refs/heads/feature %s\n" % (sha, ZERO),
        )
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertEqual(list(bare.iterdir()), [])

    def test_lock_accepts_a_legacy_home_file(self):
        legacy = self.sb.home / "legacy-home"
        legacy.mkdir()
        (legacy / "ai-sdlc.yaml").write_text("neutrality:\n  patterns: []\n")
        with mock.patch.dict(os.environ, {"TL_RELAY_HOME": str(legacy)}):
            self.assertEqual(fr_lock._home(), legacy)

    def test_a_when_to_use_change_needs_a_heldout(self):
        text = "---\nname: alpha\ndescription: Use when alpha applies.\nwhen_to_use: later\n---\n\nBody of alpha.\n"
        self.sb.commit(ALPHA, text)
        self.refused(self.score(), "--heldout")
        self.pass_all()
        directory = self.write_heldout(**{"alpha-held": ("alpha", HELD_ALPHA)})
        self.assertEqual(self.score("--heldout", directory).returncode, 0)

    def test_a_heldout_is_refused_after_a_description_change(self):
        self.change_alpha()
        self.pass_all()
        directory = self.write_heldout(**{"alpha-held": ("alpha", HELD_ALPHA)})
        self.assertEqual(self.score("--heldout", directory).returncode, 0)
        calls = len(self.sb.agent_calls())
        self.sb.commit(ALPHA, fr_fixture.SKILL % ("alpha", "alpha changed again", "alpha"))
        done = self.score("--heldout", directory)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("fresh", done.stderr)
        self.assertEqual(len(self.sb.agent_calls()), calls)

    def test_a_heldout_is_refused_when_its_recorded_commit_is_gone(self):
        self.change_alpha()
        self.pass_all()
        directory = self.write_heldout(**{"alpha-held": ("alpha", HELD_ALPHA)})
        digest, _ = fr_score.read_heldout(directory, self.sb.repo)
        fr_record.append_verdict(self.sb.repo, "other", "0" * 40, digest, "PASS")
        done = self.score("--heldout", directory)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertEqual(self.sb.agent_calls(), [])

    def test_a_heldout_survives_a_prompt_change_with_the_same_identity(self):
        self.change_alpha()
        self.pass_all()
        directory = self.write_heldout(**{"alpha-held": ("alpha", HELD_ALPHA)})
        self.assertEqual(self.score("--heldout", directory).returncode, 0)
        self.change_prompt()
        done = self.score("--heldout", directory)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_score_refuses_a_hook_that_names_another_home(self):
        other = self.sb.home / "other-home"
        other.mkdir()
        (other / "tl-relay.yaml").write_text("neutrality:\n  patterns: []\n")
        self.sb.install_hook(home=other)
        self.refused(self.score(), "names home")

    def test_score_refuses_a_legacy_hook_that_names_another_home(self):
        other = self.sb.home / "other-home"
        other.mkdir()
        (other / "tl-relay.yaml").write_text("neutrality:\n  patterns: []\n")
        self.sb.install_hook(home=other)
        hook = self.sb.repo / ".git" / "hooks" / "pre-push"
        hook.write_text(hook.read_text().replace("# tl-relay pre-push hook", "# ai-sdlc pre-push hook"))
        self.assertIn("# ai-sdlc pre-push hook", hook.read_text())
        self.refused(self.score(), "names home")

    def test_score_accepts_a_hook_that_names_this_home(self):
        self.sb.install_hook()
        self.sb.agent_plan({ALPHA_PROMPT: "alpha"})
        self.assertEqual(self.score().returncode, 0)

    def test_score_ignores_a_foreign_hook(self):
        hook = self.sb.repo / ".git" / "hooks" / "pre-push"
        hook.write_text("#!/bin/sh\nexit 0\n")
        self.sb.agent_plan({ALPHA_PROMPT: "alpha"})
        self.assertEqual(self.score().returncode, 0)


class FrontmatterSpelling(unittest.TestCase):
    def test_alternate_spellings_of_a_trigger_key_are_refused(self):
        for key in ("name", "description", "when_to_use", "disable-model-invocation"):
            for line in ('"%s": x', "'%s': x", "%s : x", "%s\t: x", "? %s", "? %s: x", '? "%s"'):
                with self.subTest(key=key, line=line):
                    with self.assertRaises(fr_inputs.InputError):
                        fr_inputs.frontmatter("---\nother: y\n" + line % key + "\n---\n")

    def test_plain_and_indented_lines_stay_valid(self):
        text = "---\nname: a\ndescription: >\n  description : inside\n  ? name\nother: y\n---\n"
        self.assertEqual(fr_inputs.frontmatter(text)["name"], "a")

    def test_the_extra_trigger_keys_are_read(self):
        fields = fr_inputs.frontmatter(
            "---\nname: a\ndescription: d\nwhen_to_use: w\ndisable-model-invocation: true\n---\n")
        self.assertEqual(fields["when_to_use"], "w")
        self.assertEqual(fields["disable-model-invocation"], "true")


class FingerprintKeys(ScoreBase):
    def changed_by(self, extra):
        before = fr_inputs.fingerprint(self.sb.repo, "HEAD")
        self.sb.commit(ALPHA, "---\nname: alpha\ndescription: Use when alpha applies.\n%s---\n\nBody of alpha.\n" % extra)
        return before != fr_inputs.fingerprint(self.sb.repo, "HEAD")

    def test_when_to_use_changes_the_fingerprint(self):
        self.assertTrue(self.changed_by("when_to_use: later\n"))

    def test_disable_model_invocation_changes_the_fingerprint(self):
        self.assertTrue(self.changed_by("disable-model-invocation: true\n"))


class UnmergedRefs(unittest.TestCase):
    setUp = Check.setUp
    patterns = Check.patterns
    head = Check.head
    check = Check.check
    blocked = Check.blocked
    allowed = Check.allowed
    change_alpha = Check.change_alpha

    def tag_line(self, sha):
        return "refs/tags/v1 %s refs/tags/v1 %s\n" % (sha, ZERO)

    def test_a_tag_with_a_leak_is_blocked(self):
        self.sb.commit("docs/leak.md", LEAK + "\n")
        self.blocked(self.check(line=self.tag_line(self.head())), 7)

    def test_an_annotated_tag_is_peeled(self):
        self.sb.commit("docs/leak.md", LEAK + "\n")
        self.sb._git("tag", "-a", "-m", "tag", "v1")
        tag = self.sb._git("rev-parse", "v1").stdout.strip()
        self.blocked(self.check(line=self.tag_line(tag)), 7)

    def test_a_clean_unscored_tag_passes(self):
        self.change_alpha()
        self.allowed(self.check(line=self.tag_line(self.head())))

    def test_a_tag_on_main_needs_no_scan(self):
        del self.sb.env["TL_RELAY_HOME"]
        main = self.sb._git("rev-parse", "refs/remotes/origin/main").stdout.strip()
        self.allowed(self.check(line=self.tag_line(main)))

    def test_a_tag_of_a_blob_is_blocked(self):
        blob = self.sb._git("rev-parse", "HEAD:hooks/session-start-skills.sh").stdout.strip()
        self.blocked(self.check(line=self.tag_line(blob)), 7)

    def test_a_tag_is_blocked_when_the_scan_cannot_run(self):
        self.sb.commit("docs/plain.md", "plain\n")
        self.patterns([])
        self.blocked(self.check(line=self.tag_line(self.head())), 7)

    def test_a_tag_is_blocked_without_a_home(self):
        self.sb.commit("docs/plain.md", "plain\n")
        del self.sb.env["TL_RELAY_HOME"]
        self.blocked(self.check(line=self.tag_line(self.head())), 7)

    def test_a_tag_is_blocked_without_origin_main(self):
        self.sb.commit("docs/plain.md", "plain\n")
        self.sb._git("update-ref", "-d", "refs/remotes/origin/main")
        self.blocked(self.check(line=self.tag_line(self.head())), 2)

    def test_a_notes_leak_in_unrelated_history_is_blocked(self):
        self.sb._git("notes", "add", "-m", LEAK, "HEAD")
        notes = self.sb._git("rev-parse", "refs/notes/commits").stdout.strip()
        self.blocked(self.check(sha=notes, local_ref="refs/notes/commits", remote_ref="refs/notes/commits"), 7)

    def test_clean_notes_pass(self):
        self.sb._git("notes", "add", "-m", "plain", "HEAD")
        notes = self.sb._git("rev-parse", "refs/notes/commits").stdout.strip()
        self.allowed(self.check(sha=notes, local_ref="refs/notes/commits", remote_ref="refs/notes/commits"))

    def test_deleting_a_tag_passes(self):
        self.allowed(self.check(line="(delete) %s refs/tags/v1 %s\n" % (ZERO, self.head())))

    def bare_home(self):
        bare = self.sb.home / "bare-home"
        bare.mkdir()
        self.sb.env["TL_RELAY_HOME"] = str(bare)
        return bare

    def test_a_home_without_config_allows_a_branch_delete(self):
        bare = self.bare_home()
        self.allowed(self.check(line="(delete) %s refs/heads/feature %s\n" % (ZERO, self.head())))
        self.assertEqual(list(bare.iterdir()), [])

    def test_a_home_without_config_allows_a_push_outside_skills(self):
        bare = self.bare_home()
        self.sb.commit("docs/plain.md", "plain\n")
        self.allowed(self.check())
        self.assertEqual(list(bare.iterdir()), [])

    def test_a_home_without_config_refuses_a_gated_push(self):
        bare = self.bare_home()
        self.sb.commit("skills/alpha/note.md", "note\n")
        done = self.check()
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("tl-relay.yaml", done.stderr)
        self.assertEqual(list(bare.iterdir()), [])

    def test_a_home_without_config_refuses_an_unmerged_tag(self):
        self.bare_home()
        self.sb.commit("docs/plain.md", "plain\n")
        self.assertEqual(self.check(line=self.tag_line(self.head())).returncode, 2)

    def annotated(self, name="v1", message="plain", tagger="Fixture", email="fixture@example.invalid", target="HEAD"):
        self.sb._git("-c", "user.name=%s" % tagger, "-c", "user.email=%s" % email, "-c", "advice.nestedTag=false",
                     "tag", "-a", "-m", message, name, target)
        return self.sb._git("rev-parse", "refs/tags/" + name).stdout.strip()

    def allow(self, address):
        home = pathlib.Path(self.sb.env["TL_RELAY_HOME"])
        (home / "tl-relay.yaml").write_text(
            "neutrality:\n  patterns:\n    - LEAK[W]ORD\n  identity_allow:\n    - %s\n" % address)

    def test_a_tag_message_leak_on_a_merged_commit_is_blocked(self):
        tag = self.annotated(message=LEAK, target="refs/remotes/origin/main")
        self.blocked(self.check(line=self.tag_line(tag)), 7)

    def test_a_tagger_name_leak_is_blocked(self):
        self.blocked(self.check(line=self.tag_line(self.annotated(tagger=LEAK))), 7)

    def test_a_tagger_email_leak_is_blocked(self):
        email = "me@%s.example" % LEAK
        self.blocked(self.check(line=self.tag_line(self.annotated(email=email))), 7)

    def test_a_nested_tag_leak_is_blocked(self):
        self.annotated(name="inner", message=LEAK)
        outer = self.annotated(name="outer", target="refs/tags/inner")
        self.blocked(self.check(line=self.tag_line(outer)), 7)

    def test_a_clean_annotated_tag_passes(self):
        self.allowed(self.check(line=self.tag_line(self.annotated())))

    def test_an_annotated_tag_is_blocked_without_a_home(self):
        tag = self.annotated()
        del self.sb.env["TL_RELAY_HOME"]
        self.blocked(self.check(line=self.tag_line(tag)), 7)

    def test_an_allowed_tagger_email_passes(self):
        email = "me@%s.example" % LEAK
        self.allow(email)
        self.allowed(self.check(line=self.tag_line(self.annotated(email=email))))

    def test_a_near_match_of_an_allowed_tagger_email_is_blocked(self):
        self.allow("me@%s.example" % LEAK)
        tag = self.annotated(email="xme@%s.example" % LEAK)
        self.blocked(self.check(line=self.tag_line(tag)), 7)

    def test_an_allowed_address_in_a_tag_message_is_blocked(self):
        email = "me@%s.example" % LEAK
        self.allow(email)
        tag = self.annotated(message=email, email=email)
        self.blocked(self.check(line=self.tag_line(tag)), 7)

    def test_a_forbidden_tagger_name_beside_an_allowed_email_is_blocked(self):
        email = "me@%s.example" % LEAK
        self.allow(email)
        tag = self.annotated(tagger=LEAK, email=email)
        self.blocked(self.check(line=self.tag_line(tag)), 7)

    def test_an_unreadable_nested_tag_object_is_blocked(self):
        inner = self.annotated(name="inner")
        outer = self.annotated(name="outer", target="refs/tags/inner")
        self.sb._git("update-ref", "-d", "refs/tags/inner")
        (self.sb.repo / ".git" / "objects" / inner[:2] / inner[2:]).unlink()
        self.blocked(self.check(line=self.tag_line(outer)), 7)

    def test_a_replaced_tag_is_still_scanned(self):
        tag = self.annotated(message=LEAK, target="refs/remotes/origin/main")
        self.sb._git("replace", "-f", tag, self.head())
        self.blocked(self.check(line=self.tag_line(tag)), 7)

    def decoy_tag(self):
        return self.annotated(name="decoy", target="refs/remotes/origin/main")

    def test_a_tag_replaced_by_a_decoy_on_main_is_blocked(self):
        self.sb.commit("docs/leak.md", LEAK + "\n")
        tag = self.annotated()
        self.blocked(self.check(line=self.tag_line(tag)), 7)
        self.sb._git("replace", "-f", tag, self.decoy_tag())
        self.blocked(self.check(line=self.tag_line(tag)), 7)

    def test_a_branch_commit_replaced_by_a_docs_commit_is_gated(self):
        self.change_alpha()
        commit = self.head()
        self.blocked(self.check(sha=commit), 5)
        self.sb._git("checkout", "-q", "-b", "decoy", "refs/remotes/origin/main")
        decoy = self.sb.commit("docs/plain.md", "plain\n")
        self.sb._git("checkout", "-q", "feature")
        self.sb._git("replace", "-f", commit, decoy)
        self.blocked(self.check(sha=commit), 5)

    def test_a_tag_of_a_tree_replaced_to_peel_to_a_commit_is_blocked(self):
        tag = self.annotated(target="HEAD^{tree}")
        self.blocked(self.check(line=self.tag_line(tag)), 7)
        self.sb._git("replace", "-f", tag, self.decoy_tag())
        self.blocked(self.check(line=self.tag_line(tag)), 7)

    def bounded_check(self, oid):
        proc = subprocess.Popen(
            self.sb._command(["check", "origin", "url"]), cwd=str(self.sb.repo), env=self.sb.env, text=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
        )
        try:
            out, err = proc.communicate(self.tag_line(oid), timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            self.fail("the check did not finish")
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)

    def test_a_tag_whose_object_is_its_own_short_prefix_is_blocked(self):
        head = b"object abcd\ntype tag\ntag loop\ntagger t <t@example.invalid> 1 +0000\n\n"
        for nonce in range(5000000):
            body = head + b"%d\n" % nonce
            if hashlib.sha1(b"tag %d\0" % len(body) + body).hexdigest().startswith("abcd"):
                break
        path = self.sb.repo.parent / "loop-tag"
        path.write_bytes(body)
        oid = self.sb._git("hash-object", "--literally", "-t", "tag", "-w", str(path)).stdout.strip()
        self.assertTrue(oid.startswith("abcd"))
        self.blocked(self.bounded_check(oid), 7)

    def test_a_real_push_of_a_leaking_annotated_tag_is_blocked(self):
        self.sb.install_hook()
        self.annotated(message=LEAK)
        done = self.sb.push("push", "origin", "v1")
        self.assertNotEqual(done.returncode, 0, done.stderr)
        self.assertIn("blocked by rule 7:", done.stderr)


if __name__ == "__main__":
    unittest.main()
