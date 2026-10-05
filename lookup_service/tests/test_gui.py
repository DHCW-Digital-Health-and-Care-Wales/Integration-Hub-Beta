from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from lookup_service.app import create_app
from lookup_service.store.file_store import FileTableStore
from tests.helpers import REPO_SEED_DIR, SeedDirTestCase, make_settings


class OverviewPageTests(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app(make_settings(), FileTableStore.load(REPO_SEED_DIR)))

    def test_lists_tables(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("health_board_mapping", response.text)
        self.assertIn("ward_map", response.text)
        self.assertIn('name="key.sending_facility"', response.text)

    def test_sets_security_headers(self) -> None:
        response = self.client.get("/")
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_lookup_tester_shows_result(self) -> None:
        response = self.client.get("/", params={"table": "ward_map", "key.sending_facility": "fac1",
                                                "key.ward_code": "w1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("7A1-W001", response.text)
        self.assertIn("FAC1 :: W1", response.text)

    def test_lookup_tester_shows_error(self) -> None:
        response = self.client.get("/", params={"table": "health_board_mapping", "key.msh3": "000"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("key_not_found", response.text)

    def test_lookup_tester_unknown_table(self) -> None:
        response = self.client.get("/", params={"table": "nope", "key.a": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("table_not_found", response.text)

    def test_static_css_served(self) -> None:
        response = self.client.get("/static/css/lookup.css")
        self.assertEqual(response.status_code, 200)
        self.assertIn("#325083", response.text)


class OverviewEscapingTests(SeedDirTestCase):
    def test_values_and_table_names_are_html_escaped(self) -> None:
        self.write_csv("codes", 'code,label\nA,"<script>alert(1)</script>"\n')
        client = TestClient(create_app(make_settings(self.seed_dir), FileTableStore.load(self.seed_dir)))

        response = client.get("/", params={"table": "codes", "key.code": "A"})
        self.assertNotIn("<script>alert(1)</script>", response.text)
        self.assertIn("&lt;script&gt;", response.text)

        response = client.get("/", params={"table": "<b>x</b>", "key.code": "A"})
        self.assertNotIn("<b>x</b>", response.text)

    def test_empty_state(self) -> None:
        client = TestClient(create_app(make_settings(self.seed_dir), FileTableStore.load(self.seed_dir)))
        self.assertIn("No tables loaded", client.get("/").text)


if __name__ == "__main__":
    unittest.main()
