# Unified Lead Workspace implementation and verification

## 27 October: Excel-style workspace

The worksheet's existing controls now use a compact ribbon (File, Home, Data, Formulas, Review, View). Records and Column view are separate, clearly labelled selectors. Column view and Manage columns remain visible when the ribbon collapses. Sheet tabs move to the bottom; Details starts closed to leave more grid space. Save/Undo/Redo remain in the quick-access strip. Review and department handoff actions are grouped on Review and reachable from Home → Review and send. No service API, data model or lead record is changed by this UI update.

Column selection now supports searching, select/clear, drag ordering and saved names. Each view retains its own order and widths. A formula-arrow bug after column reordering was fixed: reference picking follows visual order while keeping original worksheet references stable. Letter headers expose those identities; clicking a letter selects its column. The address box navigates to visible original cells without revealing hidden/filtered fields.

The full regression run passed **230 tests** (`TestArtifacts/excel-regression.xml`), followed by **18 focused UI, handoff and permission tests** after the final ribbon grouping changes (`TestArtifacts/excel-final-ui.xml`). Runs overlap. `run.py --check` passed, and the existing service health still responds with schema 4. Tests and preview rendering use isolated synthetic databases; existing demo accounts and operational records were not edited.

Previews cover draft/shared records, all command tabs, collapsed ribbons, dark mode, and widths 1120, 1366 and 1540. At 1366×768, the shared grid viewport is 360 pixels high with the ribbon open and 456 pixels collapsed; the draft viewport is 357/453. Measurements are in `TestArtifacts/excel-layout-measurements.json`; previews are `TestArtifacts/excel-*.png`. See [EXCEL_WORKSPACE_GUIDE.md](EXCEL_WORKSPACE_GUIDE.md) for current command locations. The dated sections below retain the previous service migration and demo-provisioning evidence.

Updated 26 October 2026. There is one authenticated PySide6 application. All normal, Team and Local Research shortcuts open the same login and window. The original spreadsheet, scraper, lookup, formula and chart components are reused with the shared service; no alternate research window is launched.

## Current deployment and preservation

- The service responds at `http://127.0.0.1:8765` on this PC with schema **4**. Missing and invalid sessions receive HTTP 401. Other PCs still need HTTPS/network configuration.
- The authoritative database remains `Data/LeadManager/cache/lead_manager.sqlite3`. Before demo provisioning it contained **362 leads, two campaigns, one user account and one private worksheet**. The existing account and password hash were preserved. The 26 October workflow demonstration adds **ten synthetic leads, one campaign, six dummy accounts and one private worksheet**, giving **372 leads, three campaigns, seven accounts and two worksheets**. No existing password was reset.
- All **41 existing non-migration tables** matched the immediate pre-update backup after migration. All **three historical worksheet files** matched their hashes. Database integrity is `ok` and there are zero foreign-key errors. Version 4 adds only the module-permission table and migration record.
- Source/database backup before the UI work: `TestArtifacts/before-unified-ui-20261025-233552`.
- Consistent backup immediately before the live service update: `TestArtifacts/before-unified-service-20261026-211030`.
- The old `Data/LocalResearch` files remain intact. Its checked worksheet had no lead records and its database had no campaigns requiring adoption.
- Live evidence: `TestArtifacts/unified-live-migration.json` and `TestArtifacts/unified-live-service.json`.

## Selected-lead handoffs and demonstration

The Lead Workspace now has a compact action strip above the grid: **Incoming leads**, **Review / change stage**, **Assign selected** and a department-specific **Push to Quality / Push to Delivery** button. A **Workflow** column view keeps stage, current department and assignee beside the identity fields. **My department** filters a manager or Team Lead's current department work within the existing campaign/team scope. Incoming transfers now requires an actual pending handoff, rather than showing every unassigned row.

`selection_actions` is a read-only, Leads-module-gated preview. It finds common allowed stages for the entire selection and shows each route's per-row readiness. Blocked rows prevent confirmation; selected rows are not silently skipped. Transfer checks row versions, roles, department, configured route, destination campaign access rules and current validation again in its transaction. This closes the gap where a campaign rule changed after approval. Original owner/Lead ID/history and receiving-department assignment remain unchanged.

The local server command `team_server.py create-demo` provisions six accounts in a single transaction through normal service operations, assigns them only to **DEMO-FLOW**, and creates staged fictional examples. It cannot overwrite an existing demo campaign or credential sheet and never resets an existing account. Generated credentials are kept in `Data/LeadManager/demo-accounts.txt`; they are not source fixtures or API defaults. See [DEMO_WORKFLOW_GUIDE.md](DEMO_WORKFLOW_GUIDE.md).

The pre-demo database backup is `Data/LeadManager/cache/before-demo-20261026-213916.sqlite3`. Immediately after provisioning, every preexisting row across **43 tables** was still present and unchanged; integrity was `ok`, with zero foreign-key errors. Live HTTP logins succeeded for all six accounts, each saw only DEMO-FLOW, and Operations/Quality handoff previews succeeded. These live checks did not consume the prepared practice handoffs. Evidence: `TestArtifacts/handoff-live-verification.json`.

Verification for this update: **226 tests passed** in the full regression run (`handoff-regression.xml`), followed by **9 passing focused UI/launcher tests** after the final guidance changes (`handoff-final-ui.xml`). Runs overlap. Existing imports passed `run.py --check`. Synthetic Operations, Quality, Delivery, laptop and preview-dialog screenshots are in `TestArtifacts/handoff-*.png`. The service was restarted and its authenticated endpoints and health were verified. No live web extraction, Qwen inference or external database connection was needed for this workflow update.

## One interface

The sidebar has Dashboard, Lead Workspace, Scraper, Campaign Manager, Validation Summary, AI Center, Reports, Activity & Diagnostics, Settings, Administration and Help. Only permitted modules appear. The former My Leads, Incoming Leads, Team Leads, Department Leads and My Worksheets navigation pages have been replaced by the **View** filter inside a single Lead Workspace.

Private drafts retain tabs, formulas, import/header mapping, custom columns, undo/redo, autosave and recovery. Shared filters retain paginated, server-scoped records and the existing review, assignment, transfer, rework, archive, history and comment actions. Campaign selection stays in the top bar.

Scraper is embedded in the same window with its original worker and controls. **Send to Lead Workspace** reads saved results, skips repeated rows within that workbook, and creates a private draft in the selected campaign. Validation/commit still control publication. A stop requested during the asynchronous permission check cannot start a worker afterward.

AI Center reuses rule-building, normalization, QA/explanation and campaign-insight tools. Records are fetched through current service authorization before local AI use. Email discovery again uses the account's discovery settings, including optional company-page/API lookups. Browser, email and AI caches are separated by user and server rather than opening the authoritative database from a local tool.

Personal settings, database mappings and worksheet views follow the account. Campaign validation settings remain centrally managed. Shared draft recovery and campaign-rule review have dedicated controls; unsupported local checkpoint/automatic campaign-AI settings are disabled with explanations. Export row choices are restored for the current draft/loaded page, and exported validation details contain only permitted fields.

The sidebar follows the existing blue design. Filters wrap without clipping; moving from one toolbar row to two now updates the minimum height. A compact sheet/action row leaves more space for the grid. Previews use synthetic records at desktop and laptop sizes, not live customer data.

## Module access

**Administration > Module Access** supports department defaults and individual overrides: Inherit, Allow and Deny. Individual overrides take precedence; removing an override returns to department/default behavior. Administration remains Super User only, and Super Users retain recovery access.

Scraper defaults to denied for Quality and Delivery and allowed for other departments. Activity & Diagnostics defaults to Super Users; permitted staff receive only their own audit trail. Other modules default to allowed. Module grants never remove existing campaign, role, row or field restrictions. Validation permission is required to validate or commit; Lead Workspace alone still permits draft preparation.

Every public service operation has an explicit module gate. Local Scraper actions recheck the service before starting. The client refreshes access periodically and through Account > Refresh my access. Revocation closes the restricted page and stops extraction through its normal save/stop path. A lost periodic connection pauses active extraction. Unsaved draft edits remain in memory after revocation, do not prevent access to other permitted modules, and are saved if access is restored; closing warns before discarding them.

## Other fixes

The first-account setup loop explains invalid 12–256-character passwords and retries; mismatches retry too. Existing accounts are detected before prompting, and Ctrl+C/EOF exit cleanly. Passwords remain private and hashed. The previously reported setup traceback is covered by a regression test.

## Verification

- Full regression suite: **219 passed** in `TestArtifacts/unified-regression.xml`.
- Final service/UI integration checks after export and revocation refinements: **31 passed** in `TestArtifacts/unified-final-integration.xml`.
- Final permission-editor, scraper cancellation, revocation/regrant, layout and existing usability checks: **43 passed** in `TestArtifacts/unified-final-ui.xml`.
- These test runs overlap; their counts are not additive. Coverage includes formulas/arrow references, scoped reads/writes/exports, workflow integrity, module overrides, live revocation, setup retry, all module pages, Scraper-to-draft ingestion, personal settings and export scope.
- Syntax compilation and `run.py --check` passed. The latter checks imports/dependencies; it does not claim a browser session or Qwen model is running.
- `TestArtifacts/render_team_preview.py` generated and verified the synthetic previews `unified-workspace.png`, `unified-workspace-laptop.png`, `unified-scraper.png`, `unified-dashboard.png` and `unified-module-permissions.png`.
- The current Starlette/httpx test adapter emits one non-failing deprecation warning.

## Deployment limits

The local service is verified. Remote employee connectivity, trusted HTTPS and reboot/logoff persistence are not configured or tested. No real SQL Server/PostgreSQL endpoint was supplied, and no live website extraction or Qwen inference was performed as part of this merge. Their existing engines and interfaces remain available, with normal prerequisites and permission checks. A self-contained portable build was not generated; bundled browser/model assets are still prerequisites for that build.

Formula support remains the existing supported engine catalog, not every Excel feature. Draft formulas are preserved by service saving; committed records and authorized exports contain values. Drafts are limited to 5,000 rows / 12 MB and shared pages load 200 records.

See [USABILITY_GUIDE.md](USABILITY_GUIDE.md) for the single-window workflow and [MULTIUSER_SETUP.md](MULTIUSER_SETUP.md) for accounts, permissions, networking, backup and rollback.
