import unittest

from hl7apy.parser import parse_message

from hl7_wds_transformer.wds_transformer import WdsTransformer
from tests.wds_messages import WDS_A08_DISALLOWED, WDS_A28, WDS_A31


class TestWdsTransformer(unittest.TestCase):
    def setUp(self) -> None:
        self.transformer = WdsTransformer()

    def test_a28_message_is_passed_through(self) -> None:
        msg = parse_message(WDS_A28)
        result = self.transformer.transform_message(msg)
        self.assertEqual(result.msh.msh_9.msh_9_2.value, "A28")

    def test_a31_message_is_passed_through(self) -> None:
        msg = parse_message(WDS_A31)
        result = self.transformer.transform_message(msg)
        self.assertEqual(result.msh.msh_9.msh_9_2.value, "A31")

    def test_disallowed_trigger_event_raises_value_error(self) -> None:
        msg = parse_message(WDS_A08_DISALLOWED)
        with self.assertRaises(ValueError) as ctx:
            self.transformer.transform_message(msg)
        self.assertIn("A08", str(ctx.exception))
        self.assertIn("dead-lettered", str(ctx.exception))

    def test_transformer_name(self) -> None:
        self.assertEqual(self.transformer.transformer_name, "WDS")
