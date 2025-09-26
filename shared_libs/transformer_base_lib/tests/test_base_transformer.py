import unittest
from unittest.mock import MagicMock

from transformer_base_lib.base_transformer import BaseTransformer


class TestTransformer(BaseTransformer):
    def transform_message(self, hl7_msg):
        return hl7_msg


class TestBaseTransformer(unittest.TestCase):
    def test_base_transformer_initialization(self):
        transformer = TestTransformer("test_transformer", "/custom/config/path")
        
        self.assertEqual(transformer.transformer_name, "test_transformer")
        self.assertEqual(transformer.config_path, "/custom/config/path")

    def test_base_transformer_default_config_path(self):
        transformer = TestTransformer("test_transformer")
        
        self.assertEqual(transformer.transformer_name, "test_transformer")
        self.assertTrue(transformer.config_path.endswith("config.ini"))

    def test_get_sending_app_with_unknown_app(self):
        transformer = TestTransformer("test_transformer")
        mock_message = MagicMock()

        mock_value = MagicMock()
        mock_value.value.side_effect = AttributeError()
        mock_message.msh.msh_3.msh_3_1 = mock_value

        result = transformer._get_sending_app(mock_message)

        self.assertEqual(result, "UNKNOWN")

if __name__ == '__main__':
    unittest.main()
