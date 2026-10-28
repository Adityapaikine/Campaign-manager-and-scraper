from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,QAbstractItemView,
                              QLineEdit, QCheckBox, QListWidget, QListWidgetItem, QPushButton,
                              QTableWidget, QTableWidgetItem, QMessageBox)


class ColumnViewDialog(QDialog):
    def __init__(self, parent, headers, selected, freeze=False):
        super().__init__(parent)
        self.setWindowTitle("Save a column view")
        self.resize(430, 590)
        layout = QVBoxLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("View name, for example Calling team")
        layout.addWidget(self.name)
        self.freeze = QCheckBox("Keep Name and Company visible while scrolling")
        self.freeze.setChecked(freeze)
        layout.addWidget(self.freeze)
        self.search=QLineEdit(); self.search.setPlaceholderText('Find a column…'); self.search.setClearButtonEnabled(True); layout.addWidget(self.search)
        controls=QHBoxLayout(); all_columns=QPushButton('Select all'); clear=QPushButton('Clear selection'); controls.addWidget(all_columns); controls.addWidget(clear); layout.addLayout(controls)
        self.columns = QListWidget()
        self.columns.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        for header in headers:
            item = QListWidgetItem(header)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if header in selected else Qt.CheckState.Unchecked)
            self.columns.addItem(item)
        layout.addWidget(self.columns)
        self.selection_count=QLabel(); layout.addWidget(self.selection_count)
        tip=QLabel('Drag columns to arrange their order. Hidden columns keep their data.'); tip.setWordWrap(True); layout.addWidget(tip)
        self.search.textChanged.connect(lambda text:[self.columns.item(i).setHidden(text.casefold() not in self.columns.item(i).text().casefold()) for i in range(self.columns.count())])
        all_columns.clicked.connect(lambda:self.check_columns(True)); clear.clicked.connect(lambda:self.check_columns(False))
        self.columns.itemChanged.connect(self.update_count); self.update_count()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_columns(self):
        return [self.columns.item(i).text() for i in range(self.columns.count()) if self.columns.item(i).checkState() == Qt.CheckState.Checked]

    def check_columns(self,checked):
        for i in range(self.columns.count()):self.columns.item(i).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def update_count(self,*_):
        self.selection_count.setText(f'{len(self.selected_columns())} of {self.columns.count()} columns selected')

    def accept(self):
        if not self.name.text().strip() or not self.selected_columns():
            QMessageBox.information(self, "Name and columns", "Name this view and select at least one column.")
            return
        super().accept()


class ExportChoiceDialog(QDialog):
    def __init__(self, parent, counts, default="all", *, shared=False):
        super().__init__(parent)
        self.setWindowTitle("Choose leads to export")
        self.resize(440, 210)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Export permitted fields from this draft / loaded page:" if shared else "Export the complete worksheet columns for:"))
        self.scope = QComboBox()
        for key, label in (("all", "All leads"), ("qualified", "Qualified only"),
                           ("disqualified", "Disqualified only"), ("filtered", "Currently filtered rows")):
            self.scope.addItem(f"{label} — {counts[key]:,} leads", key)
        if 'selected' in counts:self.scope.addItem(f"Selected rows — {counts['selected']:,} leads",'selected')
        self.scope.setCurrentIndex(max(0, self.scope.findData(default)))
        layout.addWidget(self.scope)
        note = QLabel("Qualified means Valid or Valid - Email Generated after validation. Edited rows awaiting validation are excluded from Qualified and Disqualified exports.")
        note.setWordWrap(True); layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        self.scope.currentIndexChanged.connect(lambda: buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(counts[self.scope.currentData()] > 0))
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(counts[self.scope.currentData()] > 0)
        layout.addWidget(buttons)


class ReferenceManagerDialog(QDialog):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.requested_upload = None
        self.setWindowTitle("Reference lists for this workspace")
        self.resize(850, 560)
        layout = QVBoxLayout(self)
        self.kind = QComboBox(); self.kind.addItem("TAL", "tal"); self.kind.addItem("Suppression", "suppression")
        layout.addWidget(self.kind)
        self.info = QLabel(); self.info.setWordWrap(True); self.info.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.info)
        self.search = QLineEdit(); self.search.setPlaceholderText("Search saved reference rows…")
        layout.addWidget(self.search)
        self.table = QTableWidget(); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        upload = QPushButton("Upload / Replace")
        upload.clicked.connect(self.upload)
        self.remove = QPushButton("Remove uploaded list")
        self.remove.clicked.connect(self.remove_list)
        close = QPushButton("Close"); close.clicked.connect(self.accept)
        actions.addWidget(upload); actions.addWidget(self.remove); actions.addStretch(); actions.addWidget(close)
        layout.addLayout(actions)
        self.kind.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        kind = self.kind.currentData()
        data = getattr(self.controller, f"{kind}_data")
        validator = getattr(self.controller.validator, f"{kind}_validator")
        sources = []
        if data:
            sources = [data]
        elif validator is not None:
            sources = [validator.data] if hasattr(validator, "data") else [value.data for _, _, value in validator.validators]
        timestamp = self.controller.reference_store.uploaded_at(kind)
        self.remove.setEnabled(bool(timestamp))
        error = self.controller.reference_errors.get(kind)
        self.info.setText(error or (f"{', '.join(source.source_name for source in sources)}\n"
                          f"{sum(source.count for source in sources):,} saved rows · "
                          + (f"Uploaded {timestamp}" if data else "Campaign reference") if sources else "No list loaded for this workspace."))
        headers = ["Source", "Reference row"]
        for source in sources:
            for record in source.records[:1]:
                headers.extend(key for key in record if key not in headers)
        rows = []
        needle = self.search.text().strip().casefold()
        for source in sources:
            for index, record in enumerate(source.records, 1):
                if not needle or needle in " ".join(record.values()).casefold():
                    rows.append({"Source": source.source_name, "Reference row": str(index), **record})
                    if len(rows) == 500: break
            if len(rows) == 500: break
        self.table.setColumnCount(len(headers)); self.table.setHorizontalHeaderLabels(headers); self.table.setRowCount(len(rows))
        for r, record in enumerate(rows):
            for c, header in enumerate(headers):
                self.table.setItem(r, c, QTableWidgetItem(str(record.get(header, ""))))
        self.table.resizeColumnsToContents()
        self.table.setToolTip("Preview shows up to 500 matching rows. Search to find other entries. All saved rows are used during validation.")

    def upload(self):
        self.requested_upload = self.kind.currentData()
        self.accept()

    def remove_list(self):
        kind = self.kind.currentData()
        answer = QMessageBox.question(self, "Remove reference list", f"Remove this workspace's uploaded {kind.upper()} list? Campaign references, if present, will become active. Leads will need validation again.")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.controller.remove_reference(kind)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Reference list", str(exc))
