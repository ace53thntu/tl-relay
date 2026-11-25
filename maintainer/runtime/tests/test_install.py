import contextlib
import io
import json
import os
import pathlib
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock

import fixture
import sdlc
from runtime import config, install

REPO = pathlib.Path(__file__).resolve().parents[3]


def pinned(env):
    kept = {k: v for k, v in os.environ.items() if not k.startswith("TL_RELAY_")}
    return dict(kept, **env)


def make(tmp, dirs=("claude-a",), root="work"):
    tmp = pathlib.Path(tmp)
    home = tmp / "home"
    home.mkdir(exist_ok=True)
    (tmp / root).mkdir(exist_ok=True)
    listing = ", ".join('"%s"' % (tmp / d) for d in dirs)
    (home / "tl-relay.yaml").write_text(
        "apiVersion: tl-relay/v1\nkind: Config\nproject:\n  name: t\n  root: %s\ninstall:\n  claude_config_dirs: [%s]\n" % (tmp / root, listing))
    return home


def run_cli(home, *argv):
    out, err = io.StringIO(), io.StringIO()
    env = {"TL_RELAY_HOME": str(home), "TL_RELAY_REPO": str(REPO)}
    with unittest.mock.patch.dict(os.environ, pinned(env), clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = sdlc.main(["install"] + list(argv))
    return code, out.getvalue(), err.getvalue()


def run_cli_decoy(decoy, *argv):
    out, err = io.StringIO(), io.StringIO()
    env = {"TL_RELAY_HOME": str(decoy), "TL_RELAY_REPO": str(REPO)}
    with unittest.mock.patch.dict(os.environ, pinned(env), clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = sdlc.main(["install"] + list(argv))
    return code, out.getvalue(), err.getvalue()


class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_closed_stdout_stops_install_with_nothing_written(self):
        class Closed(io.StringIO):
            def write(self, text):
                raise BrokenPipeError(32, "Broken pipe")
        for argv in ((), ("--dry-run",)):
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as other:
                home = make(other)
                err = io.StringIO()
                env = {"TL_RELAY_HOME": str(home), "TL_RELAY_REPO": str(REPO)}
                with unittest.mock.patch.dict(os.environ, pinned(env), clear=True), contextlib.redirect_stdout(Closed()), \
                        contextlib.redirect_stderr(err):
                    code = sdlc.main(["install"] + list(argv))
                self.assertEqual(code, 1)
                self.assertIn("output closed before install wrote anything; nothing changed", err.getvalue())
                self.assertFalse((home / "env.sh").exists())
                self.assertFalse((home / "hooks").exists())
                self.assertFalse((pathlib.Path(other) / "claude-a" / "settings.json").exists())

    def test_install_into_a_closed_pipe_prints_no_traceback(self):
        home = make(self.tmp.name)
        read, write = os.pipe()
        os.close(read)
        env = pinned({"TL_RELAY_HOME": str(home), "TL_RELAY_REPO": str(REPO)})
        try:
            done = subprocess.run([sys.executable, str(REPO / "maintainer" / "sdlc.py"), "install"],
                                  stdout=write, stderr=subprocess.PIPE, env=env)
        finally:
            os.close(write)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertNotIn(b"Traceback", done.stderr)
        self.assertNotIn(b"Exception ignored", done.stderr)
        self.assertFalse((home / "env.sh").exists())

    def test_render_fills_both_placeholders(self):
        self.assertEqual(install.render("{home}|{repo}/hooks/x", "/r", "/h"), "/h|/r/hooks/x")

    def test_render_leaves_placeholder_text_inside_values_alone(self):
        self.assertEqual(install.render("{home}|{repo}", "/r{home}", "/h{repo}"), "/h{repo}|/r{home}")

    def test_merge_replaces_old_entry_for_same_script(self):
        old = "/bin/sh '/old/home/hooks/block-env-dump.sh'"
        other = "/bin/sh '/elsewhere/mine.sh'"
        live = {"hooks": {"PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": old}, {"type": "command", "command": other}]}]}}
        new = "TL_RELAY_HOME='/h' /bin/sh '/r/hooks/block-env-dump.sh'"
        fragment = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": new}]}]}}
        commands = [h["command"] for g in install.merge_settings(live, fragment)["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertIn(new, commands)
        self.assertIn(other, commands)
        self.assertNotIn(old, commands)

    def test_install_drops_a_stale_task_hook_registration(self):
        home = make(self.tmp.name)
        stale = "TL_RELAY_HOME='/old' /bin/sh '/old/home/hooks/block-test-edit.sh'"
        path = self._settings(json.dumps({"hooks": {"PreToolUse": [
            {"matcher": "Edit|Write|NotebookEdit", "hooks": [{"type": "command", "command": stale}]}]}}))
        install.apply(install.plan(REPO, home))
        commands = [h["command"] for groups in json.loads(path.read_text())["hooks"].values() for g in groups for h in g["hooks"]]
        self.assertTrue(commands)
        for command in commands:
            self.assertNotIn("block-test-edit.sh", command)

    def test_merge_drops_a_retired_hook_under_another_event_and_the_emptied_event(self):
        stale = "/bin/sh '/old/home/hooks/validate-evidence.sh'"
        live = {"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": stale}]}]}}
        merged = install.merge_settings(live, {})
        self.assertNotIn("PostToolUse", merged["hooks"])

    def test_merge_keeps_a_user_hook_beside_a_retired_one(self):
        stale = "/bin/sh '/old/home/hooks/warn-out-of-scope.sh'"
        mine = {"type": "command", "command": "echo mine"}
        live = {"hooks": {"PostToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": stale}, mine]}]}}
        merged = install.merge_settings(live, {})
        self.assertEqual(merged["hooks"]["PostToolUse"], [{"matcher": "*", "hooks": [mine]}])

    def test_merge_leaves_a_hookless_group_under_another_event_untouched(self):
        live = {"hooks": {"Notification": [{"matcher": "*"}], "Stop": []}}
        merged = install.merge_settings(live, {})
        self.assertEqual(merged["hooks"], live["hooks"])

    def test_merge_keeps_a_look_alike_path(self):
        mine = {"type": "command", "command": "/bin/sh '/mine/block-test-edit.sh'"}
        live = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [mine]}]}}
        merged = install.merge_settings(live, {})
        self.assertEqual(merged["hooks"], live["hooks"])

    def test_home_flag_picks_the_home(self):
        home = make(self.tmp.name)
        decoy = pathlib.Path(self.tmp.name) / "decoy"
        decoy.mkdir()
        code, _, err = run_cli_decoy(decoy, "--home", str(home))
        self.assertEqual(code, 0, err)
        self.assertTrue((home / "env.sh").is_file())
        self.assertEqual(sorted(p.name for p in decoy.iterdir()), [])

    def test_install_writes_home_into_user_settings_env(self):
        home = make(self.tmp.name)
        tmp = pathlib.Path(self.tmp.name).resolve()
        (tmp / "claude-a").mkdir()
        (tmp / "claude-a" / "settings.json").write_text('{"env": {"KEEP": "1"}}')
        code, _, err = run_cli(home)
        self.assertEqual(code, 0, err)
        env = json.loads((tmp / "claude-a" / "settings.json").read_text())["env"]
        self.assertEqual(env, {"KEEP": "1", "TL_RELAY_HOME": str(home.resolve())})
        project = json.loads((tmp / "work" / ".claude" / "settings.json").read_text())
        self.assertNotIn("env", project)

    def test_relative_home_flag_writes_an_absolute_env_value(self):
        home = make(self.tmp.name)
        tmp = pathlib.Path(self.tmp.name).resolve()
        decoy = tmp / "decoy"
        decoy.mkdir()
        old = os.getcwd()
        os.chdir(tmp)
        self.addCleanup(os.chdir, old)
        code, _, err = run_cli_decoy(decoy, "--home", "home")
        self.assertEqual(code, 0, err)
        env = json.loads((tmp / "claude-a" / "settings.json").read_text())["env"]
        self.assertEqual(env["TL_RELAY_HOME"], str(home.resolve()))

    def _settings(self, text):
        tmp = pathlib.Path(self.tmp.name)
        (tmp / "claude-a").mkdir(exist_ok=True)
        path = tmp / "claude-a" / "settings.json"
        path.write_text(text)
        return path

    def test_differing_home_in_settings_without_flag_exits_1(self):
        home = make(self.tmp.name)
        path = self._settings('{"env": {"TL_RELAY_HOME": "/elsewhere"}}')
        code, _, err = run_cli(home)
        self.assertEqual(code, 1)
        self.assertIn(str(path), err)
        self.assertIn("/elsewhere", err)
        self.assertIn("--home", err)
        self.assertNotIn("Traceback", err)

    def test_the_hook_home_reads_tl_relay_home(self):
        text = "#!/bin/sh\nTL_RELAY_HOME=/h TL_RELAY_REPO=x exec /usr/bin/python3 s\n"
        self.assertEqual(install._hook_home(text), "/h")
        self.assertIsNone(install._hook_home(text.replace("TL_RELAY_", "AI_SDLC_")))

    def test_a_stray_old_home_key_is_left_alone(self):
        home = make(self.tmp.name)
        path = self._settings(json.dumps({"env": {"AI_SDLC_HOME": "/other", "KEEP": "1"}}))
        code, _, err = run_cli(home)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(path.read_text())["env"],
                         {"AI_SDLC_HOME": "/other", "KEEP": "1", "TL_RELAY_HOME": str(home.resolve())})

    def test_home_flag_replaces_a_differing_home(self):
        home = make(self.tmp.name)
        path = self._settings('{"env": {"TL_RELAY_HOME": "/elsewhere"}}')
        code, _, err = run_cli(home, "--home", str(home))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(path.read_text())["env"]["TL_RELAY_HOME"], str(home.resolve()))

    def test_same_home_spelled_differently_is_not_a_conflict(self):
        home = make(self.tmp.name)
        path = self._settings(json.dumps({"env": {"TL_RELAY_HOME": str(home) + "/"}}))
        code, _, err = run_cli(home)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(path.read_text())["env"]["TL_RELAY_HOME"], str(home.resolve()))

    def test_non_string_home_in_settings_exits_1(self):
        home = make(self.tmp.name)
        for value in (1, "", None, ["x"]):
            with self.subTest(value=value):
                path = self._settings(json.dumps({"env": {"TL_RELAY_HOME": value}}))
                code, _, err = run_cli(home)
                self.assertEqual(code, 1)
                self.assertIn(str(path), err)
                self.assertNotIn("Traceback", err)

    def test_home_flag_replaces_a_malformed_home(self):
        home = make(self.tmp.name)
        for value in (1, "", None, ["x"]):
            with self.subTest(value=value):
                path = self._settings(json.dumps({"env": {"TL_RELAY_HOME": value}}))
                code, _, err = run_cli(home, "--home", str(home))
                self.assertEqual(code, 0, err)
                self.assertEqual(json.loads(path.read_text())["env"]["TL_RELAY_HOME"], str(home.resolve()))

    def test_unresolvable_home_in_settings_exits_1(self):
        home = make(self.tmp.name)
        for value in ("~nosuchuser/x", "a\x00b"):
            with self.subTest(value=value):
                path = self._settings(json.dumps({"env": {"TL_RELAY_HOME": value}}))
                code, _, err = run_cli(home)
                self.assertEqual(code, 1)
                self.assertIn(str(path), err)
                self.assertNotIn("Traceback", err)

    def test_null_env_in_settings_is_treated_as_empty(self):
        home = make(self.tmp.name)
        path = self._settings('{"env": null}')
        code, _, err = run_cli(home)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(path.read_text())["env"], {"TL_RELAY_HOME": str(home.resolve())})

    def test_empty_home_flag_exits_1(self):
        make(self.tmp.name)
        tmp = pathlib.Path(self.tmp.name).resolve()
        decoy = tmp / "decoy"
        decoy.mkdir()
        code, _, err = run_cli_decoy(decoy, "--home", "")
        self.assertEqual(code, 1)
        self.assertIn("--home needs a path", err)
        self.assertFalse((tmp / "claude-a").exists())
        self.assertFalse((tmp / "work" / ".claude").exists())

    def test_dry_run_shows_the_env_write(self):
        home = make(self.tmp.name)
        decoy = pathlib.Path(self.tmp.name) / "decoy"
        decoy.mkdir()
        code, out, err = run_cli_decoy(decoy, "--dry-run", "--home", str(home))
        self.assertEqual(code, 0, err)
        self.assertIn('"TL_RELAY_HOME": ', out)

    def test_non_object_env_in_settings_exits_1(self):
        home = make(self.tmp.name)
        tmp = pathlib.Path(self.tmp.name).resolve()
        (tmp / "claude-a").mkdir()
        (tmp / "claude-a" / "settings.json").write_text('{"env": "x"}')
        code, _, err = run_cli(home)
        self.assertEqual(code, 1)
        self.assertIn("expected an object under env", err)
        self.assertIn("claude-a/settings.json", err)
        self.assertNotIn("Traceback", err)

    def test_second_install_changes_nothing(self):
        home = make(self.tmp.name)
        with unittest.mock.patch.dict(os.environ, pinned({"TL_RELAY_HOME": str(home), "TL_RELAY_REPO": str(REPO)}), clear=True):
            install.apply(install.plan(REPO, home))
            again = install.plan(REPO, home)
        self.assertEqual([p for p, old, new in again if old != new], [])

    def test_env_lists_every_config_dir(self):
        home = make(self.tmp.name, dirs=("a", "b"))
        text = install.env_text(config.load(REPO, home), REPO, home)
        tmp = pathlib.Path(self.tmp.name)
        self.assertIn("export TL_RELAY_USER_SETTINGS='%s:%s'" % (tmp / "a" / "settings.json", tmp / "b" / "settings.json"), text)
        for name in ("ROOT", "USER_FRAGMENT", "FRAGMENT", "SETTINGS"):
            self.assertIn("export TL_RELAY_%s=" % name, text)

    @unittest.skipUnless(fixture.CAN_SYMLINK, "cannot create symlinks")
    def test_env_writes_project_root_resolved(self):
        tmp = pathlib.Path(self.tmp.name).resolve()
        home = make(tmp)
        (tmp / "link").symlink_to(tmp / "work", target_is_directory=True)
        yaml = (home / "tl-relay.yaml").read_text()
        (home / "tl-relay.yaml").write_text(yaml.replace(str(tmp / "work"), str(tmp / "link")))
        text = install.env_text(config.load(REPO, home), REPO, home)
        self.assertIn("export TL_RELAY_ROOT='%s'\n" % (tmp / "work"), text)
        self.assertIn("export TL_RELAY_SETTINGS='%s'\n" % (tmp / "work" / ".claude" / "settings.json"), text)
        (home / "tl-relay.yaml").write_text(re.sub(r"root: .*", "root: ~/work", yaml))
        with unittest.mock.patch.dict(os.environ, pinned({"HOME": str(tmp)}), clear=True):
            text = install.env_text(config.load(REPO, home), REPO, home)
        self.assertIn("export TL_RELAY_ROOT='%s'\n" % (tmp / "work"), text)

    def test_dry_run_writes_nothing(self):
        home = make(self.tmp.name)
        code, out, _ = run_cli(home, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("settings.json", out)
        self.assertEqual(sorted(p.name for p in home.iterdir()), ["tl-relay.yaml"])
        self.assertFalse((pathlib.Path(self.tmp.name) / "claude-a").exists())

    def test_install_writes_every_file(self):
        home = make(self.tmp.name)
        code, _, _ = run_cli(home)
        tmp = pathlib.Path(self.tmp.name).resolve()
        self.assertEqual(code, 0)
        for path in (home / "hooks" / "settings-fragment.json", home / "hooks" / "user-fragment.json", home / "env.sh",
                     tmp / "claude-a" / "settings.json", tmp / "work" / ".claude" / "settings.json"):
            self.assertTrue(path.is_file(), path)
        self.assertNotIn("{home}", (home / "hooks" / "user-fragment.json").read_text())

    def test_missing_home_config_exits_1(self):
        home = pathlib.Path(self.tmp.name) / "empty"
        home.mkdir()
        code, _, err = run_cli(home)
        self.assertEqual(code, 1)
        self.assertIn("copy tl-relay.example.yaml to %s and set project.root" % (home.resolve() / "tl-relay.yaml"), err)

    def test_render_escapes_quotes_in_home_and_repo(self):
        home, repo = "/h'o\"me\\x", "/r\"e\\po"
        for name in install.FRAGMENTS:
            doc = json.loads(install.render((REPO / "maintainer" / "hooks" / name).read_text(), repo, home))
            for groups in doc["hooks"].values():
                for group in groups:
                    for hook in group["hooks"]:
                        words = shlex.split(hook["command"])
                        self.assertEqual(words[0], "TL_RELAY_HOME=" + home)
                        self.assertTrue(words[-1].startswith((repo + "/maintainer/hooks/", repo + "/hooks/")), words)

    def test_rerun_with_quotes_in_the_home_changes_nothing(self):
        base = pathlib.Path(self.tmp.name) / "it's \"q\""
        home = base / "home"
        home.mkdir(parents=True)
        (base / "work").mkdir()
        (home / "tl-relay.yaml").write_text(
            "apiVersion: tl-relay/v1\nkind: Config\nproject:\n  name: t\n  root: %s\ninstall:\n  claude_config_dirs: [%s]\n"
            % (json.dumps(str(base / "work")), json.dumps(str(base / "claude-a"))))
        with unittest.mock.patch.dict(os.environ, pinned({"TL_RELAY_HOME": str(home), "TL_RELAY_REPO": str(REPO)}), clear=True):
            install.apply(install.plan(REPO, home))
            again = install.plan(REPO, home)
        self.assertEqual([p for p, old, new in again if old != new], [])
        user = json.loads((base / "claude-a" / "settings.json").read_text())
        fragment = json.loads((home / "hooks" / "user-fragment.json").read_text())
        count = lambda doc: sum(len(g["hooks"]) for groups in doc["hooks"].values() for g in groups)
        self.assertEqual(count(user), count(fragment))

    def test_repo_path_with_a_single_quote_exits_1(self):
        home = make(self.tmp.name)
        repo = pathlib.Path(self.tmp.name) / "it's"
        repo.mkdir()
        with self.assertRaisesRegex(install.InstallError, "single quote"):
            install.plan(repo, home)
        self.assert_nothing_written(home)

    def test_newline_in_the_home_exits_1(self):
        for ch in ("\n", "\r"):
            with self.subTest(ch=repr(ch)):
                bad = pathlib.Path(self.tmp.name) / ("bad" + ch + "home")
                bad.mkdir()
                clean = make(self.tmp.name)
                code, _, err = run_cli(bad)
                self.assertEqual(code, 1)
                self.assertIn("must not contain a newline", err)
                self.assertNotIn("Traceback", err)
                self.assert_nothing_written(clean)
                self.assertFalse((bad / "hooks").exists())

    def test_newline_in_the_repo_exits_1(self):
        home = make(self.tmp.name)
        repo = pathlib.Path(self.tmp.name) / "bad\nrepo"
        repo.mkdir()
        with self.assertRaisesRegex(install.InstallError, "must not contain a newline"):
            install.plan(repo, home)
        self.assert_nothing_written(home)

    def test_newline_in_the_project_root_exits_1(self):
        home = make(self.tmp.name)
        bad = pathlib.Path(self.tmp.name) / "bad\nroot"
        bad.mkdir()
        (home / "tl-relay.yaml").write_text(
            "apiVersion: tl-relay/v1\nkind: Config\nproject:\n  name: t\n  root: %s\ninstall:\n  claude_config_dirs: [%s]\n"
            % (json.dumps(str(bad)), json.dumps(str(pathlib.Path(self.tmp.name) / "claude-a"))))
        code, _, err = run_cli(home)
        self.assertEqual(code, 1)
        self.assertIn("must not contain a newline", err)
        self.assertNotIn("Traceback", err)
        self.assert_nothing_written(home)

    def test_carriage_return_in_a_config_dir_exits_1(self):
        home = make(self.tmp.name)
        (home / "tl-relay.yaml").write_text(
            "apiVersion: tl-relay/v1\nkind: Config\nproject:\n  name: t\n  root: %s\ninstall:\n  claude_config_dirs: [%s]\n"
            % (json.dumps(str(pathlib.Path(self.tmp.name) / "work")), json.dumps(str(pathlib.Path(self.tmp.name) / "bad\rdir"))))
        code, _, err = run_cli(home)
        self.assertEqual(code, 1)
        self.assertIn("must not contain", err)
        self.assertNotIn("Traceback", err)
        self.assert_nothing_written(home)

    def test_rendered_command_keeps_one_trailing_quoted_path(self):
        for name in install.FRAGMENTS:
            doc = json.loads(install.render((REPO / "maintainer" / "hooks" / name).read_text(), "/r", "/h"))
            for groups in doc["hooks"].values():
                for group in groups:
                    for hook in group["hooks"]:
                        found = re.search(r"'([^']+)'$", hook["command"])
                        self.assertTrue(found, hook["command"])
                        self.assertRegex(found.group(1), r"^/r/(maintainer/)?hooks/[^/]+$")

    def seed(self, text, dirs=("claude-a",)):
        home = make(self.tmp.name, dirs=dirs)
        target = pathlib.Path(self.tmp.name) / dirs[0]
        target.mkdir(exist_ok=True)
        (target / "settings.json").write_text(text, encoding="utf-8")
        return home

    def test_dry_run_diff_prints_on_an_ascii_stdout(self):
        home = self.seed('{"note": "caf\\u00e9"}')
        raw = io.BytesIO()
        out = io.TextIOWrapper(raw, encoding="ascii")
        env = {"TL_RELAY_HOME": str(home), "TL_RELAY_REPO": str(REPO)}
        with unittest.mock.patch.dict(os.environ, pinned(env), clear=True), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            code = sdlc.main(["install", "--dry-run"])
        out.flush()
        self.assertEqual(code, 0)
        self.assertIn(b"caf\\xe9", raw.getvalue())

    def test_unusable_live_settings_exit_1_without_traceback(self):
        for text in ("[]", '{"hooks": null}'):
            with self.subTest(text=text):
                home = self.seed(text)
                code, _, err = run_cli(home)
                self.assertEqual(code, 1)
                self.assertTrue(err.startswith("error: "), err)

    def test_unreadable_target_refuses_before_any_write(self):
        for argv in (("--dry-run",), ()):
            with self.subTest(case="directory", argv=argv), tempfile.TemporaryDirectory() as other:
                home = make(other)
                target = pathlib.Path(other) / "claude-a" / "settings.json"
                target.mkdir(parents=True)
                code, _, err = run_cli(home, *argv)
                self.assertEqual(code, 1, err)
                self.assertIn(str(target), err)
                self.assertNotIn("Traceback", err)
                self.assertFalse((home / "env.sh").exists())
                self.assertFalse((home / "hooks").exists())
            with self.subTest(case="symlink loop", argv=argv), tempfile.TemporaryDirectory() as other:
                if not fixture.CAN_SYMLINK:
                    self.skipTest("cannot create symlinks")
                home = make(other)
                os.symlink(home / "env.sh", home / "env.sh")
                code, _, err = run_cli(home, *argv)
                self.assertEqual(code, 1, err)
                self.assertIn("env.sh", err)
                self.assertNotIn("Traceback", err)
                self.assertFalse((home / "hooks").exists())
                self.assertFalse((pathlib.Path(other) / "claude-a" / "settings.json").exists())

    def test_unreadable_settings_exit_1(self):
        home = make(self.tmp.name)
        (pathlib.Path(self.tmp.name) / "claude-a" / "settings.json").mkdir(parents=True)
        code, _, err = run_cli(home)
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("error: "), err)

    def test_unwritable_target_exit_1(self):
        home = make(self.tmp.name)
        (pathlib.Path(self.tmp.name) / "claude-a").write_text("a file, not a directory")
        code, _, err = run_cli(home)
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("error: "), err)

    def test_non_ascii_value_survives_unchanged(self):
        home = self.seed('{"note": "café ✓"}')
        code, _, _ = run_cli(home)
        self.assertEqual(code, 0)
        written = (pathlib.Path(self.tmp.name) / "claude-a" / "settings.json").read_text(encoding="utf-8")
        self.assertIn("café ✓", written)

    def test_non_list_config_dirs_exit_1(self):
        home = make(self.tmp.name)
        (home / "tl-relay.yaml").write_text((home / "tl-relay.yaml").read_text().split("install:")[0] + "install:\n  claude_config_dirs: /one/dir\n")
        code, _, err = run_cli(home)
        self.assertEqual(code, 1)
        self.assertIn("claude_config_dirs", err)

    def test_unusable_config_dir_entry_exits_1(self):
        old = os.getcwd()
        os.chdir(self.tmp.name)
        self.addCleanup(os.chdir, old)
        for entry in ("", "relative/dir", "/one:two", "/one\\ntwo"):
            with self.subTest(entry=entry):
                home = make(self.tmp.name)
                text = (home / "tl-relay.yaml").read_text()
                (home / "tl-relay.yaml").write_text(text.split("install:")[0] + 'install:\n  claude_config_dirs: ["%s"]\n' % entry)
                for argv in (("--dry-run",), ()):
                    code, _, err = run_cli(home, *argv)
                    self.assertEqual(code, 1, (entry, err))
                    self.assertIn("install.claude_config_dirs", err)
                    self.assertNotIn("Traceback", err)
                    self.assert_nothing_written(home)

    def test_falsy_non_list_config_dirs_exit_1(self):
        for value in ('""', "false", "0", "{}"):
            with self.subTest(value=value):
                home = make(self.tmp.name)
                text = (home / "tl-relay.yaml").read_text()
                (home / "tl-relay.yaml").write_text(text.split("install:")[0] + "install:\n  claude_config_dirs: %s\n" % value)
                with unittest.mock.patch.dict(os.environ, pinned({"HOME": self.tmp.name}), clear=True):
                    code, _, err = run_cli(home, "--dry-run")
                self.assertEqual(code, 1, (value, err))
                self.assertIn("install.claude_config_dirs must be a list of paths", err)

    def test_same_home_and_repo_exit_1(self):
        home = make(self.tmp.name)
        env = {"TL_RELAY_HOME": str(home), "TL_RELAY_REPO": str(home)}
        out, err = io.StringIO(), io.StringIO()
        with unittest.mock.patch.dict(os.environ, pinned(env), clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sdlc.main(["install"])
        self.assertEqual(code, 1)
        self.assertIn("overwrite", err.getvalue())

    def test_relative_home_renders_absolute_paths(self):
        home = make(self.tmp.name)
        with unittest.mock.patch.dict(os.environ, pinned({"HOME": self.tmp.name}), clear=True):
            cwd = os.getcwd()
            os.chdir(self.tmp.name)
            try:
                changes = install.plan(REPO, "home")
            finally:
                os.chdir(cwd)
        text = {p.name: new for p, old, new in changes}
        self.assertIn("TL_RELAY_HOME='%s'" % home.resolve(), text["user-fragment.json"])
        self.assertIn("export TL_RELAY_FRAGMENT='%s/hooks/settings-fragment.json'" % home.resolve(), text["env.sh"])

    def test_plan_expands_home_before_checking_config(self):
        home = make(self.tmp.name)
        (home.parent / "x").mkdir()
        (home / "tl-relay.yaml").rename(home.parent / "x" / "tl-relay.yaml")
        with unittest.mock.patch.dict(os.environ, pinned({"HOME": self.tmp.name}), clear=True):
            changes = install.plan(REPO, "~/x")
        self.assertTrue(changes)

    def test_non_list_event_in_live_settings_is_install_error(self):
        home = self.seed('{"hooks": {"PreToolUse": "x"}}')
        path = pathlib.Path(self.tmp.name) / "claude-a" / "settings.json"
        with self.assertRaises(install.InstallError) as ctx:
            install.plan(REPO, home)
        self.assertIn(str(path), str(ctx.exception))

    def test_non_utf8_settings_is_install_error(self):
        home = make(self.tmp.name)
        path = pathlib.Path(self.tmp.name) / "claude-a" / "settings.json"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\xff\xfe{")
        with self.assertRaises(install.InstallError) as ctx:
            install.plan(REPO, home)
        self.assertIn(str(path), str(ctx.exception))

    def test_missing_fragment_template_is_install_error(self):
        home = make(self.tmp.name)
        repo = pathlib.Path(self.tmp.name) / "repo"
        (repo / "maintainer" / "hooks").mkdir(parents=True)
        (repo / "maintainer" / "hooks" / "settings-fragment.json").write_text("{}")
        with self.assertRaises(install.InstallError) as ctx:
            install.plan(repo, home)
        self.assertIn(str(repo / "maintainer" / "hooks" / "user-fragment.json"), str(ctx.exception))

    def test_invalid_fragment_template_is_install_error(self):
        home = make(self.tmp.name)
        repo = pathlib.Path(self.tmp.name) / "repo"
        (repo / "maintainer" / "hooks").mkdir(parents=True)
        (repo / "maintainer" / "hooks" / "settings-fragment.json").write_text("{}")
        (repo / "maintainer" / "hooks" / "user-fragment.json").write_text("{")
        with self.assertRaises(install.InstallError) as ctx:
            install.plan(repo, home)
        self.assertIn(str(repo / "maintainer" / "hooks" / "user-fragment.json"), str(ctx.exception))

    def assert_nothing_written(self, home):
        tmp = pathlib.Path(self.tmp.name)
        self.assertFalse((home / "env.sh").exists())
        self.assertFalse((home / "hooks").exists())
        self.assertFalse((tmp / "claude-a").exists())
        self.assertFalse((tmp / "work" / ".claude").exists())

    def assert_clean_exit_1(self, home, argv):
        code, _, err = run_cli(home, *argv)
        self.assertEqual(code, 1)
        self.assertIn("error:", err)
        self.assertIn(str(home), err)
        self.assertNotIn("Traceback", err)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores directory modes")
    def test_unreadable_home_exits_1(self):
        locked = pathlib.Path(self.tmp.name) / "locked"
        locked.mkdir()
        self.addCleanup(os.chmod, locked, 0o700)
        os.chmod(locked, 0)
        home = locked / "x"
        for argv in ((), ("--dry-run",)):
            with self.subTest(argv=argv):
                self.assert_clean_exit_1(home, argv)
                self.assertFalse((pathlib.Path(self.tmp.name) / "claude-a").exists())

    def test_overlong_home_exits_1(self):
        home = pathlib.Path(self.tmp.name) / ("a" * 300)
        for argv in ((), ("--dry-run",)):
            with self.subTest(argv=argv):
                self.assert_clean_exit_1(home, argv)
                self.assertFalse((pathlib.Path(self.tmp.name) / "claude-a").exists())

    def test_unresolvable_home_env_exits_1(self):
        home = make(self.tmp.name)
        for argv in ((), ("--dry-run",)):
            with self.subTest(argv=argv):
                code, _, err = run_cli("~nosuchuser/x", *argv)
                self.assertEqual(code, 1)
                self.assertIn('home: "~nosuchuser/x" is not a usable path', err)
                self.assertNotIn("Traceback", err)
                self.assert_nothing_written(home)

    def test_unresolvable_home_flag_exits_1(self):
        home = make(self.tmp.name)
        code, _, err = run_cli(home, "--home", "~nosuchuser/x")
        self.assertEqual(code, 1)
        self.assertIn('home: "~nosuchuser/x" is not a usable path', err)
        self.assertNotIn("Traceback", err)
        self.assert_nothing_written(home)

    def test_unresolvable_repo_env_exits_1(self):
        home = make(self.tmp.name)
        out, err = io.StringIO(), io.StringIO()
        env = {"TL_RELAY_HOME": str(home), "TL_RELAY_REPO": "~nosuchuser/x"}
        with unittest.mock.patch.dict(os.environ, pinned(env), clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sdlc.main(["install"])
        self.assertEqual(code, 1)
        self.assertIn('repo: "~nosuchuser/x" is not a usable path', err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())
        self.assert_nothing_written(home)

    def test_non_string_project_root_exits_1(self):
        home = make(self.tmp.name)
        text = (home / "tl-relay.yaml").read_text()
        (home / "tl-relay.yaml").write_text(re.sub(r"root: .*", "root: 123", text))
        code, _, err = run_cli(home)
        self.assertEqual(code, 1)
        self.assertIn("project.root", err)
        self.assertNotIn("Traceback", err)
        self.assert_nothing_written(home)

    def test_nul_in_config_dirs_exits_1(self):
        home = make(self.tmp.name)
        text = (home / "tl-relay.yaml").read_text()
        (home / "tl-relay.yaml").write_text(text.split("install:")[0] + 'install:\n  claude_config_dirs: ["a\\0b"]\n')
        for argv in (("--dry-run",), ()):
            with self.subTest(argv=argv):
                code, _, err = run_cli(home, *argv)
                self.assertEqual(code, 1)
                self.assertIn("install.claude_config_dirs", err)
                self.assertNotIn("Traceback", err)
                self.assert_nothing_written(home)

    def _config(self, home, text):
        (home / "tl-relay.yaml").write_text("apiVersion: tl-relay/v1\nkind: Config\n" + text)

    def test_non_mapping_project_or_install_exits_1(self):
        tmp = pathlib.Path(self.tmp.name)
        cases = (
            ("project", "project: [a, b]\n"),
            ("install", "project:\n  name: t\n  root: %s\ninstall: one-dir\n" % (tmp / "work")),
            ("install", "project:\n  name: t\n  root: %s\ninstall: []\n" % (tmp / "work")),
        )
        for block, text in cases:
            with self.subTest(block=block):
                home = make(self.tmp.name)
                self._config(home, text)
                code, _, err = run_cli(home)
                self.assertEqual(code, 1)
                self.assertIn("%s must be a mapping" % block, err)
                self.assertNotIn("Traceback", err)
                self.assert_nothing_written(home)

    def test_empty_install_block_uses_the_default_config_dir(self):
        tmp = pathlib.Path(self.tmp.name).resolve()
        home = make(self.tmp.name)
        self._config(home, "project:\n  name: t\n  root: %s\ninstall:\n" % (tmp / "work"))
        with unittest.mock.patch.dict(os.environ, pinned({"HOME": str(tmp)}), clear=True):
            code, _, err = run_cli(home)
        self.assertEqual(code, 0, err)
        self.assertTrue((tmp / ".claude" / "settings.json").is_file())

    def _project(self, doc, name="settings.json"):
        path = pathlib.Path(self.tmp.name) / "work" / ".claude" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc))
        return path

    def test_differing_project_home_without_flag_exits_1(self):
        for value in ("/elsewhere", 123):
            with self.subTest(value=value):
                home = make(self.tmp.name)
                path = self._project({"env": {"TL_RELAY_HOME": value}})
                code, _, err = run_cli(home)
                self.assertEqual(code, 1)
                self.assertIn(str(path), err)
                self.assertIn(json.dumps(value), err)
                self.assertIn("--home", err)
                self.assertNotIn("Traceback", err)
                self.assertFalse((home / "env.sh").exists())

    def test_home_flag_removes_a_differing_project_home(self):
        home = make(self.tmp.name)
        path = self._project({"env": {"TL_RELAY_HOME": "/elsewhere", "KEEP": "1"}})
        code, _, err = run_cli(home, "--home", str(home))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(path.read_text())["env"], {"KEEP": "1"})

    def test_home_flag_drops_an_emptied_project_env(self):
        home = make(self.tmp.name)
        path = self._project({"env": {"TL_RELAY_HOME": "/elsewhere"}})
        code, _, err = run_cli(home, "--home", str(home))
        self.assertEqual(code, 0, err)
        self.assertNotIn("env", json.loads(path.read_text()))

    def test_same_project_home_is_left_alone(self):
        home = make(self.tmp.name)
        path = self._project({"env": {"TL_RELAY_HOME": str(home)}})
        code, _, err = run_cli(home)
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(path.read_text())["env"], {"TL_RELAY_HOME": str(home)})

    def test_differing_local_home_exits_1_even_with_flag(self):
        home = make(self.tmp.name)
        path = self._project({"env": {"TL_RELAY_HOME": "/elsewhere"}}, "settings.local.json")
        before = path.read_bytes()
        for argv in ((), ("--home", str(home)), ("--dry-run",)):
            with self.subTest(argv=argv):
                code, _, err = run_cli(home, *argv)
                self.assertEqual(code, 1)
                self.assertIn(str(path), err)
                self.assertIn("delete the key", err)
                self.assertNotIn("Traceback", err)
                self.assertEqual(path.read_bytes(), before)
                self.assertFalse((home / "env.sh").exists())

    def test_non_object_env_in_local_settings_exits_1(self):
        home = make(self.tmp.name)
        path = self._project({"env": "x"}, "settings.local.json")
        code, _, err = run_cli(home)
        self.assertEqual(code, 1)
        self.assertIn(str(path), err)
        self.assertIn("expected an object under env", err)
        self.assertNotIn("Traceback", err)

    def assert_fragment_hooks_in(self, home, commands):
        for name in install.FRAGMENTS:
            fragment = json.loads((home / "hooks" / name).read_text())
            for groups in fragment["hooks"].values():
                for g in groups:
                    for h in g["hooks"]:
                        self.assertIn(h["command"], commands)

    def _shared(self):
        tmp = pathlib.Path(self.tmp.name).resolve()
        home = tmp / "home"
        home.mkdir()
        (home / "tl-relay.yaml").write_text(
            "apiVersion: tl-relay/v1\nkind: Config\nproject:\n  name: t\n  root: %s\ninstall:\n  claude_config_dirs: [%s]\n"
            % (json.dumps(str(tmp)), json.dumps(str(tmp / ".claude"))))
        return home, tmp / ".claude" / "settings.json"

    def test_shared_settings_file_gets_one_change_with_both_fragments(self):
        home, shared = self._shared()
        changes = install.plan(REPO, home)
        self.assertEqual([p for p, _, _ in changes].count(shared), 1)
        install.apply(changes)
        doc = json.loads(shared.read_text())
        self.assertEqual(doc["env"]["TL_RELAY_HOME"], str(home))
        commands = [h["command"] for groups in doc["hooks"].values() for g in groups for h in g["hooks"]]
        self.assert_fragment_hooks_in(home, commands)
        self.assertEqual([p for p, old, new in install.plan(REPO, home) if old != new], [])

    @unittest.skipUnless(shutil.which("jq"), "jq is not installed")
    def test_shared_settings_file_passes_the_guardrail_comparison(self):
        home, shared = self._shared()
        install.apply(install.plan(REPO, home))
        for name in install.FRAGMENTS:
            out = subprocess.run(
                ["jq", "-n", "--slurpfile", "f", str(home / "hooks" / name), "--slurpfile", "l", str(shared),
                 "-r", "-f", str(REPO / "maintainer" / "hooks" / "compare.jq")],
                capture_output=True, text=True, check=True).stdout
            self.assertNotIn("MISSING", out, name)

    @unittest.skipUnless(fixture.CAN_SYMLINK, "cannot create symlinks")
    def test_symlink_loop_in_a_config_dir_is_a_refusal(self):
        tmp = pathlib.Path(self.tmp.name).resolve()
        home = make(tmp, dirs=("loop/.claude",))
        loop = tmp / "loop" / ".claude"
        loop.mkdir(parents=True)
        (loop / "settings.json").symlink_to(loop / "settings.json")
        code, _, err = run_cli(home, "--dry-run")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.assertIn("loop/.claude/settings.json", err)

    def test_hard_linked_settings_file_gets_one_change(self):
        tmp = pathlib.Path(self.tmp.name).resolve()
        home = tmp / "home"
        home.mkdir()
        (tmp / "Root" / ".claude").mkdir(parents=True)
        (tmp / "other" / ".claude").mkdir(parents=True)
        target = tmp / "Root" / ".claude" / "settings.json"
        target.write_text("{}")
        os.link(target, tmp / "other" / ".claude" / "settings.json")
        (home / "tl-relay.yaml").write_text(
            "apiVersion: tl-relay/v1\nkind: Config\nproject:\n  name: t\n  root: %s\ninstall:\n  claude_config_dirs: [%s]\n"
            % (json.dumps(str(tmp / "Root")), json.dumps(str(tmp / "other" / ".claude"))))
        changes = install.plan(REPO, home)
        self.assertEqual(len([p for p, _, _ in changes if p.name == "settings.json"]), 1)
        install.apply(changes)
        doc = json.loads(target.read_text())
        self.assertEqual(doc["env"]["TL_RELAY_HOME"], str(home))
        commands = [h["command"] for groups in doc["hooks"].values() for g in groups for h in g["hooks"]]
        self.assert_fragment_hooks_in(home, commands)

    def test_case_variant_alias_of_the_project_settings_gets_one_change(self):
        tmp = pathlib.Path(self.tmp.name).resolve()
        (tmp / "CaseProbe").mkdir()
        if not (tmp / "caseprobe").exists():
            self.skipTest("the temp filesystem is case-sensitive")
        home = tmp / "home"
        home.mkdir()
        (tmp / "Proj" / ".claude").mkdir(parents=True)
        (home / "tl-relay.yaml").write_text(
            "apiVersion: tl-relay/v1\nkind: Config\nproject:\n  name: t\n  root: %s\ninstall:\n  claude_config_dirs: [%s]\n"
            % (json.dumps(str(tmp / "Proj")), json.dumps(str(tmp / "proj" / ".claude"))))
        changes = install.plan(REPO, home)
        target = (tmp / "Proj" / ".claude" / "settings.json").resolve()
        same = [p for p, _, _ in changes if p.name == "settings.json" and p.parent.is_dir() and os.path.samefile(p.parent, target.parent)]
        self.assertEqual(len(same), 1)
        install.apply(changes)
        doc = json.loads(target.read_text())
        self.assertEqual(doc["env"]["TL_RELAY_HOME"], str(home))
        commands = [h["command"] for groups in doc["hooks"].values() for g in groups for h in g["hooks"]]
        self.assert_fragment_hooks_in(home, commands)


    def test_unencodable_change_refuses_before_anything_is_written(self):
        home = make(self.tmp.name)
        tmp = pathlib.Path(self.tmp.name)
        project = tmp / "work" / ".claude" / "settings.json"
        project.parent.mkdir(parents=True)
        project.write_text('{"x": "\\udce9"}')
        for argv in (("--dry-run",), ()):
            with self.subTest(argv=argv):
                code, _, err = run_cli(home, *argv)
                self.assertEqual(code, 1)
                self.assertIn(str(project), err)
                self.assertNotIn("Traceback", err)
                self.assertFalse((home / "env.sh").exists())
                self.assertFalse((home / "hooks").exists())
                self.assertFalse((tmp / "claude-a" / "settings.json").exists())

    def test_non_utf8_home_or_repo_is_install_error(self):
        home = make(self.tmp.name)
        bad = str(pathlib.Path(self.tmp.name) / "caf\udce9")
        for repo, target in ((REPO, bad), (bad, home)):
            with self.subTest(repo=repo, home=target):
                with self.assertRaisesRegex(install.InstallError, "is not valid UTF-8"):
                    install.plan(repo, target)
        self.assert_nothing_written(home)

    def test_non_utf8_home_flag_exits_1_with_nothing_written(self):
        home = make(self.tmp.name)
        bad = str(pathlib.Path(self.tmp.name) / "caf\udce9")
        code, _, err = run_cli(home, "--home", bad)
        self.assertEqual(code, 1)
        self.assertIn("is not valid UTF-8", err)
        self.assertNotIn("Traceback", err)
        self.assertFalse(os.path.lexists(bad))
        self.assert_nothing_written(home)

    def test_apply_leaves_a_file_untouched_on_an_encoding_error(self):
        path = pathlib.Path(self.tmp.name) / "out" / "settings.json"
        path.parent.mkdir()
        path.write_text('{"keep": 1}')
        with self.assertRaisesRegex(install.InstallError, re.escape(str(path))):
            install.apply([(path, '{"keep": 1}', "caf\udce9")])
        self.assertEqual(path.read_text(), '{"keep": 1}')

    def _failing(self, method, bad):
        real = getattr(pathlib.Path, method)
        def fake(path, *args, **kwargs):
            if path == bad:
                raise OSError(28, "No space left on device")
            return real(path, *args, **kwargs)
        return unittest.mock.patch.object(pathlib.Path, method, fake)

    def test_failed_write_restores_every_earlier_file(self):
        tmp = pathlib.Path(self.tmp.name)
        home = make(self.tmp.name)
        user = tmp / "claude-a" / "settings.json"
        user.parent.mkdir()
        user.write_bytes(b'{"keep": 1}\r\n')
        changes = install.plan(REPO, home)
        project = changes[-1][0]
        with self._failing("write_bytes", project):
            with self.assertRaisesRegex(install.InstallError, re.escape(str(project))):
                install.apply(changes)
        self.assertEqual(user.read_bytes(), b'{"keep": 1}\r\n')
        self.assertFalse((home / "env.sh").exists())
        self.assertFalse((home / "hooks").exists())
        self.assertFalse((tmp / "work" / ".claude").exists())

    def test_failed_restore_names_the_paths_left_changed(self):
        home = make(self.tmp.name)
        changes = install.plan(REPO, home)
        project = changes[-1][0]
        env_sh = next(path for path, _, _ in changes if path.name == "env.sh")
        with self._failing("write_bytes", project), self._failing("unlink", env_sh):
            with self.assertRaises(install.InstallError) as caught:
                install.apply(changes)
        self.assertIn("not restored", str(caught.exception))
        self.assertIn(str(env_sh), str(caught.exception))

    @unittest.skipUnless(fixture.CAN_SYMLINK, "cannot create symlinks")
    def test_symlinked_user_settings_stays_a_symlink(self):
        tmp = pathlib.Path(self.tmp.name)
        home = make(self.tmp.name)
        real = tmp / "dotfiles" / "settings.json"
        real.parent.mkdir()
        real.write_text("{}")
        (tmp / "claude-a").mkdir()
        (tmp / "claude-a" / "settings.json").symlink_to(real)
        install.apply(install.plan(REPO, home))
        self.assertTrue((tmp / "claude-a" / "settings.json").is_symlink())
        self.assertIn("hooks", json.loads(real.read_text()))

    def test_a_write_that_fails_part_way_restores_that_file(self):
        tmp = pathlib.Path(self.tmp.name)
        home = make(self.tmp.name)
        user = tmp / "claude-a" / "settings.json"
        user.parent.mkdir()
        user.write_bytes(b'{"keep": 1}\r\n')
        changes = install.plan(REPO, home)
        target = next(p for p, _, _ in changes if p.name == "settings.json" and p.parent.name == "claude-a")
        real = pathlib.Path.write_bytes
        def short(path, data):
            if path == target:
                real(path, data[:5])
                raise OSError(28, "No space left on device")
            return real(path, data)
        with unittest.mock.patch.object(pathlib.Path, "write_bytes", short):
            with self.assertRaises(install.InstallError):
                install.apply(changes)
        self.assertEqual(user.read_bytes(), b'{"keep": 1}\r\n')

    @unittest.skipUnless(fixture.CAN_SYMLINK, "cannot create symlinks")
    def test_failed_install_keeps_a_broken_symlink_as_a_symlink(self):
        tmp = pathlib.Path(self.tmp.name)
        home = make(self.tmp.name)
        link = tmp / "claude-a" / "settings.json"
        link.parent.mkdir()
        target = tmp / "dotfiles" / "settings.json"
        target.parent.mkdir()
        link.symlink_to(target)
        changes = install.plan(REPO, home)
        with self._failing("write_bytes", changes[-1][0]):
            with self.assertRaises(install.InstallError):
                install.apply(changes)
        self.assertTrue(link.is_symlink())
        self.assertFalse(target.exists())

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores file modes")
    def test_read_only_target_is_not_reported_as_not_restored(self):
        tmp = pathlib.Path(self.tmp.name)
        home = make(self.tmp.name)
        user = tmp / "claude-a" / "settings.json"
        user.parent.mkdir()
        user.write_bytes(b'{"keep": 1}')
        user.chmod(0o444)
        self.addCleanup(user.chmod, 0o644)
        changes = install.plan(REPO, home)
        target = next(p for p, _, _ in changes if p.name == "settings.json" and p.parent.name == "claude-a")
        with self.assertRaises(install.InstallError) as caught:
            install.apply(changes)
        self.assertIn(str(target), str(caught.exception))
        self.assertNotIn("not restored", str(caught.exception))
        self.assertEqual(user.read_bytes(), b'{"keep": 1}')
        self.assertFalse((home / "env.sh").exists())
        self.assertFalse((home / "hooks").exists())


    def _interrupting(self, bad, how):
        real = pathlib.Path.write_bytes
        def fake(path, data):
            if path == bad:
                how()
            return real(path, data)
        return unittest.mock.patch.object(pathlib.Path, "write_bytes", fake)

    def _raise_interrupt(self):
        raise KeyboardInterrupt

    def _send_sigterm(self):
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(1)

    def test_interrupt_during_apply_restores_and_exits_130(self):
        def unhandled(signum, frame):
            raise AssertionError("apply left SIGTERM unhandled")
        previous = signal.signal(signal.SIGTERM, unhandled)
        self.addCleanup(signal.signal, signal.SIGTERM, previous)
        for name, how in (("ctrl-c", self._raise_interrupt), ("sigterm", self._send_sigterm)):
            with self.subTest(case=name), tempfile.TemporaryDirectory() as other:
                home = make(other)
                user = pathlib.Path(other) / "claude-a" / "settings.json"
                user.parent.mkdir()
                user.write_bytes(b'{"keep": 1}\r\n')
                env = {"TL_RELAY_HOME": str(home), "TL_RELAY_REPO": str(REPO)}
                with unittest.mock.patch.dict(os.environ, pinned(env), clear=True):
                    project = install.plan(REPO, home)[-1][0]
                out, err = io.StringIO(), io.StringIO()
                try:
                    with unittest.mock.patch.dict(os.environ, pinned(env), clear=True), self._interrupting(project, how), \
                            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        code = sdlc.main(["install"])
                except KeyboardInterrupt:
                    self.fail("KeyboardInterrupt escaped sdlc.main")
                self.assertEqual(code, 130, err.getvalue())
                self.assertIn("interrupted: every file restored", err.getvalue())
                self.assertNotIn("Traceback", err.getvalue())
                self.assertEqual(user.read_bytes(), b'{"keep": 1}\r\n')
                self.assertFalse((home / "env.sh").exists())
                self.assertFalse((home / "hooks").exists())
                self.assertFalse((pathlib.Path(other) / "work" / ".claude").exists())
                self.assertIs(signal.getsignal(signal.SIGTERM), unhandled)

    def test_interrupt_during_plan_or_diff_exits_130_with_nothing_written(self):
        class Interrupting(io.StringIO):
            def write(self, text):
                raise KeyboardInterrupt
        for stage in ("plan", "diff"):
            for argv in ((), ("--dry-run",)):
                with self.subTest(stage=stage, argv=argv), tempfile.TemporaryDirectory() as other:
                    home = make(other)
                    out, err = (io.StringIO() if stage == "plan" else Interrupting()), io.StringIO()
                    env = {"TL_RELAY_HOME": str(home), "TL_RELAY_REPO": str(REPO)}
                    patched = (unittest.mock.patch.object(install, "plan", side_effect=KeyboardInterrupt)
                               if stage == "plan" else contextlib.nullcontext())
                    try:
                        with unittest.mock.patch.dict(os.environ, pinned(env), clear=True), patched, \
                                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                            code = sdlc.main(["install"] + list(argv))
                    except KeyboardInterrupt:
                        self.fail("KeyboardInterrupt escaped sdlc.main")
                    self.assertEqual(code, 130, err.getvalue())
                    self.assertIn("interrupted: nothing changed", err.getvalue())
                    self.assertNotIn("Traceback", err.getvalue())
                    self.assertFalse((home / "env.sh").exists())
                    self.assertFalse((home / "hooks").exists())
                    self.assertFalse((pathlib.Path(other) / "claude-a" / "settings.json").exists())
                    self.assertFalse((pathlib.Path(other) / "work" / ".claude").exists())

    def test_sigterm_during_the_undo_after_a_failed_write_is_ignored(self):
        def unhandled(signum, frame):
            raise AssertionError("apply left SIGTERM unhandled")
        previous = signal.signal(signal.SIGTERM, unhandled)
        self.addCleanup(signal.signal, signal.SIGTERM, previous)
        tmp = pathlib.Path(self.tmp.name)
        home = make(self.tmp.name)
        user = tmp / "claude-a" / "settings.json"
        user.parent.mkdir()
        user.write_bytes(b'{"keep": 1}\r\n')
        changes = install.plan(REPO, home)
        real_open = pathlib.Path.open
        sent = []
        def open_and_terminate(path, mode="r", *args, **kwargs):
            if mode == "wb" and path == user:
                sent.append(path)
                if len(sent) == 2:
                    self._send_sigterm()
            return real_open(path, mode, *args, **kwargs)
        with self._failing("write_bytes", changes[-1][0]), \
                unittest.mock.patch.object(pathlib.Path, "open", open_and_terminate):
            with self.assertRaises(install.InstallError):
                install.apply(changes)
        self.assertEqual(len(sent), 2)
        self.assertEqual(user.read_bytes(), b'{"keep": 1}\r\n')
        self.assertFalse((home / "env.sh").exists())
        self.assertFalse((home / "hooks").exists())
        self.assertIs(signal.getsignal(signal.SIGTERM), unhandled)

    def test_a_closed_stdout_is_refused_before_anything_is_written(self):
        home = make(self.tmp.name)
        env = pinned({"TL_RELAY_HOME": str(home), "TL_RELAY_REPO": str(REPO)})
        done = subprocess.run([sys.executable, str(REPO / "maintainer" / "sdlc.py"), "install"], env=env,
                              stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                              preexec_fn=lambda: os.close(1))
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("output closed", done.stderr)
        self.assertNotIn("Traceback", done.stderr)
        self.assertFalse((home / "env.sh").exists())

    def test_apply_puts_the_previous_sigterm_handler_back(self):
        previous = signal.getsignal(signal.SIGTERM)
        marker = lambda signum, frame: None
        signal.signal(signal.SIGTERM, marker)
        self.addCleanup(signal.signal, signal.SIGTERM, previous)
        home = make(self.tmp.name)
        install.apply(install.plan(REPO, home))
        self.assertIs(signal.getsignal(signal.SIGTERM), marker)



ISOLATED_GIT = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo, *args):
    env = dict({k: v for k, v in os.environ.items() if not k.startswith("GIT_")}, **ISOLATED_GIT)
    return subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.invalid", "-C", str(repo), *args],
                          env=env, check=True, capture_output=True, text=True).stdout.strip()


def make_clone(tmp, name="clone", init=True):
    clone = pathlib.Path(tmp).resolve() / name
    (clone / "maintainer" / "hooks").mkdir(parents=True)
    for template in ("settings-fragment.json", "user-fragment.json", "git-pre-push"):
        shutil.copy(REPO / "maintainer" / "hooks" / template, clone / "maintainer" / "hooks" / template)
    shutil.copy(REPO / "maintainer" / "tl-relay.yaml", clone / "maintainer" / "tl-relay.yaml")
    (clone / "maintainer" / "skills" / "write-skill" / "scripts").mkdir(parents=True)
    (clone / "maintainer" / "skills" / "write-skill" / "scripts" / "final_run.py").write_text("")
    (clone / "maintainer" / "sdlc.py").write_text("")
    if init:
        git(clone, "init", "-q", "-b", "main")
    return clone


def run_clone(clone, home, *argv):
    out, err = io.StringIO(), io.StringIO()
    env = pinned(dict({"TL_RELAY_HOME": str(home), "TL_RELAY_REPO": str(clone)}, **ISOLATED_GIT))
    with unittest.mock.patch.dict(os.environ, pinned(env), clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = sdlc.main(["install", "--home", str(home)] + list(argv))
    return code, out.getvalue(), err.getvalue()


class GitHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = make(self.tmp.name).resolve()
        self.clone = make_clone(self.tmp.name)
        self.hook = self.clone / ".git" / "hooks" / "pre-push"

    def untouched(self):
        self.assertFalse((self.home / "env.sh").exists())
        self.assertFalse((pathlib.Path(self.tmp.name) / "claude-a" / "settings.json").exists())

    def test_install_with_git_hook_writes_an_executable_hook(self):
        code, _, err = run_clone(self.clone, self.home, "--git-hook")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.hook.stat().st_mode & 0o777, 0o755)
        main = shlex.quote(str(self.clone))
        self.assertEqual(self.hook.read_text(), (
            "#!/bin/sh\n%s\nmain=%s\nscript=$main/maintainer/skills/write-skill/scripts/final_run.py\n"
            "if [ ! -f \"$script\" ]; then\n"
            "  echo \"tl-relay pre-push: $script is missing; check out a branch that has it in $main, "
            "rerun sdlc.py install --git-hook, or stop and ask the operator, who decides on --no-verify\" >&2\n"
            "  exit 1\n"
            "fi\n"
            "TL_RELAY_HOME=%s TL_RELAY_REPO=\"$main\" exec /usr/bin/python3 \"$script\" check \"$@\"\n"
            % (install.HOOK_MARKER, main, shlex.quote(str(self.home)))))

    def test_the_rendered_hook_uses_new_names(self):
        code, _, err = run_clone(self.clone, self.home, "--git-hook")
        self.assertEqual(code, 0, err)
        text = self.hook.read_text()
        self.assertIn("TL_RELAY_HOME=", text)
        self.assertIn("TL_RELAY_REPO=", text)
        self.assertNotIn("AI_SDLC_", text)

    def test_a_plain_install_writes_no_hook(self):
        code, _, err = run_clone(self.clone, self.home)
        self.assertEqual(code, 0, err)
        self.assertFalse(self.hook.exists())

    def test_the_real_clone_gets_no_hook_from_this_suite(self):
        common = pathlib.Path(git(REPO, "rev-parse", "--path-format=absolute", "--git-common-dir"))
        target = common / "hooks" / "pre-push"
        before = (target.exists(), target.stat().st_mtime_ns if target.exists() else None)
        code, _, err = run_cli(self.home)
        self.assertEqual(code, 0, err)
        self.assertEqual((target.exists(), target.stat().st_mtime_ns if target.exists() else None), before)

    def test_a_linked_worktree_renders_the_main_checkout(self):
        git(self.clone, "add", "-A")
        git(self.clone, "commit", "-q", "-m", "seed")
        linked = pathlib.Path(self.tmp.name).resolve() / "linked"
        git(self.clone, "worktree", "add", "-q", str(linked), "-b", "side")
        code, _, err = run_clone(linked, self.home, "--git-hook")
        self.assertEqual(code, 0, err)
        text = self.hook.read_text()
        self.assertIn("\nmain=%s\n" % shlex.quote(str(self.clone)), text)
        self.assertNotIn(str(linked), text)

    def test_a_foreign_hook_raises_and_changes_nothing(self):
        self.hook.write_text("#!/bin/sh\necho mine\n")
        code, out, err = run_clone(self.clone, self.home, "--git-hook")
        self.assertEqual(code, 1)
        self.assertIn("pre-push", err)
        self.assertEqual(self.hook.read_text(), "#!/bin/sh\necho mine\n")
        self.untouched()

    def test_a_set_hooks_path_raises_and_changes_nothing(self):
        git(self.clone, "config", "core.hooksPath", str(pathlib.Path(self.tmp.name) / "elsewhere"))
        code, out, err = run_clone(self.clone, self.home, "--git-hook")
        self.assertEqual(code, 1)
        self.assertIn("core.hooksPath", err)
        self.assertFalse(self.hook.exists())
        self.untouched()

    def test_dry_run_prints_the_diff_and_writes_nothing(self):
        code, out, err = run_clone(self.clone, self.home, "--git-hook", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn(install.HOOK_MARKER, out)
        self.assertIn("pre-push", out)
        self.assertFalse(self.hook.exists())
        self.untouched()

    def test_no_git_directory_skips_with_one_line(self):
        bare = make_clone(self.tmp.name, "nogit", init=False)
        self.assertIsNone(install.git_hook_change(bare, self.home))
        code, out, err = run_clone(bare, self.home, "--git-hook")
        self.assertEqual(code, 0, err)
        self.assertEqual(len([l for l in (out + err).splitlines() if "pre-push" in l]), 1)
        self.assertTrue((self.home / "env.sh").exists())

    def test_a_reinstall_restores_a_lost_execute_bit(self):
        run_clone(self.clone, self.home, "--git-hook")
        text = self.hook.read_text()
        self.hook.chmod(0o644)
        code, _, err = run_clone(self.clone, self.home, "--git-hook")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.hook.stat().st_mode & 0o777, 0o755)
        self.assertEqual(self.hook.read_text(), text)

    def test_undo_removes_a_new_hook_after_a_later_write_fails(self):
        change = install.git_hook_change(self.clone, self.home)
        blocker = pathlib.Path(self.tmp.name) / "blocker"
        blocker.write_text("file")
        with self.assertRaises(install.InstallError):
            install.apply([change, (blocker / "child", "", "x")])
        self.assertFalse(self.hook.exists())

    def test_a_plain_install_notes_a_missing_hook_in_one_line(self):
        code, out, err = run_clone(self.clone, self.home)
        self.assertEqual(code, 0, err)
        lines = [l for l in err.splitlines() if "pre-push" in l]
        self.assertEqual(len(lines), 1)
        self.assertIn("--git-hook", lines[0])

    def test_a_plain_install_warns_when_the_hook_names_another_home(self):
        run_clone(self.clone, self.home, "--git-hook")
        stale = self.hook.read_text().replace(shlex.quote(str(self.home)), "/elsewhere/home")
        self.hook.write_text(stale)
        code, out, err = run_clone(self.clone, self.home)
        self.assertEqual(code, 0, err)
        lines = [l for l in err.splitlines() if "pre-push" in l]
        self.assertEqual(len(lines), 1)
        self.assertIn("/elsewhere/home", lines[0])
        self.assertEqual(self.hook.read_text(), stale)

    def test_a_plain_install_never_rewrites_the_hook(self):
        run_clone(self.clone, self.home, "--git-hook")
        self.hook.write_text(self.hook.read_text() + "# edited\n")
        before = (self.hook.read_bytes(), self.hook.stat().st_mtime_ns)
        run_clone(self.clone, self.home)
        self.assertEqual((self.hook.read_bytes(), self.hook.stat().st_mtime_ns), before)

    def test_a_main_checkout_without_the_scripts_raises_and_changes_nothing(self):
        for name in ("maintainer/sdlc.py", "maintainer/skills/write-skill/scripts/final_run.py"):
            with self.subTest(missing=name):
                clone = make_clone(self.tmp.name, "lacking-" + name.replace("/", "-"))
                (clone / name).unlink()
                code, out, err = run_clone(clone, self.home, "--git-hook")
                self.assertEqual(code, 1)
                self.assertIn(name, err)
                self.assertFalse((clone / ".git" / "hooks" / "pre-push").exists())
                self.untouched()

    def test_a_home_with_a_space_draws_no_warning(self):
        spaced = pathlib.Path(self.tmp.name).resolve() / "a b"
        spaced.mkdir()
        shutil.copy(self.home / "tl-relay.yaml", spaced / "tl-relay.yaml")
        self.assertEqual(run_clone(self.clone, spaced, "--git-hook")[0], 0)
        code, out, err = run_clone(self.clone, spaced)
        self.assertEqual(code, 0, err)
        self.assertEqual([l for l in err.splitlines() if "pre-push" in l], [])

    def notice(self, fragment):
        before = self.hook.read_bytes() if self.hook.exists() else None
        code, out, err = run_clone(self.clone, self.home)
        self.assertEqual(code, 0, err)
        lines = [l for l in err.splitlines() if "pre-push" in l]
        self.assertEqual(len(lines), 1, err)
        self.assertIn(fragment, lines[0])
        self.assertEqual(self.hook.read_bytes() if self.hook.exists() else None, before)

    def test_a_plain_install_notes_a_set_hooks_path(self):
        git(self.clone, "config", "core.hooksPath", str(pathlib.Path(self.tmp.name) / "elsewhere"))
        self.notice("core.hooksPath")

    def test_a_plain_install_notes_a_hook_that_is_not_executable(self):
        run_clone(self.clone, self.home, "--git-hook")
        self.hook.chmod(0o644)
        self.notice("not executable")

    def test_a_plain_install_notes_a_foreign_hook(self):
        self.hook.write_text("#!/bin/sh\necho mine\n")
        self.notice("not written by tl-relay")

    def test_a_plain_install_draws_no_notice_for_a_current_hook(self):
        run_clone(self.clone, self.home, "--git-hook")
        code, out, err = run_clone(self.clone, self.home)
        self.assertEqual(code, 0, err)
        self.assertEqual([l for l in err.splitlines() if "pre-push" in l], [])

    def test_the_marker_names_tl_relay(self):
        self.assertEqual(install.HOOK_MARKER, "# tl-relay pre-push hook")

    def test_a_hook_with_only_the_old_marker_is_foreign(self):
        run_clone(self.clone, self.home, "--git-hook")
        self.hook.write_text(self.hook.read_text().replace(install.HOOK_MARKER, "# ai-sdlc pre-push hook"))
        before = self.hook.read_bytes()
        code, out, err = run_clone(self.clone, self.home, "--git-hook")
        self.assertEqual(code, 1)
        self.assertEqual(self.hook.read_bytes(), before)

    def test_a_dangling_foreign_symlink_raises_and_is_left_alone(self):
        target = pathlib.Path(self.tmp.name) / "nowhere"
        self.hook.symlink_to(target)
        code, out, err = run_clone(self.clone, self.home, "--git-hook")
        self.assertEqual(code, 1)
        self.assertIn("pre-push", err)
        self.assertTrue(self.hook.is_symlink())
        self.assertFalse(target.exists())
        self.untouched()

    def test_a_git_failure_other_than_not_a_repository_raises(self):
        (self.clone / ".git" / "config").write_text("[core\n")
        code, out, err = run_clone(self.clone, self.home, "--git-hook")
        self.assertEqual(code, 1)
        self.assertIn("git", err)
        self.untouched()

    def test_a_case_different_path_still_finds_the_clone(self):
        loud = self.clone.with_name(self.clone.name.upper())
        if not loud.exists() or not os.path.samefile(loud, self.clone):
            self.skipTest("case-sensitive file system")
        code, out, err = run_clone(loud, self.home, "--git-hook")
        self.assertEqual(code, 0, err)
        self.assertTrue(self.hook.exists())

    def test_non_utf8_git_output_does_not_crash_a_plain_install(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        subprocess.run(["git", "-C", str(self.clone), "config", "core.hooksPath", b"\xff".decode("latin-1")],
                       env=dict(env, **ISOLATED_GIT), check=True)
        raw = (self.clone / ".git" / "config").read_bytes().replace("\xc3\xbf".encode("latin-1"), b"\xff")
        (self.clone / ".git" / "config").write_bytes(raw)
        code, out, err = run_clone(self.clone, self.home)
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)
        code, out, err = run_clone(self.clone, self.home, "--git-hook")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)


    def test_a_plain_install_notes_a_main_checkout_without_the_scripts(self):
        for name in ("maintainer/sdlc.py", "maintainer/skills/write-skill/scripts/final_run.py"):
            with self.subTest(missing=name):
                clone = make_clone(self.tmp.name, "plain-" + name.replace("/", "-"))
                (clone / name).unlink()
                code, out, err = run_clone(clone, self.home)
                self.assertEqual(code, 0, err)
                lines = [l for l in err.splitlines() if "pre-push" in l]
                self.assertEqual(len(lines), 1, err)
                self.assertIn(name, lines[0])

    def test_a_plain_install_notes_a_hook_that_names_a_moved_checkout(self):
        run_clone(self.clone, self.home, "--git-hook")
        moved = self.clone.with_name("moved")
        self.clone.rename(moved)
        code, out, err = run_clone(moved, self.home)
        self.assertEqual(code, 0, err)
        lines = [l for l in err.splitlines() if "pre-push" in l]
        self.assertEqual(len(lines), 1, err)
        self.assertIn(str(self.clone), lines[0])
        self.assertIn("install --git-hook", lines[0])

    def test_an_unsearchable_scripts_directory_raises_install_error(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores modes")
        scripts = self.clone / "maintainer" / "skills" / "write-skill" / "scripts"
        scripts.chmod(0)
        self.addCleanup(scripts.chmod, 0o755)
        code, out, err = run_clone(self.clone, self.home, "--git-hook")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", err)
        self.untouched()

    def test_an_unreadable_hooks_directory_is_not_read_as_a_missing_hook(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores modes")
        run_clone(self.clone, self.home, "--git-hook")
        hooks = self.hook.parent
        hooks.chmod(0)
        self.addCleanup(hooks.chmod, 0o755)
        code, out, err = run_clone(self.clone, self.home)
        self.assertEqual(code, 0, err)
        lines = [l for l in err.splitlines() if "pre-push" in l]
        self.assertEqual(len(lines), 1, err)
        self.assertNotIn("not installed", lines[0])
        self.assertEqual(run_clone(self.clone, self.home, "--git-hook")[0], 1)

    def test_a_clone_path_ending_in_a_space_gets_its_hook(self):
        clone = make_clone(self.tmp.name, "trailing ")
        code, out, err = run_clone(clone, self.home, "--git-hook")
        self.assertEqual(code, 0, err)
        self.assertTrue((clone / ".git" / "hooks" / "pre-push").exists())


    def test_a_healthy_hook_run_from_another_letter_case_draws_no_notice(self):
        clone = make_clone(self.tmp.name, "caseclone")
        self.assertEqual(run_clone(clone, self.home, "--git-hook")[0], 0)
        loud = clone.with_name("CASECLONE")
        if not loud.exists() or not os.path.samefile(loud, clone):
            self.skipTest("case-sensitive file system")
        code, out, err = run_clone(loud, self.home)
        self.assertEqual(code, 0, err)
        self.assertEqual([l for l in err.splitlines() if "pre-push" in l], [])


if __name__ == "__main__":
    unittest.main()
