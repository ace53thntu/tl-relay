import contextlib
import copy
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_contract as cc
import contract as c
import render_lld as r

FIXTURES = os.path.join(HERE, "fixtures")
CONFIG = os.path.join(os.path.dirname(HERE), "redocly.yaml")
PAGE1, PAGE2 = "m/api/4-1-get-things.md", "m/api/4-2-get-things-id.md"


class CheckDocsTest(unittest.TestCase):
    def setUp(self):
        self.pages, self.contracts = c.render_module(cc.SELF_DOC, cc.SELF_RAW, "m", {}, "")

    def check(self, doc=None, lld=None, api=None, pages=None, contracts=None):
        return cc.check_docs(doc or cc.SELF_DOC, cc.SELF_RAW, cc.SELF_LLD if lld is None else lld,
                             cc.SELF_API if api is None else api, self.pages if pages is None else pages,
                             self.contracts if contracts is None else contracts)

    def test_clean_fixture_has_no_problems(self):
        self.assertEqual(self.check(), [])

    def test_missing_table_row_is_check2(self):
        self.assertIn(("check2", "GET /things/{id} has no row in LLD section 4"),
                      self.check(lld=cc.SELF_LLD.replace(cc.SELF_ROW2, "")))

    def test_row_linking_the_wrong_page_is_check2(self):
        problems = self.check(lld=cc.SELF_LLD.replace("4-2-get-things-id.md", "4-1-get-things.md"))
        self.assertIn(("check2", f"LLD row GET /things/{{id}} links {PAGE1}, not its route page"), problems)

    def test_page_with_two_markers_is_check2(self):
        pages = dict(self.pages)
        pages[PAGE1] += f"\n{c.BEGIN.format(route='GET /things/{id}')}\n{c.END}\n"
        self.assertIn(("check2", f"{PAGE1} has 2 route markers; a route page has exactly one"),
                      self.check(pages=pages))

    def test_missing_page_is_check2(self):
        pages = {k: v for k, v in self.pages.items() if k != PAGE2}
        self.assertIn(("check2", "GET /things/{id} has no route page; run render_lld.py"), self.check(pages=pages))

    def test_page_for_a_removed_route(self):
        pages = dict(self.pages)
        pages["m/api/4-9-get-gone.md"] = f"{c.BEGIN.format(route='GET /gone')}\nold\n{c.END}\n"
        self.assertIn(("check2", "route page m/api/4-9-get-gone.md renders GET /gone, which is not in the contract"),
                      self.check(pages=pages))

    def test_colon_parameter_on_api_page_is_check2(self):
        problems = self.check(api=cc.SELF_API.replace("{id}", ":id"))
        self.assertIn(("check2", "GET /things/{id} is not on the API page"), problems)
        self.assertIn(("check2", "API page route GET /things/:id is not in the contract"), problems)

    def test_edited_route_example_is_check3(self):
        pages = dict(self.pages)
        pages[PAGE2] = pages[PAGE2].replace('"id": "abc"', '"id": "xyz"')
        self.assertEqual({k for k, _ in self.check(pages=pages)}, {"check3"})

    def test_edited_common_block_is_check3(self):
        contracts = self.contracts.replace("Sign in again.", "Edited.")
        self.assertEqual({k for k, _ in self.check(contracts=contracts)}, {"check3"})

    def test_missing_common_block_is_check3(self):
        self.assertIn(("check3", "interface-contracts.md needs exactly one common-errors block; run render_lld.py"),
                      self.check(contracts="# m API\n"))

    def test_error_response_without_code_is_check4(self):
        doc = copy.deepcopy(cc.SELF_DOC)
        doc["paths"]["/things/{id}"]["get"]["responses"]["404"] = {
            "content": {"application/json": {"example": {"message": "no code"}}}}
        pages, contracts = c.render_module(doc, cc.SELF_RAW, "m", {}, "")
        problems = cc.check_docs(doc, cc.SELF_RAW, cc.SELF_LLD, cc.SELF_API, pages, contracts)
        self.assertIn(("check4", "GET /things/{id} 404 has no example carrying error.code"), problems)

    def test_self_test_passes(self):
        cc.self_test()


class RedoclyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for name in os.listdir(FIXTURES):
            shutil.copy(os.path.join(FIXTURES, name), self.tmp.name)
        self.yaml = os.path.join(self.tmp.name, "demo.openapi.yaml")
        self.lld = os.path.join(self.tmp.name, "demo-lld.md")
        self.api = os.path.join(self.tmp.name, "demo-api.md")

    def tearDown(self):
        self.tmp.cleanup()

    def test_lint_passes_the_good_fixture(self):
        code, output = c.lint(self.yaml, CONFIG)
        self.assertEqual(code, 0, output)

    def test_lint_fails_a_wrong_example(self):
        with open(self.yaml, encoding="utf-8") as fh:
            text = fh.read()
        with open(self.yaml, "w", encoding="utf-8") as fh:
            fh.write(text.replace("total: 1", "total: one", 1))
        code, output = c.lint(self.yaml, CONFIG)
        self.assertNotEqual(code, 0)
        self.assertIn("no-invalid-media-type-examples", output)

    def test_bundle_dereferences_the_shared_components(self):
        doc = c.bundle(self.yaml)
        get = doc["paths"]["/things"]["get"]
        self.assertEqual([p["name"] for p in get["parameters"]], ["page", "pageSize"])
        self.assertEqual(c.error_codes(doc, "GET /things"), ([("401", "UNAUTHENTICATED"), ("403", "FORBIDDEN")], []))

    def test_reference_bundle_keeps_the_response_refs(self):
        raw = c.bundle(self.yaml, dereferenced=False)
        self.assertEqual(raw["paths"]["/things"]["get"]["responses"]["401"],
                         {"$ref": "#/components/responses/Unauthenticated"})
        self.assertEqual(sorted(c.common_responses(raw)), ["Forbidden", "Unauthenticated"])

    def test_cli_renders_then_passes_then_fails_on_a_dropped_row(self):
        args = ["--contract", self.yaml, "--lld", self.lld]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(r.main(args), 0)
            self.assertEqual(r.main(args + ["--check"]), 0)
            self.assertEqual(cc.main(args + ["--api", self.api, "--config", CONFIG]), 0)
        with open(self.lld, encoding="utf-8") as fh:
            text = fh.read()
        with open(self.lld, "w", encoding="utf-8") as fh:
            fh.write(text.replace("| 4.3 | [`GET /things/{id}`](demo-lld/api/4-3-get-things-id.md) | Admin | none | none |\n", ""))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cc.main(args + ["--api", self.api, "--config", CONFIG]), 1)
        self.assertIn("check2: GET /things/{id} has no row in LLD section 4", out.getvalue())


    def test_cli_reports_a_missing_npx_as_check1(self):
        args = ["--contract", self.yaml, "--lld", self.lld, "--api", self.api, "--config", CONFIG]
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as empty, mock.patch.dict(os.environ, {"PATH": empty}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cc.main(args), 1)
        self.assertIn("check1: npx not found", out.getvalue())


class ModuleFlagTest(unittest.TestCase):
    def test_route_table_on_an_api_child_passes_with_module(self):
        with tempfile.TemporaryDirectory() as tmp:
            lld_dir = os.path.join(tmp, "lld")
            os.makedirs(lld_dir)
            for name in ("common.openapi.yaml", "demo.openapi.yaml"):
                shutil.copy(os.path.join(FIXTURES, name), tmp)
            with open(os.path.join(FIXTURES, "demo-lld.md"), encoding="utf-8") as fh:
                table = fh.read().replace("demo-lld/", "demo/")
            lld = os.path.join(lld_dir, "demo-api.md")
            with open(lld, "w", encoding="utf-8") as fh:
                fh.write(table)
            api = os.path.join(tmp, "hla.md")
            shutil.copy(os.path.join(FIXTURES, "demo-api.md"), api)
            args = ["--contract", os.path.join(tmp, "demo.openapi.yaml"), "--lld", lld, "--module", "demo"]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(r.main(args), 0)
                self.assertTrue(os.path.isdir(os.path.join(lld_dir, "demo", "api")))
                self.assertEqual(cc.main(args + ["--api", api, "--config", CONFIG]), 0)


class CheckCommonFlagTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for name in os.listdir(FIXTURES):
            shutil.copy(os.path.join(FIXTURES, name), self.tmp.name)
        self.common = os.path.join(self.tmp.name, "demo-api.md")
        self.args = ["--contract", os.path.join(self.tmp.name, "demo.openapi.yaml"),
                     "--lld", os.path.join(self.tmp.name, "demo-lld.md")]

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, main, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(self.args + list(extra))
        return code, out.getvalue()

    def check(self, *extra):
        return self.run_main(cc.main, "--api", self.common, "--config", CONFIG, *extra)

    def test_check_uses_common_page(self):
        self.assertEqual(self.run_main(r.main, "--common", self.common)[0], 0)
        self.assertEqual(self.check("--common", self.common)[0], 0)
        with open(self.common, encoding="utf-8") as fh:
            text = fh.read()
        with open(self.common, "w", encoding="utf-8") as fh:
            fh.write(text.replace("Sign in again.", "Edited."))
        code, out = self.check("--common", self.common)
        self.assertEqual(code, 1)
        self.assertIn("check3: the common-errors block differs from the contract", out)

    def test_missing_block_message_names_the_common_page(self):
        self.run_main(r.main, "--common", self.common)
        code, out = self.check("--common", os.path.join(self.tmp.name, "demo-lld.md"))
        self.assertEqual(code, 1)
        self.assertIn(f"check3: {os.path.join(self.tmp.name, 'demo-lld.md')} needs exactly one common-errors block", out)

    def test_lld_page_can_be_the_common_page(self):
        lld = os.path.join(self.tmp.name, "demo-lld.md")
        self.assertEqual(self.run_main(r.main, "--common", lld)[0], 0)
        self.assertEqual(self.check("--common", lld)[0], 0)

    def test_default_keeps_interface_contracts(self):
        self.assertEqual(self.run_main(r.main)[0], 0)
        self.assertEqual(self.check()[0], 0)
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "demo-lld", "interface-contracts.md")))


if __name__ == "__main__":
    unittest.main()
