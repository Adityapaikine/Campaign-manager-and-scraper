from __future__ import annotations

import customtkinter as ctk

from app.version import APP_NAME, APP_VERSION, BUILD_STAGE
from app.ui.shortcut_help import ShortcutHelpWindow


class InfoWindow(ctk.CTkToplevel):
    """Offline in-application guide for the major Lead Manager workflows."""

    def __init__(self, master):
        super().__init__(master)
        self.title(f"Info. — {APP_NAME}")
        self.geometry("980x760")
        self.minsize(780, 600)
        self.transient(master)
        self.resizable(True, True)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Application Info & User Guide",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text=f"{APP_NAME} v{APP_VERSION}  •  {BUILD_STAGE}",
            text_color=("gray35", "gray70"),
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))
        ctk.CTkButton(
            header,
            text="Keyboard Shortcuts",
            width=155,
            command=lambda: ShortcutHelpWindow(self),
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=(12, 0))

        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        pages = {
            "Getting Started": self._getting_started,
            "Workspace": self._workspace,
            "Campaign & Validation": self._campaign_validation,
            "Qwen / AI": self._qwen_ai,
            "Settings & Status": self._settings_status,
            "Workflow": self._workflow,
        }
        for name, builder in pages.items():
            tab = self.tabs.add(name)
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)
            scroll = ctk.CTkScrollableFrame(tab)
            scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
            scroll.grid_columnconfigure(0, weight=1)
            builder(scroll)

        footer = ctk.CTkFrame(self)
        footer.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 16))
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            footer,
            text=(
                "Tip: deterministic validation remains the final enforcement layer. "
                "Qwen is used for interpretation, suggestions, normalization and explanations."
            ),
            text_color=("gray35", "gray70"),
            wraplength=720,
            justify="left",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=10)
        ctk.CTkButton(footer, text="Close", width=100, command=self.destroy).grid(
            row=0, column=1, sticky="e", padx=14, pady=8
        )
        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(80, self.focus_force)

    @staticmethod
    def _title(parent, text: str, subtitle: str | None = None):
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=19, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(14, 4))
        if subtitle:
            ctk.CTkLabel(
                parent,
                text=subtitle,
                justify="left",
                anchor="w",
                wraplength=850,
                text_color=("gray35", "gray70"),
            ).pack(fill="x", padx=14, pady=(0, 8))

    @staticmethod
    def _section(parent, title: str, body: str):
        box = ctk.CTkFrame(parent)
        box.pack(fill="x", padx=12, pady=7)
        ctk.CTkLabel(
            box,
            text=title,
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(11, 3))
        ctk.CTkLabel(
            box,
            text=body,
            justify="left",
            anchor="w",
            wraplength=830,
        ).pack(fill="x", padx=14, pady=(0, 12))

    def _getting_started(self, parent):
        self._title(
            parent,
            "What this application does",
            "A campaign-aware B2B lead processing workspace that combines an Excel-style grid, deterministic validation and optional local Qwen assistance.",
        )
        self._section(parent, "Home", "Shows the active campaign, current lead count, Local Qwen status and quick actions. Qwen can be enabled, started or stopped here without opening a command window.")
        self._section(parent, "Hamburger menu", "Use ☰ to expand or collapse the left navigation. The menu provides Home, Leads Workspace, Campaign Manager, AI Center, Validation Summary, Dashboard, Audit & History, Mapping Templates, Diagnostics, Settings, Logs and Info.")
        self._section(parent, "Recommended first-time flow", "1. Open Campaign Manager and import/activate the campaign package.\n2. Open Leads Workspace and import or paste leads.\n3. Load additional TAL/Suppression only if needed.\n4. Run VALIDATE.\n5. Review the Validation Summary and coloured rows.\n6. Use Find Emails or AI tools if required.\n7. Export the approved data.")
        self._section(parent, "Lightweight design", "Normal startup does not require Qwen. Heavy spreadsheet/AI components are loaded only when needed, AI work runs in background workers, repeated AI results are cached, and Qwen can be stopped automatically when the application closes.")

    def _workspace(self, parent):
        self._title(parent, "Leads Workspace", "The main Excel-style working area for lead data.")
        entries = [
            ("New", "Starts a clean working session."),
            ("Import Leads", "Imports Excel/CSV/TXT lead data. Non-standard headers can be mapped to the fixed lead schema."),
            ("Paste Data", "Pastes tabular clipboard data into the worksheet."),
            ("Load Account/TAL", "Loads a Target Account List independently of the Campaign Manager when required."),
            ("Load Suppression", "Loads a suppression list independently. Email, LinkedIn, domain, company and supported name matching are available."),
            ("VALIDATE", "Runs deterministic validation in the background using configured rules, TAL, suppression, duplicates and the active campaign profile."),
            ("Validation Summary", "Opens totals, reference-list information and validation details for the selected record."),
            ("Find Emails", "Uses known/cache/public evidence according to Settings to generate or assess business-email candidates. Generated does not mean verified."),
            ("Save", "Quick-saves the current working data."),
            ("Export", "Exports the lead data in the fixed column order. Optional validation details can be written to a separate QA sheet."),
            ("Clear", "Clears the current working grid after confirmation."),
            ("Search / Filters", "Search across the worksheet or use Excel-style column filters. Issues Only, Missing Email and Status filters are available."),
            ("Pause / Resume / Cancel", "Controls long validation/email jobs while preserving completed work where possible."),
        ]
        for title, body in entries:
            self._section(parent, title, body)
        self._section(parent, "Editing the grid", "Click a cell to select it. F2 or double-click edits the cell. Tab moves right, Enter moves down, Arrow keys move the active-cell pointer, Shift extends selections, and standard copy/paste/undo/filter shortcuts are supported. Press F1 for the full shortcut reference.")

    def _campaign_validation(self, parent):
        self._title(parent, "Campaign Manager & Validation", "Campaign files are converted into a reviewed, structured profile before they are enforced.")
        self._section(parent, "Campaign Manager", "Imports a campaign ZIP or folder and classifies supported Excel/CSV/TXT/DOC/DOCX content. It extracts campaign requirements, tracks their sources, shows conflicts, and allows review before activation. Saved campaign profiles can also be deleted with the Delete Campaign button; deleting a profile does not delete the original source ZIP/folder. PDF parsing is intentionally not included.")
        self._section(parent, "Requirement reader", "The deterministic reader handles structured requirements first. If Qwen enhancement is enabled, ambiguous/unstructured specification text can be interpreted into suggested rules with confidence and source traceability.")
        self._section(parent, "Rule status", "Extracted/Confirmed rules can be used. Needs Review rules are not silently enforced. Conflicting values should be resolved before activation.")
        self._section(parent, "TAL matching", "Exact normalized domain/company matching is deterministic. Optional fuzzy TAL matching produces Possible Match / Manual Review rather than silently approving uncertain accounts.")
        self._section(parent, "Suppression", "Exact email, LinkedIn, domain and strong company matches take priority. Optional fuzzy name/company suppression produces Possible Suppression Match / Manual Review rather than automatic suppression.")
        self._section(parent, "Campaign rules", "Supported rules can include geography, industries, job-title keywords, seniority, job functions, required fields and confirmed account/domain caps. Qwen can interpret ambiguous instructions, but Python performs the final enforcement/counting.")
        self._section(parent, "Validation Preview", "Simulates campaign rules against current data before final use so the user can inspect expected Valid, Outside TAL, Suppressed, Duplicate, Manual Review and campaign-rule failure counts.")
        self._section(parent, "Duplicates", "Highest-priority exact checks are Business Email, LinkedIn URL, then First Name + Last Name + Company Domain. AI duplicate review is advisory for ambiguous cases and never silently deletes records.")

    def _qwen_ai(self, parent):
        self._title(parent, "Local Qwen / AI Center", "Qwen is optional and runs locally through the configured llama runtime.")
        self._section(parent, "Enable Qwen", "The Home switch enables or disables AI features. When disabled, the deterministic application remains fully usable.")
        self._section(parent, "Start / Stop", "Start launches the detected local runtime in the background. Stop terminates the application-managed Qwen server. Settings also provides Start, Stop, Restart and Refresh Status controls.")
        self._section(parent, "Portable runtime", "Preferred deployment is runtime\\qwen beside the application/EXE. A saved custom runtime folder can also be used. The original development-machine LLAMA folder is only a fallback, not a required hard-coded path.")
        self._section(parent, "AI Center — Campaign", "Advanced requirement reading and AI-assisted rule building convert natural-language campaign instructions into structured suggestions for human review.")
        self._section(parent, "AI Center — Data", "Smart normalization and enrichment work on unique values where possible, reuse approved local knowledge/cache, and preserve original source values."),
        self._section(parent, "AI Center — QA", "Explains validation issues, assists with repeated QA mappings and reviews ambiguous duplicate candidates. Recommendations remain advisory."),
        self._section(parent, "Campaign Intelligence", "Summarizes structured campaign counts, bottlenecks and management-facing observations without automatically changing campaign criteria."),
        self._section(parent, "Local Knowledge", "Approved mappings can be reused before asking Qwen again. Lookup order is deterministic mapping → approved local knowledge → AI cache → Qwen."),
        self._section(parent, "Evidence & confidence", "AI-derived suggestions can carry proposed value, confidence, reason, source/model and timestamp. Low-confidence or ambiguous results should remain review items.")

    def _settings_status(self, parent):
        self._title(parent, "Settings, Colours & Statuses", "Settings are persistent across application restarts.")
        self._section(parent, "Appearance", "Choose System/Light/Dark display mode and the application accent colour scheme.")
        self._section(parent, "Validation", "Control TAL/suppression requirements, fuzzy matching and validation-row colours. Default Outside TAL highlight is red and Suppression highlight is orange; users can assign their own colours.")
        self._section(parent, "Email Discovery", "Configure confidence threshold, whether existing emails may be revalidated, optional public search provider, workers, timeout, retries and discovery cache.")
        self._section(parent, "Performance & Recovery", "Configure autosave/checkpoint intervals. Large jobs use background workers and can be paused, resumed or cancelled. Interrupted sessions can be recovered from checkpoints.")
        self._section(parent, "Production & Export", "Control valid-only export, QA validation-detail worksheet and the default export folder.")
        self._section(parent, "Local Qwen", "Configure enable/on-demand/auto-start behavior, runtime folder, model/executable overrides, host/port, timeout, cache, confidence controls and stop-on-exit behavior.")
        self._section(parent, "Important row states", "Valid = passed current deterministic rules. Warning = non-blocking issue. Invalid = blocking validation problem. Suppressed = matched suppression. Outside TAL = failed required TAL. Duplicate = duplicate rule triggered. Manual Review = uncertain/possible match requiring human decision. Valid - Email Generated = otherwise valid record where an email was generated by the email engine.")
        self._section(parent, "Diagnostics", "Checks application directories, SQLite, dependencies and runtime configuration without exposing secret API keys.")
        self._section(parent, "Audit & History", "Shows imports, validations, email processing, settings changes, exports and automated field modifications for QA/troubleshooting.")

    def _workflow(self, parent):
        self._title(parent, "End-to-End Workflow", "A recommended production sequence.")
        self._section(parent, "1 — Prepare campaign", "Import the campaign package into Campaign Manager. Review extracted requirements/conflicts, confirm uncertain rules and activate the campaign.")
        self._section(parent, "2 — Load leads", "Import Excel/CSV/TXT data or paste rows into the worksheet. Review header mapping when source headers differ from the standard schema.")
        self._section(parent, "3 — Deterministic validation", "Run VALIDATE. The engine normalizes values for matching, checks required fields, TAL, suppression, duplicates, domains/URLs and active campaign rules without silently deleting failed rows.")
        self._section(parent, "4 — Review exceptions", "Use row colours, Status filters and Validation Summary to investigate Outside TAL, Suppressed, Duplicate, Invalid and Manual Review records.")
        self._section(parent, "5 — Optional Qwen assistance", "Use AI only where it adds value: ambiguous campaign text, title/industry normalization, QA explanation, enrichment suggestions, duplicate review and campaign intelligence. Cached/local knowledge is checked first.")
        self._section(parent, "6 — Email processing", "Run Find Emails for missing addresses after inexpensive exclusion checks. Pattern discovery/cache and optional public evidence are reused at company/domain level.")
        self._section(parent, "7 — QA and export", "Resolve review items, confirm final records, then Save/Export. Keep Validation Details enabled when QA/audit traceability is required.")
        self._section(parent, "8 — Close smoothly", "Normal shutdown writes a clean-session marker and can stop the application-managed Qwen server using a short graceful timeout. Active jobs are checkpointed so interrupted work can be recovered.")
