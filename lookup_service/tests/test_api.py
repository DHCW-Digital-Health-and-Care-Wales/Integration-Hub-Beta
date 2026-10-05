from __future__ import annotations

import json
import unittest
from typing import Any

from fastapi.testclient import TestClient

from lookup_service.app import create_app
from tests.helpers import MemoryTableStore, make_settings

HEALTH_BOARD_CSV = b"msh3,health_board\n224,VCC-NEW\n999,TEST\n"


class LookupApiTests(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        # No COSMOS_ENDPOINT: tables come read-only from the repo seed files.
        cls.client = cls.enterClassContext(TestClient(create_app(make_settings())))

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

    def test_invalid_keys(self) -> None:
        for url in (
            "/api/v1/lookup/ward_map?k=FAC1",
            "/api/v1/lookup/ward_map",
            "/api/v1/lookup/ward_map?k=FAC1&key.ward_code=W2",
            "/api/v1/lookup/ward_map?key.ward_code=W1&key.ward_code=W2&key.sending_facility=F",
            "/api/v1/lookup/health_board_mapping?k=%20%20",
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["error"], "invalid_key")

    def test_list_tables(self) -> None:
        response = self.client.get("/api/v1/tables")
        self.assertEqual(response.status_code, 200)
        tables = {t["name"]: t for t in response.json()}
        self.assertEqual(set(tables), {"health_board_mapping", "ward_map"})
        self.assertEqual(tables["ward_map"]["row_count"], 3)
        self.assertEqual(tables["ward_map"]["key_columns"], ["sending_facility", "ward_code"])
        self.assertEqual(tables["health_board_mapping"]["cache"]["mode"], "preloaded")
        self.assertEqual(tables["ward_map"]["cache"]["mode"], "ttl")
        self.assertEqual(tables["ward_map"]["ttl_seconds"], 300)

    def test_table_detail(self) -> None:
        response = self.client.get("/api/v1/tables/ward_map")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["key_normalisation"]["ward_code"]["case"], "upper")
        self.assertEqual(self.client.get("/api/v1/tables/nope").status_code, 404)

    def test_rows_paging_and_search(self) -> None:
        response = self.client.get("/api/v1/tables/ward_map/rows", params={"search": "fac1", "limit": 1})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["total"], len(body["rows"])), (2, 1))
        self.assertEqual(body["rows"][0]["key"], ["FAC1", "W1"])
        self.assertEqual(self.client.get("/api/v1/tables/ward_map/rows", params={"limit": 999}).status_code, 422)
        self.assertEqual(self.client.get("/api/v1/tables/nope/rows").status_code, 404)

    def test_upload_rejected_for_read_only_file_store(self) -> None:
        response = self.client.post("/api/v1/tables/health_board_mapping/uploads",
                                    files={"file": ("hb.csv", HEALTH_BOARD_CSV, "text/csv")})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "read_only")


class UploadApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryTableStore()
        self.client = self.enterContext(TestClient(create_app(make_settings(max_upload_mb=1), self.store)))

    def upload(self, table: str, content: bytes, **form: Any) -> Any:
        data = {name: json.dumps(value) if not isinstance(value, str) else value for name, value in form.items()}
        return self.client.post(f"/api/v1/tables/{table}/uploads", files={"file": ("data.csv", content, "text/csv")},
                                data=data)

    def test_seed_tables_are_imported_into_writable_store(self) -> None:
        self.assertEqual(set(self.store.records), {"health_board_mapping", "ward_map"})

    def test_replace_existing_table_is_visible_immediately(self) -> None:
        response = self.upload("health_board_mapping", HEALTH_BOARD_CSV)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["row_count"], 2)
        self.assertEqual(response.json()["removed"], 3)
        self.assertFalse(response.json()["created"])
        lookup = self.client.get("/api/v1/lookup/health_board_mapping?k=224").json()
        self.assertEqual(lookup["value"], "VCC-NEW")
        self.assertEqual(self.client.get("/api/v1/lookup/health_board_mapping?k=212").status_code, 404)
        self.assertEqual(self.store.records["health_board_mapping"].stats.last_upload_file, "data.csv")

    def test_ttl_table_upload_drops_stale_cache(self) -> None:
        self.assertEqual(self.client.get("/api/v1/lookup/ward_map?k=FAC1&k=W1").json()["value"], "7A1-W001")
        csv = b"sending_facility,ward_code,national_ward_code,description\nFAC1,W1,NEW,d\n"
        self.assertEqual(self.upload("ward_map", csv).status_code, 201)
        self.assertEqual(self.client.get("/api/v1/lookup/ward_map?k=FAC1&k=W1").json()["value"], "NEW")

    def test_create_table_with_definition_and_mapping(self) -> None:
        response = self.upload(
            "discharge_reason", b"Code,Text\n a ,Home\nB,Other\n",
            definition={"key_columns": ["code"], "value_columns": ["text"], "ttl_seconds": 60,
                        "key_normalisation": {"code": {"case": "upper"}}},
            mapping={"key": {"code": {"path": "Code"}}, "values": {"text": {"path": "Text"}}},
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertTrue(response.json()["created"])
        lookup = self.client.get("/api/v1/lookup/discharge_reason?key.code=a")
        self.assertEqual(lookup.json()["value"], "Home")
        self.assertEqual(self.client.get("/api/v1/tables/discharge_reason").json()["ttl_seconds"], 60)

    def test_new_table_without_definition_is_rejected(self) -> None:
        response = self.upload("brand_new", b"code,label\nA,B\n")
        self.assertEqual(response.status_code, 422)
        self.assertIn("supply a table definition", response.json()["detail"])

    def test_invalid_rows_change_nothing_and_list_line_numbers(self) -> None:
        response = self.upload("health_board_mapping", b"msh3,health_board\n224,X\n224,Y\n,Z\n")
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["error"], "invalid_upload")
        self.assertEqual(body["errors"], ["line 3: duplicate key (first seen on line 2)",
                                          "line 4: empty key part 'msh3'"])
        self.assertEqual(self.store.rows["health_board_mapping"][("224",)].values["health_board"], "VCC")

    def test_invalid_definition_and_mapping(self) -> None:
        response = self.upload("codes", b"code,label\nA,B\n", definition={"key_columns": ["missing column"]})
        self.assertEqual(response.status_code, 422)
        self.assertIn("errors", response.json())
        self.assertEqual(self.upload("codes", b"code,label\nA,B\n", definition="{bad").status_code, 422)
        self.assertEqual(self.upload("codes", b"code,label\nA,B\n", definition={},
                                     mapping={"key": "nope"}).status_code, 422)

    def test_invalid_table_name(self) -> None:
        self.assertEqual(self.upload("Bad_Name", b"code,label\nA,B\n", definition={}).status_code, 422)

    def test_empty_and_non_utf8_files(self) -> None:
        self.assertEqual(self.upload("health_board_mapping", b"msh3,health_board\n").status_code, 422)
        self.assertEqual(self.upload("health_board_mapping", b"\xff\xfe\x00").status_code, 422)

    def test_too_large(self) -> None:
        response = self.upload("health_board_mapping", b"msh3,health_board\n" + b"1,x\n" * 300_000)
        self.assertEqual(response.status_code, 413)


class WritesDisabledTests(unittest.TestCase):
    def test_uploads_forbidden_outside_local(self) -> None:
        with TestClient(create_app(make_settings(environment="DEV"), MemoryTableStore())) as client:
            response = client.post("/api/v1/tables/health_board_mapping/uploads",
                                   files={"file": ("hb.csv", HEALTH_BOARD_CSV, "text/csv")})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "writes_disabled")


class HealthTests(unittest.TestCase):
    def test_live(self) -> None:
        with TestClient(create_app(make_settings())) as client:
            self.assertEqual(client.get("/health/live").json(), {"status": "ok"})

    def test_ready_after_startup(self) -> None:
        store = MemoryTableStore()
        with TestClient(create_app(make_settings(), store)) as client:
            response = client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ready", "tables": 2, "source": "memory"})
        # An injected store belongs to the caller, so the app opens but doesn't close it.
        self.assertTrue(store.opened)
        self.assertFalse(store.closed)

    def test_not_ready_before_startup(self) -> None:
        # Without the context manager the lifespan doesn't run, so nothing is loaded.
        client = TestClient(create_app(make_settings()))
        self.assertEqual(client.get("/health/ready").status_code, 503)
        response = client.get("/api/v1/lookup/health_board_mapping?k=224")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "not_ready")


class BackendFailureTests(unittest.TestCase):
    def test_store_outage_is_503(self) -> None:
        store = MemoryTableStore()
        with TestClient(create_app(make_settings(), store)) as client:
            store.fail_reads = True
            response = client.get("/api/v1/lookup/ward_map?k=FAC1&k=W1")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "backend_unavailable")


class SwaggerGatingTests(unittest.TestCase):
    def test_docs_available_locally(self) -> None:
        with TestClient(create_app(make_settings(environment="LOCAL"))) as client:
            self.assertEqual(client.get("/openapi.json").status_code, 200)
            self.assertEqual(client.get("/docs").status_code, 200)

    def test_docs_absent_in_production(self) -> None:
        with TestClient(create_app(make_settings(environment="PRD"))) as client:
            self.assertEqual(client.get("/openapi.json").status_code, 404)
            self.assertEqual(client.get("/docs").status_code, 404)


if __name__ == "__main__":
    unittest.main()
