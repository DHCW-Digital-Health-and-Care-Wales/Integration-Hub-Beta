# tools/

Utility scripts for the Integration Hub team.

---

## `generate_sp_list.py` — Stored Procedure Excel Inventory

Scans a folder of SQL deployment scripts, extracts every stored procedure, and writes a
formatted Excel spreadsheet (`.xlsx`) containing:

| Column | Description |
|---|---|
| **Stored Procedure Name** | Fully-qualified `schema.name` |
| **Schema** | SQL schema only |
| **Description** | Extracted from comment blocks before / after the `CREATE PROCEDURE` header |
| **Tables Used** | Comma-separated list of tables referenced via `FROM`, `JOIN`, `INTO`, `UPDATE`, `MERGE`, `DELETE FROM` |
| **Is Discontinued** | `Yes` / `No` — see discontinuation rules below |
| **Replacement Stored Procedure** | For discontinued procedures, the replacement name parsed from the description |
| **Source File** | Relative path of the `.sql` file it was found in |

### Discontinuation rules

A stored procedure is marked **Discontinued** when either:

1. **`api` schema** — all procedures in the `api` schema are being retired. The replacement
   procedure name is extracted from the description comment (look for phrases like
   *"use dbo.NewProc instead"*, *"replacement: dbo.NewProc"*, *"replaced by dbo.NewProc"*, etc.).

2. **RAISERROR / THROW in active code** — the business logic has been commented out and the
   procedure body now only returns an error or warning message (`RAISERROR` or `THROW`).
   The comment text / description is scanned for the replacement procedure name.

Rows for discontinued procedures are highlighted in the Excel output.

---

### Usage

Requires **Python 3.13+** and **openpyxl**.

```bash
# Run once — openpyxl is installed into an ephemeral environment
uv run --with openpyxl python tools/generate_sp_list.py <sql_folder> [output.xlsx]
```

**Examples:**

```bash
# Scan the local SQL scripts folder, write stored_procedures.xlsx
uv run --with openpyxl python tools/generate_sp_list.py local/sql-scripts

# Scan a custom folder, write to a named file
uv run --with openpyxl python tools/generate_sp_list.py /path/to/deployment/scripts sp_inventory.xlsx
```

The tool searches *recursively* for `*.sql` files inside the given folder.

---

### Placement of description comments

The tool recognises descriptions in any of these styles:

```sql
-- =============================================
-- Author:  Team
-- Description: Returns active patients from the ward.
-- =============================================
CREATE OR ALTER PROCEDURE [dbo].[GetActivePatients]
    @SourceSystem NVARCHAR(100)
AS
BEGIN ...
```

```sql
CREATE OR ALTER PROCEDURE [dbo].[GetActivePatients]
/*
 * Description: Returns active patients from the ward.
 */
AS
BEGIN ...
```

Both **preceding** and **inline** (between header and `AS`) comment blocks are captured.

---

### Running the tests

```bash
cd tools
python -m unittest discover tests -v
```
