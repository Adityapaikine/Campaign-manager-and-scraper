# Shared Lead Workspace

**27 October interface update:** Lead Workspace now has an Excel-style ribbon. **Records** selects the draft/queue; **Column view** and **Manage columns** stay beside the grid. Workflow controls are on **Review**, also reachable through **Home → Review and send**. Worksheet tabs are at the bottom. Service operations and permissions are retained. See [EXCEL_WORKSPACE_GUIDE.md](EXCEL_WORKSPACE_GUIDE.md).

The existing Qt spreadsheet, import mapping, formulas and validators are reused. One authenticated Lead Workspace includes research and shared lead operations, backed by a service on this PC. Only the service accesses authoritative `team_*` records in `Data/LeadManager/cache/lead_manager.sqlite3`. Employees connect using individual accounts. They must not receive this PC's Data folder, backups, logs, certificates' private keys or old worksheet files.

**Start Lead Workspace.vbs** opens the single application. Older Team Workspace and Local Research shortcuts are compatibility aliases for the same login and window. There is no separate local-research application or account-menu launcher. Scraper, Lead Workspace, Campaign Manager, Validation Summary, AI Center, Dashboard, Reports, Activity & Diagnostics, Settings and Administration share one sidebar. Only permitted modules appear.

## Module permissions

Super Users open **Administration > Module Access**, choose **Department** or **Individual user**, select the subject, then set each module to **Inherit**, **Allow** or **Deny** and click **Save module access**. User overrides take priority over department settings; Inherit removes the selected override. The effective column shows the saved result. Administration remains Super User only, and Super Users cannot lock themselves out.

Scraper is denied by default for Quality and Delivery, and allowed for Operations/DBA. Other departments can be configured here. Activity & Diagnostics defaults to Super Users; explicitly permitted staff see only their own audit events. Other modules are allowed by default, with existing role/record/field restrictions still applied. Allowing Campaign Manager does not authorize an employee to change campaign configuration.

The service checks module access on every operation. Local Scraper actions recheck access before starting; the client checks access changes every 45 seconds and on **Account > Refresh my access**. Revoking Scraper stops an active extraction, saving through its normal stop path. If a periodic access check fails, extraction pauses until it can be authorized again. This governs application access; administrators must still protect server files and OS accounts.

## First-time setup on this PC

1. Run `Setup_Combined.bat` if dependencies are missing. The new dependencies are FastAPI, Uvicorn and argon2-cffi; the existing HTTP, PostgreSQL and SQL Server libraries remain in requirements.txt.
2. Run **Setup Team Server.bat**. Enter the initial Super User's full name, username, email and a password of 12–256 characters. The password is entered privately and stored as an Argon2id hash. There is no default password. Invalid or mismatched passwords show an explanation and retry without a traceback. Existing accounts are preserved; setup does not overwrite them.
3. Run **Start Team Server.bat**, then **Status Team Server.bat**. The default URL is `http://127.0.0.1:8765`; it is accessible on this PC only.
4. Open **Start Lead Workspace.vbs** and sign in. The server URL is editable in the login window. Tokens and database passwords stay in memory and are not written to settings.
5. In **Administration**, create users in this order: department managers, Team Leads, employees. Operations, Quality, DBA and Delivery already exist. Additional departments can be created. Select the appropriate department, reporting manager and Team Lead for each account.
6. In **Campaign Manager**, create or choose a campaign, review its configuration, import its account/suppression lists and assign the required users. Use **Campaign** to establish the working campaign before assigning campaign users. Campaign packages can be uploaded as ZIPs up to 10 MB compressed / 100 MB expanded / 500 entries. Review extracted rules before confirming them.
7. Open **Lead Workspace > View: All permitted leads** as Super User to review historical unassigned records. Select the intended records, choose **More > Assign historical owner**, and select an eligible campaign member. Unknown ownership is never guessed. Previously assigned original ownership cannot be overwritten.

Account deactivation and account changes revoke existing sessions. Sessions expire after eight hours. Sign out revokes that user's active sessions. Forgotten passwords are changed by a signed-in Super User through user administration; passwords cannot be recovered. Maintain at least one additional trusted Super User for recovery.

## Other employee computers

Remote HTTP is deliberately refused. Obtain a certificate whose subject alternative name matches this PC's DNS name (or IP), issued by a CA trusted on the employee PCs. A managed internal CA is suitable. Install the CA trust through your organization's normal process; the app uses Python's default system-trust SSL context and does not disable certificate verification. Alternatively, set `LEAD_TEAM_CA_FILE` to a PEM CA certificate bundle on each client.

Stop the loopback server before changing its binding. Run on this PC:

```powershell
.\'Start Team Server.ps1' -ListenAddress '0.0.0.0' -Port 8765 -Certificate 'C:\ServerCerts\server.pem' -PrivateKey 'C:\ServerCerts\server-key.pem'
```

Restrict Windows Firewall access to the intended LAN/VPN and service port. Keep the database on this PC's local disk, never an SMB/network share. Restrict Data, Logs and backup folders to the Windows account running the server and trusted administrators. The department named DBA does not grant Windows or SQL administrator privileges.

On employee PCs, use a clean portable build and open **Start Lead Workspace.vbs**. Enter `https://YOUR-SERVER-NAME:8765` and the employee's account credentials. `LEAD_TEAM_SERVER` may set the default URL. The existing portable builder copies source/runtime files and creates empty Data/Logs/Output folders; it does not copy operational data. It requires the existing bundled browser/runtime assets to build a portable distribution.

No firewall change, certificate-trust installation, Windows service installation or automatic startup task is performed by these scripts. The running server ends when its process or Windows session ends. Remote-device access and restart persistence need deployment-specific configuration and verification.

## Working with leads

- **Lead Workspace > View: Working drafts** contains your own campaign drafts. Super Users can inspect every user's active and archived drafts through **Records > Everyone's worksheets** in the selected campaign; other people's drafts and archived drafts are read-only, with an audited inspection and an option to duplicate into the Super User's own working drafts. Create, rename, duplicate and archive sheets using the tab bar. Drafts autosave at the personal Settings interval (60 seconds by default) and before switching contexts. Reopening a saved sheet restores data and formulas. A failed save leaves the pending edits visible in memory and reports the failure; unsaved edits cannot survive a client crash.
- Import Excel/CSV into a draft, confirm the column mapping and preview, validate, correct errors, then **Review & commit valid rows**. Each draft is limited to 5,000 rows / 12 MB; use additional sheets for larger files. Only valid records are published. Committing and removing the accepted draft rows happen atomically. Network retries cannot create a second committed batch when the same request is retried.
- The five validation categories are exclusive: Valid, Duplicate, Invalid, Suppressed, Pending Review. Validation checks other users' committed leads and private drafts in the same campaign without returning their record contents or worksheet identities. Exact duplicate keys use the existing normalization; possible person/company matches require review. Domain caps count existing campaign records, including archived historical records, conservatively.
- **View** also provides Assigned / owned by me and All permitted leads, with Incoming transfers, Awaiting assignment, Transferred leads and Archived where the role permits them. These are filters in the same workspace, not separate pages. Shared records load 200 per page. The lower search box searches all permitted records in the campaign; the grid's search/filter tools operate on the loaded page. Server search does not search hidden fields.
- Use **Review / change stage** above the grid to submit validated leads, approve Operations work, record quality outcomes or approve delivery. The allowed stages are the intersection for all selected rows. **Push to Quality** and **Push to Delivery** preview readiness for every selected row, then confirm the handoff. Current validation and row versions are checked again inside the write transaction; a conflict rolls back the whole bulk action. **Incoming leads** opens the same grid's incoming filter, followed by **Assign selected** for receiving staff. Team Leads/managers can use **View: My department** for current department work. The [demo walkthrough](DEMO_WORKFLOW_GUIDE.md) explains the six local dummy accounts and sample stages.
- Incoming records are visible to receiving supervisors. Receiving employees see them only after assignment. Manual, equal-workload and round-robin assignment retain original ownership. **Return for rework** requires an active rejection reason and preserves the Lead ID. If the original employee moved departments or became inactive, work returns unassigned to the original department for supervisor handling.
- The sender's authorized supervisors can monitor their team's transferred leads but cannot edit another department's current work. Managers and Team Leads cannot browse unrelated teams merely by changing an ID.
- **More > Archive selected** is available to authorized managers/Super Users. Super Users can use **View: Archived > More > Restore selected**. Restoration resets validation and requires review again; it does not erase history or duplicate protection.
- **View History**, transfer history and attributed comments are scoped to accessible leads. Notification filters, explicit mark-as-read and double-click opening are available in the header.

## Formulas, lookup and exports

Existing formula entry, arrow-reference selection, formula menus, custom columns, undo/redo, fill and filters remain available in private sheets. **Shift+Space** selects rows and **Ctrl+Space** selects columns in the grid; text editors retain normal typing. The formula reference system remains tied to original worksheet column identities when displayed columns are moved. Formula support is the existing engine's supported catalog, not a claim of every Excel function or Excel feature.

Private sheets preserve formula expressions. Committed lead values are authoritative values, not a shared recalculating workbook. Exports emit safe values and escape spreadsheet formula injection. Clipboard copy/cut in Team mode also rechecks export permissions on the server; non-exportable cells are left blank. Pending edits are saved before copying so the exported values match the server record. Private draft autosaves preserve the current undo history. Saving committed edits clears the local undo stack at that persistence boundary; server history retains committed changes.

If a network failure or version conflict prevents saving, automatic retries stop to avoid repeated dialogs. The pending values remain visible. Use **More > Save recovery draft** to save a separate private copy once connected, or retry Save. Recovery never overwrites another session's newer version. Read/preview jobs have a Cancel control that discards their results when the current read finishes. Transactional writes are not interrupted midway.

**Populate from database** asks which columns and rows to populate every time. The default matches permitted campaign leads using Prospect LinkedIn Link for prospect details and Company Website for company details. Missing/conflicting matches are skipped. SQL Server and PostgreSQL use the existing connection/header-mapping dialog with the user's own database credentials and read-only queries; they are separate reference sources, not a replacement shared application database. No real external database was supplied for an end-to-end connection test. **Find emails** uses the accessible worksheet and the account’s Email Discovery settings, including optional company-page and search-provider lookups. Email and AI caches, and the Scraper browser profile, are isolated by account and server under the Windows local application data folder. **Scraper > Send to Lead Workspace** stages its saved results directly into a new private draft in the selected campaign; it does not publish rows before validation and commit.

Field policies support Hidden, Read Only, Edit, Approve and Export, by department, role, campaign, category or header. More specific rules win; Hidden wins ties. Default Delivery access is read-only. Computed validation/QA conclusions and ownership/workflow metadata are service-managed. Approval requires a valid lead plus approval permission. Changing permissions affects subsequent server requests; previously displayed values cannot be remotely erased from a human's memory or an already authorized export.

## Dashboard definitions

The dashboard shows Campaign name, CID, Team Lead, allocation, dates, total/qualified/disqualified/delivered leads, remaining, daily target and status. Daily target is `ceil(allocation / inclusive calendar days)`. Shared counts use distinct authoritative Lead IDs, not sheet links or transfer events. Qualified includes Quality Qualified, Transferred to Delivery, Delivery Approved and Delivered; advancing a qualified lead through Delivery therefore retains its qualification count. Disqualified counts Quality Disqualified. Rework and pending revalidation do not count as qualified. A Super User can enter a cumulative delivered campaign count; blank uses Delivered workflow records. Other roles see scoped workflow delivery counts. 

Reports provide scoped workflow/validation totals, employee workload, department counts, transfer-event volume, mean elapsed creation-to-delivery hours, active employees, today's submissions (UTC) and current quality outcomes grouped by creation date. These are operational counts, not employee performance scores. The quality-by-date report is a cohort breakdown, not a historical reconstruction of each day's validation state. Report filters use creation dates. Export produces all six report tabs after another server permission check and records the export in the audit log. Campaign charts reuse the existing chart widget.

## Migration, backup and rollback

The original pre-change backup is in `TestArtifacts/before-multiuser-20261025-023319`. The single-interface update has another source and consistent database backup in `TestArtifacts/before-unified-ui-20261025-233552`. Schema versions 1–4 add team tables, original-department tracking, validation-stage recovery and configurable default field policies. Version 4 adds department/user module permissions. They do not delete or replace legacy tables. Legacy adoption preserves original workspace files and a complete JSON snapshot including formulas, assigns stable Lead IDs, retains duplicate historical rows for review and gives no historical record an arbitrary employee owner. Super Users can recover a formula-preserving private copy through **Campaign Manager > Historical worksheets**.

After closing the old local editing session, the server operator can run:

```powershell
.\.venv\Scripts\python.exe team_server.py backup --output 'C:\LeadBackups\before-adoption.sqlite3'
.\.venv\Scripts\python.exe team_server.py adopt-legacy
```

Adoption makes a further consistent backup automatically before migration. Repeating it skips identical sources. If an already-adopted legacy source changed, adoption refuses the entire transaction and requires reconciliation. After cutover, edit adopted records in Lead Workspace; legacy workbooks are historical archives. All launch paths now use the same authenticated interface. Historical local research files remain on disk; the checked LocalResearch worksheet had zero records and no campaigns at this update. `verify_team_migration.py` tests migration against a fresh database copy and leaves the live database untouched.

For rollback, stop all clients and the server, take a final current SQLite backup, and restore the pre-change source/workspace archive plus the consistent database backup together. Preserve the current database separately so subsequent shared changes can be reconciled. Do not restore only the `.sqlite3` file while SQLite is running, and do not mix an old main database with newer WAL/SHM files. Rolling back to a backup cannot retain later shared edits automatically. No destructive rollback is run by the application.

Use `team_server.py backup --output NEW_FILENAME` for regular consistent database backups, and back up server campaign-package/reference files alongside them. Keep backups private. `Stop Team Server.bat` stops only the recorded process whose command line belongs to this installation; `Status Team Server.bat` checks the health endpoint. Health confirms the service is responding, not that remote networking or any external database is configured.
