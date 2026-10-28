from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QThreadPool, QSize
from PySide6.QtGui import QAction, QColor, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDockWidget, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QProgressBar, QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from app.ai.campaign_intelligence import AICampaignIntelligence
from app.ai.campaign_reader import QwenCampaignReader
from app.ai.normalization_agent import AINormalizationAgent
from app.ai.qa_assistant import AIQAAssistant
from app.ai.rule_builder import AIRuleBuilder
from app.constants import STANDARD_HEADERS
from app.core.batch_control import BatchControl
from app.core.scraper_bridge import transfer_workbook
from app.core.campaign_models import CampaignRule
from app.core.reference_lists import available_fields
from app.excel.importer import read_import_tables
from app.ui_qt.controller import ApplicationController
from app.ui_qt.dialogs.lead_import_dialog import LeadImportDialog
from app.ui_qt.pages.ai_page import AIPage
from app.ui_qt.pages.campaigns_page import CampaignsPage
from app.ui_qt.pages.dashboard_page import DashboardPage
from app.ui_qt.pages.home_page import HomePage
from app.ui_qt.pages.info_page import InfoPage
from app.ui_qt.pages.leads_page import LeadsPage
from app.ui_qt.pages.settings_page import SettingsPage
from app.ui_qt.pages.scraper_page import ScraperPage
from app.ui_qt.pages.tools_page import ToolsPage
from app.ui_qt.pages.validation_page import ValidationPage
from app.ui_qt.qt_theme import build_stylesheet
from app.ui_qt.widgets.validation_drawer import ValidationDrawer
from app.ui_qt.widgets.workers import FunctionWorker
from app.ui_qt.widgets.icons import icon as ui_icon
from app.utils.config import EXPORT_DIR
from app.utils.logger import logger


NAV_ITEMS = [
    ("scraper", "↗", "Scraper"),
    ("home", "⌂", "Home"),
    ("leads", "▦", "Leads Workspace"),
    ("campaigns", "◫", "Campaign Manager"),
    ("validation", "✓", "Validation Summary"),
    ("ai", "✦", "AI Center"),
    ("dashboard", "▥", "Dashboard"),
    ("tools", "◷", "Operations & Diagnostics"),
    ("settings", "⚙", "Settings"),
    ("info", "ⓘ", "Info."),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.controller = ApplicationController()
        self.thread_pool = QThreadPool.globalInstance()
        self._active_control: BatchControl | None = None
        self._sidebar_collapsed = False
        self._jobs = {}
        self._job_sequence = 0
        self.setWindowTitle("Lead Workspace — Scraper & Lead Manager")
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1540, screen.width() - 60), min(940, screen.height() - 60))
        self.setMinimumSize(1120, 720)
        self._build_ui()
        self.apply_theme()
        self._wire_pages()
        self._install_shortcuts()
        self._refresh_all()
        self.autosave_timer = QTimer(self)
        self.autosave_timer.timeout.connect(self._autosave_workspace)
        self.autosave_timer.start(max(15, int(self.controller.settings.autosave_interval_seconds)) * 1000)
        QTimer.singleShot(250, self._offer_recovery)
        QTimer.singleShot(350, self.refresh_qwen_status)
        if self.controller.settings.qwen_enabled and self.controller.settings.qwen_auto_start:
            QTimer.singleShot(800, self.start_qwen)

    # ---------- UI shell ----------
    def _build_ui(self):
        root = QWidget(); root.setObjectName("appRoot")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        self.sidebar = QFrame(); self.sidebar.setObjectName("sideBar"); self.sidebar.setFixedWidth(244)
        sl = QVBoxLayout(self.sidebar); sl.setContentsMargins(14, 24, 14, 12); sl.setSpacing(5)
        brand = QHBoxLayout(); brand.setSpacing(10)
        self.brand_mark = QLabel("LW"); self.brand_mark.setObjectName("brandMark")
        self.brand_mark.setFixedSize(38, 38); self.brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brand_text = QWidget(); bt = QVBoxLayout(self.brand_text); bt.setContentsMargins(0, 0, 0, 0); bt.setSpacing(2)
        self.brand_label = QLabel("Lead Workspace"); self.brand_label.setObjectName("appTitle")
        caption = QLabel("RESEARCH & OPERATIONS"); caption.setObjectName("brandCaption")
        bt.addWidget(self.brand_label); bt.addWidget(caption)
        brand.addWidget(self.brand_mark); brand.addWidget(self.brand_text); brand.addStretch(1); sl.addLayout(brand)
        sl.addSpacing(18)
        self.nav_buttons = {}
        self.nav_sections = []
        for key, icon, label in NAV_ITEMS:
            section = {"scraper": "WORKSPACE", "ai": "INTELLIGENCE", "tools": "MANAGE"}.get(key)
            if section:
                section_label = QLabel(section); section_label.setObjectName("navSection")
                sl.addWidget(section_label); self.nav_sections.append(section_label)
            btn = QPushButton("  " + label.replace("&", "&&")); btn.setObjectName("navButton"); btn.setCheckable(True)
            btn.setIcon(ui_icon(key, "#A8B9D0", "#80E3D0")); btn.setIconSize(QSize(19, 19))
            btn.setCursor(Qt.CursorShape.PointingHandCursor); btn.setToolTip(label); btn.setAccessibleName(label)
            btn.clicked.connect(lambda _=False, k=key: self.navigate(k))
            self.nav_buttons[key] = btn; sl.addWidget(btn)
        sl.addStretch(1)
        self.sidebar_status = QLabel("One workspace.\nFrom discovery to delivery.")
        self.sidebar_status.setObjectName("sidebarNote"); sl.addWidget(self.sidebar_status)
        outer.addWidget(self.sidebar)

        main = QVBoxLayout(); main.setContentsMargins(0, 0, 0, 0); main.setSpacing(0)
        top = QFrame(); top.setObjectName("topBar"); tl = QHBoxLayout(top); tl.setContentsMargins(24, 13, 24, 13); tl.setSpacing(12)
        self.hamburger = QPushButton(); self.hamburger.setObjectName("ghostButton")
        self.hamburger.setIcon(ui_icon("menu")); self.hamburger.setFixedSize(34, 34)
        self.hamburger.setToolTip("Collapse or expand navigation"); self.hamburger.setAccessibleName("Toggle navigation")
        self.hamburger.clicked.connect(self.toggle_sidebar); tl.addWidget(self.hamburger)
        crumb = QLabel("Workspace  /"); crumb.setObjectName("muted"); tl.addWidget(crumb)
        self.page_title = QLabel("Home"); tl.addWidget(self.page_title)
        tl.addStretch(1)
        self.campaign_badge = QLabel("Campaign: None"); self.campaign_badge.setObjectName("badge"); self.campaign_badge.setMaximumWidth(260); tl.addWidget(self.campaign_badge)
        self.qwen_badge = QLabel("Qwen: Checking…"); self.qwen_badge.setObjectName("badge"); tl.addWidget(self.qwen_badge)
        info_btn = QPushButton(); info_btn.setIcon(ui_icon("info")); info_btn.setObjectName("ghostButton"); info_btn.setFixedSize(34, 34)
        info_btn.setToolTip("Help & user guide · F1"); info_btn.setAccessibleName("Help and user guide")
        info_btn.clicked.connect(lambda: self.navigate("info")); tl.addWidget(info_btn)
        main.addWidget(top)

        self.stack = QStackedWidget(); main.addWidget(self.stack, 1)
        holder = QWidget(); holder.setLayout(main); outer.addWidget(holder, 1)

        self.scraper_page = ScraperPage(self.controller)
        self.home_page = HomePage(self.controller)
        self.leads_page = LeadsPage(self.controller)
        self.campaigns_page = CampaignsPage(self.controller)
        self.validation_page = ValidationPage(self.controller)
        self.ai_page = AIPage(self.controller)
        self.dashboard_page = DashboardPage(self.controller)
        self.tools_page = ToolsPage(self.controller)
        self.settings_page = SettingsPage(self.controller)
        self.info_page = InfoPage()
        self.pages = {
            "scraper": self.scraper_page,
            "home": self.home_page, "leads": self.leads_page, "campaigns": self.campaigns_page,
            "validation": self.validation_page, "ai": self.ai_page, "dashboard": self.dashboard_page,
            "tools": self.tools_page, "settings": self.settings_page, "info": self.info_page,
        }
        for key, _, _ in NAV_ITEMS:
            page = self.pages[key]
            page.layout().setContentsMargins(26, 24, 26, 22)
            page.layout().setSpacing(14)
            self.stack.addWidget(self.pages[key])

        self.validation_dock = QDockWidget("Validation Summary", self)
        self.validation_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.validation_drawer = ValidationDrawer(self.controller)
        self.validation_dock.setWidget(self.validation_drawer)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.validation_dock)
        self.validation_dock.hide()

        status = QStatusBar(); self.setStatusBar(status)
        self.status_message = QLabel("Ready"); status.addWidget(self.status_message, 1)
        self.operation_progress = QProgressBar(); self.operation_progress.setFixedWidth(180)
        self.operation_progress.setFixedHeight(8); self.operation_progress.setTextVisible(False)
        self.operation_progress.hide(); status.addPermanentWidget(self.operation_progress)
        self.operation_detail = QLabel(); status.addPermanentWidget(self.operation_detail)
        self.operation_timer = QTimer(self); self.operation_timer.timeout.connect(self._render_jobs); self.operation_timer.start(500)
        shortcut_hint = QLabel("Ctrl+1  Scraper     Ctrl+2  Leads     F1  Help")
        shortcut_hint.setObjectName("muted"); status.addPermanentWidget(shortcut_hint)
        self.navigate("scraper")

    def _wire_pages(self):
        self.scraper_page.transfer_requested.connect(self.import_scraper_results)
        h=self.home_page
        h.navigate.connect(self.navigate); h.qwen_start_requested.connect(self.start_qwen); h.qwen_stop_requested.connect(self.stop_qwen); h.qwen_toggle_requested.connect(self.toggle_qwen_enabled)
        l=self.leads_page
        l.columns_added.connect(lambda: self.run_worker(lambda: self.controller.save_checkpoint(reason="columns-added"), started="Saving new columns…", finished="Columns added and saved"))
        l.import_requested.connect(self.import_leads); l.paste_requested.connect(l.table.paste_clipboard); l.load_tal_requested.connect(lambda:self.load_reference("tal")); l.load_suppression_requested.connect(lambda:self.load_reference("suppression")); l.validate_requested.connect(self.validate_rows); l.find_emails_requested.connect(self.find_emails); l.export_requested.connect(self.export_data); l.save_requested.connect(self.quick_save); l.new_requested.connect(self.new_session); l.validation_summary_requested.connect(self.toggle_validation_dock); l.pause_requested.connect(self.pause_job); l.resume_requested.connect(self.resume_job); l.cancel_requested.connect(self.cancel_job)
        l.table.selectionModel().currentChanged.connect(self._lead_selection_changed)
        c=self.campaigns_page
        c.import_zip_requested.connect(self.import_campaign_zip); c.import_folder_requested.connect(self.import_campaign_folder); c.activate_requested.connect(self.activate_campaign); c.delete_requested.connect(self.delete_campaign); c.ai_enhance_requested.connect(self.ai_enhance_campaign)
        s=self.settings_page
        s.settings_applied.connect(self.settings_changed); s.qwen_start_requested.connect(self.start_qwen); s.qwen_stop_requested.connect(self.stop_qwen); s.qwen_restart_requested.connect(self.restart_qwen); s.qwen_refresh_requested.connect(self.refresh_qwen_status)
        a=self.ai_page
        a.rule_builder_requested.connect(self.ai_build_rules); a.normalize_requested.connect(self.ai_normalize); a.qa_requested.connect(self.ai_qa); a.explain_requested.connect(self.ai_explain); a.intelligence_requested.connect(self.ai_intelligence)

    def _install_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda:self.navigate("scraper"))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda:self.navigate("leads"))
        QShortcut(QKeySequence("Ctrl+3"), self, activated=lambda:self.navigate("campaigns"))
        QShortcut(QKeySequence("F1"), self, activated=lambda:self.navigate("info"))
        QShortcut(QKeySequence("Ctrl+,"), self, activated=lambda:self.navigate("settings"))

    def navigate(self, key: str):
        if key not in self.pages: return
        self.stack.setCurrentWidget(self.pages[key])
        label = next((label for k, _, label in NAV_ITEMS if k == key), key)
        self.page_title.setText(label)
        for k, btn in self.nav_buttons.items(): btn.setChecked(k == key)
        if key == "home": self.home_page.refresh_metrics()
        elif key == "campaigns": self.campaigns_page.refresh_campaigns(self.controller.active_campaign.campaign_id if self.controller.active_campaign else None)
        elif key == "validation": self.validation_page.refresh(self.current_source_row())
        elif key == "dashboard": self.dashboard_page.refresh()
        elif key == "tools": self.tools_page.refresh()
        elif key == "settings": self.settings_page.load()
        elif key == "ai": self.ai_page.set_selected_row(self.current_source_row(default=-1))

    def toggle_sidebar(self):
        self._sidebar_collapsed = not self._sidebar_collapsed
        self.sidebar.setFixedWidth(76 if self._sidebar_collapsed else 244)
        self.brand_text.setVisible(not self._sidebar_collapsed)
        self.sidebar_status.setVisible(not self._sidebar_collapsed)
        for section in self.nav_sections: section.setVisible(not self._sidebar_collapsed)
        for key, icon, label in NAV_ITEMS:
            self.nav_buttons[key].setText("" if self._sidebar_collapsed else "  " + label.replace("&", "&&"))
            self.nav_buttons[key].setToolTip(label)

    def apply_theme(self):
        mode=self.controller.settings.appearance_mode
        dark = mode == "Dark"
        if mode == "System":
            dark = QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128
        QApplication.instance().setStyleSheet(build_stylesheet(self.controller.settings.color_scheme, dark))

    # ---------- generic worker ----------
    def import_scraper_results(self, path):
        if self._active_control:
            QMessageBox.information(self, "Lead job running", "Wait for validation or email finding to finish, then add results.")
            return
        if self._jobs:
            self.status_message.setText("Finish the current operation before adding results.")
            return
        def done(result):
            self._refresh_all(); self.navigate("leads")
            message = f"Added {result.added:,} lead(s); skipped {result.skipped:,} existing profile(s) or identical rows."
            self.status_message.setText(message)
            self.scraper_page._log(message + f" Evidence remains in {result.source}")
            self.run_worker(lambda: self.controller.save_checkpoint(reason="scraper-transfer"), started="Saving workspace…", finished=message)
        self.run_worker(lambda: transfer_workbook(self.controller, path), started="Adding scraper results…", on_done=done)

    def _autosave_workspace(self):
        if (self.controller.data_manager.records or self.controller.data_manager.custom_columns) and not self._jobs and not self._active_control and not QApplication.activeModalWidget():
            self.run_worker(lambda: self.controller.save_checkpoint(reason="autosave"), started="Saving workspace…", finished="Workspace saved")

    def _start_job(self, label):
        self._job_sequence += 1
        token = self._job_sequence
        self._jobs[token] = {"label": label, "start": time.monotonic(), "done": 0, "total": 0}
        self.leads_page.set_data_busy(True)
        self._render_jobs()
        return token

    def _render_jobs(self):
        self.operation_progress.setVisible(bool(self._jobs))
        if not self._jobs:
            self.operation_detail.clear()
            return
        job = list(self._jobs.values())[-1]
        total = job["total"]
        self.operation_progress.setRange(0, 100 if total else 0)
        if total:
            self.operation_progress.setValue(min(100, int(100 * job["done"] / total)))
        count = f' · {job["done"]:,}/{total:,}' if total else ''
        concurrent = f" · {len(self._jobs)} operations" if len(self._jobs) > 1 else ""
        self.status_message.setText(job["label"])
        self.operation_detail.setText(f'{int(time.monotonic() - job["start"])}s{count}{concurrent}')

    def _finish_job(self, token):
        self._jobs.pop(token, None)
        self.leads_page.set_data_busy(bool(self._jobs))
        self._render_jobs()

    def _watch_worker(self, worker, *, started, finished=None, progress_handler=None, on_done=None, batch=False):
        token = self._start_job(started)
        # Keep the Python signal owner alive until its queued UI callback runs.
        self._jobs[token]["worker"] = worker
        def progress(value):
            if isinstance(value, tuple) and len(value) >= 2:
                job = self._jobs.get(token)
                if job:
                    job.update(done=value[0], total=value[1])
                    if len(value) > 2: job["label"] = str(value[2])
                self._render_jobs()
            if progress_handler: progress_handler(value)
        def done(result):
            self._finish_job(token)
            self.status_message.setText(finished or "Ready")
            if on_done:
                try:
                    on_done(result)
                except Exception as exc:
                    self._worker_error(str(exc))
        def error(trace):
            self._finish_job(token)
            if batch:
                self._active_control = None
                self.leads_page.set_job_running(False)
            self._worker_error(trace)
        worker.signals.progress.connect(progress)
        worker.signals.finished.connect(done)
        worker.signals.error.connect(error)
        self.thread_pool.start(worker)
        return worker

    def run_worker(self, fn, *, started="Working…", finished=None, progress_handler=None, on_done=None):
        return self._watch_worker(FunctionWorker(fn), started=started, finished=finished,
                                  progress_handler=progress_handler, on_done=on_done)

    def _worker_error(self, trace: str):
        logger.error("Background operation failed: %s", trace)
        self.status_message.setText("Operation failed")
        QMessageBox.critical(self,"Operation Failed",trace.splitlines()[-1] if trace else "Unknown error")

    # ---------- lead operations ----------
    def new_session(self):
        if self._jobs: return
        if self.controller.data_manager.records and QMessageBox.question(self,"New Session","Clear the current worksheet and start a new session?") != QMessageBox.StandardButton.Yes: return
        self.controller.new_session(); self._refresh_all(); self.status_message.setText("New session created")

    def import_leads(self):
        if self._jobs: return
        path, _ = QFileDialog.getOpenFileName(self, "Import Lead Data", "", "Excel / CSV (*.xlsx *.xlsm *.csv *.tsv *.txt)")
        if not path: return
        def loaded(tables):
            dialog = LeadImportDialog(self, tables, self.controller.data_manager.headers)
            if not dialog.exec(): return
            df = dialog.selected_table()
            mapping = dialog.mapping()
            def done(prepared):
                first_row = len(self.controller.data_manager.records)
                self.leads_page.model.beginResetModel()
                try:
                    count, used_mapping = self.controller.apply_lead_import(prepared)
                finally:
                    self.leads_page.model.endResetModel()
                self.leads_page.clear_filters()
                self._refresh_all()
                self.navigate("leads")
                first_column = self.controller.data_manager.headers.index(next(iter(used_mapping.values())))
                index = self.leads_page.proxy.mapFromSource(self.leads_page.model.index(first_row, first_column))
                self.leads_page.table.setCurrentIndex(index); self.leads_page.table.scrollTo(index)
                message = f"Imported {count:,} rows" + (f" from {prepared.sheet_name}" if prepared.sheet_name else "")
                self.status_message.setText(message)
                self.run_worker(lambda: self.controller.save_checkpoint(reason="lead-import"), started="Saving imported leads…", finished=message)
            self.run_worker(lambda: self.controller.prepare_lead_import(path, mapping, dataframe=df), started=f"Preparing {len(df):,} rows…", on_done=done)
        self.run_worker(lambda: read_import_tables(path), started="Reading file and checking worksheets…", on_done=loaded)

    def load_reference(self, kind: str):
        if self._jobs: return
        title = "Load Account/TAL List" if kind == "tal" else "Load Suppression List"
        path, _ = QFileDialog.getOpenFileName(self, title, "", "Excel / CSV (*.xlsx *.xlsm *.csv *.tsv *.txt)")
        if not path: return
        def loaded(tables):
            dialog = LeadImportDialog(self, tables, available_fields(kind), reference_kind=kind)
            if not dialog.exec(): return
            mapping = dialog.mapping()
            df = dialog.selected_table()
            def done(count):
                self._refresh_all()
                self.status_message.setText(f"{kind.upper()} saved: {count:,} records — run Validate")
            self.run_worker(lambda: self.controller.load_reference(path, kind, mapping, dataframe=df),
                            started="Saving reference list…", on_done=done)
        self.run_worker(lambda: read_import_tables(path), started="Reading reference file…", on_done=loaded)

    def _batch_progress(self, value):
        done, total = value[:2]
        self.leads_page.progress.setRange(0, 100 if total else 0)
        self.leads_page.progress.setValue(int(done / max(total, 1) * 100))
        phase = value[2] if len(value) > 2 else "Processing rows"
        self.leads_page.job_label.setText(f"{phase} · {done:,}/{total:,}")
        if phase == "Saving completed leads" and time.monotonic() - getattr(self, "_email_table_refreshed", 0) > 0.5:
            self._email_table_refreshed = time.monotonic()
            self.leads_page.refresh()

    def validate_rows(self):
        if not self.controller.data_manager.records or self._active_control or self._jobs: return
        control = BatchControl(); self._active_control = control
        self.leads_page.set_job_running(True); self._batch_progress((0, len(self.controller.data_manager.records), "Validating"))
        worker = FunctionWorker(lambda: self.controller.validate(control=control,
            progress_callback=lambda d, t: worker.signals.progress.emit((d, t, "Validating"))))
        def done(summary):
            self._active_control = None; self.leads_page.set_job_running(False)
            self._refresh_all(); self.validation_drawer.refresh(self.current_source_row())
            prefix = "Validation cancelled" if control.cancelled else "Validation complete"
            self.status_message.setText(f"{prefix} — {summary.get('Valid', 0):,} valid")
        self._watch_worker(worker, started="Validating records…", progress_handler=self._batch_progress, on_done=done, batch=True)

    def find_emails(self):
        if not self.controller.data_manager.records or self._active_control or self._jobs: return
        control = BatchControl(); self._active_control = control
        self.leads_page.email_summary.setText("Checking saved results and public company pages…" if self.controller.settings.email_website_lookup
                                             else "Checking saved results and enabled search sources…")
        self.leads_page.email_summary.show()
        self.leads_page.set_job_running(True); self._batch_progress((0, 0, "Preparing email search"))
        worker = FunctionWorker(lambda: self.controller.find_emails(control=control,
            progress_callback=lambda d, t, domain, status: worker.signals.progress.emit((d, t, "Searching company domains")),
            row_progress_callback=lambda d, t: worker.signals.progress.emit((d, t, "Saving completed leads"))))
        def done(results):
            self._active_control = None; self.leads_page.set_job_running(False)
            self.leads_page.refresh(); self.validation_drawer.refresh(self.current_source_row())
            prefix = "Email search cancelled" if control.cancelled else "Email search complete"
            report = self.controller.email_finder.last_metrics
            counts = report.get("counts", {})
            summary = self.controller.validation_summary()
            message = (f"{prefix} — {counts.get('emails_added', 0):,} emails added; "
                       f"{summary['Missing Email']:,} still blank; {report.get('unfinished_rows', 0):,} need retry or setup.")
            self.status_message.setText(message)
            self.leads_page.email_summary.setText(message + " Select a row and open Summary to see its email result, source, or reason.")
        self._watch_worker(worker, started="Finding business emails…", progress_handler=self._batch_progress, on_done=done, batch=True)

    def pause_job(self):
        if self._active_control: self._active_control.pause(); self.leads_page.set_job_running(True,paused=True); self.status_message.setText("Job paused")
    def resume_job(self):
        if self._active_control: self._active_control.resume(); self.leads_page.set_job_running(True,paused=False); self.status_message.setText("Job resumed")
    def cancel_job(self):
        if self._active_control: self._active_control.cancel(); self.status_message.setText("Cancelling current job…")

    def export_data(self):
        if self._jobs: return
        default=Path(self.controller.settings.default_export_folder or EXPORT_DIR)/f"Lead_Export_{datetime.now():%Y%m%d_%H%M}.xlsx"
        path,_=QFileDialog.getSaveFileName(self,"Export Leads",str(default),"Excel Workbook (*.xlsx)")
        if not path: return
        self.run_worker(lambda: self.controller.export(path), started="Exporting workbook…", on_done=lambda result: self.status_message.setText(f"Exported: {result}"))

    def quick_save(self):
        if self._jobs: return
        folder=Path(self.controller.settings.default_export_folder or EXPORT_DIR); folder.mkdir(parents=True,exist_ok=True)
        path=folder/f"Lead_Manager_Working_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        self.run_worker(lambda: self.controller.export(str(path)), started="Saving working copy…", finished=f"Saved working copy: {path.name}")

    def toggle_validation_dock(self):
        self.validation_drawer.refresh(self.current_source_row()); self.validation_dock.setVisible(not self.validation_dock.isVisible())

    def current_source_row(self, default=None):
        idx=self.leads_page.table.currentIndex()
        if not idx.isValid(): return default
        return self.leads_page.proxy.mapToSource(idx).row()

    def _lead_selection_changed(self, current, previous):
        row=self.current_source_row(default=-1); self.validation_drawer.refresh(row if row>=0 else None); self.validation_page.refresh(row if row>=0 else None); self.ai_page.set_selected_row(row)

    # ---------- campaigns ----------
    def import_campaign_zip(self):
        path,_=QFileDialog.getOpenFileName(self,"Import Campaign ZIP","","ZIP Archive (*.zip)")
        if path: self._import_campaign(path)
    def import_campaign_folder(self):
        path=QFileDialog.getExistingDirectory(self,"Import Campaign Folder")
        if path: self._import_campaign(path)
    def _import_campaign(self,path):
        def done(profile):
            self.campaigns_page.refresh_campaigns(profile.campaign_id); self.status_message.setText(f"Campaign imported: {profile.campaign_id} — review rules before activation")
            if self.controller.settings.ai_campaign_auto_read and self.controller.settings.qwen_enabled: self.ai_enhance_campaign(profile)
        self.run_worker(lambda:self.controller.import_campaign(path),started="Reading campaign package…",on_done=done)

    def activate_campaign(self,profile):
        if self._jobs: return
        def done(warnings):
            self._refresh_all(); self.campaigns_page.refresh_campaigns(profile.campaign_id)
            self.status_message.setText(f"Campaign active: {profile.campaign_id}")
            if warnings: QMessageBox.warning(self,"Campaign Activated with Warnings","\n".join(warnings[:12]))
        self.run_worker(lambda: self.controller.activate_campaign(profile), started="Activating campaign and loading its lists…", on_done=done)

    def delete_campaign(self,profile):
        if self._jobs: return
        def done(_):
            self._refresh_all(); self.status_message.setText(f"Campaign deleted: {profile.campaign_id}")
        self.run_worker(lambda: self.controller.delete_campaign(profile.campaign_id), started="Deleting campaign…", on_done=done)

    def ai_enhance_campaign(self,profile):
        if not self.controller.settings.qwen_enabled:
            QMessageBox.information(self,"Local Qwen","Enable Qwen in Settings or Home first."); return
        def task(): return QwenCampaignReader(self.controller.ai_service).enhance_profile(profile)
        def done(suggestions):
            existing={(r.field,r.operator,json.dumps(r.value,ensure_ascii=False,sort_keys=True,default=str)) for r in profile.rules}; added=0
            for rule in suggestions:
                key=(rule.field,rule.operator,json.dumps(rule.value,ensure_ascii=False,sort_keys=True,default=str))
                if key not in existing: profile.rules.append(rule); existing.add(key); added+=1
            profile.conflicts=self.controller.campaign_importer._find_conflicts(profile.rules); self.controller.campaign_store.save(profile); self.campaigns_page.refresh_campaigns(profile.campaign_id); self.status_message.setText(f"Qwen campaign review complete — {added} rule(s) added")
        self.run_worker(task,started="Qwen is reviewing campaign specifications…",on_done=done)

    # ---------- AI Center ----------
    def ai_build_rules(self,instruction):
        if not instruction: return
        self.run_worker(lambda:AIRuleBuilder(self.controller.ai_service).build(instruction),started="Qwen is building rules…",on_done=self.ai_page.show_rules)
    def ai_normalize(self,field):
        values=[r.get(field,"-") for r in self.controller.data_manager.records]
        self.run_worker(lambda:AINormalizationAgent(self.controller.ai_service).normalize_unique(field,values),started=f"Normalizing unique {field} values…",on_done=self.ai_page.show_normalization)
    def ai_qa(self,row):
        if row<0 or row>=len(self.controller.data_manager.records): return
        rec=self.controller.data_manager.records[row]; profile=self.controller.active_campaign; rules=[r.to_dict() for r in profile.rules] if profile else []
        self.run_worker(lambda:AIQAAssistant(self.controller.ai_service).review(rec,status=self.controller.row_states.get(row),reasons=self.controller.validation_reasons.get(row,[]),campaign_rules=rules),started="Qwen QA review…",on_done=lambda x:self.ai_page.show_json("qa",x))
    def ai_explain(self,row):
        if row<0 or row>=len(self.controller.data_manager.records): return
        rec=self.controller.data_manager.records[row]
        self.run_worker(lambda:AIQAAssistant(self.controller.ai_service).explain_validation(rec,status=self.controller.row_states.get(row),reasons=self.controller.validation_reasons.get(row,[])),started="Explaining validation…",on_done=lambda x:self.ai_page.show_json("qa",x))
    def ai_intelligence(self):
        metrics=self.controller.validation_summary(); profile=self.controller.active_campaign
        metrics.update({"campaign_id":profile.campaign_id if profile else None,"campaign_name":profile.campaign_name if profile else None})
        self.run_worker(lambda:AICampaignIntelligence(self.controller.ai_service).insights(metrics),started="Generating campaign intelligence…",on_done=lambda x:self.ai_page.show_json("intelligence",x))

    # ---------- settings / Qwen ----------
    def settings_changed(self):
        self.apply_theme(); self.leads_page.refresh(); self.home_page.enable_qwen.setChecked(self.controller.settings.qwen_enabled); self.refresh_qwen_status(); self.status_message.setText("Settings saved")

    def toggle_qwen_enabled(self,enabled:bool):
        self.controller.settings.qwen_enabled=bool(enabled); self.controller.save_settings(); self.settings_page.load(); self.refresh_qwen_status()
    def refresh_qwen_status(self):
        def done(info):
            self.home_page.update_qwen(info); self.settings_page.update_qwen_status(info); self.qwen_badge.setText("Qwen: Ready" if info.reachable else "Qwen: Off"); self.qwen_badge.setStyleSheet("color:#217346;font-weight:600" if info.reachable else "")
        self.run_worker(lambda:self.controller.qwen_runtime.discover(probe=True),started="Checking Qwen…",on_done=done)
    def start_qwen(self):
        self.controller.settings.qwen_enabled=True; self.controller.save_settings(); self.run_worker(lambda:self.controller.qwen_runtime.start(wait_seconds=12),started="Starting local Qwen…",on_done=lambda info:(self.home_page.update_qwen(info),self.settings_page.update_qwen_status(info),self.qwen_badge.setText("Qwen: Ready" if info.reachable else "Qwen: Starting")))
    def stop_qwen(self):
        self.run_worker(lambda:self.controller.qwen_runtime.stop(wait_seconds=2),started="Stopping local Qwen…",on_done=lambda info:(self.home_page.update_qwen(info),self.settings_page.update_qwen_status(info),self.qwen_badge.setText("Qwen: Off")))
    def restart_qwen(self):
        def task(): self.controller.qwen_runtime.stop(wait_seconds=2); return self.controller.qwen_runtime.start(wait_seconds=12)
        self.run_worker(task,started="Restarting local Qwen…",on_done=lambda info:(self.home_page.update_qwen(info),self.settings_page.update_qwen_status(info),self.qwen_badge.setText("Qwen: Ready" if info.reachable else "Qwen: Starting")))

    # ---------- recovery / refresh / close ----------
    def _offer_recovery(self):
        snap=self.controller.checkpoints.latest()
        if snap and (snap.record_count or snap.payload.get("custom_columns")) and QMessageBox.question(self,"Open Previous Session",f"The previous workspace contains {snap.record_count:,} lead record(s). Open it?")==QMessageBox.StandardButton.Yes:
            self.controller.recover(snap); self._refresh_all(); self.status_message.setText(f"Recovered {snap.record_count:,} lead records")

    def _refresh_all(self):
        self.leads_page.refresh(); self.home_page.refresh_metrics(); self.dashboard_page.refresh(); self.validation_page.refresh(self.current_source_row()); self.validation_drawer.refresh(self.current_source_row()); self.campaigns_page.refresh_campaigns(self.controller.active_campaign.campaign_id if self.controller.active_campaign else None)
        p = self.controller.active_campaign
        campaign = f"Campaign: {p.campaign_id} — {p.campaign_name}" if p else "Campaign: None"
        self.campaign_badge.setToolTip(campaign)
        self.campaign_badge.setText(self.campaign_badge.fontMetrics().elidedText(campaign, Qt.TextElideMode.ElideRight, 235))

    def closeEvent(self,event):
        if self._active_control and not getattr(self, "_closing_jobs", False):
            answer = QMessageBox.question(self, "Close Application", "Stop the background job, preserve a checkpoint, and close?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore(); return
            self._active_control.cancel()
            self._closing_jobs = True
        scraper = self.scraper_page
        if scraper._preparing or scraper._file_loading or scraper._benchmark_running or (scraper.worker and scraper.worker.is_alive()):
            if not scraper._closing:
                if scraper.processing and QMessageBox.question(self, "Close Lead Workspace", "Stop extraction, save collected results, and close the application?") != QMessageBox.StandardButton.Yes:
                    event.ignore(); return
                scraper.shutdown(self.close)
            event.ignore(); return
        if self.thread_pool.activeThreadCount():
            self.status_message.setText("Waiting for background work to finish before closing…")
            if not getattr(self, "_close_retry_pending", False):
                self._close_retry_pending = True
                QTimer.singleShot(200, self._retry_close)
            event.ignore(); return
        self.autosave_timer.stop()
        self.operation_timer.stop()
        scraper.timer.stop()
        self.controller.shutdown()
        event.accept()

    def _retry_close(self):
        self._close_retry_pending = False
        self.close()
