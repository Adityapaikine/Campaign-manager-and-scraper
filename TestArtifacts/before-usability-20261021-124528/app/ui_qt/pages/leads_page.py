from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QProgressBar,
    QVBoxLayout, QWidget, QToolButton, QMenu, QInputDialog, QMessageBox,
)

from app.constants import MISSING_VALUE, STANDARD_HEADERS
from app.ui_qt.dialogs.filter_dialog import ColumnFilterDialog
from app.ui_qt.widgets.lead_table import LeadFilterProxyModel, LeadTableModel, LeadTableView
from app.ui_qt.widgets.icons import icon


class LeadsPage(QWidget):
    import_requested = Signal()
    paste_requested = Signal()
    load_tal_requested = Signal()
    load_suppression_requested = Signal()
    validate_requested = Signal()
    find_emails_requested = Signal()
    save_requested = Signal()
    export_requested = Signal()
    new_requested = Signal()
    validation_summary_requested = Signal()
    pause_requested = Signal()
    resume_requested = Signal()
    cancel_requested = Signal()
    columns_added = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        header = QHBoxLayout()
        headings = QVBoxLayout(); headings.setSpacing(4)
        title = QLabel("Leads Workspace")
        title.setObjectName("pageTitle")
        headings.addWidget(title)
        subtitle = QLabel("Review, enrich, and validate your next delivery."); subtitle.setObjectName("muted")
        headings.addWidget(subtitle); header.addLayout(headings)
        header.addStretch(1)
        self.count_label = QLabel("0 records")
        self.count_label.setObjectName("badge")
        header.addWidget(self.count_label)
        for text, signal, symbol in (("Import", self.import_requested, "upload"), ("Export", self.export_requested, "download")):
            btn = QPushButton(text); btn.setIcon(icon(symbol)); btn.clicked.connect(signal)
            btn.setCursor(Qt.CursorShape.PointingHandCursor); header.addWidget(btn)
        root.addLayout(header)

        actions = QFrame()
        actions.setObjectName("toolbarCard")
        toolbar = QVBoxLayout(actions); toolbar.setContentsMargins(14, 14, 14, 14); toolbar.setSpacing(12)
        al = QHBoxLayout(); al.setSpacing(8)
        for name, symbol, items in (
            ("Add data", "plus", (("New worksheet", self.new_requested), ("Paste from Excel", self.paste_requested))),
            ("Reference lists", "folder", (("Load TAL", self.load_tal_requested), ("Load Suppression", self.load_suppression_requested))),
        ):
            btn = QToolButton(); btn.setText(name); btn.setIcon(icon(symbol)); btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(btn)
            for title, signal in items:
                action = menu.addAction(title)
                action.triggered.connect(lambda _=False, target=signal: target.emit())
            btn.setMenu(menu); al.addWidget(btn)
        self.add_columns_button = QPushButton("Add Columns")
        self.add_columns_button.setIcon(icon("plus"))
        self.add_columns_button.clicked.connect(self.add_columns)
        al.addWidget(self.add_columns_button)
        al.addStretch(1)
        buttons = [
            ("Validate", self.validate_requested, True, "validation"),
            ("Find Emails", self.find_emails_requested, False, "mail"),
            ("Summary", self.validation_summary_requested, False, "dashboard"),
        ]
        for text, signal, primary, symbol in buttons:
            btn = QPushButton(text)
            btn.setIcon(icon(symbol, "#FFFFFF" if primary else "#71819B")); btn.setIconSize(QSize(17, 17))
            if primary:
                btn.setObjectName("primaryButton")
            btn.clicked.connect(signal)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            al.addWidget(btn)
        toolbar.addLayout(al)
        self.reference_label = QLabel()
        self.reference_label.setTextFormat(Qt.TextFormat.PlainText)
        self.reference_label.setObjectName("muted")
        self.reference_label.setWordWrap(True)
        toolbar.addWidget(self.reference_label)
        root.addWidget(actions)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search all lead fields…   Ctrl+F")
        self.search.addAction(icon("scraper"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        filters.addWidget(self.search, 1)
        self.status = QComboBox()
        self.status.addItems([
            "All", "Valid", "Valid - Email Generated", "Warning", "Invalid", "Suppressed",
            "Outside TAL", "Disqualified", "Duplicate", "Manual Review",
        ])
        filters.addWidget(self.status)
        self.clear_filters_btn = QPushButton("Clear Filters")
        self.clear_filters_btn.setObjectName("ghostButton")
        filters.addWidget(self.clear_filters_btn)
        toolbar.addLayout(filters)
        self.job_controls = QWidget(); job = QHBoxLayout(self.job_controls); job.setContentsMargins(0, 0, 0, 0)
        self.job_label = QLabel("Batch progress"); self.job_label.setObjectName("muted"); job.addWidget(self.job_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False); self.progress.setFixedHeight(7)
        job.addWidget(self.progress, 1)
        self.pause_btn = QPushButton("Pause"); self.pause_btn.setEnabled(False); self.pause_btn.clicked.connect(self.pause_requested)
        self.resume_btn = QPushButton("Resume"); self.resume_btn.setEnabled(False); self.resume_btn.clicked.connect(self.resume_requested)
        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.setEnabled(False); self.cancel_btn.clicked.connect(self.cancel_requested)
        job.addWidget(self.pause_btn); job.addWidget(self.resume_btn); job.addWidget(self.cancel_btn)
        toolbar.addWidget(self.job_controls); self.job_controls.hide()
        self.empty_hint = QLabel("No leads yet. Import a workbook, paste from Excel, or add results from Scraper.")
        self.empty_hint.setObjectName("muted"); self.empty_hint.setWordWrap(True); root.addWidget(self.empty_hint)
        self.email_summary = QLabel()
        self.email_summary.setWordWrap(True)
        self.email_summary.setObjectName("muted")
        self.email_summary.hide()
        root.addWidget(self.email_summary)

        self.model = LeadTableModel(controller)
        self.proxy = LeadFilterProxyModel(controller)
        self.proxy.setSourceModel(self.model)
        self.table = LeadTableView()
        self.table.setModel(self.proxy)
        self.table.setCornerButtonEnabled(True)
        self.table.setFrozen = None  # API marker: frozen columns intentionally handled later through split view.
        self.table.request_filter.connect(self.open_filter)
        self.table.request_find.connect(self.search.setFocus)
        self.table.request_save.connect(self.save_requested)
        self.table.request_validate.connect(self.validate_requested)
        self.table.data_mutated.connect(self.refresh)
        root.addWidget(self.table, 1)

        self.search.textChanged.connect(self.proxy.set_search)
        self.status.currentTextChanged.connect(self.proxy.set_status)
        self.clear_filters_btn.clicked.connect(self.clear_filters)
        self.refresh()

    def add_columns(self):
        text, accepted = QInputDialog.getMultiLineText(
            self, "Add Columns", "Enter one column name per line. New columns appear on the right.")
        if not accepted or not text.strip():
            return
        try:
            names = [line.strip() for line in text.splitlines() if line.strip()]
            self.model.beginResetModel()
            try:
                self.controller.data_manager.add_columns(names)
            finally:
                self.model.endResetModel()
            self.refresh()
            index = self.proxy.index(0, len(self.controller.data_manager.headers) - len(names))
            if index.isValid():
                self.table.setCurrentIndex(index)
                self.table.scrollTo(index)
            self.columns_added.emit()
        except ValueError as exc:
            QMessageBox.warning(self, "Column names", str(exc))

    def refresh(self):
        self.reference_label.setText(self.controller.reference_summary())
        self.model.refresh()
        self.proxy.invalidateFilter()
        count = len(self.controller.data_manager.records)
        visible = sum(1 for r in range(self.proxy.rowCount()) if self.proxy.mapToSource(self.proxy.index(r, 0)).row() < count)
        self.count_label.setText(f"{visible:,} of {count:,} leads")
        self.empty_hint.setVisible(count == 0)

    def set_data_busy(self, busy):
        self.table.setEnabled(not busy)
        for control in self.findChildren(QPushButton) + self.findChildren(QToolButton):
            if not self.job_controls.isAncestorOf(control):
                control.setEnabled(not busy)

    def set_job_running(self, running: bool, paused: bool = False):
        self.job_controls.setVisible(running)
        self.pause_btn.setEnabled(running and not paused)
        self.resume_btn.setEnabled(running and paused)
        self.cancel_btn.setEnabled(running)
        if not running:
            self.progress.setValue(0)

    def clear_filters(self):
        self.search.clear()
        self.status.setCurrentText("All")
        self.proxy.clear_filters()

    def open_filter(self, column: int):
        values = []
        seen = set()
        for record in self.controller.data_manager.records:
            value = str(record.get(self.controller.data_manager.headers[column], MISSING_VALUE))
            display = "(Blanks)" if value in {"", MISSING_VALUE} else value
            if display not in seen:
                values.append(display)
                seen.add(display)
        values.sort(key=lambda x: (x == "(Blanks)", x.casefold()))
        selected = self.proxy.column_filters.get(column, set(values))
        dialog = ColumnFilterDialog(self, self.controller.data_manager.headers[column], values, selected)
        if dialog.exec():
            chosen = dialog.selected_values()
            if chosen == set(values):
                chosen = set()
            self.proxy.set_column_filter(column, chosen)
            self.refresh()
