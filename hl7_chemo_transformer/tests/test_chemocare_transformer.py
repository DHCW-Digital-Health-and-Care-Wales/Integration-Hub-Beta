import unittest
from unittest.mock import Mock, patch

from chemo_messages import chemo_messages
from hl7apy.parser import parse_message

from hl7_chemo_transformer.chemocare_transformer import transform_chemocare_message


class TestChemocareTransformer(unittest.TestCase):
    def test_transform_a28_southwest_message(self) -> None:
        original_message = parse_message(chemo_messages["a28_southwest"])

        transformed_message = transform_chemocare_message(original_message)

        self.assertEqual(transformed_message.version, "2.5")

        segments_to_check = ["msh", "evn", "pid", "pd1", "pv1"]
        for segment in segments_to_check:
            self.assertTrue(hasattr(transformed_message, segment))

        # Check key message transformations and required fields are mapped correctly
        self.assertEqual(transformed_message.msh.msh_7.value, "20250701154910")
        self.assertEqual(transformed_message.msh.msh_9.value, "ADT^A28^ADT_A05")
        self.assertEqual(transformed_message.msh.msh_10.value, "474997159036153")
        self.assertEqual(transformed_message.msh.msh_11.value, "P")
        self.assertEqual(transformed_message.pid.pid_3[0].value, "1000000001^^^NHS^NH")
        self.assertEqual(transformed_message.pid.pid_3[1].value, "SWWCC1000000001^^^192^PI")
        self.assertEqual(transformed_message.pid.pid_5.value, "TEST^TEST^TEST^^Mr.")
        self.assertEqual(transformed_message.evn.value, "EVN|Sub|20250701154910")
        self.assertEqual(transformed_message.pd1.value, "PD1||||G7000001")
        self.assertEqual(transformed_message.pv1.value, "PV1||U")

    def test_transform_a31_bcu_message(self) -> None:
        original_message = parse_message(chemo_messages["a31_bcu"])

        transformed_message = transform_chemocare_message(original_message)

        self.assertEqual(transformed_message.version, "2.5")

        segments_to_check = ["msh", "evn", "pid", "pd1", "pv1", "nk1"]
        for segment in segments_to_check:
            self.assertTrue(hasattr(transformed_message, segment))

        # Check key message transformations and required fields are mapped correctly
        self.assertEqual(transformed_message.msh.msh_7.value, "20250701140735")
        self.assertEqual(transformed_message.msh.msh_9.value, "ADT^A31^ADT_A05")
        self.assertEqual(transformed_message.msh.msh_10.value, "201600952808665")
        self.assertEqual(transformed_message.msh.msh_11.value, "P")
        self.assertEqual(transformed_message.pid.pid_3[0].value, "1000000001^^^NHS^NH")
        self.assertEqual(transformed_message.pid.pid_3[1].value, "BCUCC1000000001^^^212^PI")
        self.assertEqual(transformed_message.pid.pid_5.value, "TEST^TEST^T^^Mrs.")
        self.assertEqual(transformed_message.evn.value, "EVN|Sub|20250701140735")
        self.assertEqual(transformed_message.pd1.value, "PD1||||G7000021")
        self.assertEqual(transformed_message.pv1.value, "PV1||U")
        self.assertEqual(transformed_message.nk1.value, "NK1||JONES^BARBARA|WIFE")

    @patch("hl7_chemo_transformer.chemocare_transformer.map_msh")
    @patch("hl7_chemo_transformer.chemocare_transformer.map_evn")
    @patch("hl7_chemo_transformer.chemocare_transformer.map_pid")
    @patch("hl7_chemo_transformer.chemocare_transformer.map_pd1")
    @patch("hl7_chemo_transformer.chemocare_transformer.map_nk1")
    @patch("hl7_chemo_transformer.chemocare_transformer.map_non_specific_segments")
    def test_all_mapper_functions_called(
        self,
        mock_map_non_specific: Mock,
        mock_map_nk1: Mock,
        mock_map_pd1: Mock,
        mock_map_pid: Mock,
        mock_map_evn: Mock,
        mock_map_msh: Mock,
    ) -> None:
        original_message = parse_message(chemo_messages["a28_southwest"])

        transformed_message = transform_chemocare_message(original_message)

        mock_map_msh.assert_called_once_with(original_message, transformed_message)
        mock_map_evn.assert_called_once_with(original_message, transformed_message)
        mock_map_pid.assert_called_once_with(original_message, transformed_message)
        mock_map_pd1.assert_called_once_with(original_message, transformed_message)
        mock_map_nk1.assert_called_once_with(original_message, transformed_message)
        mock_map_non_specific.assert_called_once_with(original_message, transformed_message)


if __name__ == "__main__":
    unittest.main()
