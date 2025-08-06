import unittest
from unittest.mock import Mock, patch

from hl7apy.parser import parse_message

from hl7_pims_transformer.pims_transformer import transform_pims_message
from tests.pims_messages import pims_messages


class TestPimsTransformer(unittest.TestCase):
    def test_transform_pims_message(self) -> None:
        original_message = parse_message(pims_messages["a08"])

        transformed_message = transform_pims_message(original_message)

        self.assertEqual(transformed_message.version, "2.5")

        segments_to_check = ["msh", "evn", "pid"]
        for segment in segments_to_check:
            self.assertTrue(hasattr(transformed_message, segment))

        self.assertEqual(transformed_message.msh.msh_9.msg_1.value, "ADT")
        self.assertEqual(transformed_message.msh.msh_10.value, "48209024")
        self.assertEqual(transformed_message.msh.msh_11.value, "P")
        self.assertEqual(transformed_message.msh.msh_17.value, "GBR")
        self.assertEqual(transformed_message.msh.msh_19.ce_1.value, "EN")
        self.assertEqual(transformed_message.pid.pid_5.value, 'TESTER^TEST^""^^MRS.')
        self.assertEqual(transformed_message.pid.pid_8.value, "F")
        self.assertEqual(
            transformed_message.pid.pid_11.value,
            "MORRISTON HOSPITAL^HEOL MAES EGLWYS^CWMRHYDYCEIRW^SWANSEASWANSEA^SA6 6NL",
        )
        self.assertEqual(transformed_message.pid.pid_13[0].value, "01234567892")
        self.assertEqual(transformed_message.pid.pid_13[1].value, "01234567896")
        self.assertEqual(transformed_message.pid.pid_14.value, "")
        self.assertEqual(transformed_message.evn.evn_1.value, "")
        self.assertEqual(transformed_message.evn.value, "EVN")

    @patch("hl7_pims_transformer.pims_transformer.map_msh")
    @patch("hl7_pims_transformer.pims_transformer.map_pid")
    @patch("hl7_pims_transformer.pims_transformer.map_evn")
    @patch("hl7_pims_transformer.pims_transformer.map_non_specific_segments")
    def test_all_mapper_functions_called(
        self,
        mock_map_evn: Mock,
        mock_map_msh: Mock,
        mock_map_pid: Mock,
        mock_map_non_specific: Mock,
    ) -> None:
        original_message = parse_message(pims_messages["a04"])

        transformed_message = transform_pims_message(original_message)

        mock_map_msh.assert_called_once_with(original_message, transformed_message)
        mock_map_pid.assert_called_once_with(original_message, transformed_message)
        mock_map_evn.assert_called_once_with(original_message, transformed_message)
        mock_map_non_specific.assert_called_once_with(original_message, transformed_message)
