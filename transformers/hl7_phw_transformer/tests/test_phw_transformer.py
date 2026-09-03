import unittest

from hl7apy.parser import parse_message

from hl7_phw_transformer.phw_transformer import PhwTransformer


class TestPhwTransformer(unittest.TestCase):
    def test_transform_message_segment_order(self) -> None:
        base_hl7_message = (
            "MSH|^~\\&|252|252|100|100|2025-05-05 23:23:28||ADT^A28^ADT_A05|"
            "202505052323326666666666|P|2.5|||||GBR||EN\r"
            "EVN||20250502102000|20250505232328|||20250505232328\r"
            "PID|||8888888^^^252^PI~6666666666^^^NHS^NH||"
            "MYSURNAME^MYFNAME^MYMNAME^^MR||19870101|M|^^||"
            "ADDRESS1^ADDRESS2^ADDRESS3^ADDRESS4^XX99 9XX^^H~^^^^^^||^^^~|||||||||||||||||||01\r"
            "PD1|||^^W99999^|G7777777\r"
            "PV1||U\r"
        )
        original_message = parse_message(base_hl7_message)
        transformer = PhwTransformer()

        new_message = transformer.transform_message(original_message)
        segments = [segment.name for segment in new_message.children]

        self.assertEqual(segments, ["MSH", "EVN", "PID", "PD1", "PV1"])


if __name__ == "__main__":
    unittest.main()
