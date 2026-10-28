# Saved reference lists — 21 October 2026

This update applies directly to the portable Lead Workspace folder. Close and reopen the application after updating.

Upload TAL and suppression lists using **Reference lists**. Choose a worksheet and map the columns. The application saves the mapped rows under `Data/LeadManager/reference_lists` and displays the file names and row counts. Both lists remain available after restarting, starting a new worksheet, or copying the complete workspace to another computer. The original upload files are no longer needed. Uploading a replacement changes only that list and enables its matching rule. Saved workspace uploads take priority over corresponding campaign lists.

Click **Validate** to update the worksheet:

| Condition | QA Status | Primary Reason |
| --- | --- | --- |
| No TAL match | Disqualified | Tal not Mapped |
| Confirmed suppression match | Disqualified | Suppression matched |

Suppression takes priority when both conditions apply. Existing matching rules remain in place: possible fuzzy matches require manual review. Other validation results are also written into the QA columns, so correcting a lead or replacing a list clears an outdated disqualification when validation runs again. Results are included in saved checkpoints and Excel exports. The Disqualified filter shows both exclusion categories; their separate summary counts and row colors remain available.

Validation evidence: 44 targeted tests passed, including actual Qt upload/mapping/Validate controls, Excel with an empty first worksheet, CSV uploads, restoration after source files move, saved-list relocation, replacement and failed uploads, corrupt saved-list handling, cancellation, checkpoint recovery, export, and existing import/matching regressions. The bundled runtime startup check passed for dependencies, spreadsheets, Qt and every application page. The 29 warnings are existing Qt filter API deprecations. Tests used isolated synthetic workspaces, leaving the user's saved data untouched. Screenshot and machine-readable results are in `TestArtifacts/saved_reference_validation.png`, `reference_validation_tests.xml`, and `reference_validation_audit.json`.
