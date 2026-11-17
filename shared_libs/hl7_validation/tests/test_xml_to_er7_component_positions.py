import re
import unittest
from pathlib import Path

from hl7_validation.convert import MAX_XML_COMPONENT_NUMBER, MAX_XML_FIELD_NUMBER, xml_to_er7

_NS = "urn:hl7-org:v2xml"


def _mrg_xml(mrg_1_children: str) -> str:
    return f'<ADT_A39 xmlns="{_NS}"><MRG><MRG.1>{mrg_1_children}</MRG.1></MRG></ADT_A39>'


def _mrg_segment(xml: str) -> str:
    return next(seg for seg in xml_to_er7(xml).split("\r") if seg.startswith("MRG|"))


class TestXmlToEr7ComponentPositions(unittest.TestCase):
    """An empty or absent component must keep its position; only trailing empty components are dropped."""

    def test_empty_first_component_keeps_its_position(self) -> None:
        xml = _mrg_xml(
            "<CX.1/><CX.2/><CX.3/><CX.4><HD.1>328</HD.1><HD.2/><HD.3/></CX.4><CX.5>PI</CX.5>"
        )
        self.assertEqual(_mrg_segment(xml), "MRG|^^^328^PI")

    def test_empty_authority_keeps_its_position(self) -> None:
        xml = _mrg_xml(
            "<CX.1>O1</CX.1><CX.2/><CX.3/><CX.4><HD.1/><HD.2/><HD.3/></CX.4><CX.5>PI</CX.5>"
        )
        self.assertEqual(_mrg_segment(xml), "MRG|O1^^^^PI")

    def test_all_components_populated(self) -> None:
        xml = _mrg_xml(
            "<CX.1>00001</CX.1><CX.2/><CX.3/><CX.4><HD.1>328</HD.1></CX.4><CX.5>PI</CX.5>"
        )
        self.assertEqual(_mrg_segment(xml), "MRG|00001^^^328^PI")

    def test_absent_components_are_placed_by_tag_number(self) -> None:
        xml = _mrg_xml("<CX.1>00001</CX.1><CX.4><HD.1>328</HD.1></CX.4><CX.5>PI</CX.5>")
        self.assertEqual(_mrg_segment(xml), "MRG|00001^^^328^PI")

    def test_trailing_empty_components_are_dropped(self) -> None:
        xml = _mrg_xml(
            "<CX.1>00001</CX.1><CX.2/><CX.3/><CX.4><HD.1>328</HD.1></CX.4><CX.5/>"
            "<CX.6><HD.1/><HD.2/><HD.3/></CX.6><CX.7/>"
        )
        self.assertEqual(_mrg_segment(xml), "MRG|00001^^^328")

    def test_subcomponents_are_joined_with_ampersand_and_keep_position(self) -> None:
        xml = _mrg_xml(
            "<CX.1>00001</CX.1><CX.4><HD.1/><HD.2>2.16.840.1</HD.2><HD.3>ISO</HD.3></CX.4>"
        )
        self.assertEqual(_mrg_segment(xml), "MRG|00001^^^&2.16.840.1&ISO")

    def test_fully_empty_field_is_empty(self) -> None:
        xml = _mrg_xml("<CX.1/><CX.4><HD.1/></CX.4>")
        self.assertEqual(_mrg_segment(xml), "MRG|")


class TestXmlToEr7PositionBounds(unittest.TestCase):
    """The number in a tag suffix sizes the padding built for it, so it must be bounded."""

    def test_oversized_component_suffix_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            xml_to_er7(_mrg_xml("<CX.1>00001</CX.1><CX.999999999/>"))

    def test_component_suffix_beyond_int_conversion_limit_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            xml_to_er7(_mrg_xml(f"<CX.{'9' * 5000}/>"))

    def test_component_at_the_limit_is_accepted_and_one_over_is_rejected(self) -> None:
        at_limit = _mrg_xml(f"<CX.{MAX_XML_COMPONENT_NUMBER}>X</CX.{MAX_XML_COMPONENT_NUMBER}>")
        self.assertEqual(_mrg_segment(at_limit), "MRG|" + "^" * (MAX_XML_COMPONENT_NUMBER - 1) + "X")

        over_limit = MAX_XML_COMPONENT_NUMBER + 1
        with self.assertRaises(ValueError):
            xml_to_er7(_mrg_xml(f"<CX.{over_limit}>X</CX.{over_limit}>"))

    def test_oversized_field_suffix_is_rejected(self) -> None:
        xml = f'<ADT_A39 xmlns="{_NS}"><MRG><MRG.999999999>X</MRG.999999999></MRG></ADT_A39>'
        with self.assertRaises(ValueError):
            xml_to_er7(xml)

    def test_field_at_the_limit_is_accepted_and_one_over_is_rejected(self) -> None:
        def mrg_xml(number: int) -> str:
            return f'<ADT_A39 xmlns="{_NS}"><MRG><MRG.{number}>X</MRG.{number}></MRG></ADT_A39>'

        self.assertEqual(xml_to_er7(mrg_xml(MAX_XML_FIELD_NUMBER)), "MRG|" + "|" * (MAX_XML_FIELD_NUMBER - 1) + "X")
        with self.assertRaises(ValueError):
            xml_to_er7(mrg_xml(MAX_XML_FIELD_NUMBER + 1))

    def test_bounds_cover_every_number_in_the_bundled_schemas(self) -> None:
        """Fails if a bundled schema is added or changed such that it needs a larger bound."""
        name_pattern = re.compile(r'(?:name|ref)="[A-Z][A-Z0-9]{1,2}\.(\d+)"')
        package_dir = Path(__file__).resolve().parent.parent / "hl7_validation"

        largest_field = largest_component = 0
        for xsd in package_dir.rglob("*.xsd"):
            numbers = [int(n) for n in name_pattern.findall(xsd.read_text(encoding="utf-8"))]
            if not numbers:
                continue
            if xsd.name.endswith("types.xsd"):
                largest_component = max(largest_component, *numbers)
            else:
                largest_field = max(largest_field, *numbers)

        self.assertGreater(largest_field, 0, "no schemas found - the scan is not looking in the right place")
        self.assertLessEqual(largest_field, MAX_XML_FIELD_NUMBER)
        self.assertLessEqual(largest_component, MAX_XML_COMPONENT_NUMBER)


if __name__ == "__main__":
    unittest.main()
