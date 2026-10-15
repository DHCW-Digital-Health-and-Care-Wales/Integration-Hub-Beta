from __future__ import annotations

import unittest

from fastapi.testclient import TestClient
from httpx import Response

from lookup_service.app import create_app
from tests.helpers import MemoryTableStore, SeedDirTestCase, codes_definition, make_row, make_settings


class OverviewPageTests(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = cls.enterClassContext(TestClient(create_app(make_settings())))

    def test_lists_tables_with_links(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="http://testserver/tables/ward_map"', response.text)
        self.assertIn("preloaded", response.text)

    def test_sets_security_headers(self) -> None:
        response = self.client.get("/")
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_hides_upload_for_read_only_store(self) -> None:
        self.assertNotIn('btn-dash--primary" href="http://testserver/upload"', self.client.get("/").text)
        response = self.client.get("/upload")
        self.assertIn("configure COSMOS_ENDPOINT", response.text)
        self.assertNotIn('enctype="multipart/form-data"', response.text)

    def test_static_assets_served(self) -> None:
        self.assertIn("#325083", self.client.get("/static/css/lookup.css").text)
        self.assertEqual(self.client.get("/static/js/upload.js").status_code, 200)


class TablePageTests(unittest.TestCase):
    client: TestClient

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = cls.enterClassContext(TestClient(create_app(make_settings())))

    def test_shows_definition_and_rows(self) -> None:
        response = self.client.get("/tables/ward_map")
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="key.sending_facility"', response.text)
        self.assertIn("7A2-W001", response.text)
        self.assertIn("3 row(s)", response.text)

    def test_search_filters_rows(self) -> None:
        response = self.client.get("/tables/ward_map", params={"search": "fac2"})
        self.assertIn("7A2-W001", response.text)
        self.assertNotIn("7A1-W002", response.text)
        self.assertIn("No rows match", self.client.get("/tables/ward_map", params={"search": "zzz"}).text)

    def test_lookup_tester_shows_result(self) -> None:
        response = self.client.get("/tables/ward_map", params={"key.sending_facility": "fac1", "key.ward_code": "w1"})
        self.assertIn("FAC1 :: W1", response.text)
        self.assertIn("<strong>7A1-W001</strong>", response.text)

    def test_lookup_tester_shows_error(self) -> None:
        response = self.client.get("/tables/health_board_mapping", params={"key.msh3": "000"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("key_not_found", response.text)

    def test_unknown_table_page(self) -> None:
        response = self.client.get("/tables/nope")
        self.assertEqual(response.status_code, 404)
        self.assertIn("does not exist", response.text)

    def test_upload_banner(self) -> None:
        self.assertIn("Upload complete: 7 row(s)", self.client.get("/tables/ward_map?uploaded=7").text)


class TablePagingTests(unittest.TestCase):
    def test_pages_through_rows(self) -> None:
        store = MemoryTableStore()
        store.put_table(codes_definition(), [make_row(f"K{i:03d}", label=f"v{i}") for i in range(120)])
        with TestClient(create_app(make_settings(seed_dir=make_settings().seed_dir / "missing"), store)) as client:
            first = client.get("/tables/codes").text
            last = client.get("/tables/codes", params={"page": 3}).text
        self.assertIn("page 1 of 3", first)
        self.assertIn("K000", first)
        self.assertNotIn("K050", first)
        self.assertIn("K119", last)
        self.assertNotIn(">Next<", last)


class UploadPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryTableStore()
        self.client = self.enterContext(TestClient(create_app(make_settings(), self.store)))

    def test_form_rendered(self) -> None:
        response = self.client.get("/upload", params={"table": "ward_map"})
        self.assertEqual(response.status_code, 200)
        self.assertIn('enctype="multipart/form-data"', response.text)
        self.assertIn('value="ward_map"', response.text)

    def test_create_table_redirects_to_table_page(self) -> None:
        response = self.client.post(
            "/upload",
            data={"table": "discharge_reason", "key_columns": "code", "key_case": "upper", "ttl_value": "2",
                  "ttl_unit": "minutes", "preload": "on", "description": "Discharge reasons"},
            files={"file": ("reasons.csv", b"code,text\na,Home\n", "text/csv")},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303, response.text)
        self.assertTrue(response.headers["location"].endswith("/tables/discharge_reason?uploaded=1"))
        definition = self.store.records["discharge_reason"].definition
        self.assertTrue(definition.preload)
        self.assertEqual(definition.ttl_seconds, 120)
        self.assertEqual(definition.rule_for("code").case, "upper")
        self.assertIn(("A",), self.store.rows["discharge_reason"])

    def test_replace_existing_keeps_definition_unless_redefine(self) -> None:
        response = self.client.post(
            "/upload", data={"table": "health_board_mapping", "key_columns": "ignored"},
            files={"file": ("hb.csv", b"msh3,health_board\n224,X\n", "text/csv")}, follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303, response.text)
        self.assertEqual(self.store.records["health_board_mapping"].definition.key_columns, ("msh3",))

    def test_errors_rerender_form_with_values(self) -> None:
        response = self.client.post(
            "/upload", data={"table": "health_board_mapping"},
            files={"file": ("hb.csv", b"msh3,health_board\n224,X\n224,Y\n", "text/csv")},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("line 3: duplicate key (first seen on line 2)", response.text)
        self.assertIn('value="health_board_mapping"', response.text)

    def test_missing_file(self) -> None:
        response = self.client.post("/upload", data={"table": "health_board_mapping"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("Choose a CSV file", response.text)

    def test_invalid_ttl(self) -> None:
        response = self.client.post("/upload", data={"table": "newtable", "ttl_value": "soon"},
                                    files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
        self.assertEqual(response.status_code, 422)
        self.assertIn("TTL must be a whole number", response.text)

    def test_blocked_outside_local(self) -> None:
        with TestClient(create_app(make_settings(environment="DEV"), MemoryTableStore())) as client:
            response = client.post("/upload", data={"table": "x"}, files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")})
            self.assertEqual(response.status_code, 403)
            self.assertIn("Uploads are disabled", client.get("/upload").text)


class TableSettingsFormTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = MemoryTableStore()
        self.client = self.enterContext(TestClient(create_app(make_settings(), self.store)))

    def save(self, **data: str) -> Response:
        return self.client.post("/tables/ward_map/settings", data=data, follow_redirects=False)

    def test_form_shown_prefilled_with_split_ttl(self) -> None:
        self.save(ttl_value="2", ttl_unit="hours")
        page = self.client.get("/tables/ward_map").text
        self.assertIn('action="http://testserver/tables/ward_map/settings"', page)
        self.assertIn('name="ttl_value" value="2"', page)
        self.assertIn('<option value="hours" selected>', page)

    def test_each_unit_converts_to_seconds(self) -> None:
        for unit, expected in (("seconds", 5), ("minutes", 300), ("hours", 18000), ("days", 432000)):
            with self.subTest(unit=unit):
                response = self.save(ttl_value="5", ttl_unit=unit)
                self.assertEqual(response.status_code, 303, response.text)
                self.assertEqual(self.store.records["ward_map"].definition.ttl_seconds, expected)
        self.assertTrue(response.headers["location"].endswith("/tables/ward_map?saved=1"))

    def test_preload_and_blank_ttl(self) -> None:
        self.save(ttl_value="", ttl_unit="hours", preload="on")
        definition = self.store.records["ward_map"].definition
        self.assertEqual((definition.ttl_seconds, definition.preload), (None, True))
        self.assertIn("Preloaded", self.client.get("/tables/ward_map?saved=1").text)
        self.assertIn("Cache settings saved", self.client.get("/tables/ward_map?saved=1").text)

    def test_invalid_values_rerender_with_error(self) -> None:
        for data in ({"ttl_value": "soon"}, {"ttl_value": "0"}, {"ttl_value": "8", "ttl_unit": "days"},
                     {"ttl_value": "1", "ttl_unit": "weeks"}):
            with self.subTest(data=data):
                response = self.save(**data)
                self.assertEqual(response.status_code, 422)
                self.assertIn("invalid_settings", response.text)
        self.assertIsNone(self.store.records["ward_map"].definition.ttl_seconds)

    def test_hidden_and_rejected_when_read_only(self) -> None:
        with TestClient(create_app(make_settings())) as client:
            self.assertNotIn("Cache settings", client.get("/tables/ward_map").text)
            response = client.post("/tables/ward_map/settings", data={"preload": "on"}, follow_redirects=False)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(client.post("/tables/nope/settings", data={}).status_code, 404)


class EscapingTests(SeedDirTestCase):
    def test_values_and_names_are_html_escaped(self) -> None:
        self.write_csv("codes", 'code,label\nA,"<script>alert(1)</script>"\n')
        with TestClient(create_app(make_settings(self.seed_dir))) as client:
            response = client.get("/tables/codes", params={"key.code": "A"})
            self.assertNotIn("<script>alert(1)</script>", response.text)
            self.assertIn("&lt;script&gt;", response.text)
            response = client.get("/tables/codes", params={"search": "<b>x</b>"})
            self.assertNotIn("<b>x</b>", response.text)

    def test_empty_state(self) -> None:
        with TestClient(create_app(make_settings(self.seed_dir))) as client:
            self.assertIn("No tables yet", client.get("/").text)


if __name__ == "__main__":
    unittest.main()
