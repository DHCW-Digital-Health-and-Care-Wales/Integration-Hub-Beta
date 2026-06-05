import os
import unittest
from unittest.mock import patch

from replay_browser.config import ConfigError, load_config


class TestConfig(unittest.TestCase):
    def test_load_config_defaults(self) -> None:
        with patch.dict(os.environ, {"MSSQL_SA_PASSWORD": "secret"}, clear=True):
            config = load_config()

        self.assertEqual(config.sql_server, "localhost,1433")
        self.assertEqual(config.sql_database, "IntegrationHub")
        self.assertEqual(config.sql_username, "sa")
        self.assertEqual(config.sql_password, "secret")
        self.assertEqual(config.page_size, 30)

    def test_load_config_rejects_partial_auth(self) -> None:
        with patch.dict(os.environ, {"SQL_USERNAME": "sa"}, clear=True):
            with self.assertRaises(ConfigError):
                load_config()

    def test_load_config_rejects_invalid_page_size(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SQL_USERNAME": "sa",
                "MSSQL_SA_PASSWORD": "secret",
                "MESSAGE_BROWSER_PAGE_SIZE": "invalid",
            },
            clear=True,
        ):
            with self.assertRaises(ConfigError):
                load_config()


if __name__ == "__main__":
    unittest.main()
