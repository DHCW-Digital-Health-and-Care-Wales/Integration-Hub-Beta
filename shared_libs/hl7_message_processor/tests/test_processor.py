import unittest

from hl7_message_processor.exceptions import MessageNotProcessableError
from hl7_message_processor.processor import ProcessedMessage, process_er7


class ProcessEr7WithExplicitStructureTests(unittest.TestCase):
    def test_msh_9_3_present_resolves_directly(self) -> None:
        er7 = (
            "MSH|^~\\&|SENDAPP|SENDFAC|RECAPP|RECFAC|20241230133601||ADT^A40^ADT_A39|MSG00001|P|2.5.1\r"
            "EVN|A40|20241230133601\r"
            "PID|1||123456^^^MRN^MR||DOE^JOHN\r"
            "MRG|987654^^^MRN^MR"
        )
        result = process_er7(er7)

        self.assertIsInstance(result, ProcessedMessage)
        self.assertEqual(result.structure_id, "ADT_A39")
        self.assertEqual(result.version, "2.5.1")
        self.assertTrue(str(result.xsd_path).endswith("2_5_1_ADT_A39.xsd"))
        self.assertIn("ADT_A39.PATIENT", result.xml)


class ProcessEr7WithTriggerAliasTests(unittest.TestCase):
    def test_msh_9_3_absent_resolves_via_trigger_table(self) -> None:
        er7 = (
            "MSH|^~\\&|A|A|B|B|20241230133601||ADT^A28|MSG002|P|2.5.1\r"
            "EVN|A28|20241230133601\r"
            "PID|1||123456^^^MRN^MR||DOE^JOHN\r"
            "PV1|1|I"
        )
        result = process_er7(er7)

        self.assertEqual(result.structure_id, "ADT_A05")
        self.assertEqual(result.version, "2.5.1")


class ProcessEr7FailureTests(unittest.TestCase):
    def test_missing_version_is_not_processable(self) -> None:
        er7 = "MSH|^~\\&|A|A|B|B|20241230133601||ADT^A28|MSG002|P\rEVN|A28\rPID|1\rPV1|1"
        with self.assertRaises(MessageNotProcessableError):
            process_er7(er7)

    def test_unresolvable_structure_is_not_processable(self) -> None:
        er7 = "MSH|^~\\&|A|A|B|B|20241230133601||ZZZ^Z99|MSG002|P|2.5.1\rZZZ|1"
        with self.assertRaises(MessageNotProcessableError):
            process_er7(er7)

    def test_message_not_fitting_grammar_is_not_processable(self) -> None:
        # ADT_A05 requires EVN and PV1 - both are missing here.
        er7 = "MSH|^~\\&|A|A|B|B|20241230133601||ADT^A28^ADT_A05|MSG002|P|2.5.1\rPID|1"
        with self.assertRaises(MessageNotProcessableError):
            process_er7(er7)


if __name__ == "__main__":
    unittest.main()
