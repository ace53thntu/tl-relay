#!/usr/bin/env python3
"""Write the task tables of task-breakdown.md and append new task ids to the estimates file."""
import argparse
import os

from breakdown import ESTIMATES, _h1, read_estimates, read_tasks

BEGIN = "<!-- breakdown:begin -->"
END = "<!-- breakdown:end -->"
PAGE = "task-breakdown.md"
HEADER = "| ID | Task | Scope | Ticket | Design | Depends on | MD |\n| --- | --- | --- | --- | --- | --- | --- |\n"


def _cell(text):
    return text.replace("|", "\\|")


def _depend(task_id):
    return "[%s](dependencies.md)" % task_id if task_id.startswith("DEP-") else task_id


def _title(set_dir):
    handle = os.path.basename(os.path.abspath(set_dir))
    path = os.path.join(set_dir, "overview.md")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return _h1(f.read()) or handle
    return handle


def _tables(tasks, estimates):
    out = [HEADER]
    for t in tasks:
        est = estimates.get(t.id, {"md": "", "ticket": ""})
        out.append("| %s |\n" % " | ".join([
            t.id, _cell(t.name), _cell(t.scope), est["ticket"], "[%s](%s)" % (t.design, t.design),
            ", ".join(_depend(d) for d in t.depends), est["md"]]))
    known = {t.id for t in tasks}
    orphans = [(i, e) for i, e in estimates.items() if i not in known]
    if orphans:
        out.append("\n### Tasks without a source\n\n| ID | Ticket | MD |\n| --- | --- | --- |\n")
        out.extend("| %s | %s | %s |\n" % (i, e["ticket"], e["md"]) for i, e in orphans)
    return "".join(out)


def generate(set_dir):
    tasks = read_tasks(set_dir)
    tsv = os.path.join(set_dir, ESTIMATES)
    estimates = read_estimates(set_dir)
    new = [t.id for t in tasks if t.id not in estimates]
    if not os.path.isfile(tsv):
        with open(tsv, "w", encoding="utf-8") as f:
            f.write("id\tmd\tticket\n")
    if new:
        with open(tsv, "rb") as f:
            text = f.read()
        with open(tsv, "a", encoding="utf-8") as f:
            if text and not text.endswith(b"\n"):
                f.write("\n")
            f.writelines("%s\t\t\n" % i for i in new)
        estimates = read_estimates(set_dir)
    block = BEGIN + "\n\n" + _tables(tasks, estimates) + "\n" + END
    page = os.path.join(set_dir, PAGE)
    if os.path.isfile(page):
        with open(page, encoding="utf-8") as f:
            text = f.read()
        start, end = text.find(BEGIN), text.find(END)
        if start < 0 or end < start:
            raise SystemExit("%s: breakdown markers missing" % page)
        text = text[:start] + block + text[end + len(END):]
    else:
        text = "---\ntype: Task Breakdown\n---\n# %s: Task breakdown\n\n%s\n" % (_title(set_dir), block)
    with open(page, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True, dest="set_dir")
    generate(ap.parse_args().set_dir)
