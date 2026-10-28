# Lead Workspace: Excel-style layout

The workspace now has ribbon tabs, a compact context row, a cell-address box and formula bar, a large grid, and worksheet tabs at the bottom. Existing editing, formulas, imports and authorized service operations are reused. The layout does not imply new Excel formatting, chart or macro features.

## Column views stay within reach

**Column view** and **Manage columns** are always visible above the formula bar, even when the ribbon is collapsed. Choose All columns, Lead overview, Workflow, Research, Email Finding, QA Review, or a custom view. **Records** separately selects Working drafts, My department, incoming transfers or other permitted queues.

**Manage columns** lets you search names, select/clear columns, drag them into order, choose whether to freeze identity fields, and name/save the view. Editing an existing custom view pre-fills its name. Hiding columns keeps their data. Built-in views remain available.

You can also drag grid headers. Each view remembers its own order and widths, including after reopening the application. **View → Freeze identity** keeps name/company fields visible while scrolling. **View → Fit columns to content** resizes visible columns. The optional **Details** panel starts closed to leave more room for the grid.

Letters above the named headers identify original worksheet columns. They stay stable when fields are hidden/reordered, so formulas keep their meaning. A narrowed view may show J, K, Q rather than A, B, C. Click a letter to select that column. Header filters and numbered row selectors remain available.

## Command locations

| Ribbon | Tools |
|---|---|
| File | New worksheet, recovery draft, export, validation-error export, shortcut help |
| Home | Paste, copy, cut, clear cells, add/delete custom columns, find/replace, column filter, validate and row scope, Review and send |
| Data | Import, find emails, populate from database, connection/header mapping in the populate dropdown, reference lists, validation-status filter, full-campaign search in shared views |
| Formulas | Function catalog/categories, column references, SUM/XLOOKUP, fill down/right, recalculate, show formulas, convert formulas to values, help |
| Review | Commit valid draft rows, stages, incoming leads, assignment, push to Quality/Delivery, rework, history/comments, validation summary, permitted record management |
| View | Freeze identity, save/load filter views, fit columns, collapse/expand ribbon or sidebar |

**Save**, Undo and Redo stay at the top right. **Find in sheet**, **Clear filters** and **Details** stay beside the grid. Private worksheet tabs, **+** and the **Sheets** rename/duplicate/delete menu are at the bottom; shared page navigation uses the same strip. The footer shows saved/unsaved state.

Commands follow current draft/shared context and account permissions. Imports and column-schema changes are draft operations. The service continues to enforce all record/field/workflow rules.

## Super User visibility

Super Users have access to every module, campaign, lead, field, user and department regardless of department/user module restrictions. Use **Campaign** to choose any campaign, then **Records → All leads** or **Archived leads**. **Column view → All columns** and **Clear filters** remove personal display filters; custom column layouts remain available.

**Records → Everyone's worksheets** lists all users' active and archived worksheets in the selected campaign. Tabs show the owner and archived status, with the username in the tooltip. Other people's drafts and all archived drafts open read-only; their original data and formulas remain intact. Super User inspections are audited. Copy and export remain available. **Sheets → Duplicate sheet** creates a separate editable copy in your own Working drafts, provided the campaign is running. Rename, delete, import, commit and cell/column edits cannot change an inspected read-only draft. **Working drafts** continues to show only your own active drafts. Ordinary users cannot inspect others' drafts.

The Super User **Dashboard** starts with **All campaigns**, and its selector can narrow it to the selected campaign. **Reports** also starts with all campaigns; **Report filters** can select one campaign, department, employee, stage or date range, or show archived leads. Report exports use the same filters as the displayed report. These views remain in the existing single application.

**Activity & Diagnostics → Older / Newer** browses the audit trail beyond its first 200 events. **Refresh activity** returns to the latest events. Super Users see organization-wide activity; other permitted users continue to see only their own events.

## Formulas and navigation

The address box accepts original worksheet cells such as A1. It does not reveal cells hidden by the current column view or filters. Enter a value/formula and press Enter, or use the checkmark; **ƒx** opens the function chooser.

Type `=` and use arrow keys to pick references, including after moving columns. **F2** switches text/reference navigation. **Shift+F3** opens the catalog; **Ctrl+Shift+F** focuses the formula bar; **Ctrl+D / Ctrl+R** fill down/right; **F9** recalculates. **Shift+Space / Ctrl+Space** select rows/columns. Drafts retain expressions; commits/exports use calculated values as before.

**Ctrl+F1**, the upper-right chevron, or a tab double-click collapses/expands the ribbon. Clicking a tab reveals its commands again. Column controls and the formula bar remain visible.

## Department handoffs

Open **Review**, or **Home → Review and send**, then select committed rows. Operations pushes Approved leads to Quality; Quality pushes Quality Qualified leads to Delivery. The same preview, validation, permissions and all-or-nothing selection checks remain in place.

Receiving supervisors use **Review → Incoming leads → Assign selected**, in the same grid. **Records: My department** focuses on current department work. Transfer history is under **Review → Notes and history**. See [DEMO_WORKFLOW_GUIDE.md](DEMO_WORKFLOW_GUIDE.md) for the existing dummy accounts and practice records.

**Find in sheet** filters the loaded draft/page. **Data → Search all campaign leads** searches all permitted campaign records. Header dropdowns retain text/number/date/blank filters and sorting. These search scopes remain distinct.
