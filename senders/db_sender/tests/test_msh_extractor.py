import unittest

from db_sender.msh_extractor import extract_msh_for_logging


class TestMshExtractor(unittest.TestCase):
    def test_extract_msh_xml_adt_a39(self) -> None:
        xml_payload = """
        <ADT_A39 xmlns="urn:hl7-org:v2xml">
            <MSH>
                <MSH.1>|</MSH.1>
                <MSH.2>^~\\&amp;</MSH.2>
                <MSH.3><HD.1>349</HD.1></MSH.3>
                <MSH.9>
                    <MSG.1>ADT</MSG.1>
                    <MSG.2>A40</MSG.2>
                    <MSG.3>ADT_A39</MSG.3>
                </MSH.9>
                <MSH.10><MSH.10.1>MSG-XML-100492</MSH.10.1></MSH.10>
            </MSH>
            <PID>
                <PID.3><CX.1>9876543210</CX.1></PID.3>
                <PID.5><XPN.1><FN.1>SECRET_PATIENT_NAME</FN.1></XPN.1></PID.5>
            </PID>
            <MRG>
                <MRG.1><CX.1>1234567890</CX.1></MRG.1>
            </MRG>
        </ADT_A39>
        """
        result = extract_msh_for_logging(xml_payload)

        self.assertEqual(result.control_id, "MSG-XML-100492")
        self.assertEqual(result.message_type, "ADT^A40^ADT_A39")
        self.assertIn("MSH", result.msh_text)
        # CRITICAL Information Governance check: patient identifiable data is NEVER present
        self.assertNotIn("SECRET_PATIENT_NAME", result.msh_text)
        self.assertNotIn("9876543210", result.msh_text)
        self.assertNotIn("PID", result.msh_text)
        self.assertNotIn("MRG", result.msh_text)

    def test_extract_msh_xml_oru_r01(self) -> None:
        xml_payload = """
        <ORU_R01>
            <MSH>
                <MSH.9><MSG.1>ORU</MSG.1><MSG.2>R01</MSG.2><MSG.3>ORU_R01</MSG.3></MSH.9>
                <MSH.10><MSH.10.1>MSG-ORU-777</MSH.10.1></MSH.10>
            </MSH>
            <PATIENT_RESULT>
                <PATIENT>
                    <PID><PID.5>CONFIDENTIAL_DIAGNOSIS</PID.5></PID>
                </PATIENT>
                <ORDER_OBSERVATION>
                    <OBR><OBR.4>XRAY CHEST</OBR.4></OBR>
                </ORDER_OBSERVATION>
            </PATIENT_RESULT>
        </ORU_R01>
        """
        result = extract_msh_for_logging(xml_payload)
        self.assertEqual(result.control_id, "MSG-ORU-777")
        self.assertEqual(result.message_type, "ORU^R01^ORU_R01")
        self.assertNotIn("CONFIDENTIAL_DIAGNOSIS", result.msh_text)
        self.assertNotIn("OBR", result.msh_text)

    def test_extract_msh_xml_omg_o19(self) -> None:
        xml_payload = """
        <OMG_O19>
            <MSH>
                <MSH.9><MSG.1>OMG</MSG.1><MSG.2>O19</MSG.2><MSG.3>OMG_O19</MSG.3></MSH.9>
                <MSH.10><MSH.10.1>MSG-OMG-888</MSH.10.1></MSH.10>
            </MSH>
            <PID><PID.5>SENSITIVE_DATA</PID.5></PID>
        </OMG_O19>
        """
        result = extract_msh_for_logging(xml_payload)
        self.assertEqual(result.control_id, "MSG-OMG-888")
        self.assertEqual(result.message_type, "OMG^O19^OMG_O19")
        self.assertNotIn("SENSITIVE_DATA", result.msh_text)
        self.assertNotIn("PID", result.msh_text)

    def test_extract_msh_er7(self) -> None:
        er7_payload = (
            "MSH|^~\\&|349|349|WRRS|DHCW|20261022143000||ADT^A40^ADT_A39|MSG-ER7-999|P|2.5.1\r"
            "PID|1||9999999999^^^NHS||SURNAME^FORENAME||19800101|M|||123 HIGH STREET\r"
            "MRG|1111111111"
        )
        result = extract_msh_for_logging(er7_payload)
        self.assertEqual(result.control_id, "MSG-ER7-999")
        self.assertEqual(result.message_type, "ADT^A40^ADT_A39")
        self.assertTrue(result.msh_text.startswith("MSH|^~\\&"))
        # Verify no PID data leaked
        self.assertNotIn("SURNAME", result.msh_text)
        self.assertNotIn("9999999999", result.msh_text)
        self.assertNotIn("HIGH STREET", result.msh_text)

    def test_extract_msh_empty(self) -> None:
        result = extract_msh_for_logging("")
        self.assertEqual(result.control_id, "UNKNOWN")
        self.assertEqual(result.msh_text, "[Empty message body]")

    def test_extract_msh_no_msh_found(self) -> None:
        result = extract_msh_for_logging("FOO|BAR|BAZ\rQUX|1|2|3")
        self.assertEqual(result.control_id, "UNKNOWN")
        self.assertEqual(result.msh_text, "[No MSH segment identified]")


if __name__ == "__main__":
    unittest.main()
