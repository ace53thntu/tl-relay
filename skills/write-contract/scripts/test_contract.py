import copy
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contract as c

DOC = {"paths": {
    "/things": {
        "get": {
            "parameters": [{"name": "page", "in": "query", "example": 1},
                           {"name": "pageSize", "in": "query", "example": 20}],
            "responses": {
                "200": {"content": {"application/json": {"example": {"items": [], "page": 1, "pageSize": 20, "total": 0}}}},
                "401": {"content": {"application/json": {"examples": {"unauthenticated": {"value": {
                    "error": {"code": "UNAUTHENTICATED", "message": "Sign in again.", "traceId": "t"}}}}}}},
            }},
        "post": {
            "requestBody": {"content": {"application/json": {"example": {"name": "First"}}}},
            "responses": {"204": {"description": "Created"},
                          "422": {"content": {"application/json": {"example": {"note": "no code"}}}}}},
    },
    "/things/{id}": {
        "parameters": [{"name": "id", "in": "path", "example": "abc"}],
        "get": {"responses": {"200": {"content": {"application/json": {"example": {"id": "abc"}}}}}},
    },
}}


class ContractTest(unittest.TestCase):
    def test_example_error_code_reads_a_nested_body_code(self):
        self.assertEqual(c.example_error_code({"status": "FAILED", "body": {"message": "token expired", "code": 401}}), "401")
        self.assertIsNone(c.example_error_code({"status": 401, "body": {"message": "Invalid Token"}}))
        self.assertIsNone(c.example_error_code({"body": "not an object"}))

    def test_operations_follow_path_then_method_order(self):
        self.assertEqual(c.operations(DOC), ["GET /things", "POST /things", "GET /things/{id}"])

    def test_render_route_parameters_and_named_example(self):
        text = c.render_route(DOC, "GET /things")
        self.assertTrue(text.startswith("**Parameters:**\n\n```json\n"))
        self.assertIn('"pageSize": 20', text)
        self.assertIn("**Response 401 · unauthenticated:**", text)

    def test_render_route_body_and_empty_response(self):
        text = c.render_route(DOC, "POST /things")
        self.assertIn("**Request body · `application/json`:**\n\n```json\n{\n  \"name\": \"First\"\n}\n```", text)
        self.assertIn("**Response 204:**\n\nNo example body.", text)

    def test_path_item_parameters_render(self):
        self.assertIn('"id": "abc"', c.render_route(DOC, "GET /things/{id}"))

    def test_error_codes_and_missing_codes(self):
        self.assertEqual(c.error_codes(DOC, "GET /things"), ([("401", "UNAUTHENTICATED")], []))
        self.assertEqual(c.error_codes(DOC, "POST /things"), ([], ["422"]))

    def test_example_error_code_reads_every_envelope(self):
        self.assertEqual(c.example_error_code({"error": {"code": "THING_NOT_FOUND"}}), "THING_NOT_FOUND")
        self.assertEqual(c.example_error_code({"errorCode": 40901, "errorMessage": "x"}), "40901")
        self.assertIsNone(c.example_error_code({"message": "no code here"}))
        self.assertIsNone(c.example_error_code("not an object"))

    def test_example_error_code_reads_problem_json(self):
        problem = {"type": "about:blank", "title": "Unauthorized", "status": 401, "code": "AUTH_USER_NOT_FOUND"}
        self.assertEqual(c.example_error_code(problem), "AUTH_USER_NOT_FOUND")
        self.assertIsNone(c.example_error_code({"code": "X", "message": "no problem type or status"}))

    def test_application_code_wins_over_the_http_status_beside_it(self):
        value = {"status": "FAILURE", "error": {"code": 409, "message": "Conflict", "responseCode": 7069}}
        self.assertEqual(c.example_error_code(value), "7069")
        self.assertEqual(c.example_error_code({"error": {"code": 401, "message": "Unauthorized"}}), "401")

    def test_error_codes_accepts_a_flat_numeric_envelope(self):
        example = {"errorCode": 40901, "errorMessage": "Already decided."}
        media = {"application/json": {"examples": {"decided": {"value": example}}}}
        op = {"responses": {"409": {"content": media}}}
        doc = {"paths": {"/orders": {"post": op}}}
        self.assertEqual(c.error_codes(doc, "POST /orders"), ([("409", "40901")], []))

    def test_unknown_route_raises(self):
        with self.assertRaises(c.ContractError):
            c.render_route(DOC, "DELETE /things")

    def test_api_route_cells_bare_and_backticked(self):
        api = "| Method and path | Actor |\n| --- | --- |\n| `GET /a/{id}` | x |\n| POST /a | y |\n| `A` path | z |\n"
        self.assertEqual(c.api_route_cells(api), ["GET /a/{id}", "POST /a"])

    def test_api_route_cells_drop_status_token(self):
        api = "| Method · Path | Caller |\n|---|---|\n| `GET /a` {status:New} | x |\n| `POST /a` {status:Changed} | y |\n"
        self.assertEqual(c.api_route_cells(api), ["GET /a", "POST /a"])

    def test_api_route_cells_linked_route(self):
        api = "| Method · Path | Caller |\n|---|---|\n| [`GET /a/{id}`](m/api/4-1-get-a-id.md) {status:New} | x |\n"
        self.assertEqual(c.api_route_cells(api), ["GET /a/{id}"])

    def test_api_route_cells_route_in_second_column(self):
        api = ("| # | Route | Caller · tenancy | Page | Replay |\n|---|---|---|---|---|\n"
               "| [4.1](m/api/4-1-get-a-id.md) | [`GET /a/{id}`](m/api/4-1-get-a-id.md) {status:New} | x | y | z |\n"
               "| 4.2 | `POST /a` | x | y | z |\n")
        self.assertEqual(c.api_route_cells(api), ["GET /a/{id}", "POST /a"])

    def test_api_route_cells_linked_route_with_trailing_summary(self):
        api = ("| # | Route | Caller |\n|---|---|---|\n"
               "| 4.1 | [`GET /pickup-slots`](m/api/4-1-get-pickup-slots.md). Slot availability for a date range ([UC-9](u.md)) | x |\n"
               "| 4.2 | `POST /a` creates a thing | y |\n")
        self.assertEqual(c.api_route_cells(api), ["GET /pickup-slots", "POST /a"])


def _examples(**named):
    return {"content": {"application/json": {"examples": {n: {"value": v} for n, v in named.items()}}}}


VALIDATOR = {"msg": ["must have required property 'correlationId' in correlationId", "must be object"], "errorCode": 400}
NOT_ACCEPTED = {"status": "FAILURE", "error": {"code": 400, "message": "Bad Request", "responseCode": 7080,
                                               "responseMessage": "This country does not accept order attachments."}}
AUTH = {"status": 401, "body": {"message": "Invalid Token"}}
JWT = {"status": "FAILED", "body": {"message": "token expired", "code": 401}}
INTERNAL = {"status": "FAILURE", "error": {"code": 500, "message": "Internal Server Error"}}
FLAT = {"errorCode": 40901, "errorMessage": "Already decided."}

TABLE_DOC = {"paths": {"/orders": {"post": {
    "parameters": [{"name": "dryRun", "in": "query", "example": False}],
    "requestBody": {"content": {"application/json": {"example": {"name": "First"}}}},
    "responses": {
        "201": {"content": {"application/json": {"example": {"id": "abc"}}}},
        "204": {"description": "Accepted"},
        "400": _examples(**{"invalid-body": VALIDATOR, "not-accepted": NOT_ACCEPTED}),
        "401": _examples(unauthenticated=AUTH, **{"jwt-rejected": JWT}),
        "404": {"description": "Missing"},
        "409": _examples(**{"already-decided": FLAT}),
        "500": _examples(**{"internal-error": INTERNAL}),
    }}}}}
TABLE_ROUTE = "POST /orders"


def _three(first, second, third):
    return {"paths": {"/orders": {"post": {"responses": {
        "400": _examples(a=first, b=second), "401": _examples(c=third)}}}}}


class ParseMarkerTest(unittest.TestCase):
    def test_non_marker_lines_return_none(self):
        for line in ("", "**Parameters:**", c.END, "<!-- another comment -->", "<!-- contract:begin nonsense -->"):
            self.assertIsNone(c.parse_marker(line), line)

    def test_plain_marker_has_no_options(self):
        self.assertEqual(c.parse_marker("<!-- contract:begin GET /things/{id} -->"), ("GET /things/{id}", {}))

    def test_unknown_option_or_value_raises(self):
        for line in ("<!-- contract:begin GET /a colour=red -->", "<!-- contract:begin GET /a errors=grid -->",
                     "<!-- contract:begin GET /a errors -->",
                     "<!-- contract:begin GET /a errors=table -->"):
            with self.assertRaises(c.ContractError, msg=line):
                c.parse_marker(line)

class ErrorTableTest(unittest.TestCase):
    def rows(self, text):
        return [line for line in text.splitlines() if line.startswith("| ") and not line.startswith("| HTTP |")
                and not line.startswith("| ---")]

    def test_problem_detail_is_the_message(self):
        problem = {"type": "auth/forbidden", "title": "FORBIDDEN", "status": 403,
                   "detail": "The session's role may not take this action.", "code": "auth/forbidden"}
        self.assertEqual(c.example_message(problem), "The session's role may not take this action.")

    def test_response_code_reads_each_envelope(self):
        self.assertEqual(c.example_response_code(NOT_ACCEPTED, "400"), "7080")
        self.assertIsNone(c.example_response_code(INTERNAL, "500"))
        self.assertIsNone(c.example_response_code(VALIDATOR, "400"))
        self.assertIsNone(c.example_response_code(AUTH, "401"))
        self.assertIsNone(c.example_response_code(JWT, "401"))
        self.assertEqual(c.example_response_code({"error": {"code": "THING_NOT_FOUND"}}, "404"), "THING_NOT_FOUND")

    def test_table_mode_renders_one_error_block_and_a_row_per_example(self):
        text = c.render_route(_three(VALIDATOR, NOT_ACCEPTED, AUTH), "POST /orders")
        self.assertEqual(text.count("```json"), 1)
        self.assertIn("**Response 400 · b:**\n\n```json", text)
        head, table = text.split("**Error responses:**\n\n")
        self.assertEqual(table.splitlines()[:2], ["| HTTP | Response code | Example | Message |", "| --- | --- | --- | --- |"])
        self.assertEqual(len(self.rows(table)), 3)
        self.assertNotIn("**Response 401", text)

    def test_error_block_falls_back_to_the_first_example_when_no_example_has_a_code(self):
        text = c.render_route(_three(VALIDATOR, AUTH, JWT), "POST /orders")
        self.assertIn("**Response 400 · a:**", text)
        self.assertEqual(text.count("```json"), 1)

    def test_success_and_empty_responses_render_before_the_errors(self):
        text = c.render_route(TABLE_DOC, TABLE_ROUTE)
        self.assertLess(text.index("**Response 204:**\n\nNo example body."), text.index("**Error responses:**"))
        self.assertEqual(text.count("```json"), 4)

    def test_rows_hold_status_code_example_and_message_in_contract_order(self):
        table = c.render_route(TABLE_DOC, TABLE_ROUTE).split("**Error responses:**\n\n")[1]
        self.assertEqual(self.rows(table), [
            "| 400 | none | invalid-body | must have required property 'correlationId' in correlationId; must be object |",
            "| 400 | `7080` | not-accepted | This country does not accept order attachments. |",
            "| 401 | none | unauthenticated | Invalid Token |",
            "| 401 | none | jwt-rejected | token expired |",
            "| 404 | none | none | none |",
            "| 409 | `40901` | already-decided | Already decided. |",
            "| 500 | none | internal-error | Internal Server Error |",
        ])

    def test_response_message_wins_over_message(self):
        table = c.render_route(TABLE_DOC, TABLE_ROUTE)
        self.assertNotIn("| Bad Request |", table)

    def test_a_pipe_in_a_message_does_not_split_the_cell(self):
        doc = {"paths": {"/a": {"get": {"responses": {"400": _examples(x={"error": {"code": 400, "message": "a | b"}})}}}}}
        self.assertIn("| a \\| b |", c.render_route(doc, "GET /a"))

    def test_a_route_with_no_error_response_gets_no_table(self):
        self.assertNotIn("Error responses", c.render_route(DOC, "GET /things/{id}"))


class LoadModuleTest(unittest.TestCase):
    def test_skips_group_pages(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "mod", "api"))
            for name in ("4-1-get-things.md", "group-shared.md"):
                with open(os.path.join(d, "mod", "api", name), "w") as fh:
                    fh.write("x")
            lld = os.path.join(d, "mod-api.md")
            open(lld, "w").close()
            _, pages, _ = c.load_module(lld, "mod", lld)
        self.assertEqual(sorted(pages), ["mod/api/4-1-get-things.md"])


if __name__ == "__main__":
    unittest.main()
