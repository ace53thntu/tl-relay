from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REAL_REPO = HERE.parent.parent
SCRIPTS = REAL_REPO / "maintainer" / "skills" / "write-skill" / "scripts"
sys.path.insert(0, str(SCRIPTS))

STUB = """#!/usr/bin/python3
import json, os, sys
plan = json.load(open(os.environ["TL_RELAY_STUB_PLAN"]))
prompt = sys.argv[2]
entry = {"prompt": prompt, "cwd": os.getcwd(), "pid": os.getpid(), "ppid": os.getppid(),
         "bootstrap": os.environ.get("TL_RELAY_BOOTSTRAP_SKILL")}
log_path = os.environ["TL_RELAY_STUB_LOG"]
seen = 0
if os.path.exists(log_path):
    seen = sum(1 for line in open(log_path) if json.loads(line)["prompt"] == prompt)
with open(log_path, "a") as log:
    log.write(json.dumps(entry) + "\\n")
action = plan.get(prompt, "result")
if isinstance(action, list):
    action = action[min(seen, len(action) - 1)]
if action == "error":
    print(json.dumps({"type": "result", "is_error": True}))
    sys.exit(0)
if action == "sleep":
    import time
    time.sleep(300)
if action != "result":
    block = {"type": "tool_use", "name": "Skill", "input": {"skill": action}}
    print(json.dumps({"type": "assistant", "message": {"content": [block]}}))
print(json.dumps({"type": "result", "is_error": False}))
"""

SKILL = "---\nname: %s\ndescription: Use when %s.\n---\n\nBody of %s.\n"
LOCAL_ENV = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_CONFIG GIT_CONFIG_PARAMETERS GIT_CONFIG_COUNT "
    "GIT_OBJECT_DIRECTORY GIT_DIR GIT_WORK_TREE GIT_IMPLICIT_WORK_TREE GIT_GRAFT_FILE "
    "GIT_INDEX_FILE GIT_NO_REPLACE_OBJECTS GIT_REPLACE_REF_BASE GIT_PREFIX "
    "GIT_SHALLOW_FILE GIT_COMMON_DIR"
).split()


class Sandbox:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="final-run.")
        root = pathlib.Path(self._tmp.name).resolve()
        self.repo = root / "repo"
        self.home = root / "home"
        self.skills_dir = self.home / ".claude" / "skills"
        self.remote = root / "remote.git"
        self.plan_file = root / "plan.json"
        self.log_file = root / "agent.log"
        self.skills_dir.mkdir(parents=True)
        stub = root / "stub-agent"
        stub.write_text(STUB)
        stub.chmod(0o755)
        temp = root / "tmp"
        temp.mkdir()
        self.env = {k: v for k, v in os.environ.items() if k not in LOCAL_ENV and k != "CLAUDE_CONFIG_DIR"
                    and not k.startswith(("AI_SDLC_", "TL_RELAY_"))}
        self.env.update(
            HOME=str(self.home),
            TMPDIR=str(temp),
            PYTHONDONTWRITEBYTECODE="1",
            TL_RELAY_HOME=str(self.home / "tl-relay-home"),
            TL_RELAY_TRIGGER_AGENT=str(stub),
            TL_RELAY_REPO=str(REAL_REPO),
            TL_RELAY_STUB_PLAN=str(self.plan_file),
            TL_RELAY_STUB_LOG=str(self.log_file),
        )
        ai_home = pathlib.Path(self.env["TL_RELAY_HOME"])
        ai_home.mkdir()
        (ai_home / "tl-relay.yaml").write_text("neutrality:\n  patterns: []\n")
        self.agent_plan({})
        self._build()

    def cleanup(self):
        self._tmp.cleanup()

    def _git(self, *args, cwd=None):
        return subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args],
            cwd=str(cwd or self.repo), env=self.env, check=True, capture_output=True, text=True,
        )

    def _write(self, path, text):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def _build(self):
        self.repo.mkdir()
        self._git("init", "-q", "-b", "main")
        shutil.copytree(
            HERE, self.repo / "skills" / "tests",
            ignore=shutil.ignore_patterns("prompts", "__pycache__"),
        )
        shutil.copytree(
            SCRIPTS, self.repo / "maintainer" / "skills" / "write-skill" / "scripts", ignore=shutil.ignore_patterns("__pycache__"),
        )
        shutil.copytree(
            REAL_REPO / "maintainer" / "runtime", self.repo / "maintainer" / "runtime", ignore=shutil.ignore_patterns("tests", "__pycache__"),
        )
        shutil.copy(REAL_REPO / "maintainer" / "sdlc.py", self.repo / "maintainer" / "sdlc.py")
        self._write("maintainer/hooks/git-pre-push", (REAL_REPO / "maintainer" / "hooks" / "git-pre-push").read_text())
        for name in ("alpha", "beta", "using-tl-relay"):
            self._write("skills/%s/SKILL.md" % name, SKILL % (name, name + " applies", name))
        self._write("skills/tests/prompts/alpha-explicit.txt", "expect: alpha\nRun the alpha skill.\n")
        self._write("hooks/session-start-skills.sh", "#!/bin/sh\nexit 0\n")
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "seed")
        self._git("init", "-q", "--bare", "-b", "main", str(self.remote), cwd=self.home)
        self._git("remote", "add", "origin", str(self.remote))
        self._git("push", "-q", "-u", "origin", "main")

    def install_hook(self, home=None):
        code = (
            "import sys; sys.path.insert(0, sys.argv[1] + '/maintainer'); from runtime import install; "
            "install.apply([install.git_hook_change(sys.argv[1], sys.argv[2])])"
        )
        subprocess.run(
            ["/usr/bin/python3", "-c", code, str(self.repo), str(home or self.env["TL_RELAY_HOME"])],
            cwd=str(self.repo), env=self.env, check=True, capture_output=True, text=True,
        )

    def push(self, *args, cwd=None, env=None):
        return subprocess.run(
            ["git", *args], cwd=str(cwd or self.repo), env=env or self.env, capture_output=True, text=True,
        )

    def commit(self, path, text):
        self._write(path, text)
        self._git("add", "-A")
        self._git("commit", "-q", "-m", "edit " + path)
        return self._git("rev-parse", "HEAD").stdout.strip()

    def branch(self, name):
        self._git("checkout", "-q", "-b", name)

    def _command(self, argv):
        return ["/usr/bin/python3", str(SCRIPTS / "final_run.py"), "--repo", str(self.repo), *argv]

    def run(self, *argv, env=None):
        return subprocess.run(
            self._command(argv), cwd=str(self.repo), env=env or self.env, capture_output=True, text=True,
        )

    def popen(self, *argv):
        self.out_file = self.log_file.with_name("score.out")
        self.err_file = self.log_file.with_name("score.err")
        with open(self.out_file, "w") as out, open(self.err_file, "w") as err:
            return subprocess.Popen(
                self._command(argv), cwd=str(self.repo), env=self.env, stdout=out, stderr=err
            )

    def agent_plan(self, mapping):
        self.plan_file.write_text(json.dumps(mapping))

    def agent_calls(self):
        if not self.log_file.exists():
            return []
        return [json.loads(line) for line in self.log_file.read_text().splitlines()]
