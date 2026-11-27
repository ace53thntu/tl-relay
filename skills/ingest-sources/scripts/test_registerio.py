import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from registerio import bad_char, register_field  # noqa: E402


class BadCharTest(unittest.TestCase):
    def test_bad_char_finds_each_blocked_class(self):
        for ch in ("\t", "\n", "\r", "\x7f", "\x85", "\ufeff", "\u200b", "\u2028", "\u2029"):
            self.assertEqual(bad_char("S-01" + ch + "AC1"), ch, repr(ch))
        self.assertEqual(bad_char("\ufeffS-01-AC1"), "\ufeff")

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


if __name__ == "__main__":
    unittest.main()
