from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QDoubleSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)

from app.ui_qt.qt_theme import ACCENTS


class SettingsPage(QWidget):
    settings_applied = Signal()
    qwen_start_requested = Signal()
    qwen_stop_requested = Signal()
    qwen_restart_requested = Signal()
    qwen_refresh_requested = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        title = QLabel("Settings")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        subtitle = QLabel("Application, validation, export and local-Qwen settings. All tabs are scrollable and resizable.")
        subtitle.setObjectName("muted")
        root.addWidget(subtitle)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.appearance = self._tab("Appearance")
        self.validation = self._tab("Validation")
        self.email = self._tab("Email Discovery")
        self.performance = self._tab("Performance & Recovery")
        self.export = self._tab("Production & Export")
        self.qwen = self._tab("Local Qwen")
        self._build_appearance()
        self._build_validation()
        self._build_email()
        self._build_performance()
        self._build_export()
        self._build_qwen()

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.apply_btn = QPushButton("Apply Settings")
        self.apply_btn.setObjectName("primaryButton")
        self.apply_btn.clicked.connect(self.apply)
        footer.addWidget(self.apply_btn)
        root.addLayout(footer)
        self.load()

    def _tab(self, name: str) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setLayout(QVBoxLayout())
        content.layout().setContentsMargins(10, 10, 10, 10)
        content.layout().setSpacing(12)
        scroll.setWidget(content)
        self.tabs.addTab(scroll, name)
        return content

    def _card(self, parent: QWidget, title: str) -> tuple[QFrame, QFormLayout]:
        frame = QFrame(); frame.setObjectName("card")
        vl = QVBoxLayout(frame)
        heading = QLabel(title); heading.setObjectName("sectionTitle")
        vl.addWidget(heading)
        form = QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        vl.addLayout(form)
        parent.layout().addWidget(frame)
        return frame, form

    def _build_appearance(self):
        _, form = self._card(self.appearance, "Application Appearance")
        self.appearance_mode = QComboBox(); self.appearance_mode.addItems(["System", "Light", "Dark"])
        self.color_scheme = QComboBox(); self.color_scheme.addItems(list(ACCENTS))
        form.addRow("Appearance mode", self.appearance_mode)
        form.addRow("Accent colour scheme", self.color_scheme)
        self.appearance.layout().addStretch(1)

    def _color_row(self, initial=""):
        holder = QWidget(); row = QHBoxLayout(holder); row.setContentsMargins(0,0,0,0)
        edit = QLineEdit(initial); edit.setMaximumWidth(120)
        btn = QPushButton("Choose Colour")
        def choose():
            color = QColorDialog.getColor(QColor(edit.text() or "#FFFFFF"), self)
            if color.isValid(): edit.setText(color.name().upper())
        btn.clicked.connect(choose)
        row.addWidget(edit); row.addWidget(btn); row.addStretch(1)
        return holder, edit

    def _build_validation(self):
        _, form = self._card(self.validation, "Validation Rules")
        self.require_tal = QCheckBox("Require TAL match when a TAL is loaded")
        self.enable_suppression = QCheckBox("Enable suppression matching")
        self.tal_fuzzy = QCheckBox("Enable fuzzy matching for TAL company names")
        self.supp_fuzzy = QCheckBox("Enable fuzzy matching for Suppression company/prospect names")
        form.addRow(self.require_tal); form.addRow(self.enable_suppression); form.addRow(self.tal_fuzzy); form.addRow(self.supp_fuzzy)
        _, colours = self._card(self.validation, "Validation Row Colours")
        out_holder, self.outside_color = self._color_row()
        sup_holder, self.suppression_color = self._color_row()
        colours.addRow("Outside TAL", out_holder)
        colours.addRow("Suppressed", sup_holder)
        self.validation.layout().addStretch(1)

    def _build_email(self):
        _, form = self._card(self.email, "Email Discovery")
        self.email_confidence = QSpinBox(); self.email_confidence.setRange(0,100); self.email_confidence.setSuffix(" %")
        self.revalidate_email = QCheckBox("Revalidate existing emails")
        self.website_lookup = QCheckBox("Check public company pages (no API key needed)")
        self.web_search = QCheckBox("Also search the wider web (requires a search API key)")
        self.provider = QComboBox(); self.provider.addItems(["Auto", "Brave", "Serper", "SerpAPI", "Disabled"])
        self.email_workers = QSpinBox(); self.email_workers.setRange(1,4)
        self.email_timeout = QSpinBox(); self.email_timeout.setRange(2,15); self.email_timeout.setSuffix(" sec")
        self.email_retries = QSpinBox(); self.email_retries.setRange(0,6)
        self.email_cache_days = QSpinBox(); self.email_cache_days.setRange(0,365); self.email_cache_days.setSuffix(" days")
        form.addRow("Minimum auto-fill confidence", self.email_confidence)
        form.addRow(self.revalidate_email)
        form.addRow(self.website_lookup)
        form.addRow(self.web_search)
        form.addRow("Search provider", self.provider)
        form.addRow("Parallel company searches", self.email_workers)
        form.addRow("Request timeout", self.email_timeout)
        form.addRow("Retries", self.email_retries)
        form.addRow("Discovery cache", self.email_cache_days)
        note = QLabel("Find Emails checks saved results first, then up to three public company pages when enabled. Published addresses are added to Business Email ID; generated addresses remain unverified. Low-confidence guesses are kept for review in Summary. Website checks and optional wider search share a 15-second budget per company. Requests respect website cooldowns; unfinished rows can be retried.")
        note.setWordWrap(True); note.setObjectName("muted"); self.email.layout().addWidget(note)
        self.email.layout().addStretch(1)

    def _build_performance(self):
        _, form = self._card(self.performance, "Performance & Recovery")
        self.autosave = QSpinBox(); self.autosave.setRange(15,3600); self.autosave.setSuffix(" sec")
        self.checkpoint_records = QSpinBox(); self.checkpoint_records.setRange(10,5000)
        self.keep_checkpoints = QSpinBox(); self.keep_checkpoints.setRange(2,20)
        form.addRow("Autosave interval", self.autosave)
        form.addRow("Checkpoint every N records", self.checkpoint_records)
        form.addRow("Keep recent checkpoints", self.keep_checkpoints)
        self.performance.layout().addStretch(1)

    def _build_export(self):
        _, form = self._card(self.export, "Production & Export")
        self.export_valid_only = QCheckBox("Export valid / valid-email-generated rows only by default")
        self.include_validation = QCheckBox("Include Validation Details worksheet")
        self.export_folder = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_export)
        holder = QWidget(); row = QHBoxLayout(holder); row.setContentsMargins(0,0,0,0); row.addWidget(self.export_folder,1); row.addWidget(browse)
        form.addRow(self.export_valid_only); form.addRow(self.include_validation); form.addRow("Default export folder", holder)
        self.export.layout().addStretch(1)

    def _build_qwen(self):
        _, form = self._card(self.qwen, "Local Qwen Runtime")
        self.qwen_enabled = QCheckBox("Enable local Qwen features")
        self.qwen_autostart = QCheckBox("Auto-start Qwen with application")
        self.qwen_stop_exit = QCheckBox("Stop Qwen when application closes")
        self.ai_start_demand = QCheckBox("Start Qwen only when an AI feature needs it")
        self.ai_cache = QCheckBox("Enable local AI response cache")
        self.qwen_folder = QLineEdit()
        folder_browse = QPushButton("Browse…"); folder_browse.clicked.connect(self._browse_qwen)
        folder_holder = QWidget(); hr=QHBoxLayout(folder_holder); hr.setContentsMargins(0,0,0,0); hr.addWidget(self.qwen_folder,1); hr.addWidget(folder_browse)
        self.qwen_host = QLineEdit(); self.qwen_port = QSpinBox(); self.qwen_port.setRange(1024,65535)
        self.qwen_args = QLineEdit()
        self.ai_conf = QDoubleSpinBox(); self.ai_conf.setRange(0.0,1.0); self.ai_conf.setSingleStep(0.05)
        self.ai_parallel = QSpinBox(); self.ai_parallel.setRange(1,4)
        self.ai_timeout = QSpinBox(); self.ai_timeout.setRange(10,600); self.ai_timeout.setSuffix(" sec")
        self.ai_cache_days = QSpinBox(); self.ai_cache_days.setRange(1,3650); self.ai_cache_days.setSuffix(" days")
        self.ai_campaign_read = QCheckBox("Use Qwen second-pass campaign requirement reader")
        for widget in (self.qwen_enabled,self.qwen_autostart,self.qwen_stop_exit,self.ai_start_demand,self.ai_cache,self.ai_campaign_read): form.addRow(widget)
        form.addRow("Qwen runtime folder", folder_holder)
        form.addRow("Host", self.qwen_host); form.addRow("Port", self.qwen_port); form.addRow("Additional runtime arguments", self.qwen_args)
        form.addRow("Minimum AI confidence", self.ai_conf); form.addRow("Parallel AI calls", self.ai_parallel); form.addRow("AI request timeout", self.ai_timeout); form.addRow("AI cache retention", self.ai_cache_days)
        runtime = QFrame(); runtime.setObjectName("card"); vl=QVBoxLayout(runtime); t=QLabel("Runtime Controls"); t.setObjectName("sectionTitle"); vl.addWidget(t)
        self.qwen_status = QLabel("Not checked"); self.qwen_status.setWordWrap(True); self.qwen_status.setObjectName("muted"); vl.addWidget(self.qwen_status)
        buttons=QHBoxLayout();
        for text, signal in (("Refresh",self.qwen_refresh_requested),("Start",self.qwen_start_requested),("Stop",self.qwen_stop_requested),("Restart",self.qwen_restart_requested)):
            b=QPushButton(text); b.clicked.connect(signal); buttons.addWidget(b)
        buttons.addStretch(1); vl.addLayout(buttons); self.qwen.layout().addWidget(runtime); self.qwen.layout().addStretch(1)

    def _browse_export(self):
        path = QFileDialog.getExistingDirectory(self, "Default Export Folder", self.export_folder.text())
        if path: self.export_folder.setText(path)

    def _browse_qwen(self):
        path = QFileDialog.getExistingDirectory(self, "Select Qwen / LLAMA Runtime Folder", self.qwen_folder.text())
        if path: self.qwen_folder.setText(path)

    def load(self):
        s=self.controller.settings
        self.appearance_mode.setCurrentText(s.appearance_mode); self.color_scheme.setCurrentText(s.color_scheme)
        self.require_tal.setChecked(s.require_tal_match); self.enable_suppression.setChecked(s.enable_suppression); self.tal_fuzzy.setChecked(s.enable_tal_fuzzy_match); self.supp_fuzzy.setChecked(s.enable_suppression_fuzzy_match)
        self.outside_color.setText(s.outside_tal_color); self.suppression_color.setText(s.suppression_match_color)
        self.email_confidence.setValue(s.minimum_email_confidence); self.revalidate_email.setChecked(s.revalidate_existing_emails); self.web_search.setChecked(s.email_search_enabled); self.provider.setCurrentText(s.search_provider_name); self.email_workers.setValue(s.email_search_max_workers); self.email_timeout.setValue(s.email_search_timeout); self.email_retries.setValue(s.email_search_retries); self.email_cache_days.setValue(s.email_discovery_cache_days)
        self.website_lookup.setChecked(s.email_website_lookup)
        self.autosave.setValue(s.autosave_interval_seconds); self.checkpoint_records.setValue(s.autosave_record_interval); self.keep_checkpoints.setValue(s.checkpoint_keep_last)
        self.export_valid_only.setChecked(s.export_valid_only); self.include_validation.setChecked(s.include_validation_details); self.export_folder.setText(s.default_export_folder)
        self.qwen_enabled.setChecked(s.qwen_enabled); self.qwen_autostart.setChecked(s.qwen_auto_start); self.qwen_stop_exit.setChecked(s.qwen_stop_on_exit); self.ai_start_demand.setChecked(s.ai_start_on_demand); self.ai_cache.setChecked(s.ai_cache_enabled); self.qwen_folder.setText(s.qwen_folder); self.qwen_host.setText(s.qwen_host); self.qwen_port.setValue(s.qwen_port); self.qwen_args.setText(s.qwen_extra_args); self.ai_conf.setValue(s.ai_min_confidence); self.ai_parallel.setValue(s.ai_max_parallel_calls); self.ai_timeout.setValue(s.ai_request_timeout); self.ai_cache_days.setValue(s.ai_cache_days); self.ai_campaign_read.setChecked(s.ai_campaign_auto_read)

    def apply(self):
        s=self.controller.settings
        s.appearance_mode=self.appearance_mode.currentText(); s.color_scheme=self.color_scheme.currentText()
        s.require_tal_match=self.require_tal.isChecked(); s.enable_suppression=self.enable_suppression.isChecked(); s.enable_tal_fuzzy_match=self.tal_fuzzy.isChecked(); s.enable_suppression_fuzzy_match=self.supp_fuzzy.isChecked(); s.outside_tal_color=self.outside_color.text().strip() or "#FFC7CE"; s.suppression_match_color=self.suppression_color.text().strip() or "#FFD59A"
        s.minimum_email_confidence=self.email_confidence.value(); s.revalidate_existing_emails=self.revalidate_email.isChecked(); s.email_search_enabled=self.web_search.isChecked(); s.search_provider_name=self.provider.currentText(); s.email_search_max_workers=self.email_workers.value(); s.email_search_timeout=self.email_timeout.value(); s.email_search_retries=self.email_retries.value(); s.email_discovery_cache_days=self.email_cache_days.value()
        s.email_website_lookup=self.website_lookup.isChecked()
        s.autosave_interval_seconds=self.autosave.value(); s.autosave_record_interval=self.checkpoint_records.value(); s.checkpoint_keep_last=self.keep_checkpoints.value(); s.export_valid_only=self.export_valid_only.isChecked(); s.include_validation_details=self.include_validation.isChecked(); s.default_export_folder=self.export_folder.text().strip()
        s.qwen_enabled=self.qwen_enabled.isChecked(); s.qwen_auto_start=self.qwen_autostart.isChecked(); s.qwen_stop_on_exit=self.qwen_stop_exit.isChecked(); s.ai_start_on_demand=self.ai_start_demand.isChecked(); s.ai_cache_enabled=self.ai_cache.isChecked(); s.qwen_folder=self.qwen_folder.text().strip(); s.qwen_host=self.qwen_host.text().strip() or "127.0.0.1"; s.qwen_port=self.qwen_port.value(); s.qwen_extra_args=self.qwen_args.text().strip(); s.ai_min_confidence=self.ai_conf.value(); s.ai_max_parallel_calls=self.ai_parallel.value(); s.ai_request_timeout=self.ai_timeout.value(); s.ai_cache_days=self.ai_cache_days.value(); s.ai_campaign_auto_read=self.ai_campaign_read.isChecked()
        self.controller.save_settings(); self.settings_applied.emit()

    def update_qwen_status(self, info):
        if info is None: return
        self.qwen_status.setText(f"{info.message}\nExecutable: {info.executable or '-'}\nModel: {info.model or '-'}\nEndpoint: http://{info.host}:{info.port}")
