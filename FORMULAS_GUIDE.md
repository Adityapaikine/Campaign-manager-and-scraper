# Formulas in Lead Workspace

The lead worksheet has a compact **ƒx Formulas** dropdown and formula bar directly above the grid. Select a cell, type a value or formula, and press **Enter** or click **✓**. The cell shows the calculated result; selecting it shows the original expression in the formula bar. **F2** edits the expression inside the cell.

In Lead Workspace, formula editing and column management belong to private worksheet drafts. Commit publishes their calculated values. Authorized exports and clipboard copies contain server-authorized values; they do not export a recalculating shared workbook. The separate local-research launcher is retired; formulas remain saved in the private draft on the service. See [MULTIUSER_SETUP.md](MULTIUSER_SETUP.md) for shared saving, recovery and field permissions.

## Quick start

1. Choose **Add columns**. Enter `column1`, `column2` and `Total`, one name per line.
2. Enter `12` and `8` in the first two new columns on the same lead row.
3. In `Total`, enter `=column1+column2`. The result is `20`.
4. Change `12` to `15`. The result becomes `23` automatically.

A name matching an existing header takes priority. If no header called `column1` exists, `column1` means the first worksheet column, including hidden columns. In the standard layout that is Date, so use numeric columns when adding numbers.

## Build a formula with arrow keys

Select the output cell and type `=`. Use the arrow keys to point to the first input cell, type `+`, then use the arrow keys to point to the second input cell. Press **Enter** to calculate. This works inside a cell and in the formula bar.

For the three adjacent custom columns above (`column1`, `column2`, `Total`), start in `Total` and press **= → Left → Left → + → Left → Enter**. With the standard 42 lead columns preceding them, the resulting expression is `=AQ1+AR1`, equivalent to `=column1+column2` on the first lead row. The result stays in `Total`; the input cells are unchanged.

- After `=`, an operator, `(` or an argument separator, arrows start picking a reference relative to the output cell. Further arrows move that reference; typing an operator begins the next one.
- The referenced cell has a blue outline. The formula bar displays the draft while you edit inside the grid.
- **Shift+arrows** extend the current reference into a range, for example after typing `=SUM(`. A range includes the original worksheet cells between its endpoints, including hidden or filtered cells; use separate references when those cells should be excluded.
- **F2 while editing** toggles between pointing to cells and moving the text cursor. Ctrl+arrows keep normal text navigation. Arrows inside quoted text or an unfinished `[Header]` edit the text.
- **Esc** cancels the draft. Arrows follow visible rows and columns, including frozen identity fields, but insert the underlying worksheet addresses so sorting does not change which lead a reference identifies.

## References and examples

| Purpose | Formula |
| --- | --- |
| Calculate from columns in the same lead | `=[Units]*[Price]` |
| Calculate ten percent of revenue | `=[Revenue]*10%` |
| Combine a name | `=TRIM([First Name])&" "&[Last Name]` |
| Clean email capitalization | `=LOWER([Business Email ID])` in a different output column |
| Conditional label | `=IF([Revenue]>=1000000,"Priority","Standard")` |
| Handle a calculation error | `=IFERROR(A1/B1,0)` |
| Sum a range | `=SUM(A1:A10)` |
| Exact lookup | `=XLOOKUP(A1,B1:B10,C1:C10,"Missing")` |
| Excel-style VLOOKUP | `=VLOOKUP(A1,B1:D10,3,FALSE)` |
| Join text | `=TEXTJOIN(" ",TRUE,[First Name],[Last Name])` |
| Display a date | `=TEXT(TODAY(),"yyyy-mm-dd")` |
| Name an intermediate calculation | `=LET(amount,100,amount*1.1)` |

Use square brackets for headers with spaces. Simple names such as `Units` also work without brackets. Use **Formulas → Insert column reference** to select a header. A formula referring to its own output cell, directly or through another formula, produces `#CYCLE!`; write transformations into a separate custom column.

`A1` means column A, original worksheet row 1. The first lead is row 1; there is no header-row offset inside the application. Hover a column heading to see its letter. The address on the left of the formula bar identifies the selected source cell. Sorting, filtering, hiding columns and freezing identity columns do not change reference identity. Use `$A$1`, `A$1` or `$A1` to lock references when filling.

Whole-column references such as `AQ:AQ` use the currently loaded lead rows. Ordinary numbers and TRUE/FALSE values are interpreted as numbers and booleans during calculation; empty cells and the application's `-` missing marker are treated as blank. Formula output is stored as a displayed string, consistent with other lead values. Dates calculate as Excel serial numbers; use TEXT to display a date. Formula values are recalculated on edits, imports, fill operations, database population, workspace loading, and F9. Volatile functions are refreshed on recalculation, not by a continuous clock.

## Find and insert functions

Open **Formulas → Insert function** or press **Shift+F3**. Search by name or filter by category. The library contains **469 function names and language forms** from the installed engine, covering math, text, logical, date/time, lookup/reference, statistical, financial, engineering, information and compatibility functions. Common functions also have quick entries in the dropdown. The formula bar completes function names entered at the beginning of an expression.

Choose a function to insert its name, then enter the arguments. Many functions have a usage example in the library. Availability is based on the installed `formulas 1.3.4` engine; this is not a claim of complete compatibility with every Excel version, function signature, add-in or workbook feature. LET and LAMBDA-based helpers are available within the engine's supported syntax; arbitrary named-function definitions are not provided.

## Shortcuts and selection operations

| Shortcut | Action |
| --- | --- |
| `=` while a cell is selected | Begin a formula in the cell |
| `F2` | Edit the selected cell's original expression |
| Arrow keys after `=` or an operator | Pick an input cell without moving the output cell |
| `Shift+arrows` while picking | Extend a reference into a range |
| `F2` while editing a formula | Toggle reference picking / text-cursor navigation |
| `Ctrl+Shift+F` | Focus/select the formula bar |
| `Shift+F3` | Browse functions |
| `Enter` in formula bar | Apply to the selected cell |
| `Esc` in formula bar | Discard the draft and show the saved value/formula |
| `F4` in formula bar | Cycle A1 → $A$1 → A$1 → $A1 for the reference at the cursor |
| `Ctrl+D` | Fill selected cells down from the top selected cell in each column |
| `Ctrl+R` | Fill selected cells right from the left selected cell in each row |
| `Ctrl+backtick` | Toggle formulas/results in the grid |
| `F9` | Recalculate formulas |
| `Ctrl+Z` / `Ctrl+Y` | Undo / redo edits, fill and column changes |

Fill adjusts relative A1 references and respects locked references. Only selected cells are changed; hidden/filter-excluded rows are not filled. Normal clipboard copy copies the displayed cells. Show formulas first if you want to copy expression text. Pasting an expression executes it at the destination as written; use Fill for automatic relative-reference adjustment.

**Formulas → Replace selected formulas with values** removes the expressions while retaining their current results. This is undoable. Prefix an equals sign with an apostrophe, for example `'=A1+B1`, to enter literal text. Imported workbooks and database lookup values are not automatically activated as worksheet formulas.

## Add and delete columns

**Add columns** appends named custom columns. **Formulas → Delete custom columns** lets you explicitly select which custom columns to remove. Deletion removes their values/formulas and updates positional references to surviving columns. References to a deleted cell become `#REF!`. Undo restores the columns, values and expressions.

The 42 standard lead fields are required by validation, imports, lookups and exports. They remain in the schema. Use **Columns** in the view toolbar to hide them or save a compact custom view. QA Status and Primary Reason are generated by validation and cannot be formula inputs or targets. Formula changes mark affected lead rows for validation again.

## Saving, exports and errors

Expressions and calculated values are saved in your private campaign draft on the service. Save recovery draft creates a separate private copy after a failed save. Existing worksheets without formula metadata open normally. Undo history remains session-only.

Excel exports and clipboard copies contain server-authorized calculated values. They do not export expression metadata or a live recalculating workbook. Private draft saving preserves executable formulas. The older Worksheet Formulas export sheet remains an historical format; importing its calculated Lead Data does not recreate formulas.

Errors are shown in the cell with a red background and an explanatory tooltip:

- `#NAME?`: an unknown function or reference.
- `#REF!`: a deleted/unavailable column, external worksheet reference or reserved validation output.
- `#CYCLE!`: a circular formula dependency.
- `#DIV/0!`, `#VALUE!`, `#N/A`, `#NUM!`: Excel-style calculation errors.
- `#SPILL!`: the expression returns multiple cells. Use a scalar result, such as `INDEX(...)`, `SUM(...)` or `TEXTJOIN(...)`, around the array calculation.

The worksheet supports one result per lead cell. Dynamic output spilling, external workbooks/sheets, VBA/macros, arbitrary named functions, INDIRECT, OFFSET, and Excel workbook formatting features are not implemented. Expressions are limited to 8,192 characters, individual ranges to 100,000 cells, and calculated text to 32,767 characters. Matrix/repetition functions also have allocation limits. Unsupported expressions show errors instead of being treated as completed calculations.
