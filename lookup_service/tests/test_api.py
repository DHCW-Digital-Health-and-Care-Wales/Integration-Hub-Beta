from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from lookup_service.app import create_app
from lookup_service.store.file_store import FileTableStore
from tests.helpers import REPO_SEED_DIR, make_settings


class LookupApiTests(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(create_app(make_settings(), FileTableStore.load(REPO_SEED_DIR)))

    def test_single_key_lookup(self) -> None:
        response = self.client.get("/api/v1/lookup/health_board_mapping", params={"k": "224"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "table": "health_board_mapping",
                "key": ["224"],
                "value": "VCC",
                "values": {"health_board": "VCC"},
                "source": "file",
                "cached": True,
            },
        )

    def test_composite_key_positional(self) -> None:
        response = self.client.get("/api/v1/lookup/ward_map?k=FAC1&k=W2")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["value"], "7A1-W002")
        self.assertEqual(body["values"]["description"], "Example ward two")

    def test_composite_key_named_and_normalised(self) -> None:
        response = self.client.get("/api/v1/lookup/ward_map?key.ward_code=w2&key.sending_facility=%20fac1%20")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["key"], ["FAC1", "W2"])

    def test_unknown_table(self) -> None:
        response = self.client.get("/api/v1/lookup/nope?k=1")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "table_not_found", "detail": "Table 'nope' does not exist",
                                           "table": "nope"})

    def test_unknown_key_does_not_echo_key(self) -> None:
        response = self.client.get("/api/v1/lookup/health_board_mapping?k=SECRET999")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "key_not_found")
        self.assertNotIn("SECRET999", response.text)

    def test_wrong_arity(self) -> None:
        response = self.client.get("/api/v1/lookup/ward_map?k=FAC1")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "invalid_key")

    def test_no_key(self) -> None:
        response = self.client.get("/api/v1/lookup/ward_map")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "invalid_key")

    def test_mixed_key_styles(self) -> None:
        response = self.client.get("/api/v1/lookup/ward_map?k=FAC1&key.ward_code=W2")
        self.assertEqual(response.status_code, 422)

    def test_named_part_supplied_twice(self) -> None:
        response = self.client.get("/api/v1/lookup/ward_map?key.ward_code=W1&key.ward_code=W2&key.sending_facility=F")
        self.assertEqual(response.status_code, 422)
        self.assertIn("more than once", response.json()["detail"])

    def test_empty_key_part(self) -> None:
        response = self.client.get("/api/v1/lookup/health_board_mapping?k=%20%20")
        self.assertEqual(response.status_code, 422)

    def test_list_tables(self) -> None:
        response = self.client.get("/api/v1/tables")
        self.assertEqual(response.status_code, 200)
        tables = {t["name"]: t for t in response.json()}
        self.assertEqual(set(tables), {"health_board_mapping", "ward_map"})
        self.assertEqual(tables["ward_map"]["row_count"], 3)
        self.assertEqual(tables["ward_map"]["key_columns"], ["sending_facility", "ward_code"])
        self.assertEqual(tables["ward_map"]["default_value_column"], "national_ward_code")


class HealthTests(unittest.TestCase):
    def test_live(self) -> None:
        client = TestClient(create_app(make_settings(), FileTableStore.load(REPO_SEED_DIR)))
        self.assertEqual(client.get("/health/live").json(), {"status": "ok"})

    def test_ready_after_startup_load(self) -> None:
        # No store injected: the lifespan loads the seed directory on startup.
        with TestClient(create_app(make_settings())) as client:
            response = client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready", "tables": 2})

    def test_not_ready_before_load(self) -> None:
        # Without the context manager the lifespan doesn't run, so nothing is loaded.
        client = TestClient(create_app(make_settings()))
        self.assertEqual(client.get("/health/ready").status_code, 503)
        response = client.get("/api/v1/lookup/health_board_mapping?k=224")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "not_ready")


class SwaggerGatingTests(unittest.TestCase):
    def test_docs_available_locally(self) -> None:
        client = TestClient(create_app(make_settings(environment="LOCAL"), FileTableStore.load(REPO_SEED_DIR)))
        self.assertEqual(client.get("/openapi.json").status_code, 200)
        self.assertEqual(client.get("/docs").status_code, 200)

    def test_docs_absent_in_production(self) -> None:
        client = TestClient(create_app(make_settings(environment="PRD"), FileTableStore.load(REPO_SEED_DIR)))
        self.assertEqual(client.get("/openapi.json").status_code, 404)
        self.assertEqual(client.get("/docs").status_code, 404)


if __name__ == "__main__":
    unittest.main()
