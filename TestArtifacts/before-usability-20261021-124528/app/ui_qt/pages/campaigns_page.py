from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget, QMessageBox, QPushButton,
    QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from app.core.campaign_models import CampaignProfile
from app.ui_qt.widgets.icons import icon


ROLE_LABELS = {
    "specification": "Specification",
    "tal": "TAL",
    "reference_tal": "Reference TAL",
    "client_suppression": "Client Suppression",
    "internal_suppression": "Internal Suppression",
    "processed_suppression": "Processed Leads Suppression",
    "competitor_exclusion": "Competitor Exclusion",
    "domain_suppression": "Domain Suppression",
    "domain_limit": "Domain Limit",
    "unknown": "Unknown",
}


class CampaignsPage(QWidget):
    import_zip_requested = Signal()
    import_folder_requested = Signal()
    activate_requested = Signal(object)
    delete_requested = Signal(object)
    ai_enhance_requested = Signal(object)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.current_profile: CampaignProfile | None = None
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)

        head = QHBoxLayout()
        title = QLabel("Campaign Manager")
        title.setObjectName("pageTitle")
        head.addWidget(title)
        head.addStretch(1)
        for text, signal, primary in (
            ("Import ZIP", self.import_zip_requested, True),
            ("Import Folder", self.import_folder_requested, False),
        ):
            b = QPushButton(text)
            if primary:
                b.setObjectName("primaryButton")
            b.clicked.connect(signal)
            head.addWidget(b)
        root.addLayout(head)
        subtitle = QLabel("Organize campaign files, review requirements, and activate the rules for your leads.")
        subtitle.setObjectName("muted"); subtitle.setWordWrap(True); root.addWidget(subtitle)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False); split.setHandleWidth(16)
        left = QFrame()
        left.setObjectName("card")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(18, 18, 18, 18); ll.setSpacing(12)
        saved = QLabel("Saved campaigns"); saved.setObjectName("sectionTitle"); ll.addWidget(saved)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._selection_changed)
        ll.addWidget(self.list, 1)
        self.refresh_button = QPushButton("Refresh Campaign List")
        self.refresh_button.clicked.connect(self.refresh_campaigns)
        ll.addWidget(self.refresh_button)
        split.addWidget(left)

        right = QFrame()
        right.setObjectName("card")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(20, 18, 20, 18); rl.setSpacing(14)
        self.campaign_title = QLabel("Select or import a campaign")
        self.campaign_title.setObjectName("sectionTitle")
        rl.addWidget(self.campaign_title)
        actions = QHBoxLayout()
        self.activate_btn = QPushButton("Activate Campaign")
        self.activate_btn.setObjectName("primaryButton")
        self.ai_btn = QPushButton("AI Enhance Specs")
        self.delete_btn = QPushButton("Delete Campaign")
        self.delete_btn.setObjectName("dangerButton")
        self.activate_btn.clicked.connect(lambda: self.current_profile and self.activate_requested.emit(self.current_profile))
        self.ai_btn.clicked.connect(lambda: self.current_profile and self.ai_enhance_requested.emit(self.current_profile))
        self.delete_btn.clicked.connect(self._delete_clicked)
        actions.addWidget(self.activate_btn)
        actions.addWidget(self.ai_btn)
        actions.addStretch(1)
        actions.addWidget(self.delete_btn)
        rl.addLayout(actions)

        self.tabs = QTabWidget()
        self.overview = QTextEdit(); self.overview.setReadOnly(True)
        self.overview.setPlaceholderText("Start with a campaign package.\n\nImport a ZIP or folder, then review the extracted requirements, target accounts, and supporting sources here.")
        self.files = QTableWidget(0, 5)
        self.files.setHorizontalHeaderLabels(["File", "Role", "Format", "Records", "Confidence"])
        self.rules = QTableWidget(0, 7)
        self.rules.setHorizontalHeaderLabels(["Category", "Field", "Operator", "Value", "Confidence", "Status", "Source"])
        self.conflicts = QTableWidget(0, 4)
        self.conflicts.setHorizontalHeaderLabels(["Rule", "Values", "Sources", "Resolved"])
        self.sources = QTextEdit(); self.sources.setReadOnly(True)
        self.tabs.addTab(self.overview, "Overview")
        self.tabs.addTab(self.files, "Files")
        self.tabs.addTab(self.rules, "Rules")
        self.tabs.addTab(self.conflicts, "Conflicts")
        self.tabs.addTab(self.sources, "Sources")
        rl.addWidget(self.tabs, 1)
        split.addWidget(right)
        split.setSizes([280, 950])
        root.addWidget(split, 1)
        self.refresh_campaigns()

    def refresh_campaigns(self, select_id: str | None = None):
        profiles = self.controller.campaign_store.list()
        self.list.blockSignals(True)
        self.list.clear()
        row_to_select = -1
        for i, profile in enumerate(profiles):
            label = f"{profile.campaign_id} — {profile.campaign_name}"
            if profile.active:
                label = "● " + label
            self.list.addItem(label)
            self.list.item(i).setData(Qt.ItemDataRole.UserRole, profile.campaign_id)
            if select_id and profile.campaign_id == select_id:
                row_to_select = i
        self.list.blockSignals(False)
        if profiles:
            self.list.setCurrentRow(row_to_select if row_to_select >= 0 else 0)
        else:
            self.current_profile = None
            self._render(None)

    def _selection_changed(self, row: int):
        if row < 0:
            self._render(None); return
        item = self.list.item(row)
        profile = self.controller.campaign_store.get(item.data(Qt.ItemDataRole.UserRole))
        self._render(profile)

    def _render(self, profile: CampaignProfile | None):
        self.current_profile = profile
        enabled = profile is not None
        self.activate_btn.setEnabled(enabled)
        self.ai_btn.setEnabled(enabled and self.controller.settings.qwen_enabled)
        self.delete_btn.setEnabled(enabled)
        if profile is None:
            self.campaign_title.setText("Select or import a campaign")
            self.overview.clear(); self.files.setRowCount(0); self.rules.setRowCount(0); self.conflicts.setRowCount(0); self.sources.clear()
            return
        self.campaign_title.setText(f"{profile.campaign_id} — {profile.campaign_name}" + ("   • Active" if profile.active else ""))
        self.overview.setPlainText(
            f"Campaign ID: {profile.campaign_id}\n"
            f"Campaign Name: {profile.campaign_name}\n"
            f"Imported: {profile.imported_at}\n"
            f"Source: {profile.source_root}\n"
            f"Files: {len(profile.files)}\nRules: {len(profile.rules)}\nConflicts: {len(profile.conflicts)}\n\n"
            f"{profile.notes or 'No importer warnings.'}"
        )
        self.files.setRowCount(len(profile.files))
        for r, info in enumerate(profile.files):
            vals = [info.relative_path, ROLE_LABELS.get(info.role, info.role), info.format.upper(), f"{info.record_count:,}", f"{info.confidence:.0%}"]
            for c, val in enumerate(vals):
                self.files.setItem(r, c, QTableWidgetItem(str(val)))
        self.files.resizeColumnsToContents()

        self.rules.setRowCount(len(profile.rules))
        source_lines = []
        for r, rule in enumerate(profile.rules):
            source_text = "; ".join(f"{s.file} {s.location}".strip() for s in rule.sources) or "-"
            vals = [rule.category, rule.field, rule.operator, json.dumps(rule.value, ensure_ascii=False) if not isinstance(rule.value, str) else rule.value, f"{rule.confidence:.0%}", rule.status, source_text]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                if c != 5:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.rules.setItem(r, c, item)
            for source in rule.sources:
                source_lines.append(f"{rule.field}\n  File: {source.file}\n  Location: {source.location or '-'}\n  Excerpt: {source.excerpt or '-'}\n")
        self.rules.resizeColumnsToContents()
        self.sources.setPlainText("\n".join(source_lines))

        self.conflicts.setRowCount(len(profile.conflicts))
        for r, conflict in enumerate(profile.conflicts):
            vals = [conflict.rule_key, json.dumps(conflict.values, ensure_ascii=False), "; ".join(conflict.sources), "Yes" if conflict.resolved else "No"]
            for c, val in enumerate(vals):
                self.conflicts.setItem(r, c, QTableWidgetItem(str(val)))
        self.conflicts.resizeColumnsToContents()

    def _delete_clicked(self):
        profile = self.current_profile
        if not profile:
            return
        answer = QMessageBox.question(
            self,
            "Delete Campaign",
            f"Delete the saved campaign profile '{profile.campaign_id} — {profile.campaign_name}'?\n\n"
            "The original campaign ZIP/folder will NOT be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_requested.emit(profile)
