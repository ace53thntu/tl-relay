import pathlib
import tempfile
import unittest

from test_skills import frontmatter, yamlio

ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENTS = ["design-writer", "solution-architect", "software-engineer",
          "qa-engineer", "qa-conformance", "security-engineer", "temporal-reviewer",
          "temporal-code-reviewer"]
KEY_CLASSES = ["contract", "data_model", "architecture", "security_release", "timeline", "none"]
ERROR_CLASSES = ["missing_detail", "voice_structure", "length_focus", "key_decision_unasked", "other"]
EXPECTED = {
    "design-writer": ("opus", ["write-hla", "write-design", "write-lld", "write-contract", "ingest-sources", "write-task-breakdown", "technical-writing"]),
    "solution-architect": ("opus", ["lens-solution-architect"]),
    "software-engineer": ("sonnet", ["lens-software-engineer"]),
    "qa-engineer": ("sonnet", ["lens-qa-engineer"]),
    "qa-conformance": ("opus", ["lens-qa-conformance"]),
    "security-engineer": ("opus", ["lens-security-engineer"]),
    "temporal-reviewer": ("opus", ["temporal-workflow-design-critic"]),
    "temporal-code-reviewer": ("opus", ["temporal:temporal-developer", "temporal-developer"]),
}
NON_REVIEWER_LENSES = {"lens-qa-conformance"}
EXTERNAL_SKILLS = {"temporal-workflow-design-critic", "temporal:temporal-developer", "temporal-developer"}


class PersonaTests(unittest.TestCase):
    def test_invalid_yaml_in_an_agent_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "agent.md"
            path.write_text("---\nname: x\nskills: [a, b\n---\nbody\n", encoding="utf-8")
            with self.assertRaisesRegex(yamlio.YamlError, r"did not find expected ',' or '\]'"):
                frontmatter(path)

    def test_every_persona_has_frontmatter_name_description_model_skills(self):
        for stem in AGENTS:
            path = ROOT / "agents" / ("%s.md" % stem)
            self.assertTrue(path.is_file(), stem)
            fields = frontmatter(path)
            self.assertEqual(fields.get("name"), stem)
            self.assertTrue(fields.get("description"), stem)
            self.assertIn(fields.get("model"), {"opus", "sonnet"}, stem)
            self.assertIsInstance(fields.get("skills"), list, stem)
            self.assertTrue(fields["skills"], stem)

    def test_every_bound_skill_exists(self):
        for stem in AGENTS:
            for skill in frontmatter(ROOT / "agents" / ("%s.md" % stem))["skills"]:
                if skill in EXTERNAL_SKILLS:
                    continue
                self.assertTrue((ROOT / "skills" / skill / "SKILL.md").is_file(), skill)

    def test_every_reviewer_lens_cites_the_finding_schema(self):
        lenses = sorted(p for p in (ROOT / "skills").glob("lens-*/SKILL.md") if p.parent.name != "lens-shared" and p.parent.name not in NON_REVIEWER_LENSES)
        self.assertEqual(len(lenses), 4)
        for path in lenses:
            self.assertIn("../lens-shared/finding-schema.md", path.read_text(), path.parent.name)

    def test_the_finding_schema_names_each_key_class(self):
        text = (ROOT / "skills" / "lens-shared" / "finding-schema.md").read_text()
        for value in KEY_CLASSES:
            self.assertIn("`%s`" % value, text)

    def test_the_finding_schema_names_error_classes_and_personas(self):
        text = (ROOT / "skills" / "lens-shared" / "finding-schema.md").read_text()
        for value in ERROR_CLASSES:
            self.assertIn("`%s`" % value, text)
        self.assertIn("`personas`", text)

    def test_conformance_lens_names_every_verdict(self):
        text = (ROOT / "skills/lens-qa-conformance/SKILL.md").read_text()
        for verdict in ["covered", "code-only", "missing", "baseline", "env-only", "out-of-scope", "overridden"]:
            self.assertIn("`%s`" % verdict, text)
        self.assertIn("one hop", text)
        self.assertIn("`**Rules:**`", text)
        self.assertEqual(text.count("This verdict is blocking."), 2)
        self.assertIn("When more than one verdict fits", text)
        self.assertIn("git show <base>:<path>", text)
        self.assertIn("`## DDL`", text)
        self.assertIn("git grep <pattern> <base>", text)
        self.assertIn("git ls-tree -r <base>", text)
        self.assertIn("git grep <pattern> HEAD", text)
        self.assertIn("Never count both.", text)
        self.assertIn("`**Out of scope**` are not case labels.", text)
        for line in [
            "When more than one verdict fits, take the first in this order: `overridden`, `out-of-scope`, `env-only`, `baseline`, `covered`, `code-only`, `missing`.",
            "`covered`: the diff carries the code, and a test at HEAD asserts the rule.",
            "`code-only`: the diff carries the code, and no test at HEAD asserts the rule. This verdict is blocking.",
            "`missing`: HEAD carries no code for the rule, including base code the diff deleted or broke. This verdict is blocking.",
            "`baseline`: the base commit carries the rule, and the diff leaves that code unchanged at HEAD.",
            "`env-only`: HEAD carries the code, or the rule lives outside the repo, and only a deployed environment can show it.",
        ]:
            self.assertIn(line, text)

    def test_every_reviewer_tags_by_the_shared_tagging_rules(self):
        schema = (ROOT / "skills" / "lens-shared" / "finding-schema.md").read_text()
        self.assertIn("## Tagging rules", schema)
        lenses = sorted(p for p in (ROOT / "skills").glob("lens-*/SKILL.md") if p.parent.name != "lens-shared" and p.parent.name not in NON_REVIEWER_LENSES)
        for path in lenses + [ROOT / "agents" / "temporal-reviewer.md"]:
            text = path.read_text()
            self.assertIn("tagging rules", text, path.name)
            self.assertNotIn("Tag every choice", text, path.name)

    def test_each_agent_model_and_skills_match_the_table(self):
        for stem, (model, skills) in EXPECTED.items():
            fields = frontmatter(ROOT / "agents" / ("%s.md" % stem))
            self.assertEqual(fields["model"], model, stem)
            self.assertEqual(fields["skills"], skills, stem)

    def test_conformance_lens_names_locations_without_ambiguity(self):
        text = (ROOT / "skills/lens-qa-conformance/SKILL.md").read_text()
        self.assertIn("one or more `file:line` entries at HEAD, joined by `, `", text)
        self.assertIn("Give `test` as `<test file>::<test name>`", text)

    def test_temporal_code_reviewer_returns_code_findings(self):
        text = (ROOT / "agents/temporal-code-reviewer.md").read_text()
        for field in ["`side`", "`file`", "`line`", "`rule`", "`defect`", "`fix`", "`severity`"]:
            self.assertIn(field, text)
        self.assertNotIn("what the page must answer", text)
        for line in ["`blocking`", "`minor`", "Never edit code or pages.",
                     "Never install tools, start servers or run workflows.",
                     "git show <base>:<path>",
                     "The `side` is `head`, or `base` when the code that carried the rule no longer exists at HEAD.",
                     "The `file` is the path inside the reviewed repository on that side.",
                     "The `line` is the line number on that side."]:
            self.assertIn(line, text)

    def test_empty_anchor_rule_wins_over_key_decision_check(self):
        js = (ROOT / "skills/tl-design/workflows/design-persona-review.js").read_text()
        schema = (ROOT / "skills/lens-shared/finding-schema.md").read_text()
        self.assertIn("wins over the key-decision check", schema)
        self.assertIn("keep the first key_class other than none that a reviewer set", js)
        self.assertIn("keeps the first `key_class` other than `none`", schema)
        self.assertIn("A rule 2 finding with a key_class other than none is always blocking", js)
        self.assertIn("rules 1 and 2 do not cover", js)
        self.assertIn("It is `blocking` when its `key_class` is not `none`", schema)

    def test_only_the_key_decision_check_sets_key_decision_unasked(self):
        js = (ROOT / "skills/tl-design/workflows/design-persona-review.js").read_text()
        schema = (ROOT / "skills/lens-shared/finding-schema.md").read_text()
        line = [l for l in js.splitlines() if "Every other finding" in l][0]
        self.assertNotIn("key_decision_unasked", line)
        self.assertTrue(line.endswith("Rule 4 may change it afterwards.',"))
        self.assertIn("Only rule 4 sets key_decision_unasked.", js)
        self.assertIn("pick the error_class that fits from missing_detail, voice_structure, length_focus or other", js)
        self.assertIn("It marks the finding `key_decision_unasked` and `blocking` when the Agent decisions section has no row for its `page` and `anchor`.", schema)
        self.assertIn("The key-decision check applies to a finding whose `key_class` is not `none`.", schema)
        self.assertIn("It skips findings that the outside-owner rule or the empty or off-page anchor rule covers.", schema)
        self.assertIn("Only the key-decision check sets `key_decision_unasked`.", schema)


if __name__ == "__main__":
    unittest.main()
