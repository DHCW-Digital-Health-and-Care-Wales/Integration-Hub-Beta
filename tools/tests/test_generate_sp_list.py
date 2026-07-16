"""
Tests for tools/generate_sp_list.py

Run with:  uv run python -m unittest discover tools/tests
"""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub openpyxl so the module can be imported without the package installed
# ---------------------------------------------------------------------------
_openpyxl_stub = types.ModuleType("openpyxl")
_openpyxl_stub.Workbook = MagicMock  # type: ignore[attr-defined]

_styles_stub = types.ModuleType("openpyxl.styles")
_styles_stub.Font = MagicMock  # type: ignore[attr-defined]
_styles_stub.PatternFill = MagicMock  # type: ignore[attr-defined]
_styles_stub.Alignment = MagicMock  # type: ignore[attr-defined]

_utils_stub = types.ModuleType("openpyxl.utils")


def _get_column_letter(n: int) -> str:
    """Minimal openpyxl.utils.get_column_letter equivalent for A–ZZ range."""
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


_utils_stub.get_column_letter = _get_column_letter  # type: ignore[attr-defined]

sys.modules.setdefault("openpyxl", _openpyxl_stub)
sys.modules.setdefault("openpyxl.styles", _styles_stub)
sys.modules.setdefault("openpyxl.utils", _utils_stub)

# Now import the module under test
_TOOLS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_TOOLS_DIR))

import generate_sp_list as gsl  # noqa: E402

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Helper to read a fixture file
# ---------------------------------------------------------------------------

def _fixture(name: str) -> str:
    return (_FIXTURES_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests – description extraction
# ---------------------------------------------------------------------------


class TestExtractDescription(unittest.TestCase):

    def test_line_comments_extracted(self):
        sql = """
CREATE OR ALTER PROCEDURE [dbo].[MyProc]
-- Author: Test
-- Description: Does something useful
-- Extra info here
AS BEGIN END
"""
        procs = gsl.parse_stored_procedures(sql, "test.sql")
        self.assertEqual(len(procs), 1)
        desc = procs[0].description
        self.assertIn("Does something useful", desc)

    def test_block_comment_extracted(self):
        sql = """
CREATE OR ALTER PROCEDURE dbo.MyProc
/*
 * Description: Block comment description
 * Author: Test
 */
AS BEGIN END
"""
        procs = gsl.parse_stored_procedures(sql, "test.sql")
        self.assertIn("Block comment description", procs[0].description)

    def test_divider_lines_excluded(self):
        sql = """
CREATE OR ALTER PROCEDURE dbo.MyProc
-- =============================================
-- Description: Real description
-- =============================================
AS BEGIN END
"""
        desc = gsl.parse_stored_procedures(sql, "test.sql")[0].description
        self.assertNotIn("===", desc)
        self.assertIn("Real description", desc)


# ---------------------------------------------------------------------------
# Tests – table extraction
# ---------------------------------------------------------------------------


class TestExtractTables(unittest.TestCase):

    def test_simple_from_clause(self):
        sql = """
CREATE OR ALTER PROCEDURE dbo.MyProc AS
BEGIN
    SELECT * FROM dbo.Patient;
END
"""
        procs = gsl.parse_stored_procedures(sql, "test.sql")
        self.assertIn("dbo.Patient", procs[0].tables_used)

    def test_join_extracted(self):
        sql = """
CREATE OR ALTER PROCEDURE dbo.MyProc AS
BEGIN
    SELECT p.Id FROM dbo.Patient p
    INNER JOIN dbo.Admission a ON a.PatientId = p.Id;
END
"""
        tables = gsl.parse_stored_procedures(sql, "test.sql")[0].tables_used
        self.assertIn("dbo.Patient", tables)
        self.assertIn("dbo.Admission", tables)

    def test_temp_tables_excluded(self):
        sql = """
CREATE OR ALTER PROCEDURE dbo.MyProc AS
BEGIN
    SELECT * FROM #TempPatients;
    INSERT INTO @TableVar SELECT 1;
END
"""
        tables = gsl.parse_stored_procedures(sql, "test.sql")[0].tables_used
        self.assertEqual(tables, [])

    def test_insert_into_extracted(self):
        sql = """
CREATE OR ALTER PROCEDURE dbo.MyProc AS
BEGIN
    INSERT INTO dbo.MessageLog (Col1) VALUES (1);
END
"""
        tables = gsl.parse_stored_procedures(sql, "test.sql")[0].tables_used
        self.assertIn("dbo.MessageLog", tables)

    def test_update_extracted(self):
        sql = """
CREATE OR ALTER PROCEDURE dbo.MyProc AS
BEGIN
    UPDATE dbo.Admission SET Status = 'Done' WHERE Id = 1;
END
"""
        tables = gsl.parse_stored_procedures(sql, "test.sql")[0].tables_used
        self.assertIn("dbo.Admission", tables)

    def test_no_duplicates(self):
        sql = """
CREATE OR ALTER PROCEDURE dbo.MyProc AS
BEGIN
    SELECT * FROM dbo.Patient p
    INNER JOIN dbo.Patient p2 ON p2.Id = p.ParentId;
END
"""
        tables = gsl.parse_stored_procedures(sql, "test.sql")[0].tables_used
        self.assertEqual(tables.count("dbo.Patient"), 1)


# ---------------------------------------------------------------------------
# Tests – discontinued detection
# ---------------------------------------------------------------------------


class TestIsDiscontinued(unittest.TestCase):

    def test_api_schema_is_discontinued(self):
        sql = """
CREATE OR ALTER PROCEDURE [api].[GetPatient] AS
BEGIN
    SELECT * FROM dbo.Patient;
END
"""
        proc = gsl.parse_stored_procedures(sql, "test.sql")[0]
        self.assertTrue(proc.is_discontinued)

    def test_raiserror_marks_discontinued(self):
        sql = """
CREATE OR ALTER PROCEDURE [dbo].[OldProc] AS
BEGIN
    RAISERROR('Deprecated', 16, 1);
    /* SELECT * FROM dbo.OldTable; */
END
"""
        proc = gsl.parse_stored_procedures(sql, "test.sql")[0]
        self.assertTrue(proc.is_discontinued)

    def test_throw_marks_discontinued(self):
        sql = """
CREATE OR ALTER PROCEDURE dbo.OldProc AS
BEGIN
    THROW 50001, 'No longer in use', 1;
    -- SELECT * FROM dbo.OldTable;
END
"""
        proc = gsl.parse_stored_procedures(sql, "test.sql")[0]
        self.assertTrue(proc.is_discontinued)

    def test_raiserror_in_comment_only_not_discontinued(self):
        """If RAISERROR only appears inside a comment, not in active code, not discontinued."""
        sql = """
CREATE OR ALTER PROCEDURE dbo.ActiveProc AS
BEGIN
    -- NOTE: previously called RAISERROR here but removed
    SELECT * FROM dbo.Patient;
END
"""
        proc = gsl.parse_stored_procedures(sql, "test.sql")[0]
        self.assertFalse(proc.is_discontinued)

    def test_normal_dbo_proc_not_discontinued(self):
        sql = """
CREATE OR ALTER PROCEDURE dbo.MyProc AS
BEGIN
    SELECT * FROM dbo.Patient;
END
"""
        proc = gsl.parse_stored_procedures(sql, "test.sql")[0]
        self.assertFalse(proc.is_discontinued)


# ---------------------------------------------------------------------------
# Tests – replacement SP extraction
# ---------------------------------------------------------------------------


class TestExtractReplacement(unittest.TestCase):

    def test_replacement_from_description(self):
        sql = """
CREATE OR ALTER PROCEDURE [api].[GetPatient]
-- Description: Deprecated. Use dbo.GetActivePatients instead.
AS BEGIN SELECT 1; END
"""
        proc = gsl.parse_stored_procedures(sql, "test.sql")[0]
        self.assertIsNotNone(proc.replacement_sp)
        self.assertIn("GetActivePatients", proc.replacement_sp)  # type: ignore[arg-type]

    def test_replacement_from_body_comment(self):
        sql = """
CREATE OR ALTER PROCEDURE dbo.OldProc AS
BEGIN
    RAISERROR('Old. Replaced by dbo.NewProc.', 16, 1);
    -- Replacement: dbo.NewProc
END
"""
        proc = gsl.parse_stored_procedures(sql, "test.sql")[0]
        self.assertIsNotNone(proc.replacement_sp)
        self.assertIn("NewProc", proc.replacement_sp)  # type: ignore[arg-type]

    def test_no_replacement_for_active_proc(self):
        sql = """
CREATE OR ALTER PROCEDURE dbo.MyProc AS
BEGIN SELECT * FROM dbo.Patient; END
"""
        proc = gsl.parse_stored_procedures(sql, "test.sql")[0]
        self.assertIsNone(proc.replacement_sp)


# ---------------------------------------------------------------------------
# Tests – full file parsing
# ---------------------------------------------------------------------------


class TestParseFiles(unittest.TestCase):

    def test_active_procedures_file(self):
        sql = _fixture("active_procedures.sql")
        procs = gsl.parse_stored_procedures(sql, "active_procedures.sql")
        self.assertEqual(len(procs), 3)
        names = [p.name for p in procs]
        self.assertIn("GetActivePatients", names)
        self.assertIn("InsertMessage", names)
        self.assertIn("GetPendingReplayMessages", names)
        for p in procs:
            self.assertFalse(p.is_discontinued, f"{p.name} should not be discontinued")
            self.assertIsNone(p.replacement_sp)

    def test_active_procedures_tables(self):
        sql = _fixture("active_procedures.sql")
        procs = gsl.parse_stored_procedures(sql, "active_procedures.sql")
        get_active = next(p for p in procs if p.name == "GetActivePatients")
        self.assertIn("dbo.Patient", get_active.tables_used)
        self.assertIn("dbo.Admission", get_active.tables_used)
        self.assertIn("dbo.Ward", get_active.tables_used)

    def test_raiserror_discontinued_file(self):
        sql = _fixture("discontinued_raiserror.sql")
        procs = gsl.parse_stored_procedures(sql, "discontinued_raiserror.sql")
        self.assertEqual(len(procs), 2)
        for p in procs:
            self.assertTrue(p.is_discontinued, f"{p.name} should be discontinued")

    def test_raiserror_discontinued_replacements(self):
        sql = _fixture("discontinued_raiserror.sql")
        procs = gsl.parse_stored_procedures(sql, "discontinued_raiserror.sql")
        legacy = next(p for p in procs if p.name == "GetPatients_Legacy")
        self.assertIsNotNone(legacy.replacement_sp)
        self.assertIn("GetActivePatients", legacy.replacement_sp)  # type: ignore[arg-type]

    def test_api_schema_discontinued_file(self):
        sql = _fixture("discontinued_api_schema.sql")
        procs = gsl.parse_stored_procedures(sql, "discontinued_api_schema.sql")
        self.assertEqual(len(procs), 2)
        for p in procs:
            self.assertEqual(p.schema, "api")
            self.assertTrue(p.is_discontinued, f"{p.name} should be discontinued")

    def test_api_schema_replacements(self):
        sql = _fixture("discontinued_api_schema.sql")
        procs = gsl.parse_stored_procedures(sql, "discontinued_api_schema.sql")
        get_patient = next(p for p in procs if p.name == "GetPatient")
        self.assertIsNotNone(get_patient.replacement_sp)
        self.assertIn("GetActivePatients", get_patient.replacement_sp)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests – multiple SPs in one file
# ---------------------------------------------------------------------------


class TestMultipleProcsPerFile(unittest.TestCase):

    def test_multiple_procs_parsed(self):
        sql = """
CREATE OR ALTER PROCEDURE dbo.ProcA AS BEGIN SELECT * FROM dbo.TableA; END
GO
CREATE OR ALTER PROCEDURE dbo.ProcB AS BEGIN SELECT * FROM dbo.TableB; END
GO
"""
        procs = gsl.parse_stored_procedures(sql, "multi.sql")
        self.assertEqual(len(procs), 2)
        self.assertEqual(procs[0].name, "ProcA")
        self.assertEqual(procs[1].name, "ProcB")

    def test_source_file_recorded(self):
        sql = "CREATE PROCEDURE dbo.MyProc AS BEGIN SELECT 1; END"
        procs = gsl.parse_stored_procedures(sql, "my_scripts/deploy.sql")
        self.assertEqual(procs[0].source_file, "my_scripts/deploy.sql")


# ---------------------------------------------------------------------------
# Tests – schema and full_name
# ---------------------------------------------------------------------------


class TestSchemaAndFullName(unittest.TestCase):

    def test_default_schema_dbo(self):
        sql = "CREATE PROCEDURE MyProc AS BEGIN SELECT 1; END"
        proc = gsl.parse_stored_procedures(sql, "test.sql")[0]
        self.assertEqual(proc.schema, "dbo")
        self.assertEqual(proc.full_name, "dbo.MyProc")

    def test_explicit_schema_preserved(self):
        sql = "CREATE PROCEDURE [reporting].[GetStats] AS BEGIN SELECT 1; END"
        proc = gsl.parse_stored_procedures(sql, "test.sql")[0]
        self.assertEqual(proc.schema, "reporting")
        self.assertEqual(proc.full_name, "reporting.GetStats")

    def test_brackets_stripped_from_name(self):
        sql = "CREATE PROCEDURE [dbo].[MyProc] AS BEGIN SELECT 1; END"
        proc = gsl.parse_stored_procedures(sql, "test.sql")[0]
        self.assertEqual(proc.name, "MyProc")
        self.assertEqual(proc.schema, "dbo")


if __name__ == "__main__":
    unittest.main()
