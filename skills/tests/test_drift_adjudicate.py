import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "ingest-sources" / "workflows" / "drift-adjudicate.js"
HARNESS = Path(__file__).resolve().parent / "workflow_harness.mjs"
DIGEST = "ab" * 32


@unittest.skipUnless(shutil.which("node"), "node not on PATH")
class DriftAdjudicateTest(unittest.TestCase):
    def run_harness(self, digest=DIGEST):
        args = {
            "kind": "stories",
            "ws": "/w",
            "oldSource": "/w/old.md",
            "newSource": "/w/new.md",
            "slices": [
                {"name": "s1", "new_ids": ["A-1"], "rule_on": []},
                {"name": "s2", "new_ids": ["B-1"], "rule_on": ["B-0"]},
            ],
        }
        if digest is not None:
            args["digest"] = digest
        return subprocess.run(
            ["node", str(HARNESS), str(SCRIPT), json.dumps(args)],
            capture_output=True,
            text=True,
        )

    def prompts(self, done):
        found = []
        for line in done.stdout.splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict) and "prompt" in obj:
                found.append(obj["prompt"])
        return found

    def test_each_reader_prompt_carries_the_stamp(self):
        prompts = self.prompts(self.run_harness())
        self.assertEqual(len(prompts), 2)
        for p in prompts:
            step3 = next(l for l in p.splitlines() if l.startswith("Step 3."))
            step4 = next(l for l in p.splitlines() if l.startswith("Step 4."))
            self.assertIn("whose first line is <!-- drift inputs sha256 " + DIGEST + " -->", step3)
            self.assertIn("whose first line is the same stamp", step4)

    def test_missing_digest_stops_the_run(self):
        done = self.run_harness(digest=None)
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("digest", done.stderr)
        self.assertEqual(self.prompts(done), [])


if __name__ == "__main__":
    unittest.main()
