import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contract as c

UNAUTH = {"content": {"application/json": {"examples": {"unauthenticated": {"value": {
    "error": {"code": "UNAUTHENTICATED", "message": "Sign in again."}}}}}}}
NOT_FOUND = {"content": {"application/json": {"examples": {"missing": {"value": {
    "error": {"code": "THING_NOT_FOUND", "message": "No such thing."}}}}}}}
GONE = {"content": {"application/json": {"examples": {"gone": {"value": {
    "error": {"code": "THING_GONE", "message": "Gone."}}}}}}}


def _doc(ref):
    unauth = {"$ref": "#/components/responses/Unauthenticated"} if ref else UNAUTH
    gone = {"$ref": "#/components/responses/Gone"} if ref else GONE
    return {"paths": {
        "/things": {"get": {"summary": "List things", "responses": {
            "200": {"content": {"application/json": {"example": {"items": []}}}}, "401": unauth}}},
        "/things/{id}": {"get": {
            "summary": "Read a thing",
            "parameters": [{"name": "id", "in": "path", "example": "abc"}],
            "responses": {"200": {"content": {"application/json": {"example": {"id": "abc"}}}},
                          "401": unauth, "404": NOT_FOUND, "410": gone}}}},
        "components": {"responses": {"Unauthenticated": UNAUTH, "Gone": GONE}}}


DOC, RAW = _doc(False), _doc(True)
PAGE1, PAGE2 = "m/api/4-1-get-things.md", "m/api/4-2-get-things-id.md"


class CommonResponseTest(unittest.TestCase):
    def test_identical_rows_print_once(self):
        doc = {"paths": {"/a": {"get": {"responses": {"401": UNAUTH}}}, "/b": {"get": {"responses": {"401": UNAUTH}}}},
               "components": {"responses": {"Unauthenticated": UNAUTH, "Again": UNAUTH}}}
        raw = {"paths": {"/a": {"get": {"responses": {"401": {"$ref": "#/components/responses/Unauthenticated"}}}},
                         "/b": {"get": {"responses": {"401": {"$ref": "#/components/responses/Again"}}}}}}
        raw["paths"]["/c"] = {"get": {"responses": {"401": {"$ref": "#/components/responses/Unauthenticated"}}}}
        raw["paths"]["/d"] = {"get": {"responses": {"401": {"$ref": "#/components/responses/Again"}}}}
        doc["paths"]["/c"] = {"get": {"responses": {"401": UNAUTH}}}
        doc["paths"]["/d"] = {"get": {"responses": {"401": UNAUTH}}}
        self.assertEqual(c.render_common(doc, raw).count("| 401 | `UNAUTHENTICATED` |"), 1)

    def test_common_responses_need_two_routes(self):
        self.assertEqual(c.common_responses(RAW),
                         {"Unauthenticated": [("GET /things", "401"), ("GET /things/{id}", "401")]})

    def test_common_statuses(self):
        self.assertEqual(c.common_statuses(RAW, "GET /things/{id}"), frozenset({"401"}))
        self.assertEqual(c.common_statuses(DOC, "GET /things/{id}"), frozenset())

    def test_render_route_skips_only_common_statuses(self):
        text = c.render_route(DOC, "GET /things/{id}", skip=frozenset({"401"}))
        self.assertNotIn("UNAUTHENTICATED", text)
        self.assertIn("`THING_NOT_FOUND`", text)
        self.assertIn("`THING_GONE`", text)

    def test_render_common_lists_each_common_response_once(self):
        text = c.render_common(DOC, RAW)
        self.assertIn("| 401 | `UNAUTHENTICATED` | unauthenticated | Sign in again. |", text)
        self.assertEqual(text.count("UNAUTHENTICATED"), 2)
        self.assertNotIn("THING_NOT_FOUND", text)

    def test_render_common_without_common_responses(self):
        self.assertEqual(c.render_common(DOC, DOC), "None.")


class MarkerTest(unittest.TestCase):
    def test_common_marker_parses(self):
        self.assertEqual(c.parse_marker("<!-- contract:begin common-errors -->"), (c.COMMON, {}))

    def test_marker_blocks_in_order(self):
        text = (f"{c.BEGIN.format(route='GET /a')}\nx\n{c.END}\n\nprose\n\n"
                f"{c.BEGIN.format(route=c.COMMON)}\ny\n{c.END}\n")
        self.assertEqual(c.marker_blocks(text), [("GET /a", "x"), (c.COMMON, "y")])

    def test_marker_without_end_raises(self):
        with self.assertRaises(c.ContractError):
            c.marker_blocks(f"{c.BEGIN.format(route='GET /a')}\nx\n")

    def test_table_routes_read_only_section_4(self):
        lld = ("# m\n\n## 4. Interface contracts\n\n| # | Route |\n| --- | --- |\n"
               f"| 4.1 | [`GET /things`]({PAGE1}) |\n\n## 5. Next\n\n| 5.1 | [`GET /other`](x.md) |\n")
        self.assertEqual(c.table_routes(lld), [("GET /things", PAGE1)])

    def test_page_name(self):
        self.assertEqual(c.page_name(8, "GET /purchases/{orderId}"), "4-8-get-purchases-orderid.md")
        self.assertEqual(c.page_name(2, "POST /api/v1/week-plans"), "4-2-post-api-v1-week-plans.md")


class RenderModuleTest(unittest.TestCase):
    def test_render_module_creates_pages_and_contracts(self):
        pages, contracts = c.render_module(DOC, RAW, "m", {}, "")
        self.assertEqual(sorted(pages), [PAGE1, PAGE2])
        self.assertNotIn("UNAUTHENTICATED", pages[PAGE2])
        self.assertIn("`THING_NOT_FOUND`", pages[PAGE2])
        self.assertIn("](../interface-contracts.md)", pages[PAGE2])
        self.assertIn("**Rules:**", pages[PAGE2])
        self.assertIn("## Common errors", contracts)
        self.assertIn("`UNAUTHENTICATED`", contracts)

    def test_route_page_title_leads_with_the_summary(self):
        pages, _ = c.render_module(DOC, RAW, "m", {}, "")
        self.assertIn('title: "API 4.2: GET /things/{id} - Read a thing"', pages[PAGE2])
        self.assertIn("# API 4.2: GET /things/{id} - Read a thing\n", pages[PAGE2])

    def test_route_without_summary_is_titled_by_its_route(self):
        doc = {"paths": {"/a": {"get": {"responses": {"401": UNAUTH}}}}}
        pages, _ = c.render_module(doc, doc, "m", {}, "")
        self.assertIn('title: "API 4.1: GET /a"', pages["m/api/4-1-get-a.md"])

    def test_render_module_is_idempotent(self):
        pages, contracts = c.render_module(DOC, RAW, "m", {}, "")
        self.assertEqual(c.render_module(DOC, RAW, "m", pages, contracts), (pages, contracts))

    def test_existing_page_keeps_its_name(self):
        named = "m/api/4-2-read.md"
        existing = {named: (f"intro\n\n{c.BEGIN.format(route='GET /things/{id}')}\nstale\n{c.END}\n\n"
                            "**Rules:**\n\n- kept\n")}
        pages, _ = c.render_module(DOC, RAW, "m", existing, "")
        self.assertNotIn(PAGE2, pages)
        self.assertIn("- kept", pages[named])
        self.assertNotIn("stale", pages[named])

    def test_existing_contracts_page_gains_common_errors(self):
        contracts = "---\ntype: LLD\n---\n\n# m API\n\n## Access control\n\nRules.\n"
        _, out = c.render_module(DOC, RAW, "m", {}, contracts)
        self.assertTrue(out.startswith(contracts.rstrip("\n")))
        self.assertIn("## Common errors\n\n" + c.BEGIN.format(route=c.COMMON), out)

    def test_marker_for_a_route_not_in_the_contract_is_left_alone(self):
        page = f"{c.BEGIN.format(route='GET /gone')}\nold\n{c.END}\n"
        self.assertEqual(c.fill_markers(DOC, RAW, page), page)


if __name__ == "__main__":
    unittest.main()
