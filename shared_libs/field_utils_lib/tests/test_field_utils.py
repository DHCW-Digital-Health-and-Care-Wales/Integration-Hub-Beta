import unittest
from unittest.mock import MagicMock

from field_utils_lib.field_utils import get_hl7_field_value, set_nested_field, copy_segment_fields_in_range


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
    def test_copy_segment_fields_in_range_single_field(self):
        source_segment = MagicMock()
        target_segment = MagicMock()
        
        source_field = MagicMock()
        source_field.value = "test_value"
        source_segment.msh_3 = source_field
        
        copy_segment_fields_in_range(source_segment, target_segment, "msh", start=3, end=3)
        
        self.assertEqual(target_segment.msh_3, source_field)

    def test_copy_segment_fields_in_range_multiple_fields(self):
        source_segment = MagicMock()
        target_segment = MagicMock()
        
        for i in range(3, 6):
            field = MagicMock()
            field.value = f"value_{i}"
            setattr(source_segment, f"msh_{i}", field)
        
        copy_segment_fields_in_range(source_segment, target_segment, "msh", start=3, end=5)
        
        for i in range(3, 6):
            self.assertEqual(getattr(target_segment, f"msh_{i}"), getattr(source_segment, f"msh_{i}"))

    def test_copy_segment_fields_in_range_inclusive_end(self):
        source_segment = MagicMock()
        target_segment = MagicMock()
        
        for i in range(1, 40):
            field = MagicMock()
            field.value = f"pid_{i}"
            setattr(source_segment, f"pid_{i}", field)
        
        copy_segment_fields_in_range(source_segment, target_segment, "pid", start=1, end=39)
        
        self.assertEqual(getattr(target_segment, "pid_1"), getattr(source_segment, "pid_1"))
        self.assertEqual(getattr(target_segment, "pid_39"), getattr(source_segment, "pid_39"))

    def test_copy_segment_fields_in_range_skips_missing_fields(self):
        source_segment = MagicMock()
        target_segment = MagicMock()
        
        source_field = MagicMock()
        source_field.value = "value_3"
        source_segment.msh_3 = source_field
        
        del source_segment.msh_4
        del source_segment.msh_5
        
        copy_segment_fields_in_range(source_segment, target_segment, "msh", start=3, end=5)
        
        self.assertEqual(target_segment.msh_3, source_field)

    def test_copy_segment_fields_in_range_large_range(self):
        source_segment = MagicMock()
        target_segment = MagicMock()
        
        # Setup source fields
        for i in range(1, 40):
            field = MagicMock()
            field.value = f"pid_{i}"
            setattr(source_segment, f"pid_{i}", field)
        
        copy_segment_fields_in_range(source_segment, target_segment, "pid", start=1, end=39)
        
        for i in range(1, 40):
            self.assertEqual(getattr(target_segment, f"pid_{i}"), getattr(source_segment, f"pid_{i}"))

    def test_copy_segment_fields_in_range_msh_13_to_21(self):
        source_segment = MagicMock()
        target_segment = MagicMock()
        
        for i in range(13, 22):
            field = MagicMock()
            field.value = f"msh_{i}"
            setattr(source_segment, f"msh_{i}", field)
        
        copy_segment_fields_in_range(source_segment, target_segment, "msh", start=13, end=21)
        
        for i in range(13, 22):
            self.assertEqual(getattr(target_segment, f"msh_{i}"), getattr(source_segment, f"msh_{i}"))


if __name__ == '__main__':
    unittest.main()
