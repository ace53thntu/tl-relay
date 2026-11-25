import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "tl-design" / "workflows" / "design-persona-review.js"
HARNESS = Path(__file__).resolve().parent / "workflow_harness.mjs"


@unittest.skipUnless(shutil.which("node"), "node not on PATH")
class WorkflowAgentsTest(unittest.TestCase):
    def run_harness(self, agents, temporal=False, workspace=None):
        with tempfile.TemporaryDirectory() as knowledge:
            args = {
                "handle": "demo",
                "knowledge": knowledge,
                "stage": "hla",
                "round": 1,
                "pages": ["/tmp/x.md"],
                "ledger": os.path.join(knowledge, "ledger.md"),
            }
            if temporal:
                args["temporal"] = True
            if workspace is not None:
                args["workspace"] = workspace
            if agents is not None:
                args["agents"] = agents
            return subprocess.run(
                ["node", str(HARNESS), str(SCRIPT), json.dumps(args)],
                capture_output=True,
                text=True,
            )

    def calls(self, agents, temporal=False, workspace=None):
        done = self.run_harness(agents, temporal, workspace)
        self.assertEqual(done.returncode, 0, done.stderr)
        return [json.loads(line) for line in done.stdout.splitlines()]

    def test_plugin_prefixes_agent_names(self):
        types = [c["opts"].get("agentType") for c in self.calls("plugin")]
        self.assertIn("tl-relay:solution-architect", types)
        self.assertNotIn("solution-architect", types)

    def test_bare_is_the_default(self):
        types = [c["opts"].get("agentType") for c in self.calls(None)]
        self.assertIn("solution-architect", types)
        self.assertEqual(types, [c["opts"].get("agentType") for c in self.calls("bare")])

    def test_none_names_the_lens_and_model(self):
        calls = self.calls("none")
        sa = next(c for c in calls if 'persona "sa"' in c["prompt"])
        self.assertNotIn("agentType", sa["opts"])
        self.assertEqual(sa["opts"]["model"], "opus")
        self.assertTrue(sa["prompt"].startswith("Load the skill lens-solution-architect"))
        self.assertIn("You review the named pages as the solution architect", sa["prompt"])
        se = next(c for c in calls if 'persona "se"' in c["prompt"])
        self.assertEqual(se["opts"]["model"], "sonnet")

    def test_merge_call_is_unchanged_in_every_mode(self):
        for mode in ("plugin", "bare", "none"):
            merge = self.calls(mode)[-1]
            self.assertEqual(merge["opts"]["model"], "opus")
            self.assertNotIn("agentType", merge["opts"])

    def test_roles_match_agent_files(self):
        prompts = {}
        for c in self.calls("none", temporal=True, workspace="/ws"):
            prompts[c["opts"].get("label")] = c["prompt"]
        names = {"sa": "solution-architect", "se": "software-engineer", "qa": "qa-engineer",
                 "security": "security-engineer", "temporal": "temporal-reviewer"}
        for pid, name in names.items():
            text = (ROOT / "agents" / f"{name}.md").read_text()
            body = text.split("\n---\n", 1)[1].strip()
            self.assertIn("\n" + body + "\n", prompts[f"review {pid}"], pid)

    def test_temporal_prompt_names_the_workspace_root(self):
        calls = self.calls("bare", temporal=True, workspace="/ws")
        prompt = next(c["prompt"] for c in calls if 'persona "temporal"' in c["prompt"])
        self.assertIn("under the workspace root /ws", prompt)

    def test_temporal_without_workspace_throws(self):
        done = self.run_harness("bare", temporal=True)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("missing args: workspace", done.stderr)

    def test_unknown_mode_throws(self):
        done = self.run_harness("x")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("unknown agents mode x", done.stderr)
