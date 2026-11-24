import os
import re
from collections import namedtuple

ESTIMATES = "task-breakdown.estimates.tsv"
Task = namedtuple("Task", "id name scope design depends")

SCHEMA_PAGE = "schema-changes.md"
SCHEMA_NAME = "Create schema and config changes"
SHARED_LABEL = re.compile(r"^\*\*(?:Existing tables|Shared tables)\*\*\s*$")
MODULE_LABEL = re.compile(r"^\*\*([A-Za-z0-9]+) · .+\*\*\s*$")
LABEL = re.compile(r"^\*\*(.+?)\*\*\s*$")
ROUTE_H1 = re.compile(r"^API 4\.(\d+):\s+(\S+)\s+(\S+)(?:\s+-\s+(.+?))?\s*$")
ELEMENT_H1 = re.compile(r"^(?!API )([A-Z][A-Za-z]+) 4\.(\d+):\s+(.+?)(?:\s+-\s+(.+?))?\s*$")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _sections(text):
    out, name = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            name = line[3:].strip()
            out[name] = []
        elif name is not None:
            out[name].append(line)
    return out


def _h1(text):
    body = re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S)
    fenced = False
    for line in body.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("# "):
            return line[2:].strip()
    return _frontmatter(text).get("title", "")


def _frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    out = {}
    for line in (m.group(1).splitlines() if m else []):
        if ":" in line and not line[0].isspace():
            k, v = line.split(":", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            out[k.strip()] = v
    return out


def _md_files(directory):
    if not os.path.isdir(directory):
        return []
    return sorted(n for n in os.listdir(directory) if n.endswith(".md"))


CONFIG_NAME = re.compile(r"\*\*(.+?)\*\*|`([^`]+)`|([^.]+)")


def _config_name(entry):
    m = CONFIG_NAME.match(entry.strip())
    return next(g for g in m.groups() if g is not None).strip().strip("`").rstrip(".").strip("`")


def _schema(set_dir):
    path = os.path.join(set_dir, SCHEMA_PAGE)
    if not os.path.isfile(path):
        return None
    sections = _sections(_read(path))
    labels = [m.group(1) for m in (LABEL.match(l.strip()) for l in sections.get("Data model", [])) if m]
    lines = [l.strip() for l in sections.get("Data model", [])]
    shared = any(SHARED_LABEL.match(l) for l in lines)
    codes = {m.group(1) for m in (MODULE_LABEL.match(l) for l in lines) if m}
    config = [_config_name(l.strip()[2:]) for l in sections.get("Config changes", []) if l.strip().startswith(("- ", "* "))]
    if not labels and not config:
        return None
    return SCHEMA_PAGE, "; ".join(labels + config), shared, codes


def _dependencies(set_dir):
    path = os.path.join(set_dir, "dependencies.md")
    blocks = {}
    if not os.path.isfile(path):
        return blocks
    col = None
    for line in _read(path).splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if "Blocked tasks" in cells:
            col = cells.index("Blocked tasks")
        elif col is not None and cells[0].startswith("DEP-") and len(cells) > col:
            for task in cells[col].split(","):
                task = task.strip()
                if task and task != "none":
                    blocks.setdefault(task, []).append(cells[0])
    return blocks


def _module_codes(set_dir):
    lld = os.path.join(set_dir, "lld")
    codes = (_frontmatter(_read(os.path.join(lld, n))).get("module_code") for n in _md_files(lld))
    return [c for c in codes if c]


def _routes(set_dir):
    routes = []
    lld = os.path.join(set_dir, "lld")
    for name in _md_files(lld):
        code = _frontmatter(_read(os.path.join(lld, name))).get("module_code")
        module = name[:-3]
        api = os.path.join(lld, module, "api")
        if not code:
            continue
        for page in _md_files(api):
            if not re.match(r"^4-\d+-", page):
                continue
            m = ROUTE_H1.match(_h1(_read(os.path.join(api, page))))
            if not m:
                continue
            scope = m.group(2) + " " + m.group(3)
            routes.append((code, int(m.group(1)), scope, m.group(4) or scope,
                           os.path.join("lld", module, "api", page)))
    return sorted(routes, key=lambda r: (r[0], r[1]))


def _all_elements(set_dir):
    elements = []
    lld = os.path.join(set_dir, "lld")
    for name in _md_files(lld):
        code = _frontmatter(_read(os.path.join(lld, name))).get("module_code")
        module = name[:-3]
        if not code:
            continue
        for page in _md_files(os.path.join(lld, module)):
            m = ELEMENT_H1.match(_h1(_read(os.path.join(lld, module, page))))
            if not m:
                continue
            scope = m.group(1) + " " + m.group(3)
            elements.append((code, int(m.group(2)), scope, m.group(4) or scope,
                             os.path.join("lld", module, page)))
    return elements


def _split_elements(set_dir):
    taken = {(code, n) for code, n, _, _, _ in _routes(set_dir)}
    kept, duplicates = [], []
    for element in _all_elements(set_dir):
        key = (element[0], element[1])
        if key in taken:
            duplicates.append(element)
        else:
            taken.add(key)
            kept.append(element)
    return kept, duplicates


def duplicate_task_ids(set_dir):
    return ["%s: duplicate task id %s-4.%d" % (page.replace(os.sep, "/"), code, n)
            for code, n, _, _, page in _split_elements(set_dir)[1]]


def _has_element_page(lld, module):
    directory = os.path.join(lld, module)
    return any(ELEMENT_H1.match(_h1(_read(os.path.join(directory, p)))) for p in _md_files(directory))


def modules_without_code(set_dir):
    lld = os.path.join(set_dir, "lld")
    return ["lld/%s" % n for n in _md_files(lld)
            if (os.path.isdir(os.path.join(lld, n[:-3], "api")) or _has_element_page(lld, n[:-3]))
            and not _frontmatter(_read(os.path.join(lld, n))).get("module_code")]


def non_route_pages(set_dir):
    lld = os.path.join(set_dir, "lld")
    out = []
    for name in _md_files(lld):
        api = os.path.join(lld, name[:-3], "api")
        for page in _md_files(api):
            if re.match(r"^4-\d+-", page) and not ROUTE_H1.match(_h1(_read(os.path.join(api, page)))):
                out.append("lld/%s/api/%s" % (name[:-3], page))
    return out


def _use_cases(set_dir):
    out = []
    directory = os.path.join(set_dir, "use-cases")
    for name in _md_files(directory):
        m = re.match(r"^((?:[a-z0-9]+-)?uc-(\d+))", name)
        if not m:
            continue
        text = _read(os.path.join(directory, name))
        screens = _sections(text).get("Screens")
        if screens is None:
            continue
        labels = [re.sub(r"[`*]", "", l.strip()[2:]).strip() for l in screens if l.strip().startswith(("- ", "* "))]
        title = re.sub(r"^(?:[A-Za-z0-9]+-)?UC-\d+\s*[:\-–·.]*\s*", "", _h1(text), flags=re.I)
        out.append((int(m.group(2)), m.group(1).upper(), title, "; ".join(labels),
                    os.path.join("use-cases", name), text))
    return sorted(out, key=lambda u: (u[0], u[1]))


def read_tasks(set_dir):
    blocks = _dependencies(set_dir)

    def depends(task_id, *tasks):
        return list(tasks) + blocks.get(task_id, [])

    tasks = []
    schema = _schema(set_dir)
    if schema:
        page, scope, _, _ = schema
        tasks.append(Task("SCHEMA", SCHEMA_NAME, scope, page, depends("SCHEMA")))
    shared, codes = (schema[2], schema[3]) if schema else (False, set())
    route_ids = []
    routes = _routes(set_dir)
    sources = sorted(routes + _split_elements(set_dir)[0], key=lambda r: (r[0], r[1]))
    for code, n, scope, name, page in sources:
        task_id = "%s-4.%d" % (code, n)
        if (code, n, scope, name, page) in routes:
            route_ids.append((task_id, scope))
        tasks.append(Task(task_id, name, scope, page, depends(task_id, *(["SCHEMA"] if shared or code in codes else []))))
    multi = len(_module_codes(set_dir)) > 1
    for _, task_id, name, scope, page, text in _use_cases(set_dir):
        if not multi:
            task_id = task_id[task_id.rfind("UC-"):]
        used = [rid for rid, route in route_ids
                if re.search(re.escape(route) + r"(?![\w/{}-])", text)]
        tasks.append(Task(task_id, name, scope, page, depends(task_id, *used)))
    return tasks


def read_estimates(set_dir):
    path = os.path.join(set_dir, ESTIMATES)
    rows = {}
    if not os.path.isfile(path):
        return rows
    for line in _read(path).splitlines()[1:]:
        if not line.strip():
            continue
        cells = [c.strip() for c in line.split("\t")] + ["", ""]
        rows[cells[0]] = {"md": cells[1], "ticket": cells[2]}
    return rows
