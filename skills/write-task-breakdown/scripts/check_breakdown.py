#!/usr/bin/env python3
"""Fail on an empty set, a module page without module_code, a non-route page under api/, an element page that repeats a task id, a task without a man-day figure in whole hours above 0 or a row without a source element."""
import argparse
import os
import re
import sys
from fractions import Fraction

from breakdown import duplicate_task_ids, modules_without_code, non_route_pages, read_estimates, read_tasks


def _whole_hours(value):
    text = value.strip()
    if not re.fullmatch(r"[0-9]+(\.[0-9]+)?", text):
        return False
    figure = Fraction(text)
    return figure > 0 and (figure * 8).denominator == 1


def problems(set_dir):
    tasks = read_tasks(set_dir)
    estimates = read_estimates(set_dir)
    found = []
    if not tasks:
        found.append("set: no tasks found")
    found.extend("%s: no module_code" % page for page in modules_without_code(set_dir))
    found.extend("%s: not a route page" % page for page in non_route_pages(set_dir))
    found.extend(duplicate_task_ids(set_dir))
    for task in tasks:
        md = estimates.get(task.id, {"md": ""})["md"]
        if not md:
            found.append("%s: no man-day figure" % task.id)
        elif not _whole_hours(md):
            found.append("%s: man-day figure '%s' is not in whole hours above 0" % (task.id, md))
    sourced = {task.id for task in tasks}
    found.extend("%s: no source element" % row for row in estimates if row not in sourced)
    return found


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True, dest="set_dir")
    args = ap.parse_args()
    if not os.path.isdir(args.set_dir):
        ap.error("--set %s is not a directory" % args.set_dir)
    found = problems(args.set_dir)
    for line in found:
        print(line)
    sys.exit(1 if found else 0)
