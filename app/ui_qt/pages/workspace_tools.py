from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QComboBox, QLabel, QHBoxLayout, QPushButton, QCheckBox, QWidget, QMessageBox

from app.ui_qt.dialogs.workspace_dialogs import ColumnViewDialog
from app.ui_qt.widgets.lead_table import LeadTableView
from app.ui_qt.widgets.icons import icon


PRESET_VIEWS = {
    "All columns": None,
    "Lead overview": ["Date", "Campaign Name", "Agent Name", "Calling Agent Name", "Phone Number", "Dispo", "Comment"],
    "Workflow": ["First Name", "Last Name", "Company Name", "Workflow Status", "Current Department", "Assigned User"],
    "Research": ["First Name", "Last Name", "Company Name", "Company Website", "Job Title", "Industry",
                 "Country", "Phone Number", "Prospect LinkedIn Link", "Business Email ID"],
    "Email Finding": ["First Name", "Last Name", "Company Name", "Company Website", "Business Email ID",
                      "Email Status", "Prospect LinkedIn Link", "QA Status", "Primary Reason"],
    "QA Review": ["First Name", "Last Name", "Company Name", "Business Email ID", "Job Title", "Country",
                  "Company Website", "QA Status", "Primary Reason", "QA Name", "Audited Date", "Comment"],
}
IDENTITY_COLUMNS = {"First Name", "Last Name", "Company Name"}


class WorkspaceTools:
    def build_workspace_selector(self, root):
        row = QHBoxLayout(); row.setSpacing(6)
        self.workspace_label = QLabel("Workspace")
        row.addWidget(self.workspace_label)
        self.workspace_selector = QComboBox()
        self.workspace_selector.setMinimumWidth(170)
        self.workspace_selector.setMaximumWidth(210)
        self.workspace_selector.setAccessibleName("Campaign workspace")
        row.addWidget(self.workspace_selector)
        self.workspace_selector.setToolTip("Each campaign keeps its own leads and reference lists.")
        self.workspace_row = row
        root.addLayout(row)
        self.update_workspaces()
        self.workspace_selector.currentIndexChanged.connect(lambda: self.workspace_requested.emit(self.workspace_selector.currentData() or ""))

    def update_workspaces(self):
        selected = self.controller.active_campaign.campaign_id if self.controller.active_campaign else ""
        self.workspace_selector.blockSignals(True)
        self.workspace_selector.clear()
        self.workspace_selector.addItem("General workspace", "")
        for profile in self.controller.campaign_store.list():
            self.workspace_selector.addItem(f"{profile.campaign_id} — {profile.campaign_name}", profile.campaign_id)
        self.workspace_selector.setCurrentIndex(max(0, self.workspace_selector.findData(selected)))
        self.workspace_selector.blockSignals(False)

    def build_view_controls(self, toolbar):
        self.view_controls = QWidget()
        row = QHBoxLayout(self.view_controls); row.setContentsMargins(0, 0, 0, 0); row.setSpacing(6)
        row.addWidget(QLabel("View"))
        self.view_selector = QComboBox()
        self.custom_views = self.controller.settings_service.get("lead_column_views", {})
        self.view_selector.addItems([*PRESET_VIEWS, *[name for name in self.custom_views if name not in PRESET_VIEWS]])
        self.view_selector.setMinimumWidth(120)
        self.view_selector.setMaximumWidth(155)
        self.view_selector.setAccessibleName("Column view")
        row.addWidget(self.view_selector)
        save_view = QPushButton("Columns"); save_view.setIcon(icon("columns"))
        self.columns_button = save_view
        save_view.setToolTip("Choose columns and save a custom view"); save_view.clicked.connect(self.save_column_view)
        row.addWidget(save_view)
        self.freeze_identity = QCheckBox("Freeze identity")
        self.freeze_identity.setToolTip("Freeze First Name, Last Name and Company Name")
        row.addWidget(self.freeze_identity)
        row.addStretch()
        self.undo_button = QPushButton(); self.undo_button.setIcon(icon("undo")); self.undo_button.setFixedSize(28, 28)
        self.undo_button.setAccessibleName("Undo")
        self.undo_button.setToolTip("Undo the last cell edit, paste or clear · Ctrl+Z")
        self.redo_button = QPushButton(); self.redo_button.setIcon(icon("redo")); self.redo_button.setFixedSize(28, 28)
        self.redo_button.setAccessibleName("Redo")
        self.redo_button.setToolTip("Redo the last undone edit · Ctrl+Y")
        self.undo_button.clicked.connect(self.undo_edit)
        self.redo_button.clicked.connect(self.redo_edit)
        row.addWidget(self.undo_button); row.addWidget(self.redo_button)
        toolbar.addWidget(self.view_controls)
        self.filter_hint = QLabel("Use the dropdown in any column heading to filter.")
        self.filter_hint.setWordWrap(True)
        self.filter_hint.setObjectName("metricHint")
        self._applying_view = False
        self._view_widths = self.controller.settings_service.get("lead_column_widths", {})
        self._view_orders = self.controller.settings_service.get("lead_column_orders", {})

    def build_table_pair(self, root):
        self.frozen_table = LeadTableView()
        self.frozen_table.setModel(self.proxy)
        self.frozen_table.setSelectionModel(self.table.selectionModel())
        for view in (self.table, self.frozen_table):
            view.selection_columns = lambda: [c for pane in (self.frozen_table, self.table)
                                               for c in (pane.horizontalHeader().logicalIndex(i) for i in range(self.model.columnCount())) if not pane.isColumnHidden(c)]
        self.frozen_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for table in (self.table, self.frozen_table):
            table.request_filter.connect(self.open_filter)
            table.request_find.connect(self.search.setFocus)
            table.request_save.connect(self.save_requested)
            table.request_validate.connect(self.validate_requested)
            table.request_undo.connect(self.undo_edit)
            table.request_redo.connect(self.redo_edit)
            table.data_mutated.connect(self.refresh)
            table.horizontalHeader().sectionResized.connect(self._column_resized)
            table.horizontalHeader().sectionMoved.connect(lambda logical,old,new,table=table:self._column_moved(table))
        self.frozen_table.verticalScrollBar().valueChanged.connect(self.table.verticalScrollBar().setValue)
        self.table.verticalScrollBar().valueChanged.connect(self.frozen_table.verticalScrollBar().setValue)
        self.frozen_table.horizontalHeader().sortIndicatorChanged.connect(self.table.horizontalHeader().setSortIndicator)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self.frozen_table.horizontalHeader().setSortIndicator)
        holder = QWidget(); layout = QHBoxLayout(holder); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(0)
        layout.addWidget(self.frozen_table); layout.addWidget(self.table, 1)
        root.addWidget(holder, 1)
        self.model.changed.connect(self.cells_changed)
        self.proxy.filters_changed.connect(self.update_filter_display)
        self.width_timer = QTimer(self); self.width_timer.setSingleShot(True); self.width_timer.setInterval(350)
        self.width_timer.timeout.connect(lambda: self.controller.settings_service.set("lead_column_widths", self._view_widths))
        self.view_selector.currentTextChanged.connect(self.change_column_view)
        self.freeze_identity.toggled.connect(self.apply_column_view)
        preferred = self.controller.settings_service.get("lead_last_view", "All columns")
        self.view_selector.setCurrentText(preferred if self.view_selector.findText(preferred) >= 0 else "All columns")
        self.change_column_view(self.view_selector.currentText())

    def change_column_view(self, name):
        freeze = self.custom_views.get(name, {}).get("freeze", name not in {"All columns", "Lead overview", "Workflow"})
        self.freeze_identity.blockSignals(True); self.freeze_identity.setChecked(freeze); self.freeze_identity.blockSignals(False)
        self.controller.settings_service.set("lead_last_view", name)
        self.apply_column_view()

    def apply_column_view(self, *_):
        if not hasattr(self, "frozen_table"):
            return
        self._applying_view = True
        try:
            name = self.view_selector.currentText()
            headers = self.controller.data_manager.headers
            columns = PRESET_VIEWS.get(name, self.custom_views.get(name, {}).get("columns"))
            visible = set(headers if columns is None else columns)
            if self.freeze_identity.isChecked():
                visible.update(IDENTITY_COLUMNS)
            pinned = visible & IDENTITY_COLUMNS if self.freeze_identity.isChecked() else set()
            permissions = getattr(self.controller, "field_permissions", {})
            visible = {field for field in visible if permissions.get(field) != "Hidden"}
            pinned &= visible
            order=self._view_orders.get(name,columns or headers)
            order=list(dict.fromkeys([f for f in order if f in headers]+headers))
            for pane in (self.table,self.frozen_table):
                head=pane.horizontalHeader()
                for visual,field in enumerate(order):head.moveSection(head.visualIndex(headers.index(field)),visual)
            for index, header in enumerate(headers):
                self.table.setColumnHidden(index, header not in visible or header in pinned)
                self.frozen_table.setColumnHidden(index, header not in pinned)
                overview_widths = {"Date": 124, "Campaign Name": 150, "Agent Name": 130,
                                   "Calling Agent Name": 148, "Phone Number": 148, "Dispo": 132, "Comment": 190}
                default_width = overview_widths.get(header, 170) if name == "Lead overview" else (130 if header in IDENTITY_COLUMNS else 180)
                width = int(self._view_widths.get(name, {}).get(header, default_width))
                self.table.setColumnWidth(index, width)
                self.frozen_table.setColumnWidth(index, width)
            self.frozen_table.setVisible(bool(pinned))
            self.table.verticalHeader().setVisible(not pinned)
            self._resize_frozen()
            self.update_filter_display()
        finally:
            self._applying_view = False

    def _resize_frozen(self):
        width = self.frozen_table.verticalHeader().width() + 4
        width += sum(self.frozen_table.columnWidth(i) for i in range(self.model.columnCount()) if not self.frozen_table.isColumnHidden(i))
        self.frozen_table.setFixedWidth(width)

    def _column_moved(self,table):
        if self._applying_view or not hasattr(self,'frozen_table'):return
        headers=self.controller.data_manager.headers; head=table.horizontalHeader()
        if head.count()!=len(headers) or any(not 0<=head.logicalIndex(i)<len(headers) for i in range(len(headers))):return
        order=[headers[head.logicalIndex(i)] for i in range(len(headers))]
        self._view_orders[self.view_selector.currentText()]=order
        self.controller.settings_service.set('lead_column_orders',self._view_orders)
        self._applying_view=True
        try:
            for other in (self.table,self.frozen_table):
                if other is table:continue
                target=other.horizontalHeader()
                for visual,field in enumerate(order):target.moveSection(target.visualIndex(headers.index(field)),visual)
        finally:self._applying_view=False

    def _column_resized(self, column, old, width):
        if self._applying_view or not hasattr(self, "frozen_table"):
            return
        self._applying_view = True
        try:
            self.table.setColumnWidth(column, width); self.frozen_table.setColumnWidth(column, width)
            name = self.controller.data_manager.headers[column]
            self._view_widths.setdefault(self.view_selector.currentText(), {})[name] = width
            self._resize_frozen()
            self.width_timer.start()
        finally:
            self._applying_view = False

    def save_column_view(self):
        headers=self.controller.data_manager.headers
        order=[headers[self.table.horizontalHeader().logicalIndex(i)] for i in range(len(headers))]
        selected = [name for name in order if not self.table.isColumnHidden(headers.index(name)) or not self.frozen_table.isColumnHidden(headers.index(name))]
        dialog = ColumnViewDialog(self, order, selected, self.freeze_identity.isChecked())
        current=self.view_selector.currentText()
        if current in self.custom_views:dialog.name.setText(current)
        if not dialog.exec(): return
        name = dialog.name.text().strip()
        if name in PRESET_VIEWS:
            QMessageBox.information(self, "Choose another name", "The built-in views are kept as defaults. Choose a name for your custom view.")
            return
        self.custom_views[name] = {"columns": dialog.selected_columns(), "freeze": dialog.freeze.isChecked()}
        self._view_orders[name]=dialog.selected_columns()+[f for f in order if f not in dialog.selected_columns()]
        self.controller.settings_service.set('lead_column_orders',self._view_orders)
        self.controller.settings_service.set("lead_column_views", self.custom_views)
        if self.view_selector.findText(name) < 0: self.view_selector.addItem(name)
        self.view_selector.setCurrentText(name)
        self.change_column_view(name)

    def update_filter_display(self):
        if not hasattr(self, "frozen_table"):
            return
        columns = set(self.proxy.column_filters) | set(self.proxy.column_conditions)
        for table in (self.table, self.frozen_table):
            table.horizontalHeader().filtered_columns = columns
            table.horizontalHeader().viewport().update()
        names = [self.controller.data_manager.headers[i] for i in sorted(columns) if i < self.model.columnCount()]
        text = "Column filters: " + ", ".join(names) if names else "Use the dropdown in any column heading to filter."
        self.filter_hint.setText(text)
        count = len(self.controller.data_manager.records)
        visible = len(self.visible_rows())
        self.count_label.setText(f"{visible:,} of {count:,} leads")
        if hasattr(self, "table_title"):
            self.table_title.setText(f"Leads ({count:,})")
        if hasattr(self, "empty_hint"):
            self.empty_hint.setText(("No leads match these filters. Use Clear filters to show all leads." if getattr(self,'excel_layout',False) else "No leads match these filters. Use Reset to show all leads.") if count else
                                    "No leads yet. Import a workbook, paste from Excel, or add results from Scraper.")
            self.empty_hint.setVisible(visible == 0)
        self.clear_filters_btn.setEnabled(not getattr(self, "_data_busy", False) and bool(columns or self.proxy.search_text or self.proxy.status_filter != "All"))

    def visible_rows(self):
        count = len(self.controller.data_manager.records)
        return [index for row in range(self.proxy.rowCount()) if (index := self.proxy.mapToSource(self.proxy.index(row, 0)).row()) < count]

    def selected_rows(self):
        count = len(self.controller.data_manager.records)
        return sorted({self.proxy.mapToSource(index).row() for index in self.table.selectionModel().selectedIndexes()
                       if self.proxy.mapToSource(index).row() < count})

    def undo_edit(self):
        index = self.proxy.mapToSource(self.table.currentIndex())
        if self.controller.undo_edit():
            self.refresh()
            self.restore_cell(index.row(), index.column())

    def redo_edit(self):
        index = self.proxy.mapToSource(self.table.currentIndex())
        if self.controller.redo_edit():
            self.refresh()
            self.restore_cell(index.row(), index.column())

    def cells_changed(self):
        # Keep the active editor and keyboard position during ordinary cell edits.
        self.update_filter_display()
        self.undo_button.setEnabled(bool(self.controller.history.undo_stack))
        self.redo_button.setEnabled(bool(self.controller.history.redo_stack))

    def restore_cell(self, row, column):
        if row < 0 or column < 0: return
        index = self.proxy.mapFromSource(self.model.index(row, column))
        if index.isValid():
            table = self.frozen_table if not self.frozen_table.isColumnHidden(column) else self.table
            table.setCurrentIndex(index)

    def focus_source_cell(self, row, field=None):
        headers = self.controller.data_manager.headers
        column = headers.index(field) if field in headers else headers.index("QA Status")
        table = self.frozen_table if not self.frozen_table.isColumnHidden(column) else self.table
        if table.isColumnHidden(column):
            table.setColumnHidden(column, False)
        index = self.proxy.mapFromSource(self.model.index(row, column))
        if not index.isValid():
            self.clear_filters()
            index = self.proxy.mapFromSource(self.model.index(row, column))
        table.setCurrentIndex(index); table.scrollTo(index); table.setFocus()
