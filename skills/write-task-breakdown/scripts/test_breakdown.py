import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import breakdown as bd
import check_breakdown as cb
import generate_breakdown as gb

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check_breakdown.py")
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "demo")


class BreakdownTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.set = os.path.join(self.tmp, "demo")
        shutil.copytree(FIXTURE, self.set)

    def path(self, *parts):
        return os.path.join(self.set, *parts)

    def write(self, rel, text):
        full = self.path(rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)

    def read(self, rel):
        with open(self.path(rel), encoding="utf-8") as f:
            return f.read()

    def write_estimates(self, rows):
        with open(self.path(bd.ESTIMATES), "w", encoding="utf-8") as f:
            f.write("id\tmd\tticket\n")
            for task_id, row in rows.items():
                f.write("%s\t%s\t%s\n" % (task_id, row["md"], row["ticket"]))

    def fill_all(self, value):
        rows = bd.read_estimates(self.set)
        for row in rows.values():
            row["md"] = value
        self.write_estimates(rows)

    def tasks(self):
        return {t.id: t for t in bd.read_tasks(self.set)}

    def test_tasks_are_schema_two_routes_one_element_and_one_ui_task(self):
        self.assertEqual([t.id for t in bd.read_tasks(self.set)], ["SCHEMA", "BK-4.1", "BK-4.2", "BK-4.3", "UC-1"])

    def test_route_task_takes_its_name_and_scope_from_the_h1(self):
        t = self.tasks()["BK-4.1"]
        self.assertEqual((t.name, t.scope), ("Creates a booking", "POST /bookings"))

    def test_depends_on_covers_schema_routes_and_dependencies(self):
        t = self.tasks()
        self.assertEqual(t["BK-4.1"].depends, ["SCHEMA"])
        self.assertEqual(t["BK-4.2"].depends, ["SCHEMA", "DEP-1"])
        self.assertEqual(t["UC-1"].depends, ["BK-4.1"])

    def test_schema_and_ui_task_names_and_scopes(self):
        t = self.tasks()
        self.assertEqual((t["SCHEMA"].name, t["SCHEMA"].scope),
                         ("Create schema and config changes", "BK · bookings; BOOKING_TTL"))
        self.assertEqual((t["UC-1"].name, t["UC-1"].scope), ("Book a trip", "Trip summary; Confirm booking"))

    def test_schema_scope_names_each_config_entry_only(self):
        text = self.read("schema-changes.md").replace(
            "- `BOOKING_TTL`",
            "- **`BOOKING_TTL`.** `900` s on every deployment; it bounds a hold.\n"
            "- `RETRY_LIMIT` caps attempts at 3.\n"
            "- **Queue backlog alert.** New, outside the worker.")
        self.write("schema-changes.md", text)
        self.assertEqual(self.tasks()["SCHEMA"].scope,
                         "BK · bookings; BOOKING_TTL; RETRY_LIMIT; Queue backlog alert")

    def test_an_h1_without_a_summary_takes_method_and_path(self):
        self.write("lld/booking/api/4-2-cancel.md", "# API 4.2: DELETE /bookings/{id}\n")
        self.assertEqual(self.tasks()["BK-4.2"].name, "DELETE /bookings/{id}")

    def test_existing_tables_make_every_route_depend_on_schema(self):
        text = self.read("schema-changes.md").replace("**BK · bookings**", "**Existing tables**")
        self.write("schema-changes.md", text)
        t = self.tasks()
        self.assertIn("SCHEMA", t["BK-4.1"].depends)
        self.assertIn("SCHEMA", t["BK-4.2"].depends)

    def test_a_module_prefix_applies_to_use_cases_in_a_multi_module_set(self):
        self.write("lld/payment.md", "---\nmodule_code: PY\n---\n# Payment\n")
        os.rename(self.path("use-cases", "uc-1-book.md"), self.path("use-cases", "bk-uc-1-book.md"))
        self.assertIn("BK-UC-1", self.tasks())
        os.remove(self.path("lld", "payment.md"))
        self.assertNotIn("BK-UC-1", self.tasks())

    def test_a_single_module_set_ignores_the_file_name_prefix(self):
        os.rename(self.path("use-cases", "uc-1-book.md"), self.path("use-cases", "bk-uc-1-book.md"))
        self.assertIn("UC-1", self.tasks())

    def test_an_unprefixed_use_case_stays_uc_n_in_a_multi_module_set(self):
        self.write("lld/payment.md", "---\nmodule_code: PY\n---\n# Payment\n")
        self.assertIn("UC-1", self.tasks())

    def test_schema_dependency_is_scoped_to_the_routes_own_module(self):
        self.write("lld/payment.md", "---\nmodule_code: PY\n---\n# Payment\n")
        self.write("lld/payment/api/4-1-pay.md", "# API 4.1: POST /payments - Takes a payment\n")
        t = self.tasks()
        self.assertEqual(t["PY-4.1"].depends, [])
        self.assertEqual(t["BK-4.1"].depends, ["SCHEMA"])

    def test_shared_tables_make_a_route_in_another_module_depend_on_schema(self):
        self.write("lld/payment.md", "---\nmodule_code: PY\n---\n# Payment\n")
        self.write("lld/payment/api/4-1-pay.md", "# API 4.1: POST /payments - Takes a payment\n")
        text = self.read("schema-changes.md").replace("**BK · bookings**", "**Shared tables**")
        self.write("schema-changes.md", text)
        self.assertEqual(self.tasks()["PY-4.1"].depends, ["SCHEMA"])

    def test_an_append_after_a_tsv_without_a_final_newline_keeps_the_last_row(self):
        gb.generate(self.set)
        text = self.read(bd.ESTIMATES).replace("UC-1\t\t", "UC-1\t3\tPROJ-9").rstrip("\n")
        self.write(bd.ESTIMATES, text)
        self.write("lld/booking/api/4-4-list.md", "# API 4.4: GET /bookings - Lists bookings\n")
        gb.generate(self.set)
        est = bd.read_estimates(self.set)
        self.assertEqual(est["UC-1"], {"md": "3", "ticket": "PROJ-9"})
        self.assertIn("BK-4.4", est)

    def test_a_new_route_appends_a_row_with_an_empty_md(self):
        gb.generate(self.set)
        self.write("lld/booking/api/4-4-list.md", "# API 4.4: GET /bookings - Lists bookings\n")
        gb.generate(self.set)
        self.assertIn("BK-4.4\t\t\n", self.read(bd.ESTIMATES))

    def test_a_removed_route_keeps_its_row_under_tasks_without_a_source(self):
        gb.generate(self.set)
        os.remove(self.path("lld/booking/api/4-2-cancel.md"))
        gb.generate(self.set)
        self.assertIn("BK-4.2\t\t\n", self.read(bd.ESTIMATES))
        self.assertIn("### Tasks without a source\n\n| ID | Ticket | MD |\n| --- | --- | --- |\n| BK-4.2 |",
                      self.read("task-breakdown.md"))

    def test_an_existing_md_survives_a_rerun(self):
        gb.generate(self.set)
        text = self.read(bd.ESTIMATES).replace("BK-4.1\t\t", "BK-4.1\t2\tPROJ-1")
        self.write(bd.ESTIMATES, text)
        gb.generate(self.set)
        self.assertEqual(bd.read_estimates(self.set)["BK-4.1"], {"md": "2", "ticket": "PROJ-1"})
        self.assertIn("| BK-4.1 | Creates a booking | POST /bookings | PROJ-1 |", self.read("task-breakdown.md"))

    def test_two_runs_write_identical_bytes(self):
        gb.generate(self.set)
        first = self.read("task-breakdown.md")
        gb.generate(self.set)
        self.assertEqual(self.read("task-breakdown.md"), first)

    def test_text_outside_the_markers_survives(self):
        gb.generate(self.set)
        text = self.read("task-breakdown.md")
        self.write("task-breakdown.md", text.replace("# demo: Task breakdown\n", "# demo: Task breakdown\n\nKeep me.\n"))
        gb.generate(self.set)
        self.assertIn("Keep me.", self.read("task-breakdown.md"))

    def test_the_new_page_uses_the_overview_h1_as_its_title(self):
        self.write("overview.md", "# Demo platform\n")
        gb.generate(self.set)
        self.assertIn("# Demo platform: Task breakdown", self.read("task-breakdown.md"))

    def test_the_new_page_falls_back_to_the_overview_frontmatter_title(self):
        self.write("overview.md", '---\ntitle: "Demo platform"\n---\nBody.\n')
        gb.generate(self.set)
        self.assertIn("# Demo platform: Task breakdown", self.read("task-breakdown.md"))

    def test_the_overview_h1_wins_over_its_frontmatter_title(self):
        self.write("overview.md", '---\ntitle: "Front title"\n---\n# Body title\n')
        gb.generate(self.set)
        self.assertIn("# Body title: Task breakdown", self.read("task-breakdown.md"))

    def test_a_fenced_heading_in_the_overview_is_not_the_title(self):
        self.write("overview.md", '---\ntitle: "Demo platform"\n---\n```\n# comment\n```\n')
        gb.generate(self.set)
        self.assertIn("# Demo platform: Task breakdown", self.read("task-breakdown.md"))

    def test_the_new_page_falls_back_to_the_handle_without_an_overview(self):
        gb.generate(self.set)
        self.assertIn("# %s: Task breakdown" % os.path.basename(self.set), self.read("task-breakdown.md"))

    def test_design_and_dependency_cells_are_links(self):
        gb.generate(self.set)
        page = self.read("task-breakdown.md")
        self.assertIn("[lld/booking/api/4-2-cancel.md](lld/booking/api/4-2-cancel.md)", page)
        self.assertIn("SCHEMA, [DEP-1](dependencies.md)", page)

    def test_an_empty_md_fails_and_names_the_task(self):
        gb.generate(self.set)
        self.assertIn("BK-4.1: no man-day figure", cb.problems(self.set))

    def test_a_fresh_generate_lists_exactly_the_five_tasks(self):
        gb.generate(self.set)
        self.assertEqual(cb.problems(self.set), [
            "SCHEMA: no man-day figure", "BK-4.1: no man-day figure",
            "BK-4.2: no man-day figure", "BK-4.3: no man-day figure", "UC-1: no man-day figure"])

    def test_a_task_without_a_row_counts_as_an_empty_md(self):
        self.assertIn("SCHEMA: no man-day figure", cb.problems(self.set))

    def test_a_row_with_no_source_fails(self):
        gb.generate(self.set)
        self.fill_all("1")
        os.remove(self.path("lld/booking/api/4-2-cancel.md"))
        gb.generate(self.set)
        self.assertEqual(cb.problems(self.set), ["BK-4.2: no source element"])

    def test_an_orphan_with_an_empty_md_reports_only_the_missing_source(self):
        gb.generate(self.set)
        self.fill_all("1")
        with open(self.path(bd.ESTIMATES), "a", encoding="utf-8") as f:
            f.write("GONE-4.9\t\t\n")
        self.assertEqual(cb.problems(self.set), ["GONE-4.9: no source element"])

    def test_md_must_be_whole_hours_above_zero(self):
        gb.generate(self.set)
        self.fill_all("1")
        rows = bd.read_estimates(self.set)
        for value in ("1,5", "abc", "0", "0.3", "1.3", "1e1", "-1"):
            rows["BK-4.1"]["md"] = value
            self.write_estimates(rows)
            self.assertEqual(cb.problems(self.set),
                             ["BK-4.1: man-day figure '%s' is not in whole hours above 0" % value])
        for value in (" 2 ", "0.125", "0.5"):
            rows["BK-4.1"]["md"] = value
            self.write_estimates(rows)
            self.assertEqual(cb.problems(self.set), [])

    def test_every_md_filled_and_every_row_sourced_passes(self):
        gb.generate(self.set)
        self.fill_all("0.5")
        self.assertEqual(cb.problems(self.set), [])

    def test_a_set_with_no_tasks_fails(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        self.assertEqual(cb.problems(empty), ["set: no tasks found"])

    def test_a_module_page_without_module_code_is_reported(self):
        self.write("lld/booking.md", "# Booking\n")
        self.assertIn("lld/booking.md: no module_code", cb.problems(self.set))

    def test_a_quoted_module_code_is_unquoted(self):
        self.write("lld/booking.md", '---\nmodule_code: "BK"\n---\n# Booking\n')
        t = self.tasks()
        self.assertIn("BK-4.1", t)
        self.assertIn("BK-4.2", t)
        self.assertIn("SCHEMA", t["BK-4.1"].depends)

    def test_an_element_page_under_api_is_reported(self):
        self.write("lld/booking/api/4-5-retry.md", "# Workflow 4.5: retry - Retries a failed sync\n")
        self.assertNotIn("BK-4.5", self.tasks())
        self.assertIn("lld/booking/api/4-5-retry.md: not a route page", cb.problems(self.set))

    def test_a_route_title_in_frontmatter_only_is_read(self):
        self.write("lld/booking/api/4-1-create.md",
                   '---\ntitle: "API 4.1: POST /bookings - Creates a booking"\n---\nBody.\n')
        self.assertEqual(self.tasks()["BK-4.1"].name, "Creates a booking")
        self.assertNotIn("lld/booking/api/4-1-create.md: not a route page", cb.problems(self.set))
        self.write("use-cases/uc-1-book.md",
                   '---\ntitle: "UC-1: Book a trip"\n---\n## Screens\n\n- Trip summary\n')
        self.assertEqual(self.tasks()["UC-1"].name, "Book a trip")

    def test_a_nested_title_key_in_frontmatter_is_not_the_page_title(self):
        self.write("lld/booking/api/4-1-create.md",
                   '---\ntitle: "API 4.1: POST /bookings - Creates a booking"\nsources:\n  - resource: x\n    title: Other\n---\n')
        self.assertEqual(self.tasks()["BK-4.1"].name, "Creates a booking")

    def test_a_fenced_comment_is_not_the_page_title(self):
        self.write("lld/booking/api/4-1-create.md",
                   '---\ntitle: "API 4.1: POST /bookings - Creates a booking"\n---\n```\n# comment\n```\n')
        self.assertEqual(self.tasks()["BK-4.1"].name, "Creates a booking")

    def test_an_element_page_with_a_summary_becomes_a_task(self):
        t = self.tasks()["BK-4.3"]
        self.assertEqual((t.name, t.scope, t.design),
                         ("Retries a failed sync", "Workflow retry", "lld/booking/retry.md"))

    def test_an_element_page_without_a_summary_takes_kind_and_name(self):
        self.write("lld/booking/retry.md", "# Schedule 4.3: orphanScan\n")
        t = self.tasks()["BK-4.3"]
        self.assertEqual((t.name, t.scope), ("Schedule orphanScan", "Schedule orphanScan"))

    def test_an_element_page_depends_on_schema_like_a_route(self):
        self.assertEqual(self.tasks()["BK-4.3"].depends, ["SCHEMA"])
        self.write("lld/payment.md", "---\nmodule_code: PY\n---\n# Payment\n")
        self.write("lld/payment/scan.md", "# Job 4.1: scan - Scans payments\n")
        self.assertEqual(self.tasks()["PY-4.1"].depends, [])

    def test_a_dependency_listing_the_element_id_adds_it(self):
        text = self.read("dependencies.md").replace("| BK-4.2 |", "| BK-4.2, BK-4.3 |")
        self.write("dependencies.md", text)
        self.assertEqual(self.tasks()["BK-4.3"].depends, ["SCHEMA", "DEP-1"])

    def test_a_page_with_a_non_matching_h1_yields_no_task_and_no_problem(self):
        self.write("lld/booking/execution-logic.md", "# Booking execution logic\n")
        self.write("lld/booking/scenarios.md", "# Scenarios\n")
        self.assertEqual([t.id for t in bd.read_tasks(self.set)],
                         ["SCHEMA", "BK-4.1", "BK-4.2", "BK-4.3", "UC-1"])
        self.assertEqual([p for p in cb.problems(self.set) if "execution-logic" in p or "scenarios" in p], [])

    def test_an_element_page_in_a_deeper_directory_yields_no_task(self):
        self.write("lld/booking/deep/other.md", "# Workflow 4.9: other - Other\n")
        self.assertNotIn("BK-4.9", self.tasks())
        self.assertIn("BK-4.3", self.tasks())

    def test_a_frontmatter_title_names_an_element_page(self):
        self.write("lld/booking/retry.md", '---\ntitle: "Consumer 4.3: retryQueue - Drains retries"\n---\nBody.\n')
        t = self.tasks()["BK-4.3"]
        self.assertEqual((t.name, t.scope), ("Drains retries", "Consumer retryQueue"))

    def test_routes_and_elements_sort_together_by_number(self):
        os.remove(self.path("lld/booking/api/4-1-create.md"))
        self.write("lld/booking/api/4-4-create.md", "# API 4.4: POST /bookings - Creates a booking\n")
        self.write("lld/booking/hold.md", "# Workflow 4.1: hold - Holds a seat\n")
        self.assertEqual([t.id for t in bd.read_tasks(self.set)],
                         ["SCHEMA", "BK-4.1", "BK-4.2", "BK-4.3", "BK-4.4", "UC-1"])

    def test_a_route_and_an_element_with_the_same_id_keep_the_route_and_report_the_page(self):
        self.write("lld/booking/hold.md", "# Workflow 4.1: hold - Holds a seat\n")
        self.assertEqual(self.tasks()["BK-4.1"].scope, "POST /bookings")
        self.assertIn("lld/booking/hold.md: duplicate task id BK-4.1", cb.problems(self.set))

    def test_an_element_scope_in_a_use_case_body_adds_no_dependency(self):
        text = self.read("use-cases/uc-1-book.md")
        before = self.tasks()["UC-1"].depends
        self.write("use-cases/uc-1-book.md", text + "\nWorkflow retry ends.\n")
        self.assertEqual(self.tasks()["UC-1"].depends, before)

    def test_a_multi_word_element_name_with_a_summary(self):
        self.write("lld/booking/retry.md", "# Notification 4.3: Loyalty Service events - Emits loyalty events\n")
        t = self.tasks()["BK-4.3"]
        self.assertEqual((t.name, t.scope), ("Emits loyalty events", "Notification Loyalty Service events"))

    def test_a_multi_word_element_name_without_a_summary(self):
        self.write("lld/booking/retry.md", "# Helper 4.3: Order cancel signal\n")
        t = self.tasks()["BK-4.3"]
        self.assertEqual((t.name, t.scope), ("Helper Order cancel signal", "Helper Order cancel signal"))

    def test_two_elements_with_one_number_keep_the_first_and_report_the_other(self):
        self.write("lld/booking/a-first.md", "# Job 4.7: first - First\n")
        self.write("lld/booking/b-second.md", "# Job 4.7: second - Second\n")
        self.assertEqual(self.tasks()["BK-4.7"].design, "lld/booking/a-first.md")
        self.assertIn("lld/booking/b-second.md: duplicate task id BK-4.7", cb.problems(self.set))

    def test_a_module_page_without_module_code_is_reported_when_it_holds_element_pages(self):
        self.write("lld/payment.md", "# Payment\n")
        self.write("lld/payment/scan.md", "# Job 4.1: scan - Scans payments\n")
        self.assertIn("lld/payment.md: no module_code", cb.problems(self.set))
        self.write("lld/other.md", "# Other\n")
        self.write("lld/other/notes.md", "# Other notes\n")
        self.assertNotIn("lld/other.md: no module_code", cb.problems(self.set))

    def run_cli(self, set_dir):
        return subprocess.run([sys.executable, SCRIPT, "--set", set_dir],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    def test_the_cli_refuses_a_set_directory_that_does_not_exist(self):
        result = self.run_cli(self.path("missing"))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_the_cli_exits_1_and_prints_one_line_per_problem(self):
        gb.generate(self.set)
        result = self.run_cli(self.set)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(len(result.stdout.splitlines()), 5)


if __name__ == "__main__":
    unittest.main()
