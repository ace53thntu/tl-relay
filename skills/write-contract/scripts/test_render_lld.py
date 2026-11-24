import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render_lld as r

FIXTURES = os.path.join(HERE, "fixtures")


class RenderLldCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for name in os.listdir(FIXTURES):
            shutil.copy(os.path.join(FIXTURES, name), self.tmp.name)
        self.args = ["--contract", os.path.join(self.tmp.name, "demo.openapi.yaml"),
                     "--lld", os.path.join(self.tmp.name, "demo-lld.md")]
        self.module = os.path.join(self.tmp.name, "demo-lld")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *extra):
        with contextlib.redirect_stdout(io.StringIO()):
            return r.main(self.args + list(extra))

    def read(self, *parts):
        with open(os.path.join(*parts), encoding="utf-8") as fh:
            return fh.read()

    def test_writes_route_pages_and_leaves_the_lld_alone(self):
        before = self.read(self.tmp.name, "demo-lld.md")
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(self.read(self.tmp.name, "demo-lld.md"), before)
        self.assertEqual(sorted(os.listdir(os.path.join(self.module, "api"))),
                         ["4-1-get-things.md", "4-2-post-things.md", "4-3-get-things-id.md"])
        self.assertIn("## Common errors", self.read(self.module, "interface-contracts.md"))
        self.assertNotIn("UNAUTHENTICATED", self.read(self.module, "api", "4-3-get-things-id.md"))

    def test_check_reports_stale_then_up_to_date(self):
        self.assertEqual(self.run_cli("--check"), 1)
        self.assertEqual(self.run_cli(), 0)
        self.assertEqual(self.run_cli("--check"), 0)
        page = os.path.join(self.module, "api", "4-3-get-things-id.md")
        text = self.read(page)
        with open(page, "w", encoding="utf-8") as fh:
            fh.write(text.replace('"name": "First"', '"name": "Edited"'))
        self.assertEqual(self.run_cli("--check"), 1)


class CommonFlagTest(unittest.TestCase):
    setUp = RenderLldCliTest.setUp
    tearDown = RenderLldCliTest.tearDown
    run_cli = RenderLldCliTest.run_cli
    read = RenderLldCliTest.read

    def setUp(self):
        RenderLldCliTest.setUp(self)
        self.common = os.path.join(self.tmp.name, "demo-api.md")
        self.args += ["--common", self.common]

    def test_common_flag_renders_block_into_given_page(self):
        self.assertEqual(self.run_cli(), 0)
        self.assertIn("## Common errors", self.read(self.common))
        self.assertIn("UNAUTHENTICATED", self.read(self.common))
        self.assertFalse(os.path.exists(os.path.join(self.module, "interface-contracts.md")))

    def test_new_route_page_links_common_page(self):
        self.run_cli()
        first = self.read(self.module, "api", "4-1-get-things.md").split("# API 4.1")[1]
        self.assertIn("(../../demo-api.md)", first)
        self.assertIn("(../../demo-api.md#common-errors)", first)

    def test_default_keeps_interface_contracts(self):
        self.args = self.args[:-2]
        self.assertEqual(self.run_cli(), 0)
        self.assertIn("## Common errors", self.read(self.module, "interface-contracts.md"))
        self.assertIn("(../interface-contracts.md#common-errors)",
                      self.read(self.module, "api", "4-1-get-things.md"))
        self.assertNotIn("Common errors", self.read(self.common))

    def test_text_outside_the_markers_is_untouched(self):
        head = "# Demo API\n\nShared rules stay.\n\n## Common errors\n\n"
        tail = "\n\nTrailing prose.\n"
        with open(self.common, "w", encoding="utf-8") as fh:
            fh.write(head + "<!-- contract:begin common-errors -->\nold\n<!-- contract:end -->" + tail)
        self.assertEqual(self.run_cli(), 0)
        text = self.read(self.common)
        self.assertTrue(text.startswith(head + "<!-- contract:begin common-errors -->\n"))
        self.assertTrue(text.endswith("<!-- contract:end -->" + tail))
        self.assertNotIn("\nold\n", text)

    def test_page_without_block_gets_one_appended(self):
        with open(self.common, "w", encoding="utf-8") as fh:
            fh.write("# Demo API\n\nRules.\n")
        self.assertEqual(self.run_cli(), 0)
        text = self.read(self.common)
        self.assertTrue(text.startswith("# Demo API\n\nRules.\n"))
        self.assertIn("\n## Common errors\n\n<!-- contract:begin common-errors -->\n", text)

    def test_check_names_the_common_page(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(r.main(self.args + ["--check"]), 1)
        self.assertIn(self.common, out.getvalue())


class RetitleTest(unittest.TestCase):
    setUp = RenderLldCliTest.setUp
    tearDown = RenderLldCliTest.tearDown
    run_cli = RenderLldCliTest.run_cli
    read = RenderLldCliTest.read

    def edit(self, path, old, new):
        text = self.read(path)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, new))

    def test_render_keeps_the_title_of_an_existing_page(self):
        self.run_cli()
        contract = os.path.join(self.tmp.name, "demo.openapi.yaml")
        self.edit(contract, "summary: Read a thing", "summary: Read one thing")
        self.run_cli()
        self.assertIn('title: "API 4.3: GET /things/{id} - Read a thing"',
                      self.read(self.module, "api", "4-3-get-things-id.md"))

    def test_retitle_follows_the_summary_and_drops_the_prefix(self):
        self.run_cli()
        page = os.path.join(self.module, "api", "4-3-get-things-id.md")
        self.edit(page, "API 4.3:", "Demo Shop API 4.3:")
        self.edit(os.path.join(self.tmp.name, "demo.openapi.yaml"), "summary: Read a thing", "summary: Read one thing")
        self.assertEqual(self.run_cli("--retitle"), 0)
        text = self.read(page)
        new = "API 4.3: GET /things/{id} - Read one thing"
        self.assertIn(f'title: "{new}"', text)
        self.assertIn(f"\n# {new}\n", text)
        self.assertIn('title: "API 4.1: GET /things - List things"',
                      self.read(self.module, "api", "4-1-get-things.md"))

    def test_retitle_replaces_a_title_in_another_form(self):
        self.run_cli()
        page = os.path.join(self.module, "api", "4-1-get-things.md")
        self.edit(page, "API 4.1: GET /things - List things", "Demo route 4.1 GET /things")
        self.assertEqual(self.run_cli("--retitle"), 0)
        self.assertIn('title: "API 4.1: GET /things - List things"', self.read(page))


if __name__ == "__main__":
    unittest.main()
