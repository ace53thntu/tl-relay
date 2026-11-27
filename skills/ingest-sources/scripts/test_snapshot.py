import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import snapshot as sn

st = sn.st


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "k")
        st.init(self.root, "demo")
        self.src = os.path.join(self.tmp.name, "stories v1.xlsx")
        with open(self.src, "wb") as fh:
            fh.write(b"first")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, path, received="2026-08-31", label="v1", extra=()):
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sn.main(["--knowledge-root", self.root, "--handle", "demo", "--kind", "stories",
                            "--label", label, "--received", received, *extra, path])
        self.last_stderr = err.getvalue()
        return code, (json.loads(out.getvalue()) if code == 0 else None)

    def test_check_on_a_new_file_copies_and_records_nothing(self):
        code, out = self.run_cli(self.src, extra=("--check",))
        self.assertEqual(code, 0)
        self.assertEqual(out, {"duplicate_of": None, "sha256": hashlib.sha256(b"first").hexdigest(),
                               "content_sha256": hashlib.sha256(b"first").hexdigest(),
                               "path": None, "baseline": None})
        self.assertEqual(st.load(st.index_path(self.root, "demo"))["sources"], [])
        self.assertFalse(os.path.exists(os.path.join(self.root, "raw")))

    def test_check_reports_a_duplicate_without_recording(self):
        self.run_cli(self.src)
        other = os.path.join(self.tmp.name, "renamed.xlsx")
        with open(other, "wb") as fh:
            fh.write(b"first")
        code, out = self.run_cli(other, received="2026-09-12", extra=("--check",))
        self.assertEqual(code, 0)
        self.assertEqual(out["duplicate_of"], "raw/projects/demo/2026-08-31/stories/stories v1.xlsx")
        self.assertIsNone(out["path"])
        self.assertIsNone(out["baseline"])
        self.assertEqual(len(st.load(st.index_path(self.root, "demo"))["sources"]), 1)
        self.assertFalse(os.path.exists(os.path.join(self.root, "raw/projects/demo/2026-09-12")))

    def test_check_still_validates_its_arguments(self):
        code, _ = self.run_cli(self.src, received="2026-8-31", extra=("--check",))
        self.assertEqual(code, 1)

    def test_check_refuses_a_name_a_real_run_refuses(self):
        bad = os.path.join(self.tmp.name, "stories\nv1.xlsx")
        with open(bad, "wb") as fh:
            fh.write(b"first")
        code, _ = self.run_cli(bad, extra=("--check",))
        self.assertEqual(code, 1)
        self.assertEqual(st.load(st.index_path(self.root, "demo"))["sources"], [])

    def test_check_refuses_a_different_file_at_the_archive_path(self):
        dest = os.path.join(self.root, "raw/projects/demo/2026-08-31/stories/stories v1.xlsx")
        os.makedirs(os.path.dirname(dest))
        with open(dest, "wb") as fh:
            fh.write(b"other")
        code, _ = self.run_cli(self.src, extra=("--check",))
        self.assertEqual(code, 1)

    def test_copies_by_date_and_kind_and_records_the_baseline(self):
        code, out = self.run_cli(self.src)
        self.assertEqual(code, 0)
        self.assertEqual(out["path"], "raw/projects/demo/2026-08-31/stories/stories v1.xlsx")
        self.assertEqual(out["sha256"], hashlib.sha256(b"first").hexdigest())
        self.assertTrue(out["baseline"])
        self.assertTrue(os.path.isfile(os.path.join(self.root, out["path"])))
        self.assertEqual(len(st.load(st.index_path(self.root, "demo"))["sources"]), 1)

    def test_same_bytes_under_another_name_is_not_a_new_revision(self):
        self.run_cli(self.src)
        other = os.path.join(self.tmp.name, "renamed.xlsx")
        with open(other, "wb") as fh:
            fh.write(b"first")
        code, out = self.run_cli(other, received="2026-09-12", label="v1 again")
        self.assertEqual(code, 0)
        self.assertEqual(out["duplicate_of"], "raw/projects/demo/2026-08-31/stories/stories v1.xlsx")
        self.assertIsNone(out["path"])
        self.assertEqual(len(st.load(st.index_path(self.root, "demo"))["sources"]), 1)

    def test_a_second_revision_is_not_the_baseline(self):
        self.run_cli(self.src)
        v2 = os.path.join(self.tmp.name, "stories v2.xlsx")
        with open(v2, "wb") as fh:
            fh.write(b"second")
        code, out = self.run_cli(v2, received="2026-09-12", label="v2")
        self.assertEqual(code, 0)
        self.assertFalse(out["baseline"])

    def test_rejects_a_malformed_date(self):
        code, _ = self.run_cli(self.src, received="12-09-2026")
        self.assertEqual(code, 1)

    def test_rejects_a_date_with_a_trailing_newline(self):
        code, _ = self.run_cli(self.src, received="2026-08-31\n")
        self.assertEqual(code, 1)
        self.assertIn("--received must be YYYY-MM-DD", self.last_stderr)
        self.assertFalse(os.path.exists(os.path.join(self.root, "raw", "projects", "demo", "2026-08-31\n")))

    def test_a_name_with_a_newline_is_refused_before_the_copy(self):
        src = os.path.join(self.tmp.name, "book\nx.xlsx")
        with open(src, "wb") as fh:
            fh.write(b"third")
        kind_dir = os.path.join(self.root, "raw", "projects", "demo", "2026-08-31", "stories")
        for _ in range(2):
            code, _ = self.run_cli(src)
            self.assertEqual(code, 1)
            self.assertIn("cannot archive as", self.last_stderr)
            self.assertFalse(os.path.exists(kind_dir))
        self.assertEqual(st.load(st.index_path(self.root, "demo"))["sources"], [])

    def test_a_multi_line_label_is_refused_before_the_copy(self):
        code, _ = self.run_cli(self.src, label="v1\nx")
        self.assertEqual(code, 1)
        self.assertIn("label must be one line", self.last_stderr)
        self.assertFalse(os.path.exists(os.path.join(self.root, "raw", "projects", "demo", "2026-08-31", "stories")))

    def test_a_name_or_label_with_a_control_character_is_refused_before_the_copy(self):
        src = os.path.join(self.tmp.name, "book\x7f.xlsx")
        with open(src, "wb") as fh:
            fh.write(b"fourth")
        kind_dir = os.path.join(self.root, "raw", "projects", "demo", "2026-08-31", "stories")
        code, _ = self.run_cli(src)
        self.assertEqual(code, 1)
        self.assertIn("cannot archive as", self.last_stderr)
        self.assertIn("or holds a newline, DEL, a C1 control other than U+0085, U+FFFE or U+FFFF", self.last_stderr)
        code, _ = self.run_cli(self.src, label="v1\x80")
        self.assertEqual(code, 1)
        self.assertIn("label must be one line with no DEL, C1 control other than U+0085, U+FFFE or U+FFFF", self.last_stderr)
        self.assertFalse(os.path.exists(kind_dir))

    def test_a_handle_the_runtime_would_refuse_is_refused_up_front(self):
        for handle in ("Demo", "demo/x", "demo/../demo", "..", ".", ""):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), mock.patch.object(st, "load", side_effect=AssertionError("state loaded")):
                code = sn.main(["--knowledge-root", self.root, "--handle", handle, "--kind", "stories",
                                "--label", "v1", "--received", "2026-08-31", self.src])
            self.assertEqual(code, 1, handle)
            self.assertEqual(err.getvalue(), "snapshot: handle must be a lowercase letter followed by lowercase letters, "
                             "digits or hyphens, got %r\n" % handle, handle)

    def test_rejects_full_width_digits_in_the_date(self):
        code, _ = self.run_cli(self.src, received="２０２６-08-31")
        self.assertEqual(code, 1)
        self.assertIn("--received must be YYYY-MM-DD", self.last_stderr)

    def test_a_resave_of_the_same_workbook_is_not_a_new_revision(self):
        import zipfile
        a = os.path.join(self.tmp.name, "wb v1.xlsx")
        b = os.path.join(self.tmp.name, "wb v1 again.xlsx")
        for path, when in ((a, "2026-09-20T10:15:53Z"), (b, "2026-09-21T03:18:51Z")):
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("xl/worksheets/sheet1.xml", b"<sheet/>")
                z.writestr("docProps/core.xml",
                           b"<c><dcterms:modified>" + when.encode() + b"</dcterms:modified></c>")
        code, first = self.run_cli(a)
        self.assertEqual(code, 0)
        self.assertIsNone(first["duplicate_of"])
        code, second = self.run_cli(b, received="2026-09-21", label="v1 again")
        self.assertEqual(code, 0)
        self.assertEqual(second["duplicate_of"], first["path"])
        self.assertEqual(len(st.load(st.index_path(self.root, "demo"))["sources"]), 1)

    def test_a_corrupt_deflate_stream_fails_cleanly(self):
        import zipfile
        p = os.path.join(self.tmp.name, "broken.xlsx")
        with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("xl/worksheets/sheet1.xml", os.urandom(200_000))
        with open(p, "rb") as fh:
            raw = bytearray(fh.read())
        for i in range(1000, 1200):
            raw[i] ^= 0xFF
        with open(p, "wb") as fh:
            fh.write(bytes(raw))
        code, out = self.run_cli(p)
        self.assertEqual(code, 1)
        self.assertTrue(self.last_stderr.startswith("snapshot:"))
        self.assertNotIn("Traceback", self.last_stderr)


if __name__ == "__main__":
    unittest.main()
