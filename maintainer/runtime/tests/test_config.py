import os
import pathlib
import re
import tempfile
import unittest
import unittest.mock

import fixture
from runtime import config


class Config(unittest.TestCase):
    def test_merge_home_wins_and_lists_replace(self):
        repo = {"git": {"branch_pattern": "a", "worktree_root": "/r"}, "x": [1, 2]}
        home = {"git": {"worktree_root": "/h"}, "x": [3]}
        self.assertEqual(
            config.merge(repo, home),
            {"git": {"branch_pattern": "a", "worktree_root": "/h"}, "x": [3]},
        )

    def test_merge_treats_a_home_null_as_absent(self):
        self.assertEqual(config.merge({"git": {"a": 1}}, {"git": None, "new": None}), {"git": {"a": 1}, "new": None})

    def test_a_malformed_file_is_a_config_error_naming_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "tl-relay.yaml").write_text("a: [1\n")
            with self.assertRaisesRegex(config.ConfigError, "tl-relay.yaml"):
                config._read(pathlib.Path(tmp) / "tl-relay.yaml")

    def test_merge_does_not_mutate_its_inputs(self):
        repo = {"git": {"a": 1}}
        config.merge(repo, {"git": {"b": 2}})
        self.assertEqual(repo, {"git": {"a": 1}})

    def test_load_merges_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, home = pathlib.Path(tmp) / "repo", pathlib.Path(tmp) / "home"
            (repo / "maintainer").mkdir(parents=True)
            home.mkdir()
            (repo / "maintainer" / "tl-relay.yaml").write_text("git:\n  branch_pattern: a\n")
            (home / "tl-relay.yaml").write_text("git:\n  worktree_root: /h\n")
            self.assertEqual(config.load(repo, home), {"git": {"branch_pattern": "a", "worktree_root": "/h"}})

    def test_load_reads_the_repo_config_under_maintainer(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, home = pathlib.Path(tmp) / "repo", pathlib.Path(tmp) / "home"
            (repo / "maintainer").mkdir(parents=True)
            (repo / "maintainer" / "tl-relay.yaml").write_text("tracker:\n  kind: jira\n")
            (repo / "tl-relay.yaml").write_text("tracker:\n  kind: wrong\n")
            self.assertEqual(config.load(repo, home), {"tracker": {"kind": "jira"}})

    def test_load_without_home_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, home = pathlib.Path(tmp) / "repo", pathlib.Path(tmp) / "home"
            (repo / "maintainer").mkdir(parents=True)
            (repo / "maintainer" / "tl-relay.yaml").write_text("a: 1\n")
            self.assertEqual(config.load(repo, home), {"a": 1})

    def test_load_rejects_a_list_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, home = pathlib.Path(tmp) / "repo", pathlib.Path(tmp) / "home"
            (repo / "maintainer").mkdir(parents=True)
            (repo / "maintainer" / "tl-relay.yaml").write_text("- a\n- b\n")
            with self.assertRaises(config.ConfigError) as caught:
                config.load(repo, home)
            self.assertEqual(str(caught.exception), "%s: the top level must be a mapping" % (repo / "maintainer" / "tl-relay.yaml"))

    def test_default_home_prefers_tl_relay_home(self):
        with unittest.mock.patch.dict(os.environ, {"TL_RELAY_HOME": "/x/new"}):
            self.assertEqual(config.default_home(), pathlib.Path("/x/new"))

    def test_an_empty_tl_relay_home_uses_the_default_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            with unittest.mock.patch.dict(os.environ, {"TL_RELAY_HOME": "", "AI_SDLC_HOME": "/x/old"}), \
                    unittest.mock.patch.object(pathlib.Path, "home", return_value=tmp):
                self.assertEqual(config.default_home(), tmp / ".tl-relay")

    def test_default_home_without_variables(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            with unittest.mock.patch.dict(os.environ), unittest.mock.patch.object(pathlib.Path, "home", return_value=tmp):
                os.environ.pop("TL_RELAY_HOME", None)
                os.environ.pop("AI_SDLC_HOME", None)
                self.assertEqual(config.default_home(), tmp / ".tl-relay")
                (tmp / ".ai-sdlc").mkdir()
                self.assertEqual(config.default_home(), tmp / ".tl-relay")

    def test_default_repo(self):
        with unittest.mock.patch.dict(os.environ, {"TL_RELAY_REPO": "/x/repo"}):
            self.assertEqual(config.default_repo(), pathlib.Path("/x/repo"))
        with unittest.mock.patch.dict(os.environ, {}):
            os.environ.pop("TL_RELAY_REPO", None)
            self.assertTrue((config.default_repo() / "maintainer" / "runtime" / "config.py").is_file())

    def test_load_ignores_an_old_home_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, home = pathlib.Path(tmp) / "repo", pathlib.Path(tmp) / "home"
            (repo / "maintainer").mkdir(parents=True)
            home.mkdir()
            (home / "ai-sdlc.yaml").write_text("project: {name: old}\n")
            self.assertEqual(config.load(repo, home), {})

    def _file(self, tmp, text):
        path = pathlib.Path(tmp) / "tl-relay.yaml"
        path.write_text(text)
        return path

    def test_a_non_mapping_block_is_a_config_error_naming_file_and_key(self):
        for key in config.MAPPING_BLOCKS:
            for value in ("just-a-string", "[a, b]", "[]"):
                with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as tmp:
                    path = self._file(tmp, "%s: %s\n" % (key, value))
                    with self.assertRaisesRegex(config.ConfigError, "%s: %s must be a mapping" % (re.escape(str(path)), key)):
                        config._read(path)

    def test_an_empty_block_still_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(config._read(self._file(tmp, "git:\nproject: {}\n")), {"git": None, "project": {}})

    def test_the_tracked_configs_still_load(self):
        repo = pathlib.Path(__file__).resolve().parents[2]
        for name in ("tl-relay.yaml", "tl-relay.example.yaml"):
            with self.subTest(name=name):
                config._read(repo / name)

    def test_the_example_holds_only_keys_the_tooling_reads(self):
        repo = pathlib.Path(__file__).resolve().parents[2]
        doc = config._read(repo / "tl-relay.example.yaml")
        self.assertEqual(doc["apiVersion"], "tl-relay/v1")
        self.assertEqual(sorted(doc), ["apiVersion", "install", "kind", "project"])

    def test_the_block_list(self):
        self.assertEqual(config.MAPPING_BLOCKS, ("project", "install", "tracker", "neutrality"))


if __name__ == "__main__":
    unittest.main()
