import unittest
from unittest.mock import Mock, patch

from hl7apy.parser import parse_message

from hl7_pims_transformer.pims_transformer import transform_pims_message
from hl7_pims_transformer.utils.field_utils import get_hl7_field_value
from tests.pims_messages import pims_messages


class TestPimsTransformer(unittest.TestCase):
    def test_transform_pims_a08_message(self) -> None:
        original_message = parse_message(pims_messages["a08"])

        transformed_message = transform_pims_message(original_message)

        self.assertEqual(transformed_message.version, "2.5")

        segments_to_check = ["msh", "pid", "pd1", "pv1"]
        for segment in segments_to_check:
            self.assertTrue(hasattr(transformed_message, segment))

        self.assertEqual(transformed_message.msh.msh_9.value, "ADT^A31^ADT_A05")
        self.assertEqual(transformed_message.msh.msh_10.value, "48209024")
        self.assertEqual(transformed_message.msh.msh_11.value, "P")
        self.assertEqual(transformed_message.msh.msh_17.value, "GBR")
        self.assertEqual(transformed_message.msh.msh_19.ce_1.value, "EN")
        self.assertEqual(transformed_message.pid.pid_3[0].value, "")
        self.assertEqual(transformed_message.pid.pid_3[1].value, "N5022039^^^103^PI")
        # empty string should be preserved
        self.assertEqual(transformed_message.pid.pid_5.value, 'TESTER^TEST^""^^MRS.')
        self.assertEqual(transformed_message.pid.pid_8.value, "F")
        self.assertEqual(
            transformed_message.pid.pid_11.value,
            "MORRISTON HOSPITAL^HEOL MAES EGLWYS^CWMRHYDYCEIRW^SWANSEASWANSEA^SA6 6NL",
        )
        self.assertEqual(transformed_message.pid.pid_13[0].value, "01234567892")
        self.assertEqual(transformed_message.pid.pid_13[1].value, "01234567896")
        self.assertEqual(transformed_message.pid.pid_14.value, "")
        self.assertEqual(transformed_message.pid.pid_29.ts_1.value, '""')
        self.assertEqual(transformed_message.pid.pid_7.ts_1.value, "20000101")
        self.assertEqual(transformed_message.evn.evn_2.ts_1.value, "20241231101035")
        self.assertEqual(transformed_message.evn.evn_6.ts_1.value, "20241231101035")
        self.assertEqual(transformed_message.evn.value, "EVN||20241231101035||||20241231101035")
        self.assertEqual(transformed_message.pd1.pd1_3.xon_3.value, "W98006")
        self.assertEqual(transformed_message.pd1.pd1_4.xcn_1.value, "G9310201")
        self.assertEqual(transformed_message.pd1.value, "PD1|||^^W98006|G9310201")
        self.assertEqual(transformed_message.pv1.pv1_2.value, "N")
        self.assertEqual(transformed_message.pv1.value, "PV1||N")
        # MRG not present for A08
        self.assertEqual(transformed_message.mrg.value, "MRG")

    def test_transform_pims_a04_message(self) -> None:
        original_message = parse_message(pims_messages["a04"])

        transformed_message = transform_pims_message(original_message)

        self.assertEqual(transformed_message.version, "2.5")

        segments_to_check = ["msh", "pid", "pd1", "pv1"]
        for segment in segments_to_check:
            self.assertTrue(hasattr(transformed_message, segment))

        self.assertEqual(transformed_message.msh.msh_9.value, "ADT^A28^ADT_A05")
        self.assertEqual(transformed_message.msh.msh_10.value, "73726643")
        self.assertEqual(transformed_message.msh.msh_11.value, "P")
        self.assertEqual(transformed_message.msh.msh_17.value, "GBR")
        self.assertEqual(transformed_message.msh.msh_19.ce_1.value, "EN")
        self.assertEqual(transformed_message.pid.pid_3[0].value, "N4000000001^^^108^LI")
        self.assertEqual(transformed_message.pid.pid_3[1].value, "N1000001^^^103^PI")
        # empty string should be preserved
        self.assertEqual(transformed_message.pid.pid_5.value, 'TEST^TEST-TEST^""^^MISS')
        self.assertEqual(transformed_message.pid.pid_8.value, "F")
        self.assertEqual(transformed_message.pid.pid_11.value, '1 TEST^TEST^TEST^""^CF11 9AD')
        self.assertEqual(transformed_message.pid.pid_13[0].value, "07000000001")
        self.assertEqual(transformed_message.pid.pid_13[1].value, "07000000001")
        self.assertEqual(transformed_message.pid.pid_14.value, "07000000001")
        self.assertEqual(transformed_message.pid.pid_29.ts_1.value, '""')
        # EVN not present for A08
        self.assertEqual(transformed_message.evn.evn_1.value, "")
        self.assertEqual(transformed_message.evn.evn_2.ts_1.value, "20250702085440")
        self.assertEqual(transformed_message.evn.evn_6.ts_1.value, "20250702085450")
        self.assertEqual(transformed_message.pd1.pd1_3.xon_3.value, "W90001")
        self.assertEqual(transformed_message.pd1.pd1_4.xcn_1.value, "G7000001")
        self.assertEqual(transformed_message.pd1.value, "PD1|||^^W90001|G7000001")
        self.assertEqual(transformed_message.pv1.pv1_2.value, "N")
        self.assertEqual(transformed_message.pv1.value, "PV1||N")
        # MRG not present for A08
        self.assertEqual(transformed_message.mrg.value, "MRG")

    def test_transform_pims_a40_message(self) -> None:
        original_message = parse_message(pims_messages["a40"])

        transformed_message = transform_pims_message(original_message)

        self.assertEqual(transformed_message.version, "2.5")

        segments_to_check = ["msh", "pid", "mrg"]
        for segment in segments_to_check:
            self.assertTrue(hasattr(transformed_message, segment))

        self.assertEqual(transformed_message.msh.msh_9.msg_1.value, "ADT")
        self.assertEqual(transformed_message.msh.msh_10.value, "73711860")
        self.assertEqual(transformed_message.msh.msh_11.value, "P")
        self.assertEqual(transformed_message.msh.msh_17.value, "GBR")
        self.assertEqual(transformed_message.msh.msh_19.ce_1.value, "EN")
        self.assertEqual(transformed_message.pid.pid_5.value, "TEST^TEST^TEST^^MS.")
        self.assertEqual(transformed_message.pid.pid_8.value, "F")
        self.assertEqual(
            transformed_message.pid.pid_11.value,
            "1, TEST^TEST TEST^TEST^TEST^CF11 9AD",
        )
        self.assertEqual(transformed_message.pid.pid_13[0].value, "07000000001 TEST PTNR")
        self.assertEqual(transformed_message.pid.pid_13[1].value, "07000000001 PT")
        self.assertEqual(transformed_message.pid.pid_14.value, "50500 02920")
        self.assertEqual(transformed_message.pid.pid_29.ts_1.value, '""')
        self.assertEqual(transformed_message.pid.pid_7.ts_1.value, "20000101")
        self.assertEqual(transformed_message.evn.evn_2.ts_1.value, "20250630155034")
        self.assertEqual(transformed_message.evn.evn_6.ts_1.value, "20250630155034")
        self.assertEqual(transformed_message.evn.value, "EVN||20250630155034||||20250630155034")

        # PD1 not present for A40
        self.assertEqual(transformed_message.pd1.pd1_3.xon_3.value, "")
        self.assertEqual(transformed_message.pd1.pd1_4.xcn_1.value, "")
        self.assertEqual(transformed_message.pd1.value, "PD1")
        # PV1 not present for A40
        self.assertEqual(transformed_message.pv1.pv1_2.value, "")
        self.assertEqual(transformed_message.pv1.value, "PV1")
        self.assertEqual(transformed_message.mrg.mrg_1.cx_1.value, "00100001")
        self.assertEqual(get_hl7_field_value(transformed_message.mrg, "mrg_1.cx_4.hd_1"), "103")
        self.assertEqual(transformed_message.mrg.mrg_1.cx_5.value, "PI")

    @patch("hl7_pims_transformer.pims_transformer.map_msh")
    @patch("hl7_pims_transformer.pims_transformer.map_pid")
    @patch("hl7_pims_transformer.pims_transformer.map_evn")
    @patch("hl7_pims_transformer.pims_transformer.map_pd1")
    @patch("hl7_pims_transformer.pims_transformer.map_pv1")
    @patch("hl7_pims_transformer.pims_transformer.map_mrg")
    @patch("hl7_pims_transformer.pims_transformer.map_non_specific_segments")
    def test_all_mapper_functions_called(
        self,
        mock_map_evn: Mock,
        mock_map_msh: Mock,
        mock_map_pid: Mock,
        mock_map_pd1: Mock,
        mock_map_pv1: Mock,
        mock_map_mrg: Mock,
        mock_map_non_specific: Mock,
    ) -> None:
        original_message = parse_message(pims_messages["a04"])

        transformed_message = transform_pims_message(original_message)

        mock_map_msh.assert_called_once_with(original_message, transformed_message)
        mock_map_pid.assert_called_once_with(original_message, transformed_message)
        mock_map_evn.assert_called_once_with(original_message, transformed_message)
        mock_map_pd1.assert_called_once_with(original_message, transformed_message)
        mock_map_pv1.assert_called_once_with(original_message, transformed_message)
        mock_map_mrg.assert_called_once_with(original_message, transformed_message)
        mock_map_non_specific.assert_called_once_with(original_message, transformed_message)
