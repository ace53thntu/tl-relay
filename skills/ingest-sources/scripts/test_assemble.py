import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assemble as asm

HEADER = "| New criterion | Old criterion | Continuity |\n| --- | --- | --- |\n"
SLICE_A = HEADER + "| `S-01-AC1` | `US-01-AC1a` | identical |\n| `S-01-AC2` | `US-01-AC2a` | changed |\n"
SLICE_B = HEADER + "| `S-02-AC1` | — | new |\n| — | `US-16-AC1a` | withdrawn |\n| — | `US-16-AC1b` | withdrawn |\n"
OLD = ["US-01-AC1a", "US-01-AC2a", "US-16-AC1a", "US-16-AC1b"]
NEW = ["S-01-AC1", "S-01-AC2", "S-02-AC1"]
OLD_STORY = {"US-01-AC1a": "US-01", "US-01-AC2a": "US-01", "US-16-AC1a": "US-16", "US-16-AC1b": "US-16"}


def make_ws(d, stamps=("good", "good"), slice_g=False):
    with open(os.path.join(d, "slices.json"), "w", encoding="utf-8") as fh:
        json.dump([{"name": "A", "new_ids": NEW[:2], "rule_on": []},
                   {"name": "B", "new_ids": NEW[2:], "rule_on": OLD[2:]}], fh)
    for name, ids, story in (("old", OLD, OLD_STORY), ("new", NEW, {})):
        with open(os.path.join(d, name + ".jsonl"), "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps({"id": i, "story": story.get(i, "S")}) + "\n" for i in ids))
    with open(os.path.join(d, "pairs.tsv"), "w", encoding="utf-8") as fh:
        fh.write("new_id\told_id\tkind\trule_changed\tratio\n")
        fh.write("S-01-AC1\tUS-01-AC1a\t\t\t\nS-01-AC2\tUS-01-AC2a\t\t\t\nS-02-AC1\t\t\t\t\n")
    digest = asm.inputs_digest(d)
    for name, body, stamp in (("A", SLICE_A, stamps[0]), ("B", SLICE_B, stamps[1])):
        head = "" if stamp is None else asm.STAMP.format(digest if stamp == "good" else stamp) + "\n"
        for kind, text in (("slice", body), ("findings", "findings\n")):
            with open(os.path.join(d, f"{kind}-{name}.md"), "w", encoding="utf-8") as fh:
                fh.write(head + text)
    if slice_g:
        with open(os.path.join(d, "slice-G.md"), "w", encoding="utf-8") as fh:
            fh.write(asm.STAMP.format("f" * 64) + "\n" + HEADER + "| `S-01-AC1` | `US-01-AC1a` | identical |\n")
        with open(os.path.join(d, "findings-G.md"), "w", encoding="utf-8") as fh:
            fh.write("findings\n")
    return digest


def run_main(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = asm.main(argv)
    return code, out.getvalue(), err.getvalue()


class AssembleTest(unittest.TestCase):
    def rows(self, a=SLICE_A, b=SLICE_B):
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for name, text in (("slice-A.md", a), ("slice-B.md", b)):
                paths.append(os.path.join(d, name))
                with open(paths[-1], "w", encoding="utf-8") as fh:
                    fh.write(text)
            return asm.read_slices(paths)

    def test_clean_slices_count_every_verdict(self):
        counts, errors = asm.check(self.rows(), NEW, OLD)
        self.assertEqual(errors, [])
        self.assertEqual(counts, {"changed": 1, "identical": 1, "new": 1, "reworded": 0, "withdrawn": 2})

    def test_ids_to_scan_add_a_story_whose_criteria_were_all_withdrawn(self):
        self.assertEqual(asm.ids_to_scan(self.rows(), OLD_STORY), ["US-01-AC2a", "US-16", "US-16-AC1a", "US-16-AC1b"])

    def test_a_missing_ruling_is_an_error(self):
        _, errors = asm.check(self.rows(b=SLICE_B.rsplit("| — | `US-16-AC1b`", 1)[0]), NEW, OLD)
        self.assertIn("old US-16-AC1b ruled 0 times", errors)

    def test_a_double_ruling_is_an_error(self):
        _, errors = asm.check(self.rows(a=SLICE_A + "| `S-02-AC1` | `US-16-AC1a` | reworded |\n"), NEW, OLD)
        self.assertIn("new S-02-AC1 ruled 2 times", errors)
        self.assertIn("old US-16-AC1a ruled 2 times", errors)

    def test_a_new_verdict_naming_an_old_criterion_is_an_error(self):
        bad = SLICE_B.replace("| `S-02-AC1` | — | new |", "| `S-02-AC1` | `US-16-AC1a` | new |")
        _, errors = asm.check(self.rows(b=bad), NEW, OLD)
        self.assertTrue(any("new verdict must name only a new criterion" in e for e in errors))

    def test_pending_lists_unstamped_and_missing_slices(self):
        with tempfile.TemporaryDirectory() as d:
            digest = make_ws(d, stamps=("good", None))
            h = hashlib.sha256()
            for name in ("slices.json", "new.jsonl", "old.jsonl"):
                with open(os.path.join(d, name), "rb") as fh:
                    data = fh.read()
                h.update(name.encode() + b"\n" + str(len(data)).encode() + b"\n" + data)
            expected = h.hexdigest()
            self.assertEqual(asm.pending(d), {"inputs_sha256": expected, "pending": ["B"]})
            make_ws(d)
            self.assertEqual(asm.pending(d)["pending"], [])
            os.remove(os.path.join(d, "findings-A.md"))
            self.assertEqual(asm.pending(d), {"inputs_sha256": digest, "pending": ["A"]})

    def test_pending_rejects_a_stamp_from_another_slicing(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d, stamps=("0" * 64, "0" * 64))
            self.assertEqual(asm.pending(d)["pending"], ["A", "B"])

    def test_main_ignores_files_outside_slices_json(self):
        with tempfile.TemporaryDirectory() as d:
            digest = make_ws(d, slice_g=True)
            code, _, _ = run_main(["--ws", d, "--out", os.path.join(d, "adjudication.json"), "--ids-out", os.path.join(d, "ids.txt")])
            self.assertEqual(code, 0)
            with open(os.path.join(d, "adjudication.json"), encoding="utf-8") as fh:
                adj = json.load(fh)
            self.assertEqual(adj["inputs_sha256"], digest)
            self.assertEqual(adj["findings"], [os.path.join(d, "findings-A.md"), os.path.join(d, "findings-B.md")])

    def test_main_fails_on_a_stale_stamp(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d, stamps=("good", "0" * 64))
            code, _, err = run_main(["--ws", d, "--out", os.path.join(d, "adjudication.json"), "--ids-out", os.path.join(d, "ids.txt")])
            self.assertEqual(code, 1)
            self.assertIn("slice-B.md", err)
            self.assertIn("rerun reader B", err)
            self.assertFalse(os.path.exists(os.path.join(d, "adjudication.json")))

    def test_pending_cli_prints_json(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d, stamps=("good", None))
            code, out, _ = run_main(["--ws", d, "--pending"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out), asm.pending(d))

    def test_undecodable_reader_file_is_pending(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d)
            with open(os.path.join(d, "slice-B.md"), "wb") as fh:
                fh.write(b"\xff\xfe")
            self.assertEqual(asm.pending(d)["pending"], ["B"])

    def test_a_bom_and_padding_on_the_stamp_line_still_count_as_stamped(self):
        with tempfile.TemporaryDirectory() as d:
            digest = make_ws(d)
            with open(os.path.join(d, "slice-A.md"), "w", encoding="utf-8") as fh:
                fh.write("\ufeff  " + asm.STAMP.format(digest) + "  \n" + SLICE_A)
            self.assertEqual(asm.pending(d)["pending"], [])

    def test_pending_with_an_output_flag_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d)
            for flag in ("--out", "--ids-out"):
                with self.assertRaises(SystemExit) as cm:
                    run_main(["--ws", d, "--pending", flag, os.path.join(d, "x")])
                self.assertEqual(cm.exception.code, 2)

    def test_missing_slices_json_fails_in_both_modes(self):
        with tempfile.TemporaryDirectory() as d:
            for argv in (["--ws", d, "--pending"], ["--ws", d, "--out", os.path.join(d, "o"), "--ids-out", os.path.join(d, "i")]):
                code, _, err = run_main(argv)
                self.assertEqual(code, 1)
                self.assertTrue(err.startswith("assemble: cannot read"))

    def test_a_text_change_in_new_jsonl_makes_every_slice_pending(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d)
            path = os.path.join(d, "new.jsonl")
            with open(path, encoding="utf-8") as fh:
                rows = [json.loads(line) for line in fh]
            rows[0]["text"] = "reworded"
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("".join(json.dumps(r) + "\n" for r in rows))
            self.assertEqual(asm.pending(d)["pending"], ["A", "B"])

    def test_old_jsonl_change_changes_the_digest(self):
        with tempfile.TemporaryDirectory() as d:
            before = make_ws(d)
            with open(os.path.join(d, "old.jsonl"), "ab") as fh:
                fh.write(b" ")
            self.assertNotEqual(asm.inputs_digest(d), before)

    def test_missing_jsonl_fails_in_both_modes(self):
        for name in ("new.jsonl", "old.jsonl"):
            with tempfile.TemporaryDirectory() as d:
                make_ws(d)
                os.remove(os.path.join(d, name))
                for argv in (["--ws", d, "--pending"], ["--ws", d, "--out", os.path.join(d, "o"), "--ids-out", os.path.join(d, "i")]):
                    code, _, err = run_main(argv)
                    self.assertEqual(code, 1)
                    self.assertEqual(len(err.splitlines()), 1)
                    self.assertTrue(err.startswith(f"assemble: cannot read {os.path.join(d, name)}: "))

    def test_malformed_jsonl_fails_with_its_path(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d)
            with open(os.path.join(d, "new.jsonl"), "w", encoding="utf-8") as fh:
                fh.write("{not json\n")
            code, _, err = run_main(["--ws", d, "--out", os.path.join(d, "o"), "--ids-out", os.path.join(d, "i")])
            self.assertEqual(code, 1)
            self.assertEqual(len(err.splitlines()), 1)
            self.assertTrue(err.startswith(f"assemble: cannot read {os.path.join(d, 'new.jsonl')}: "))

    def append(self, d, name, text):
        with open(os.path.join(d, name), "a", encoding="utf-8") as fh:
            fh.write(text)

    def drop(self, d, name, rid):
        path = os.path.join(d, name)
        with open(path, encoding="utf-8") as fh:
            rows = [r for r in (json.loads(line) for line in fh) if r["id"] != rid]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in rows))

    def pending_err(self, d):
        code, _, err = run_main(["--ws", d, "--pending"])
        self.assertEqual(code, 1)
        return err

    def test_pending_rejects_a_truncated_register_line(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d)
            with open(os.path.join(d, "old.jsonl"), "w", encoding="utf-8") as fh:
                fh.write("".join(json.dumps({"id": i, "story": "S"}) + "\n" for i in OLD[:3]) + '{"id": "US-16-AC1b"')
            err = self.pending_err(d)
            self.assertEqual(len(err.splitlines()), 1)
            self.assertTrue(err.startswith(f"assemble: cannot read {os.path.join(d, 'old.jsonl')}: "))

    def drop_story(self, d):
        path = os.path.join(d, "old.jsonl")
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh]
        for r in rows:
            if r["id"] == "US-16-AC1b":
                del r["story"]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in rows))
        stamp = asm.STAMP.format(asm.inputs_digest(d))
        for name in os.listdir(d):
            if name.startswith(("slice-", "findings-")) and name.endswith(".md"):
                with open(os.path.join(d, name), encoding="utf-8") as fh:
                    lines = fh.read().split("\n")
                lines[0] = stamp
                with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                    fh.write("\n".join(lines))

    def test_pending_rejects_an_old_row_without_story(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d)
            self.drop_story(d)
            err = self.pending_err(d)
            self.assertEqual(len(err.splitlines()), 1)
            self.assertTrue(err.startswith(f"assemble: cannot read {os.path.join(d, 'old.jsonl')}: "))

    def test_main_rejects_an_old_row_without_story(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d)
            self.drop_story(d)
            code, _, err = run_main(["--ws", d, "--out", os.path.join(d, "o"), "--ids-out", os.path.join(d, "i")])
            self.assertEqual(code, 1)
            self.assertEqual(len(err.splitlines()), 1)
            self.assertTrue(err.startswith(f"assemble: cannot read {os.path.join(d, 'old.jsonl')}: "))

    def test_pending_rejects_a_row_without_id(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d)
            self.append(d, "new.jsonl", '{"story": "S"}\n')
            err = self.pending_err(d)
            self.assertEqual(len(err.splitlines()), 1)
            self.assertTrue(err.startswith(f"assemble: cannot read {os.path.join(d, 'new.jsonl')}: "))

    def test_pending_names_a_lost_new_row(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d)
            self.drop(d, "new.jsonl", "S-02-AC1")
            self.assertEqual(self.pending_err(d), f"{os.path.join(d, 'new.jsonl')}: id S-02-AC1 missing\n")

    def test_pending_names_a_lost_paired_old_row(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d)
            self.drop(d, "old.jsonl", "US-01-AC1a")
            self.assertEqual(self.pending_err(d), f"{os.path.join(d, 'old.jsonl')}: id US-01-AC1a missing\n")

    def test_pending_names_a_lost_unclaimed_old_row(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d)
            self.drop(d, "old.jsonl", "US-16-AC1b")
            self.assertEqual(self.pending_err(d), f"{os.path.join(d, 'old.jsonl')}: id US-16-AC1b missing\n")

    def test_pending_names_an_extra_row_after_the_missing_ones(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d)
            self.drop(d, "new.jsonl", "S-02-AC1")
            self.append(d, "new.jsonl", json.dumps({"id": "S-09-AC1", "story": "S"}) + "\n")
            self.append(d, "old.jsonl", json.dumps({"id": "US-99-AC1", "story": "S"}) + "\n")
            n, o = os.path.join(d, "new.jsonl"), os.path.join(d, "old.jsonl")
            self.assertEqual(self.pending_err(d).splitlines(),
                             [f"{n}: id S-02-AC1 missing", f"{n}: unexpected id S-09-AC1", f"{o}: unexpected id US-99-AC1"])

    def test_pending_without_pairs_tsv_fails_with_its_path(self):
        for damage in ("remove", "garbage", "oversized"):
            with tempfile.TemporaryDirectory() as d:
                make_ws(d)
                path = os.path.join(d, "pairs.tsv")
                if damage == "remove":
                    os.remove(path)
                else:
                    payload = b"\xff\xfe" if damage == "garbage" else b"new_id\told_id\n" + b"x" * 200000 + b"\n"
                    with open(path, "wb") as fh:
                        fh.write(payload)
                err = self.pending_err(d)
                self.assertEqual(len(err.splitlines()), 1)
                self.assertTrue(err.startswith(f"assemble: cannot read {path}: "))

    def test_main_rejects_a_row_without_id(self):
        with tempfile.TemporaryDirectory() as d:
            make_ws(d)
            self.append(d, "new.jsonl", '{"story": "S"}\n')
            code, _, err = run_main(["--ws", d, "--out", os.path.join(d, "o"), "--ids-out", os.path.join(d, "i")])
            self.assertEqual(code, 1)
            self.assertEqual(len(err.splitlines()), 1)
            self.assertTrue(err.startswith(f"assemble: cannot read {os.path.join(d, 'new.jsonl')}: "))


if __name__ == "__main__":
    unittest.main()
