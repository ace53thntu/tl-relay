import pathlib
import re
import sys
import tempfile
import unittest

SKILLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILLS.parent / "maintainer"))

from runtime import yamlio  # noqa: E402

FORKED = ("debug-issue", "test-first", "verify-done", "brainstorm", "write-plan", "run-plan", "review-change", "using-tl-relay")

UPSTREAM_NAMES = (
    "brainstorming",
    "diagnosing-superpowers",
    "dispatching-parallel-agents",
    "executing-plans",
    "finishing-a-development-branch",
    "receiving-code-review",
    "requesting-code-review",
    "subagent-driven-development",
    "systematic-debugging",
    "test-driven-development",
    "using-git-worktrees",
    "using-superpowers",
    "verification-before-completion",
    "writing-plans",
    "writing-skills",
)

PLUGIN = re.compile(r"superpowers|CLAUDE_PLUGIN_ROOT|primeradiant", re.IGNORECASE)
LINK = re.compile(r"\]\(([^)\s]+)\)")
FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[^\n]*$", re.MULTILINE | re.DOTALL)
CODE_SPAN = re.compile(r"(`+).+?\1")


def upstream_pattern(name):
    if name == "brainstorming":
        return "`%s`" % name
    return r"(?<![\w-])%s(?![\w-])" % re.escape(name)


def forked_files(markdown_only=False):
    for name in FORKED:
        for path in sorted((SKILLS / name).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if markdown_only and path.suffix != ".md":
                continue
            yield path


def local_links(text):
    return LINK.findall(CODE_SPAN.sub("", FENCE.sub("", text)))


def skill_dirs():
    return sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").is_file())


def skill_files(markdown_only=False):
    for directory in skill_dirs():
        for path in sorted(directory.rglob("*")):
            parts = path.relative_to(SKILLS).parts
            if any(p == "__pycache__" or p.startswith(".venv") for p in parts):
                continue
            if not path.is_file():
                continue
            if markdown_only and path.suffix != ".md":
                continue
            yield path


def read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def frontmatter(path):
    lines = read(path).splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("no frontmatter in %s" % path)
    if "---" not in lines[1:]:
        raise ValueError("no closing --- in %s" % path)
    end = lines[1:].index("---") + 1
    with tempfile.TemporaryDirectory() as tmp:
        block = pathlib.Path(tmp) / "frontmatter.yaml"
        block.write_text("\n".join([""] + lines[1:end]) + "\n", encoding="utf-8")
        try:
            fields = yamlio.load(block)
        except yamlio.YamlError as exc:
            raise yamlio.YamlError(str(exc).replace(str(block), str(path))) from None
    if fields is None:
        return {}
    if not isinstance(fields, dict):
        raise ValueError("frontmatter is not a mapping in %s" % path)
    return fields


class ForkedSkills(unittest.TestCase):
    def test_each_skill_names_itself(self):
        for directory in skill_dirs():
            name = directory.name
            with self.subTest(skill=name):
                fields = frontmatter(directory / "SKILL.md")
                self.assertEqual(fields.get("name"), name)
                self.assertTrue(fields.get("description"))

    def test_every_forked_skill_is_a_skill_directory(self):
        found = {d.name for d in skill_dirs()}
        self.assertLessEqual(set(FORKED), found, f"forked skills without a SKILL.md: {sorted(set(FORKED) - found)}")

    def test_no_skill_file_names_the_plugin(self):
        for path in skill_files():
            with self.subTest(file=str(path.relative_to(SKILLS))):
                self.assertIsNone(PLUGIN.search(read(path)))

    def test_no_forked_skill_names_an_upstream_skill(self):
        for path in forked_files():
            text = read(path)
            for name in UPSTREAM_NAMES:
                with self.subTest(file=str(path.relative_to(SKILLS)), name=name):
                    self.assertIsNone(re.search(upstream_pattern(name), text))

    def test_each_relative_link_resolves(self):
        for path in skill_files(markdown_only=True):
            if "fixtures" in path.relative_to(SKILLS).parts:
                continue
            for target in local_links(read(path)):
                if re.match(r"[a-z][a-z0-9+.-]*:|#", target) or re.search("[<>…]", target):
                    continue
                with self.subTest(file=str(path.relative_to(SKILLS)), link=target):
                    self.assertTrue((path.parent / target.split("#")[0]).exists())

    def test_links_in_code_are_not_checked(self):
        text = "see [a](real.md)\n```\n[b](fake.md)\n```\nand `[c](fake2.md)` here"
        self.assertEqual(local_links(text), ["real.md"])

    def test_no_skill_names_a_superpowers_skill(self):
        for path in sorted(SKILLS.rglob("*")):
            relative = path.relative_to(SKILLS)
            if not path.is_file() or "__pycache__" in relative.parts:
                continue
            if relative.parts[0] == "tests":
                continue
            if any(part.startswith(".venv") for part in relative.parts):
                continue
            text = read(path)
            with self.subTest(file=str(relative)):
                self.assertNotIn("superpowers:", text)
            for name in UPSTREAM_NAMES:
                with self.subTest(file=str(relative), name=name):
                    self.assertIsNone(re.search(upstream_pattern(name), text))


class Frontmatter(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = pathlib.Path(tmp.name) / "SKILL.md"

    def parse(self, text):
        self.path.write_text(text, encoding="utf-8")
        return frontmatter(self.path)

    def test_invalid_yaml_raises_the_parser_error(self):
        with self.assertRaisesRegex(yamlio.YamlError, "mapping values are not allowed"):
            self.parse("---\nname: x\ndescription: Use when: a thing\n---\nbody\n")

    def test_a_parse_error_names_the_skill_file(self):
        with self.assertRaisesRegex(yamlio.YamlError, re.escape(str(self.path))):
            self.parse("---\nname: x\ndescription: Use when: a thing\n---\nbody\n")

    def test_a_parse_error_gives_the_skill_file_line(self):
        with self.assertRaisesRegex(yamlio.YamlError, "at line 3 "):
            self.parse("---\nname: x\ndescription: Use when: a thing\n---\nbody\n")

    def test_a_file_without_an_opening_marker_raises(self):
        with self.assertRaisesRegex(ValueError, "no frontmatter"):
            self.parse("name: x\n---\nbody\n")

    def test_a_file_without_a_closing_marker_raises(self):
        with self.assertRaisesRegex(ValueError, "no closing --- in"):
            self.parse("---\nname: x\nbody\n")

    def test_frontmatter_that_is_not_a_mapping_raises(self):
        with self.assertRaisesRegex(ValueError, "not a mapping"):
            self.parse("---\njust text\n---\nbody\n")

    def test_empty_frontmatter_has_no_fields(self):
        self.assertEqual(self.parse("---\n---\nbody\n"), {})


if __name__ == "__main__":
    unittest.main()
