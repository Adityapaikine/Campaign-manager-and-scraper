LEAD WORKSPACE - COPY AND START
==============================

1. Copy the ENTIRE "Lead Workspace" folder to another 64-bit Windows 10/11 PC.
   Keep app, scraper_engine and runtime together with the launcher files.
   Use a writable location, such as Documents. Do not use Program Files.
2. Double-click "Start Lead Workspace.bat" (or "Start Lead Workspace.vbs").
3. Import your Excel/CSV file and use the application.

No separate Python installation, pip command, browser download or administrator
installation is needed for the prepared portable folder.

"Check This Computer.bat" checks the bundled libraries, Excel support and browser.
The startup error log is Logs/launcher.log.

The prepared package starts with fresh data and preferences. It does not contain
the original user's leads, campaigns, saved browser sign-in, API keys, or logs.
Sign in to LinkedIn manually on each PC when using the Scraper. Internet access
is still required to visit websites. Existing website access limits still apply.

Company-page email lookup works without a search API key. Optional broader API
search requires your own key: copy .env.example to .env and fill in the provider
you use. Never share a completed .env when sharing the application.

The included Qwen runtime/model is optional and is discovered from runtime/qwen.
It needs enough memory on the destination computer; the app starts without it.
If building with --without-qwen, these files will be absent.

Excel, CSV and DOCX support are included. Legacy .doc campaign documents still
require Microsoft Word or antiword on that PC. Microsoft Excel is not required
for workbook imports/exports.

New work is stored under Data, exports under Data/LeadManager/exports or Output,
and logs under Logs. Choose files outside the folder again on a new computer.
A custom external export folder or external Qwen path must be selected again.

TAL AND SUPPRESSION LISTS
Upload each list once using Leads Workspace > Reference lists. Choose the
worksheet and map its columns. The file name and saved row count are displayed
below the toolbar. The mapped rows are saved in Data/LeadManager/reference_lists
and restored automatically after restarting. The original upload file is no
longer needed. Keep Data when moving your current workspace to another PC.
Uploading another list replaces the saved list of that type and enables its
matching rule. Workspace uploads take priority over corresponding campaign lists.

Click Validate to fill QA Status and Primary Reason:
- No TAL match: Disqualified / Tal not Mapped
- Confirmed suppression match: Disqualified / Suppression matched
Suppression takes priority if both apply. Possible fuzzy matches continue to
require manual review. Results are saved with the worksheet and included in
Excel exports. Use the Disqualified filter to review these rows. Re-run Validate
after replacing a list or correcting a lead. Starting a new worksheet keeps
your saved reference lists. Creating a clean portable copy excludes saved data.

Python source files are included and editable. "Create Portable Copy.bat" creates
another clean distributable under Portable, without copying your runtime data.
Do not copy only a .py file or the .venv folder: dependencies are required.
Library licenses remain with their installed packages; Python's license is in
runtime/python/LICENSE.txt.

This package targets Windows x64, not macOS/Linux or native Windows ARM builds.
