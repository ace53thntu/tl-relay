#!/usr/bin/env python3
"""Convert one worksheet of an .xlsx workbook to a Markdown table, standard library only."""
import argparse
import hashlib
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
P = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def col_index(ref):
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def si_text(si):
    parts = []
    for child in si:
        if child.tag == M + "t":
            parts.append(child.text or "")
        elif child.tag == M + "r":
            t = child.find(M + "t")
            parts.append((t.text or "") if t is not None else "")
    return "".join(parts)


def shared_strings(z):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    return [si_text(si) for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(M + "si")]


def sheet_parts(z):
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target").lstrip("/") for r in rels.findall(P + "Relationship")}
    out = []
    for s in wb.find(M + "sheets").findall(M + "sheet"):
        t = target[s.get(R + "id")]
        out.append((s.get("name"), t if t.startswith("xl/") else "xl/" + t))
    return out


def cell_value(c, strings):
    v = c.find(M + "v")
    if v is None or v.text is None:
        return ""
    return strings[int(v.text)] if c.get("t") == "s" else v.text


def read_sheet(path, sheet=None):
    with zipfile.ZipFile(path) as z:
        parts = sheet_parts(z)
        match = parts[:1] if sheet is None else [p for p in parts if p[0] == sheet]
        if not match:
            raise SystemExit(f"xlsx2md: no sheet named {sheet!r}; sheets are {[p[0] for p in parts]}")
        name, part = match[0]
        strings = shared_strings(z)
        root = ET.fromstring(z.read(part))
    rows = []
    for row in root.iter(M + "row"):
        values = {col_index(c.get("r")): cell_value(c, strings) for c in row.findall(M + "c")}
        rows.append([values.get(i, "") for i in range(max(values) + 1)] if values else [])
    width = max((len(r) for r in rows), default=0)
    return name, [r + [""] * (width - len(r)) for r in rows]


def cell_md(text):
    return text.replace("\r\n", "\n").replace("|", "\\|").replace("\n", "<br>")


def to_markdown(rows):
    rows = [r for r in rows if any(v.strip() for v in r)]
    if not rows:
        return ""
    head, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(cell_md(h) for h in head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    lines += ["| " + " | ".join(cell_md(v) for v in r) + " |" for r in body]
    return "\n".join(lines) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("xlsx")
    p.add_argument("--sheet")
    p.add_argument("--list", action="store_true")
    p.add_argument("--out")
    a = p.parse_args(argv)
    if a.list:
        with zipfile.ZipFile(a.xlsx) as z:
            print("\n".join(n for n, _ in sheet_parts(z)))
        return 0
    name, rows = read_sheet(a.xlsx, a.sheet)
    with open(a.xlsx, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    base = os.path.basename(a.xlsx)
    text = (f"# {os.path.splitext(base)[0]}\n\nConverted from `{base}`, sheet `{name}`, sha256 `{digest}`.\n\n"
            + to_markdown(rows))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
