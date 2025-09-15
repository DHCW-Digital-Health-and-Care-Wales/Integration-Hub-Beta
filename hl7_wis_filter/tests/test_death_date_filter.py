import unittest
from typing import Optional
from unittest.mock import Mock

from hl7apy.core import Field, Message

from hl7_wis_filter.death_date_filter import DeathDateFilter, DeathDateFilterResult


class TestDeathDateFilterResult(unittest.TestCase):

    def test_init_with_minimal_parameters(self) -> None:
        result = DeathDateFilterResult(should_forward=True, reason="Test reason")

        self.assertTrue(result.should_forward)
        self.assertEqual(result.reason, "Test reason")
        self.assertIsNone(result.pid_29_ts1_value)
        self.assertIsNone(result.pid_30_value)

    def test_init_with_all_parameters(self) -> None:
        result = DeathDateFilterResult(
            should_forward=False,
            reason="Test reason",
            pid_29_ts1_value="20230115094530",
            pid_30_value="Y"
        )

        self.assertFalse(result.should_forward)
        self.assertEqual(result.reason, "Test reason")
        self.assertEqual(result.pid_29_ts1_value, "20230115094530")
        self.assertEqual(result.pid_30_value, "Y")


class TestDeathDateFilter(unittest.TestCase):

    def setUp(self) -> None:
        self.filter = DeathDateFilter()

    def _create_mock_message(self, message_type: str = "ADT^A28",
                           pid_29_has_ts1: bool = False,
                           pid_29_ts1_value: Optional[str] = None,
                           pid_30_value: Optional[str] = None,
                           has_pid_segment: bool = True) -> Mock:
        mock_message = Mock(spec=Message)
        mock_msh = Mock()
        mock_msh.msh_9.to_er7.return_value = message_type
        mock_message.msh = mock_msh

        if has_pid_segment:
            mock_pid = Mock()

            # Mock PID.29 (Date/Time of Death)
            if pid_29_has_ts1 and pid_29_ts1_value is not None:
                mock_pid_29 = Mock(spec=Field)
                mock_pid_29.ts_1 = Mock()
                mock_pid_29.ts_1.value = pid_29_ts1_value
                mock_pid.pid_29 = mock_pid_29
            elif pid_29_has_ts1:
                # PID.29 has TS.1 component but no value
                mock_pid_29 = Mock(spec=Field)
                mock_pid_29.ts_1 = Mock()
                mock_pid_29.ts_1.value = None
                mock_pid.pid_29 = mock_pid_29
            else:
                # No TS.1 component or no PID.29 field
                if pid_29_ts1_value is not None:
                    # PID.29 exists but without TS.1 component
                    mock_pid_29 = Mock(spec=Field)
                    mock_pid_29.value = pid_29_ts1_value
                    # Remove ts_1 attribute to simulate missing component
                    if hasattr(mock_pid_29, 'ts_1'):
                        delattr(mock_pid_29, 'ts_1')
                    mock_pid.pid_29 = mock_pid_29
                else:
                    mock_pid.pid_29 = None

            # Mock PID.30 (Death Indicator)
            if pid_30_value is not None:
                mock_pid_30 = Mock(spec=Field)
                mock_pid_30.value = pid_30_value
                mock_pid.pid_30 = mock_pid_30
            else:
                mock_pid.pid_30 = None

            mock_message.pid = mock_pid
        else:
            mock_message.pid = None

        return mock_message

    def test_init(self) -> None:
        filter_instance = DeathDateFilter()
        expected_types = {"ADT^A28", "ADT^A31"}
        self.assertEqual(filter_instance.accepted_message_types, expected_types)

    def test_should_forward_message_with_unsupported_message_type(self) -> None:
        mock_message = self._create_mock_message(message_type="ADT^A01")

        result = self.filter.should_forward_message(mock_message)

        self.assertFalse(result.should_forward)
        self.assertIn("Unsupported message type: ADT^A01", result.reason)

    def test_should_forward_message_without_pid_segment(self) -> None:
        mock_message = self._create_mock_message(has_pid_segment=False)

        result = self.filter.should_forward_message(mock_message)

        self.assertFalse(result.should_forward)
        self.assertEqual(result.reason, "No PID segment found in message")

    def test_should_forward_message_with_pid_29_ts1_populated(self) -> None:
        mock_message = self._create_mock_message(
            message_type="ADT^A28",
            pid_29_has_ts1=True,
            pid_29_ts1_value="20230115094530"
        )

        result = self.filter.should_forward_message(mock_message)

        self.assertTrue(result.should_forward)
        self.assertIn("PID.29.TS.1 (Date/Time of Death timestamp) populated", result.reason)
        self.assertEqual(result.pid_29_ts1_value, "20230115094530")
        self.assertIsNone(result.pid_30_value)

    def test_should_forward_message_with_pid_30_populated(self) -> None:
        mock_message = self._create_mock_message(
            message_type="ADT^A31",
            pid_30_value="Y"
        )

        result = self.filter.should_forward_message(mock_message)

        self.assertTrue(result.should_forward)
        self.assertIn("PID.30 (Death Indicator) populated", result.reason)
        self.assertIsNone(result.pid_29_ts1_value)
        self.assertEqual(result.pid_30_value, "Y")

    def test_should_forward_message_with_both_pid_fields_populated(self) -> None:
        mock_message = self._create_mock_message(
            message_type="ADT^A28",
            pid_29_has_ts1=True,
            pid_29_ts1_value="20230115094530",
            pid_30_value="Y"
        )

        result = self.filter.should_forward_message(mock_message)

        self.assertTrue(result.should_forward)
        self.assertIn("PID.29.TS.1 (Date/Time of Death timestamp) populated", result.reason)
        self.assertIn("PID.30 (Death Indicator) populated", result.reason)
        self.assertEqual(result.pid_29_ts1_value, "20230115094530")
        self.assertEqual(result.pid_30_value, "Y")

    def test_should_not_forward_message_with_empty_pid_fields(self) -> None:
        mock_message = self._create_mock_message(message_type="ADT^A28")

        result = self.filter.should_forward_message(mock_message)

        self.assertFalse(result.should_forward)
        self.assertIn("Neither PID.29.TS.1 nor PID.30 are populated", result.reason)
        self.assertIsNone(result.pid_29_ts1_value)
        self.assertIsNone(result.pid_30_value)

    def test_should_not_forward_message_with_pid_29_without_ts1(self) -> None:
        mock_message = self._create_mock_message(
            message_type="ADT^A28",
            pid_29_has_ts1=False,
            pid_29_ts1_value="20230115094530"  # Simulates PID.29 without TS.1
        )

        result = self.filter.should_forward_message(mock_message)

        self.assertFalse(result.should_forward)
        self.assertIn("Neither PID.29.TS.1 nor PID.30 are populated", result.reason)
        self.assertIsNone(result.pid_29_ts1_value)

    def test_should_not_forward_message_with_whitespace_only_values(self) -> None:
        mock_message = self._create_mock_message(
            message_type="ADT^A28",
            pid_29_has_ts1=True,
            pid_29_ts1_value="   ",
            pid_30_value=" "
        )

        result = self.filter.should_forward_message(mock_message)

        self.assertFalse(result.should_forward)
        self.assertIn("Neither PID.29.TS.1 nor PID.30 are populated", result.reason)

    def test_should_forward_message_with_pid_29_ts1_edge_case_values(self) -> None:
        test_cases = [
            "0",  # Single digit
            "20230101000000",  # Midnight
            "99991231235959",  # Year 9999
        ]

        for test_value in test_cases:
            with self.subTest(pid_29_ts1_value=test_value):
                mock_message = self._create_mock_message(
                    message_type="ADT^A28",
                    pid_29_has_ts1=True,
                    pid_29_ts1_value=test_value
                )

                result = self.filter.should_forward_message(mock_message)

                self.assertTrue(result.should_forward)
                self.assertEqual(result.pid_29_ts1_value, test_value)

    def test_is_supported_message_type(self) -> None:
        # Test supported types
        self.assertTrue(self.filter._is_supported_message_type("ADT^A28"))
        self.assertTrue(self.filter._is_supported_message_type("ADT^A31"))

        # Test unsupported types
        self.assertFalse(self.filter._is_supported_message_type("ADT^A01"))
        self.assertFalse(self.filter._is_supported_message_type("ORU^R01"))
        self.assertFalse(self.filter._is_supported_message_type(""))

    def test_extract_field_value_with_field_object(self) -> None:
        mock_field = Mock()
        mock_field.value = "test_value"

        result = self.filter._extract_field_value(mock_field)

        self.assertEqual(result, "test_value")

    def test_extract_field_value_with_string(self) -> None:
        result = self.filter._extract_field_value("test_string")

        self.assertEqual(result, "test_string")

    def test_extract_field_value_with_none(self) -> None:
        result = self.filter._extract_field_value(None)

        self.assertIsNone(result)

    def test_is_field_populated_with_valid_and_empty_values(self) -> None:
        test_cases = [
            ("valid_value", True),
            ("Y", True),
            ("20230115094530", True),
            ("0", True),
            ("   valid   ", True),
            (None, False),
            ("", False),
            ("   ", False),
            ("\t\n", False),
        ]

        for test_value, expected in test_cases:
            with self.subTest(value=test_value):
                result = self.filter._is_field_populated(test_value)
                self.assertEqual(result, expected)

    def test_extract_pid_29_ts1_value_with_valid_timestamp_field(self) -> None:
        mock_pid_segment = Mock()
        mock_pid_29 = Mock(spec=Field)
        mock_pid_29.ts_1 = Mock()
        mock_pid_29.ts_1.value = "20230115094530"
        mock_pid_segment.pid_29 = mock_pid_29

        result = self.filter._extract_pid_29_ts1_value(mock_pid_segment)

        self.assertEqual(result, "20230115094530")

    def test_extract_pid_29_ts1_value_without_ts1_component(self) -> None:
        mock_pid_segment = Mock()
        mock_pid_29 = Mock(spec=Field)
        mock_pid_29.value = "20230115094530"
        # Simulate missing ts_1 attribute
        if hasattr(mock_pid_29, 'ts_1'):
            delattr(mock_pid_29, 'ts_1')
        mock_pid_segment.pid_29 = mock_pid_29

        result = self.filter._extract_pid_29_ts1_value(mock_pid_segment)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
