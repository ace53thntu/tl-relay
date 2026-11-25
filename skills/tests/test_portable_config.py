import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PAGE = ROOT / "skills" / "using-tl-relay" / "config.md"

NEEDLES = (
    "## Lookup", "## Paths", "## Worktrees", "## Unset knowledge_dir",
    "git rev-parse --path-format=absolute --git-common-dir",
    "The walk stops before `~`",
    "`~/.tl-relay/config.yaml`",
    "key by key",
    "`<runtime>` is `<state_dir>/<workspace>`",
    "`state_dir` defaults to `~/.tl-relay`",
    "Two workspace roots with the same basename share one `<runtime>`",
    "`<design root>`",
    "`plan-runs/<plan>/`",
    "the `CLAUDE.md` section \"Worktree location\", else `$WORKTREE_ROOT`, else `worktree_dir`, else `<state_dir>/worktrees`",
    "`<root>/<repo>/<branch>`",
    "`knowledge_dir` has no default",
    "say so in one line",
    "never resolves against a worktree",
    "never follow the override",
)


class PortableConfigTest(unittest.TestCase):
    def test_config_page_states_each_rule(self):
        text = PAGE.read_text()
        for needle in NEEDLES:
            self.assertIn(needle, text)

    def test_example_config_lists_worktree_dir(self):
        self.assertIn("worktree_dir", (ROOT / "config.example.yaml").read_text())

    def test_readme_links_the_config_page(self):
        self.assertIn("using-tl-relay/config.md", (ROOT / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
