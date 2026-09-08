import unittest
from pathlib import Path
from xml.etree.ElementTree import Element as XElem  # nosec B405

from defusedxml.ElementTree import fromstring

from hl7_message_processor.constants import HL7_XML_NAMESPACE
from hl7_message_processor.converter import (
    _emit_element,
    _extract_text_from_element,
    _serialize_with_default_namespace,
    er7_to_xml,
    xml_to_er7,
)
from hl7_message_processor.exceptions import MessageNotProcessableError
from hl7_message_processor.xsd_structure import TypeMaps

_SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "hl7_message_processor" / "schemas" / "2_5_1"
_CUSTOM_SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "hl7_message_processor" / "custom_schemas" / "2_5_1"


def _tag(local_name: str) -> str:
    return f"{{{HL7_XML_NAMESPACE}}}{local_name}"


class Adt39DepthTests(unittest.TestCase):
    """Reproduces the design report's section 3.1 bug: an A40 (ADT_A39) message must nest PID/MRG
    inside an ADT_A39.PATIENT group element, not flatten them to the top level."""

    def setUp(self) -> None:
        self.er7 = (
            "MSH|^~\\&|SENDAPP|SENDFAC|RECAPP|RECFAC|20241230133601||ADT^A40^ADT_A39|MSG00001|P|2.5.1\r"
            "EVN|A40|20241230133601\r"
            "PID|1||123456^^^MRN^MR||DOE^JOHN\r"
            "MRG|987654^^^MRN^MR"
        )
        self.xsd_path = str(_SCHEMAS_DIR / "2_5_1_ADT_A39.xsd")

    def test_pid_and_mrg_are_nested_under_patient_group(self) -> None:
        xml = er7_to_xml(self.er7, self.xsd_path, structure_id="ADT_A39")
        root = fromstring(xml)

        self.assertEqual(root.tag, _tag("ADT_A39"))
        self.assertIsNone(root.find(_tag("PID")), "PID must not be a direct child of the root")
        self.assertIsNone(root.find(_tag("MRG")), "MRG must not be a direct child of the root")

        patient_group = root.find(_tag("ADT_A39.PATIENT"))
        self.assertIsNotNone(patient_group, "ADT_A39.PATIENT group is missing")
        self.assertIsNotNone(patient_group.find(_tag("PID")))
        self.assertIsNotNone(patient_group.find(_tag("MRG")))

    def test_msh_and_evn_present_at_top_level(self) -> None:
        xml = er7_to_xml(self.er7, self.xsd_path, structure_id="ADT_A39")
        root = fromstring(xml)
        self.assertIsNotNone(root.find(_tag("MSH")))
        self.assertIsNotNone(root.find(_tag("EVN")))

    def test_msh_9_message_type_is_decomposed_into_components(self) -> None:
        xml = er7_to_xml(self.er7, self.xsd_path, structure_id="ADT_A39")
        root = fromstring(xml)
        msh = root.find(_tag("MSH"))
        msh_9 = msh.find(_tag("MSH.9"))
        self.assertIsNotNone(msh_9)
        self.assertEqual(msh_9.find(_tag("MSG.1")).text, "ADT")
        self.assertEqual(msh_9.find(_tag("MSG.2")).text, "A40")
        self.assertEqual(msh_9.find(_tag("MSG.3")).text, "ADT_A39")

    def test_message_missing_required_evn_is_not_processable(self) -> None:
        er7_missing_evn = (
            "MSH|^~\\&|SENDAPP|SENDFAC|RECAPP|RECFAC|20241230133601||ADT^A40^ADT_A39|MSG00001|P|2.5.1\r"
            "PID|1||123456^^^MRN^MR||DOE^JOHN\r"
            "MRG|987654^^^MRN^MR"
        )
        with self.assertRaises(MessageNotProcessableError):
            er7_to_xml(er7_missing_evn, self.xsd_path, structure_id="ADT_A39")


class OruR01DepthTests(unittest.TestCase):
    """Reproduces the design report's section 3.2 bug: ORU_R01 has multiple levels of nested
    groups (PATIENT_RESULT > PATIENT > VISIT, and PATIENT_RESULT > ORDER_OBSERVATION > OBSERVATION),
    which a single "current group" pointer cannot track correctly."""

    def setUp(self) -> None:
        self.er7 = (
            "MSH|^~\\&|A|A|B|B|20241230133601||ORU^R01^ORU_R01|565475252|P|2.5.1\r"
            "PID|1||123456^^^MRN^MR||DOE^JOHN\r"
            "PV1|1|I\r"
            "OBR|1|||TESTCODE^Test Name\r"
            "OBX|1|ST|COMP^Component||42||||||F"
        )
        self.xsd_path = str(_CUSTOM_SCHEMAS_DIR / "ORU_R01_2_5_1.xsd")

    def test_full_group_nesting_depth_is_preserved(self) -> None:
        xml = er7_to_xml(self.er7, self.xsd_path, structure_id="ORU_R01")
        root = fromstring(xml)

        patient_result = root.find(_tag("ORU_R01.PATIENT_RESULT"))
        self.assertIsNotNone(patient_result, "ORU_R01.PATIENT_RESULT group is missing")

        patient = patient_result.find(_tag("ORU_R01.PATIENT"))
        self.assertIsNotNone(patient, "ORU_R01.PATIENT group is missing")
        self.assertIsNotNone(patient.find(_tag("PID")))
        visit = patient.find(_tag("ORU_R01.VISIT"))
        self.assertIsNotNone(visit, "ORU_R01.VISIT group is missing")
        self.assertIsNotNone(visit.find(_tag("PV1")))

        order_observation = patient_result.find(_tag("ORU_R01.ORDER_OBSERVATION"))
        self.assertIsNotNone(order_observation, "ORU_R01.ORDER_OBSERVATION group is missing")
        self.assertIsNotNone(order_observation.find(_tag("OBR")))

        observation = order_observation.find(_tag("ORU_R01.OBSERVATION"))
        self.assertIsNotNone(observation, "ORU_R01.OBSERVATION group is missing")
        self.assertIsNotNone(observation.find(_tag("OBX")))


class SubcomponentSeparatorTests(unittest.TestCase):
    """A component that is itself composite (e.g. an XCN field's 9th component, type HD - the
    assigning authority) must have its own sub-parts split/joined on "&" (the HL7 subcomponent
    separator), never "^" (the component separator used one level up, for the field's own
    components) - see e.g. XCN.9 -> HD.1/HD.2/HD.3."""

    def setUp(self) -> None:
        # Minimal synthetic type map mirroring XCN.9 (type HD) -> HD.1/HD.2/HD.3 (base types),
        # avoiding the need for a full field/segment/schema fixture for this focused case.
        self.type_maps = TypeMaps(
            element_to_type={"XCN.9": "HD"},
            type_children={"HD": ["HD.1", "HD.2", "HD.3"]},
            type_base={},
            element_max_occurs={},
            segment_sequences={},
        )
        # XCN.9 is reached via one prior level of "^" splitting (the field's own components), so
        # its own decomposition must use "&", mirroring how _emit_element/_extract_text_from_element
        # actually recurse in er7_to_xml/xml_to_er7.
        self.raw_value = "C7479400&2.16.840.1.113883.2.1.8.1.5.351&ISO"

    def test_er7_to_xml_splits_subcomponents_on_ampersand_not_caret(self) -> None:
        root = XElem("root")
        _emit_element(root, "XCN.9", self.raw_value, self.type_maps, separator="&")
        xml = _serialize_with_default_namespace(root)

        parsed = fromstring(xml)
        xcn_9 = parsed.find(_tag("XCN.9"))
        self.assertEqual(xcn_9.find(_tag("HD.1")).text, "C7479400")
        self.assertEqual(xcn_9.find(_tag("HD.2")).text, "2.16.840.1.113883.2.1.8.1.5.351")
        self.assertEqual(xcn_9.find(_tag("HD.3")).text, "ISO")

    def test_xml_to_er7_joins_subcomponents_on_ampersand_not_caret(self) -> None:
        root = XElem("root")
        _emit_element(root, "XCN.9", self.raw_value, self.type_maps, separator="&")

        er7_value = _extract_text_from_element(root[0], separator="&")
        self.assertEqual(er7_value, self.raw_value)


class Er7EscapeSequenceTests(unittest.TestCase):
    """ER7 escape sequences (\\T\\, \\F\\, etc.) must be decoded to literal characters when
    converting to XML, so the XML serializer can entity-encode them correctly (e.g. \\T\\ -> & ->
    &amp;), per the HL7 v2 XML encoding rules."""

    def setUp(self) -> None:
        self.xsd_path = str(_SCHEMAS_DIR / "2_5_1_ADT_A39.xsd")

    def _build_er7(self, family_name: str) -> str:
        return (
            "MSH|^~\\&|SENDAPP|SENDFAC|RECAPP|RECFAC|20241230133601||ADT^A40^ADT_A39|MSG00001|P|2.5.1\r"
            "EVN|A40|20241230133601\r"
            f"PID|1||123456^^^MRN^MR||{family_name}^JOHN\r"
            "MRG|987654^^^MRN^MR"
        )

    def test_subcomponent_separator_escape_decoded_to_ampersand_in_xml(self) -> None:
        er7 = self._build_er7(r"BGH ACCIDENT \T\ EMERGENCY")
        xml = er7_to_xml(er7, self.xsd_path, structure_id="ADT_A39")

        # The literal & must be present in the parsed XML text (defusedxml/ElementTree already
        # decodes the &amp; entity on parse), i.e. entity-encoding round-trips correctly.
        root = fromstring(xml)
        pid_5 = root.find(_tag("ADT_A39.PATIENT")).find(_tag("PID")).find(_tag("PID.5"))
        family_name = pid_5.find(_tag("XPN.1")).find(_tag("FN.1"))
        self.assertEqual(family_name.text, "BGH ACCIDENT & EMERGENCY")

        # The raw serialized string must contain the proper XML entity, not a literal &.
        self.assertIn("BGH ACCIDENT &amp; EMERGENCY", xml)

    def test_msh_encoding_characters_field_is_never_decoded(self) -> None:
        # MSH.2 ("^~\&") is the literal delimiter definition itself, not escaped data.
        er7 = self._build_er7("DOE")
        xml = er7_to_xml(er7, self.xsd_path, structure_id="ADT_A39")
        root = fromstring(xml)
        msh_2 = root.find(_tag("MSH")).find(_tag("MSH.2"))
        self.assertEqual(msh_2.text, "^~\\&")


class XmlToEr7EscapeSequenceTests(unittest.TestCase):
    """Literal HL7 delimiter characters read back from XML must be re-encoded into ER7 escape
    sequences before being assembled into a pipe-and-hat message, so they aren't misread as real
    field/component/repetition separators."""

    def setUp(self) -> None:
        self.xsd_path = str(_SCHEMAS_DIR / "2_5_1_ADT_A39.xsd")

    def test_literal_ampersand_encoded_back_to_subcomponent_escape(self) -> None:
        er7 = (
            "MSH|^~\\&|SENDAPP|SENDFAC|RECAPP|RECFAC|20241230133601||ADT^A40^ADT_A39|MSG00001|P|2.5.1\r"
            "EVN|A40|20241230133601\r"
            r"PID|1||123456^^^MRN^MR||BGH ACCIDENT \T\ EMERGENCY^JOHN" "\r"
            "MRG|987654^^^MRN^MR"
        )
        xml = er7_to_xml(er7, self.xsd_path, structure_id="ADT_A39")
        er7_back = xml_to_er7(xml)

        pid_segment = next(seg for seg in er7_back.split("\r") if seg.startswith("PID|"))
        self.assertIn(r"BGH ACCIDENT \T\ EMERGENCY", pid_segment)

    def test_msh_encoding_characters_field_is_never_re_encoded(self) -> None:
        er7 = (
            "MSH|^~\\&|SENDAPP|SENDFAC|RECAPP|RECFAC|20241230133601||ADT^A40^ADT_A39|MSG00001|P|2.5.1\r"
            "EVN|A40|20241230133601\r"
            "PID|1||123456^^^MRN^MR||DOE^JOHN\r"
            "MRG|987654^^^MRN^MR"
        )
        xml = er7_to_xml(er7, self.xsd_path, structure_id="ADT_A39")
        er7_back = xml_to_er7(xml)

        msh_segment = next(seg for seg in er7_back.split("\r") if seg.startswith("MSH|"))
        self.assertTrue(msh_segment.startswith("MSH|^~\\&|"))


class XmlToEr7RoundTripTests(unittest.TestCase):
    def test_adt_a39_round_trips_back_to_equivalent_er7(self) -> None:
        er7 = (
            "MSH|^~\\&|SENDAPP|SENDFAC|RECAPP|RECFAC|20241230133601||ADT^A40^ADT_A39|MSG00001|P|2.5.1\r"
            "EVN|A40|20241230133601\r"
            "PID|1||123456^^^MRN^MR||DOE^JOHN\r"
            "MRG|987654^^^MRN^MR"
        )
        xsd_path = str(_SCHEMAS_DIR / "2_5_1_ADT_A39.xsd")
        xml = er7_to_xml(er7, xsd_path, structure_id="ADT_A39")
        er7_back = xml_to_er7(xml)

        segments = er7_back.split("\r")
        self.assertEqual(len(segments), 4)
        self.assertEqual(segments[0].split("|")[8], "ADT^A40^ADT_A39")
        self.assertTrue(segments[1].startswith("EVN|"))
        self.assertTrue(segments[2].startswith("PID|"))
        self.assertTrue(segments[3].startswith("MRG|"))


class ObxVariableValueTypeTests(unittest.TestCase):
    """OBX-5's data type isn't fixed by the schema ("varies"/"xsd:anyType"); it's only resolvable
    at runtime from OBX-2 (Value Type). A composite OBX-2 code (e.g. CE) must decompose OBX-5 into
    its components, while a simple/text OBX-2 code (e.g. TX, ST, NM) must leave OBX-5 as plain
    text - see the module docstring / _resolve_variable_datatype_override."""

    def setUp(self) -> None:
        self.xsd_path = str(_CUSTOM_SCHEMAS_DIR / "ORU_R01_2_5_1.xsd")

    def _build_er7(self, obx_value_type: str, obx_value: str) -> str:
        return (
            "MSH|^~\\&|A|A|B|B|20241230133601||ORU^R01^ORU_R01|565475252|P|2.5.1\r"
            "PID|1||123456^^^MRN^MR||DOE^JOHN\r"
            "PV1|1|I\r"
            "OBR|1|||TESTCODE^Test Name\r"
            f"OBX|1|{obx_value_type}|COMP^Component||{obx_value}||||||F"
        )

    def _find_obx5(self, root: XElem) -> XElem:
        patient_result = root.find(_tag("ORU_R01.PATIENT_RESULT"))
        assert patient_result is not None
        order_observation = patient_result.find(_tag("ORU_R01.ORDER_OBSERVATION"))
        assert order_observation is not None
        observation = order_observation.find(_tag("ORU_R01.OBSERVATION"))
        assert observation is not None
        obx = observation.find(_tag("OBX"))
        assert obx is not None
        obx_5 = obx.find(_tag("OBX.5"))
        assert obx_5 is not None
        return obx_5

    def test_coded_element_value_type_decomposes_obx5_into_components(self) -> None:
        er7 = self._build_er7("CE", "NORM^Normal^99")
        xml = er7_to_xml(er7, self.xsd_path, structure_id="ORU_R01")
        root = fromstring(xml)

        obx_5 = self._find_obx5(root)
        self.assertIsNone(obx_5.text)
        ce_1 = obx_5.find(_tag("CE.1"))
        ce_2 = obx_5.find(_tag("CE.2"))
        ce_3 = obx_5.find(_tag("CE.3"))
        assert ce_1 is not None
        assert ce_2 is not None
        assert ce_3 is not None
        self.assertEqual(ce_1.text, "NORM")
        self.assertEqual(ce_2.text, "Normal")
        self.assertEqual(ce_3.text, "99")

    def test_text_value_type_leaves_obx5_as_plain_text(self) -> None:
        er7 = self._build_er7("TX", "Patient reviewed and findings are within normal limits.")
        xml = er7_to_xml(er7, self.xsd_path, structure_id="ORU_R01")
        root = fromstring(xml)

        obx_5 = self._find_obx5(root)
        self.assertEqual(obx_5.text, "Patient reviewed and findings are within normal limits.")
        self.assertEqual(len(list(obx_5)), 0)

    def test_numeric_value_type_leaves_obx5_as_plain_text(self) -> None:
        er7 = self._build_er7("NM", "72")
        xml = er7_to_xml(er7, self.xsd_path, structure_id="ORU_R01")
        root = fromstring(xml)

        obx_5 = self._find_obx5(root)
        self.assertEqual(obx_5.text, "72")
        self.assertEqual(len(list(obx_5)), 0)


if __name__ == "__main__":
    unittest.main()
