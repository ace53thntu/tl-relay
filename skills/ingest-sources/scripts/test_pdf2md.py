import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
PYPDF = importlib.util.find_spec("pypdf") is not None
if PYPDF:
    import pdf2md


def make_pdf(path, texts):
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [" + " ".join(f"{4 + 2 * i} 0 R" for i in range(len(texts)))
            + f"] /Count {len(texts)} >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i, t in enumerate(texts):
        stream = f"BT /F1 24 Tf 72 720 Td ({t}) Tj ET"
        objs.append("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>")
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream")
    out, offsets = b"%PDF-1.4\n", []
    for n, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{off:010d} 00000 n \n" for off in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    with open(path, "wb") as fh:
        fh.write(out)


@unittest.skipUnless(PYPDF, "pypdf is missing; run with a Python that has ingest-sources/requirements.txt installed")
class Pdf2MdTest(unittest.TestCase):
    def test_extracts_each_page_under_its_own_heading(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.pdf")
            make_pdf(path, ["Hello design", "Second page"])
            pages, md = pdf2md.convert(path)
        self.assertEqual(pages, 2)
        self.assertIn("## Page 1\n\nHello design", md)
        self.assertIn("## Page 2\n\nSecond page", md)

    @unittest.skipUnless(os.environ.get("INGEST_LIVE_DIR"), "set INGEST_LIVE_DIR to read the PRD")
    def test_real_prd(self):
        pages, md = pdf2md.convert(os.path.join(os.environ["INGEST_LIVE_DIR"], "prd.pdf"))
        self.assertEqual(pages, 29)
        self.assertIn("Spam Act", md)


class BrokenPypdfTest(unittest.TestCase):
    def test_a_broken_pypdf_is_not_reported_as_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.mkdir(os.path.join(tmp, "pypdf"))
            with open(os.path.join(tmp, "pypdf", "__init__.py"), "w") as fh:
                fh.write("import a_dependency_that_is_not_installed\n")
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdf2md.py")
            done = subprocess.run([sys.executable, script, "x.pdf"], capture_output=True, text=True,
                                  env=dict(os.environ, PYTHONPATH=tmp))
        self.assertEqual(done.returncode, 1)
        self.assertIn("pdf2md: pypdf failed to import", done.stderr)
        self.assertNotIn("is missing", done.stderr)

    def test_a_missing_pypdf_names_the_real_skill_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "pypdf.py"), "w") as fh:
                fh.write("raise ModuleNotFoundError('x', name='pypdf')\n")
            here = os.path.dirname(os.path.abspath(__file__))
            done = subprocess.run([sys.executable, os.path.join(here, "pdf2md.py"), "x.pdf"], capture_output=True,
                                  text=True, env=dict(os.environ, PYTHONPATH=tmp))
        self.assertIn(os.path.dirname(here) + "/.venv", done.stderr)
        self.assertNotIn("<skill dir>", done.stderr)


if __name__ == "__main__":
    unittest.main()
