from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize, QTimer, QEvent
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QProgressBar,
    QVBoxLayout, QWidget, QToolButton, QMenu, QInputDialog, QMessageBox, QSplitter, QSizePolicy,
)

from app.constants import MISSING_VALUE, STANDARD_HEADERS
from app.ui_qt.dialogs.filter_dialog import ColumnFilterDialog
from app.ui_qt.widgets.lead_table import LeadFilterProxyModel, LeadTableModel, LeadTableView
from app.ui_qt.widgets.icons import icon
from app.ui_qt.widgets.lead_details import LeadDetailsPanel, LeadEditDialog
from app.ui_qt.pages.workspace_tools import WorkspaceTools
from app.ui_qt.pages.formula_tools import FormulaTools
from app.core.column_filter import value_key


class LeadsPage(FormulaTools, WorkspaceTools, QWidget):
    import_requested = Signal()
    paste_requested = Signal()
    load_tal_requested = Signal()
    load_suppression_requested = Signal()
    validate_requested = Signal()
    find_emails_requested = Signal()
    populate_requested = Signal()
    database_connection_requested = Signal()
    add_to_database_requested = Signal()
    save_requested = Signal()
    export_requested = Signal()
    new_requested = Signal()
    validation_summary_requested = Signal()
    pause_requested = Signal()
    resume_requested = Signal()
    cancel_requested = Signal()
    columns_added = Signal()
    manage_references_requested = Signal()
    validate_selected_requested = Signal()
    validate_edited_requested = Signal()
    workspace_requested = Signal(str)
    recheck_requested = Signal(int)

    def __init__(self, controller, parent=None, *, compact=False):
        super().__init__(parent)
        self.setObjectName("leadWorkspace")
        self.controller = controller
        self._data_busy = False
        self._details_preference = None
        root = QVBoxLayout(self); root.setContentsMargins(12, 12, 12, 10); root.setSpacing(8)

        header = QHBoxLayout(); header.setSpacing(8)
        self.heading_row = header
        headings = QVBoxLayout(); headings.setSpacing(2)
        title = QLabel("Lead Workspace"); title.setObjectName("pageTitle"); headings.addWidget(title)
        subtitle = QLabel("View, manage, and validate leads across your campaigns.")
        subtitle.setObjectName("muted"); headings.addWidget(subtitle); header.addLayout(headings, 1)
        if compact:title.hide(); subtitle.hide()
        self.populate_button = QToolButton()
        self.populate_button.setText("Populate from database")
        self.populate_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.populate_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        database_menu = QMenu(self.populate_button)
        database_menu.addAction("Database connection & column mapping…").triggered.connect(self.database_connection_requested)
        self.populate_button.setMenu(database_menu)
        self.populate_button.setIcon(icon("database"))
        self.populate_button.setToolTip("Choose columns to fill using saved prospect LinkedIn links and company websites")
        self.populate_button.clicked.connect(self.populate_requested)
        header.addWidget(self.populate_button)
        self.import_button = QPushButton("Import leads"); self.import_button.setObjectName("primaryButton")
        self.import_button.setIcon(icon("plus", "#FFFFFF")); self.import_button.clicked.connect(self.import_requested)
        header.addWidget(self.import_button)
        export = QPushButton("Export"); export.setIcon(icon("download")); export.clicked.connect(self.export_requested)
        self.export_button = export
        header.addWidget(export)
        more = QToolButton(); more.setIcon(icon("more")); more.setAccessibleName("More worksheet actions")
        more.setToolTip("More worksheet actions"); more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more_menu = QMenu(more)
        for text, signal in (("Paste from Excel", self.paste_requested), ("Save working copy", self.save_requested),
                             ("Add current leads to reference database…", self.add_to_database_requested),
                             ("New worksheet…", self.new_requested)):
            more_menu.addAction(text).triggered.connect(lambda checked=False, target=signal: target.emit())
        self.more_menu=more_menu
        self.worksheet_more = more
        more.setMenu(more_menu); header.addWidget(more)
        self.header_widget=QWidget(); self.header_widget.setLayout(header); root.addWidget(self.header_widget)

        actions = QFrame(); actions.setObjectName("toolbarCard")
        self.toolbar_card = actions
        toolbar = QVBoxLayout(actions); toolbar.setContentsMargins(8, 7, 8, 6); toolbar.setSpacing(5)
        self.build_workspace_selector(toolbar)
        self.search = QLineEdit(); self.search.setMinimumWidth(180); self.search.setMaximumWidth(260)
        self.search.setPlaceholderText("Search leads…  Ctrl+F"); self.search.setAccessibleName("Search all lead fields")
        self.search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.workspace_row.addWidget(self.search, 1)
        self.status = QComboBox(); self.status.setAccessibleName("Validation status filter")
        self.status.addItems(["All", "Valid", "Valid - Email Generated", "Warning", "Invalid", "Suppressed",
                              "Outside TAL", "Disqualified", "Duplicate", "Manual Review", "Needs validation"])
        self.status.setMinimumWidth(120); self.status.setMaximumWidth(155); self.status.setToolTip("Filter by validation status")
        self.workspace_row.addWidget(self.status)
        self.clear_filters_btn = QPushButton("Reset"); self.clear_filters_btn.setToolTip("Clear all search, status, and column filters")
        self.clear_filters_btn.setObjectName("ghostButton"); self.workspace_row.addWidget(self.clear_filters_btn)
        self.workspace_row.addStretch(1)
        self._filter_widgets = (self.workspace_label, self.workspace_selector, self.search, self.status, self.clear_filters_btn)

        self.action_controls = QWidget()
        al = QHBoxLayout(self.action_controls); al.setContentsMargins(0, 0, 0, 0); al.setSpacing(5)
        for name, symbol, items in (
            ("Add data", "plus", (("New worksheet", self.new_requested), ("Paste from Excel", self.paste_requested))),
            ("Reference lists", "folder", (("Load TAL", self.load_tal_requested), ("Load Suppression", self.load_suppression_requested), ("Manage saved lists…", self.manage_references_requested))),
        ):
            btn = QToolButton(); btn.setText(name); btn.setIcon(icon(symbol))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup); menu = QMenu(btn)
            for text, signal in items:
                menu.addAction(text).triggered.connect(lambda checked=False, target=signal: target.emit())
            btn.setMenu(menu); al.addWidget(btn)
        self.add_columns_button = QPushButton("Add columns"); self.add_columns_button.setIcon(icon("columns"))
        self.add_columns_button.clicked.connect(self.add_columns); al.addWidget(self.add_columns_button)
        al.addStretch(1)
        self.validation_actions = QWidget(); validation_buttons = QHBoxLayout(self.validation_actions)
        validation_buttons.setContentsMargins(0, 0, 0, 0); validation_buttons.setSpacing(5)
        for text, signal, primary, symbol in (
            ("Validate", self.validate_requested, True, "validation"),
            ("Find emails", self.find_emails_requested, False, "mail"),
            ("Summary", self.validation_summary_requested, False, "dashboard"),
        ):
            btn = QPushButton(text); btn.setIcon(icon(symbol, "#FFFFFF" if primary else "#627697"))
            if primary: btn.setObjectName("primaryButton")
            btn.clicked.connect(signal); validation_buttons.addWidget(btn)
            if primary:
                scope = QToolButton(); scope.setText("Rows"); scope.setToolTip("Choose which leads to validate")
                scope.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup); menu = QMenu(scope)
                for title, target in (("Validate all rows", self.validate_requested), ("Validate selected rows", self.validate_selected_requested), ("Validate edited / unfinished rows", self.validate_edited_requested)):
                    menu.addAction(title).triggered.connect(lambda checked=False, target=target: target.emit())
                scope.setMenu(menu); validation_buttons.addWidget(scope)
        al.addWidget(self.validation_actions); toolbar.addWidget(self.action_controls)
        self._toolbar_layout = toolbar; self._inline_actions = False
        self.reference_label = QLabel(); self.reference_label.setTextFormat(Qt.TextFormat.PlainText)
        self.reference_label.setObjectName("metricHint"); self.reference_label.setWordWrap(True)
        toolbar.addWidget(self.reference_label); root.addWidget(actions)
        self.job_controls = QWidget(); job = QHBoxLayout(self.job_controls); job.setContentsMargins(0, 0, 0, 0)
        self.job_label = QLabel("Batch progress"); self.job_label.setObjectName("muted"); job.addWidget(self.job_label)
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0)
        self.progress.setTextVisible(False); self.progress.setFixedHeight(7); job.addWidget(self.progress, 1)
        self.pause_btn = QPushButton("Pause"); self.pause_btn.setEnabled(False); self.pause_btn.clicked.connect(self.pause_requested)
        self.resume_btn = QPushButton("Resume"); self.resume_btn.setEnabled(False); self.resume_btn.clicked.connect(self.resume_requested)
        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.setEnabled(False); self.cancel_btn.clicked.connect(self.cancel_requested)
        job.addWidget(self.pause_btn); job.addWidget(self.resume_btn); job.addWidget(self.cancel_btn)
        toolbar.addWidget(self.job_controls); self.job_controls.hide()
        self.email_summary = QLabel(); self.email_summary.setWordWrap(True); self.email_summary.setObjectName("muted")
        self.email_summary.hide(); root.addWidget(self.email_summary)

        self.content_splitter = QSplitter(Qt.Orientation.Horizontal); self.content_splitter.setHandleWidth(8)
        self.content_splitter.setChildrenCollapsible(False); root.addWidget(self.content_splitter, 1)
        self.table_card = QFrame(); self.table_card.setObjectName("tableCard"); self.table_card.setMinimumWidth(500)
        card = QVBoxLayout(self.table_card); card.setContentsMargins(0, 0, 0, 0); card.setSpacing(0)
        table_top = QWidget(); top = QVBoxLayout(table_top); top.setContentsMargins(10, 7, 10, 7); top.setSpacing(5)
        self.table_top = table_top
        table_heading = QHBoxLayout(); table_heading.setSpacing(8)
        self.table_title = QLabel("Leads (0)"); self.table_title.setObjectName("sectionTitle")
        self.count_label = QLabel("0 of 0 leads"); self.count_label.setObjectName("metricHint")
        table_heading.addWidget(self.table_title); table_heading.addStretch(1)
        self.details_button = QPushButton("Details"); self.details_button.setIcon(icon("panel")); self.details_button.setCheckable(True)
        self.details_button.setToolTip("Show or hide selected lead details"); self.details_button.clicked.connect(self.toggle_details)
        table_heading.addWidget(self.details_button); top.addLayout(table_heading)
        self.build_view_controls(top); card.addWidget(table_top)
        self._table_top_layout = top; self._table_heading = table_heading; self._inline_views = False
        self.empty_hint = QLabel("No leads yet. Import a workbook, paste from Excel, or add results from Scraper.")
        self.empty_hint.setObjectName("emptyHint"); self.empty_hint.setWordWrap(True); card.addWidget(self.empty_hint)
        self.model = LeadTableModel(controller); self.proxy = LeadFilterProxyModel(controller); self.proxy.setSourceModel(self.model)
        self.table = LeadTableView(); self.table.setModel(self.proxy); self.table.setCornerButtonEnabled(True)
        self.build_formula_bar(card)
        self.build_table_pair(card)
        self.connect_formula_bar()
        footer = QHBoxLayout(); footer.setContentsMargins(10, 5, 10, 5); footer.setSpacing(12)
        footer.addWidget(self.count_label)
        footer.addWidget(self.filter_hint, 1)
        self.selection_label = QLabel("Click a cell to review a lead"); self.selection_label.setObjectName("metricHint")
        footer.addWidget(self.selection_label); card.addLayout(footer)
        self.content_splitter.addWidget(self.table_card)
        self.details_panel = LeadDetailsPanel(controller); self.content_splitter.addWidget(self.details_panel)
        self.content_splitter.setStretchFactor(0, 1); self.content_splitter.setStretchFactor(1, 0)
        self.content_splitter.setSizes([850, 330])
        self.details_panel.close_requested.connect(lambda: self.toggle_details(False))
        self.details_panel.edit_requested.connect(self.edit_lead)
        self.details_panel.notes_requested.connect(lambda row: self.edit_lead(row, focus="Notes"))
        self.details_panel.recheck_requested.connect(lambda row: self.recheck_requested.emit(row))
        self.table_card.installEventFilter(self)
        self.table.selectionModel().currentChanged.connect(self.refresh_details)
        self.table.selectionModel().selectionChanged.connect(self.update_selection_count)
        self.model.changed.connect(self.refresh_details)
        self.search.textChanged.connect(self.proxy.set_search); self.status.currentTextChanged.connect(self.proxy.set_status)
        self.clear_filters_btn.clicked.connect(self.clear_filters)
        self.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow_controls()
        if hasattr(self, "details_panel"):
            show = self._details_preference if self._details_preference is not None else self.width() >= 1180
            visible = bool(show and self.width() >= 880)
            self.details_panel.setVisible(visible)
            self.details_button.setChecked(visible)
            self.details_button.setEnabled(self.width() >= 880 and not self._data_busy)
            self.selection_label.setVisible(self.table_card.width() >= 650)

    def reflow_controls(self):
        if getattr(self,'excel_layout',False):return
        if not hasattr(self, "details_panel"):
            return
        # Use the actual font and control widths, including display scaling.
        filter_width = sum(max(widget.minimumWidth(), min(widget.maximumWidth(), widget.sizeHint().width()))
                           for widget in self._filter_widgets)
        needed = filter_width + self.action_controls.minimumSizeHint().width() + 42
        inline = self.width() - 40 >= needed
        if inline != self._inline_actions:
            self._inline_actions = inline
            if inline:
                self._toolbar_layout.removeWidget(self.action_controls)
                self.action_controls.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                self.workspace_row.addWidget(self.action_controls)
            else:
                self.workspace_row.removeWidget(self.action_controls)
                self.action_controls.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
                self._toolbar_layout.insertWidget(1, self.action_controls)
            self.action_controls.show()
        # Reparenting the controls from one row to two changes their minimum
        # height. Propagate it immediately so the grid cannot squeeze the text
        # after a window resize or sidebar toggle.
        self._toolbar_layout.invalidate()
        card=self._toolbar_layout.parentWidget()
        card.setMinimumHeight(card.minimumSizeHint().height())
        card.updateGeometry()
        self.reflow_table_heading()

    def reflow_table_heading(self):
        if getattr(self,'excel_layout',False):return
        if not hasattr(self, "_table_top_layout"):
            return
        needed = self.table_title.sizeHint().width() + self.view_controls.minimumSizeHint().width() + self.details_button.sizeHint().width() + 50
        inline = self.table_card.width() >= needed
        if inline != self._inline_views:
            self._inline_views = inline
            if inline:
                self._table_top_layout.removeWidget(self.view_controls)
                self._table_heading.insertWidget(2, self.view_controls)
            else:
                self._table_heading.removeWidget(self.view_controls)
                self._table_top_layout.addWidget(self.view_controls)
            self.view_controls.show()

    def eventFilter(self, watched, event):
        if watched is getattr(self, "formula_entry", None) and self.formula_key_event(event):
            return True
        if watched is getattr(self, "table_card", None) and event.type() == QEvent.Type.Resize:
            self.reflow_table_heading()
            if hasattr(self, "selection_label"):
                self.selection_label.setVisible(self.table_card.width() >= 650)
        return super().eventFilter(watched, event)

    def toggle_details(self, checked):
        self._details_preference = bool(checked)
        self.details_panel.setVisible(bool(checked))
        self.details_button.setChecked(bool(checked))
        if checked: self.content_splitter.setSizes([max(500, self.width() - 360), 330])

    def refresh_details(self, *_):
        if not hasattr(self, "details_panel"): return
        index = self.proxy.mapToSource(self.table.currentIndex())
        row = index.row() if index.isValid() else None
        self.details_panel.refresh(row)
        self.update_selection_count()

    def update_selection_count(self, *_):
        if not hasattr(self, "selection_label"): return
        count = len(self.selected_rows())
        self.selection_label.setText(f"{count:,} lead{'s' if count != 1 else ''} selected" if count else "Click a cell to review a lead")

    def edit_lead(self, row, focus=None):
        if self._data_busy or not 0 <= row < len(self.controller.data_manager.records): return
        dialog = LeadEditDialog(self, {header: self.controller.data_manager.raw_value(row, header)
                                      for header in self.controller.data_manager.headers})
        if focus:
            QTimer.singleShot(0, dialog, lambda: dialog.focus_field(focus))
        if not dialog.exec(): return
        changed = self.controller.edit_cells({(row, field): value for field, value in dialog.values().items()}, "Edit lead details")
        if changed:
            self.model.dataChanged.emit(self.model.index(0, 0), self.model.index(self.model.rowCount()-1, self.model.columnCount()-1))
            self.model.changed.emit()
        self.refresh_details()

    def add_columns(self):
        if self._data_busy:
            return
        text, accepted = QInputDialog.getMultiLineText(
            self, "Add Columns", "Enter one column name per line. New columns appear on the right.")
        if not accepted or not text.strip():
            return
        try:
            names = [line.strip() for line in text.splitlines() if line.strip()]
            self.model.beginResetModel()
            try:
                self.controller.change_columns(names)
            finally:
                self.model.endResetModel()
            self.refresh()
            self.view_selector.setCurrentText("All columns")
            self.apply_column_view()
            index = self.proxy.index(0, len(self.controller.data_manager.headers) - len(names))
            if index.isValid():
                self.table.setCurrentIndex(index)
                self.table.scrollTo(index)
            self.columns_added.emit()
        except ValueError as exc:
            QMessageBox.warning(self, "Column names", str(exc))

    def refresh(self):
        workspace = self.controller.workspace_key
        current = self.proxy.mapToSource(self.table.currentIndex())
        selected = (current.row(), current.column()) if current.isValid() and getattr(self, "_last_workspace", workspace) == workspace else None
        self._last_workspace = workspace
        self.reference_label.setText(self.controller.reference_summary())
        self.model.refresh()
        self.proxy.refresh_filter()
        if hasattr(self, "frozen_table"):
            self.apply_column_view()
            self.undo_button.setEnabled(bool(self.controller.history.undo_stack))
            self.redo_button.setEnabled(bool(self.controller.history.redo_stack))
        count = len(self.controller.data_manager.records)
        visible = sum(1 for r in range(self.proxy.rowCount()) if self.proxy.mapToSource(self.proxy.index(r, 0)).row() < count)
        self.count_label.setText(f"{visible:,} of {count:,} leads")
        self.empty_hint.setVisible(visible == 0)
        self.table_title.setText(f"Leads ({count:,})")
        if selected and selected[0] < count:
            self.restore_cell(*selected)
        self.refresh_details()
        self.sync_formula_bar()

    def set_data_busy(self, busy):
        self._data_busy = busy
        self.formula_bar.setEnabled(not busy)
        self.table.setEnabled(not busy)
        self.frozen_table.setEnabled(not busy)
        self.workspace_selector.setEnabled(not busy)
        self.view_selector.setEnabled(not busy)
        self.freeze_identity.setEnabled(not busy)
        for control in self.findChildren(QPushButton) + self.findChildren(QToolButton):
            if not self.job_controls.isAncestorOf(control):
                control.setEnabled(not busy)
        self.details_panel.set_busy(busy)
        self.details_button.setEnabled(not busy and self.width() >= 880)
        if not busy:
            self.update_filter_display()
            self.undo_button.setEnabled(bool(self.controller.history.undo_stack))
            self.redo_button.setEnabled(bool(self.controller.history.redo_stack))

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
        if column < 0 or column >= self.model.columnCount(): return
        values = self.proxy.column_values(column)
        selected = self.proxy.column_filters.get(column)
        dialog = ColumnFilterDialog(self, self.controller.data_manager.headers[column], values, selected,
                                    self.proxy.column_conditions.get(column))
        if dialog.exec():
            if dialog.sort_order is not None:
                self.table.sortByColumn(column, dialog.sort_order)
            elif dialog.clear_requested:
                self.proxy.set_column_filter(column, None)
                self.proxy.set_condition(column, None)
            else:
                chosen = dialog.selected_values()
                # All available values means no restriction, except an explicit empty selection.
                if chosen and chosen == {value_key(value) for value in values}:
                    chosen = None
                self.proxy.set_column_filter(column, chosen)
                self.proxy.set_condition(column, dialog.condition())
            self.update_filter_display()
