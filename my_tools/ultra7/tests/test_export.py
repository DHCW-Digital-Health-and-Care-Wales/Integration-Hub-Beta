import unittest

from ultra7.export import extension_for, sanitize_filename, unique_filename


class TestExtensionFor(unittest.TestCase):
    def test_known_formats(self) -> None:
        self.assertEqual(extension_for("hl7"), ".hl7")
        self.assertEqual(extension_for("xml"), ".xml")
        self.assertEqual(extension_for("json"), ".json")


class TestSanitizeFilename(unittest.TestCase):
    def test_sanitizes_unsafe_characters(self) -> None:
        self.assertEqual(sanitize_filename("My Message"), "My Message")
        self.assertEqual(sanitize_filename("a/b\\c"), "a_b_c")

    def test_blank_name_falls_back_to_message(self) -> None:
        self.assertEqual(sanitize_filename("   "), "message")


class TestUniqueFilename(unittest.TestCase):
    def test_first_use_is_unmodified(self) -> None:
        used: set[str] = set()
        self.assertEqual(unique_filename("A01", ".hl7", used), "A01.hl7")

    def test_duplicate_names_get_disambiguated(self) -> None:
        used: set[str] = set()
        first = unique_filename("A01", ".hl7", used)
        second = unique_filename("A01", ".hl7", used)
        third = unique_filename("A01", ".hl7", used)
        self.assertEqual([first, second, third], ["A01.hl7", "A01 (2).hl7", "A01 (3).hl7"])


if __name__ == "__main__":
    unittest.main()
