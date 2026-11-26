import pathlib
import unittest

SKILLS = pathlib.Path(__file__).resolve().parents[1]


class PortableTlDesignTest(unittest.TestCase):
    text = (SKILLS / "tl-design/SKILL.md").read_text()

    def test_reads_config_keys_with_defaults(self):
        for needle in (".tl-relay/config.yaml", "operator_language", "`en`", "state_dir", "knowledge_dir",
                       "publish.command", "publish.confirm_flag", "{dir}", "{target}"):
            self.assertIn(needle, self.text)

    def test_publish_dir_sits_in_state_dir(self):
        self.assertIn("<runtime>/designs/<handle>/publish/", self.text)

    def test_publish_skips_without_a_command(self):
        self.assertIn("When `publish.command` is unset, step 12 reports the skip and the run goes on to step 13.", self.text)

    def test_publish_waits_for_the_dry_run_approval(self):
        self.assertIn("Then stop and wait for the operator to approve that output.", self.text)
        self.assertIn("When `publish.confirm_flag` is unset, run the command once, only after the operator approves the target.", self.text)

    def test_none_mode_names_the_role_source(self):
        self.assertIn("`ROLES` and `MODELS` constants in `<skill dir>/workflows/design-persona-review.js`", self.text)
        self.assertIn("`design-writer` runs on `opus`", self.text)

    def test_publish_dir_is_gitignored(self):
        self.assertIn("adds the line `<runtime>/designs/*/publish/` to the workspace `.gitignore` if absent", self.text)
        self.assertNotIn("the line `<state_dir>/designs/`", self.text)
        self.assertIn("Every step 12 run checks the workspace `.gitignore`", self.text)
        self.assertIn("relative to the workspace root", self.text)
        unset = "- When `publish.command` is unset, step 12 reports the skip and the run goes on to step 13.\n- Otherwise"
        self.assertIn(unset, self.text)
        self.assertLess(self.text.index("Every step 12 run checks"), self.text.index(unset))

    def writer_role(self):
        return self.text.split("`design-writer` runs on `opus`", 1)[1].split("- No subagent tool", 1)[0]

    def test_none_mode_writer_role_matches_the_agent_file(self):
        body = (SKILLS.parent / "agents/design-writer.md").read_text().split("---", 2)[2]
        self.assertIn("`key_class`", body)
        role = " ".join(self.writer_role().split())
        trigger = " ".join(body.split("only when ", 1)[1].split(".", 1)[0].split())
        self.assertIn(trigger, role)
        tag = " ".join(body.split("§ Agent decisions ", 1)[1].split(".", 1)[0].split())
        self.assertIn(tag, role)

    def test_ask_rule_table_has_a_none_row(self):
        table = self.text.split("## Ask rule", 1)[1].split("**Open points.**", 1)[0]
        for value in ("contract", "data_model", "architecture", "security_release", "timeline", "none"):
            self.assertIn(f"| `{value}` |", table)

    def test_none_mode_writer_role_points_to_the_ask_rule_table(self):
        role = self.writer_role()
        self.assertIn("quotes the [Ask rule](#ask-rule) `key_class` table", " ".join(role.split()))
        self.assertNotIn("| `contract` |", role)
        self.assertNotIn("lens finding schema", role)
        self.assertIn("It never asks about a choice that matches the code at the baseline, follows from an earlier answer, "
                      "or carries out an answered decision.", role)

    def test_every_writer_dispatch_quotes_the_ask_rule(self):
        dispatch = self.text.split("The session dispatches `design-writer`", 1)[1].split("Questions to the operator", 1)[0]
        self.assertIn("Every `design-writer` dispatch prompt, in `plugin`, `bare` and `none` mode, quotes the "
                      "[Ask rule](#ask-rule) `key_class` table, with the `none` row, and its never-ask sentence.",
                      " ".join(dispatch.split()))

    def test_lint_runs_only_when_present(self):
        self.assertIn("| `sh \"$K/scripts/lint.sh\"`, only when `knowledge_dir` is set and `$K/scripts/lint.sh` exists | The hub |",
                      self.text)
        self.assertIn("When `knowledge_dir` is unset or `$K/scripts/lint.sh` does not exist, the head reports the lint skip "
                      "and the gate does not wait on it.", self.text)
        self.assertNotIn("Each must exit 0", self.text)

    def test_design_root_feeds_the_scripts(self):
        for needle in ("`DROOT` is the absolute `<design root>`", "`D` is `$DROOT/designs/<handle>`",
                       '--knowledge-root "$DROOT"', "| `workspace` |", "../using-tl-relay/config.md"):
            self.assertIn(needle, self.text)
        self.assertNotIn("`D` is `$K/designs/<handle>`", self.text)

    def test_file_tasks_skips_without_a_command(self):
        self.assertIn("with no such command, report a skip and go to step 14", self.text)

    def test_no_hard_coded_knowledge_dir(self):
        self.assertNotIn("`_knowledge/designs/", self.text)

    def test_scripts_resolve_from_the_skill_dir(self):
        self.assertNotIn("~/.claude/skills", self.text)
        self.assertNotIn("WF/", self.text)
        self.assertIn("<skill dir>/workflows/design-set-write.js", self.text)

    def test_agents_mode_and_sequential_fallback(self):
        for needle in ("`plugin`", "`bare`", "`none`", "tl-relay:", "Running without agents or Workflows"):
            self.assertIn(needle, self.text)

    def test_sibling_check(self):
        self.assertIn("npx skills add", self.text)

    def test_lens_shared_installs_as_a_skill(self):
        text = (SKILLS / "lens-shared/SKILL.md").read_text()
        self.assertIn("name: lens-shared", text)
        self.assertIn("finding-schema.md", text)

    def test_retro_edits_only_in_a_checkout(self):
        self.assertNotIn("ai-sdlc/skills/", self.text)
        self.assertIn("git checkout of `tl-relay`", self.text)

    def test_no_home_coupling(self):
        for needle in ("AI_SDLC_HOME", "ai-sdlc.yaml"):
            self.assertNotIn(needle, self.text)


    def test_step_one_splits_ingest_between_writer_and_session(self):
        row = next(l for l in self.text.splitlines() if l.startswith("| 1 | Ingest |"))
        self.assertIn("For a `stories` revision: 1 to 4.3, then 4.6 and 4.7. The session runs 4.4 and 4.5", row)
        self.assertNotIn("records no run id for step 1", self.text)
        self.assertIn("at steps 1, 5, 8 and 9.", self.text)
        block = self.text.split("A new revision of a `stories` source runs in four parts:", 1)[1].split("## Steps", 1)[0]
        for needle in ("It stops once `$WS/slices.json` exists.", "If it returns without `slices.json`",
                       "`$WS/drift-args.json`", "`$WS/writer.json`", "`<runtime>/designs/<handle>/runs/`", "Run `ingest-sources` step 4.4 in the session",
                       "for `ingest-sources` steps 4.6 and 4.7 on the same `$WS`", "with the `--page` flags",
                       "A resume at step 1 reads `ingest_ws`", "Reuse `ingest_ws` when it is set.",
                       "every step 1 entry in `workflow_runs`", "With `G-ingest` signed, it finishes part 4.",
                       "If it returns without `$WS/impact.tsv`", "Write that line relative to the workspace root."):
            self.assertIn(needle, block)
        self.assertIn("A dispatch skips the snapshot when the revision in `ingest_sha256` is already recorded.", self.text)
        self.assertNotIn("D/ingest/", self.text)
        self.assertIn("Then remove `G-ingest` from `signed:`, and run `set-stage --stage ingest --status draft`.", self.text)
        self.assertIn("rerun `set-stage --stage ingest --status signed-off` with the gate date", self.text)
        self.assertNotIn("under `D/runs/`", self.text)
        self.assertIn("steps 1 to 3. The session then presents `G-ingest`.", self.text)
        template = (SKILLS / "tl-design/templates/workflow-state.md").read_text()
        self.assertIn("ingest_ws:", template)
        self.assertIn("ingest_sha256:", template)


if __name__ == "__main__":
    unittest.main()
