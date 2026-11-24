#!/usr/bin/env python3
"""Check an OpenAPI contract against its LLD, its route pages and its route list. Exit 0 only when all four checks pass."""
import argparse
import copy
import os
import sys

from contract import (BEGIN, COMMON, END, ContractError, api_route_cells, bundle, common_statuses, error_codes,
                      lint, load_module, marker_blocks, operations, render_common, render_module, render_route,
                      table_routes)

DEFAULT_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "redocly.yaml")

SELF_UNAUTH = {"content": {"application/json": {"example": {
    "error": {"code": "UNAUTHENTICATED", "message": "Sign in again."}}}}}
SELF_MISSING = {"content": {"application/json": {"example": {
    "error": {"code": "THING_NOT_FOUND", "message": "No such thing."}}}}}


def _self_doc(ref):
    unauth = {"$ref": "#/components/responses/Unauthenticated"} if ref else SELF_UNAUTH
    return {"paths": {
        "/things": {"get": {"responses": {
            "200": {"content": {"application/json": {"example": {"items": []}}}}, "401": unauth}}},
        "/things/{id}": {"get": {
            "parameters": [{"name": "id", "in": "path", "example": "abc"}],
            "responses": {"200": {"content": {"application/json": {"example": {"id": "abc"}}}},
                          "401": unauth, "404": SELF_MISSING}}}},
        "components": {"responses": {"Unauthenticated": SELF_UNAUTH}}}


SELF_DOC, SELF_RAW = _self_doc(False), _self_doc(True)
SELF_API = ("| Method and path | Actor | Purpose |\n| --- | --- | --- |\n"
            "| `GET /things` | Any | list |\n| `GET /things/{id}` | Any | read |\n")
SELF_ROW2 = "| 4.2 | [`GET /things/{id}`](m/api/4-2-get-things-id.md) | Any | none | none |\n"
SELF_LLD = ("# m\n\n## 4. Interface contracts and API specifications\n\n"
            "| # | Route | Caller · tenancy | Page | Replay |\n| --- | --- | --- | --- | --- |\n"
            "| 4.1 | [`GET /things`](m/api/4-1-get-things.md) | Any | none | none |\n" + SELF_ROW2 + "\n## 5. Next\n")


def check_docs(doc, raw, lld_text, api_text, pages, contracts_text, common_name="interface-contracts.md"):
    problems = []
    ops = operations(doc)
    rows = table_routes(lld_text)
    row_routes = [route for route, _ in rows]
    cells = api_route_cells(api_text)
    page_of = {}
    for key, text in sorted(pages.items()):
        routes = [k for k, _ in marker_blocks(text) if k != COMMON]
        if len(routes) != 1:
            problems.append(("check2", f"{key} has {len(routes)} route markers; a route page has exactly one"))
        for route in routes:
            page_of.setdefault(route, []).append(key)
    for r in ops:
        if r not in row_routes:
            problems.append(("check2", f"{r} has no row in LLD section 4"))
        if r not in cells:
            problems.append(("check2", f"{r} is not on the API page"))
        if r not in page_of:
            problems.append(("check2", f"{r} has no route page; run render_lld.py"))
    problems += [("check2", f"LLD row {r} is not in the contract") for r in row_routes if r not in ops]
    problems += [("check2", f"API page route {r} is not in the contract") for r in cells if r not in ops]
    problems += [("check2", f"route page {k} renders {r}, which is not in the contract")
                 for r, keys in page_of.items() if r not in ops for k in keys]
    for r, href in rows:
        if r in page_of and os.path.normpath(href) not in page_of[r]:
            problems.append(("check2", f"LLD row {r} links {href}, not its route page"))
    for key, text in sorted(pages.items()):
        for r, body in marker_blocks(text):
            if r in ops and body != render_route(doc, r, skip=common_statuses(raw, r)):
                problems.append(("check3", f"{key} block for {r} differs from the contract; run render_lld.py"))
    common = [body for k, body in marker_blocks(contracts_text) if k == COMMON]
    if len(common) != 1:
        problems.append(("check3", f"{common_name} needs exactly one common-errors block; run render_lld.py"))
    elif common[0] != render_common(doc, raw):
        problems.append(("check3", "the common-errors block differs from the contract; run render_lld.py"))
    for r in ops:
        _, missing = error_codes(doc, r)
        problems += [("check4", f"{r} {s} has no example carrying error.code") for s in missing]
    return problems


def self_test():
    pages, contracts = render_module(SELF_DOC, SELF_RAW, "m", {}, "")
    page1, page2 = "m/api/4-1-get-things.md", "m/api/4-2-get-things-id.md"
    two = dict(pages)
    two[page1] += f"\n{BEGIN.format(route='GET /things/{id}')}\n{END}\n"
    edited = dict(pages)
    edited[page2] = pages[page2].replace('"id": "abc"', '"id": "xyz"')
    nocode = copy.deepcopy(SELF_DOC)
    nocode["paths"]["/things/{id}"]["get"]["responses"]["404"] = {
        "content": {"application/json": {"example": {"message": "no code"}}}}
    failures = []
    clean = check_docs(SELF_DOC, SELF_RAW, SELF_LLD, SELF_API, pages, contracts)
    if clean:
        failures.append(f"clean fixture reported {clean}")
    cases = (
        ("check2", "page without a row", SELF_DOC, SELF_LLD.replace(SELF_ROW2, ""), pages, contracts),
        ("check2", "row linking the wrong page", SELF_DOC,
         SELF_LLD.replace("4-2-get-things-id.md", "4-1-get-things.md"), pages, contracts),
        ("check2", "page with two markers", SELF_DOC, SELF_LLD, two, contracts),
        ("check3", "edited route block", SELF_DOC, SELF_LLD, edited, contracts),
        ("check3", "stale common errors", SELF_DOC, SELF_LLD, pages, contracts.replace("Sign in again.", "Edited.")),
        ("check4", "error without a code", nocode, SELF_LLD, pages, contracts),
    )
    for want, label, doc, lld, pg, ct in cases:
        got = {k for k, _ in check_docs(doc, SELF_RAW, lld, SELF_API, pg, ct)}
        if want not in got:
            failures.append(f"{want} red undetected for {label}, got {sorted(got)}")
    got = {k for k, _ in check_docs(SELF_DOC, SELF_RAW, SELF_LLD, SELF_API.replace("{id}", ":id"), pages, contracts)}
    if "check2" not in got:
        failures.append(f"check2 red undetected for API page route, got {sorted(got)}")
    if failures:
        for f in failures:
            print(f"check-contract self-test: {f}", file=sys.stderr)
        sys.exit(3)


def main(argv=None):
    self_test()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--contract", required=True)
    p.add_argument("--lld", required=True)
    p.add_argument("--api", required=True)
    p.add_argument("--module")
    p.add_argument("--common")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    args = p.parse_args(argv)
    problems = []
    code, output = lint(args.contract, args.config)
    if code != 0:
        print(output[-3000:], file=sys.stderr)
        problems.append(("check1", f"redocly lint exited {code}"))
    try:
        doc, raw = bundle(args.contract), bundle(args.contract, dereferenced=False)
        with open(args.lld, encoding="utf-8") as fh:
            lld = fh.read()
        with open(args.api, encoding="utf-8") as fh:
            api = fh.read()
        _, pages, contracts = load_module(args.lld, args.module, args.common)
        problems += check_docs(doc, raw, lld, api, pages, contracts, args.common or "interface-contracts.md")
    except ContractError as e:
        problems.append(("check1", str(e)))
    for c, m in problems:
        print(f"{c}: {m}")
    print(f"check-contract: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
