import unittest
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as ET
from hl7apy.exceptions import InvalidEncodingChars

from hl7_validation.convert import convert_er7_to_xml


class TestConvertEr7ToXmlNoDataLoss(unittest.TestCase):
    @staticmethod
    def _sample_messages_dir() -> Path:
        """Return the repository's local sample message directory."""
        return Path(__file__).resolve().parents[3] / "local" / "sample_messages"

    @staticmethod
    def _normalize_field_value(value: str) -> str:
        """
        Normalize an HL7 field string for semantic equality checks.

        Trailing empty components (e.g., "^^W00000^") are formatting-only and
        can be dropped by parser/serializer round-trips without losing data.
        For example, ^^W00000^ equals ^^W00000.
        """
        repetitions = value.split("~")
        normalized_reps: list[str] = []

        for rep in repetitions:
            components = rep.split("^")
            while components and components[-1] == "":
                components.pop()
            normalized_reps.append("^".join(components))

        return "~".join(normalized_reps)

    @staticmethod
    def _strip_namespace(tag: str) -> str:
        """
        Remove the XML namespace from a tag.

        XML from `convert_er7_to_xml` is namespace-qualified
        (`{urn:hl7-org:v2xml}PID`), but comparison logic expects plain HL7
        names (`PID`, `PID.3`).
        """
        if tag.startswith("{") and "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    @staticmethod
    def _is_segment_tag(tag: str) -> bool:
        """
        Return True if a tag resembles an HL7 segment name.

        Treat 3-character tags with two leading letters and a final letter
        or digit as segment identifiers (e.g., MSH, PID, PV1). This helps
        distinguish segment nodes from group/container nodes in XML.
        """
        if len(tag) != 3:
            return False
        return tag[0].isupper() and tag[1].isupper() and (tag[2].isupper() or tag[2].isdigit())

    def _extract_text(self, elem: Any) -> str:
        """
        Reconstruct an ER7-like value from an XML field/component node.

        Behavior:
        - If the current element has direct text, return its stripped value.
        - Otherwise, recurse through child elements and collect non-empty text.
        - Join child values with `^` to mirror HL7 component composition.

        This allows XML structures such as nested datatype components to be
        compared back to the original ER7 field representation.
        """
        text = (elem.text or "").strip()
        if text:
            return text

        children_values: list[str] = []
        for child in list(elem):
            child_text = self._extract_text(child)
            if child_text:
                children_values.append(child_text)
        return "^".join(children_values) if children_values else ""

    @staticmethod
    def _parse_er7_segments(er7: str) -> list[tuple[str, dict[int, str]]]:
        """
        Parse an ER7 message into an ordered segment/field structure.

        Output format is `[(segment_name, {field_number: value, ...}), ...]`
        with HL7 field numbering semantics preserved, including special MSH
        handling where `MSH.1` is the field separator.
        """
        segments: list[tuple[str, dict[int, str]]] = []

        for line in [ln.strip("\r") for ln in er7.splitlines() if ln.strip()]:
            parts = line.split("|")
            seg_name = parts[0]
            fields: dict[int, str] = {}

            if seg_name == "MSH":
                fields[1] = "|"
                for index in range(1, len(parts)):
                    fields[index + 1] = parts[index]
            else:
                for index in range(1, len(parts)):
                    fields[index] = parts[index]

            segments.append((seg_name, fields))

        return segments

    def _parse_xml_segments(self, xml_string: str) -> list[tuple[str, dict[int, str]]]:
        """
        Parse converter-produced HL7v2 XML into ordered segment field maps.

        The XML emitted by `convert_er7_to_xml` can contain namespace-qualified
        tags and optional group/container elements. This helper walks the full
        tree, keeps only segment nodes (e.g., MSH, PID, PV1), and flattens each
        segment into:

        - segment name (str)
        - dictionary of field number -> ER7-like value string

        Repeated XML fields are merged back to `~`-separated values so they can
        be compared with the original ER7 payload using the same representation.

        Returns:
            Ordered list of `(segment_name, {field_number: value})` tuples.
        """
        root = ET.fromstring(xml_string)
        segments: list[tuple[str, dict[int, str]]] = []

        def walk(node: Any) -> None:
            """Recursively traverse XML, collecting only HL7 segment elements."""
            for child in list(node):
                tag = self._strip_namespace(child.tag)
                if self._is_segment_tag(tag):
                    fields: dict[int, list[str]] = {}
                    for field_elem in list(child):
                        field_tag = self._strip_namespace(field_elem.tag)
                        if "." not in field_tag:
                            continue

                        _, field_num_str = field_tag.split(".", 1)
                        try:
                            field_num = int(field_num_str)
                        except ValueError:
                            continue

                        field_value = self._extract_text(field_elem)
                        fields.setdefault(field_num, []).append(field_value)

                    merged_fields = {idx: "~".join(values) for idx, values in fields.items()}
                    segments.append((tag, merged_fields))
                else:
                    walk(child)

        walk(root)
        return segments

    @staticmethod
    def _get_field_value(
        segments: list[tuple[str, dict[int, str]]], segment_name: str, field_number: int
    ) -> str | None:
        """Return the first value for a specific segment field from parsed segment tuples."""
        return next((fields.get(field_number) for seg_name, fields in segments if seg_name == segment_name), None)

    def _assert_no_non_empty_data_loss(self, er7_message: str) -> None:
        normalized_er7 = "\r".join([line for line in er7_message.splitlines() if line.strip()])

        xml_string = convert_er7_to_xml(normalized_er7)

        er7_segments = self._parse_er7_segments(normalized_er7)
        xml_segments = self._parse_xml_segments(xml_string)

        self.assertEqual(len(er7_segments), len(xml_segments), "Segment count should be preserved")

        missing_non_empty: list[tuple[int, str, int, str]] = []
        changed_non_empty: list[tuple[int, str, int, str, str]] = []

        for segment_index, (er7_seg_name, er7_fields) in enumerate(er7_segments):
            xml_seg_name, xml_fields = xml_segments[segment_index]
            self.assertEqual(er7_seg_name, xml_seg_name, "Segment order and type should be preserved")

            for field_num, er7_value in er7_fields.items():
                if er7_value == "":
                    continue

                xml_value = xml_fields.get(field_num)
                if xml_value is None:
                    missing_non_empty.append((segment_index + 1, er7_seg_name, field_num, er7_value))
                elif self._normalize_field_value(xml_value) != self._normalize_field_value(er7_value):
                    changed_non_empty.append((segment_index + 1, er7_seg_name, field_num, er7_value, xml_value))

        self.assertEqual(
            missing_non_empty,
            [],
            f"Non-empty fields missing in XML: {missing_non_empty}",
        )
        self.assertEqual(
            changed_non_empty,
            [],
            f"Non-empty fields changed in XML: {changed_non_empty}",
        )

        er7_pid3 = next((fields.get(3) for seg_name, fields in er7_segments if seg_name == "PID"), None)
        xml_pid3 = next((fields.get(3) for seg_name, fields in xml_segments if seg_name == "PID"), None)

        self.assertIsNotNone(er7_pid3, "ER7 message should contain PID.3")
        self.assertIsNotNone(xml_pid3, "Converted XML should contain PID.3")
        self.assertEqual(
            self._normalize_field_value(xml_pid3 or ""),
            self._normalize_field_value(er7_pid3 or ""),
            f"PID.3 should be preserved after conversion: ER7={er7_pid3!r}, XML={xml_pid3!r}",
        )

    def test_convert_er7_to_xml_no_non_empty_data_loss_for_phw(self) -> None:
        sample_path = self._sample_messages_dir() / "phw-to-mpi.sample.hl7"

        er7_message = sample_path.read_text(encoding="utf-8").strip()
        self._assert_no_non_empty_data_loss(er7_message)

    def test_convert_er7_to_xml_no_non_empty_data_loss_for_paris(self) -> None:
        sample_path = self._sample_messages_dir() / "paris-to-mpi.sample.hl7"

        er7_message = sample_path.read_text(encoding="utf-8").strip()
        self._assert_no_non_empty_data_loss(er7_message)

    def test_convert_er7_to_xml_no_non_empty_data_loss_for_chemocare_post_transformation(self) -> None:
        er7_message = (
            "MSH|^~\\&|212|212|200|200|20250701140735||ADT^A31^ADT_A05|201600952808665|P|2.5|||NE|NE\r"
            "EVN|Sub|20250701140735\r"
            "PID|1||1000000001^^^NHS^NH~BCUCC1000000001^^^212^PI||TEST^TEST^T^^Mrs.||20000101000000|"
            "F|||TEST,^TEST^TEST TEST^^CF11 9AD||01000 000 001|07000000001||||||||||||||||||0\r"
            "PD1||||G7000021\r"
            "PV1||U\r"
            "NK1||JONES^BARBARA|WIFE"
        )

        self._assert_no_non_empty_data_loss(er7_message)

    def test_convert_er7_to_xml_no_non_empty_data_loss_for_mpi_outbound_pharmacy(self) -> None:
        sample_path = self._sample_messages_dir() / "mpi-outbound-pharmacy.sample.hl7"
        er7_message = sample_path.read_text(encoding="utf-8").strip()

        self._assert_no_non_empty_data_loss(er7_message)

    def test_convert_er7_to_xml_no_non_empty_data_loss_for_pims_post_transformation(self) -> None:
        er7_message = (
            "MSH|^~\\&|103|103|200|200|20241231101053||ADT^A31^ADT_A05|48209024|P|2.5|||||GBR||EN\r"
            "EVN||20241231101035||||20241231101035\r"
            'PID|||N5022039^^^103^PI||TESTER^TEST^""^^MRS.||20000101|F|||'
            "MORRISTON HOSPITAL^HEOL MAES EGLWYS^CWMRHYDYCEIRW^SWANSEASWANSEA^SA6 6NL||"
            '01234567892~01234567896||||||||||||||||""\r'
            "PD1|||^^W98006|G9310201\r"
            "PV1||N"
        )

        self._assert_no_non_empty_data_loss(er7_message)

    def test_convert_er7_to_xml_preserves_literal_double_quotes_in_pid29(self) -> None:
        pid_fields = [""] * 30
        pid_fields[3] = "8888888^^^252^PI~4444444444^^^NHS^NH"
        pid_fields[5] = "MYSURNAME^MYFNAME^MYMNAME^^MR"
        pid_fields[7] = "19990101"
        pid_fields[8] = "M"
        pid_fields[11] = "99, MY ROAD^MY PLACE^MY CITY^MY COUNTY^SA99 1XX^^H"
        pid_fields[29] = '""'
        pid_segment = "PID|" + "|".join(pid_fields[1:30])

        er7_message = "\r".join(
            [
                "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:32||ADT^A31^ADT_A05|2025050523233644444|P|2.5|||||GBR||EN",
                "EVN||20250502092900|20250505232332|||20250505232332",
                pid_segment,
                "PD1|||^^W00000|G999999",
                "PV1||U",
            ]
        )

        self._assert_no_non_empty_data_loss(er7_message)

        normalized_er7 = "\r".join([line for line in er7_message.splitlines() if line.strip()])
        xml_string = convert_er7_to_xml(normalized_er7)
        er7_segments = self._parse_er7_segments(normalized_er7)
        xml_segments = self._parse_xml_segments(xml_string)

        self.assertEqual(self._get_field_value(er7_segments, "PID", 29), '""')
        self.assertEqual(self._get_field_value(xml_segments, "PID", 29), '""')

    def test_convert_er7_to_xml_specific_inline_message_with_invalid_encoding_chars_raises(self) -> None:
        er7_message = (
            # invalid encoding in MSH-1 (field separator) causes conversion to fail.
            "MSH|^\\&|103|103|200|200|20241231101053||ADT^A31^ADT_A05|48209024|P|2.5|||||GBR||EN\r"
            "EVN||20241231101035||||20241231101035\r"
        )

        with self.assertRaises(InvalidEncodingChars):
            convert_er7_to_xml(er7_message)

    def test_convert_er7_to_xml_no_non_empty_data_loss_for_chemocare(self) -> None:
        sample_path = self._sample_messages_dir() / "chemocare-to-mpi.sample.hl7"

        er7_message = sample_path.read_text(encoding="utf-8").strip()
        with self.assertRaises(ValueError):
            # Unable to determine structure (MSH-9.3) from ER7 message, so conversion fails.
            convert_er7_to_xml(er7_message)

    def test_assert_no_non_empty_data_loss_detects_missing_field(self) -> None:
        """
        This message uses HL7 v2.3.1 and includes MSH.21. In the current parser
        mapping path, MSH.21 is not preserved in XML, so data-loss detection
        should raise an assertion.
        """
        er7_message = (
            "MSH|^~\\&|103|103|200|200|20241231101053||ADT^A31^ADT_A05|48209024|P|2.3.1|||||GBR||EN||ITKv1.0\r"
            "EVN||20241231101035||||20241231101035\r"
            "PID|||N5022039^^^103^PI||TESTER^TEST\r"
            "PV1||N"
        )

        with self.assertRaises(AssertionError) as assertion_error:
            self._assert_no_non_empty_data_loss(er7_message)

        self.assertIn("Non-empty fields missing in XML", str(assertion_error.exception))

    def test_hl7_v24_detects_data_loss_when_multiple_fields_have_significant_whitespace(self) -> None:
        """
        The converter trims surrounding whitespace from field values.
        This payload intentionally carries leading/trailing spaces in multiple
        non-empty fields, so data-loss detection should fail with changed-field
        assertions.
        """
        er7_message = (
            "MSH|^~\\&|103|103|200|200|20241231101053||ADT^A31^ADT_A05| 48209024 |P|2.4|||||GBR||EN\r"
            "EVN||20241231101035||||20241231101035\r"
            'PID||| 000123^^^103^PI || TESTER ^ TEST ^""^^MRS. ||20000101|F|||'
            " 1 TEST STREET ^TEST^^TEST^CF11 9AD ||01234567892~01234567896\r"
            "PV1||N"
        )

        with self.assertRaises(AssertionError) as assertion_error:
            self._assert_no_non_empty_data_loss(er7_message)

        self.assertIn("Non-empty fields changed in XML", str(assertion_error.exception))


if __name__ == "__main__":
    unittest.main()
