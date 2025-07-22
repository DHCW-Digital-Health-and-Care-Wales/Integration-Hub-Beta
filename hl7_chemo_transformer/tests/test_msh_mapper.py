import unittest
from unittest.mock import MagicMock, patch

from hl7apy.core import Message
from hl7apy.parser import parse_message

from hl7_chemo_transformer.mappers.msh_mapper import map_msh
from hl7_chemo_transformer.utils.field_utils import get_hl7_field_value


class TestMSHMapper(unittest.TestCase):
    def setUp(self) -> None:
        self.msh_header = "MSH|^~\\&|192|192|200|200|20250701154910||ADT^A28|474997159036153|P|2.4|||NE|NE\r"
        self.original_message = parse_message(self.msh_header)

        self.new_message = Message(version="2.5")

    def test_map_msh_basic_fields(self) -> None:
        map_msh(self.original_message, self.new_message)

        self.assertEqual(
            get_hl7_field_value(self.original_message.msh, "msh_1"),
            get_hl7_field_value(self.new_message.msh, "msh_1"),
        )
        self.assertEqual(
            get_hl7_field_value(self.original_message.msh, "msh_2"),
            get_hl7_field_value(self.new_message.msh, "msh_2"),
        )

    def test_map_msh_nested_fields(self) -> None:
        map_msh(self.original_message, self.new_message)

        self.assertEqual(
            get_hl7_field_value(self.original_message.msh, "msh_3.hd_1"),
            get_hl7_field_value(self.new_message.msh, "msh_3.hd_1"),
        )

    def test_map_msh_message_type(self) -> None:
        map_msh(self.original_message, self.new_message)

        self.assertEqual(
            get_hl7_field_value(self.original_message.msh, "msh_9.msg_1"),
            get_hl7_field_value(self.new_message.msh, "msh_9.msg_1"),
        )
        self.assertEqual(
            get_hl7_field_value(self.original_message.msh, "msh_9.msg_2"),
            get_hl7_field_value(self.new_message.msh, "msh_9.msg_2"),
        )
        self.assertEqual(
            "ADT_A05",
            get_hl7_field_value(self.new_message.msh, "msh_9.msg_3"),
        )
        self.assertEqual("ADT^A28^ADT_A05", get_hl7_field_value(self.new_message.msh, "msh_9"))

    def test_map_msh_version_id(self) -> None:
        map_msh(self.original_message, self.new_message)

        self.assertEqual("2.5", get_hl7_field_value(self.new_message.msh, "msh_12.vid_1"))

    @patch("hl7_chemo_transformer.mappers.msh_mapper.set_nested_field")
    def test_map_msh_calls_set_nested_field(self, mock_set_nested_field: MagicMock) -> None:
        map_msh(self.original_message, self.new_message)

        # Verify that set_nested_field was called with the expected parameters
        mock_set_nested_field.assert_any_call(self.original_message.msh, self.new_message.msh, "msh_3", "hd_1")
        mock_set_nested_field.assert_any_call(self.original_message.msh, self.new_message.msh, "msh_9", "msg_1")


if __name__ == "__main__":
    unittest.main()
