# Populate leads from a database

The application can populate leads from its local SQLite database, Microsoft SQL Server, or PostgreSQL. The local option requires no server or credentials.

- Database: `Data/LeadManager/cache/lead_manager.sqlite3`
- Reference table: `lead_reference`
- Headers: the same 42 standard lead headers, plus any custom headers present when data is copied.
- All saved workspaces are copied into this shared reference table on initial setup. Their existing worksheet files are preserved. Blank entry rows are excluded. Reopening the application does not repeat the initial copy.

## Populate a worksheet

1. Open **Leads Workspace** and import, paste, or enter the leads to enrich.
2. Click **Populate from database** beside **Import leads**.
3. Choose **Selected leads**, **Visible leads**, or **All leads in this workspace**. If rows are selected, Selected leads is the default; otherwise, Visible leads is the default.
4. Check the columns to populate. This chooser opens every time, with no remembered column selections.
5. Leave **Replace existing values** unchecked to fill only empty cells. Check it to replace values in the selected columns.
6. Click **Populate**. Results show how many cells and leads changed. **Show Details** lists skipped-cell counts and the first 200 missing-key, missing-match, empty-source, or conflicting-value cases.

| Fields | Match key |
| --- | --- |
| Business Email ID, Job Title, Job Level, Job Function, Address, City, State, Zip Code, Address Link, Country, Phone Number, Phone Number Link | Prospect LinkedIn Link |
| Company Name, Company Website, Industry, Company Size, Industry Link, Revenue, Revenue Link, SIC Code, NAICS Code, SIC/NAICS Code Link | Company Website |

Matching ignores HTTP versus HTTPS, `www`, trailing URL slashes, and query strings. Company websites match on the full hostname after removing `www`; distinct subdomains stay separate. Prospect matching accepts LinkedIn `/in/` profile links. Missing or invalid keys do not match.

**Company Website is both a lookup key and an optional destination column.** A blank company website cannot be populated using this lookup. When a website already exists, replacement can copy the matching saved URL spelling, such as `https://www.example.com/`.

## How values are handled

- Only checked destination columns are populated. The existing validation workflow also marks affected leads and related duplicates **Needs validation**.
- Empty source values never erase existing worksheet values.
- Multiple matching reference rows are allowed. Each selected field is populated only when all its nonempty saved values agree, ignoring letter case. Different values are reported as a conflict; no arbitrary first row wins. Other nonconflicting fields can still be filled.
- Postal, SIC, and NAICS codes are stored as text so existing leading zeros are retained.
- Sorting and filtering preserve the underlying lead identities.
- Population is one **Undo / Redo** operation. Use **Ctrl+Z** or **Ctrl+Y** during the current editing session. Successful changes are saved to the workspace; history is session-only, as with other edits.
- Lookup reads the reference database without changing it. An activity entry records the selected fields and counts.

## Add more reference data later

Use the workspace's **…** menu → **Add current leads to reference database…**. This copies the complete current workspace with all columns after showing its lead count. Identical full rows and blank rows are skipped; existing database rows are preserved. If new rows disagree with older values for a matching key, subsequent population reports those fields as conflicts.

For direct SQLite maintenance, quote headers containing spaces or punctuation, for example `SELECT "Business Email ID" FROM lead_reference`. Direct SQL edits to the table are used on the next lookup. Resolve conflicting source values in the reference table before retrying those fields. The small `lead_reference_meta` table only records that initial workspace copying has completed.

The new reference table is independent of TAL and suppression lists. Their validation rules and existing imports, exports, scraping, and email-finding operations remain in place.

## Connect SQL Server or PostgreSQL

Open **Settings → Database → Database connection & column mapping…**, or use the arrow beside **Populate from database** to open the same window.

1. Choose **SQL Server** or **PostgreSQL**.
2. Enter the server/host, port, database name, and authentication details. SQL Server supports a SQL username/password or the current Windows account. For a SQL Server named instance, use `SERVER\INSTANCE` and port **Default / named instance** (0). PostgreSQL normally uses port 5432.
3. Set the connection's TLS options. SQL Server defaults to encryption with certificate verification. PostgreSQL defaults to **Verify certificate and hostname**; supply the root CA certificate if your server needs one. Change these options only to match your server's configuration.
4. Click **Test connection & load tables**. The application lists tables and views accessible to that account.
5. Choose a table or view. The application checks read access and opens **Column mapping**.
6. For each application header, choose the corresponding database column. For example:

   | Application header | Example database column |
   | --- | --- |
   | Prospect LinkedIn Link | `linkedin_url` |
   | Business Email ID | `work_email` |
   | Company Website | `company_domain` |
   | Company Name | `business_name` |
   | Job Title | `job_title` |

7. Review suggested matches, correct any differences, and leave unused headers **Not mapped**. Click **Use this database** to save the connection details and mapping.
8. Click **Populate from database**. It shows the selected source and asks which columns to populate on every run. Fields without a mapped source column or matching key are disabled.

Each database column maps to one application header. Prospect fields require a mapping for **Prospect LinkedIn Link**. Company fields require **Company Website**. If your data is split across tables, select a database view that combines the needed source columns. The application does not execute user-entered SQL or create/modify remote tables.

Connection settings and mappings are remembered separately for SQL Server and PostgreSQL. You can switch back to **Local database** at any time. Testing or cancelling setup does not replace the saved source. The external server is checked before each population; a connection failure never silently switches to the local source. If a mapped column has been renamed or removed, reconnect and review the mapping before populating again.

Passwords are kept only in memory for the current application session. After reopening, the application asks for the password when needed. Windows authentication does not require a password prompt. Raw driver errors and connection strings are not written to the application's error log or shown in dialogs.

Remote population only reads the source. The **Add current leads to reference database…** action continues to copy leads into the **local** reference table. It does not upload leads to SQL Server or PostgreSQL. Use an account with SELECT access to the intended tables/views.

## Connector installation and verification

The Python packages `psycopg[binary]` and `pyodbc` are included in `requirements.txt` and installed by `Setup_Combined.bat`. Portable builds carry those packages and this guide.

SQL Server additionally requires the 64-bit **Microsoft ODBC Driver 18 or 17 for SQL Server** on the destination computer. The connection screen includes the [official Microsoft download link](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server). The legacy Windows driver named only `SQL Server` is not used. Installing the Microsoft driver may require an administrator.

Lookups stream source rows in batches rather than importing the entire external table into the local reference database. Queries have a 60-second timeout and the lookup has a two-minute processing limit. For a very large reference database, select a smaller view containing the relevant leads. A failed or timed-out lookup does not apply a partial set of values.

Development checks include database-driver contract tests for both engines, mapping and password handling, real Qt population tests, and a real connection to a disposable PostgreSQL cluster. Your own server connection is confirmed only after you enter its details and successfully test it.
