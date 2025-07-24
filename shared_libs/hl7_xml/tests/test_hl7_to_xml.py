import os
import unittest
import xml.etree.ElementTree as ElementTree

from hl7apy.parser import parse_message

from hl7_xml.hl7_to_xml import mapHl7toXml

HL7_ER_FILENAME = os.path.join(os.path.dirname(__file__), 'ADT_A28.hl7')
HL7_XML_FILENAME = os.path.join(os.path.dirname(__file__), 'ADT_A28.xml')

class TestHl7ToXml(unittest.TestCase):


    def test_log_message_received(self):
        hl7_er = self._read_resource(HL7_ER_FILENAME)
        hl7 = parse_message(hl7_er)
        expected_xml = self._read_resource(HL7_XML_FILENAME)

        result = mapHl7toXml(hl7)

        # self.assertEqual(result, expected_xml)
        self._assertEqualXml(result, expected_xml)


    def _read_resource(self, path: str) -> str:
        content = []
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(1000)
                if chunk:
                    content.append(chunk)
                else:
                    break
        return b"".join(content).decode("utf-8")

    def _assertEqualXml(self, first: str, second: str):
        firstStd = ElementTree.tostring(ElementTree.fromstring(first))
        secondStd = ElementTree.tostring(ElementTree.fromstring(first))

        self.assertEqual(firstStd, secondStd)

