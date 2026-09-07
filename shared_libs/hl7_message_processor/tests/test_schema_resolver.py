import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hl7_message_processor.exceptions import SchemaNotFoundError
from hl7_message_processor.schema_resolver import SchemaResolver, normalize_version


class NormalizeVersionTests(unittest.TestCase):
    def test_dots_become_underscores(self) -> None:
        self.assertEqual(normalize_version("2.5.1"), "2_5_1")

    def test_strips_whitespace(self) -> None:
        self.assertEqual(normalize_version("  2.5.1  "), "2_5_1")


class SchemaResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)

        self.schemas_dir = root / "schemas"
        self.custom_schemas_dir = root / "custom_schemas"

        standard_version_dir = self.schemas_dir / "2_5_1"
        standard_version_dir.mkdir(parents=True)
        (standard_version_dir / "2_5_1_ADT_A05.xsd").write_text("<xsd:schema/>")
        (standard_version_dir / "2_5_1_ORU_R01.xsd").write_text("<xsd:schema/>")
        (standard_version_dir / "2_5_1_fields.xsd").write_text("<xsd:schema/>")
        (standard_version_dir / "2_5_1_segments.xsd").write_text("<xsd:schema/>")
        (standard_version_dir / "2_5_1_types.xsd").write_text("<xsd:schema/>")

        custom_version_dir = self.custom_schemas_dir / "2_5_1"
        custom_version_dir.mkdir(parents=True)
        (custom_version_dir / "ORU_R01_2_5_1.xsd").write_text("<xsd:schema/>")

        self.resolver = SchemaResolver(self.schemas_dir, self.custom_schemas_dir)

    def test_resolves_standard_schema_when_no_custom_exists(self) -> None:
        path = self.resolver.resolve("2.5.1", "ADT_A05")
        self.assertEqual(path, self.schemas_dir / "2_5_1" / "2_5_1_ADT_A05.xsd")

    def test_prefers_custom_schema_when_one_exists(self) -> None:
        path = self.resolver.resolve("2.5.1", "ORU_R01")
        self.assertEqual(path, self.custom_schemas_dir / "2_5_1" / "ORU_R01_2_5_1.xsd")

    def test_non_structure_files_are_not_indexed(self) -> None:
        with self.assertRaises(SchemaNotFoundError):
            self.resolver.resolve("2.5.1", "fields")

    def test_raises_when_neither_directory_has_a_match(self) -> None:
        with self.assertRaises(SchemaNotFoundError):
            self.resolver.resolve("2.5.1", "NOPE_N00")

    def test_raises_for_unknown_version(self) -> None:
        with self.assertRaises(SchemaNotFoundError):
            self.resolver.resolve("9.9.9", "ADT_A05")

    def test_missing_directories_do_not_raise_at_construction(self) -> None:
        resolver = SchemaResolver(Path("/does/not/exist"), Path("/also/missing"))
        with self.assertRaises(SchemaNotFoundError):
            resolver.resolve("2.5.1", "ADT_A05")


if __name__ == "__main__":
    unittest.main()
