"""Choose a populated worksheet and inspect its mapping before importing."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHeaderView, QLabel,
    QMessageBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from app.excel.importer import detect_mapping
from app.core.reference_lists import detect_reference_mapping


class LeadImportDialog(QDialog):
    def __init__(self, parent, tables, headers, *, reference_kind=None):
        super().__init__(parent)
        self.reference_kind = reference_kind
        self.setWindowTitle(f"Load {reference_kind.upper()} — worksheet and columns" if reference_kind else "Import leads — worksheet and columns")
        self.resize(880, 650)
        self.tables = tables
        self.headers = list(headers)
        self._boxes = {}
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.addWidget(QLabel("Worksheet / source"))
        self.sheet_selector = QComboBox()
        self.sheet_selector.setAccessibleName("Worksheet to import")
        for name, table in tables.items():
            self.sheet_selector.addItem(f"{name} — {len(table):,} rows", name)
        root.addWidget(self.sheet_selector)
        self.summary = QLabel(); self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        self.preview = QTableWidget(0, 3)
        self.preview.setHorizontalHeaderLabels(["Source column", "Example value", "Import as"])
        self.preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.preview.verticalHeader().hide()
        self.preview.verticalHeader().setDefaultSectionSize(42)
        self.preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.preview, 1)
        note = QLabel("This list is saved in the workspace for future validation. Upload a new list to replace it. Choose (Ignore) to skip a column." if reference_kind else "Check the examples and column mapping. New fields are added only after a successful import. Choose (Ignore) to skip a column.")
        note.setWordWrap(True); root.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.import_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.import_button.setText("Import rows")
        self.import_button.setObjectName("primaryButton")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.sheet_selector.currentIndexChanged.connect(self._sheet_changed)
        first_populated = next((index for index, table in enumerate(tables.values()) if len(table)), 0)
        self.sheet_selector.setCurrentIndex(first_populated)
        self._sheet_changed()

    def selected_table(self):
        return self.tables[self.sheet_selector.currentData()]

    def _sheet_changed(self, *_):
        table = self.selected_table()
        self.summary.setText(
            f"{len(table):,} data rows found. Only this worksheet will be imported."
            if len(table) else "This worksheet has no data rows. Select a populated worksheet above.")
        self.import_button.setEnabled(bool(len(table)))
        self.import_button.setText(f"Import {len(table):,} rows")
        suggested = (detect_reference_mapping(list(table.columns), self.reference_kind)
                     if self.reference_kind else detect_mapping(list(table.columns)))
        targets = list(self.headers)
        by_name = {name.casefold(): name for name in targets}
        for source in table.columns:
            if self.reference_kind:
                continue
            if source in suggested:
                continue
            name = str(source).strip()
            if not name or name.startswith(("=", "+", "-", "@", "Unnamed:")):
                continue
            if name.casefold() not in by_name:
                targets.append(name); by_name[name.casefold()] = name
            suggested[source] = by_name[name.casefold()]
        self.preview.clearContents(); self.preview.setRowCount(len(table.columns)); self._boxes = {}
        for index, source in enumerate(table.columns):
            sample = next((str(value) for value in table[source] if str(value).strip()), "")
            source_item = QTableWidgetItem(str(source)); source_item.setToolTip(str(source))
            sample_item = QTableWidgetItem(sample[:120]); sample_item.setToolTip(sample)
            self.preview.setItem(index, 0, source_item); self.preview.setItem(index, 1, sample_item)
            box = QComboBox(); box.addItems(["(Ignore)"] + targets)
            box.setCurrentText(suggested.get(source, "(Ignore)"))
            self._boxes[source] = box; self.preview.setCellWidget(index, 2, box)

    def mapping(self):
        return {source: box.currentText() for source, box in self._boxes.items() if box.currentText() != "(Ignore)"}

    def accept(self):
        if self.selected_table().empty:
            return
        mapping = self.mapping()
        if not mapping:
            QMessageBox.warning(self, "Choose columns", "Map at least one column before importing.")
            return
        targets = [name.casefold() for name in mapping.values()]
        if len(targets) != len(set(targets)):
            QMessageBox.warning(self, "Duplicate mapping", "Two source columns map to the same field. Choose a different field or (Ignore).")
            return
        super().accept()
