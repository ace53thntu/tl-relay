import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state as st


class StateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.path = st.init(self.root, "demo")

    def tearDown(self):
        self.tmp.cleanup()

    def test_init_creates_typed_dirs_and_todo_stages(self):
        for d in st.PAGE_DIRS:
            self.assertTrue(os.path.isdir(os.path.join(self.root, "designs", "demo", d)))
        s = st.load(self.path)
        self.assertEqual([x["status"] for x in s["stages"]], ["todo"] * 4)
        with self.assertRaises(st.StateError):
            st.init(self.root, "demo")

    def test_first_source_of_a_kind_is_baseline(self):
        s = st.load(self.path)
        self.assertTrue(st.add_source(s, "stories", "v1", "2026-08-31", "a" * 64, "raw/projects/demo/2026-08-31/stories/a.xlsx"))
        self.assertFalse(st.add_source(s, "stories", "v2", "2026-09-12", "b" * 64, "raw/projects/demo/2026-09-12/stories/b.xlsx"))
        self.assertTrue(st.add_source(s, "prd", "v1", "2026-08-27", "c" * 64, "raw/projects/demo/2026-08-27/prd/c.pdf"))
        with self.assertRaises(st.StateError):
            st.add_source(s, "other", "dup", "2026-09-13", "a" * 64, "raw/projects/demo/2026-09-13/other/d")

    def test_pending_impact_blocks_only_its_own_stage(self):
        s = st.load(self.path)
        st.add_source(s, "stories", "v1", "2026-08-31", "a" * 64, "raw/projects/demo/2026-08-31/stories/a.xlsx")
        st.add_impact(s, "design", [("hlds/x.md", "Decision 19", "US-16-AC1b")], "drift")
        with self.assertRaises(st.StateError):
            st.set_stage(s, "design", "signed-off", "2026-09-13")
        st.set_stage(s, "review", "signed-off", "2026-09-13")
        self.assertEqual(st.stage(s, "review")["baselines"], {"stories": "a" * 64})
        self.assertEqual(st.clear_impact(s, "hlds/x.md", "Decision 19"), 1)
        st.set_stage(s, "design", "signed-off", "2026-09-13")

    def test_signed_off_needs_a_date(self):
        s = st.load(self.path)
        with self.assertRaises(st.StateError):
            st.set_stage(s, "review", "signed-off")

    def test_moving_a_baseline_marks_every_signed_stage_stale(self):
        s = st.load(self.path)
        st.add_source(s, "stories", "v1", "2026-08-31", "a" * 64, "raw/projects/demo/2026-08-31/stories/a.xlsx")
        st.set_stage(s, "design", "signed-off", "2026-09-11")
        st.add_source(s, "stories", "v2", "2026-09-12", "b" * 64, "raw/projects/demo/2026-09-12/stories/b.xlsx")
        self.assertEqual(st.set_baseline(s, "stories", "b" * 64), ["design"])
        self.assertEqual(st.baseline(s, "stories")["sha256"], "b" * 64)

    def test_next_step_prefers_stale_and_skips_not_applicable(self):
        s = st.load(self.path)
        self.assertEqual(st.next_step(s)["stage"], "ingest")
        st.set_stage(s, "ingest", "signed-off", "2026-09-01")
        st.set_stage(s, "review", "n/a")
        self.assertEqual(st.next_step(s), {"stage": "design", "status": "todo", "gate": "G-design", "reads": []})
        st.stage(s, "breakdown")["status"] = "stale"
        self.assertEqual(st.next_step(s)["stage"], "breakdown")

    def test_save_keeps_the_pages_section(self):
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write("* [A](specs/a.md) - A page.\n")
        s = st.load(self.path)
        st.set_stage(s, "review", "draft")
        st.save(self.path, s)
        with open(self.path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("* [A](specs/a.md) - A page.", text)
        self.assertEqual(st.stage(st.load(self.path), "review")["status"], "draft")

    def test_add_impact_reads_the_impact_tsv(self):
        tsv = os.path.join(self.root, "impact.tsv")
        with open(tsv, "w", encoding="utf-8") as fh:
            fh.write("page\tsection\tids\nhlds/x.md\tDecision 19\tUS-16-AC1a,US-16-AC1b\n")
        with contextlib.redirect_stdout(io.StringIO()):
            code = st.main(["--knowledge-root", self.root, "--handle", "demo", "add-impact",
                            "--stage", "design", "--reason", "drift", "--from-tsv", tsv])
        self.assertEqual(code, 0)
        pending = st.load(self.path)["pending_impact"]
        self.assertEqual(pending, [{"stage": "design", "page": "hlds/x.md", "section": "Decision 19",
                                    "ids": "US-16-AC1a,US-16-AC1b", "reason": "drift"}])

    def test_set_reads_records_sorted_kinds_and_next_reports_them(self):
        state = st.load(self.path)
        self.assertEqual(st.set_reads(state, "review", ["stories", "prd", "stories"]), ["prd", "stories"])
        st.save(self.path, state)
        state = st.load(self.path)
        st.set_stage(state, "ingest", "n/a")
        self.assertEqual(st.next_step(state), {"stage": "review", "status": "todo", "gate": "G-review", "reads": ["prd", "stories"]})

    def test_set_reads_rejects_an_unknown_kind_and_state_without_reads_loads(self):
        state = st.load(self.path)
        with self.assertRaises(st.StateError):
            st.set_reads(state, "design", ["prd", "wireframe"])
        for s in state["stages"]:
            del s["reads"]
        self.assertEqual(st.next_step(state)["reads"], [])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = st.main(["--knowledge-root", self.root, "--handle", "demo", "set-reads", "--stage", "design", "--kinds", "prd,screens"])
        self.assertEqual(code, 1)

    def test_cli_next_and_refusal_exit_codes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = st.main(["--knowledge-root", self.root, "--handle", "demo", "next"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["gate"], "G-ingest")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = st.main(["--knowledge-root", self.root, "--handle", "demo", "set-stage",
                            "--stage", "design", "--status", "signed-off"])
        self.assertEqual(code, 1)
        self.assertIn("date", err.getvalue())

    def test_add_source_refuses_a_path_outside_the_archive(self):
        s = st.load(self.path)
        with self.assertRaises(st.StateError) as caught:
            st.add_source(s, "stories", "v1", "2026-09-20", "a" * 64,
                          "raw/pdf/aul-crm/20-09-2026/book.xlsx")
        self.assertIn("snapshot.py", str(caught.exception))

    def test_add_source_accepts_an_archived_path(self):
        s = st.load(self.path)
        st.add_source(s, "stories", "v1", "2026-09-20", "a" * 64,
                      "raw/projects/demo/2026-09-20/stories/book.xlsx")
        self.assertEqual(len(s["sources"]), 1)

    def test_add_source_refuses_a_newline_in_any_archive_segment(self):
        s = st.load(self.path)
        for sha, path in (("b" * 64, "raw/projects/demo/2026-09-20/stories/book.xlsx\n"),
                          ("c" * 64, "raw/projects/de\nmo/2026-09-20/stories/book.xlsx")):
            with self.subTest(path=path):
                with self.assertRaises(st.StateError):
                    st.add_source(s, "stories", "v1", "2026-09-20", sha, path)
        self.assertEqual(s["sources"], [])
        st.add_source(s, "stories", "v1", "2026-09-20", "a" * 64, "raw/projects/demo/2026-09-20/stories/stories v1.xlsx")
        self.assertEqual(len(s["sources"]), 1)

    def test_add_source_refuses_a_dot_segment_and_non_ascii_digits(self):
        s = st.load(self.path)
        for n, path in enumerate(("raw/projects/../2026-09-20/stories/b",
                                  "raw/projects/./2026-09-20/stories/b",
                                  "raw/projects/demo/2026-09-20/../b",
                                  "raw/projects/demo/2026-09-20/stories/..",
                                  "raw/projects/demo/2026-09-20/sto\nries/b",
                                  "raw/projects/demo/２０２６-09-20/stories/b")):
            with self.subTest(path=path):
                with self.assertRaises(st.StateError):
                    st.add_source(s, "stories", "v1", "2026-09-20", str(n) * 64, path)
        self.assertEqual(s["sources"], [])
        for n, name in enumerate(("..notes.md", ".hidden.xlsx", "stories v1.xlsx")):
            st.add_source(s, "stories", "v1", "2026-09-20", "e%d" % n * 32, "raw/projects/demo/2026-09-20/stories/" + name)
        self.assertEqual(len(s["sources"]), 3)

    def test_add_source_refuses_a_bad_received_and_a_multi_line_label(self):
        s = st.load(self.path)
        ok = "raw/projects/demo/2026-09-20/stories/book.xlsx"
        for n, (label, received, text) in enumerate((("v1", "2026-09-20\n", "received must be YYYY-MM-DD"),
                                                     ("v1", "２０２６-09-20", "received must be YYYY-MM-DD"),
                                                     ("v1", "20-09-2026", "received must be YYYY-MM-DD"),
                                                     ("v1\nx", "2026-09-20", "label must be one line"))):
            with self.subTest(label=label, received=received):
                with self.assertRaisesRegex(st.StateError, text):
                    st.add_source(s, "stories", label, received, str(n) * 64, ok)
        self.assertEqual(s["sources"], [])

    def test_add_source_refuses_a_control_character_in_a_segment_or_label(self):
        s = st.load(self.path)
        for n, path in enumerate(("raw/projects/demo/2026-09-20/stories/book\x7f.xlsx",
                                  "raw/projects/de\x9fmo/2026-09-20/stories/b",
                                  "raw/projects/demo/2026-09-20/stories/b\ufffe")):
            with self.subTest(path=path):
                with self.assertRaises(st.StateError):
                    st.add_source(s, "stories", "v1", "2026-09-20", str(n) * 64, path)
        with self.assertRaisesRegex(st.StateError, "label must be one line with no DEL, C1 control other than U[+]0085, U[+]FFFE or U[+]FFFF"):
            st.add_source(s, "stories", "v1\x80", "2026-09-20", "9" * 64, "raw/projects/demo/2026-09-20/stories/book.xlsx")
        self.assertEqual(s["sources"], [])

    def test_four_stages_with_stage_named_gates(self):
        self.assertEqual(st.STAGES, ["ingest", "review", "design", "breakdown"])
        self.assertEqual(st.GATES["design"], "G-design")

    def test_init_creates_the_page_tree_dirs(self):
        for d in ("use-cases", "lld", "sources", "audits", "contracts", "specs"):
            self.assertTrue(os.path.isdir(os.path.join(self.root, "designs", "demo", d)))

    def test_init_has_no_hub_target(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            st.main(["--knowledge-root", self.root, "--handle", "other", "init", "--target", "hub"])

    def test_reopening_design_marks_a_signed_breakdown_stale(self):
        s = st.load(self.path)
        st.set_stage(s, "design", "signed-off", "2026-11-11")
        st.set_stage(s, "breakdown", "signed-off", "2026-11-12")
        st.set_stage(s, "design", "draft")
        self.assertEqual(st.stage(s, "breakdown")["status"], "stale")

    def test_a_handle_the_runtime_would_refuse_is_refused_before_any_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "a", "b", "k")
            for handle in ("Demo", "../../x", "a/b", "1abc", "-a", "", "demo\n"):
                err = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                    code = st.main(["--knowledge-root", root, "--handle=" + handle, "init"])
                self.assertEqual(code, 1, handle)
                self.assertEqual(err.getvalue(), "state: handle must be a lowercase letter followed by lowercase letters, "
                                 "digits or hyphens, got %r\n" % handle, handle)
            self.assertEqual([d for d, _, files in os.walk(tmp) if files], [])
            self.assertTrue(st.init(root, "demo-2").endswith(os.path.join("designs", "demo-2", "index.md")))

    def test_a_read_with_a_refused_handle_stops_before_the_state_is_loaded(self):
        with tempfile.TemporaryDirectory() as root:
            st.init(root, "demo")
            for cmd in ("show", "next"):
                err = io.StringIO()
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err), \
                        mock.patch.object(st, "load", side_effect=AssertionError("state loaded")):
                    code = st.main(["--knowledge-root", root, "--handle=Demo", cmd])
                self.assertEqual(code, 1, cmd)
                self.assertEqual(err.getvalue(), "state: handle must be a lowercase letter followed by lowercase letters, "
                                 "digits or hyphens, got 'Demo'\n", cmd)


def old_stage(sid, status, signed=None, baselines=None, reads=None):
    return {"id": sid, "status": status, "signed": signed, "baselines": baselines or {}, "reads": reads or []}


class MigrateTest(unittest.TestCase):
    def old_state(self, hla, lld, absorb=None, pending=None, breakdown=None):
        stages = [old_stage("ingest", "signed-off", "2026-09-01"), old_stage("review", "signed-off", "2026-09-02"),
                  hla, lld, absorb or old_stage("absorb", "todo")]
        if breakdown:
            stages.append(breakdown)
        return {"handle": "old", "target": "hub", "tier": "T2", "sources": [], "stages": stages,
                "pending_impact": pending or []}

    def test_both_signed_takes_the_later_date(self):
        s = st.migrate(self.old_state(
            old_stage("hla", "signed-off", "2026-10-01", {"prd": "a"}, ["prd"]),
            old_stage("contract-lld", "signed-off", "2026-10-05", {"prd": "b"}, ["stories"])))
        d = st.stage(s, "design")
        self.assertEqual((d["status"], d["signed"], d["baselines"], d["reads"]),
                         ("signed-off", "2026-10-05", {"prd": "b"}, ["stories"]))

    def test_less_advanced_status_wins(self):
        s = st.migrate(self.old_state(old_stage("hla", "signed-off", "2026-10-01"), old_stage("contract-lld", "draft")))
        self.assertEqual(st.stage(s, "design")["status"], "draft")

    def test_unsigned_pair_takes_fields_from_contract_lld(self):
        s = st.migrate(self.old_state(old_stage("hla", "draft", reads=["prd"]),
                                      old_stage("contract-lld", "todo", reads=["stories"])))
        d = st.stage(s, "design")
        self.assertEqual((d["status"], d["reads"]), ("todo", ["stories"]))

    def test_one_not_applicable_stage_gives_way_to_the_signed_one(self):
        s = st.migrate(self.old_state(old_stage("hla", "n/a"),
                                      old_stage("contract-lld", "signed-off", "2026-10-05", {"prd": "b"}, ["prd"])))
        d = st.stage(s, "design")
        self.assertEqual((d["status"], d["signed"], d["baselines"], d["reads"]),
                         ("signed-off", "2026-10-05", {"prd": "b"}, ["prd"]))

    def test_hla_signed_later_wins_its_fields(self):
        s = st.migrate(self.old_state(
            old_stage("hla", "signed-off", "2026-10-09", {"prd": "a"}, ["prd"]),
            old_stage("contract-lld", "signed-off", "2026-10-05", {"prd": "b"}, ["stories"])))
        d = st.stage(s, "design")
        self.assertEqual((d["status"], d["signed"], d["baselines"], d["reads"]),
                         ("signed-off", "2026-10-09", {"prd": "a"}, ["prd"]))

    def test_draft_hla_beside_signed_contract_lld_is_draft(self):
        s = st.migrate(self.old_state(old_stage("hla", "draft"), old_stage("contract-lld", "signed-off", "2026-10-05")))
        self.assertEqual(st.stage(s, "design")["status"], "draft")

    def test_contract_lld_not_applicable_gives_way_to_signed_hla(self):
        s = st.migrate(self.old_state(old_stage("hla", "signed-off", "2026-10-05", {"prd": "a"}, ["prd"]),
                                      old_stage("contract-lld", "n/a")))
        d = st.stage(s, "design")
        self.assertEqual((d["status"], d["signed"], d["baselines"], d["reads"]),
                         ("signed-off", "2026-10-05", {"prd": "a"}, ["prd"]))

    def test_two_not_applicable_stages_stay_not_applicable(self):
        s = st.migrate(self.old_state(old_stage("hla", "n/a"), old_stage("contract-lld", "n/a")))
        self.assertEqual(st.stage(s, "design")["status"], "n/a")

    def test_a_set_without_breakdown_gets_a_not_applicable_one(self):
        s = st.migrate(self.old_state(old_stage("hla", "draft"), old_stage("contract-lld", "draft")))
        self.assertEqual(st.stage(s, "breakdown")["status"], "n/a")

    def test_pending_impact_moves_to_design(self):
        rows = [{"stage": "hla", "page": "a", "section": "x", "ids": "", "reason": "r"},
                {"stage": "contract-lld", "page": "b", "section": "y", "ids": "", "reason": "r"}]
        s = st.migrate(self.old_state(old_stage("hla", "draft"), old_stage("contract-lld", "draft"), pending=rows))
        self.assertEqual([p["stage"] for p in s["pending_impact"]], ["design", "design"])

    def test_absorb_is_removed(self):
        s = st.migrate(self.old_state(old_stage("hla", "draft"), old_stage("contract-lld", "draft"),
                                      absorb=old_stage("absorb", "signed-off", "2026-10-06")))
        self.assertEqual([x["id"] for x in s["stages"]], st.STAGES)

    def test_a_hub_set_loses_target_and_tier(self):
        s = st.migrate(self.old_state(old_stage("hla", "draft"), old_stage("contract-lld", "draft")))
        self.assertNotIn("target", s)
        self.assertNotIn("tier", s)

    def test_an_old_block_is_rewritten_on_the_next_write(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "index.md")
            old = self.old_state(old_stage("hla", "draft"), old_stage("contract-lld", "draft"))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f"# old\n\n<!-- tl-design:state -->\n```json\n{json.dumps(old)}\n```\n<!-- /tl-design:state -->\n")
            st.save(path, st.load(path))
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        block = json.loads(st.BLOCK.search(text).group(2))
        self.assertEqual([x["id"] for x in block["stages"]], st.STAGES)


class ManagedSetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.path = st.init(self.root, "demo")
        state = st.load(self.path)
        state["managed_by"] = "tl-relay"
        st.save(self.path, state)

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = st.main(["--knowledge-root", self.root, "--handle", "demo", *args])
        return code, out.getvalue(), err.getvalue()

    def test_a_write_on_a_set_with_a_managed_key_succeeds(self):
        code, out, err = self.run_main("set-stage", "--stage", "ingest", "--status", "draft")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(st.stage(st.load(self.path), "ingest")["status"], "draft")

    def test_show_and_next_still_work_on_a_managed_set(self):
        code, out, _ = self.run_main("show")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["managed_by"], "tl-relay")
        code, out, _ = self.run_main("next")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["stage"], "ingest")


if __name__ == "__main__":
    unittest.main()
