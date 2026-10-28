from __future__ import annotations

import csv
import io
import re
import threading
import queue
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.constants import MISSING_VALUE, STANDARD_HEADERS
from app.core.data_manager import DataManager
from app.core.batch_control import BatchControl
from app.core.checkpoint_service import CheckpointService, CheckpointSnapshot
from app.core.audit_service import record_audit_change
from app.core.activity_history import record_activity
from app.core.settings_service import SettingsService
from app.core.email_finder import EmailFinder, EmailFindingResult
from app.core.reference_lists import (
    available_fields,
    detect_reference_mapping,
    load_reference_data,
)
from app.core.suppression_validator import SuppressionValidator
from app.core.tal_validator import TALValidator
from app.core.validator import ValidationEngine, ValidationResult
from app.core.campaign_manager import CampaignProfileStore
from app.core.campaign_models import CampaignProfile
from app.core.campaign_activation import build_campaign_validators
from app.ai.qwen_runtime import QwenRuntimeManager
from app.ai.ai_service import AIServiceConfig, LocalAIService
from app.excel.exporter import export_records
from app.excel.importer import detect_mapping, import_records, read_source_table
from app.ui.column_mapping_window import ColumnMappingDialog
from app.ui.data_grid import DataGrid
from app.ui.excel_filter_popup import ExcelFilterPopup, TextFilter
from app.ui.logs_window import LogsWindow
from app.ui.dashboard_window import DashboardWindow
from app.ui.audit_history_window import AuditHistoryWindow
from app.ui.ai_center_window import AICenterWindow
from app.ui.diagnostics_window import DiagnosticsWindow
from app.ui.mapping_templates_window import MappingTemplatesWindow
from app.ui.settings_window import SettingsWindow
from app.ui.shortcut_help import ShortcutHelpWindow
from app.ui.info_window import InfoWindow
from app.ui.validation_panel import ValidationSummaryWindow
from app.ui.campaign_manager_window import CampaignManagerWindow
from app.ui.theme import (
    DEFAULT_APPEARANCE_MODE,
    DEFAULT_COLOR_SCHEME,
    DEFAULT_VALIDATION_COLORS,
    get_palette,
    normalize_hex_color,
)
from app.utils.config import EXPORT_DIR
from app.utils.logger import logger


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("B2B Lead Manager — v1.2 Local AI")
        self.geometry("1500x850")
        self.minsize(1100, 700)

        self.data_manager = DataManager()
        self.validator = ValidationEngine()
        self.email_finder = EmailFinder()
        self.email_results: dict[int, EmailFindingResult] = {}
        self.minimum_email_confidence = 75
        self.revalidate_existing_emails = False
        self.email_search_enabled = False
        self.search_provider_name = "Auto"
        self.email_search_max_workers = 4
        self.email_search_timeout = 15
        self.email_search_retries = 2
        self.email_discovery_cache_days = 30
        self._email_job_running = False
        self._email_job_snapshot: list[dict[str, str]] | None = None
        self._email_job_queue: queue.Queue[tuple] = queue.Queue()
        self._validation_job_queue: queue.Queue[tuple] = queue.Queue()
        self._validation_job_snapshot: list[dict[str, str]] | None = None
        self._active_job_type: str | None = None
        self._job_control: BatchControl | None = None
        self._job_processed = 0
        self._job_total = 0
        self.autosave_interval_seconds = 60
        self.autosave_record_interval = 100
        self.checkpoint_keep_last = 5
        self.checkpoint_service = CheckpointService(keep_last=self.checkpoint_keep_last)
        self.settings_service = SettingsService()
        self.qwen_enabled = False
        self.qwen_auto_start = False
        self.qwen_folder = ""
        self.qwen_executable = ""
        self.qwen_model = ""
        self.qwen_host = "127.0.0.1"
        self.qwen_port = 8080
        self.qwen_extra_args = ""
        self.ai_features_enabled = True
        self.ai_start_on_demand = True
        self.ai_cache_enabled = True
        self.ai_cache_days = 180
        self.ai_min_confidence = 75
        self.ai_max_prompt_chars = 12000
        self.ai_max_parallel_calls = 1
        self.ai_request_timeout = 90
        self.ai_campaign_auto_read = False
        self.qwen_stop_on_exit = True
        self.qwen_runtime: QwenRuntimeManager | None = None
        self.ai_service: LocalAIService | None = None
        self._qwen_status_probe_pending = False
        self._qwen_busy = False
        self._qwen_status_text = "Qwen Off"
        self.campaign_store = CampaignProfileStore()
        self.active_campaign_profile: CampaignProfile | None = None
        self.export_valid_only = False
        self.include_validation_details = True
        self.default_export_folder = str(EXPORT_DIR)
        self.appearance_mode = DEFAULT_APPEARANCE_MODE
        self.color_scheme = DEFAULT_COLOR_SCHEME
        self.outside_tal_color = DEFAULT_VALIDATION_COLORS["outside_tal"]
        self.suppression_match_color = DEFAULT_VALIDATION_COLORS["suppressed"]
        self._dirty = False
        self.row_states: dict[int, str] = {}
        self.validation_reasons: dict[int, list[str]] = {}
        self.validation_results: dict[int, ValidationResult] = {}
        self.tal_file: str | None = None
        self.suppression_file: str | None = None
        self.tal_data = None
        self.suppression_data = None
        self.require_tal_match = True
        self.enable_suppression = True
        self.enable_tal_fuzzy_match = True
        self.enable_suppression_fuzzy_match = True
        self.validation_panel_window = None
        self.validation_panel = None
        self.validation_summary_cache = {}
        self.validation_reference_cache = {"tal_name": None, "tal_count": 0, "suppression_name": None, "suppression_count": 0}

        # Excel-style AutoFilter state. Value filters and optional text filters are
        # kept separately so a user can combine checklist values with a text rule.
        self.column_filters: dict[str, set[str]] = {}
        self.text_filters: dict[str, TextFilter] = {}
        self._filter_popup: ExcelFilterPopup | None = None
        self.issues_only_var = ctk.BooleanVar(value=False)
        self.missing_email_only_var = ctk.BooleanVar(value=False)

        self._load_persistent_settings()
        self.qwen_runtime = QwenRuntimeManager(
            folder=self.qwen_folder,
            executable=self.qwen_executable,
            model=self.qwen_model,
            host=self.qwen_host,
            port=self.qwen_port,
            extra_args=self.qwen_extra_args,
        )
        self.ai_service = LocalAIService(
            self.qwen_runtime,
            AIServiceConfig(
                enabled=bool(self.ai_features_enabled and self.qwen_enabled),
                start_on_demand=bool(self.ai_start_on_demand),
                cache_enabled=bool(self.ai_cache_enabled),
                cache_days=int(self.ai_cache_days),
                minimum_confidence=float(self.ai_min_confidence) / 100.0,
                max_prompt_chars=int(self.ai_max_prompt_chars),
                max_parallel_calls=int(self.ai_max_parallel_calls),
                request_timeout=float(self.ai_request_timeout),
            ),
        )
        ctk.set_appearance_mode(self.appearance_mode)
        self._build_layout()
        self._apply_color_scheme_to_widgets()
        active_campaign = self.campaign_store.active()
        if active_campaign is not None:
            self.activate_campaign_profile(active_campaign, silent=True)
        self.protocol("WM_DELETE_WINDOW", self._request_close)
        self.after(350, self._offer_recovery_if_available)
        self.after(self.autosave_interval_seconds * 1000, self._autosave_tick)
        self.after(900, self._refresh_qwen_status)
        if self.qwen_enabled and self.qwen_auto_start:
            self.after(800, self.start_qwen)
        logger.info("Application started")

    def _build_layout(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self._sidebar_expanded = True
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.toolbar_buttons: dict[str, ctk.CTkButton] = {}
        self.utility_buttons: dict[str, ctk.CTkButton] = {}
        self.production_buttons: dict[str, ctk.CTkButton] = {}

        # Left hamburger navigation
        self.sidebar = ctk.CTkFrame(self, width=230, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)

        sidebar_header = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        sidebar_header.grid(row=0, column=0, sticky="ew", padx=8, pady=(12, 8))
        self.hamburger_button = ctk.CTkButton(
            sidebar_header, text="☰", width=42, command=self._toggle_sidebar
        )
        self.hamburger_button.pack(side="left", padx=(0, 8))
        self.sidebar_title = ctk.CTkLabel(
            sidebar_header, text="B2B Lead Manager", font=ctk.CTkFont(size=17, weight="bold")
        )
        self.sidebar_title.pack(side="left")

        nav_items = [
            ("Home", "⌂", lambda: self._show_page("home")),
            ("Leads Workspace", "▦", lambda: self._show_page("workspace")),
            ("Campaign Manager", "◫", self.open_campaign_manager),
            ("AI Center", "✦", self.open_ai_center),
            ("Validation Summary", "✓", self.open_validation_summary),
            ("Dashboard", "▥", lambda: DashboardWindow(self)),
            ("Audit & History", "◷", lambda: AuditHistoryWindow(self)),
            ("Mapping Templates", "≡", lambda: MappingTemplatesWindow(self)),
            ("Diagnostics", "⚙", lambda: DiagnosticsWindow(self)),
            ("Info.", "ⓘ", self.open_info),
            ("Settings", "⚒", self.open_settings),
            ("Logs", "☷", lambda: LogsWindow(self)),
        ]
        for row, (label, icon, command) in enumerate(nav_items, start=1):
            button = ctk.CTkButton(
                self.sidebar, text=f"{icon}  {label}", anchor="w", height=38, command=command
            )
            button.grid(row=row, column=0, sticky="ew", padx=10, pady=3)
            button._full_text = f"{icon}  {label}"
            button._collapsed_text = icon
            self.nav_buttons[label] = button
            if label in {"Settings", "Logs"}:
                self.utility_buttons[label] = button
            if label in {"Campaign Manager", "Dashboard", "Audit & History", "Mapping Templates", "Diagnostics"}:
                self.production_buttons[label] = button

        self.sidebar.grid_rowconfigure(len(nav_items) + 1, weight=1)
        qwen_side = ctk.CTkFrame(self.sidebar)
        qwen_side.grid(row=len(nav_items)+2, column=0, sticky="ew", padx=10, pady=(8, 12))
        self.sidebar_qwen_title = ctk.CTkLabel(qwen_side, text="Local Qwen", font=ctk.CTkFont(weight="bold"))
        self.sidebar_qwen_title.pack(anchor="w", padx=10, pady=(8, 2))
        self.sidebar_qwen_status = ctk.CTkLabel(qwen_side, text="Off", anchor="w")
        self.sidebar_qwen_status.pack(fill="x", padx=10, pady=(0, 8))

        # Main shell
        self.main_shell = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_shell.grid(row=0, column=1, sticky="nsew")
        self.main_shell.grid_rowconfigure(1, weight=1)
        self.main_shell.grid_columnconfigure(0, weight=1)

        topbar = ctk.CTkFrame(self.main_shell)
        topbar.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        topbar.grid_columnconfigure(1, weight=1)
        self.page_title_label = ctk.CTkLabel(topbar, text="Home", font=ctk.CTkFont(size=20, weight="bold"))
        self.page_title_label.grid(row=0, column=0, sticky="w", padx=14, pady=10)
        self.active_campaign_label = ctk.CTkLabel(topbar, text="Campaign: None")
        self.active_campaign_label.grid(row=0, column=1, sticky="w", padx=18)
        self.top_qwen_status = ctk.CTkLabel(topbar, text="Qwen: Off")
        self.top_qwen_status.grid(row=0, column=2, sticky="e", padx=(8, 8))
        self.info_button = ctk.CTkButton(topbar, text="Info.", width=72, command=self.open_info)
        self.info_button.grid(row=0, column=3, sticky="e", padx=(0, 12), pady=7)

        self.page_container = ctk.CTkFrame(self.main_shell, fg_color="transparent")
        self.page_container.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)

        self.home_page = ctk.CTkFrame(self.page_container)
        self.workspace_page = ctk.CTkFrame(self.page_container)
        for page in (self.home_page, self.workspace_page):
            page.grid(row=0, column=0, sticky="nsew")

        self._build_home_page()
        self._build_workspace_page()
        self._show_page("home")
        self.refresh_grid()

    def _build_home_page(self) -> None:
        page = self.home_page
        page.grid_columnconfigure(0, weight=1)
        page.grid_columnconfigure(1, weight=1)
        page.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(
            page, text="Lead Operations Workspace", font=ctk.CTkFont(size=27, weight="bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=22, pady=(22, 4))
        ctk.CTkLabel(
            page, text="Import, validate, enrich and review campaign leads from one workspace.",
            text_color=("gray35", "gray70")
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=22, pady=(0, 18))

        qwen_card = ctk.CTkFrame(page)
        qwen_card.grid(row=2, column=0, sticky="nsew", padx=(22, 8), pady=8)
        qwen_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(qwen_card, text="Local Qwen AI", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4)
        )
        self.home_qwen_switch_var = ctk.BooleanVar(value=bool(self.qwen_enabled))
        self.home_qwen_switch = ctk.CTkSwitch(
            qwen_card, text="Enable Qwen", variable=self.home_qwen_switch_var, command=self._home_toggle_qwen
        )
        self.home_qwen_switch.grid(row=0, column=1, sticky="e", padx=16, pady=(14, 4))
        self.home_qwen_status = ctk.CTkLabel(qwen_card, text="Status: Off", anchor="w")
        self.home_qwen_status.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=4)
        self.home_qwen_model = ctk.CTkLabel(qwen_card, text="Model: Not detected", anchor="w", wraplength=650, justify="left")
        self.home_qwen_model.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=4)
        self.home_qwen_folder = ctk.CTkLabel(qwen_card, text="Runtime: Auto-detect", anchor="w", wraplength=650, justify="left")
        self.home_qwen_folder.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 12))
        qwen_actions = ctk.CTkFrame(qwen_card, fg_color="transparent")
        qwen_actions.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 14))
        ctk.CTkButton(qwen_actions, text="Start", width=90, command=self.start_qwen).pack(side="left", padx=(0, 6))
        ctk.CTkButton(qwen_actions, text="Stop", width=90, command=self.stop_qwen).pack(side="left", padx=6)
        ctk.CTkButton(qwen_actions, text="Qwen Settings", width=120, command=self.open_settings).pack(side="left", padx=6)

        campaign_card = ctk.CTkFrame(page)
        campaign_card.grid(row=2, column=1, sticky="nsew", padx=(8, 22), pady=8)
        campaign_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(campaign_card, text="Active Campaign", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4)
        )
        self.home_campaign_label = ctk.CTkLabel(campaign_card, text="No campaign activated", anchor="w", wraplength=620, justify="left")
        self.home_campaign_label.grid(row=1, column=0, sticky="ew", padx=16, pady=6)
        self.home_record_label = ctk.CTkLabel(campaign_card, text="Records: 0", anchor="w")
        self.home_record_label.grid(row=2, column=0, sticky="ew", padx=16, pady=6)
        ctk.CTkButton(campaign_card, text="Open Campaign Manager", command=self.open_campaign_manager).grid(
            row=3, column=0, sticky="w", padx=16, pady=(8, 14)
        )

        quick = ctk.CTkFrame(page)
        quick.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=22, pady=(8, 22))
        for col in range(5):
            quick.grid_columnconfigure(col, weight=1)
        ctk.CTkLabel(quick, text="Quick Actions", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(14, 10)
        )
        actions = [
            ("Open Leads Workspace", lambda: self._show_page("workspace")),
            ("Import Leads", self.import_leads),
            ("Campaign Manager", self.open_campaign_manager),
            ("Local Qwen AI Center", self.open_ai_center),
            ("Validate Current Data", self.validate_rows),
        ]
        for col, (label, command) in enumerate(actions):
            ctk.CTkButton(quick, text=label, command=command, height=44).grid(
                row=1, column=col, sticky="ew", padx=8, pady=(0, 16)
            )

    def _build_workspace_page(self) -> None:
        page = self.workspace_page
        page.grid_rowconfigure(3, weight=1)
        page.grid_columnconfigure(0, weight=1)

        actions = ctk.CTkFrame(page)
        actions.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 6))
        primary = [
            ("New", self.new_session), ("Import Leads", self.import_leads), ("Paste Data", self.paste_data),
            ("Load Account/TAL", self.load_tal), ("Load Suppression", self.load_suppression),
            ("Save", self.quick_save), ("Export", self.export_data), ("Clear", self.clear_rows),
        ]
        for text, command in primary:
            button = ctk.CTkButton(actions, text=text, command=command, width=110)
            button.pack(side="left", padx=3, pady=7)
            self.toolbar_buttons[text] = button

        validation_bar = ctk.CTkFrame(page)
        validation_bar.grid(row=1, column=0, sticky="ew", padx=0, pady=(0, 6))
        validation_actions = [
            ("VALIDATE", self.validate_rows), ("Validation Summary", self.open_validation_summary),
            ("Find Emails", self.find_emails), ("Campaign Manager", self.open_campaign_manager),
        ]
        for text, command in validation_actions:
            button = ctk.CTkButton(
                validation_bar, text=text, command=command, width=132,
                font=ctk.CTkFont(weight="bold") if text == "VALIDATE" else None
            )
            button.pack(side="left", padx=3, pady=7)
            self.toolbar_buttons[text] = button

        search_frame = ctk.CTkFrame(page)
        search_frame.grid(row=2, column=0, sticky="ew", padx=0, pady=(0, 6))
        ctk.CTkLabel(search_frame, text="Search:").pack(side="left", padx=(8, 4))
        self.search_var = ctk.StringVar()
        self.search_entry = ctk.CTkEntry(search_frame, textvariable=self.search_var, width=280)
        self.search_entry.pack(side="left", padx=4, pady=6)
        self.search_entry.bind("<KeyRelease>", lambda _e: self.refresh_grid())
        ctk.CTkButton(search_frame, text="Clear Filters", command=self.clear_all_filters, width=95).pack(side="left", padx=4)
        ctk.CTkCheckBox(search_frame, text="Issues Only", variable=self.issues_only_var, command=self.refresh_grid).pack(side="left", padx=5)
        ctk.CTkCheckBox(search_frame, text="Missing Email", variable=self.missing_email_only_var, command=self.refresh_grid).pack(side="left", padx=5)
        ctk.CTkLabel(search_frame, text="Status:").pack(side="left", padx=(8, 3))
        self.status_filter_var = ctk.StringVar(value="All")
        self.status_filter_menu = ctk.CTkOptionMenu(
            search_frame, variable=self.status_filter_var,
            values=["All", "Valid", "Valid - Email Generated", "Warning", "Invalid", "Suppressed", "Outside TAL", "Duplicate", "Manual Review"],
            command=lambda _value: self.refresh_grid(), width=120
        )
        self.status_filter_menu.pack(side="left", padx=(0, 4), pady=6)
        self.filter_summary_label = ctk.CTkLabel(search_frame, text="No column filters")
        self.filter_summary_label.pack(side="left", padx=6)

        self.status_label = ctk.CTkLabel(search_frame, text="Ready")
        self.status_label.pack(side="right", padx=10)
        self.cancel_job_button = ctk.CTkButton(search_frame, text="Cancel", width=66, state="disabled", command=self.cancel_active_job)
        self.cancel_job_button.pack(side="right", padx=2)
        self.resume_job_button = ctk.CTkButton(search_frame, text="Resume", width=66, state="disabled", command=self.resume_active_job)
        self.resume_job_button.pack(side="right", padx=2)
        self.pause_job_button = ctk.CTkButton(search_frame, text="Pause", width=66, state="disabled", command=self.pause_active_job)
        self.pause_job_button.pack(side="right", padx=2)
        self.job_progress = ctk.CTkProgressBar(search_frame, width=120)
        self.job_progress.set(0)
        self.job_progress.pack(side="right", padx=(4,2), pady=8)
        self.email_progress = self.job_progress

        body = ctk.CTkFrame(page)
        body.grid(row=3, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        self.grid = DataGrid(body, self._on_grid_change, on_filter_request=self.open_column_filter)
        self.grid.set_validation_colors(outside_tal=self.outside_tal_color, suppressed=self.suppression_match_color)
        self.grid.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.grid.bind("<<DeleteRows>>", lambda _e: self.delete_selected())
        self.grid.bind("<<FocusSearch>>", lambda _e: self._focus_search())
        self.grid.bind("<<QuickSave>>", lambda _e: self.quick_save())
        self.grid.bind("<<NewSession>>", lambda _e: self.new_session())
        self.grid.bind("<<ImportLeads>>", lambda _e: self.import_leads())
        self.grid.bind("<<ExportData>>", lambda _e: self.export_data())
        self.grid.bind("<<CloseWindow>>", lambda _e: self._request_close())
        self.grid.bind("<<ValidateRows>>", lambda _e: self.validate_rows())
        self.grid.bind("<<ShortcutHelp>>", lambda _e: self.show_shortcut_help())
        self.grid.bind("<<ToggleFilters>>", lambda _e: self.toggle_filters_shortcut())
        self.grid.bind("<<GridSelectionChanged>>", lambda _e: self._show_active_validation())

    def _show_page(self, name: str) -> None:
        if name == "workspace":
            self.workspace_page.tkraise()
            self.page_title_label.configure(text="Leads Workspace")
        else:
            self.home_page.tkraise()
            self.page_title_label.configure(text="Home")
            self._refresh_home_metrics()

    def _toggle_sidebar(self) -> None:
        self._sidebar_expanded = not self._sidebar_expanded
        width = 230 if self._sidebar_expanded else 62
        self.sidebar.configure(width=width)
        self.sidebar_title.configure(text="B2B Lead Manager" if self._sidebar_expanded else "")
        for button in self.nav_buttons.values():
            button.configure(
                text=button._full_text if self._sidebar_expanded else button._collapsed_text,
                anchor="w" if self._sidebar_expanded else "center",
            )
        self.sidebar_qwen_title.configure(text="Local Qwen" if self._sidebar_expanded else "AI")
        self.sidebar_qwen_status.configure(text=self._qwen_status_text if self._sidebar_expanded else "")

    def _refresh_home_metrics(self) -> None:
        if hasattr(self, "home_record_label"):
            self.home_record_label.configure(text=f"Records: {len(self.data_manager.records):,}")
        if hasattr(self, "home_campaign_label"):
            if self.active_campaign_profile:
                self.home_campaign_label.configure(
                    text=f"{self.active_campaign_profile.campaign_id} — {self.active_campaign_profile.campaign_name}"
                )
            else:
                self.home_campaign_label.configure(text="No campaign activated")

    def _home_toggle_qwen(self) -> None:
        enabled = bool(self.home_qwen_switch_var.get())
        self.qwen_enabled = enabled
        self.settings_service.set("qwen_enabled", enabled)
        self._reconfigure_ai_service()
        if enabled:
            self.start_qwen()
        else:
            self.stop_qwen()

    def _refresh_qwen_status(self, schedule: bool = True) -> None:
        if self.qwen_runtime is None:
            return
        if self._qwen_status_probe_pending:
            if schedule and self.winfo_exists():
                self.after(8000, self._refresh_qwen_status)
            return
        self._qwen_status_probe_pending = True

        def worker():
            try:
                info = self.qwen_runtime.discover(probe=bool(self.qwen_enabled))
                self.after(0, lambda: self._apply_qwen_status_info(info))
            except Exception:
                logger.exception("Qwen status refresh failed")
                self.after(0, self._apply_qwen_status_error)

        threading.Thread(target=worker, daemon=True, name="qwen-status").start()
        if schedule and self.winfo_exists():
            self.after(8000, self._refresh_qwen_status)

    def _apply_qwen_status_info(self, info) -> None:
        self._qwen_status_probe_pending = False
        enabled = bool(self.qwen_enabled)
        if not enabled:
            status = "Off"
        elif info.reachable:
            status = "Ready"
        elif info.running:
            status = "Starting"
        else:
            status = "Stopped"
        self._qwen_status_text = status
        if hasattr(self, "home_qwen_switch_var") and self.home_qwen_switch_var.get() != enabled:
            self.home_qwen_switch_var.set(enabled)
        if hasattr(self, "home_qwen_status"):
            self.home_qwen_status.configure(text=f"Status: {status} — {info.message}")
            self.home_qwen_model.configure(text=f"Model: {Path(info.model).name if info.model else 'Not detected'}")
            self.home_qwen_folder.configure(text=f"Runtime: {info.folder or 'Not detected'}")
        if hasattr(self, "top_qwen_status"):
            self.top_qwen_status.configure(text=f"Qwen: {status}")
        if hasattr(self, "sidebar_qwen_status"):
            self.sidebar_qwen_status.configure(text=status if self._sidebar_expanded else "")

    def _apply_qwen_status_error(self) -> None:
        self._qwen_status_probe_pending = False
        self._qwen_status_text = "Error"
        if hasattr(self, "top_qwen_status"):
            self.top_qwen_status.configure(text="Qwen: Error")

    def start_qwen(self) -> None:
        if self.qwen_runtime is None or self._qwen_busy:
            return
        self.qwen_enabled = True
        self.settings_service.set("qwen_enabled", True)
        self._reconfigure_ai_service()
        if hasattr(self, "home_qwen_switch_var"):
            self.home_qwen_switch_var.set(True)
        self._qwen_busy = True
        self._qwen_status_text = "Starting"
        self._refresh_qwen_ui_text("Starting Qwen...")
        def worker():
            try:
                info = self.qwen_runtime.start()
                self.after(0, lambda: self._on_qwen_action_complete(info.message))
            except Exception as exc:
                logger.exception("Could not start Qwen")
                self.after(0, lambda: self._on_qwen_action_complete(f"Start failed: {exc}"))
        threading.Thread(target=worker, daemon=True).start()

    def stop_qwen(self) -> None:
        if self.qwen_runtime is None or self._qwen_busy:
            return
        self.qwen_enabled = False
        self.settings_service.set("qwen_enabled", False)
        self._reconfigure_ai_service()
        if hasattr(self, "home_qwen_switch_var"):
            self.home_qwen_switch_var.set(False)
        self._qwen_busy = True
        def worker():
            try:
                info = self.qwen_runtime.stop()
                self.after(0, lambda: self._on_qwen_action_complete(info.message))
            except Exception as exc:
                logger.exception("Could not stop Qwen")
                self.after(0, lambda: self._on_qwen_action_complete(f"Stop failed: {exc}"))
        threading.Thread(target=worker, daemon=True).start()

    def restart_qwen(self) -> None:
        if self.qwen_runtime is None or self._qwen_busy:
            return
        self.qwen_enabled = True
        self.settings_service.set("qwen_enabled", True)
        self._reconfigure_ai_service()
        self._qwen_busy = True
        def worker():
            try:
                info = self.qwen_runtime.restart()
                self.after(0, lambda: self._on_qwen_action_complete(info.message))
            except Exception as exc:
                logger.exception("Could not restart Qwen")
                self.after(0, lambda: self._on_qwen_action_complete(f"Restart failed: {exc}"))
        threading.Thread(target=worker, daemon=True).start()

    def _on_qwen_action_complete(self, message: str) -> None:
        self._qwen_busy = False
        self._refresh_qwen_status(schedule=False)
        if hasattr(self, "status_label"):
            self._set_status(message)

    def _refresh_qwen_ui_text(self, message: str) -> None:
        if hasattr(self, "home_qwen_status"):
            self.home_qwen_status.configure(text=f"Status: {message}")
        if hasattr(self, "top_qwen_status"):
            self.top_qwen_status.configure(text=f"Qwen: {message}")

    def _reconfigure_ai_service(self) -> None:
        if self.ai_service is None or self.qwen_runtime is None:
            return
        self.ai_service.reconfigure(
            AIServiceConfig(
                enabled=bool(self.ai_features_enabled and self.qwen_enabled),
                start_on_demand=bool(self.ai_start_on_demand),
                cache_enabled=bool(self.ai_cache_enabled),
                cache_days=int(self.ai_cache_days),
                minimum_confidence=float(self.ai_min_confidence) / 100.0,
                max_prompt_chars=int(self.ai_max_prompt_chars),
                max_parallel_calls=int(self.ai_max_parallel_calls),
                request_timeout=float(self.ai_request_timeout),
            )
        )

    def configure_ai_controls(
        self, *, enabled: bool, start_on_demand: bool, cache_enabled: bool, cache_days: int,
        minimum_confidence: int, max_prompt_chars: int, max_parallel_calls: int,
        request_timeout: int, stop_on_exit: bool, campaign_auto_read: bool = False
    ) -> None:
        self.ai_features_enabled = bool(enabled)
        self.ai_start_on_demand = bool(start_on_demand)
        self.ai_cache_enabled = bool(cache_enabled)
        self.ai_cache_days = int(cache_days)
        self.ai_min_confidence = int(minimum_confidence)
        self.ai_max_prompt_chars = int(max_prompt_chars)
        self.ai_max_parallel_calls = int(max_parallel_calls)
        self.ai_request_timeout = int(request_timeout)
        self.ai_campaign_auto_read = bool(campaign_auto_read)
        self.qwen_stop_on_exit = bool(stop_on_exit)
        self.settings_service.update_many({
            "ai_features_enabled": self.ai_features_enabled,
            "ai_start_on_demand": self.ai_start_on_demand,
            "ai_cache_enabled": self.ai_cache_enabled,
            "ai_cache_days": self.ai_cache_days,
            "ai_min_confidence": self.ai_min_confidence,
            "ai_max_prompt_chars": self.ai_max_prompt_chars,
            "ai_max_parallel_calls": self.ai_max_parallel_calls,
            "ai_request_timeout": self.ai_request_timeout,
            "ai_campaign_auto_read": self.ai_campaign_auto_read,
            "qwen_stop_on_exit": self.qwen_stop_on_exit,
        })
        self._reconfigure_ai_service()

    def configure_qwen_runtime(
        self, *, folder: str, executable: str, model: str, host: str, port: int,
        extra_args: str, enabled: bool, auto_start: bool
    ) -> None:
        was_running = bool(self.qwen_runtime and self.qwen_runtime.discover(probe=False).running)
        self.qwen_folder = folder.strip()
        self.qwen_executable = executable.strip()
        self.qwen_model = model.strip()
        self.qwen_host = host.strip() or "127.0.0.1"
        self.qwen_port = int(port)
        self.qwen_extra_args = extra_args.strip()
        self.qwen_enabled = bool(enabled)
        self.qwen_auto_start = bool(auto_start)
        if self.qwen_runtime is None:
            self.qwen_runtime = QwenRuntimeManager()
        self.qwen_runtime.configure(
            folder=self.qwen_folder, executable=self.qwen_executable, model=self.qwen_model,
            host=self.qwen_host, port=self.qwen_port, extra_args=self.qwen_extra_args
        )
        self.settings_service.update_many({
            "qwen_folder": self.qwen_folder, "qwen_executable": self.qwen_executable,
            "qwen_model": self.qwen_model, "qwen_host": self.qwen_host, "qwen_port": self.qwen_port,
            "qwen_extra_args": self.qwen_extra_args, "qwen_enabled": self.qwen_enabled,
            "qwen_auto_start": self.qwen_auto_start,
        })
        self._reconfigure_ai_service()
        if self.qwen_enabled and self.qwen_auto_start and not was_running:
            self.start_qwen()
        self._refresh_qwen_status(schedule=False)

    def open_validation_summary(self) -> None:
        if self.validation_panel_window is not None and self.validation_panel_window.winfo_exists():
            self.validation_panel_window.focus()
            self.validation_panel_window.lift()
            self._refresh_validation_panel_window()
            return
        self.validation_panel_window = ValidationSummaryWindow(self)
        self.validation_panel = self.validation_panel_window.panel
        self.validation_panel_window.protocol("WM_DELETE_WINDOW", self._close_validation_summary_window)
        self._refresh_validation_panel_window()

    def _close_validation_summary_window(self) -> None:
        if self.validation_panel_window is not None and self.validation_panel_window.winfo_exists():
            self.validation_panel_window.destroy()
        self.validation_panel_window = None
        self.validation_panel = None

    def _refresh_validation_panel_window(self) -> None:
        if not self.validation_panel:
            return
        self.validation_panel.update_summary(self.validation_summary_cache or {})
        self.validation_panel.update_reference_lists(**self.validation_reference_cache)
        self._show_active_validation()

    def _update_validation_summary_display(self, summary: dict[str, int]) -> None:
        self.validation_summary_cache = dict(summary)
        if self.validation_panel:
            self.validation_panel.update_summary(self.validation_summary_cache)

    def _update_validation_reference_display(self, *, tal_name: str | None = None, tal_count: int = 0, suppression_name: str | None = None, suppression_count: int = 0) -> None:
        self.validation_reference_cache = {
            "tal_name": tal_name,
            "tal_count": tal_count,
            "suppression_name": suppression_name,
            "suppression_count": suppression_count,
        }
        if self.validation_panel:
            self.validation_panel.update_reference_lists(**self.validation_reference_cache)

    def _load_persistent_settings(self) -> None:
        defaults = {
            "require_tal_match": self.require_tal_match,
            "enable_suppression": self.enable_suppression,
            "enable_tal_fuzzy_match": self.enable_tal_fuzzy_match,
            "enable_suppression_fuzzy_match": self.enable_suppression_fuzzy_match,
            "minimum_email_confidence": self.minimum_email_confidence,
            "revalidate_existing_emails": self.revalidate_existing_emails,
            "email_search_enabled": self.email_search_enabled,
            "search_provider_name": self.search_provider_name,
            "email_search_max_workers": self.email_search_max_workers,
            "email_search_timeout": self.email_search_timeout,
            "email_search_retries": self.email_search_retries,
            "email_discovery_cache_days": self.email_discovery_cache_days,
            "autosave_interval_seconds": self.autosave_interval_seconds,
            "autosave_record_interval": self.autosave_record_interval,
            "checkpoint_keep_last": self.checkpoint_keep_last,
            "export_valid_only": self.export_valid_only,
            "include_validation_details": self.include_validation_details,
            "default_export_folder": self.default_export_folder,
            "appearance_mode": self.appearance_mode,
            "color_scheme": self.color_scheme,
            "outside_tal_color": self.outside_tal_color,
            "suppression_match_color": self.suppression_match_color,
            "qwen_enabled": self.qwen_enabled,
            "qwen_auto_start": self.qwen_auto_start,
            "qwen_folder": self.qwen_folder,
            "qwen_executable": self.qwen_executable,
            "qwen_model": self.qwen_model,
            "qwen_host": self.qwen_host,
            "qwen_port": self.qwen_port,
            "qwen_extra_args": self.qwen_extra_args,
            "ai_features_enabled": self.ai_features_enabled,
            "ai_start_on_demand": self.ai_start_on_demand,
            "ai_cache_enabled": self.ai_cache_enabled,
            "ai_cache_days": self.ai_cache_days,
            "ai_min_confidence": self.ai_min_confidence,
            "ai_max_prompt_chars": self.ai_max_prompt_chars,
            "ai_max_parallel_calls": self.ai_max_parallel_calls,
            "ai_request_timeout": self.ai_request_timeout,
            "ai_campaign_auto_read": self.ai_campaign_auto_read,
            "qwen_stop_on_exit": self.qwen_stop_on_exit,
        }
        for name, default in defaults.items():
            setattr(self, name, self.settings_service.get(name, default))
        self.outside_tal_color = normalize_hex_color(
            self.outside_tal_color, DEFAULT_VALIDATION_COLORS["outside_tal"]
        )
        self.suppression_match_color = normalize_hex_color(
            self.suppression_match_color, DEFAULT_VALIDATION_COLORS["suppressed"]
        )
        self.checkpoint_service.keep_last = int(self.checkpoint_keep_last)
        self.validator.require_tal_match = bool(self.require_tal_match)
        self.validator.enable_suppression = bool(self.enable_suppression)

    def _palette(self) -> dict[str, str]:
        return get_palette(self.color_scheme)

    def _apply_color_scheme_to_widgets(self) -> None:
        palette = self._palette()
        accent = palette["accent"]
        hover = palette["hover"]
        # Apply the selected accent consistently to interactive controls.
        for group_name in ("toolbar_buttons", "utility_buttons", "production_buttons", "nav_buttons"):
            for button in getattr(self, group_name, {}).values():
                try:
                    button.configure(fg_color=accent, hover_color=hover)
                except Exception:
                    pass
        validate = getattr(self, "toolbar_buttons", {}).get("VALIDATE")
        if validate is not None:
            try:
                validate.configure(fg_color=palette["strong"], hover_color=hover)
            except Exception:
                pass
        for button_name in ("pause_job_button", "resume_job_button"):
            button = getattr(self, button_name, None)
            if button is not None:
                try:
                    button.configure(fg_color=accent, hover_color=hover)
                except Exception:
                    pass

    def apply_appearance_settings(self, appearance_mode: str, color_scheme: str) -> None:
        mode = appearance_mode if appearance_mode in {"System", "Light", "Dark"} else DEFAULT_APPEARANCE_MODE
        self.appearance_mode = mode
        self.color_scheme = color_scheme if color_scheme in {
            "Excel Green", "Professional Blue", "Teal", "Purple", "Orange", "Slate"
        } else DEFAULT_COLOR_SCHEME
        ctk.set_appearance_mode(self.appearance_mode)
        self._apply_color_scheme_to_widgets()
        self._persist_settings()

    def _persist_settings(self) -> None:
        self.settings_service.update_many(self._checkpoint_settings())

    def show_shortcut_help(self) -> None:
        ShortcutHelpWindow(self)

    def open_campaign_manager(self) -> None:
        CampaignManagerWindow(
            self, on_activate=self.activate_campaign_profile, on_delete=self.handle_campaign_deleted,
            ai_service=self.ai_service, auto_ai_read=bool(self.ai_campaign_auto_read),
        )

    def handle_campaign_deleted(self, profile: CampaignProfile, was_active: bool) -> None:
        """Synchronize the main workspace after a saved campaign is deleted."""
        if not was_active:
            return
        if self.active_campaign_profile and self.active_campaign_profile.campaign_id != profile.campaign_id:
            return
        self.active_campaign_profile = None
        self.validator.configure_campaign(None)
        self.validator.configure_tal(None, require_match=self.require_tal_match)
        self.validator.configure_suppression(None, enabled=self.enable_suppression)
        self.tal_file = None
        self.suppression_file = None
        self.tal_data = None
        self.suppression_data = None
        if hasattr(self, "active_campaign_label"):
            self.active_campaign_label.configure(text="Campaign: None")
        self._update_validation_reference_display()
        self._invalidate_validation()
        if hasattr(self, "grid"):
            self.refresh_grid()
        self._refresh_home_metrics()
        self._set_status(f"Campaign deleted and deactivated: {profile.campaign_id}")
        record_activity(
            "campaign",
            f"Deleted campaign {profile.campaign_id}",
            {"name": profile.campaign_name, "was_active": True},
        )

    def open_ai_center(self) -> None:
        if self.ai_service is None:
            messagebox.showerror("Local Qwen", "Local AI service is not initialized.")
            return
        AICenterWindow(self)

    def activate_campaign_profile(self, profile: CampaignProfile, *, silent: bool = False) -> None:
        tal_validator, suppression_validator, warnings = build_campaign_validators(
            profile,
            tal_fuzzy_enabled=self.enable_tal_fuzzy_match,
            suppression_fuzzy_enabled=self.enable_suppression_fuzzy_match,
        )
        self.active_campaign_profile = profile
        self.validator.configure_campaign(profile)
        self.validator.configure_tal(tal_validator, require_match=self.require_tal_match)
        self.validator.configure_suppression(suppression_validator, enabled=self.enable_suppression)
        if hasattr(self, "active_campaign_label"):
            self.active_campaign_label.configure(text=f"Campaign: {profile.campaign_id} — {profile.campaign_name}")
        self._refresh_home_metrics()

        tal_file = next((item for item in profile.files if item.role == "tal"), None)
        suppression_files = [
            item for item in profile.files
            if item.role in {"client_suppression", "internal_suppression", "processed_suppression", "competitor_exclusion", "domain_suppression"}
        ]
        self._update_validation_reference_display(
            tal_name=tal_file.relative_path if tal_file else None,
            tal_count=tal_file.record_count if tal_file else 0,
            suppression_name=(f"Campaign package ({len(suppression_files)} sources)" if suppression_files else None),
            suppression_count=sum(item.record_count for item in suppression_files),
        )
        self._invalidate_validation()
        if hasattr(self, "grid"):
            self.refresh_grid()
        if warnings and not silent:
            messagebox.showwarning(
                "Campaign Activation",
                "Campaign activated with warnings:\n\n" + "\n".join(warnings[:10]),
            )
        if not silent:
            self._set_status(f"Campaign active: {profile.campaign_id} — {profile.campaign_name}; run VALIDATE")
            record_activity(
                "campaign",
                f"Activated campaign {profile.campaign_id}",
                {"name": profile.campaign_name, "warnings": warnings},
            )

    def open_info(self) -> None:
        InfoWindow(self)

    def open_settings(self) -> None:
        SettingsWindow(self)

    def apply_phase7_settings(
        self,
        *,
        require_tal_match: bool,
        enable_suppression: bool,
        enable_tal_fuzzy_match: bool = True,
        enable_suppression_fuzzy_match: bool = True,
        minimum_email_confidence: int = 75,
        revalidate_existing_emails: bool,
        email_search_enabled: bool,
        search_provider_name: str,
        email_search_max_workers: int,
        email_search_timeout: int,
        email_search_retries: int,
        email_discovery_cache_days: int,
        autosave_interval_seconds: int,
        autosave_record_interval: int,
        checkpoint_keep_last: int,
        export_valid_only: bool,
        include_validation_details: bool,
        default_export_folder: str,
        appearance_mode: str | None = None,
        color_scheme: str | None = None,
        outside_tal_color: str | None = None,
        suppression_match_color: str | None = None,
    ) -> None:
        self.apply_phase6_settings(
            require_tal_match=require_tal_match,
            enable_suppression=enable_suppression,
            minimum_email_confidence=minimum_email_confidence,
            revalidate_existing_emails=revalidate_existing_emails,
            email_search_enabled=email_search_enabled,
            search_provider_name=search_provider_name,
            email_search_max_workers=email_search_max_workers,
            email_search_timeout=email_search_timeout,
            email_search_retries=email_search_retries,
            email_discovery_cache_days=email_discovery_cache_days,
            autosave_interval_seconds=autosave_interval_seconds,
            autosave_record_interval=autosave_record_interval,
            checkpoint_keep_last=checkpoint_keep_last,
        )
        self.enable_tal_fuzzy_match = bool(enable_tal_fuzzy_match)
        self.enable_suppression_fuzzy_match = bool(enable_suppression_fuzzy_match)
        if self.validator.tal_validator is not None:
            self.validator.tal_validator.fuzzy_enabled = self.enable_tal_fuzzy_match
        if self.validator.suppression_validator is not None:
            self.validator.suppression_validator.fuzzy_enabled = self.enable_suppression_fuzzy_match
        self.export_valid_only = bool(export_valid_only)
        self.include_validation_details = bool(include_validation_details)
        self.default_export_folder = str(default_export_folder or "").strip() or str(EXPORT_DIR)
        if appearance_mode is not None or color_scheme is not None:
            self.apply_appearance_settings(
                appearance_mode or self.appearance_mode,
                color_scheme or self.color_scheme,
            )
        self.outside_tal_color = normalize_hex_color(
            outside_tal_color or self.outside_tal_color,
            DEFAULT_VALIDATION_COLORS["outside_tal"],
        )
        self.suppression_match_color = normalize_hex_color(
            suppression_match_color or self.suppression_match_color,
            DEFAULT_VALIDATION_COLORS["suppressed"],
        )
        if hasattr(self, "grid"):
            self.grid.set_validation_colors(
                outside_tal=self.outside_tal_color,
                suppressed=self.suppression_match_color,
            )
            self.refresh_grid()
        self._persist_settings()
        record_activity(
            "settings",
            "Production settings updated",
            {
                "export_valid_only": self.export_valid_only,
                "include_validation_details": self.include_validation_details,
                "default_export_folder": self.default_export_folder,
                "appearance_mode": self.appearance_mode,
                "color_scheme": self.color_scheme,
                "outside_tal_color": self.outside_tal_color,
                "suppression_match_color": self.suppression_match_color,
                "enable_tal_fuzzy_match": self.enable_tal_fuzzy_match,
                "enable_suppression_fuzzy_match": self.enable_suppression_fuzzy_match,
            },
        )

    def apply_phase6_settings(
        self,
        *,
        require_tal_match: bool,
        enable_suppression: bool,
        minimum_email_confidence: int,
        revalidate_existing_emails: bool,
        email_search_enabled: bool,
        search_provider_name: str,
        email_search_max_workers: int,
        email_search_timeout: int,
        email_search_retries: int,
        email_discovery_cache_days: int,
        autosave_interval_seconds: int,
        autosave_record_interval: int,
        checkpoint_keep_last: int,
    ) -> None:
        self.require_tal_match = bool(require_tal_match)
        self.enable_suppression = bool(enable_suppression)
        self.minimum_email_confidence = max(0, min(100, int(minimum_email_confidence)))
        self.revalidate_existing_emails = bool(revalidate_existing_emails)
        self.email_search_enabled = bool(email_search_enabled)
        self.search_provider_name = str(search_provider_name or "Auto")
        self.email_search_max_workers = max(1, min(16, int(email_search_max_workers)))
        self.email_search_timeout = max(2, min(120, int(email_search_timeout)))
        self.email_search_retries = max(0, min(6, int(email_search_retries)))
        self.email_discovery_cache_days = max(0, min(365, int(email_discovery_cache_days)))
        self.autosave_interval_seconds = max(15, min(3600, int(autosave_interval_seconds)))
        self.autosave_record_interval = max(10, min(5000, int(autosave_record_interval)))
        self.checkpoint_keep_last = max(2, min(20, int(checkpoint_keep_last)))
        self.checkpoint_service.keep_last = self.checkpoint_keep_last
        self.validator.require_tal_match = self.require_tal_match
        self.validator.enable_suppression = self.enable_suppression
        self._invalidate_validation()
        self._mark_dirty()
        self.refresh_grid()
        mode = f"{self.search_provider_name}" if self.email_search_enabled else "disabled"
        self._set_status(
            f"Settings updated; web discovery {mode}; autosave every {self.autosave_interval_seconds}s"
        )
        self._persist_settings()

    def apply_phase5_settings(
        self,
        *,
        require_tal_match: bool,
        enable_suppression: bool,
        minimum_email_confidence: int,
        revalidate_existing_emails: bool,
        email_search_enabled: bool,
        search_provider_name: str,
        email_search_max_workers: int,
        email_search_timeout: int,
        email_search_retries: int,
        email_discovery_cache_days: int,
    ) -> None:
        self.apply_phase6_settings(
            require_tal_match=require_tal_match,
            enable_suppression=enable_suppression,
            minimum_email_confidence=minimum_email_confidence,
            revalidate_existing_emails=revalidate_existing_emails,
            email_search_enabled=email_search_enabled,
            search_provider_name=search_provider_name,
            email_search_max_workers=email_search_max_workers,
            email_search_timeout=email_search_timeout,
            email_search_retries=email_search_retries,
            email_discovery_cache_days=email_discovery_cache_days,
            autosave_interval_seconds=self.autosave_interval_seconds,
            autosave_record_interval=self.autosave_record_interval,
            checkpoint_keep_last=self.checkpoint_keep_last,
        )

    # Backward-compatible callback names for earlier phase code/tests.
    def apply_phase4_settings(
        self,
        *,
        require_tal_match: bool,
        enable_suppression: bool,
        minimum_email_confidence: int,
        revalidate_existing_emails: bool,
    ) -> None:
        self.apply_phase5_settings(
            require_tal_match=require_tal_match,
            enable_suppression=enable_suppression,
            minimum_email_confidence=minimum_email_confidence,
            revalidate_existing_emails=revalidate_existing_emails,
            email_search_enabled=self.email_search_enabled,
            search_provider_name=self.search_provider_name,
            email_search_max_workers=self.email_search_max_workers,
            email_search_timeout=self.email_search_timeout,
            email_search_retries=self.email_search_retries,
            email_discovery_cache_days=self.email_discovery_cache_days,
        )

    def apply_phase3_settings(self, *, require_tal_match: bool, enable_suppression: bool) -> None:
        self.apply_phase4_settings(
            require_tal_match=require_tal_match,
            enable_suppression=enable_suppression,
            minimum_email_confidence=self.minimum_email_confidence,
            revalidate_existing_emails=self.revalidate_existing_emails,
        )

    def toggle_filters_shortcut(self) -> None:
        """Excel Ctrl+Shift+L equivalent for the always-filterable grid."""
        if self.column_filters or self.text_filters:
            self.clear_all_filters()
            return
        # The grid permanently exposes filter arrows. With no active filter,
        # Ctrl+Shift+L opens the active column's filter menu instead of hiding
        # the controls, which keeps the fixed Lead Manager header available.
        self.grid._open_active_filter()

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _checkpoint_references(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.tal_data is not None:
            payload["tal"] = {
                "path": self.tal_data.source_path,
                "mapping": dict(self.tal_data.mapping),
            }
        if self.suppression_data is not None:
            payload["suppression"] = {
                "path": self.suppression_data.source_path,
                "mapping": dict(self.suppression_data.mapping),
            }
        return payload

    def _checkpoint_settings(self) -> dict[str, object]:
        return {
            "require_tal_match": self.require_tal_match,
            "enable_suppression": self.enable_suppression,
            "enable_tal_fuzzy_match": self.enable_tal_fuzzy_match,
            "enable_suppression_fuzzy_match": self.enable_suppression_fuzzy_match,
            "minimum_email_confidence": self.minimum_email_confidence,
            "revalidate_existing_emails": self.revalidate_existing_emails,
            "email_search_enabled": self.email_search_enabled,
            "search_provider_name": self.search_provider_name,
            "email_search_max_workers": self.email_search_max_workers,
            "email_search_timeout": self.email_search_timeout,
            "email_search_retries": self.email_search_retries,
            "email_discovery_cache_days": self.email_discovery_cache_days,
            "autosave_interval_seconds": self.autosave_interval_seconds,
            "autosave_record_interval": self.autosave_record_interval,
            "checkpoint_keep_last": self.checkpoint_keep_last,
            "export_valid_only": self.export_valid_only,
            "include_validation_details": self.include_validation_details,
            "default_export_folder": self.default_export_folder,
            "appearance_mode": self.appearance_mode,
            "color_scheme": self.color_scheme,
            "outside_tal_color": self.outside_tal_color,
            "suppression_match_color": self.suppression_match_color,
            "qwen_enabled": self.qwen_enabled,
            "qwen_auto_start": self.qwen_auto_start,
            "qwen_folder": self.qwen_folder,
            "qwen_executable": self.qwen_executable,
            "qwen_model": self.qwen_model,
            "qwen_host": self.qwen_host,
            "qwen_port": self.qwen_port,
            "qwen_extra_args": self.qwen_extra_args,
            "ai_features_enabled": self.ai_features_enabled,
            "ai_start_on_demand": self.ai_start_on_demand,
            "ai_cache_enabled": self.ai_cache_enabled,
            "ai_cache_days": self.ai_cache_days,
            "ai_min_confidence": self.ai_min_confidence,
            "ai_max_prompt_chars": self.ai_max_prompt_chars,
            "ai_max_parallel_calls": self.ai_max_parallel_calls,
            "ai_request_timeout": self.ai_request_timeout,
            "ai_campaign_auto_read": self.ai_campaign_auto_read,
            "qwen_stop_on_exit": self.qwen_stop_on_exit,
        }

    def _job_checkpoint_payload(self, state: str | None = None) -> dict[str, object]:
        if not self._active_job_type:
            return {}
        return {
            "type": self._active_job_type,
            "state": state or (
                "paused" if self._job_control and self._job_control.paused else "running"
            ),
            "processed": self._job_processed,
            "total": self._job_total,
        }

    def _save_checkpoint(
        self,
        *,
        reason: str,
        clean_shutdown: bool = False,
        records: list[dict[str, str]] | None = None,
        job: dict[str, object] | None = None,
    ) -> None:
        try:
            self.checkpoint_service.save(
                records=[dict(row) for row in (records if records is not None else self.data_manager.records)],
                row_states=dict(self.row_states),
                validation_reasons={k: list(v) for k, v in self.validation_reasons.items()},
                references=self._checkpoint_references(),
                settings=self._checkpoint_settings(),
                job=job if job is not None else self._job_checkpoint_payload(),
                clean_shutdown=clean_shutdown,
                reason=reason,
            )
            self._dirty = False
        except Exception:
            logger.exception("Checkpoint save failed | reason=%s", reason)

    def _autosave_tick(self) -> None:
        try:
            if self.data_manager.records and (self._dirty or self._active_job_type):
                self._save_checkpoint(reason="autosave")
        finally:
            self.after(max(15, self.autosave_interval_seconds) * 1000, self._autosave_tick)

    def _offer_recovery_if_available(self) -> None:
        if self.data_manager.records:
            return
        snapshot = self.checkpoint_service.latest_recoverable()
        if snapshot is None:
            return
        job = snapshot.job
        job_text = ""
        if job.get("type"):
            job_text = (
                f"\n\nInterrupted job: {job.get('type')} "
                f"({int(job.get('processed', 0)):,}/{int(job.get('total', 0)):,})"
            )
        recover = messagebox.askyesno(
            "Recover Previous Session",
            f"A recoverable session with {snapshot.record_count:,} record(s) was found.{job_text}\n\n"
            "Recover it now?",
        )
        if not recover:
            # Write a clean empty marker so the same declined crash snapshot does
            # not prompt on every subsequent launch.
            try:
                self.checkpoint_service.mark_current_session_clean(records=[])
            except Exception:
                logger.exception("Could not dismiss recovery checkpoint")
            return
        self._restore_checkpoint(snapshot)

    def _restore_checkpoint(self, snapshot: CheckpointSnapshot) -> None:
        payload = snapshot.payload
        settings = payload.get("settings") or {}
        for name in (
            "require_tal_match", "enable_suppression", "enable_tal_fuzzy_match",
            "enable_suppression_fuzzy_match", "minimum_email_confidence",
            "revalidate_existing_emails", "email_search_enabled", "search_provider_name",
            "email_search_max_workers", "email_search_timeout", "email_search_retries",
            "email_discovery_cache_days", "autosave_interval_seconds",
            "autosave_record_interval", "checkpoint_keep_last",
            "export_valid_only", "include_validation_details", "default_export_folder",
            "appearance_mode", "color_scheme", "outside_tal_color", "suppression_match_color",
            "qwen_enabled", "qwen_auto_start", "qwen_folder", "qwen_executable",
            "qwen_model", "qwen_host", "qwen_port", "qwen_extra_args",
            "ai_features_enabled", "ai_start_on_demand", "ai_cache_enabled", "ai_cache_days",
            "ai_min_confidence", "ai_max_prompt_chars", "ai_max_parallel_calls",
            "ai_request_timeout", "ai_campaign_auto_read", "qwen_stop_on_exit",
        ):
            if name in settings:
                setattr(self, name, settings[name])
        self.outside_tal_color = normalize_hex_color(
            self.outside_tal_color, DEFAULT_VALIDATION_COLORS["outside_tal"]
        )
        self.suppression_match_color = normalize_hex_color(
            self.suppression_match_color, DEFAULT_VALIDATION_COLORS["suppressed"]
        )
        self.checkpoint_service.keep_last = int(self.checkpoint_keep_last)
        self.validator.require_tal_match = bool(self.require_tal_match)
        self.validator.enable_suppression = bool(self.enable_suppression)
        if self.qwen_runtime is not None:
            self.qwen_runtime.configure(
                folder=self.qwen_folder, executable=self.qwen_executable, model=self.qwen_model,
                host=self.qwen_host, port=int(self.qwen_port), extra_args=self.qwen_extra_args
            )
        self._reconfigure_ai_service()
        ctk.set_appearance_mode(self.appearance_mode)
        self._apply_color_scheme_to_widgets()
        if hasattr(self, "grid"):
            self.grid.set_validation_colors(
                outside_tal=self.outside_tal_color,
                suppressed=self.suppression_match_color,
            )

        self.data_manager.replace_all(payload.get("records") or [], source_name="Recovered Session")
        self.row_states = {int(k): str(v) for k, v in (payload.get("row_states") or {}).items()}
        self.validation_reasons = {
            int(k): list(v) for k, v in (payload.get("validation_reasons") or {}).items()
        }
        self.validation_results.clear()
        self.email_results.clear()

        refs = payload.get("references") or {}
        self._restore_reference_from_checkpoint(refs.get("tal"), "tal")
        self._restore_reference_from_checkpoint(refs.get("suppression"), "suppression")
        self._update_validation_reference_display(
            tal_name=self.tal_data.source_name if self.tal_data else None,
            tal_count=self.tal_data.count if self.tal_data else 0,
            suppression_name=self.suppression_data.source_name if self.suppression_data else None,
            suppression_count=self.suppression_data.count if self.suppression_data else 0,
        )
        self._dirty = True
        self.refresh_grid()
        self._set_status(f"Recovered {len(self.data_manager.records):,} record(s) from checkpoint")
        logger.info("Recovered checkpoint: %s", snapshot.path)

        job = snapshot.job
        if job.get("type") in {"validation", "email"} and job.get("state") in {
            "running", "paused", "cancel_requested", "interrupted"
        }:
            resume = messagebox.askyesno(
                "Resume Interrupted Job",
                f"The recovered session contains an interrupted {job.get('type')} job.\n\n"
                "Resume it now? Cached completed work will be reused.",
            )
            if resume:
                if job.get("type") == "validation":
                    self.after(100, self.validate_rows)
                else:
                    self.after(100, self.find_emails)

    def _restore_reference_from_checkpoint(self, info: object, kind: str) -> None:
        if not isinstance(info, dict):
            return
        path = str(info.get("path") or "")
        mapping = info.get("mapping") or {}
        if not path or not Path(path).exists():
            return
        try:
            data = load_reference_data(path, kind, dict(mapping))
            if kind == "tal":
                self.tal_file = path
                self.tal_data = data
                self.validator.configure_tal(
                    TALValidator(data, fuzzy_enabled=self.enable_tal_fuzzy_match),
                    require_match=self.require_tal_match,
                )
            else:
                self.suppression_file = path
                self.suppression_data = data
                self.validator.configure_suppression(
                    SuppressionValidator(data, fuzzy_enabled=self.enable_suppression_fuzzy_match),
                    enabled=self.enable_suppression
                )
        except Exception:
            logger.exception("Could not restore %s reference list from %s", kind, path)

    def _set_background_job_running(
        self, running: bool, *, job_type: str | None = None, control: BatchControl | None = None
    ) -> None:
        if running:
            self._active_job_type = job_type
            self._job_control = control
            self._job_processed = 0
            self.pause_job_button.configure(state="normal")
            self.resume_job_button.configure(state="disabled")
            self.cancel_job_button.configure(state="normal")
        else:
            self._active_job_type = None
            self._job_control = None
            self._job_processed = 0
            self._job_total = 0
            self.pause_job_button.configure(state="disabled")
            self.resume_job_button.configure(state="disabled")
            self.cancel_job_button.configure(state="disabled")
            self.job_progress.set(0)

        locked_buttons = {
            "New", "Import Leads", "Paste Data", "Load Account/TAL",
            "Load Suppression", "VALIDATE", "Find Emails", "Clear",
        }
        for name, button in getattr(self, "toolbar_buttons", {}).items():
            if name in locked_buttons:
                button.configure(state="disabled" if running else "normal")
        settings_button = getattr(self, "utility_buttons", {}).get("Settings")
        if settings_button is not None:
            settings_button.configure(state="disabled" if running else "normal")

    def pause_active_job(self) -> None:
        if not self._job_control or not self._active_job_type:
            return
        self._job_control.pause()
        self.pause_job_button.configure(state="disabled")
        self.resume_job_button.configure(state="normal")
        self._set_status(f"{self._active_job_type.title()} paused at {self._job_processed:,}/{self._job_total:,}")
        self._save_checkpoint(reason="job-paused", job=self._job_checkpoint_payload("paused"))

    def resume_active_job(self) -> None:
        if not self._job_control or not self._active_job_type:
            return
        self._job_control.resume()
        self.pause_job_button.configure(state="normal")
        self.resume_job_button.configure(state="disabled")
        self._set_status(f"{self._active_job_type.title()} resumed")

    def cancel_active_job(self) -> None:
        if not self._job_control or not self._active_job_type:
            return
        if not messagebox.askyesno(
            "Cancel Job",
            "Cancel the active job? Already completed work will be retained where possible.",
        ):
            return
        self._job_control.cancel()
        self.pause_job_button.configure(state="disabled")
        self.resume_job_button.configure(state="disabled")
        self.cancel_job_button.configure(state="disabled")
        self._set_status(f"Cancelling {self._active_job_type}... waiting for current operation to stop")
        self._save_checkpoint(
            reason="job-cancel-requested",
            job=self._job_checkpoint_payload("cancel_requested"),
        )

    def _request_close(self) -> None:
        if self._active_job_type:
            if not messagebox.askyesno(
                "Close Application",
                "A background job is still running. Close now and recover/resume from the latest checkpoint next time?",
            ):
                return
            if self._job_control:
                self._job_control.cancel()
            self._save_checkpoint(
                reason="closed-during-job",
                clean_shutdown=False,
                job=self._job_checkpoint_payload("interrupted"),
            )
            try:
                if self.qwen_runtime and self.qwen_stop_on_exit:
                    self.qwen_runtime.shutdown_quick()
            except Exception:
                logger.exception("Could not stop Qwen during shutdown")
            self.destroy()
            return
        # A normal close only needs a tiny clean-shutdown marker. The periodic
        # autosave checkpoints already protect crash recovery; rewriting thousands
        # of lead rows during every normal exit would make closing feel slow.
        try:
            self.checkpoint_service.mark_current_session_clean(records=[])
        except Exception:
            logger.exception("Could not write clean shutdown marker")
        try:
            if self.qwen_runtime and self.qwen_stop_on_exit:
                self.qwen_runtime.shutdown_quick()
        except Exception:
            logger.exception("Could not stop Qwen during shutdown")
        self.destroy()

    def _set_status(self, text: str) -> None:
        self.status_label.configure(text=text)
        self.update_idletasks()

    def _invalidate_email_results(self) -> None:
        self.email_results.clear()

    def _invalidate_validation(self) -> None:
        """Clear stale batch results after data/reference/settings changes."""
        self.row_states.clear()
        self.validation_reasons.clear()
        self.validation_results.clear()
        if hasattr(self, "status_filter_var") and self.status_filter_var.get() != "All":
            self.status_filter_var.set("All")
        self._update_validation_summary_display({})
        self._show_active_validation()

    def _show_active_validation(self) -> None:
        if not self.validation_panel:
            return
        row_id = self.grid.active_row_index
        if row_id is None or not (0 <= row_id < len(self.data_manager.records)):
            self.validation_panel.show_record(None, None, [])
            return
        result = self.validation_results.get(row_id)
        self.validation_panel.show_record(
            row_id + 1,
            self.row_states.get(row_id),
            self.validation_reasons.get(row_id, []),
            tal_status=result.tal_status if result else None,
            tal_reason=result.tal_reason if result else None,
            suppression_status=result.suppression_status if result else None,
            suppression_reason=result.suppression_reason if result else None,
            duplicate_status=result.duplicate_status if result else None,
            email_result=self.email_results.get(row_id),
        )

    @staticmethod
    def _normalized_filter_value(value: object) -> str:
        text = "" if value is None else str(value).strip()
        return text if text else MISSING_VALUE

    def _active_filter_headers(self) -> set[str]:
        return set(self.column_filters) | set(self.text_filters)

    def _active_filter_columns(self) -> set[int]:
        result: set[int] = set()
        for header in self._active_filter_headers():
            try:
                result.add(STANDARD_HEADERS.index(header))
            except ValueError:
                continue
        return result

    def _record_matches(
        self,
        row: dict[str, str],
        *,
        row_index: int | None = None,
        exclude_header: str | None = None,
    ) -> bool:
        query = self.search_var.get().strip().casefold() if hasattr(self, "search_var") else ""
        if query and not any(query in str(value).casefold() for value in row.values()):
            return False

        status_filter = self.status_filter_var.get() if hasattr(self, "status_filter_var") else "All"
        if status_filter != "All":
            if row_index is None or self.row_states.get(row_index) != status_filter:
                return False

        if self.missing_email_only_var.get():
            email = self._normalized_filter_value(row.get("Business Email ID", MISSING_VALUE))
            if email != MISSING_VALUE:
                return False

        if self.issues_only_var.get():
            if row_index is None or self.row_states.get(row_index, "") in {"", "Valid", "Valid - Email Generated"}:
                return False

        for header, allowed_values in self.column_filters.items():
            if header == exclude_header:
                continue
            value = self._normalized_filter_value(row.get(header, MISSING_VALUE))
            if value not in allowed_values:
                return False

        for header, rule in self.text_filters.items():
            if header == exclude_header:
                continue
            value = self._normalized_filter_value(row.get(header, MISSING_VALUE))
            if not rule.matches(value):
                return False

        return True

    def _filter_values_for_column(self, header: str) -> list[str]:
        values = {
            self._normalized_filter_value(row.get(header, MISSING_VALUE))
            for index, row in enumerate(self.data_manager.records)
            if self._record_matches(row, row_index=index, exclude_header=header)
        }
        # Preserve already selected values even if another filter currently hides
        # them, so opening and confirming a filter never silently discards choices.
        values.update(self.column_filters.get(header, set()))
        return sorted(values, key=lambda value: (value == MISSING_VALUE, value.casefold()))

    def open_column_filter(self, column: int, x: int, y: int) -> None:
        if not (0 <= column < len(STANDARD_HEADERS)):
            return
        header = STANDARD_HEADERS[column]
        if self._filter_popup is not None and self._filter_popup.winfo_exists():
            self._filter_popup.destroy()

        popup = ExcelFilterPopup(
            self,
            column_name=header,
            values=self._filter_values_for_column(header),
            active_values=self.column_filters.get(header),
            active_text_filter=self.text_filters.get(header),
            x=x,
            y=y,
            on_apply=lambda values, text_rule, h=header: self._apply_column_filter(h, values, text_rule),
            on_clear=lambda h=header: self._clear_column_filter(h),
            on_sort_ascending=lambda c=column: self._sort_records_by_column(c, descending=False),
            on_sort_descending=lambda c=column: self._sort_records_by_column(c, descending=True),
        )
        self._filter_popup = popup

    def _apply_column_filter(
        self,
        header: str,
        selected_values: set[str] | None,
        text_filter: TextFilter | None,
    ) -> None:
        if selected_values is None:
            self.column_filters.pop(header, None)
        else:
            self.column_filters[header] = set(selected_values)

        if text_filter is None or not text_filter.value:
            self.text_filters.pop(header, None)
        else:
            self.text_filters[header] = text_filter

        self.grid.set_filtered_columns(self._active_filter_columns())
        self.refresh_grid()
        self._set_status(f'Filter updated: {header}')
        logger.info(
            "Column filter updated | column=%s | checked_values=%s | text_filter=%s",
            header,
            None if selected_values is None else len(selected_values),
            text_filter,
        )

    def _clear_column_filter(self, header: str) -> None:
        self.column_filters.pop(header, None)
        self.text_filters.pop(header, None)
        self.grid.set_filtered_columns(self._active_filter_columns())
        self.refresh_grid()
        self._set_status(f'Filter cleared: {header}')
        logger.info("Column filter cleared | column=%s", header)

    def clear_all_filters(self) -> None:
        has_quick = (
            self.issues_only_var.get()
            or self.missing_email_only_var.get()
            or self.status_filter_var.get() != "All"
        )
        if not self.column_filters and not self.text_filters and not has_quick:
            return
        self.column_filters.clear()
        self.text_filters.clear()
        self.issues_only_var.set(False)
        self.missing_email_only_var.set(False)
        self.status_filter_var.set("All")
        self.grid.set_filtered_columns(set())
        self.refresh_grid()
        self._set_status("All filters cleared")
        logger.info("All filters cleared")

    @staticmethod
    def _parse_number(value: str) -> float | None:
        cleaned = value.strip().replace(",", "").replace("$", "").replace("%", "")
        if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", cleaned):
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _parse_date(value: str) -> datetime | None:
        for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue
        return None

    def _sort_records_by_column(self, column: int, *, descending: bool) -> None:
        if not (0 <= column < len(STANDARD_HEADERS)):
            return
        header = STANDARD_HEADERS[column]

        decorated = [
            (
                record,
                self.row_states.get(index),
                self.validation_reasons.get(index),
                self.validation_results.get(index),
                self.email_results.get(index),
            )
            for index, record in enumerate(self.data_manager.records)
        ]
        non_missing: list[tuple[dict[str, str], str | None, list[str] | None, ValidationResult | None, EmailFindingResult | None]] = []
        missing: list[tuple[dict[str, str], str | None, list[str] | None, ValidationResult | None, EmailFindingResult | None]] = []
        for item in decorated:
            value = self._normalized_filter_value(item[0].get(header, MISSING_VALUE))
            (missing if value == MISSING_VALUE else non_missing).append(item)

        values = [self._normalized_filter_value(item[0].get(header, MISSING_VALUE)) for item in non_missing]
        date_mode = header in {"Date", "Audited Date"} and all(self._parse_date(v) is not None for v in values)
        numeric_mode = bool(values) and all(self._parse_number(v) is not None for v in values)

        if date_mode:
            key = lambda item: self._parse_date(self._normalized_filter_value(item[0].get(header))) or datetime.min
        elif numeric_mode:
            key = lambda item: self._parse_number(self._normalized_filter_value(item[0].get(header))) or 0.0
        else:
            key = lambda item: self._normalized_filter_value(item[0].get(header)).casefold()

        non_missing.sort(key=key, reverse=descending)
        ordered = non_missing + missing  # Excel-like: blanks remain at the bottom.
        self.data_manager.records = [item[0] for item in ordered]
        self.row_states = {
            index: item[1]
            for index, item in enumerate(ordered)
            if item[1] is not None
        }
        self.validation_reasons = {
            index: item[2]
            for index, item in enumerate(ordered)
            if item[2] is not None
        }
        self.validation_results = {
            index: item[3]
            for index, item in enumerate(ordered)
            if item[3] is not None
        }
        self.email_results = {
            index: item[4]
            for index, item in enumerate(ordered)
            if item[4] is not None
        }
        self._mark_dirty()
        self.refresh_grid()
        direction = "Z to A" if descending else "A to Z"
        self._set_status(f"Sorted {header}: {direction}")
        logger.info("Sorted records | column=%s | descending=%s", header, descending)

    def _on_cell_change(self, index: int, column: str, value: str) -> None:
        self.data_manager.update_cell(index, column, value)
        self._invalidate_email_results()
        self._invalidate_validation()
        self._mark_dirty()
        logger.info("Cell edited | row=%s | column=%s", index + 1, column)

    def _on_grid_change(
        self,
        matrix: list[list[str]],
        row_ids: list[int | None],
        event_name: str,
    ) -> None:
        changed_rows: set[int] = set()
        assigned_new_ids: list[tuple[int, int]] = []

        for display_row, values in enumerate(matrix):
            padded = list(values[: len(STANDARD_HEADERS)])
            if len(padded) < len(STANDARD_HEADERS):
                padded.extend([MISSING_VALUE] * (len(STANDARD_HEADERS) - len(padded)))
            incoming = dict(zip(STANDARD_HEADERS, padded, strict=False))

            row_id = row_ids[display_row] if display_row < len(row_ids) else None
            if row_id is None or not (0 <= row_id < len(self.data_manager.records)):
                if not self.grid._row_has_user_data(padded):
                    continue
                self.data_manager.append_record(incoming, source_name="Manual Entry")
                row_id = len(self.data_manager.records) - 1
                assigned_new_ids.append((display_row, row_id))
                changed_rows.add(row_id)
                continue

            record = self.data_manager.records[row_id]
            row_changed = False
            for column in STANDARD_HEADERS:
                old_value = record.get(column, MISSING_VALUE)
                new_value = incoming.get(column, MISSING_VALUE)
                if str(old_value) != str(new_value):
                    self.data_manager.update_cell(row_id, column, new_value)
                    row_changed = True
            if row_changed:
                changed_rows.add(row_id)

        for display_row, row_id in assigned_new_ids:
            self.grid.set_row_id(display_row, row_id)

        if assigned_new_ids:
            self.after_idle(self.refresh_grid)

        if changed_rows:
            # Pattern learning and duplicate state are batch-wide, so edits can
            # change results for other rows too. Invalidate prior derived results.
            self._invalidate_email_results()
            self._invalidate_validation()
            self._mark_dirty()

        # Sorting is now performed centrally by the filter menu so the data model,
        # validation state and filters remain synchronized.
        if changed_rows:
            self._set_status(
                f"Updated {len(changed_rows):,} row(s) via spreadsheet ({event_name})"
            )
            logger.info(
                "Spreadsheet edit | event=%s | changed_rows=%s | total_rows=%s",
                event_name,
                len(changed_rows),
                len(self.data_manager.records),
            )

    def new_session(self) -> None:
        if self.data_manager.records and not messagebox.askyesno(
            "New", "Start a new session and clear current rows?"
        ):
            return
        self.data_manager.clear()
        self.row_states.clear()
        self.validation_reasons.clear()
        self.validation_results.clear()
        self.email_results.clear()
        self.column_filters.clear()
        self.text_filters.clear()
        self.issues_only_var.set(False)
        self.missing_email_only_var.set(False)
        self.status_filter_var.set("All")
        self.tal_file = None
        self.suppression_file = None
        self.tal_data = None
        self.suppression_data = None
        self.validator.configure_tal(None)
        self.validator.configure_suppression(None)
        self.validator.configure_campaign(self.active_campaign_profile)
        if self.active_campaign_profile is not None:
            tal_validator, suppression_validator, _warnings = build_campaign_validators(
                self.active_campaign_profile,
                tal_fuzzy_enabled=self.enable_tal_fuzzy_match,
                suppression_fuzzy_enabled=self.enable_suppression_fuzzy_match,
            )
            self.validator.configure_tal(tal_validator, require_match=self.require_tal_match)
            self.validator.configure_suppression(suppression_validator, enabled=self.enable_suppression)
        self.grid.set_filtered_columns(set())
        self.refresh_grid()
        self._update_validation_summary_display({})
        self._update_validation_reference_display()
        self._show_active_validation()
        self._dirty = False
        try:
            self.checkpoint_service.mark_current_session_clean(records=[])
        except Exception:
            logger.exception("Could not reset recovery marker for new session")
        logger.info("New session created")

    def clear_rows(self) -> None:
        if not self.data_manager.records:
            return
        if messagebox.askyesno("Clear", "Clear all rows from the working grid?"):
            self.new_session()

    def import_leads(self) -> None:
        path = filedialog.askopenfilename(
            title="Import lead data",
            filetypes=[("Excel / CSV", "*.xlsx *.xlsm *.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            df = read_source_table(path)
            columns = [str(column) for column in df.columns]
            detected = detect_mapping(columns)
            dialog = ColumnMappingDialog(
                self,
                title="Confirm Lead Import Column Mapping",
                columns=columns,
                target_fields=list(STANDARD_HEADERS),
                detected_mapping=detected,
                template_kind="lead",
            )
            mapping = dialog.show()
            if mapping is None:
                self._set_status("Lead import cancelled")
                return
            rows, mapping = import_records(path, manual_mapping=mapping)
            added = self.data_manager.extend(rows, source_name=Path(path).name)
            if added:
                self._invalidate_email_results()
                self._invalidate_validation()
                self._mark_dirty()
            self.refresh_grid()
            self._set_status(f"Imported {added:,} rows")
            record_activity(
                "import",
                f"Imported {added:,} lead record(s)",
                {"file": Path(path).name, "mapping": mapping},
            )
            logger.info("Imported %s records from %s | mapping=%s", added, path, mapping)
        except Exception as exc:
            logger.exception("Import failed: %s", path)
            messagebox.showerror("Import failed", str(exc))

    def _focus_search(self) -> None:
        self.search_entry.focus_set()
        self.search_entry.select_range(0, "end")

    def _read_clipboard_matrix(self) -> list[list[str]]:
        try:
            raw = self.clipboard_get()
        except Exception:
            messagebox.showwarning("Paste", "Clipboard does not contain text data.")
            return []
        if not raw.strip():
            return []
        return list(csv.reader(io.StringIO(raw), delimiter="\t"))

    def paste_into_grid(self) -> None:
        """Compatibility path for explicit paste actions; Ctrl+V is native tksheet."""
        parsed = self._read_clipboard_matrix()
        if not parsed:
            return

        start_col = self.grid.paste_start_column
        active_row = self.grid.active_row_index
        if active_row is None:
            self._append_parsed_clipboard(parsed)
            return

        visible = self.grid.visible_indices()
        try:
            visible_start = visible.index(active_row)
        except ValueError:
            visible_start = 0

        rows_touched = 0
        cells_touched = 0
        for row_offset, values in enumerate(parsed):
            visible_pos = visible_start + row_offset
            if visible_pos < len(visible):
                target_index = visible[visible_pos]
            else:
                self.data_manager.append_record({}, source_name="Manual Entry")
                target_index = len(self.data_manager.records) - 1
                visible.append(target_index)

            changed_this_row = False
            for col_offset, value in enumerate(values):
                col_index = start_col + col_offset
                if col_index >= len(STANDARD_HEADERS):
                    break
                column = STANDARD_HEADERS[col_index]
                self.data_manager.update_cell(target_index, column, value)
                changed_this_row = True
                cells_touched += 1

            if changed_this_row:
                rows_touched += 1

        if rows_touched:
            self._invalidate_email_results()
            self._invalidate_validation()
            self._mark_dirty()
        self.refresh_grid()
        self._set_status(f"Pasted {cells_touched:,} cells into {rows_touched:,} row(s)")
        logger.info(
            "Direct grid paste | rows=%s | cells=%s | start_row=%s | start_col=%s",
            rows_touched,
            cells_touched,
            active_row + 1,
            start_col + 1,
        )

    def _append_parsed_clipboard(self, parsed: list[list[str]]) -> None:
        recognized = detect_mapping(parsed[0]) if parsed else {}
        rows: list[dict[str, str]] = []
        if len(recognized) >= 2:
            header_row = parsed[0]
            mapping = detect_mapping(header_row)
            for values in parsed[1:]:
                row = {h: MISSING_VALUE for h in STANDARD_HEADERS}
                for idx, source_header in enumerate(header_row):
                    target = mapping.get(source_header)
                    if target and idx < len(values):
                        row[target] = values[idx]
                rows.append(row)
        else:
            start = self.grid.paste_start_column
            for values in parsed:
                row = {h: MISSING_VALUE for h in STANDARD_HEADERS}
                for offset, value in enumerate(values):
                    col_index = start + offset
                    if col_index < len(STANDARD_HEADERS):
                        row[STANDARD_HEADERS[col_index]] = value
                rows.append(row)

        added = self.data_manager.extend(rows, source_name="Manual Entry")
        if added:
            self._invalidate_email_results()
            self._invalidate_validation()
            self._mark_dirty()
        self.refresh_grid()
        self._set_status(f"Pasted {added:,} rows")
        logger.info("Pasted %s rows from clipboard", added)

    def paste_data(self) -> None:
        parsed = self._read_clipboard_matrix()
        if parsed:
            self._append_parsed_clipboard(parsed)

    def _choose_reference_mapping(self, path: str, kind: str) -> dict[str, str] | None:
        df = read_source_table(path)
        columns = [str(column) for column in df.columns]
        detected = detect_reference_mapping(columns, kind)
        dialog = ColumnMappingDialog(
            self,
            title=("Confirm Account/TAL Column Mapping" if kind == "tal" else "Confirm Suppression Column Mapping"),
            columns=columns,
            target_fields=available_fields(kind),
            detected_mapping=detected,
            required_any={"Company Name", "Domain"} if kind == "tal" else set(),
            template_kind=kind,
        )
        return dialog.show()

    def load_tal(self) -> None:
        path = filedialog.askopenfilename(
            title="Load Account/TAL List",
            filetypes=[("Excel / CSV", "*.xlsx *.xlsm *.csv *.txt *.tsv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            mapping = self._choose_reference_mapping(path, "tal")
            if mapping is None:
                self._set_status("TAL load cancelled")
                return
            data = load_reference_data(path, "tal", mapping)
            self.tal_file = path
            self.tal_data = data
            self.validator.configure_tal(TALValidator(data, fuzzy_enabled=self.enable_tal_fuzzy_match), require_match=self.require_tal_match)
            self._invalidate_validation()
            self._mark_dirty()
            self._update_validation_reference_display(
                tal_name=data.source_name,
                tal_count=data.count,
                suppression_name=self.suppression_data.source_name if self.suppression_data else None,
                suppression_count=self.suppression_data.count if self.suppression_data else 0,
            )
            self.refresh_grid()
            logger.info("TAL loaded | file=%s | records=%s | mapping=%s", path, data.count, mapping)
            record_activity(
                "tal", f"Loaded TAL with {data.count:,} account(s)",
                {"file": data.source_name, "mapping": mapping},
            )
            self._set_status(f"TAL loaded: {data.count:,} account(s) — run VALIDATE")
        except Exception as exc:
            logger.exception("TAL load failed: %s", path)
            messagebox.showerror("TAL load failed", str(exc))

    def load_suppression(self) -> None:
        path = filedialog.askopenfilename(
            title="Load Suppression List",
            filetypes=[("Excel / CSV", "*.xlsx *.xlsm *.csv *.txt *.tsv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            mapping = self._choose_reference_mapping(path, "suppression")
            if mapping is None:
                self._set_status("Suppression load cancelled")
                return
            data = load_reference_data(path, "suppression", mapping)
            self.suppression_file = path
            self.suppression_data = data
            self.validator.configure_suppression(
                SuppressionValidator(data, fuzzy_enabled=self.enable_suppression_fuzzy_match), enabled=self.enable_suppression
            )
            self._invalidate_validation()
            self._mark_dirty()
            self._update_validation_reference_display(
                tal_name=self.tal_data.source_name if self.tal_data else None,
                tal_count=self.tal_data.count if self.tal_data else 0,
                suppression_name=data.source_name,
                suppression_count=data.count,
            )
            self.refresh_grid()
            logger.info(
                "Suppression loaded | file=%s | records=%s | mapping=%s",
                path,
                data.count,
                mapping,
            )
            record_activity(
                "suppression", f"Loaded suppression list with {data.count:,} record(s)",
                {"file": data.source_name, "mapping": mapping},
            )
            self._set_status(f"Suppression loaded: {data.count:,} record(s) — run VALIDATE")
        except Exception as exc:
            logger.exception("Suppression load failed: %s", path)
            messagebox.showerror("Suppression load failed", str(exc))

    def validate_rows(self) -> None:
        if self._active_job_type:
            messagebox.showinfo(
                "Validate",
                f"A {self._active_job_type} job is already running. Pause/cancel it before starting validation.",
            )
            return
        if not self.data_manager.records:
            messagebox.showinfo("Validate", "There are no lead records to validate.")
            return

        self.validator.require_tal_match = self.require_tal_match
        self.validator.enable_suppression = self.enable_suppression
        snapshot = [dict(record) for record in self.data_manager.records]
        self._validation_job_snapshot = snapshot
        control = BatchControl()
        self._job_total = len(snapshot)
        self._set_background_job_running(True, job_type="validation", control=control)
        self._job_total = len(snapshot)
        self.job_progress.set(0)
        self._set_status(f"Validation started: 0/{len(snapshot):,}")
        self._save_checkpoint(
            reason="validation-started",
            records=snapshot,
            job={"type": "validation", "state": "running", "processed": 0, "total": len(snapshot)},
        )

        while not self._validation_job_queue.empty():
            try:
                self._validation_job_queue.get_nowait()
            except queue.Empty:
                break

        checkpoint_context = {
            "references": self._checkpoint_references(),
            "settings": self._checkpoint_settings(),
        }

        def progress(done: int, total: int) -> None:
            self._validation_job_queue.put(("progress", done, total))
            if done % max(10, self.autosave_record_interval) == 0:
                try:
                    self.checkpoint_service.save(
                        records=snapshot,
                        references=checkpoint_context["references"],
                        settings=checkpoint_context["settings"],
                        job={
                            "type": "validation", "state": "running",
                            "processed": done, "total": total,
                        },
                        reason="validation-progress",
                    )
                except Exception:
                    logger.exception("Validation progress checkpoint failed")

        def worker() -> None:
            try:
                results = self.validator.validate_records(
                    snapshot,
                    control=control,
                    progress_callback=progress,
                    progress_interval=25,
                )
                cancelled = bool(self.validator.last_run_cancelled)
                self._validation_job_queue.put(("done", results, None, snapshot, cancelled))
            except Exception as exc:
                logger.exception("Background validation failed")
                self._validation_job_queue.put(("done", None, exc, snapshot, False))

        threading.Thread(target=worker, daemon=True, name="phase6-validation").start()
        self.after(60, self._poll_validation_job_queue)

    def _poll_validation_job_queue(self) -> None:
        if self._active_job_type != "validation":
            return
        got_done = False
        while True:
            try:
                message = self._validation_job_queue.get_nowait()
            except queue.Empty:
                break
            if message[0] == "progress":
                _, done, total = message
                self._job_processed = int(done)
                self._job_total = int(total)
                self.job_progress.set((done / total) if total else 0)
                self.status_label.configure(text=f"Validating {done:,}/{total:,} ({(done / total * 100) if total else 0:.1f}%)")
            elif message[0] == "done":
                _, results, error, snapshot, cancelled = message
                got_done = True
                self._finish_validation_job(results, error, snapshot, cancelled)
                break
        if self._active_job_type == "validation" and not got_done:
            self.after(60, self._poll_validation_job_queue)

    def _finish_validation_job(
        self,
        results: list[ValidationResult] | None,
        error: Exception | None,
        snapshot: list[dict[str, str]],
        cancelled: bool,
    ) -> None:
        try:
            if error is not None:
                messagebox.showerror("Validation failed", str(error))
                self._set_status("Validation failed")
                return
            if results is None:
                self._set_status("Validation ended without results")
                return
            if self.data_manager.records != snapshot:
                messagebox.showwarning(
                    "Validation",
                    "Worksheet data changed while validation was running. Results were not applied. Run VALIDATE again.",
                )
                self._set_status("Validation results discarded because worksheet data changed")
                return

            self.row_states.clear()
            self.validation_reasons.clear()
            self.validation_results.clear()
            summary = {
                "Total Records": len(self.data_manager.records),
                "Valid": 0, "Warnings": 0, "Invalid": 0, "Suppressed": 0,
                "Outside TAL": 0, "Duplicates": 0, "Missing Email": 0,
                "Emails Found": 0, "Manual Review": 0,
            }
            for index, result in enumerate(results):
                record = self.data_manager.records[index]
                self.row_states[index] = result.status
                self.validation_reasons[index] = list(result.reasons)
                self.validation_results[index] = result
                status_key = {
                    "Valid": "Valid", "Valid - Email Generated": "Valid",
                    "Warning": "Warnings", "Invalid": "Invalid",
                    "Suppressed": "Suppressed", "Outside TAL": "Outside TAL",
                    "Manual Review": "Manual Review",
                }.get(result.status)
                if status_key:
                    summary[status_key] += 1
                if result.duplicate_status == "Exact Duplicate":
                    summary["Duplicates"] += 1
                if record.get("Business Email ID", MISSING_VALUE) == MISSING_VALUE:
                    summary["Missing Email"] += 1
                else:
                    summary["Emails Found"] += 1

            # For a cancelled run, unprocessed rows are intentionally left without
            # derived state. This preserves completed work without pretending the
            # remainder was validated.
            if len(results) < len(self.data_manager.records):
                for record in self.data_manager.records[len(results):]:
                    if record.get("Business Email ID", MISSING_VALUE) == MISSING_VALUE:
                        summary["Missing Email"] += 1
                    else:
                        summary["Emails Found"] += 1

            self._update_validation_summary_display(summary)
            self.refresh_grid()
            self._show_active_validation()
            processed = len(results)
            self._job_processed = processed
            self._mark_dirty()
            if cancelled:
                self._set_status(
                    f"Validation cancelled: {processed:,}/{len(snapshot):,} processed; completed results retained"
                )
                logger.info("Validation cancelled | processed=%s | total=%s", processed, len(snapshot))
            else:
                self._set_status(f"Phase-7 validation complete: {processed:,} records")
                logger.info("Phase-7 validation completed | summary=%s", summary)
            record_activity(
                "validation",
                "Validation cancelled" if cancelled else "Validation completed",
                {"processed": processed, "total": len(snapshot), "summary": summary},
            )
        finally:
            self._validation_job_snapshot = None
            self._set_background_job_running(False)
            if self.data_manager.records:
                self._save_checkpoint(reason="validation-finished", job={})

    def _set_email_job_running(self, running: bool) -> None:
        self._email_job_running = running
        if running:
            control = self._job_control or BatchControl()
            self._set_background_job_running(True, job_type="email", control=control)
        elif self._active_job_type == "email":
            self._set_background_job_running(False)

    def _email_progress_update(self, done: int, total: int, domain: str, status: str) -> None:
        if not self._email_job_running:
            return
        self._job_processed = int(done)
        # Discovery is stage one of the email job. Reserve the last 35% of the
        # progress bar for per-row generation/application preparation.
        fraction = (done / total) if total else 0
        self.job_progress.set(max(0.0, min(0.65, fraction * 0.65)))
        self.status_label.configure(
            text=f"Email discovery {done:,}/{total:,}: {domain} — {status}"
        )

    def _email_row_progress_update(self, done: int, total: int) -> None:
        if not self._email_job_running:
            return
        self._job_processed = int(done)
        self._job_total = int(total)
        if self.email_search_enabled:
            fraction = 0.65 + 0.35 * ((done / total) if total else 0)
        else:
            fraction = (done / total) if total else 0
        self.job_progress.set(max(0.0, min(1.0, fraction)))
        self.status_label.configure(
            text=f"Email processing {done:,}/{total:,} ({(done / total * 100) if total else 0:.1f}%)"
        )

    def find_emails(self) -> None:
        if self._active_job_type:
            messagebox.showinfo(
                "Find Emails",
                f"A {self._active_job_type} job is already running. Pause/cancel it before starting another job.",
            )
            return
        if not self.data_manager.records:
            messagebox.showinfo("Find Emails", "There are no lead records to process.")
            return

        snapshot = [dict(record) for record in self.data_manager.records]
        self._email_job_snapshot = snapshot
        self._job_control = BatchControl()
        self._set_email_job_running(True)
        control = self._job_control
        self._job_total = len(snapshot)
        self._job_processed = 0
        self.job_progress.set(0)
        self._set_status(
            "Phase-6 email engine: learning cache and discovering public patterns..."
            if self.email_search_enabled
            else "Email engine: learning/cached patterns (public search disabled)..."
        )
        self._save_checkpoint(
            reason="email-job-started",
            records=snapshot,
            job={"type": "email", "state": "running", "processed": 0, "total": len(snapshot)},
        )

        while not self._email_job_queue.empty():
            try:
                self._email_job_queue.get_nowait()
            except queue.Empty:
                break

        checkpoint_context = {
            "references": self._checkpoint_references(),
            "settings": self._checkpoint_settings(),
        }

        def progress(done: int, total: int, domain: str, status: str) -> None:
            self._email_job_queue.put(("progress", done, total, domain, status))
            if done % max(10, self.autosave_record_interval) == 0:
                try:
                    self.checkpoint_service.save(
                        records=snapshot,
                        references=checkpoint_context["references"],
                        settings=checkpoint_context["settings"],
                        job={
                            "type": "email", "state": "running",
                            "stage": "domain-discovery", "processed": done, "total": total,
                        },
                        reason="email-discovery-progress",
                    )
                except Exception:
                    logger.exception("Email discovery checkpoint failed")

        def row_progress(done: int, total: int) -> None:
            self._email_job_queue.put(("row_progress", done, total))
            if done % max(10, self.autosave_record_interval) == 0:
                try:
                    self.checkpoint_service.save(
                        records=snapshot,
                        references=checkpoint_context["references"],
                        settings=checkpoint_context["settings"],
                        job={
                            "type": "email", "state": "running",
                            "stage": "row-generation", "processed": done, "total": total,
                        },
                        reason="email-row-progress",
                    )
                except Exception:
                    logger.exception("Email row checkpoint failed")

        def worker() -> None:
            try:
                # Inexpensive exclusions are also moved off the Tk thread in Phase 6.
                baseline_results = self.validator.validate_records(
                    snapshot, control=control, progress_interval=250
                )
                if self.validator.last_run_cancelled:
                    self._email_job_queue.put(("done", [], None, snapshot, True))
                    return
                blocked_statuses = {
                    index: result.status
                    for index, result in enumerate(baseline_results)
                    if result.status in {"Suppressed", "Outside TAL", "Duplicate"}
                }
                results = self.email_finder.find_missing(
                    snapshot,
                    minimum_confidence=self.minimum_email_confidence,
                    revalidate_existing=self.revalidate_existing_emails,
                    blocked_statuses=blocked_statuses,
                    enable_web_search=self.email_search_enabled,
                    search_provider_name=self.search_provider_name,
                    max_workers=self.email_search_max_workers,
                    request_timeout_seconds=self.email_search_timeout,
                    retries=self.email_search_retries,
                    discovery_cache_days=self.email_discovery_cache_days,
                    progress_callback=progress,
                    row_progress_callback=row_progress,
                    control=control,
                    progress_interval=50,
                )
                cancelled = bool(self.email_finder.last_run_cancelled or control.cancelled)
            except Exception as exc:
                logger.exception("Phase-6 email processing failed")
                self._email_job_queue.put(("done", None, exc, snapshot, False))
                return
            self._email_job_queue.put(("done", results, None, snapshot, cancelled))

        # Phase-5 worker name retained for backward compatibility; Phase 6 adds controls/recovery.
        threading.Thread(target=worker, daemon=True, name="phase5-email-discovery").start()
        self.after(60, self._poll_email_job_queue)

    def _poll_email_job_queue(self) -> None:
        if not self._email_job_running:
            return
        got_done = False
        while True:
            try:
                message = self._email_job_queue.get_nowait()
            except queue.Empty:
                break
            kind = message[0]
            if kind == "progress":
                _, done, total, domain, status = message
                self._email_progress_update(done, total, domain, status)
            elif kind == "row_progress":
                _, done, total = message
                self._email_row_progress_update(done, total)
            elif kind == "done":
                _, results, error, snapshot, cancelled = message
                got_done = True
                self._finish_email_job(results, error, snapshot, cancelled)
                break
        if self._email_job_running and not got_done:
            self.after(60, self._poll_email_job_queue)

    def _finish_email_job(
        self,
        results: list[EmailFindingResult] | None,
        error: Exception | None,
        snapshot: list[dict[str, str]],
        cancelled: bool = False,
    ) -> None:
        run_validation_after = False
        applied = possible = preserved = skipped = 0
        web_domains: set[str] = set()
        try:
            if error is not None:
                messagebox.showerror("Find Emails failed", str(error))
                self._set_status("Email processing failed")
                return
            if results is None:
                self._set_status("Email processing ended without results")
                return
            if self.data_manager.records != snapshot:
                messagebox.showwarning(
                    "Find Emails",
                    "Worksheet data changed while email discovery was running. Results were not applied. "
                    "Run Find Emails again to use the current data.",
                )
                self._set_status("Email results discarded because worksheet data changed")
                return

            self.email_results = {result.row_index: result for result in results}
            for result in results:
                if not (0 <= result.row_index < len(self.data_manager.records)):
                    continue
                record = self.data_manager.records[result.row_index]
                old_email = record.get("Business Email ID", MISSING_VALUE)
                if result.discovery_status:
                    web_domains.add(str(record.get("Company Website", MISSING_VALUE)))

                if result.applied and result.candidate != MISSING_VALUE:
                    self.data_manager.update_cell(result.row_index, "Business Email ID", result.candidate)
                    self.data_manager.update_cell(result.row_index, "Email Status", result.status)
                    applied += 1
                    record_key = str(record.get("Prospect LinkedIn Link") or f"row-{result.row_index + 1}")
                    record_audit_change(
                        record_key=record_key,
                        field_name="Business Email ID",
                        old_value=str(old_email),
                        new_value=result.candidate,
                        reason=f"{result.source}; pattern={result.pattern or '-'}",
                        confidence=result.confidence,
                    )
                elif result.status in {
                    "Possible", "Missing Name", "Missing Domain", "Invalid Domain",
                    "Manual Review", "Suppressed", "Not Found"
                }:
                    if old_email == MISSING_VALUE or self.revalidate_existing_emails:
                        self.data_manager.update_cell(result.row_index, "Email Status", result.status)
                    if result.status == "Possible":
                        possible += 1
                    else:
                        skipped += 1
                else:
                    preserved += 1

                logger.info(
                    "Email engine | row=%s | status=%s | candidate=%s | confidence=%s | "
                    "pattern=%s | source=%s | discovery=%s | provider=%s | queries=%s | "
                    "cached=%s | applied=%s | reason=%s",
                    result.row_index + 1, result.status, result.candidate, result.confidence,
                    result.pattern, result.source, result.discovery_status,
                    result.discovery_provider, result.web_query_count, result.discovery_cached,
                    result.applied, result.reason,
                )

            if results:
                self._mark_dirty()
                self._invalidate_validation()
            self.refresh_grid()
            self._show_active_validation()
            processed = len(results)
            if cancelled:
                self._set_status(
                    f"Email job cancelled: {processed:,} row result(s) retained; completed domain cache preserved"
                )
            else:
                self._set_status(
                    f"Email engine complete: {applied:,} filled, {possible:,} possible, "
                    f"{preserved:,} preserved, {skipped:,} skipped/review"
                )
                run_validation_after = True

            discovery_text = (
                f"Public discovery touched {len(web_domains):,} unique domain(s)."
                if self.email_search_enabled
                else "Public web discovery was disabled; learned/cached evidence only."
            )
            title = "Find Emails cancelled" if cancelled else "Find Emails complete"
            record_activity(
                "email",
                title,
                {
                    "processed": processed, "total": len(snapshot), "auto_filled": applied,
                    "possible": possible, "preserved": preserved, "skipped": skipped,
                    "web_domains": len(web_domains),
                },
            )
            messagebox.showinfo(
                title,
                f"Processed row results: {processed:,}/{len(snapshot):,}\n"
                f"Auto-filled: {applied:,}\n"
                f"Possible (below threshold): {possible:,}\n"
                f"Existing preserved/revalidated: {preserved:,}\n"
                f"Skipped / manual review: {skipped:,}\n\n"
                f"{discovery_text}\n\n"
                + (
                    "Completed work and persistent caches were retained. Run Find Emails again to resume remaining work."
                    if cancelled
                    else "Generated addresses are evidence-based candidates, not proof that a mailbox exists."
                ),
            )
        finally:
            self._email_job_snapshot = None
            self._set_email_job_running(False)
            if self.data_manager.records:
                self._save_checkpoint(reason="email-job-finished", job={})

        if run_validation_after and self.data_manager.records:
            # Validation itself is a Phase-6 background job, so this does not freeze
            # Tk even for large datasets.
            self.after(75, self.validate_rows)

    def delete_selected(self) -> None:
        indices = self.grid.selected_indices()
        if not indices:
            return
        self.data_manager.delete_indices(indices)
        self._invalidate_email_results()
        self._invalidate_validation()
        self._mark_dirty()
        self.refresh_grid()
        logger.info("Deleted %s selected rows", len(indices))

    def refresh_grid(self) -> None:
        self.grid.set_filtered_columns(self._active_filter_columns())
        total = len(self.data_manager.records)
        status_filter_active = self.status_filter_var.get() != "All"
        quick_filter_active = self.issues_only_var.get() or self.missing_email_only_var.get() or status_filter_active
        if not self._active_filter_headers() and not self.search_var.get().strip() and not quick_filter_active:
            self.grid.load_rows(self.data_manager.records, self.row_states)
            visible = total
        else:
            filtered_rows: list[dict[str, str]] = []
            filtered_row_ids: list[int] = []
            for original_index, row in enumerate(self.data_manager.records):
                if self._record_matches(row, row_index=original_index):
                    filtered_rows.append(row)
                    filtered_row_ids.append(original_index)
            self.grid.load_rows(filtered_rows, self.row_states, row_ids=filtered_row_ids)
            visible = len(filtered_rows)

        filter_count = len(self._active_filter_headers())
        quick_names: list[str] = []
        if self.issues_only_var.get():
            quick_names.append("Issues")
        if self.missing_email_only_var.get():
            quick_names.append("Missing Email")
        if self.status_filter_var.get() != "All":
            quick_names.append(f"Status={self.status_filter_var.get()}")
        if filter_count or quick_names:
            parts = []
            if filter_count:
                parts.append(f"{filter_count} column filter(s)")
            parts.extend(quick_names)
            self.filter_summary_label.configure(
                text=f"{' • '.join(parts)} • Showing {visible:,}/{total:,}"
            )
        elif self.search_var.get().strip():
            self.filter_summary_label.configure(text=f"Search • Showing {visible:,}/{total:,}")
        else:
            self.filter_summary_label.configure(text=f"No column filters • {total:,} record(s)")
        self._refresh_home_metrics()

    def _validation_detail_rows(self, indices: list[int] | None = None) -> list[dict[str, object]]:
        selected = indices if indices is not None else list(range(len(self.data_manager.records)))
        details: list[dict[str, object]] = []
        for index in selected:
            result = self.validation_results.get(index)
            email = self.email_results.get(index)
            details.append({
                "Row": index + 1,
                "Final Status": self.row_states.get(index, "Not Validated"),
                "Validation Reason": "; ".join(self.validation_reasons.get(index, [])) or "-",
                "TAL Match": result.tal_status if result else "-",
                "TAL Reason": result.tal_reason if result else "-",
                "Suppression": result.suppression_status if result else "-",
                "Suppression Reason": result.suppression_reason if result else "-",
                "Duplicate": result.duplicate_status if result else "-",
                "Email Engine": email.status if email else "-",
                "Email Confidence": email.confidence if email else "-",
                "Email Pattern": email.pattern if email and email.pattern else "-",
            })
        return details

    def _export_indices(self) -> list[int]:
        if not self.export_valid_only:
            return list(range(len(self.data_manager.records)))
        return [
            index for index in range(len(self.data_manager.records))
            if self.row_states.get(index) in {"Valid", "Valid - Email Generated"}
        ]

    def quick_save(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = Path(self.default_export_folder or str(EXPORT_DIR))
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            folder = EXPORT_DIR
        path = folder / f"lead_working_copy_{timestamp}.xlsx"
        try:
            details = self._validation_detail_rows() if self.include_validation_details else None
            export_records(self.data_manager.to_dataframe(), path, validation_details=details)
            logger.info("Working copy saved: %s", path)
            record_activity(
                "save", f"Saved working copy with {len(self.data_manager.records):,} row(s)",
                {"file": str(path)},
            )
            self._set_status(f"Saved: {path.name}")
            messagebox.showinfo("Saved", f"Working copy saved to:\n{path}")
        except Exception as exc:
            logger.exception("Save failed")
            messagebox.showerror("Save failed", str(exc))

    def export_data(self) -> None:
        default_folder = Path(self.default_export_folder or str(EXPORT_DIR))
        initial_dir = str(default_folder if default_folder.exists() else EXPORT_DIR)
        path = filedialog.asksaveasfilename(
            title="Export lead data",
            defaultextension=".xlsx",
            initialdir=initial_dir,
            filetypes=[("Excel workbook", "*.xlsx")],
        )
        if not path:
            return
        try:
            indices = self._export_indices()
            if self.export_valid_only and not indices:
                messagebox.showwarning(
                    "Export",
                    "Export Valid Only is enabled, but there are no Valid records. "
                    "Run VALIDATE or change the export setting.",
                )
                return
            rows = [self.data_manager.records[index] for index in indices]
            import pandas as pd
            frame = pd.DataFrame(rows, columns=list(STANDARD_HEADERS))
            details = self._validation_detail_rows(indices) if self.include_validation_details else None
            output = export_records(frame, path, validation_details=details)
            logger.info("Exported %s rows to %s", len(rows), output)
            record_activity(
                "export",
                f"Exported {len(rows):,} record(s)",
                {
                    "file": str(output),
                    "valid_only": self.export_valid_only,
                    "qa_sheet": self.include_validation_details,
                },
            )
            self.default_export_folder = str(Path(path).parent)
            self._persist_settings()
            self._set_status(f"Exported {len(rows):,} rows")
            messagebox.showinfo("Export complete", f"Exported to:\n{output}")
        except Exception as exc:
            logger.exception("Export failed")
            messagebox.showerror("Export failed", str(exc))

