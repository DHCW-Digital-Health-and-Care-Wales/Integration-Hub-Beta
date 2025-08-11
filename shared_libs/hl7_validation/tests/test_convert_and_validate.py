import unittest

from hl7_validation.convert import er7_to_xml


class TestConvert(unittest.TestCase):
    def test_er7_to_xml_basic(self) -> None:
        er7 = "MSH|^~\\&|SND|FAC|RCV|FAC|20250101010101||ADT^A28|MSGID|P|2.5\rPID|1||12345^^^HOSP^MR||Doe^John||19800101|M\r"
        xml_str = er7_to_xml(er7)
        self.assertIn("<MSH>", xml_str)
        self.assertIn("<PID>", xml_str)


if __name__ == "__main__":
    unittest.main()


