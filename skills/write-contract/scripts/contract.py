#!/usr/bin/env python3
"""Shared parsing for write-contract: bundle an OpenAPI yaml, list its routes, render LLD examples."""
import json
import os
import re
import subprocess
import tempfile

REDOCLY = "@redocly/cli@2.52.1"
METHODS = ["get", "post", "put", "patch", "delete"]
ROUTE_RE = re.compile(r"^(?:GET|POST|PUT|PATCH|DELETE) /")
BEGIN = "<!-- contract:begin {route} -->"
END = "<!-- contract:end -->"
MARKER_RE = re.compile(r"^<!-- contract:begin ((?:GET|POST|PUT|PATCH|DELETE) \S+|common-errors)((?: \S+)*) -->$")
COMMON = "common-errors"
RESPONSE_REF = "#/components/responses/"
TABLE_LINK_RE = re.compile(r"\[`?((?:GET|POST|PUT|PATCH|DELETE) /[^\]`]*)`?\]\(([^)\s]+)\)")
BARE_ROUTE_RE = re.compile(r"^`?((?:GET|POST|PUT|PATCH|DELETE) /[^`\s]*)")
MARKER_OPTIONS = {}


class ContractError(Exception):
    pass


def fenced_flags(lines):
    flags, inside = [], False
    for line in lines:
        fence = line.lstrip().startswith(("```", "~~~"))
        flags.append(inside or fence)
        if fence:
            inside = not inside
    return flags


def parse_marker(line):
    m = MARKER_RE.match(line)
    if not m:
        return None
    options = {}
    for token in m.group(2).split():
        key, eq, value = token.partition("=")
        if not eq or value not in MARKER_OPTIONS.get(key, ()):
            raise ContractError(f"{m.group(1)}: unknown marker option {token}")
        options[key] = value
    return m.group(1), options


def run_redocly(args):
    return subprocess.run(["npx", "--yes", REDOCLY, *args], capture_output=True, text=True)


def bundle(yaml_path, dereferenced=True):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "bundle.json")
        flags = ["--dereferenced"] if dereferenced else []
        r = run_redocly(["bundle", yaml_path, *flags, "--ext", "json", "-o", out])
        if r.returncode != 0 or not os.path.exists(out):
            raise ContractError(f"redocly bundle failed for {yaml_path}: {r.stderr.strip()[-400:]}")
        with open(out, encoding="utf-8") as fh:
            return json.load(fh)


def lint(yaml_path, config):
    r = run_redocly(["lint", "--config", config, yaml_path])
    return r.returncode, r.stdout + r.stderr


def operations(doc):
    ops = []
    for path, item in doc.get("paths", {}).items():
        for m in METHODS:
            if m in item:
                ops.append(f"{m.upper()} {path}")
    return ops


def operation(doc, route):
    method, path = route.split(" ", 1)
    try:
        return doc["paths"][path][method.lower()]
    except KeyError:
        raise ContractError(f"{route} is not in the contract") from None


def _examples(media):
    if "examples" in media:
        return [(name, ex.get("value")) for name, ex in media["examples"].items()]
    if "example" in media:
        return [(None, media["example"])]
    return []


def _json_block(value):
    return "```json\n" + json.dumps(value, indent=2, ensure_ascii=False) + "\n```"


def _is_error(status):
    return status[:1] in ("4", "5")


def render_route(doc, route, skip=frozenset()):
    op = operation(doc, route)
    path_item = doc["paths"][route.split(" ", 1)[1]]
    parts = []
    params = {p["name"]: p["example"] for p in path_item.get("parameters", []) + op.get("parameters", [])
              if "example" in p}
    if params:
        parts.append("**Parameters:**\n\n" + _json_block(params))
    for ctype, media in op.get("requestBody", {}).get("content", {}).items():
        for name, value in _examples(media):
            label = f"**Request body · `{ctype}`" + (f" · {name}" if name else "") + ":**"
            parts.append(label + "\n\n" + _json_block(value))
    failures = []
    for status, resp in op.get("responses", {}).items():
        if status in skip:
            continue
        rendered = False
        for media in resp.get("content", {}).values():
            for name, value in _examples(media):
                if _is_error(status):
                    failures.append((status, name, value))
                else:
                    label = f"**Response {status}" + (f" · {name}" if name else "") + ":**"
                    parts.append(label + "\n\n" + _json_block(value))
                rendered = True
        if not rendered:
            if _is_error(status):
                failures.append((status, None, None))
            else:
                parts.append(f"**Response {status}:**\n\nNo example body.")
    if failures:
        parts += _error_table(failures)
    return "\n\n".join(parts)


def _error_table(failures):
    shown = [f for f in failures if f[2] is not None]
    chosen = next((f for f in shown if example_response_code(f[2], f[0]) is not None), None) or next(iter(shown), None)
    parts = []
    if chosen:
        status, name, value = chosen
        parts.append(f"**Response {status}" + (f" · {name}" if name else "") + ":**\n\n" + _json_block(value))
    rows = ["| HTTP | Response code | Example | Message |", "| --- | --- | --- | --- |"]
    for status, name, value in failures:
        code = example_response_code(value, status)
        cells = [status, f"`{code}`" if code else "none", name or "none", example_message(value) or "none"]
        row = "| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |"
        if row not in rows:
            rows.append(row)
    parts.append("**Error responses:**\n\n" + "\n".join(rows))
    return parts


# Read the most specific application code the example carries. Some services
# nest an envelope under `error` and put the HTTP status in `error.code` with
# the application code beside it in `error.responseCode`; others carry a flat
# `errorCode`, or an RFC 9457 problem body with a top-level `code`. Codes may be
# numbers, so every shape is compared as a string against the LLD table cell.
def example_error_code(value):
    if not isinstance(value, dict):
        return None
    nested = value.get("error")
    if isinstance(nested, dict):
        for key in ("responseCode", "code"):
            if nested.get(key) is not None:
                return str(nested[key])
    if value.get("errorCode") is not None:
        return str(value["errorCode"])
    body = value.get("body")
    if isinstance(body, dict) and body.get("code") is not None:
        return str(body["code"])
    if "type" in value and "status" in value and value.get("code") is not None:
        return str(value["code"])
    return None


def example_response_code(value, status):
    nested = value.get("error") if isinstance(value, dict) else None
    if isinstance(nested, dict) and nested.get("responseCode") is not None:
        return str(nested["responseCode"])
    code = example_error_code(value)
    return None if code == str(status) else code


def example_message(value):
    if not isinstance(value, dict):
        return None
    nested = value.get("error") if isinstance(value.get("error"), dict) else {}
    body = value.get("body") if isinstance(value.get("body"), dict) else {}
    msg = value.get("msg")
    candidates = [nested.get("responseMessage"), value.get("errorMessage"),
                  "; ".join(str(m) for m in msg) if isinstance(msg, list) and msg else None,
                  body.get("message"), nested.get("message"),
                  value.get("detail") if "type" in value and "status" in value else None]
    found = next((m for m in candidates if m), None)
    return None if found is None else str(found)


def error_codes(doc, route):
    op = operation(doc, route)
    codes, missing = [], []
    for status, resp in op.get("responses", {}).items():
        if status[:1] not in ("4", "5"):
            continue
        found = [code for media in resp.get("content", {}).values() for _, v in _examples(media)
                 if (code := example_error_code(v)) is not None]
        if not found:
            missing.append(status)
        codes += [(status, c) for c in found]
    return codes, missing


def section4(lld_text):
    lines = lld_text.splitlines()
    fenced = fenced_flags(lines)
    start = next((i for i, line in enumerate(lines) if line.startswith("## 4.") and not fenced[i]), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ") and not fenced[i]), len(lines))
    return "\n".join(lines[start:end])


def api_route_cells(text):
    cells = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        for raw in line.split("|")[1:]:
            cell = re.sub(r"\s*\{status:[^}]*\}", "", raw).strip()
            m = TABLE_LINK_RE.match(cell) or BARE_ROUTE_RE.match(cell)
            if m:
                cells.append(m.group(1))
                break
    return cells


ROUTE_PAGE = ('---\ntype: LLD\ntitle: "API 4.{n}: {heading}"\ndescription: "{summary}"\nstatus: draft\n---\n\n'
              "# API 4.{n}: {heading}\n\n"
              "Route 4.{n} of the [{module} API]({common}). "
              "The [common errors]({common}#common-errors) apply to this route.\n\n"
              "{begin}\n{end}\n\n**Rules:**\n\nNone.\n")
CONTRACTS_PAGE = ('---\ntype: LLD\ntitle: "{module} API"\n'
                  'description: "Rules every {module} route shares, and its common errors."\nstatus: draft\n---\n\n'
                  "# {module} API\n\n## Common errors\n\n{begin}\n{end}\n")


def common_responses(raw):
    uses = {}
    for route in operations(raw):
        for status, resp in operation(raw, route).get("responses", {}).items():
            ref = resp.get("$ref", "") if isinstance(resp, dict) else ""
            if ref.startswith(RESPONSE_REF):
                uses.setdefault(ref[len(RESPONSE_REF):], []).append((route, status))
    return {name: u for name, u in uses.items() if len({route for route, _ in u}) >= 2}


def common_statuses(raw, route):
    return frozenset(s for u in common_responses(raw).values() for r, s in u if r == route)


def render_common(doc, raw):
    failures = []
    for uses in common_responses(raw).values():
        route, status = uses[0]
        resp = operation(doc, route)["responses"][status]
        found = [(status, name, value) for media in resp.get("content", {}).values()
                 for name, value in _examples(media)]
        failures += found or [(status, None, None)]
    return "\n\n".join(_error_table(failures)) if failures else "None."


def marker_blocks(text):
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        marker = parse_marker(lines[i])
        if not marker:
            i += 1
            continue
        end = next((j for j in range(i + 1, len(lines)) if lines[j] == END), None)
        if end is None:
            raise ContractError(f"{marker[0]}: a begin marker has no end marker")
        out.append((marker[0], "\n".join(lines[i + 1:end]).strip("\n")))
        i = end + 1
    return out


def table_routes(lld_text):
    out = []
    for line in section4(lld_text).splitlines():
        m = TABLE_LINK_RE.search(line) if line.startswith("|") else None
        if m:
            out.append((m.group(1), m.group(2)))
    return out


def page_name(n, route):
    method, path = route.split(" ", 1)
    return f"4-{n}-{method.lower()}-{re.sub(r'[^a-z0-9]+', '-', path.lower()).strip('-')}.md"


def fill_markers(doc, raw, text):
    ops = set(operations(doc))
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        marker = parse_marker(lines[i])
        if not marker:
            out.append(lines[i])
            i += 1
            continue
        key = marker[0]
        end = next((j for j in range(i + 1, len(lines)) if lines[j] == END), None)
        if end is None:
            raise ContractError(f"{key}: a begin marker has no end marker")
        if key == COMMON:
            out += [lines[i], render_common(doc, raw), END]
        elif key in ops:
            out += [lines[i], render_route(doc, key, skip=common_statuses(raw, key)), END]
        else:
            out += lines[i:end + 1]
        i = end + 1
    return "\n".join(out)


def route_heading(doc, route):
    summary = operation(doc, route).get("summary", route).replace('"', "'")
    return route if summary == route else f"{route} - {summary.rstrip('.')}"


def retitle(doc, pages, module):
    """Retitle each route page from its operation summary, keeping the page's number."""
    ops, pages, renames = set(operations(doc)), dict(pages), {}
    for key, text in pages.items():
        route = next((k for k, _ in marker_blocks(text) if k in ops), None)
        number = re.match(r"4-(\d+)-", os.path.basename(key))
        found = re.search(r'^title: "(.*)"$', text, re.M)
        if not (route and number and found):
            continue
        old = found.group(1)
        new = f"API 4.{number.group(1)}: {route_heading(doc, route)}"
        if new != old:
            pages[key] = text.replace(f'title: "{old}"', f'title: "{new}"', 1).replace(f"\n# {old}\n", f"\n# {new}\n", 1)
            renames[old] = new
    return pages, renames


def render_module(doc, raw, module, pages, contracts_text, common_link="../interface-contracts.md"):
    pages = dict(pages)
    have = {key for text in pages.values() for key, _ in marker_blocks(text)}
    for n, route in enumerate(operations(doc), 1):
        if route not in have:
            summary = operation(doc, route).get("summary", route).replace('"', "'")
            heading = route_heading(doc, route)
            pages[f"{module}/api/{page_name(n, route)}"] = ROUTE_PAGE.format(
                module=module, n=n, heading=heading, summary=summary, common=common_link, begin=BEGIN.format(route=route), end=END)
    if not contracts_text:
        contracts_text = CONTRACTS_PAGE.format(module=module, begin=BEGIN.format(route=COMMON), end=END)
    elif COMMON not in {key for key, _ in marker_blocks(contracts_text)}:
        contracts_text = contracts_text.rstrip("\n") + f"\n\n## Common errors\n\n{BEGIN.format(route=COMMON)}\n{END}\n"
    return ({key: fill_markers(doc, raw, text) for key, text in pages.items()},
            fill_markers(doc, raw, contracts_text))


def _module_base(lld_path, module=None):
    return os.path.dirname(os.path.abspath(lld_path)), module or os.path.splitext(os.path.basename(lld_path))[0]


def common_path(lld_path, module=None, common=None):
    base, module = _module_base(lld_path, module)
    return os.path.abspath(common) if common else os.path.join(base, module, "interface-contracts.md")


def common_link(lld_path, module=None, common=None):
    if not common:
        return "../interface-contracts.md"
    base, module = _module_base(lld_path, module)
    return os.path.relpath(os.path.abspath(common), os.path.join(base, module, "api"))


def load_module(lld_path, module=None, common=None):
    base, module = _module_base(lld_path, module)
    api = os.path.join(base, module, "api")
    pages = {}
    if os.path.isdir(api):
        for name in sorted(os.listdir(api)):
            if name.endswith(".md") and not name.startswith("group-"):
                with open(os.path.join(api, name), encoding="utf-8") as fh:
                    pages[f"{module}/api/{name}"] = fh.read()
    contracts = ""
    path = common_path(lld_path, module, common)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            contracts = fh.read()
    return module, pages, contracts


def save_module(lld_path, pages, contracts_text, module=None, common=None):
    base, module = _module_base(lld_path, module)
    os.makedirs(os.path.join(base, module, "api"), exist_ok=True)
    for key, text in pages.items():
        with open(os.path.join(base, key), "w", encoding="utf-8") as fh:
            fh.write(text)
    path = common_path(lld_path, module, common)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(contracts_text)
