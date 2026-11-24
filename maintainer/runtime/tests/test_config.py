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
            (pathlib.Path(tmp) / "ai-sdlc.yaml").write_text("a: [1\n")
            with self.assertRaisesRegex(config.ConfigError, "ai-sdlc.yaml"):
                config._read(pathlib.Path(tmp) / "ai-sdlc.yaml")

    def test_merge_does_not_mutate_its_inputs(self):
        repo = {"git": {"a": 1}}
        config.merge(repo, {"git": {"b": 2}})
        self.assertEqual(repo, {"git": {"a": 1}})

    def test_load_merges_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, home = pathlib.Path(tmp) / "repo", pathlib.Path(tmp) / "home"
            (repo / "maintainer").mkdir(parents=True)
            home.mkdir()
            (repo / "maintainer" / "ai-sdlc.yaml").write_text("git:\n  branch_pattern: a\n")
            (home / "ai-sdlc.yaml").write_text("git:\n  worktree_root: /h\n")
            self.assertEqual(config.load(repo, home), {"git": {"branch_pattern": "a", "worktree_root": "/h"}})

    def test_load_reads_the_repo_config_under_maintainer(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, home = pathlib.Path(tmp) / "repo", pathlib.Path(tmp) / "home"
            (repo / "maintainer").mkdir(parents=True)
            (repo / "maintainer" / "ai-sdlc.yaml").write_text("tracker:\n  kind: jira\n")
            (repo / "ai-sdlc.yaml").write_text("tracker:\n  kind: wrong\n")
            self.assertEqual(config.load(repo, home), {"tracker": {"kind": "jira"}})

    def test_load_without_home_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, home = pathlib.Path(tmp) / "repo", pathlib.Path(tmp) / "home"
            (repo / "maintainer").mkdir(parents=True)
            (repo / "maintainer" / "ai-sdlc.yaml").write_text("a: 1\n")
            self.assertEqual(config.load(repo, home), {"a": 1})

    def test_load_rejects_a_list_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, home = pathlib.Path(tmp) / "repo", pathlib.Path(tmp) / "home"
            (repo / "maintainer").mkdir(parents=True)
            (repo / "maintainer" / "ai-sdlc.yaml").write_text("- a\n- b\n")
            with self.assertRaises(config.ConfigError) as caught:
                config.load(repo, home)
            self.assertEqual(str(caught.exception), "%s: the top level must be a mapping" % (repo / "maintainer" / "ai-sdlc.yaml"))

    def test_default_home(self):
        with unittest.mock.patch.dict(os.environ, {"AI_SDLC_HOME": "/x/home"}):
            self.assertEqual(config.default_home(), pathlib.Path("/x/home"))
        env = {k: v for k, v in os.environ.items() if k != "AI_SDLC_HOME"}
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(config.default_home(), pathlib.Path.home() / ".ai-sdlc")

    def test_default_repo(self):
        with unittest.mock.patch.dict(os.environ, {"AI_SDLC_REPO": "/x/repo"}):
            self.assertEqual(config.default_repo(), pathlib.Path("/x/repo"))
        env = {k: v for k, v in os.environ.items() if k != "AI_SDLC_REPO"}
        with unittest.mock.patch.dict(os.environ, env, clear=True):
            self.assertTrue((config.default_repo() / "maintainer" / "runtime" / "config.py").is_file())


    def _file(self, tmp, text):
        path = pathlib.Path(tmp) / "ai-sdlc.yaml"
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
        for name in ("ai-sdlc.yaml", "ai-sdlc.example.yaml"):
            with self.subTest(name=name):
                config._read(repo / name)

    def test_the_block_list(self):
        self.assertEqual(config.MAPPING_BLOCKS, ("project", "install", "tracker", "neutrality"))


if __name__ == "__main__":
    unittest.main()
