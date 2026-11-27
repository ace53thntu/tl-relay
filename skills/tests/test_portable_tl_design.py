import pathlib
import unittest

SKILLS = pathlib.Path(__file__).resolve().parents[1]


class PortableTlDesignTest(unittest.TestCase):
    text = (SKILLS / "tl-design/SKILL.md").read_text()

    def test_reads_config_keys_with_defaults(self):
        for needle in (".tl-relay/config.yaml", "operator_language", "`en`", "state_dir", "knowledge_dir",
                       "publish.command", "publish.confirm_flag", "{dir}", "{target}"):
            self.assertIn(needle, self.text)

    def test_restage_keeps_only_the_blocks_publish_keep_names(self):
        self.assertIn("publish.keep", self.text)
        self.assertIn("--keep", self.text)
        self.assertNotIn("`confluence:` block", self.text)

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

    def test_state_command_sets_no_shell_variable(self):
        self.assertNotIn("S=<skill dir>", self.text)
        self.assertNotIn('"$S"', self.text)
        self.assertIn('python3 "<skill dir>/scripts/state.py" --knowledge-root', self.text)
        self.assertIn("Set no shell variable in a command, because Claude Code asks before every command that sets one.",
                      " ".join(self.text.split()))

    def test_sibling_check(self):
        section = " ".join(self.text.split("## Sibling skills")[1].split("\n## ")[0].split())
        self.assertIn("in the session's skill list", section)
        self.assertIn("The list is the whole check: run no command and read no file for it.", section)
        self.assertNotIn("sits beside", section)
        self.assertIn("npx skills add", section)

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
                       "is not empty and `$WS/impact.tsv` is missing", "`ingest-<date>-<first 8 characters of ingest_sha256>`", "Write that line relative to the workspace root."):
            self.assertIn(needle, block)
        for needle in ("Write the drift args, `digest` included, to `$WS/drift-args.json`",
                       "Part 2 is done once `$WS/adjudication.json` carries the `inputs_sha256` that `assemble.py --pending` prints.",
                       "A resume whose `--pending` list is empty reruns only step 4.5.",
                       "Part 3 is done once the drift record's `audits/<date>-stories-adjudication.json` carries that `inputs_sha256`."):
            self.assertIn(needle, block)
        self.assertIn("With no such run, it continues from the first part that is not done.", self.text)
        self.assertNotIn("Part 2 is done once `$WS/adjudication.json` exists.", block)
        self.assertNotIn("the first part whose output is missing", self.text)
        self.assertIn("A dispatch skips the snapshot when the revision in `ingest_sha256` is already recorded.", self.text)
        self.assertNotIn("D/ingest/", self.text)
        self.assertIn("On a fresh entry, remove `G-ingest` from `signed:`, and run `set-stage --stage ingest --status draft`.", self.text)
        self.assertIn("rerun `set-stage --stage ingest --status signed-off` with the gate date", self.text)
        self.assertNotIn("under `D/runs/`", self.text)
        self.assertIn("Also clear `ingest_ws` and every step 1 entry in `workflow_runs`.", self.text)
        self.assertIn("steps 1 to 3. The session then presents `G-ingest`.", self.text)
        template = (SKILLS / "tl-design/templates/workflow-state.md").read_text()
        self.assertIn("ingest_ws:", template)
        self.assertIn("ingest_sha256:", template)

    def test_ingest_errors_reach_the_operator(self):
        text = " ".join(self.text.split())
        d1 = "Every `design-writer` dispatch for `ingest-sources`, the first snapshot's included, adds one rule to its prompt."
        d2 = "A sentence of `ingest-sources` that sends an error to the operator outranks the Ask rule: stop there and return that error as a question."
        s1 = "When such a dispatch returns that question, ask it through `AskUserQuestion` before any other step, not as a plain report."
        s2 = "Never add it to the open points, and present no `G-ingest` until the operator answers."
        p1 = "A nonzero exit from that rerun goes to the operator as a question."
        p2 = "Nothing is cleared until the operator answers."
        paragraph = " ".join((d1, d2, s1, s2))
        self.assertIn(paragraph, text)
        self.assertIn(" ".join((p1, p2)), text)
        self.assertLess(text.index("With `G-ingest` signed, it finishes part 4."), text.index(paragraph))
        self.assertLess(text.index(paragraph), text.index("## Steps"))
        self.assertLess(text.index("Then rerun the `gen_register.py` command"), text.index(p1))
        self.assertLess(text.index(p2), text.index("Last, clear `ingest_ws`"))
        self.assertIn("If it returns without `slices.json` or `writer.json`, report its reason and stop.", text)

    def test_first_snapshot_resume_holds_g_ingest(self):
        text = " ".join(self.text.split())
        f1 = "At step 1, a source already recorded with `baseline: true` counts as ingested unless it is the only recorded source of its kind and `ingest_sha256` holds its file `sha256`. Skip its snapshot."
        l107 = "A source with no baseline of its kind takes one `design-writer` dispatch for `ingest-sources` steps 1 to 3. The session then presents `G-ingest`."
        f2 = "After the gate rules for a first snapshot, clear `ingest_sha256`."
        f3 = "When `ingest_sha256` holds the only recorded source of its kind, a resume with `G-ingest` unsigned repeats that dispatch, with the snapshot skipped."
        f4 = "With `G-ingest` signed, that resume finishes the gate rules, then clears `ingest_sha256`."
        f5 = "Another file waits while `ingest_sha256` holds the only recorded source of its kind."
        f6 = "A new revision enters step 1 fresh when `ingest_sha256` does not hold its file `sha256`."
        f8 = "A source with no baseline of its kind enters step 1 fresh when `ingest_sha256` is empty, and otherwise waits."
        f7 = "Then record the file's `sha256` as `ingest_sha256` in `workflow-state.md`."
        block = " ".join((f1, l107, f2, f3, f4, f5, f6, f8))
        self.assertIn(block, text)
        self.assertIn(f7, text)
        self.assertLess(text.index("## Start and resume"), text.index(block))
        self.assertLess(text.index(block), text.index(f7))
        self.assertLess(text.index(f7), text.index("## Steps"))
        self.assertNotIn("counts as ingested. Skip its snapshot.", text)
        self.assertNotIn("Then record the revision's file", text)
        self.assertIn("A dispatch skips the snapshot when the revision in `ingest_sha256` is already recorded.", text)


if __name__ == "__main__":
    unittest.main()
