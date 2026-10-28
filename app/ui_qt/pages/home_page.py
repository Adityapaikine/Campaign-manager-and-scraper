from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from app.ui_qt.widgets.cards import MetricCard
from app.ui_qt.widgets.icons import icon


class HomePage(QWidget):
    navigate = Signal(str)
    qwen_start_requested = Signal()
    qwen_stop_requested = Signal()
    qwen_toggle_requested = Signal(bool)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        hero = QFrame(); hero.setObjectName("heroCard")
        hero_l = QVBoxLayout(hero); hero_l.setContentsMargins(28, 24, 28, 24); hero_l.setSpacing(10)
        eyebrow = QLabel("YOUR WORKSPACE, AT A GLANCE"); eyebrow.setObjectName("heroText"); hero_l.addWidget(eyebrow)
        heading = QLabel("From first profile to final list."); heading.setObjectName("heroTitle"); heading.setWordWrap(True); hero_l.addWidget(heading)
        subtitle = QLabel("A single place to extract leads, manage campaigns, and deliver better data.")
        subtitle.setObjectName("heroText"); subtitle.setWordWrap(True); hero_l.addWidget(subtitle)
        hero_actions = QHBoxLayout(); hero_actions.addStretch(1)
        extract = QPushButton("Open Scraper"); extract.setObjectName("primaryButton"); extract.setIcon(icon("arrow", "#FFFFFF"))
        extract.clicked.connect(lambda: self.navigate.emit("scraper")); hero_actions.addWidget(extract); hero_l.addLayout(hero_actions)
        layout.addWidget(hero)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        self.leads_card = MetricCard("Lead Records", "0", "Current worksheet")
        self.campaign_card = MetricCard("Active Campaign", "None", "No campaign profile active")
        self.valid_card = MetricCard("Validated", "0", "Run Validate from Leads Workspace")
        self.qwen_card = MetricCard("Local Qwen", "Stopped", "Optional — starts only when needed")
        for i, card in enumerate((self.leads_card, self.campaign_card, self.valid_card, self.qwen_card)):
            metrics.addWidget(card, 0, i)
        layout.addLayout(metrics)

        quick = QFrame()
        quick.setObjectName("card")
        ql = QVBoxLayout(quick)
        ql.setContentsMargins(20, 18, 20, 18); ql.setSpacing(14)
        title = QLabel("Continue your workflow")
        title.setObjectName("sectionTitle")
        ql.addWidget(title)
        row = QHBoxLayout()
        for label, page in (
            ("Open Leads Workspace", "leads"),
            ("Campaign Manager", "campaigns"),
            ("AI Center", "ai"),
        ):
            btn = QPushButton(label)
            btn.setIcon(icon(page))
            if page == "leads":
                btn.setObjectName("primaryButton")
            btn.clicked.connect(lambda _=False, p=page: self.navigate.emit(p))
            row.addWidget(btn)
        row.addStretch(1)
        ql.addLayout(row)
        layout.addWidget(quick)

        qwen = QFrame()
        qwen.setObjectName("card")
        ql = QVBoxLayout(qwen)
        ql.setContentsMargins(20, 18, 20, 18); ql.setSpacing(12)
        title = QLabel("Local Qwen Runtime")
        title.setObjectName("sectionTitle")
        ql.addWidget(title)
        self.qwen_detail = QLabel("Checking local runtime...")
        self.qwen_detail.setObjectName("muted")
        self.qwen_detail.setWordWrap(True)
        ql.addWidget(self.qwen_detail)
        buttons = QHBoxLayout()
        self.start_qwen = QPushButton("Start Qwen")
        self.start_qwen.setObjectName("primaryButton")
        self.stop_qwen = QPushButton("Stop Qwen")
        self.enable_qwen = QPushButton("Enable Qwen")
        self.enable_qwen.setCheckable(True)
        self.enable_qwen.setChecked(bool(controller.settings.qwen_enabled))
        self.start_qwen.clicked.connect(self.qwen_start_requested)
        self.stop_qwen.clicked.connect(self.qwen_stop_requested)
        self.enable_qwen.toggled.connect(self.qwen_toggle_requested)
        buttons.addWidget(self.enable_qwen)
        buttons.addWidget(self.start_qwen)
        buttons.addWidget(self.stop_qwen)
        buttons.addStretch(1)
        ql.addLayout(buttons)
        layout.addWidget(qwen)
        layout.addStretch(1)
        self.refresh_metrics()

    def refresh_metrics(self):
        self.leads_card.set_value(f"{len(self.controller.data_manager.records):,}")
        profile = self.controller.active_campaign
        if profile:
            self.campaign_card.set_value(profile.campaign_id, profile.campaign_name)
        else:
            self.campaign_card.set_value("None", "No campaign profile active")
        summary = self.controller.validation_summary()
        validated = sum(summary[k] for k in ("Valid", "Warnings", "Invalid", "Suppressed", "Outside TAL", "Duplicates", "Manual Review"))
        self.valid_card.set_value(f"{validated:,}", f"of {summary['Total Records']:,} records")

    def update_qwen(self, info):
        if info is None:
            return
        status = "Ready" if info.reachable else ("Starting" if info.running else "Stopped")
        self.qwen_card.set_value(status, info.message)
        model = info.model.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] if info.model else "No model detected"
        self.qwen_detail.setText(f"{info.message}\nModel: {model}\nEndpoint: http://{info.host}:{info.port}")
