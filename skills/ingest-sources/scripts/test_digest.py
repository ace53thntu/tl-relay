import hashlib
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import digest as dg


def write_zip(path, core_modified, sheet=b"<sheet><row>a</row></sheet>"):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("docProps/core.xml",
                   b'<cp:coreProperties><dcterms:modified>'
                   + core_modified.encode()
                   + b"</dcterms:modified></cp:coreProperties>")


class DigestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.a = os.path.join(self.tmp.name, "a.xlsx")
        self.b = os.path.join(self.tmp.name, "b.xlsx")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_resave_changes_the_file_digest(self):
        write_zip(self.a, "2026-09-20T10:15:53Z")
        write_zip(self.b, "2026-09-21T03:18:51Z")
        self.assertNotEqual(dg.file_sha256(self.a), dg.file_sha256(self.b))

    def test_a_resave_does_not_change_the_content_digest(self):
        write_zip(self.a, "2026-09-20T10:15:53Z")
        write_zip(self.b, "2026-09-21T03:18:51Z")
        self.assertEqual(dg.content_sha256(self.a), dg.content_sha256(self.b))

    def test_a_changed_sheet_does_change_the_content_digest(self):
        write_zip(self.a, "2026-09-20T10:15:53Z")
        write_zip(self.b, "2026-09-20T10:15:53Z", sheet=b"<sheet><row>b</row></sheet>")
        self.assertNotEqual(dg.content_sha256(self.a), dg.content_sha256(self.b))

    def test_a_non_zip_input_digests_its_bytes(self):
        p = os.path.join(self.tmp.name, "stories.md")
        with open(p, "wb") as fh:
            fh.write(b"# stories")
        self.assertEqual(dg.content_sha256(p), dg.file_sha256(p))
        self.assertEqual(dg.content_sha256(p), hashlib.sha256(b"# stories").hexdigest())


if __name__ == "__main__":
    unittest.main()
