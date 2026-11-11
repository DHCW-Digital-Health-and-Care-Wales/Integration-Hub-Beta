import unittest

from db_sender.parsers.hl7_id_extractor import (
    extract_mrg_identifiers,
    extract_pid_identifier_by_authority,
    get_trigger_event,
)

SAMPLE_A31_ER7 = (
    "MSH|^~\\&|328|LIMS|WRRS|DHCW|20260101120000||ADT^A31^ADT_A05|MSG0001|P|2.5\r"
    "EVN||20260101120000\r"
    "PID|1||9876543210^^^NHS^NH~L12345^^^328^PI||SMITH^JOHN||19800101|M\r"
    "PV1|1|N"
)

SAMPLE_A31_COMPACTED_ER7 = (
    "MSH|^~\\&|328|LIMS|WRRS|DHCW|20260101120000||ADT^A31^ADT_A05|MSG0001|P|2.5\r"
    "EVN||20260101120000\r"
    "PID|1||9876543210^NHS^NH~L12345^328^PI||SMITH^JOHN||19800101|M\r"
    "PV1|1|N"
)

SAMPLE_A40_ER7 = (
    "MSH|^~\\&|328|LIMS|WRRS|DHCW|20260101120000||ADT^A40^ADT_A39|MSG0002|P|2.5\r"
    "EVN||20260101120000\r"
    "PID|1||SURVIVOR123^^^328^PI||SMITH^JOHN||19800101|M\r"
    "MRG|OLD999^^^328^PI\r"
    "PV1|1|N"
)

SAMPLE_A40_COMPACTED_ER7 = (
    "MSH|^~\\&|328|LIMS|WRRS|DHCW|20260101120000||ADT^A40^ADT_A39|MSG0002|P|2.5\r"
    "EVN||20260101120000\r"
    "PID|1||SURVIVOR123^328^PI||SMITH^JOHN||19800101|M\r"
    "MRG|OLD999^328^PI\r"
    "PV1|1|N"
)

SAMPLE_A31_XML = (
    "<ns0:ADT_A05 xmlns:ns0=\"urn:hl7-org:v2xml\">"
    "<ns0:MSH><ns0:MSH.1>|</ns0:MSH.1><ns0:MSH.2>^~\\&amp;</ns0:MSH.2>"
    "<ns0:MSH.3><ns0:HD.1>328</ns0:HD.1></ns0:MSH.3>"
    "<ns0:MSH.9><ns0:MSG.1>ADT</ns0:MSG.1><ns0:MSG.2>A31</ns0:MSG.2><ns0:MSG.3>ADT_A05</ns0:MSG.3></ns0:MSH.9>"
    "<ns0:MSH.10>MSG-XML-A31</ns0:MSH.10></ns0:MSH>"
    "<ns0:PID>"
    "<ns0:PID.3><ns0:CX.1>9876543210</ns0:CX.1><ns0:CX.4><ns0:HD.1>NHS</ns0:HD.1></ns0:CX.4></ns0:PID.3>"
    "<ns0:PID.3><ns0:CX.1>L12345</ns0:CX.1><ns0:CX.4><ns0:HD.1>328</ns0:HD.1></ns0:CX.4></ns0:PID.3>"
    "</ns0:PID></ns0:ADT_A05>"
)

SAMPLE_A40_XML = (
    "<ns0:ADT_A39 xmlns:ns0=\"urn:hl7-org:v2xml\">"
    "<ns0:MSH><ns0:MSH.1>|</ns0:MSH.1><ns0:MSH.2>^~\\&amp;</ns0:MSH.2>"
    "<ns0:MSH.3><ns0:HD.1>328</ns0:HD.1></ns0:MSH.3>"
    "<ns0:MSH.9><ns0:MSG.1>ADT</ns0:MSG.1><ns0:MSG.2>A40</ns0:MSG.2><ns0:MSG.3>ADT_A39</ns0:MSG.3></ns0:MSH.9>"
    "<ns0:MSH.10>MSG-XML-A40</ns0:MSH.10></ns0:MSH>"
    "<ns0:ADT_A39.PATIENT>"
    "<ns0:PID><ns0:PID.3><ns0:CX.1>NEW-SURVIVOR</ns0:CX.1><ns0:CX.4><ns0:HD.1>328</ns0:HD.1></ns0:CX.4></ns0:PID.3></ns0:PID>"
    "<ns0:MRG><ns0:MRG.1><ns0:CX.1>OLD-MERGED</ns0:CX.1><ns0:CX.4><ns0:HD.1>328</ns0:HD.1></ns0:CX.4></ns0:MRG.1></ns0:MRG>"
    "</ns0:ADT_A39.PATIENT></ns0:ADT_A39>"
)


class TestHl7IdExtractor(unittest.TestCase):

    def test_get_trigger_event_er7(self) -> None:
        self.assertEqual(get_trigger_event(SAMPLE_A31_ER7), "A31")
        self.assertEqual(get_trigger_event(SAMPLE_A40_ER7), "A40")

    def test_get_trigger_event_xml(self) -> None:
        self.assertEqual(get_trigger_event(SAMPLE_A31_XML), "A31")
        self.assertEqual(get_trigger_event(SAMPLE_A40_XML), "A40")

    def test_extract_mrg_identifiers_er7_standard(self) -> None:
        old_id, old_auth = extract_mrg_identifiers(SAMPLE_A40_ER7)
        self.assertEqual(old_id, "OLD999")
        self.assertEqual(old_auth, "328")

    def test_extract_mrg_identifiers_er7_compacted(self) -> None:
        old_id, old_auth = extract_mrg_identifiers(SAMPLE_A40_COMPACTED_ER7)
        self.assertEqual(old_id, "OLD999")
        self.assertEqual(old_auth, "328")

    def test_extract_mrg_identifiers_xml(self) -> None:
        old_id, old_auth = extract_mrg_identifiers(SAMPLE_A40_XML)
        self.assertEqual(old_id, "OLD-MERGED")
        self.assertEqual(old_auth, "328")

    def test_extract_mrg_identifiers_missing_mrg(self) -> None:
        old_id, old_auth = extract_mrg_identifiers(SAMPLE_A31_ER7)
        self.assertIsNone(old_id)
        self.assertIsNone(old_auth)

    def test_extract_mrg_identifiers_empty_input(self) -> None:
        old_id, old_auth = extract_mrg_identifiers("")
        self.assertIsNone(old_id)
        self.assertIsNone(old_auth)

    def test_extract_pid_by_authority_er7_standard(self) -> None:
        nhs_id = extract_pid_identifier_by_authority(SAMPLE_A31_ER7, "NHS")
        lims_id = extract_pid_identifier_by_authority(SAMPLE_A31_ER7, "328")
        missing_id = extract_pid_identifier_by_authority(SAMPLE_A31_ER7, "NONEXISTENT")

        self.assertEqual(nhs_id, "9876543210")
        self.assertEqual(lims_id, "L12345")
        self.assertIsNone(missing_id)

    def test_extract_pid_by_authority_er7_compacted(self) -> None:
        nhs_id = extract_pid_identifier_by_authority(SAMPLE_A31_COMPACTED_ER7, "NHS")
        lims_id = extract_pid_identifier_by_authority(SAMPLE_A31_COMPACTED_ER7, "328")

        self.assertEqual(nhs_id, "9876543210")
        self.assertEqual(lims_id, "L12345")

    def test_extract_pid_by_authority_xml(self) -> None:
        nhs_id = extract_pid_identifier_by_authority(SAMPLE_A31_XML, "NHS")
        lims_id = extract_pid_identifier_by_authority(SAMPLE_A31_XML, "328")
        survivor_id = extract_pid_identifier_by_authority(SAMPLE_A40_XML, "328")

        self.assertEqual(nhs_id, "9876543210")
        self.assertEqual(lims_id, "L12345")
        self.assertEqual(survivor_id, "NEW-SURVIVOR")

    def test_extract_pid_by_authority_case_insensitive(self) -> None:
        nhs_id = extract_pid_identifier_by_authority(SAMPLE_A31_ER7, "nhs")
        self.assertEqual(nhs_id, "9876543210")

    def test_extract_pid_by_authority_empty_input(self) -> None:
        self.assertIsNone(extract_pid_identifier_by_authority("", "NHS"))
        self.assertIsNone(extract_pid_identifier_by_authority(SAMPLE_A31_ER7, ""))

    def test_extract_pid_standard_cx_does_not_match_other_components(self) -> None:
        msg = "MSH|^~\\&|SEND|FAC|||20260101||ADT^A31||P|2.5\rPID|||WRONG^^^999^PI^328~RIGHT^^^328^PI"
        self.assertEqual(extract_pid_identifier_by_authority(msg, "328"), "RIGHT")
        self.assertEqual(extract_pid_identifier_by_authority(msg, "999"), "WRONG")

    def test_extract_mrg_standard_cx_does_not_treat_type_as_authority(self) -> None:
        msg = "MSH|^~\\&|SEND|FAC|||20260101||ADT^A40||P|2.5\rMRG|OLD^^^^PI"
        old_id, old_auth = extract_mrg_identifiers(msg)
        self.assertEqual(old_id, "OLD")
        self.assertIsNone(old_auth)

    def test_extract_mrg_er7_compacted_layouts(self) -> None:
        msg_2comp = "MSH|^~\\&|SEND|FAC|||20260101||ADT^A40||P|2.5\rMRG|OLD^PAS"
        self.assertEqual(extract_mrg_identifiers(msg_2comp), ("OLD", "PAS"))

        msg_3comp = "MSH|^~\\&|SEND|FAC|||20260101||ADT^A40||P|2.5\rMRG|OLD^PAS^PI"
        self.assertEqual(extract_mrg_identifiers(msg_3comp), ("OLD", "PAS"))

    def test_extract_mrg_repetitions(self) -> None:
        msg = "MSH|^~\\&|SEND|FAC|||20260101||ADT^A40||P|2.5\rMRG|FIRST^^^AUTH1~SECOND^^^AUTH2"
        self.assertEqual(extract_mrg_identifiers(msg), ("FIRST", "AUTH1"))

    def test_extract_pid_xml_ignores_assigning_facility_hd1(self) -> None:
        xml_msg = """<?xml version="1.0" encoding="UTF-8"?>
        <ADT_A31 xmlns="urn:hl7-org:v2xml">
            <PID>
                <PID.3>
                    <CX.1>WRONG_PATIENT</CX.1>
                    <CX.4><HD.1>999</HD.1></CX.4>
                    <CX.6><HD.1>328</HD.1></CX.6>
                </PID.3>
                <PID.3>
                    <CX.1>CORRECT_PATIENT</CX.1>
                    <CX.4><HD.1>328</HD.1></CX.4>
                </PID.3>
            </PID>
        </ADT_A31>"""
        self.assertEqual(extract_pid_identifier_by_authority(xml_msg, "328"), "CORRECT_PATIENT")
        self.assertEqual(extract_pid_identifier_by_authority(xml_msg, "999"), "WRONG_PATIENT")


if __name__ == "__main__":
    unittest.main()
