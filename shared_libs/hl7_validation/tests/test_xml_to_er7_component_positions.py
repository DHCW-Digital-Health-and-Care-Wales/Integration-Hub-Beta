import unittest

from hl7_validation.convert import xml_to_er7

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


if __name__ == "__main__":
    unittest.main()
