import contextlib
import io
import unittest

import overlap
from overlap import normalise, line_hash, file_verdict


def distinct(n):
    return [f"line number {i:04d} with padding text" for i in range(n)]


def hashes_of(lines):
    return {line_hash(normalise(line)) for line in lines}


class Normalise(unittest.TestCase):
    def test_a_short_line_is_not_counted(self):
        self.assertIsNone(normalise("   }   "))
        self.assertIsNone(normalise("x" * 19))

    def test_case_and_spacing_do_not_hide_a_match(self):
        self.assertEqual(
            normalise("Foo   Bar baz qux quux corge"),
            normalise("foo bar BAZ qux quux corge"),
        )


class Verdict(unittest.TestCase):
    def verdict(self, lines, upstream_lines, fixed_lines=()):
        return file_verdict(
            "\n".join(lines), hashes_of(upstream_lines), hashes_of(fixed_lines)
        )

    def test_ten_percent_passes_and_eleven_fails(self):
        lines = distinct(100)
        ten = lines[::10]
        self.assertTrue(self.verdict(lines, ten).passes)
        self.assertFalse(self.verdict(lines, ten + [lines[5]]).passes)

    def test_three_matching_lines_in_a_row_fail(self):
        lines = distinct(100)
        self.assertFalse(self.verdict(lines, lines[10:13]).passes)
        self.assertTrue(self.verdict(lines, lines[10:12]).passes)

    def test_a_fixed_line_is_not_counted(self):
        lines = distinct(10)
        self.assertEqual(self.verdict(lines, [], lines[:1]).counted, 9)

    def test_a_fixed_line_does_not_reset_a_run(self):
        lines = distinct(4)
        v = self.verdict(lines, [lines[0], lines[2], lines[3]], [lines[1]])
        self.assertEqual(v.longest_run, 3)

    def test_a_repeated_fixed_line_counts_each_time(self):
        lines = distinct(3)
        v = self.verdict(lines + [lines[0]] * 5 + distinct(10)[4:], [], lines[:1])
        self.assertEqual(v.exempted, 6)

    def test_more_than_five_exempted_lines_fail(self):
        fixed = distinct(1)
        clean = distinct(11)[1:]
        self.assertFalse(self.verdict(fixed * 6 + clean, [], fixed).passes)
        self.assertTrue(self.verdict(fixed * 5 + clean, [], fixed).passes)

    def test_an_empty_file_passes(self):
        self.assertTrue(file_verdict("", set(), set()).passes)


class Repository(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = overlap.load_upstream()
        cls.fixed = overlap.load_fixed()

    def verdict_of(self, path, rel):
        text = path.read_text(encoding="utf-8", errors="replace")
        return file_verdict(text, self.upstream, self.fixed.get(rel, set()))

    def test_the_walk_covers_every_skill_and_skips_tooling(self):
        from test_skills import skill_dirs, skill_files
        names = [d.name for d in skill_dirs()]
        self.assertIn("ingest-sources", names)
        self.assertIn("write-hla", names)
        self.assertNotIn("tests", names)
        rels = {str(p.relative_to(overlap.SKILLS)) for p in skill_files()}
        self.assertIn("ingest-sources/scripts/pdf2md.py", rels)
        self.assertIn("debug-issue/tests/test-pressure-1.md", rels)

    def test_every_skill_file_passes(self):
        for path, rel in overlap.overlap_files():
            with self.subTest(file=rel):
                self.assertTrue(self.verdict_of(path, rel).passes)

    def test_the_walk_covers_maintainer_skills(self):
        rels = {rel for _, rel in overlap.overlap_files()}
        self.assertIn("write-skill/gates.md", rels)
        self.assertIn("retro/SKILL.md", rels)
        self.assertIn("debug-issue/SKILL.md", rels)

    def test_no_skill_name_is_in_both_roots(self):
        public = {p.name for p in overlap.SKILLS.iterdir() if (p / "SKILL.md").is_file()}
        internal = {p.name for p in overlap.MAINTAINER_SKILLS.iterdir() if (p / "SKILL.md").is_file()}
        self.assertEqual(public & internal, set())

    def test_the_report_lists_maintainer_files(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            overlap.report()
        self.assertRegex(out.getvalue(), r"(?m)^PASS \S+ \S+ run=\d+ write-skill/gates\.md$")

    def test_at_most_five_fixed_lines_per_file(self):
        paths = {rel: path for path, rel in overlap.overlap_files()}
        for rel in self.fixed:
            with self.subTest(file=rel):
                self.assertLessEqual(self.verdict_of(paths[rel], rel).exempted, 5)

    def test_no_fixed_line_is_listed_twice(self):
        entries = [
            tuple(raw.split("\t")[:2])
            for raw in overlap.FIXED.read_text(encoding="utf-8").splitlines()
            if raw.strip()
        ]
        self.assertEqual(len(entries), len(set(entries)))

    def test_every_fixed_line_has_a_reason(self):
        for raw in overlap.FIXED.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            with self.subTest(line=raw[:40]):
                parts = raw.split("\t")
                self.assertEqual(len(parts), 3)
                self.assertTrue(parts[2].strip())

    def test_the_fixture_names_all_three_sources(self):
        lines = overlap.UPSTREAM.read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines[0].startswith("# superpowers 7.0.2 "))
        self.assertTrue(lines[1].startswith("# agent-skills "))
        self.assertTrue(lines[2].startswith("# skill-creator "))


if __name__ == "__main__":
    unittest.main()
