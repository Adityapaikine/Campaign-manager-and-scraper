from __future__ import annotations

import csv
import io
from typing import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal, QEventLoop
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QHeaderView, QTableView, QProgressDialog, QMessageBox

from app.constants import MISSING_VALUE, STANDARD_HEADERS


def column_letters(index: int) -> str:
    index += 1
    out = ""
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


class LeadTableModel(QAbstractTableModel):
    changed = Signal()

    def __init__(self, controller, *, blank_rows: int = 40, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.blank_rows = max(20, int(blank_rows))

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return max(self.blank_rows, len(self.controller.data_manager.records) + 20)

    def columnCount(self, parent=QModelIndex()):
        return len(self.controller.data_manager.headers)

    def _record(self, row: int):
        if 0 <= row < len(self.controller.data_manager.records):
            return self.controller.data_manager.records[row]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        record = self._record(row)
        header = self.controller.data_manager.headers[col]

        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if record is None:
                return ""
            value = str(record.get(header, MISSING_VALUE))
            return "" if value == MISSING_VALUE else value

        if role == Qt.ItemDataRole.BackgroundRole and record is not None:
            status = self.controller.row_states.get(row, "")
            if status == "Outside TAL":
                return QColor(self.controller.settings.outside_tal_color)
            if status == "Suppressed":
                return QColor(self.controller.settings.suppression_match_color)
            if status == "Invalid":
                return QColor("#FDE2E1")
            if status == "Duplicate":
                return QColor("#FFF2CC")
            if status == "Manual Review":
                return QColor("#EADCF8")
            if status.startswith("Valid"):
                return QColor("#E2F0D9")

        if role == Qt.ItemDataRole.ForegroundRole and record is not None:
            status = self.controller.row_states.get(row, "")
            if status in {"Outside TAL", "Suppressed", "Invalid", "Duplicate", "Manual Review"} or status.startswith("Valid"):
                background = self.data(index, Qt.ItemDataRole.BackgroundRole)
                return QColor("#142235" if background.lightnessF() > 0.5 else "#FFFFFF")

        if role == Qt.ItemDataRole.ToolTipRole and record is not None:
            email = getattr(self.controller, "email_results", {}).get(row)
            if email and header in {"Business Email ID", "Email Status"}:
                return (f"{email.status}\n{email.reason}\n"
                        + (f"Candidate: {email.candidate}\nConfidence: {email.confidence}%\n" if email.candidate != MISSING_VALUE else "")
                        + "\n".join(email.evidence_sources))
            reasons = self.controller.validation_reasons.get(row, [])
            if reasons:
                return "\n".join(reasons)
        return None

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return f"{column_letters(section)}  {self.controller.data_manager.headers[section]}"
        return str(section + 1)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
            | Qt.ItemFlag.ItemIsDragEnabled
        )

    def _ensure_row(self, row: int) -> None:
        while len(self.controller.data_manager.records) <= row:
            self.controller.data_manager.append_record({}, source_name="Manual Entry")

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        row, col = index.row(), index.column()
        old_count = self.rowCount()
        new_count = max(self.blank_rows, max(len(self.controller.data_manager.records), row + 1) + 20)
        if new_count > old_count:
            self.beginInsertRows(QModelIndex(), old_count, new_count - 1)
        self._ensure_row(row)
        if new_count > old_count:
            self.endInsertRows()
        text = str(value or "").strip()
        self.controller.data_manager.update_cell(row, self.controller.data_manager.headers[col], text or MISSING_VALUE)
        self.controller.clear_derived_state()
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
        self.changed.emit()
        return True

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()

    def clear_cells(self, indexes: Iterable[QModelIndex]):
        for idx in indexes:
            if idx.isValid() and idx.row() < len(self.controller.data_manager.records):
                self.controller.data_manager.update_cell(idx.row(), self.controller.data_manager.headers[idx.column()], MISSING_VALUE)
        self.controller.clear_derived_state()
        self.refresh()
        self.changed.emit()


class LeadFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.search_text = ""
        self.status_filter = "All"
        self.column_filters: dict[int, set[str]] = {}
        self.setDynamicSortFilter(True)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_search(self, text: str):
        self.search_text = str(text or "").strip().casefold()
        self.invalidateFilter()

    def set_status(self, status: str):
        self.status_filter = status or "All"
        self.invalidateFilter()

    def set_column_filter(self, column: int, allowed: set[str] | None):
        if not allowed:
            self.column_filters.pop(column, None)
        else:
            self.column_filters[column] = set(allowed)
        self.invalidateFilter()

    def clear_filters(self):
        self.search_text = ""
        self.status_filter = "All"
        self.column_filters.clear()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex):
        record_count = len(self.controller.data_manager.records)
        has_filters = bool(self.search_text or self.status_filter != "All" or self.column_filters)
        if source_row >= record_count:
            return not has_filters

        record = self.controller.data_manager.records[source_row]
        if self.status_filter == "Disqualified":
            if record.get("QA Status") != "Disqualified":
                return False
        elif self.status_filter != "All" and self.controller.row_states.get(source_row, "") != self.status_filter:
            return False
        for col, allowed in self.column_filters.items():
            value = str(record.get(self.controller.data_manager.headers[col], MISSING_VALUE))
            display = "(Blanks)" if value in {"", MISSING_VALUE} else value
            if display not in allowed:
                return False
        if self.search_text:
            haystack = " ".join(str(record.get(h, "")) for h in self.controller.data_manager.headers).casefold()
            if self.search_text not in haystack:
                return False
        return True


class LeadTableView(QTableView):
    request_filter = Signal(int)
    request_find = Signal()
    request_save = Signal()
    request_validate = Signal()
    data_mutated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        self.setEditTriggers(
            QTableView.EditTrigger.DoubleClicked
            | QTableView.EditTrigger.EditKeyPressed
            | QTableView.EditTrigger.AnyKeyPressed
            | QTableView.EditTrigger.SelectedClicked
        )
        self.setSortingEnabled(True)
        self.setWordWrap(False)
        self.verticalHeader().setDefaultSectionSize(34)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.horizontalHeader().setSectionsMovable(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setDefaultSectionSize(155)
        self.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._header_menu_request)
        self.setCornerButtonEnabled(True)
        self.setTabKeyNavigation(True)

        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.request_find)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.request_save)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.request_validate)

    def _header_menu_request(self, pos):
        col = self.horizontalHeader().logicalIndexAt(pos)
        if col >= 0:
            self.request_filter.emit(col)

    def keyPressEvent(self, event):
        model = self.model()
        source = model.sourceModel() if isinstance(model, QSortFilterProxyModel) else model
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            return
        if event.matches(QKeySequence.StandardKey.Cut):
            self.copy_selection()
            if isinstance(source, LeadTableModel):
                src_indexes = [model.mapToSource(i) if isinstance(model, QSortFilterProxyModel) else i for i in self.selectedIndexes()]
                source.clear_cells(src_indexes)
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_clipboard()
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and not self.state() == QTableView.State.EditingState:
            if isinstance(source, LeadTableModel):
                src_indexes = [model.mapToSource(i) if isinstance(model, QSortFilterProxyModel) else i for i in self.selectedIndexes()]
                source.clear_cells(src_indexes)
            return
        super().keyPressEvent(event)

    def copy_selection(self):
        indexes = sorted(self.selectedIndexes(), key=lambda i: (i.row(), i.column()))
        if not indexes:
            return
        rows = range(indexes[0].row(), indexes[-1].row() + 1)
        cols = range(indexes[0].column(), indexes[-1].column() + 1)
        selected = {(i.row(), i.column()) for i in indexes}
        output = io.StringIO()
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        for r in rows:
            writer.writerow([self.model().index(r, c).data() if (r, c) in selected else "" for c in cols])
        QApplication.clipboard().setText(output.getvalue().rstrip("\n"))

    def paste_clipboard(self):
        text = QApplication.clipboard().text()
        if not text:
            return
        current = self.currentIndex()
        if not current.isValid():
            current = self.model().index(0, 0)
        reader = list(csv.reader(io.StringIO(text), delimiter="\t"))
        proxy = self.model()
        source = proxy.sourceModel() if isinstance(proxy, QSortFilterProxyModel) else proxy
        if not isinstance(source, LeadTableModel):
            return
        if not reader:
            return
        start_row = current.row() if current.isValid() else 0
        start_col = current.column() if current.isValid() else 0
        if max(map(len, reader)) + start_col > source.columnCount():
            QMessageBox.information(self, "Add columns before pasting",
                "This selection is wider than the worksheet. Use Add Columns, then paste again. No cells were changed.")
            return
        progress = QProgressDialog("Pasting worksheet rows…", "", 0, len(reader), self)
        progress.setWindowTitle("Paste from Excel")
        progress.setCancelButton(None)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0 if len(reader) >= 500 else 400)
        progress.setValue(0)
        # Resolve visible rows before editing: sorting/filtering can change after
        # each cell, and proxy.index() cannot address rows that do not exist yet.
        targets = []
        next_row = len(source.controller.data_manager.records)
        for offset in range(len(reader)):
            visible = proxy.index(start_row + offset, start_col)
            if visible.isValid():
                mapped = proxy.mapToSource(visible) if isinstance(proxy, QSortFilterProxyModel) else visible
                target = mapped.row()
                next_row = max(next_row, target + 1)
            else:
                target = next_row
                next_row += 1
            targets.append(target)
        source.beginResetModel()
        try:
            source._ensure_row(max(targets))
            headers = source.controller.data_manager.headers
            for number, (target, row_values) in enumerate(zip(targets, reader), 1):
                for offset, value in enumerate(row_values):
                    col = start_col + offset
                    if col < len(headers):
                        source.controller.data_manager.update_cell(target, headers[col], value)
                if number % 500 == 0:
                    progress.setValue(number)
            source.controller.clear_derived_state()
        finally:
            source.endResetModel()
            progress.setValue(len(reader))
            progress.close()
        source.changed.emit()
        self.data_mutated.emit()
