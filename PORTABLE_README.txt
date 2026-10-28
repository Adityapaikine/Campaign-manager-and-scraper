LEAD WORKSPACE - ONE APPLICATION
================================

Copy the entire prepared portable client folder to a writable location on a
64-bit Windows PC. Keep app, scraper_engine and runtime with the launcher files.
Open Start Lead Workspace.vbs (or .bat), enter the service URL, and sign in.
Older Team Workspace and Local Research shortcuts open this same interface.

The shared service runs on the designated server PC. Start Team Server.bat and
Status Team Server.bat manage/check it. Setup Team Server.bat creates the first
Super User only when no account exists. Passwords must contain 12-256 characters.
No default password exists. Existing accounts are not overwritten by setup.

Local server URL: http://127.0.0.1:8765. Other PCs require an HTTPS URL and trusted
certificate; see MULTIUSER_SETUP.md. Do not give employees the server Data folder,
backups, logs or certificate private keys. Lead data stays behind the service.
A clean portable build excludes operational data and credentials.

One sidebar includes Scraper, Lead Workspace, Campaign Manager, Validation,
AI Center, Dashboard, Reports, Activity, Settings and Administration. Only
permitted modules appear. Administration > Module Access controls department
permissions and individual overrides. Role, record and field restrictions
still apply inside each module.

Lead Workspace uses one View filter for drafts and shared lead queues. Scraper
sends its results into a private working draft in the same window. Validate
and commit after reviewing imported data. Formulas remain in private drafts;
committed records and authorized exports contain their calculated values.

Scraper requires a local browser and manual website sign-in. Optional company
page lookups require Internet access. Broader search requires a configured
provider/API key; never distribute a completed .env file. Account-specific
browser and research caches live under the Windows local app data folder.
Local Qwen remains optional and needs its own model/runtime assets.

The prepared portable folder includes Python and dependencies. A source-only
checkout needs Setup_Combined.bat; it is not itself a self-contained package.
Create Portable Copy.bat checks browser/runtime prerequisites before building.
No automatic service start after Windows reboot is installed by these scripts.

Read USABILITY_GUIDE.md for controls, FORMULAS_GUIDE.md for formula examples and
MULTIUSER_SETUP.md for accounts, permissions, deployment, backup and recovery.
