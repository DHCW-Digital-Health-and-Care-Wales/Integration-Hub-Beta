"""Tests for CoreReferenceTransformer — message-type filter and WRDSService wiring."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from hl7apy.parser import parse_message

from hl7_core_reference_transformer.app_config import WRDSConfig
from hl7_core_reference_transformer.core_reference_transformer import CoreReferenceTransformer
from tests.messages import A04_NOT_IN_SCOPE, A28_ALL_FIELDS_POPULATED

_WRDS_CONFIG = WRDSConfig(
    endpoint_url="https://example.test/wrdssoapservice",
    timeout_seconds=30,
    client_cert_path=None,
    lookup_table_name="FioranoCodeTranslation",
)


class TestCoreReferenceTransformer(unittest.TestCase):
    @patch("hl7_core_reference_transformer.core_reference_transformer.WRDSService")
    def test_in_scope_message_delegates_to_mapper(self, mock_wrds_service_cls: MagicMock) -> None:
        transformer = CoreReferenceTransformer(wrds_config=_WRDS_CONFIG)
        message = parse_message(A28_ALL_FIELDS_POPULATED)

        with patch(
            "hl7_core_reference_transformer.core_reference_transformer.apply_core_reference_mapping"
        ) as mock_apply:
            mock_apply.return_value = message

            result = transformer.transform_message(message)

            mock_apply.assert_called_once_with(message, transformer._wrds_service, "FioranoCodeTranslation")
            self.assertIs(result, message)

    @patch("hl7_core_reference_transformer.core_reference_transformer.WRDSService")
    def test_out_of_scope_message_passes_through_unchanged(self, mock_wrds_service_cls: MagicMock) -> None:
        transformer = CoreReferenceTransformer(wrds_config=_WRDS_CONFIG)
        message = parse_message(A04_NOT_IN_SCOPE)

        with patch(
            "hl7_core_reference_transformer.core_reference_transformer.apply_core_reference_mapping"
        ) as mock_apply:
            result = transformer.transform_message(message)

            mock_apply.assert_not_called()
            self.assertIs(result, message)

    @patch("hl7_core_reference_transformer.core_reference_transformer.WRDSService")
    def test_wrds_service_constructed_from_config(self, mock_wrds_service_cls: MagicMock) -> None:
        CoreReferenceTransformer(wrds_config=_WRDS_CONFIG)

        mock_wrds_service_cls.assert_called_once_with(
            endpoint_url="https://example.test/wrdssoapservice",
            timeout_seconds=30,
            client_cert_path=None,
            fixture_file_path=None,
        )

    @patch("hl7_core_reference_transformer.core_reference_transformer.WRDSService")
    def test_transformer_name_is_core_reference(self, mock_wrds_service_cls: MagicMock) -> None:
        transformer = CoreReferenceTransformer(wrds_config=_WRDS_CONFIG)

        self.assertEqual(transformer.transformer_name, "CoreReference")


if __name__ == "__main__":
    unittest.main()
