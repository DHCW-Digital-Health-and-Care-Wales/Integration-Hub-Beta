import unittest

from field_utils_lib import get_hl7_field_value
from hl7apy.core import Message
from hl7apy.parser import parse_message

from training_hl7_transformer.mappers.pid_mapper import map_pid


class TestPIDMapper(unittest.TestCase):


    def setUp(self) -> None:
        self.hl7_message = (
            "MSH|^~\\&|169|FAC|RECV|RECV_FAC|20260122143055||ADT^A31|MSG001|P|2.3.1\r"
            "PID|||12345678^^^HOSPITAL^MRN||Smith^John^William^^Mr||19850315|M|||"
            "123 Main Street^^Cardiff^Wales^CF10 1AA^^H\r"
        )
        self.original_message = parse_message(self.hl7_message)
        self.new_message = Message(version="2.3.1")


    def test_map_pid_all_direct_mappings(self) -> None:
        map_pid(self.original_message, self.new_message)

        test_cases = [
            "pid_3", "pid_5", "pid_7", "pid_8"
        ]

        for field_path in test_cases:
            # PID-5 (Patient Name) should be uppercased in the new message, while other fields should be copied as-is
            if field_path == "pid_5":
                self.assertEqual(
                    get_hl7_field_value(self.original_message.pid, field_path).upper(),
                    get_hl7_field_value(self.new_message.pid, field_path),
                )
            else:
                self.assertEqual(
                    get_hl7_field_value(self.original_message.pid, field_path),
                    get_hl7_field_value(self.new_message.pid, field_path),
                )

    def test_map_pid_copies_patient_id(self) -> None:
        """
        Test that PID-3 (Patient Identifier List) is copied correctly.
        """
        # Act
        map_pid(self.original_message, self.new_message)

        # Assert
        original_pid3 = get_hl7_field_value(self.original_message.pid, "pid_3")
        new_pid3 = get_hl7_field_value(self.new_message.pid, "pid_3")
        self.assertEqual(original_pid3, new_pid3)


    def test_map_pid_returns_transformation_details(self) -> None:
            """
            Test that map_pid returns a dictionary with transformation details.
            """
            # Act
            result = map_pid(self.original_message, self.new_message)

            # Assert
            self.assertIsInstance(result, dict)
            self.assertIn("pid_5.xpn_1.fn_1", result if result is not None else {})
            self.assertIn("pid_5.xpn_2", result if result is not None else {})
            self.assertIn("pid_5.xpn_3", result if result is not None else {})
            self.assertIn("pid_5.xpn_4", result if result is not None else {})
            self.assertIn("pid_5.xpn_5", result if result is not None else {})
            # Expecting exactly 5 entries for the name transformation details
            self.assertEqual(len(result if result is not None else {}), 5)
