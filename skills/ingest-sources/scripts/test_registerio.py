import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from registerio import bad_char, register_field, require_columns  # noqa: E402


class BadCharTest(unittest.TestCase):
    def test_bad_char_finds_each_blocked_class(self):
        for ch in ("\t", "\n", "\r", "\x7f", "\x85", "\ufeff", "\u200b", "\u2028", "\u2029"):
            self.assertEqual(bad_char("S-01" + ch + "AC1"), ch, repr(ch))
        self.assertEqual(bad_char("\ufeffS-01-AC1"), "\ufeff")

    def test_bad_char_finds_surrogates_lookalike_spaces_and_markup(self):
        for ch in ("\ud800", "\udcff", "\u00a0", "\u3000", "\u2009", "|", '"', "`"):
            self.assertEqual(bad_char("S-01" + ch + "AC1"), ch, repr(ch))

    def test_bad_char_passes_letters_from_any_script(self):
        for value in ("S-01-AC1", "US-01 AC1", "Tiếng-Việt-01", "ภาษาไทย-01", "US-01-AC1*"):
            self.assertIsNone(bad_char(value), value)

    def test_register_field_names_the_code_point(self):
        with self.assertRaises(ValueError) as cm:
            register_field({"id": "S-01\tAC1"}, 3, "id")
        self.assertEqual(str(cm.exception), "row 3: 'id' holds U+0009")

    def test_register_field_checks_surrounding_whitespace_first(self):
        with self.assertRaises(ValueError) as cm:
            register_field({"story": "US-01\n"}, 2, "story")
        self.assertEqual(str(cm.exception), "row 2: 'story' must not carry surrounding whitespace")


class RequireColumnsTest(unittest.TestCase):
    def test_present_columns_pass(self):
        self.assertIsNone(require_columns(["new_id", "old_id", "kind"], ("new_id", "old_id")))

    def test_a_missing_column_is_named(self):
        with self.assertRaises(ValueError) as cm:
            require_columns(["new_id", "old", "kind"], ("new_id", "old_id"))
        self.assertEqual(str(cm.exception), "missing column old_id")

    def test_no_header_names_the_first_column(self):
        with self.assertRaises(ValueError) as cm:
            require_columns(None, ("new_id", "old_id"))
        self.assertEqual(str(cm.exception), "missing column new_id")


if __name__ == "__main__":
    unittest.main()
