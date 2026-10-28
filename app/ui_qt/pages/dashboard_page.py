from __future__ import annotations

import sqlite3
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QGridLayout, QHBoxLayout,
                              QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSplitter,
                              QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QScrollArea, QFrame, QSizePolicy)

from app.core.campaign_dashboard import HEADERS, STATUSES, CampaignTrackingStore, campaign_progress
from app.ui_qt.dialogs.campaign_plan_dialog import CampaignPlanDialog
from app.ui_qt.widgets.campaign_charts import CampaignCharts
from app.ui_qt.widgets.cards import MetricCard
from app.ui_qt.widgets.icons import icon


class DashboardItem(QTableWidgetItem):
    def __lt__(self, other):
        a, b = self.data(Qt.ItemDataRole.UserRole + 1), other.data(Qt.ItemDataRole.UserRole + 1)
        if a is None or b is None:
            return a is not None and b is None
        return a < b


class DashboardPage(QWidget):
    campaigns_requested = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller; self.rows = []; self.filtered_rows = []; self.warnings = []
        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); outer.addWidget(scroll)
        body = QWidget(); body.setObjectName("scrollContent"); scroll.setWidget(body)
        root = QVBoxLayout(body); root.setContentsMargins(14, 12, 14, 12); root.setSpacing(10)
        heading = QHBoxLayout(); title = QLabel("Campaign dashboard"); title.setObjectName("pageTitle")
        heading.addWidget(title); heading.addStretch(1)
        campaigns = QPushButton("Campaign Manager"); campaigns.clicked.connect(self.campaigns_requested); heading.addWidget(campaigns)
        refresh = QPushButton("Refresh"); refresh.clicked.connect(self.refresh); heading.addWidget(refresh); root.addLayout(heading)
        subtitle = QLabel("Plan delivery, track campaign progress, and review lead quality across your workspaces.")
        subtitle.setObjectName("muted"); subtitle.setWordWrap(True); root.addWidget(subtitle)
        cards = QGridLayout(); self.cards = {}
        for i, (key, label) in enumerate((("allocation", "Total allocation"), ("total", "Total leads"), ("delivered", "Delivered leads"), ("remaining", "Remaining to deliver"))):
            card = MetricCard(label); card.setMinimumHeight(92); card.setMaximumHeight(112)
            card.layout().setContentsMargins(14, 8, 14, 8); card.layout().setSpacing(3)
            card.value_label.setStyleSheet("font-size: 22pt; font-weight: 700;")
            cards.addWidget(card, 0, i); self.cards[key] = card
        root.addLayout(cards)
        toolbar = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Search campaign name or CID…"); self.search.setAccessibleName("Search campaigns")
        self.search.setMaximumWidth(300); toolbar.addWidget(self.search, 1)
        self.status = QComboBox(); self.status.addItems(["All statuses", *STATUSES, "Not set"]); self.status.setAccessibleName("Filter campaign status")
        toolbar.addWidget(self.status)
        self.row_count = QLabel(); self.row_count.setObjectName("metricHint"); toolbar.addWidget(self.row_count)
        toolbar.addStretch(1)
        self.edit_button = QPushButton("Edit plan & delivery"); self.edit_button.setIcon(icon("edit")); self.edit_button.setObjectName("primaryButton")
        self.edit_button.clicked.connect(self.edit_plan); toolbar.addWidget(self.edit_button); root.addLayout(toolbar)
        self.split = QSplitter(Qt.Orientation.Vertical); self.split.setChildrenCollapsible(False); self.split.setHandleWidth(8)
        self.split.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Ignored)
        self.split.setMinimumHeight(460)
        self.table = QTableWidget(0, len(HEADERS)); self.table.setObjectName("campaignDashboardTable")
        self.table.setHorizontalHeaderLabels([h.replace("Total allocation", "Total\nallocation").replace("Remaining to deliver", "Remaining\nto deliver").replace("Average leads per day", "Average leads\nper day") for h in HEADERS])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True); self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(32); self.table.setWordWrap(False)
        self.table.setMinimumHeight(170); self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True); self.table.horizontalHeader().setMinimumHeight(48)
        for i, width in enumerate((190, 85, 95, 105, 105, 85, 105, 115, 105, 110, 115, 90)):
            self.table.setColumnWidth(i, width)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.table.itemDoubleClicked.connect(lambda *_: self.edit_plan())
        self.split.addWidget(self.table)
        self.charts = CampaignCharts(controller); self.split.addWidget(self.charts)
        self.split.setStretchFactor(0, 1); self.split.setStretchFactor(1, 1); self.split.setSizes([290, 270]); root.addWidget(self.split, 1)
        self.details = QLabel(); self.details.setWordWrap(True); self.details.setTextFormat(Qt.TextFormat.PlainText); self.details.setObjectName("metricHint"); root.addWidget(self.details)
        self.warning = QLabel(); self.warning.setWordWrap(True); self.warning.setTextFormat(Qt.TextFormat.PlainText); self.warning.setObjectName("muted"); root.addWidget(self.warning)
        self.search.textChanged.connect(self.render); self.status.currentTextChanged.connect(self.render)
        self.refresh()

    def refresh(self):
        try:
            self.rows, self.warnings = campaign_progress(self.controller)
        except (sqlite3.Error, OSError, ValueError):
            self.rows = []; self.warnings = ["Campaign data could not be loaded. Refresh to try again; existing data has been preserved."]
        self.render()

    def current_campaign(self):
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            return None
        cid = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        return next((item for item in self.rows if item.campaign_id == cid), None)

    def render(self, *_):
        previous = self.current_campaign(); selected = previous.campaign_id if previous else None
        query = self.search.text().strip().casefold(); status = self.status.currentText()
        rows = [item for item in self.rows if (not query or query in f"{item.campaign_name} {item.campaign_id}".casefold())
                and (status == "All statuses" or (item.status or "Not set") == status)]
        self.filtered_rows = rows
        self.table.setSortingEnabled(False); self.table.blockSignals(True); self.table.setRowCount(len(rows))
        for r, item in enumerate(rows):
            values = [item.campaign_name, item.campaign_id or "—", item.allocation, item.start, item.end,
                      item.total, item.qualified, item.disqualified, item.delivered, item.remaining, item.average, item.status or "Not set"]
            for c, value in enumerate(values):
                text = "Not set" if value is None and c in {2, 3, 4, 8} else ("—" if value is None else
                       value.strftime("%d-%b-%Y") if c in {3, 4} else f"{value:,}" if isinstance(value, int) else str(value))
                cell = DashboardItem(text); cell.setData(Qt.ItemDataRole.UserRole, item.campaign_id)
                cell.setData(Qt.ItemDataRole.UserRole + 1, value.toordinal() if c in {3, 4} and value is not None else value)
                if c in {2, 5, 6, 7, 8, 9, 10}: cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if c == 10: cell.setToolTip(item.pace_note())
                elif c == 8: cell.setToolTip("Cumulative delivered count entered by the user. Exports do not change this value.")
                elif c == 9: cell.setToolTip("Total allocation minus delivered leads, with a minimum of zero.")
                elif c in {5, 6, 7}: cell.setToolTip(item.warning or "Counts use saved campaign workspaces plus current unsaved edits. Edited leads awaiting validation are pending.")
                if c == 11 and item.status:
                    bg, fg = {"Running": ("#D5F8EC", "#07694D"), "Closed": ("#E7EDF6", "#425676"), "Paused": ("#FFF0BC", "#805300")}[item.status]
                    cell.setBackground(QColor(bg)); cell.setForeground(QColor(fg))
                self.table.setItem(r, c, cell)
        self.table.blockSignals(False); self.table.setSortingEnabled(True)
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) == selected:
                self.table.selectRow(r); break
        else:
            if rows: self.table.selectRow(0)
        self.row_count.setText(f"{len(rows):,} rows")
        for key, card in self.cards.items():
            known = [getattr(row, key) for row in rows if getattr(row, key) is not None]
            value = f"{sum(known):,}" if known else "—"
            missing = len(rows) - len(known)
            subtitle = f"{missing} not configured / unavailable" if missing else "Filtered campaigns"
            if key == "total" and known:
                subtitle = f"{sum(row.qualified or 0 for row in rows):,} qualified · {sum(row.disqualified or 0 for row in rows):,} disqualified"
                if missing: subtitle += f" · {missing} unavailable"
            card.set_value(value, subtitle)
        self.charts.refresh(rows)
        warnings = list(self.warnings)
        if not self.rows and not warnings: warnings.append("No campaigns yet. Open Campaign Manager to import a campaign package, then set its plan and delivery totals here.")
        self.warning.setText("\n".join(warnings)); self.warning.setVisible(bool(warnings))
        self.selection_changed()

    def selection_changed(self):
        item = self.current_campaign()
        self.edit_button.setEnabled(bool(item and item.campaign_id))
        self.details.setText((item.pace_note() + (" " + item.warning if item.warning else "")) if item else
                             "Average leads per day = total allocation ÷ calendar days (both dates included), rounded up.")

    def edit_plan(self):
        item = self.current_campaign()
        if not item or not item.campaign_id: return
        dialog = CampaignPlanDialog(self, item)
        if dialog.exec():
            try:
                CampaignTrackingStore().save(item.campaign_id, **dialog.values())
                self.refresh()
            except (ValueError, sqlite3.Error) as exc:
                QMessageBox.warning(self, "Campaign plan", str(exc) if isinstance(exc, ValueError) else "The plan could not be saved. Try again after other database work finishes.")
