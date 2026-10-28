# Lead Workspace: everyday controls

Open **Start Lead Workspace.vbs** and sign in. All older Team and Local Research shortcuts open the same application. The sidebar contains only modules your account may access. Scraper and the lead tools now share this window.

**27 October update:** Lead Workspace uses an Excel-style ribbon: File, Home, Data, Formulas, Review and View. **Records** and **Column view** stay above the formula bar; private worksheet tabs are at the bottom. See [EXCEL_WORKSPACE_GUIDE.md](EXCEL_WORKSPACE_GUIDE.md) for the complete current command map. Existing functions, permissions and records are preserved.

## One Lead Workspace

Choose a campaign with **Campaign** in the top bar. Use **Records** for Working drafts, Assigned / owned by me or All permitted leads. Supervisors also have Incoming transfers, Awaiting assignment and Transferred leads; Team Leads/managers have My department, and Super Users can select Archived. **Column view** separately selects which fields appear. These controls change the same grid.

Working drafts are private worksheets. Their tabs sit below the grid; use **+** or **Sheets** to create, rename, duplicate or archive them. Imports, pastes, custom columns and formulas are staged here. **Review → Commit valid rows** publishes valid rows and keeps rejected rows in the draft. Validation and duplicate checks run on the service.

Shared views load 200 records per page. **Data → Search all campaign leads** searches all permitted campaign records; **Find in sheet** and header filters operate on the loaded page. Working drafts hold up to 5,000 rows. Use more sheets for larger files.

## Scraper in the same window

Open **Scraper**, select the source and results workbook, then start extraction. The existing pause, resume, stop, browser session, extraction options, preview and activity log remain available. **Send to Lead Workspace** imports the saved results directly into a new private draft in the selected campaign. Repeated rows within that result file are skipped. Campaign-wide duplicate checks still run before commit.

Scraper access is checked before starting an action. Browser profiles and research caches are separated by signed-in account and server on this PC. A missing browser/runtime or unavailable optional Qwen model is reported when used; a visible module does not mean an external integration is configured.

## Filters, details and space

Click a header dropdown or press **Alt+Down** to search values, keep blanks, sort, or apply text/number/date conditions. Filters combine. **Clear filters** resets filtering. Numeric values sort numerically. The table retains horizontal scrolling when columns do not fit.

Use **Column view** for Lead overview, Workflow, Research, Email Finding, QA Review or All columns. **Manage columns** searches, selects, orders and saves custom views. **View → Freeze identity** keeps name/company columns beside the scrolling data. Hidden columns retain their values; exports include only fields the service permits.

Select a row and use **Details** to see its contact, validation and notes. The details panel collapses on narrower windows. The navigation button at the top left collapses the sidebar. Filters and actions wrap to readable rows; they are not squeezed into clipped controls.

## Formulas and editing

Type **=** in a draft cell, use arrow keys to pick the first input, type **+**, pick the second input, and press **Enter**. **F2** edits the expression; **Shift+arrows** extends a range; **Esc** cancels. Both the cell editor and formula bar support this.

The **ƒx Formulas** dropdown and **Shift+F3** open the supported function catalog. **Ctrl+Shift+F** focuses the formula bar, **Ctrl+D** fills down, **F9** recalculates, and **Ctrl+Z / Ctrl+Y** undo/redo. **Shift+Space** selects rows; **Ctrl+Space** selects columns. Add custom columns with **Add columns** and remove them through the Formulas menu. Standard lead fields can be hidden, but remain part of the schema.

Draft saves retain formula expressions and current undo history. Committing publishes calculated values. A committed edit records service history and resets the local undo stack. See [FORMULAS_GUIDE.md](FORMULAS_GUIDE.md) for examples and compatibility limits.

## Validation, workflow and lookup

Import Excel/CSV, map its headers, validate and review before commit. Existing TAL, suppression, duplicate and campaign-rule checks apply. Super Users manage campaign configuration and reference lists in Campaign Manager. Row and field permissions apply to bulk actions as well as individual edits.

Open **Review**, or **Home → Review and send**, for stages, assignment and **Push to Quality / Push to Delivery**. Select rows first. The preview explains missing approval or validation for each selected row; all rows must pass before sending. **Review → Incoming leads** shows unassigned handoffs in the same table. **Records: My department** focuses on current department work. **Column view: Workflow** groups identity, stage, department and assignee. Receiving employees see work after assignment. Rework and history retain the same Lead ID and owner; transfer history is under **Review → Notes and history**. See [DEMO_WORKFLOW_GUIDE.md](DEMO_WORKFLOW_GUIDE.md).

**Populate from database** asks which fields and rows to populate every time. Prospect details match Prospect LinkedIn Link; company details match Company Website. The default source is permitted campaign records. The database dropdown also supports SQL Server/PostgreSQL connections and explicit header mapping. External connections use your database credentials and read-only lookup queries.

**Find emails** uses your Email Discovery settings, worksheet evidence, and optional public company-page/search-provider lookups. AI Center retains rule suggestions, normalization, QA explanations and campaign insights, with current access checks before supplying records to a local model.

## Module permissions

A Super User opens **Administration > Module Access**, chooses a department or individual user, sets **Inherit**, **Allow** or **Deny**, then saves. An individual override wins over the department setting. Inherit removes that override. The Effective access column shows the saved result. Administration remains Super User only, and module access does not bypass field, record or workflow restrictions.

Quality and Delivery have Scraper denied by default. Departments and individual exceptions can be changed here. Use **Account > Refresh my access** to check changes immediately; the window also checks periodically. Validation permission is required to validate or commit; users can still prepare drafts with Lead Workspace access alone.

## Dashboard and exports

Dashboard retains the campaign table and charts: campaign name, CID, Team Lead, allocation, dates, total leads, qualified/disqualified/delivered leads, remaining delivery, daily target and status. The target is `ceil(allocation / (end date - start date + 1))`, including calendar weekends and both dates. For example, 100 leads over three days requires 34 per day. Super Users edit campaign plans and the cumulative delivered count in **Campaign Manager > Edit configuration**. Reports provide authorized workflow, quality and workload breakdowns.

**Export** offers All, Qualified, Disqualified, Currently filtered and Selected rows from the current draft or loaded shared page, with counts before saving. Qualified here means validation status Valid or Valid - Email Generated, distinct from Quality-department qualification on the campaign dashboard. Personal export defaults and folder come from Settings. Validation Details are included when the authorized exported records contain validation fields. Values are exported safely; hidden/non-exportable fields are omitted. Clipboard copy/cut also checks export rights on the service.

## Save, recover and start

Drafts autosave at the interval in Settings (60 seconds by default) and before context changes. Failed saves keep edits in memory; **File → Save recovery draft** creates a separate copy when connected. If Lead Workspace access is revoked, unsaved edits remain in memory, other permitted modules stay usable, and closing warns before discarding them.

**Ctrl+1** opens Scraper, **Ctrl+2** Lead Workspace, **Ctrl+3** Campaign Manager, **Ctrl+,** Settings and **F1** Help. Start/Stop/Status Team Server controls manage the service on this PC. Other computers need its configured HTTPS URL. See [MULTIUSER_SETUP.md](MULTIUSER_SETUP.md) for accounts, networking, backup and deployment.
