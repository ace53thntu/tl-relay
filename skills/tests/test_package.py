import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class PackageTest(unittest.TestCase):
    def test_plugin_manifest(self):
        m = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        self.assertEqual((m["name"], m["version"], m["license"]), ("tl-relay", "0.3.8", "MIT"))

    def test_marketplace_version_matches_the_plugin(self):
        plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
        market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual([p.get("version") for p in market["plugins"]], [plugin["version"]])

    def bundles(self):
        section = (ROOT / "README.md").read_text().split("### Bundles", 1)[1].split("\n### ", 1)[0]
        rows = {m.group(1): set(re.findall(r"`([a-z-]+)`", m.group(2)))
                for m in re.finditer(r"^\| (\w+) \| (`.*) \|$", section, re.M)}
        commands = [set(re.findall(r"--skill ([a-z-]+)", block))
                    for block in re.findall(r"```sh\n(.*?)```", section, re.S)]
        return rows, commands

    def test_each_readme_bundle_has_a_matching_install_command(self):
        rows, commands = self.bundles()
        self.assertEqual(set(rows), {"Design", "Build"})
        for name, skills in rows.items():
            self.assertIn(skills, commands, name)

    def test_build_bundle_carries_the_run_plan_sub_skills(self):
        rows, _ = self.bundles()
        required = re.findall(r"the `([a-z-]+)` skill\. \*\*REQUIRED SUB-SKILL", (ROOT / "skills/run-plan/SKILL.md").read_text())
        self.assertTrue(required)
        self.assertLessEqual(set(required), rows["Build"])

    def test_each_bundle_carries_the_skills_its_members_read_code_through(self):
        rows, _ = self.bundles()
        for name, skills in rows.items():
            for member in skills:
                text = (ROOT / "skills" / member / "SKILL.md").read_text()
                needed = set(re.findall(r"[Rr]ead the code through `([a-z-]+)`", text))
                self.assertLessEqual(needed, skills, "%s bundle, %s" % (name, member))

    def test_readme_says_npx_installs_the_main_branch_and_how_to_pin(self):
        text = (ROOT / "README.md").read_text()
        self.assertIn("installs the skills from the `main` branch", text)
        self.assertIn("npx skills add ace53thntu/tl-relay@v", text)

    def test_readme_says_npx_without_agent_also_writes_claude_skills(self):
        self.assertIn("`.claude/skills/`", (ROOT / "README.md").read_text())

    def test_readme_requirements_name_the_supported_systems(self):
        section = (ROOT / "README.md").read_text().split("### Requirements", 1)[1].split("\n### ", 1)[0]
        self.assertIn("- macOS or Linux.", section)

    def test_readme_allows_the_plugin_cache(self):
        section = (ROOT / "README.md").read_text().split("### Claude Code plugin", 1)[1].split("\n### ", 1)[0]
        for needle in ('"additionalDirectories": ["~/.claude/plugins/cache/tl-relay"]',
                       '"Bash(python3 /*/.claude/plugins/cache/tl-relay/*)"',
                       '"Bash(python3 \\"/*/.claude/plugins/cache/tl-relay/*)"',
                       '"Bash(sh /*/.claude/plugins/cache/tl-relay/*)"',
                       '"Bash(/*/.claude/plugins/cache/tl-relay/*/.venv/bin/python /*/.claude/plugins/cache/tl-relay/*)"',
                       '"Bash(\\"/*/.claude/plugins/cache/tl-relay/*/.venv/bin/python\\" \\"/*/.claude/plugins/cache/tl-relay/*)"'):
            self.assertIn(needle, section)
        self.assertNotIn("Bash(python3 */", section)
        self.assertNotIn("Bash(sh */", section)

    def test_marketplace_points_at_the_root(self):
        m = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(m["name"], "tl-relay")
        self.assertEqual([(p["name"], p["source"]) for p in m["plugins"]], [("tl-relay", "./")])

    def test_hook_uses_plugin_root(self):
        cmd = json.dumps(json.loads((ROOT / "hooks/hooks.json").read_text()))
        self.assertIn("SessionStart", cmd)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/session-start-skills.sh", cmd)

    @unittest.skipUnless(os.access("/usr/bin/jq", os.X_OK) or shutil.which("jq"), "jq missing")
    def test_hook_prints_using_tl_relay_from_plugin_root(self):
        env = {k: v for k, v in os.environ.items() if k != "TL_RELAY_BOOTSTRAP_SKILL"}
        env["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
        out = subprocess.run(["sh", str(ROOT / "hooks/session-start-skills.sh")], input=b"{}", env=env,
                             stdout=subprocess.PIPE, check=True).stdout.decode()
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("name: using-tl-relay", context)

    def test_config_example_lists_every_key(self):
        text = (ROOT / "config.example.yaml").read_text()
        for key in ("knowledge_dir", "state_dir", "worktree_dir", "operator_language", "publish:", "command", "confirm_flag", "keep",
                    "tracker:", "comment", "vale:", "vocab", "{dir}", "{target}", "{body_file}"):
            self.assertIn(key, text)

    def test_public_tree_is_free_of_home_couplings(self):
        skip = {"__pycache__", ".venv", "tests"}
        suffixes = (".md", ".py", ".sh", ".js", ".json", ".yaml", ".yml")
        for top in ("skills", "agents", "hooks", "README.md", "config.example.yaml", ".claude-plugin"):
            for path in [ROOT / top] if (ROOT / top).is_file() else (ROOT / top).rglob("*"):
                rel = path.relative_to(ROOT).parts
                if not path.is_file() or skip & set(rel):
                    continue
                in_scripts = rel[0] == "skills" and "scripts" in rel
                if path.suffix not in suffixes and not (in_scripts and path.suffix == ""):
                    continue
                try:
                    text = path.read_text()
                except UnicodeDecodeError:
                    continue
                for needle in ("AI_SDLC_HOME", "ai-sdlc.yaml", "~/.claude/skills", ".ai-sdlc/", "ai-sdlc"):
                    self.assertNotIn(needle, text, "%s: %s" % (path, needle))

    def test_gitignore_covers_state(self):
        text = (ROOT / ".gitignore").read_text()
        self.assertIn(".tl-relay/sdd/", text)
        self.assertIn(".tl-relay/designs/", text)

    def test_ci_runs_every_suite_with_a_stub_claude(self):
        text = (ROOT / ".github/workflows/test.yml").read_text()
        for needle in ("skills/tests", "maintainer/runtime/tests", "maintainer/hooks/tests/run.sh",
                       "maintainer/ci/stub-claude", "pull_request", "push", "skills/$s/scripts",
                       "maintainer/skills/retro/scripts", "skills/technical-writing/vale/test.sh"):
            self.assertIn(needle, text)
        blocks = re.findall(r"^( *)env:\n((?:\1 +.*\n)+)", text, re.M)
        for _, body in blocks:
            self.assertNotIn("runner.", body)
        self.assertIn("if: ${{ !cancelled() }}\n        run: |\n          mkdir -p \"$RUNNER_TEMP/bin\"\n          cp maintainer/ci/stub-claude", text)
        self.assertIn('-z "${CLAUDE_STUB_LOG:-}"', text)


if __name__ == "__main__":
    unittest.main()
