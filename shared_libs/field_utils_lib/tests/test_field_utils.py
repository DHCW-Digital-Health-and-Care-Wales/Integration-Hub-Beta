import unittest
from unittest.mock import MagicMock

from hl7apy.core import Message
from hl7apy.parser import parse_message

from field_utils_lib.field_utils import (
    copy_segment_fields_in_range,
    get_hl7_field_value,
    set_nested_field,
)


class TestGetHl7FieldValue(unittest.TestCase):
    def test_get_hl7_field_value_simple_path(self):
        mock_segment = MagicMock()
        mock_field = MagicMock()
        mock_field.value = "test_value"
        mock_segment.msh_3 = mock_field
        
        result = get_hl7_field_value(mock_segment, "msh_3")
        
        self.assertEqual(result, "test_value")

    def test_get_hl7_field_value_nested_path(self):
        mock_segment = MagicMock()
        mock_field = MagicMock()
        mock_subfield = MagicMock()
        mock_subfield.value = "nested_value"
        mock_field.hd_1 = mock_subfield
        mock_segment.msh_4 = mock_field
        
        result = get_hl7_field_value(mock_segment, "msh_4.hd_1")
        
        self.assertEqual(result, "nested_value")

    def test_get_hl7_field_value_missing_field_returns_empty_string(self):
        mock_segment = MagicMock()
        del mock_segment.nonexistent
        
        result = get_hl7_field_value(mock_segment, "nonexistent")
        
        self.assertEqual(result, "")

    def test_get_hl7_field_value_with_bracket_notation(self):
        mock_segment = MagicMock()
        mock_field_array = [MagicMock(), MagicMock()]
        mock_field_array[1].value = "indexed_value"
        mock_segment.pid_13 = mock_field_array
        
        result = get_hl7_field_value(mock_segment, "pid_13[1]")
        
        self.assertEqual(result, "indexed_value")

    def test_get_hl7_field_value_with_empty_value(self):
        mock_segment = MagicMock()
        mock_field = MagicMock()
        mock_field.value = None
        mock_segment.empty_field = mock_field
        
        result = get_hl7_field_value(mock_segment, "empty_field")
        
        self.assertEqual(result, "")


class TestSetNestedField(unittest.TestCase):
    def test_set_nested_field_simple_copy(self):
        source_obj = MagicMock()
        target_obj = MagicMock()
        source_field = MagicMock()
        source_field.value = "source_value"
        source_obj.test_field = source_field
        
        result = set_nested_field(source_obj, target_obj, "test_field")
        
        self.assertTrue(result)
        self.assertEqual(target_obj.test_field, source_field)

    def test_set_nested_field_nested_path(self):
        source_obj = MagicMock()
        target_obj = MagicMock()
        source_parent = MagicMock()
        target_parent = MagicMock()
        source_field = MagicMock()
        source_field.value = "nested_value"
        
        source_parent.child_field = source_field
        source_obj.parent_field = source_parent
        target_obj.parent_field = target_parent
        
        result = set_nested_field(source_obj, target_obj, "parent_field.child_field")
        
        self.assertTrue(result)
        self.assertEqual(target_parent.child_field, source_field)

    def test_set_nested_field_missing_source_field(self):
        source_obj = MagicMock()
        target_obj = MagicMock()
        del source_obj.missing_field
        
        result = set_nested_field(source_obj, target_obj, "missing_field")
        
        self.assertFalse(result)

    def test_set_nested_field_empty_source_value(self):
        source_obj = MagicMock()
        target_obj = MagicMock()
        source_field = MagicMock()
        source_field.value = ""
        source_obj.empty_field = source_field
        
        result = set_nested_field(source_obj, target_obj, "empty_field")
        
        self.assertFalse(result)

    def test_set_nested_field_with_none_value(self):
        source_obj = MagicMock()
        target_obj = MagicMock()
        source_field = MagicMock()
        source_field.value = None
        source_obj.none_field = source_field
        
        result = set_nested_field(source_obj, target_obj, "none_field")
        
        self.assertFalse(result)


class TestCopySegmentFieldsInRange(unittest.TestCase):
    def setUp(self) -> None:
        self.hl7_message = (
            "MSH|^~\\&|SEND_APP|SEND_FAC|REC_APP|REC_FAC|20250505||ADT^A31^ADT_A05|"
            "MSG123|P|2.5|||||GBR|8859/1|EN\r"
            "PID|||8888^^^252^PI~4444^^^NHS^NH||SURNAME^FNAME^MNAME^^MR||"
            "19990101|M|^^||99 ROAD^PLACE^CITY^COUNTY^SA99 1XX^^H"
            "~SECOND1^SECOND2^SECOND3^SECOND4^SB99 9SB^^H||"
            "^^^home~^^^work||||||||||||||||2024-12-31|||01\r"
        )
        self.original_message = parse_message(self.hl7_message)

    def test_copy_single_field(self) -> None:
        new_msg = Message(version="2.5")
        new_pid = new_msg.add_segment("PID")

        copy_segment_fields_in_range(self.original_message.pid, new_pid, "pid", start=7, end=7)

        self.assertEqual(
            get_hl7_field_value(new_pid, "pid_7"),
            get_hl7_field_value(self.original_message.pid, "pid_7"),
        )

    def test_copy_multiple_fields(self) -> None:
        new_msg = Message(version="2.5")
        new_pid = new_msg.add_segment("PID")

        copy_segment_fields_in_range(self.original_message.pid, new_pid, "pid", start=7, end=9)

        for i in range(7, 10):
            self.assertEqual(
                get_hl7_field_value(new_pid, f"pid_{i}"),
                get_hl7_field_value(self.original_message.pid, f"pid_{i}"),
                f"PID.{i} mismatch",
            )

    def test_copy_inclusive_end(self) -> None:
        new_msg = Message(version="2.5")
        new_pid = new_msg.add_segment("PID")

        copy_segment_fields_in_range(self.original_message.pid, new_pid, "pid", start=1, end=39)

        # Verify both start and end are included
        self.assertEqual(
            get_hl7_field_value(new_pid, "pid_1"),
            get_hl7_field_value(self.original_message.pid, "pid_1"),
        )
        self.assertEqual(
            get_hl7_field_value(new_pid, "pid_39"),
            get_hl7_field_value(self.original_message.pid, "pid_39"),
        )

    def test_copy_skips_empty_fields(self) -> None:
        """Fields with no data should not cause errors."""
        new_msg = Message(version="2.5")
        new_pid = new_msg.add_segment("PID")

        # PID.4, PID.9, PID.10 are empty in our test message
        copy_segment_fields_in_range(self.original_message.pid, new_pid, "pid", start=1, end=10)

        # Non-empty fields should be copied
        self.assertEqual(
            get_hl7_field_value(new_pid, "pid_5"),
            get_hl7_field_value(self.original_message.pid, "pid_5"),
        )

    def test_copy_large_range(self) -> None:
        new_msg = Message(version="2.5")
        new_pid = new_msg.add_segment("PID")

        copy_segment_fields_in_range(self.original_message.pid, new_pid, "pid", start=1, end=39)

        for i in range(1, 40):
            self.assertEqual(
                get_hl7_field_value(new_pid, f"pid_{i}"),
                get_hl7_field_value(self.original_message.pid, f"pid_{i}"),
                f"PID.{i} mismatch",
            )

    def test_copy_msh_fields(self) -> None:
        new_msg = Message(version="2.5")

        copy_segment_fields_in_range(self.original_message.msh, new_msg.msh, "msh", start=3, end=21)

        for i in range(3, 22):
            self.assertEqual(
                get_hl7_field_value(new_msg.msh, f"msh_{i}"),
                get_hl7_field_value(self.original_message.msh, f"msh_{i}"),
                f"MSH.{i} mismatch",
            )

    def test_copy_preserves_pid_3_repetitions(self) -> None:
        """PID.3 (Patient Identifier List) commonly has multiple repetitions."""
        new_msg = Message(version="2.5")
        new_pid = new_msg.add_segment("PID")
        original_pid = self.original_message.pid

        copy_segment_fields_in_range(original_pid, new_pid, "pid", start=3, end=3)

        self.assertEqual(len(original_pid.pid_3), 2)
        self.assertEqual(len(new_pid.pid_3), len(original_pid.pid_3))
        for i in range(len(original_pid.pid_3)):
            self.assertEqual(
                original_pid.pid_3[i].value,
                new_pid.pid_3[i].value,
                f"PID.3 repetition {i} mismatch",
            )

    def test_copy_preserves_pid_11_repetitions(self) -> None:
        """PID.11 (Patient Address) commonly has multiple repetitions."""
        new_msg = Message(version="2.5")
        new_pid = new_msg.add_segment("PID")
        original_pid = self.original_message.pid

        copy_segment_fields_in_range(original_pid, new_pid, "pid", start=11, end=11)

        self.assertEqual(len(original_pid.pid_11), 2)
        self.assertEqual(len(new_pid.pid_11), len(original_pid.pid_11))
        for i in range(len(original_pid.pid_11)):
            self.assertEqual(
                original_pid.pid_11[i].value,
                new_pid.pid_11[i].value,
                f"PID.11 repetition {i} mismatch",
            )

    def test_copy_preserves_pid_13_repetitions(self) -> None:
        """PID.13 (Phone Number Home) commonly has multiple repetitions."""
        new_msg = Message(version="2.5")
        new_pid = new_msg.add_segment("PID")
        original_pid = self.original_message.pid

        copy_segment_fields_in_range(original_pid, new_pid, "pid", start=13, end=13)

        self.assertEqual(len(original_pid.pid_13), 2)
        self.assertEqual(len(new_pid.pid_13), len(original_pid.pid_13))
        for i in range(len(original_pid.pid_13)):
            self.assertEqual(
                original_pid.pid_13[i].value,
                new_pid.pid_13[i].value,
                f"PID.13 repetition {i} mismatch",
            )

    def test_copy_range_with_mix_of_single_and_repeating_fields(self) -> None:
        """A range containing both single-value and repeating fields should handle all correctly."""
        new_msg = Message(version="2.5")
        new_pid = new_msg.add_segment("PID")
        original_pid = self.original_message.pid

        # PID.1-13 includes single fields (pid_7, pid_8) and repeating fields (pid_3, pid_11, pid_13)
        copy_segment_fields_in_range(original_pid, new_pid, "pid", start=1, end=13)

        # Check single-value fields
        self.assertEqual(
            get_hl7_field_value(new_pid, "pid_7"),
            get_hl7_field_value(original_pid, "pid_7"),
        )
        self.assertEqual(
            get_hl7_field_value(new_pid, "pid_8"),
            get_hl7_field_value(original_pid, "pid_8"),
        )

        # Check repeating fields
        self.assertEqual(len(new_pid.pid_3), len(original_pid.pid_3))
        self.assertEqual(len(new_pid.pid_11), len(original_pid.pid_11))
        self.assertEqual(len(new_pid.pid_13), len(original_pid.pid_13))


if __name__ == '__main__':
    unittest.main()
