# Lead Workspace UI update — 21 October 2026

The existing PySide6 Windows application now follows the supplied CRM reference: a light navigation sidebar, blue actions, clearer table headings, subtle alternating rows, disposition/QA badges, and a selected-lead details panel. The shared theme also applies to the scraper, campaign manager, validation, dashboard, settings, and other existing pages.

## Compact spacing refinement

Following the spacing feedback, the lead workspace body font is now 9 pt instead of 10 pt, table headings are 8 pt instead of 9 pt, and worksheet rows are 32 pixels high instead of 38. The other application pages retain their existing text sizing.

The workspace selector, search, status filter, and actions share a compact row on wide windows. Search is limited to a useful width rather than stretching across the screen. On smaller windows the actions move to a second compact row. Column-view controls now share the Leads heading where space allows, and the lead count appears in the table footer. Reference-list status remains visible.

At 1680 × 960, the filter/action area decreased from 133 to 65 pixels high, while the table viewport grew from 496 to 675 pixels high: 21 full rows fit instead of 13. At 1120 × 740, 13 rows fit instead of 6. The comparison is recorded in `TestArtifacts/spacing_before.json` and `TestArtifacts/spacing_after.json`, with matching screenshots. No records, validation rules, export behavior, or scraping logic changed for this refinement.

The spacing refinement passed all 68 existing tests (`TestArtifacts/ui_spacing_tests.xml`) and Python compilation checks. Visual checks also covered 125% display scaling. The updated preview is `TestArtifacts/compact_lead_workspace.png`.

## Using the updated interface

1. Open **Start Lead Workspace.vbs** or **Start Lead Workspace.bat**. Close and reopen an existing instance to load the updated source.
2. Choose **Leads Workspace**, or press **Ctrl+2**.
3. The **Lead overview** view shows the existing campaign, agent, phone, disposition, and comment fields. Choose **All columns** for the complete worksheet, including full-width spreadsheet pasting.
4. Select a cell to review its lead. **Edit lead** opens a form with explicit Save changes and Cancel controls. **Edit notes** opens the form at Notes. **Recheck row** uses the existing validation workflow.
5. **Details** toggles the right panel. It initially collapses on smaller windows to leave room for the worksheet. The navigation can also collapse using the menu icon beside the page title.

All existing workspace, reference-list, validation, email-finding, scraper transfer, import/export, custom-column, undo/redo, save, and batch controls remain available. The table keeps continuous scrolling and its existing copy/paste behavior. The redesign does not add pagination, change worksheet schemas, or introduce a second lead store.

## Corrections made during review

- The Needs validation filter includes new leads that do not yet have a stored validation result.
- Empty entry rows no longer enable saved-lead actions in the validation drawer or supply a nonexistent selected lead to the main window.
- The validation drawer resets its suggested field when moving to an unvalidated lead, avoiding a stale field recommendation from the previous selection.
- A selected lead remains selected after a worksheet refresh in the same workspace; changing workspaces clears that selection.
- Empty search/filter results have a clear message and Reset action.
- The Qt filter refresh uses the current API rather than the deprecated invalidateFilter call.
- The computer check distinguishes a source installation's local virtual environment from a fully bundled portable Python runtime. A normal .venv no longer causes a false portable-runtime failure.

## Data and preferences

No existing lead records, campaign files, TAL lists, suppression lists, or scraping engine source were edited. Tests and previews use isolated synthetic workspaces.

Only these three existing display preferences were set in the working installation:

- appearance_mode: Light
- color_scheme: Professional Blue
- lead_last_view: Lead overview

The previous values are saved in `TestArtifacts/ui_display_preferences_before.json`. The original Qt source and tests are backed up in `TestArtifacts/ui-source-before-redesign-20261021-205813.zip`; the original computer-check script is in `TestArtifacts/portable_check_before_ui_review.py`.

## Verification and previews

The regression suite includes the original tests for large pastes, imports, exports, campaign workspaces, reference lists, validation, and scraper-related local behavior. New tests cover source-row selection after sorting, details-form save/cancel/undo, notes editing, busy/blank-row actions, literal imported text, retained selection, and compact/dark layouts.

Commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --junitxml=TestArtifacts/ui_redesign_tests.xml
.\.venv\Scripts\python.exe portable_check.py --ui
.\.venv\Scripts\python.exe -m compileall -q app tests portable_check.py
```

Final result: **68 tests passed**, with no failures or warnings. Test results are in `TestArtifacts/ui_redesign_tests.xml`; the successful all-page startup check is in `TestArtifacts/ui_startup_check.txt`. Python compilation checks also passed.

Screenshots use synthetic sample leads, not customer records:

- `TestArtifacts/redesigned_lead_workspace.png`
- `TestArtifacts/redesigned_laptop.png`
- `TestArtifacts/redesigned_compact.png`
- `TestArtifacts/redesigned_dark.png`
- `TestArtifacts/redesigned_scraper.png`

Desktop and compact layouts were checked at 1680 × 960, 1366 × 800, and 1120 × 740. The local virtual environment was installed from the existing requirements file so the supplied launchers can run this source copy. This does not make the folder a standalone portable-runtime distribution. Live LinkedIn scraping and Qwen inference were not exercised; the startup check reports that local Qwen model assets are absent.
