#!/usr/bin/env python3
"""Check design pages against the word, row and block budgets of the tl-design skills.

Word = whitespace-separated token with markup stripped, kept only if it holds a letter or digit.
Usage: doc_budget.py <path>... [--json] [--waive <path>]... [--baseline <json>]
"""
import argparse
import collections
import json
import os
import re
import sys

BUDGETS = {
    "hla": 4000,
    "hla-3": 200,
    "hla-4": 320,
    "hla-5": 120,
    "hla-5-count": 8,
    "hla-terms-entry": 30,
    "decision": 75,
    "cost-bullet": 30,
    "challenges": 50,
    "use-case": 300,
    "lld": 1200,
    "api": 800,
    "execution-logic": 1000,
    "execution-logic-rules": 800,
    "element": 600,
    "route": 300,
    "schema": 600,
    "scenarios-rows": 15,
    "dependencies": 150,
    "schema-changes": 600,
}

ALLOWED_FENCES = ("mermaid", "json")
GUARD_HEADER = "|#|Check|Reply|Scenario|"
FORBIDDEN = [
    ("guard table", lambda l: l.replace(" ", "").startswith(GUARD_HEADER)),
    ("**Logic:** label", lambda l: l.strip().startswith("**Logic:**")),
    ("## DDL heading", lambda l: re.match(r"^#{1,6}\s+DDL\b", l) is not None),
    ("DDL in migration order", lambda l: "DDL in migration order" in l),
    ("solution panel", lambda l: re.search(r"\b(Bad|Good|Great) solution\b", l) is not None),
]
EXEMPT = {
    "schema-changes": {"## DDL heading", "DDL in migration order"},
    "hla": {"solution panel"},
    "use-case": {"solution panel"},
}
JSON_LABEL = re.compile(r"^\*\*[^*]+ · [^*]+:\*\*$")

PATTERNS = [
    ("hla", r"(^|/)designs/[^/]+/overview\.md$"),
    ("schema-changes", r"(^|/)designs/[^/]+/schema-changes\.md$"),
    ("dependencies", r"(^|/)designs/[^/]+/dependencies\.md$"),
    ("use-case", r"(^|/)use-cases/([a-z]{2,4}-)?uc-[^/]+\.md$"),
    ("execution-logic", r"(^|/)(shared-)?execution-logic\.md$"),
    ("schema", r"(^|/)(data-)?schema\.md$"),
    ("schema", r"(^|/)[^/]+__[^/]+-schema\.md$"),
    ("scenarios", r"(^|/)scenarios\.md$"),
    ("route", r"(^|/)lld/[^/]+/api/4-[^/]+\.md$"),
    ("route", r"(^|/)[^/]+__[^/]+-lld/(.+/)?4-[^/]+\.md$"),
    ("api", r"(^|/)lld/[^/]+-api\.md$"),
    ("api", r"(^|/)lld/[^/]+/interface-contracts\.md$"),
    ("api", r"(^|/)L2-integration/[^/]+/[^/]+__[^/]+-api\.md$"),
    ("hla", r"(^|/)hlds/[^/]+\.md$"),
    ("hla", r"(^|/)L1-architecture/[^/]+__system-overview\.md$"),
    ("hla", r"(^|/)L3-features/([^/]+)/[^/]+__\2\.md$"),
    ("lld", r"(^|/)lld/[^/]+\.md$"),
    ("lld", r"(^|/)L2-integration/[^/]+/[^/]+__[^/]+-lld\.md$"),
    ("element", r"(^|/)lld/[^/]+/[^/]+\.md$"),
    ("element", r"(^|/)[^/]+__[^/]+-lld/[^/]+\.md$"),
]
PATTERNS = [(t, re.compile(p)) for t, p in PATTERNS]
SKIP_DIRS = ("_archived", "audits")
UNTYPED = re.compile(r"^(index|task-breakdown|open-points[^/]*|implementation-notes)\.md$")
FINAL_DESIGN = re.compile(r"^### 3\.\d+ Final design\b")
LINE_SUFFIX = re.compile(r", line \d+$")

CONTRACT = re.compile(r"<!--\s*contract:begin\b.*?<!--\s*contract:end\s*-->", re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
FENCE = re.compile(r"^\s*(```|~~~)\s*([\w-]*)")
IMAGE_LINE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def page_type(path):
    p = os.path.abspath(path).replace(os.sep, "/")
    if UNTYPED.match(p.rsplit("/", 1)[-1]):
        return "unknown"
    for t, rx in PATTERNS:
        if rx.search(p):
            return t
    return "unknown"


def _blank(m):
    return "\n" * m.group(0).count("\n")


def _clean(text):
    text = CONTRACT.sub(_blank, text)
    text = FRONTMATTER.sub(_blank, text)
    return COMMENT.sub(_blank, text)


def _numbered(text):
    """Yield (line number, line, fence_tag) where fence_tag is None outside a fence, '' for an untagged fence opener."""
    fence = None
    for n, line in enumerate(_clean(text).split("\n"), 1):
        m = FENCE.match(line)
        if m and fence is None:
            fence = m.group(1)
            yield n, line, m.group(2)
            continue
        if fence is not None:
            if m and m.group(1) == fence:
                fence = None
            continue
        yield n, line, None


def _lines(text):
    for _, line, tag in _numbered(text):
        yield line, tag


def _count(text):
    n = 0
    for tok in re.sub(r"<[^>]+>", " ", text).replace("|", " ").split():
        tok = re.sub(r"[*_`#>~\[\]()]", "", tok)
        if re.search(r"\w", tok):
            n += 1
    return n


def prose_words(text):
    prose = [l for l, tag in _lines(text) if tag is None and not IMAGE_LINE.match(l)]
    return _count("\n".join(prose))


def sections(text):
    out, head, body = [], None, []
    for line, tag in _lines(text):
        m = HEADING.match(line) if tag is None else None
        if m and len(m.group(1)) <= 3:
            if head is not None:
                out.append((head, "\n".join(body).strip()))
            head, body = (line.strip() if len(m.group(1)) == 3 else None), []
        elif head is not None:
            body.append(line if tag is None else "")
    if head is not None:
        out.append((head, "\n".join(body).strip()))
    return out


def _rules_section(text):
    body, inside = [], False
    for line, tag in _lines(text):
        m = HEADING.match(line) if tag is None else None
        if m and len(m.group(1)) <= 2:
            inside = m.group(2).strip() == "Rules" and len(m.group(1)) == 2
            continue
        if inside and tag is None:
            body.append(line)
    return "\n".join(body) if body else None


def _without_rules(text):
    out, skip = [], False
    for line in text.split("\n"):
        m = HEADING.match(line)
        if m and len(m.group(1)) <= 2:
            skip = len(m.group(1)) == 2 and m.group(2).strip() == "Rules"
        if not skip:
            out.append(line)
    return "\n".join(out)


def _terms_body(text):
    body, inside = [], False
    for line, tag in _lines(text):
        m = HEADING.match(line) if tag is None else None
        if m and len(m.group(1)) <= 2:
            inside = len(m.group(1)) == 2 and m.group(2).strip() == "Terms"
            continue
        if inside and tag is None:
            body.append(line)
    return "\n".join(body) if body else None


TERM_ENTRY = re.compile(r"^\s*-\s+\*\*(.+?)\*\*\s*:")
TERM_LINK = re.compile(r"\[([^\[\]]+)\]\(([^)\s#]*)#terms\)")


def _norm_term(t):
    t = t.lower().replace("`", "").replace("-", " ")
    return " ".join(re.sub(r"^(the|a|an)\s+", "", t.strip()).split())


def _in_code(line):
    spans, i = [], 0
    while True:
        a = line.find("`", i)
        if a < 0:
            return spans
        b = a
        while b < len(line) and line[b] == "`":
            b += 1
        close = re.compile(r"(?<!`)`{%d}(?!`)" % (b - a)).search(line, b)
        if not close:
            i = b
            continue
        spans.append((a, close.end()))
        i = close.end()


def _plural_of(name, known):
    if name.endswith("ies") and name[:-3] + "y" in known:
        return True
    return name.endswith("s") and name[:-1] in known


def _term_ok(text, known):
    for part in re.split(r"\s+and\s+", text.strip(), flags=re.I):
        name = _norm_term(part)
        if name not in known and not _plural_of(name, known):
            return False
    return True


def _term_entries(text):
    body = _terms_body(text) or ""
    out = set()
    for line in body.split("\n"):
        m = TERM_ENTRY.match(line)
        if m:
            out.update(_norm_term(t) for t in m.group(1).split(", "))
    return out


def _check_terms_links(pages):
    entries = {}
    for pg in pages:
        if pg["type"] == "hla":
            with open(pg["path"], encoding="utf-8") as f:
                entries[os.path.realpath(pg["path"])] = _term_entries(f.read())
    for pg in pages:
        with open(pg["path"], encoding="utf-8") as f:
            text = f.read()
        for n, line, tag in _numbered(text):
            if tag is not None:
                continue
            spans = _in_code(line)
            for m in TERM_LINK.finditer(line):
                if any(a <= m.start() < b for a, b in spans):
                    continue
                target = os.path.realpath(os.path.join(os.path.dirname(pg["path"]), m.group(2)))
                if target not in entries:
                    continue
                if _term_ok(m.group(1), entries[target]):
                    continue
                text_ = m.group(1).strip()
                pg["violations"].append({"rule": "term-missing", "where": "%s, line %d" % (text_, n), "detail": text_})


def _forbidden(text, ptype):
    allowed = ALLOWED_FENCES + (("sql",) if ptype == "schema-changes" else ())
    found, prev = [], ""
    for n, line, tag in _numbered(text):
        if tag is not None:
            if tag not in allowed:
                found.append(("forbidden-block", "fence, line %d" % n, "fenced block tagged '%s'" % (tag or "untagged")))
            elif tag == "json" and not JSON_LABEL.match(prev.strip()):
                found.append(("forbidden-block", "json, line %d" % n, "json block without a '**Kind · name:**' label"))
            prev = line
            continue
        for name, test in FORBIDDEN:
            if name in EXEMPT.get(ptype, ()):
                continue
            if test(line):
                found.append(("forbidden-block", "%s, line %d" % (name, n), line.strip()[:60]))
        if line.strip():
            prev = line
    return found


def _table_rows(text):
    tables, cur = [], []
    for line, tag in _lines(text):
        if tag is None and line.lstrip().startswith("|"):
            cur.append(line)
        elif cur:
            tables.append(cur)
            cur = []
    if cur:
        tables.append(cur)
    counts = []
    for t in tables:
        sep = len(t) > 1 and re.match(r"^\s*\|[\s:|-]+\|?\s*$", t[1]) is not None
        counts.append(len(t) - (2 if sep else 1))
    return counts


def check_page(path):
    ptype = page_type(path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    res = {"path": path, "type": ptype, "words": 0, "budget": None, "violations": []}
    if ptype == "unknown":
        return res
    v = res["violations"]

    def add(rule, where, detail):
        v.append({"rule": rule, "where": where, "detail": detail})

    body = text
    if ptype == "execution-logic":
        rules = _rules_section(text)
        body = _without_rules(text)
        if rules is not None:
            n = prose_words(rules)
            if n > BUDGETS["execution-logic-rules"]:
                add("section-budget", "Rules", "%d words, budget %d" % (n, BUDGETS["execution-logic-rules"]))
    if ptype == "dependencies":
        body = "\n".join(l for l in body.split("\n") if not l.lstrip().startswith("|"))
    res["words"] = prose_words(body)
    res["budget"] = BUDGETS.get(ptype)
    if res["budget"] is not None and res["words"] > res["budget"]:
        add("page-budget", "page", "%d words, budget %d" % (res["words"], res["budget"]))

    if ptype == "hla":
        fives = 0
        for head, sbody in sections(text):
            m = re.match(r"^### ([345])\.(\d+)", head or "")
            if not m or FINAL_DESIGN.match(head):
                continue
            key = "hla-" + m.group(1)
            if m.group(1) == "5":
                fives += 1
            n = prose_words(sbody)
            if n > BUDGETS[key]:
                add("section-budget", "%s.%s" % (m.group(1), m.group(2)), "%d words, budget %d" % (n, BUDGETS[key]))
        for term, n, words, raw in _terms_entry_words(text):
            if words > BUDGETS["hla-terms-entry"]:
                add("terms-entry", "%s, line %d" % (term, n), "%d words, budget %d" % (words, BUDGETS["hla-terms-entry"]))
            owned = _owned_values(raw)
            if owned:
                add("terms-value", "%s, line %d" % (term, n), owned)
        if fives > BUDGETS["hla-5-count"]:
            add("failure-count", "5", "%d questions, budget %d" % (fives, BUDGETS["hla-5-count"]))

    if ptype in WORD_CAP_TYPES:
        words_check = _panel_words if ptype in PANEL_TYPES else _legacy_form_words
        for rule, where, detail in words_check(text):
            add(rule, where, detail)

    if ptype == "scenarios":
        for i, n in enumerate(_table_rows(text), 1):
            if n > BUDGETS["scenarios-rows"]:
                add("row-budget", "table %d" % i, "%d rows, budget %d" % (n, BUDGETS["scenarios-rows"]))

    for rule, where, detail in _forbidden(text, ptype):
        add(rule, where, detail)
    return res


PANEL_TYPES = {"hla", "use-case"}
WORD_CAP_TYPES = {"hla", "lld", "api", "route", "element", "execution-logic", "use-case"}
BOLD_LABEL = re.compile(r"^\s*\*\*[^*]+\*\*")
BULLET = re.compile(r"^\s*[-*]\s+")


def _terms_entry_words(text):
    """Yield (term, line number, word count, text) for each bullet under ## Terms."""
    inside, cur = False, None
    for n, line, tag in _numbered(text):
        m = HEADING.match(line) if tag is None else None
        if m and len(m.group(1)) <= 2:
            inside = len(m.group(1)) == 2 and m.group(2).strip() == "Terms"
        if cur and (not inside or tag is not None or not line.strip() or BULLET.match(line) or m):
            yield cur[0], cur[1], _count(cur[2]), cur[2]
            cur = None
        if not inside or tag is not None:
            continue
        e = TERM_ENTRY.match(line)
        if e:
            cur = [e.group(1), n, line]
        elif cur:
            cur[2] += "\n" + line
    if cur:
        yield cur[0], cur[1], _count(cur[2]), cur[2]


def _owned_values(raw):
    """Return why a Terms entry copies a value another page owns, or None."""
    body = TERM_ENTRY.sub("", raw, count=1)
    body = re.sub(r"\[[^\]]*\]\([^)]*\)", "link", body)
    if re.search(r"(?<![A-Za-z])\d", body):
        return "holds a number or id; link the page that owns it"
    if len(re.findall(r"`[^`]+`", body)) >= 2:
        return "lists code values; link the page that owns them"
    return None


def _legacy_form_words(text):
    """Yield (rule, where, detail) for an over-long **Decision.** paragraph or **Cost.** bullet."""
    lines, where, out = [], "page", []
    for n, line, tag in _numbered(text):
        head = HEADING.match(line) if tag is None else None
        if head:
            where = line.strip()
        lines.append((n, line, tag, where, head is not None))

    def plain(k):
        return lines[k][2] is None and not lines[k][4] and not BOLD_LABEL.match(lines[k][1]) and not lines[k][1].lstrip().startswith(">")

    def check(kind, n, wh, buf):
        key, rule = ("decision", "decision-words") if kind == "decision" else ("cost-bullet", "cost-words")
        words = _count(buf)
        if words > BUDGETS[key]:
            out.append((rule, "%s, line %d" % (wh, n), "%d words, budget %d" % (words, BUDGETS[key])))

    i = 0
    while i < len(lines):
        n, line, tag, wh, ish = lines[i]
        st = line.lstrip()
        if tag is not None or ish:
            i += 1
        elif st.startswith("**Decision.**"):
            buf = [st[len("**Decision.**"):]]
            i += 1
            while i < len(lines) and lines[i][1].strip() and plain(i):
                buf.append(lines[i][1])
                i += 1
            check("decision", n, wh, "\n".join(buf))
        elif st.startswith("**Cost.**"):
            rest = st[len("**Cost.**"):]
            items = [[n, [rest]]] if rest.strip() else []
            i += 1
            while i < len(lines) and (not lines[i][1].strip() or plain(i)):
                if not lines[i][1].strip():
                    j = i
                    while j < len(lines) and not lines[j][1].strip():
                        j += 1
                    if j >= len(lines) or not plain(j) or not (BULLET.match(lines[j][1]) or not items):
                        break
                    i = j
                    continue
                if BULLET.match(lines[i][1]):
                    items.append([lines[i][0], [BULLET.sub("", lines[i][1])]])
                elif items:
                    items[-1][1].append(lines[i][1])
                else:
                    items.append([lines[i][0], [lines[i][1]]])
                i += 1
            for ln, buf in items:
                check("cost", ln, wh, "\n".join(buf))
        else:
            i += 1
    return out


PANEL_LINE = re.compile(r"^\s*>\s?")
PANEL_KIND = re.compile(r"^\*\*(Bad|Good|Great) solution\b")
PANEL_MARK = re.compile(r"^\[!\w+\]")
PANEL_LABEL = re.compile(r"^\*\*(Approach|Challenges)\.\*\*")


def _panel_words(text):
    """Yield (rule, where, detail) for an over-long Great **Approach.** or a panel **Challenges.**."""
    out, where, kind, label, buf, start = [], "page", None, None, [], 0

    def flush():
        nonlocal label, buf
        if label is not None:
            words = _count("\n".join(buf))
            key, rule = ("decision", "decision-words") if label == "Approach" else ("challenges", "challenges-words")
            if (label != "Approach" or kind == "Great") and words > BUDGETS[key]:
                out.append((rule, "%s, line %d" % (where, start), "%d words, budget %d" % (words, BUDGETS[key])))
        label, buf = None, []

    for n, line, tag in _numbered(text):
        head = HEADING.match(line) if tag is None else None
        if head or tag is not None or not PANEL_LINE.match(line):
            flush()
            kind = None
            if head:
                where = line.strip()
            continue
        st = PANEL_LINE.sub("", line).strip()
        if not st:
            continue
        m = PANEL_KIND.match(st)
        lab = PANEL_LABEL.match(st)
        if PANEL_MARK.match(st):
            flush()
            kind = None
        elif m:
            flush()
            kind = m.group(1)
        elif lab:
            flush()
            label, start, buf = lab.group(1), n, [st[lab.end():]]
        elif label is not None:
            buf.append(st)
    flush()
    return out


def _walk(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith(("_stage-", ".")))
        for f in sorted(files):
            if f.endswith(".md") and not f.startswith("."):
                yield os.path.join(d, f)


NUMERIC_RULES = {"page-budget", "section-budget", "terms-entry", "decision-words", "challenges-words", "cost-words", "row-budget", "failure-count"}


def _lead_number(detail):
    m = re.match(r"(\d+) ", detail)
    return int(m.group(1)) if m else None


def _load_baseline(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    root = os.path.dirname(os.path.abspath(path))
    base = {}
    for pg in data["pages"]:
        keys, nums = base.setdefault(os.path.realpath(os.path.join(root, pg["path"])), (collections.Counter(), {}))
        for v in pg["violations"]:
            key = (v["rule"], LINE_SUFFIX.sub("", v["where"]))
            keys[key] += 1
            n = _lead_number(v["detail"]) if v["rule"] in NUMERIC_RULES else None
            if n is not None:
                nums[key] = max(n, nums.get(key, n))
    return base


def _apply_baseline(page, base):
    keys, nums = base.get(os.path.realpath(page["path"]), ({}, {}))
    held = collections.Counter(keys)
    new, old = [], []
    for v in page["violations"]:
        key = (v["rule"], LINE_SUFFIX.sub("", v["where"]))
        if held[key] > 0:
            held[key] -= 1
            n = _lead_number(v["detail"]) if v["rule"] in NUMERIC_RULES else None
            if n is not None and key in nums and n > nums[key]:
                v["detail"] += ", was %d in baseline" % nums[key]
                new.append(v)
            else:
                old.append(v)
        else:
            new.append(v)
    page["violations"], page["baselined"] = new, old


def main(argv=None):
    ap = argparse.ArgumentParser(prog="doc_budget.py")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--waive", action="append", default=[])
    ap.add_argument("--baseline")
    args = ap.parse_args(argv)

    base = None
    if args.baseline:
        try:
            base = _load_baseline(args.baseline)
        except (OSError, ValueError, KeyError, TypeError) as e:
            print("doc_budget: unreadable baseline %s: %s" % (args.baseline, e), file=sys.stderr)
            return 2

    files = []
    for p in args.paths:
        if os.path.isdir(p):
            files.extend(_walk(p))
        elif os.path.isfile(p):
            files.append(p)
        else:
            print("doc_budget: no such path: %s" % p, file=sys.stderr)
            return 2

    waive = {os.path.realpath(w) for w in args.waive}
    pages, waived = [], []
    for f in files:
        if os.path.realpath(f) in waive:
            waived.append(f)
        else:
            pages.append(check_page(f))
    _check_terms_links([pg for pg in pages if pg["type"] != "unknown"])
    if base is not None:
        for pg in pages:
            _apply_baseline(pg, base)

    if args.json:
        for pg in pages:
            pg["path"] = os.path.realpath(pg["path"])
        waived = [os.path.realpath(x) for x in waived]
        print(json.dumps({"pages": pages, "waived": waived}, indent=2))
    else:
        for pg in pages:
            for x in pg["violations"]:
                print("%s: %s [%s] %s" % (pg["path"], x["rule"], x["where"], x["detail"]))
        for w in waived:
            print("waived: %s" % w)
    return 1 if any(pg["violations"] for pg in pages) else 0


if __name__ == "__main__":
    sys.exit(main())
