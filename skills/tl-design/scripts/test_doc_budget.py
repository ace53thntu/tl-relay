import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doc_budget as db

TH = "designs/dos-th-truck-booking/"
HUB = "projects/yff/.knowledge/"


def w(n):
    return " ".join(["word"] * n)


class DocBudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        p = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def check(self, rel, text):
        return db.check_page(self.write(rel, text))

    def rules(self, res):
        return [(v["rule"], v["where"]) for v in res["violations"]]

    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = db.main(list(argv))
        return code, out.getvalue()

    def test_prose_words_skips_fences_frontmatter_comments_images(self):
        text = "---\ntype: LLD\ntitle: a b c d e\n---\n" + w(10) + "\n![x](a.png)\n<!-- " + w(20) + " -->\n```mermaid\n" + w(50) + "\n```\n"
        self.assertEqual(db.prose_words(text), 10)

    def test_long_erdiagram_not_counted(self):
        text = w(5) + "\n```mermaid\nerDiagram\n" + "\n".join("A ||--o{ B : has" for _ in range(40)) + "\n```\n"
        self.assertEqual(db.prose_words(text), 5)

    def test_details_words_count(self):
        text = w(4) + "\n<details>\n<summary>more</summary>\n" + w(6) + "\n</details>\n"
        self.assertEqual(db.prose_words(text), 11)

    def test_table_text_counts_separator_does_not(self):
        text = "| a | b |\n| --- | --- |\n| c | d |\n"
        self.assertEqual(db.prose_words(text), 4)

    def test_sections_split_on_h3(self):
        text = "## Top\nx\n### 3.1 A\none two\n### 3.2 B\nthree\n"
        self.assertEqual(db.sections(text), [("### 3.1 A", "one two"), ("### 3.2 B", "three")])

    def test_contract_block_not_counted_or_flagged(self):
        text = w(10) + "\n<!-- contract:begin GET /x -->\n```json\n{\"a\": \"" + w(30) + "\"}\n```\n<!-- contract:end -->\n"
        r = self.check(TH + "lld/marketplace/api/4-1-get-x.md", text)
        self.assertEqual(r["words"], 10)
        self.assertEqual(r["violations"], [])

    def test_json_label_exemption(self):
        block = "```json\n{}\n```\n"
        ok = self.check(TH + "lld/marketplace/api/4-1-a.md", "**Response 403 · not-order-owner:**\n\n" + block)
        self.assertEqual(ok["violations"], [])
        bad = self.check(TH + "lld/marketplace/api/4-2-b.md", "Some prose here.\n\n" + block)
        self.assertEqual(self.rules(bad), [("forbidden-block", "json, line 3")])

    def test_forbidden_blocks(self):
        cases = [
            "```\nx\n```\n",
            "```text\nx\n```\n",
            "```ts\nx\n```\n",
            "```tsx\nx\n```\n",
            "```sql\nx\n```\n",
            "```yaml\nx\n```\n",
            "```bash\nx\n```\n",
            "| # | Check | Reply | Scenario |\n| --- | --- | --- | --- |\n| 1 | a | b | c |\n",
            "**Logic:**\nstep\n",
            "## DDL\nx\n",
            "**Great solution: x**\n",
        ]
        for i, c in enumerate(cases):
            r = self.check(TH + "lld/marketplace/m%d.md" % i, "intro\n\n" + c)
            self.assertEqual(len(r["violations"]), 1, (c, r["violations"]))
            self.assertEqual(r["violations"][0]["rule"], "forbidden-block")

    def test_page_types(self):
        cases = {
            "hlds/dos-th-truck-booking.md": "hla",
            "_knowledge/hlds/x.md": "hla",
            TH + "hlds/dos-th-truck-booking.md": "hla",
            TH + "hlds/dos-th-truck-booking/use-cases/uc-1-create.md": "use-case",
            TH + "hlds/planning/use-cases/pl-uc-1-create-a-week-plan.md": "use-case",
            TH + "hlds/visit-execution/use-cases/vx-uc-7-block-a-sign-in.md": "use-case",
            TH + "hlds/accounts-recommendations/use-cases/ar-uc-1-list.md": "use-case",
            TH + "hlds/priorities/use-cases/pr-uc-4-get.md": "use-case",
            TH + "hlds/planning/use-cases/index.md": "unknown",
            TH + "hlds/planning/use-cases/notes-uc.md": "unknown",
            TH + "lld/marketplace.md": "lld",
            TH + "lld/marketplace-api.md": "api",
            TH + "lld/marketplace/interface-contracts.md": "api",
            TH + "lld/marketplace/api/4-1-get-pickup-slots.md": "route",
            TH + "lld/marketplace/execution-logic.md": "execution-logic",
            TH + "lld/shared-execution-logic.md": "execution-logic",
            TH + "lld/marketplace/data-schema.md": "schema",
            TH + "lld/marketplace/scenarios.md": "scenarios",
            TH + "lld/marketplace-pickup-booking-temporal/workflow.md": "element",
            TH + "index.md": "unknown",
            TH + "open-points.md": "unknown",
            TH + "task-breakdown.md": "unknown",
            "designs/x/overview.md": "hla",
            "designs/x/schema-changes.md": "schema-changes",
            "designs/x/dependencies.md": "dependencies",
            "designs/yff-th/lld/schema-changes.md": "lld",
            HUB + "L1-architecture/yff__system-overview.md": "hla",
            HUB + "L2-integration/coupons/yff__coupons-lld.md": "lld",
            HUB + "L2-integration/coupons/yff__coupons-api.md": "api",
            HUB + "L2-integration/coupons/yff__coupons-lld/4-1-get.md": "route",
            HUB + "L2-integration/coupons/yff__coupons-lld/workflow.md": "element",
            HUB + "L2-integration/coupons/yff__coupons-lld/scenarios.md": "scenarios",
        }
        for path, want in cases.items():
            self.assertEqual(db.page_type(path), want, path)

    def test_dependencies_page_over_150_words_outside_the_table_fails(self):
        r = self.check("designs/x/dependencies.md", w(151) + "\n")
        self.assertEqual(self.rules(r), [("page-budget", "page")])

    def test_dependencies_table_lines_do_not_count(self):
        cell = " ".join(["cell"] * 10)
        rows = "".join("| %s | %s | %s |\n" % (cell, cell, cell) for _ in range(10))
        text = w(20) + "\n\n| a | b | c |\n| --- | --- | --- |\n" + rows
        r = self.check("designs/x/dependencies.md", text)
        self.assertEqual(r["words"], 20)
        self.assertEqual(r["violations"], [])

    def test_schema_changes_allows_ddl_heading_and_sql_fence(self):
        wrapped = "<details><summary>DDL in migration order</summary>\n\n```sql\nALTER TABLE a ADD b int;\n```\n\n</details>\n"
        r = self.check("designs/x/schema-changes.md", "intro\n\n## DDL\n\n```sql\nALTER TABLE a ADD b int;\n```\n\n" + wrapped)
        self.assertEqual(r["type"], "schema-changes")
        self.assertEqual(r["violations"], [])

    def test_ddl_heading_still_fails_on_an_lld_page(self):
        r = self.check(TH + "lld/marketplace.md", "intro\n\n## DDL\n\n```sql\nx\n```\n")
        self.assertIn(("forbidden-block", "## DDL heading, line 3"), self.rules(r))

    def test_relative_path_in_a_set_directory(self):
        d = os.path.join(tempfile.mkdtemp(), "designs", "x")
        os.makedirs(d)
        open(os.path.join(d, "overview.md"), "w").close()
        old = os.getcwd()
        os.chdir(d)
        try:
            self.assertEqual(db.page_type("overview.md"), "hla")
        finally:
            os.chdir(old)

    def test_hub_page_types(self):
        cases = {
            HUB + "L3-features/coupons/yff__coupons.md": "hla",
            HUB + "L3-features/import/yff__import.md": "hla",
            HUB + "L3-features/import/yff__import-schema.md": "schema",
            HUB + "L3-features/import/yff__import-sequences.md": "unknown",
            HUB + "L3-features/import/yff__import-actors-and-state.md": "unknown",
            HUB + "L1-architecture/yff__system-overview.md": "hla",
            HUB + "L1-architecture/yff__infrastructure.md": "unknown",
            HUB + "L2-integration/coupons/yff__coupons-lld/api/4-1-get-coupons.md": "route",
            HUB + "L2-integration/coupons/yff__coupons-lld/execution-logic.md": "execution-logic",
        }
        for path, want in cases.items():
            self.assertEqual(db.page_type(path), want, path)

    def test_index_and_local_pages_unknown(self):
        cases = [
            "_knowledge/plans/lld/index.md",
            "_knowledge/hlds/index.md",
            TH + "lld/index.md",
            TH + "lld/task-breakdown.md",
            TH + "hlds/open-points-full.md",
            TH + "implementation-notes.md",
            TH + "lld/implementation-notes.md",
        ]
        for path in cases:
            self.assertEqual(db.page_type(path), "unknown", path)

    def test_forbidden_where_has_line(self):
        text = "---\ntitle: x\n---\n\n<!-- contract:begin GET /x -->\n```json\n{}\n```\n<!-- contract:end -->\n\n```ts\nx\n```\n"
        r = self.check(TH + "lld/marketplace/api/4-1-get-x.md", text)
        self.assertEqual(self.rules(r), [("forbidden-block", "fence, line 11")])

    def test_baseline(self):
        p = self.write(TH + "lld/marketplace.md", "## DDL\n" + w(1300))
        code, out = self.run_cli(p, "--json")
        self.assertEqual(code, 1)
        base = self.write("baseline.json", out)
        self.assertEqual(self.run_cli(p, "--baseline", base)[0], 0)
        with open(p, "w", encoding="utf-8") as f:
            f.write("intro\n\n## DDL\n" + w(1290) + "\n**Logic:**\n")
        self.assertEqual(self.run_cli(p, "--baseline", base)[0], 1)
        code, out = self.run_cli(p, "--json", "--baseline", base)
        data = json.loads(out)
        self.assertEqual(self.rules(data["pages"][0]), [("forbidden-block", "**Logic:** label, line 5")])
        other = self.write(TH + "lld/other.md", "## DDL\n")
        self.assertEqual(self.run_cli(other, "--baseline", base)[0], 1)
        bad = self.write("bad.json", "not json")
        self.assertEqual(self.run_cli(p, "--baseline", bad)[0], 2)

    def baseline_of(self, p):
        return self.write("baseline.json", self.run_cli(p, "--json")[1])

    def test_baseline_growth_fails(self):
        p = self.write(TH + "hlds/a.md", "### 3.1 A\n" + w(500) + "\n")
        base = self.baseline_of(p)
        self.assertEqual(self.run_cli(p, "--baseline", base)[0], 0)
        with open(p, "w", encoding="utf-8") as f:
            f.write("### 3.1 A\n" + w(800) + "\n")
        code, out = self.run_cli(p, "--json", "--baseline", base)
        self.assertEqual(code, 1)
        v = json.loads(out)["pages"][0]["violations"][0]
        self.assertEqual(v["detail"], "800 words, budget 200, was 500 in baseline")

    def test_baseline_shrink_passes(self):
        p = self.write(TH + "hlds/a.md", "### 3.1 A\n" + w(500) + "\n")
        base = self.baseline_of(p)
        with open(p, "w", encoding="utf-8") as f:
            f.write("### 3.1 A\n" + w(300) + "\n")
        self.assertEqual(self.run_cli(p, "--baseline", base)[0], 0)

    def test_baseline_rows_growth_fails(self):
        def table(n):
            return "| a | b |\n| --- | --- |\n" + "".join("| %d | x |\n" % i for i in range(n))
        p = self.write(TH + "lld/marketplace/scenarios.md", table(20))
        base = self.baseline_of(p)
        self.assertEqual(self.run_cli(p, "--baseline", base)[0], 0)
        with open(p, "w", encoding="utf-8") as f:
            f.write(table(25))
        self.assertEqual(self.run_cli(p, "--baseline", base)[0], 1)

    def test_baseline_relative_paths(self):
        p = self.write(TH + "lld/marketplace.md", "## DDL\n" + w(1300))
        data = json.loads(self.run_cli(p, "--json")[1])
        data["pages"][0]["path"] = os.path.relpath(p, self.root)
        base = self.write("baseline.json", json.dumps(data))
        self.assertEqual(self.run_cli(p, "--baseline", base)[0], 0)

    def test_json_paths_are_absolute(self):
        p = self.write(TH + "lld/marketplace.md", "## DDL\n" + w(1300))
        w2 = self.write(TH + "lld/other.md", "x")
        old = os.getcwd()
        os.chdir(self.root)
        try:
            data = json.loads(self.run_cli(os.path.relpath(p, self.root), os.path.relpath(w2, self.root), "--waive", os.path.relpath(w2, self.root), "--json")[1])
        finally:
            os.chdir(old)
        self.assertEqual(data["pages"][0]["path"], os.path.realpath(p))
        self.assertEqual(data["waived"], [os.path.realpath(w2)])

    def test_hub_lld_budget_applied(self):
        r = self.check(HUB + "L2-integration/coupons/yff__coupons-lld.md", w(1201))
        self.assertEqual(self.rules(r), [("page-budget", "page")])

    def test_unknown_page_unchecked(self):
        text = "```json\n{\"stage\": \"hla\"}\n```\n" + w(5000)
        r = self.check(TH + "index.md", text)
        self.assertEqual(r["type"], "unknown")
        self.assertEqual(r["violations"], [])

    def test_hla_section_budgets(self):
        ok = self.check(TH + "hlds/a.md", "### 3.1 A\n" + w(200) + "\n### 4.1 B\n" + w(320) + "\n")
        self.assertEqual(ok["violations"], [])
        r = self.check(TH + "hlds/b.md", "### 3.1 A\n" + w(201) + "\n### 4.2 B\n" + w(321) + "\n")
        self.assertEqual(self.rules(r), [("section-budget", "3.1"), ("section-budget", "4.2")])
        r = self.check(TH + "hlds/c.md", "### 3.5 Other\n" + w(201) + "\n")
        self.assertEqual(self.rules(r), [("section-budget", "3.5")])
        r = self.check(TH + "hlds/d.md", "### 5.1 Q\n" + w(121) + "\n")
        self.assertEqual(self.rules(r), [("section-budget", "5.1")])
        ok = self.check(TH + "hlds/e.md", "### 5.1 Q\n" + w(120) + "\n")
        self.assertEqual(ok["violations"], [])

    def test_final_design_has_no_section_budget(self):
        r = self.check(TH + "hlds/c.md", "### 3.6 Final design\n" + w(400) + "\n")
        self.assertEqual(r["violations"], [])
        r = self.check(TH + "hlds/e.md", "### 3.6 Final design\n" + w(4001) + "\n")
        self.assertEqual(self.rules(r), [("page-budget", "page")])

    def test_hla_failure_count(self):
        eight = "".join("### 5.%d Q\n%s\n" % (i, w(10)) for i in range(1, 9))
        self.assertEqual(self.check(TH + "hlds/a.md", eight)["violations"], [])
        r = self.check(TH + "hlds/b.md", eight + "### 5.9 Q\n" + w(10) + "\n")
        self.assertEqual(self.rules(r), [("failure-count", "5")])

    def test_execution_logic_rules_budget(self):
        rel = TH + "lld/marketplace/execution-logic.md"
        ok = self.check(rel, w(1000) + "\n\n## Rules\n" + w(800) + "\n")
        self.assertEqual(ok["violations"], [])
        bad = self.check(rel, w(1000) + "\n\n## Rules\n" + w(801) + "\n")
        self.assertEqual(self.rules(bad), [("section-budget", "Rules")])
        over = self.check(rel, w(1001) + "\n\n## Rules\n" + w(800) + "\n")
        self.assertEqual(self.rules(over), [("page-budget", "page")])

    def test_page_budget(self):
        rel = TH + "lld/marketplace/api/4-1-get-x.md"
        self.assertEqual(self.check(rel, w(300))["violations"], [])
        self.assertEqual(self.rules(self.check(rel, w(301))), [("page-budget", "page")])

    def test_scenario_rows(self):
        def table(n):
            return "| a | b |\n| --- | --- |\n" + "".join("| %d | x |\n" % i for i in range(n))
        rel = TH + "lld/marketplace/scenarios.md"
        self.assertEqual(self.check(rel, table(15))["violations"], [])
        r = self.check(rel, table(16))
        self.assertEqual(self.rules(r), [("row-budget", "table 1")])

    def test_old_page_reports_and_is_not_edited(self):
        text = "## DDL\n```sql\nx\n```\n" + w(2000)
        p = self.write(TH + "lld/marketplace.md", text)
        code, _ = self.run_cli(p)
        self.assertEqual(code, 1)
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), text)

    def test_waive(self):
        p = self.write(TH + "lld/marketplace/api/4-1-get-x.md", w(400))
        code, out = self.run_cli(p, "--json", "--waive", p)
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["waived"], [os.path.realpath(p)])
        self.assertEqual(data["pages"], [])

    def test_exit_codes(self):
        self.write(TH + "lld/marketplace/api/4-1-ok.md", w(10))
        self.assertEqual(self.run_cli(self.root)[0], 0)
        self.write(TH + "lld/marketplace/api/4-2-bad.md", w(400))
        code, out = self.run_cli(self.root, "--json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["pages"][1]["violations"][0]["rule"], "page-budget")
        self.assertEqual(self.run_cli(os.path.join(self.root, "missing"))[0], 2)

    def test_walk_skips_archived_audits_stage(self):
        for d in ("_archived", "audits", "_stage-x"):
            self.write(TH + d + "/lld/marketplace.md", w(5000))
        self.assertEqual(self.run_cli(self.root)[0], 0)

    def test_walk_skips_publish_and_runs(self):
        self.write(TH + "publish/_knowledge/lld/marketplace.md", w(5000))
        self.write(TH + "runs/r1/lld/marketplace.md", w(5000))
        self.assertEqual(self.run_cli(self.root)[0], 0)

    def test_walk_skips_hidden_dirs_and_files(self):
        self.write(TH + ".draft/lld/marketplace.md", w(5000))
        self.write(TH + "lld/.big.md", w(5000))
        self.assertEqual(self.run_cli(self.root)[0], 0)
        self.write(TH + "lld/big.md", w(5000))
        self.assertEqual(self.run_cli(self.root)[0], 1)
        with tempfile.TemporaryDirectory() as hub_root:
            p = os.path.join(hub_root, HUB + "L2-integration/coupons/yff__coupons-lld.md")
            os.makedirs(os.path.dirname(p))
            with open(p, "w", encoding="utf-8") as f:
                f.write(w(5000))
            self.assertEqual(self.run_cli(os.path.join(hub_root, HUB))[0], 1)

    def terms_hla(self, terms_body):
        return self.write("d/hlds/x.md", "Intro.\n\n## Terms\n\n" + terms_body + "\n\n## 1. Requirements\n\nText.\n")

    def term_violations(self, link_text):
        route = self.write("d/lld/m/api/4-1-a.md", "See [%s](../../../hlds/x.md#terms) here.\n" % link_text)
        hla = os.path.join(self.root, "d/hlds/x.md")
        _, out = self.run_cli(route, hla, "--json")
        pages = {os.path.basename(pg["path"]): pg for pg in json.loads(out)["pages"]}
        return pages["4-1-a.md"]["violations"]

    def hit(self, res, rule):
        return [v for v in res["violations"] if v["rule"] == rule]

    def test_terms_entry_over(self):
        r = db.check_page(self.terms_hla("- **Walk-in**: " + w(30)))
        v = self.hit(r, "terms-entry")
        self.assertEqual([(x["where"], x["detail"]) for x in v], [("Walk-in, line 5", "31 words, budget 30")])

    def test_terms_entry_ok(self):
        r = db.check_page(self.terms_hla("- **Walk-in**: " + w(29)))
        self.assertEqual(self.hit(r, "terms-entry"), [])

    def test_terms_value_number(self):
        r = db.check_page(self.terms_hla("- **Reconciliation scan**: The job that runs every 15 minutes."))
        self.assertEqual([x["where"] for x in self.hit(r, "terms-value")], ["Reconciliation scan, line 5"])

    def test_terms_value_code_list(self):
        r = db.check_page(self.terms_hla("- **Attempt**: A row holding `type` and `status`."))
        self.assertEqual(len(self.hit(r, "terms-value")), 1)

    def test_terms_value_digit_in_word(self):
        r = db.check_page(self.terms_hla("- **Booker**: The retailer on a b2b direct order."))
        self.assertEqual(self.hit(r, "terms-value"), [])

    def test_terms_value_ok(self):
        r = db.check_page(self.terms_hla("- **Book-again**: A new attempt on an order whose `status` is final, see [4.4](x.md#44-a)."))
        self.assertEqual(self.hit(r, "terms-value"), [])

    def test_terms_no_total_cap(self):
        body = "\n".join("- **Term%d**: %s" % (i, w(20)) for i in range(20))
        r = db.check_page(self.terms_hla(body))
        self.assertEqual(r["violations"], [])

    def panel(self, kind, approach="Short.", challenges="Short."):
        return "> [!TIP]\n> **%s solution: x**\n>\n> **Approach.** %s\n>\n> **Challenges.** %s\n\n" % (kind, approach, challenges)

    def deep_dive(self, approach="Short.", challenges="Short."):
        return "### 4.1 How?\n\nProblem.\n\n" + self.panel("Bad", challenges=challenges) + self.panel("Great", approach, challenges)

    def hla_page(self, body):
        return self.write("d/hlds/x.md", "Intro.\n\n## 4. Deep dives\n\n" + body)

    def test_panels_allowed_on_hla(self):
        page = self.hla_page("### 4.1 How?\n\nProblem.\n\n" + self.panel("Bad") + self.panel("Good") + self.panel("Great"))
        self.assertEqual(self.hit(db.check_page(page), "forbidden-block"), [])

    def test_panels_allowed_on_use_case(self):
        p = self.write("d/designs/x/use-cases/uc-1-a.md", "## Decision\n\nProblem.\n\n" + self.panel("Great"))
        self.assertEqual(self.hit(db.check_page(p), "forbidden-block"), [])

    def test_panels_forbidden_on_lld(self):
        p = self.write("d/designs/x/lld/m/api/4-1-a.md", self.panel("Great"))
        self.assertEqual(len(self.hit(db.check_page(p), "forbidden-block")), 1)

    def test_approach_over(self):
        r = db.check_page(self.hla_page(self.deep_dive(approach=w(76))))
        v = self.hit(r, "decision-words")
        self.assertEqual([(x["where"], x["detail"]) for x in v], [("### 4.1 How?, line 19", "76 words, budget 75")])

    def test_approach_ok(self):
        r = db.check_page(self.hla_page(self.deep_dive(approach=w(75))))
        self.assertEqual(self.hit(r, "decision-words"), [])

    def test_approach_of_bad_panel_not_capped(self):
        page = self.hla_page("### 4.1 How?\n\nProblem.\n\n" + self.panel("Bad", approach=w(90)) + self.panel("Great"))
        self.assertEqual(self.hit(db.check_page(page), "decision-words"), [])

    def test_challenges_over(self):
        r = db.check_page(self.hla_page(self.deep_dive(challenges=w(51))))
        self.assertEqual(len(self.hit(r, "challenges-words")), 2)

    def test_challenges_ok(self):
        r = db.check_page(self.hla_page(self.deep_dive(challenges=w(50))))
        self.assertEqual(self.hit(r, "challenges-words"), [])

    def test_challenges_in_good_panel_over(self):
        page = self.hla_page("### 4.1 How?\n\nProblem.\n\n" + self.panel("Good", challenges=w(51)) + self.panel("Great"))
        self.assertEqual(len(self.hit(db.check_page(page), "challenges-words")), 1)

    def test_challenges_multi_line_counts_whole_paragraph(self):
        page = self.hla_page("### 4.1 How?\n\nProblem.\n\n> [!TIP]\n> **Great solution: x**\n>\n> **Challenges.** " + w(30) + "\n> " + w(30) + "\n")
        self.assertEqual(len(self.hit(db.check_page(page), "challenges-words")), 1)

    def legacy_form(self, decision="Short.", cost="- Short."):
        body = "### 4.1 How?\n\nProblem.\n\n**Decision.** %s\n\n**Rejected.**\n\n- A: no.\n\n**Cost.**\n\n%s\n" % (decision, cost)
        return self.write("d/lld/m/api/4-1-a.md", body)

    def test_legacy_decision_over(self):
        v = self.hit(db.check_page(self.legacy_form(decision=w(76))), "decision-words")
        self.assertEqual([(x["where"], x["detail"]) for x in v], [("### 4.1 How?, line 5", "76 words, budget 75")])

    def test_legacy_decision_ok(self):
        self.assertEqual(self.hit(db.check_page(self.legacy_form(decision=w(75))), "decision-words"), [])

    def test_legacy_cost_bullet_over(self):
        self.assertEqual(len(self.hit(db.check_page(self.legacy_form(cost="- " + w(31))), "cost-words")), 1)

    def test_legacy_cost_bullet_ok(self):
        self.assertEqual(self.hit(db.check_page(self.legacy_form(cost="- " + w(30))), "cost-words"), [])

    def test_legacy_cost_four_bullets_ok(self):
        p = self.legacy_form(cost="\n".join("- " + w(25) for _ in range(4)))
        self.assertEqual(self.hit(db.check_page(p), "cost-words"), [])

    def test_legacy_decision_stops_at_blockquote(self):
        p = self.legacy_form(decision=w(70) + "\n> [!WARNING]\n> " + w(30))
        self.assertEqual(self.hit(db.check_page(p), "decision-words"), [])

    def test_legacy_cost_stops_at_blockquote(self):
        p = self.legacy_form(cost="- " + w(20) + "\n> [!WARNING]\n> " + w(30))
        self.assertEqual(self.hit(db.check_page(p), "cost-words"), [])

    def test_decision_cost_kept_on_route_page(self):
        p = self.write("d/lld/m/api/4-1-a.md", "**Decision.** " + w(90) + "\n\n**Cost.**\n\n- " + w(40) + "\n")
        self.assertEqual(sorted(x["rule"] for x in db.check_page(p)["violations"] if x["rule"].endswith("-words")), ["cost-words", "decision-words"])

    def test_decision_cost_not_counted_on_hla(self):
        page = self.hla_page("### 4.1 How?\n\nProblem.\n\n**Decision.** " + w(90) + "\n")
        self.assertEqual(self.hit(db.check_page(page), "decision-words"), [])

    def test_challenges_split_by_blank_quote_line(self):
        page = self.hla_page("### 4.1 How?\n\n> [!TIP]\n> **Great solution: x**\n>\n> **Challenges.** " + w(30) + "\n>\n> " + w(30) + "\n")
        self.assertEqual(len(self.hit(db.check_page(page), "challenges-words")), 1)

    def test_challenges_bullets_after_bare_label(self):
        page = self.hla_page("### 4.1 How?\n\n> [!TIP]\n> **Great solution: x**\n>\n> **Challenges.**\n>\n> - " + w(26) + "\n> - " + w(25) + "\n")
        self.assertEqual(len(self.hit(db.check_page(page), "challenges-words")), 1)

    def test_continuation_starting_bold_counts(self):
        page = self.hla_page("### 4.1 How?\n\n> [!TIP]\n> **Great solution: x**\n>\n> **Approach.** " + w(46) + "\n> **Kenya** " + w(29) + "\n")
        self.assertEqual(len(self.hit(db.check_page(page), "decision-words")), 1)

    def test_waits_on_panel_not_counted_in_approach(self):
        page = self.hla_page("### 4.1 How?\n\n> [!TIP]\n> **Great solution: x**\n>\n> **Approach.** " + w(40) + "\n>\n> [!WARNING]\n> **Waits on:** " + w(40) + "\n")
        self.assertEqual(self.hit(db.check_page(page), "decision-words"), [])

    def test_term_missing(self):
        self.terms_hla("- **Walk-in**: a walk-in order.")
        v = self.term_violations("Booker")
        self.assertEqual([(x["rule"], x["where"], x["detail"]) for x in v], [("term-missing", "Booker, line 1", "Booker")])

    def test_term_present_plural(self):
        self.terms_hla("- **Walk-in**: a walk-in order.")
        self.assertEqual(self.term_violations("Walk-ins"), [])

    def test_term_present_plural_ies(self):
        self.terms_hla("- **Offline copy**: a module's last read on the phone.")
        self.assertEqual(self.term_violations("offline copies"), [])

    def test_term_plural_ies_needs_y_entry(self):
        self.terms_hla("- **Walk-in**: a walk-in order.")
        self.assertEqual(len(self.term_violations("Walk-inies")), 1)

    def test_term_split_entry(self):
        self.terms_hla("- **Toggle ON path, toggle OFF path**: the two paths.")
        self.assertEqual(self.term_violations("toggle OFF path"), [])

    def test_term_target_not_in_run(self):
        self.terms_hla("- **Walk-in**: a walk-in order.")
        route = self.write("d/lld/m/api/4-1-a.md", "See [Booker](../../../hlds/x.md#terms) here.\n")
        code, out = self.run_cli(route)
        self.assertEqual((code, out), (0, ""))

    def test_term_normalised(self):
        self.terms_hla("- **Walk-in**: a walk-in order.\n- **Book-again**: a rebooking.")
        self.assertEqual(self.term_violations("the `Walk-in`"), [])
        self.assertEqual(self.term_violations("book again"), [])

    def test_term_and_split(self):
        self.terms_hla("- **Toggle ON path, toggle OFF path**: the two paths.")
        self.assertEqual(self.term_violations("toggle ON path and the toggle OFF path"), [])

    def test_term_inflected_still_flagged(self):
        self.terms_hla("- **Adoption**: taking over an order.")
        self.assertEqual(len(self.term_violations("adopted")), 1)

    def test_term_in_inline_code_skipped(self):
        self.terms_hla("- **Walk-in**: a walk-in order.")
        route = self.write("d/lld/m/api/4-1-a.md", "Write `[Booker](../../../hlds/x.md#terms)` to link.\n")
        hla = os.path.join(self.root, "d/hlds/x.md")
        self.assertEqual(self.run_cli(route, hla), (0, ""))

    def test_term_missing_baseline_survives_line_shift(self):
        self.terms_hla("- **Walk-in**: a walk-in order.")
        route = self.write("d/lld/m/api/4-1-a.md", "See [Booker](../../../hlds/x.md#terms) here.\n")
        hla = os.path.join(self.root, "d/hlds/x.md")
        _, out = self.run_cli(route, hla, "--json")
        base = os.path.join(self.root, "base.json")
        with open(base, "w") as f:
            f.write(out)
        self.write("d/lld/m/api/4-1-a.md", "New line.\n\nSee [Booker](../../../hlds/x.md#terms) here.\n")
        self.assertEqual(self.run_cli(route, hla, "--baseline", base)[0], 0)

    def term_line_violations(self, line):
        self.terms_hla("- **Adoption**: taking over an order.")
        route = self.write("d/lld/m/api/4-1-a.md", line + "\n")
        hla = os.path.join(self.root, "d/hlds/x.md")
        _, out = self.run_cli(route, hla, "--json")
        pages = {os.path.basename(pg["path"]): pg for pg in json.loads(out)["pages"]}
        return [x["detail"] for x in pages["4-1-a.md"]["violations"] if x["rule"] == "term-missing"]

    def test_term_link_with_code_text_and_later_code(self):
        self.assertEqual(self.term_line_violations("[`Walk-in`](../../../hlds/x.md#terms) and `foo`"), ["`Walk-in`"])

    def test_term_link_between_code_spans(self):
        self.assertEqual(self.term_line_violations("`a` then [Booker](../../../hlds/x.md#terms) then `b`"), ["Booker"])


if __name__ == "__main__":
    unittest.main()
