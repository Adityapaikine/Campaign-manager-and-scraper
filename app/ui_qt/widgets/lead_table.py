from __future__ import annotations

import csv
import io
from typing import Iterable

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt, Signal, QEventLoop, QRectF, QItemSelection, QItemSelectionModel
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QPainter, QPen
from PySide6.QtWidgets import QApplication, QHeaderView, QTableView, QProgressDialog, QMessageBox, QStyledItemDelegate, QStyleOptionViewItem, QStyle

from app.constants import MISSING_VALUE, STANDARD_HEADERS
from app.core.column_filter import display_value, value_key, matches_condition, number, date_value
from app.ui_qt.widgets.filter_header import FilterHeader
from app.utils.text_utils import clean_missing


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
        self.show_formulas = False

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
            if role == Qt.ItemDataRole.EditRole:
                value = self.controller.data_manager.raw_value(row, header)
            elif self.show_formulas and (row, header) in self.controller.data_manager.formulas:
                value = self.controller.data_manager.formulas[row, header]
            else:
                value = str(record.get(header, MISSING_VALUE))
            return "" if value == MISSING_VALUE else value

        if role == Qt.ItemDataRole.ToolTipRole and (row, header) in self.controller.data_manager.formulas:
            expression = self.controller.data_manager.formulas[row, header]
            error = self.controller.data_manager.formula_errors.get((row, header), "")
            return expression + ("\n" + error if error else "\nF2 to edit · Ctrl+Shift+F for formula bar")

        if role == Qt.ItemDataRole.BackgroundRole and record is not None:
            if (row, header) in self.controller.data_manager.formula_errors:
                return QColor("#FFE7E9")
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
            if (row, header) in self.controller.data_manager.formula_errors:
                return QColor("#B02337")
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
        if role == Qt.ItemDataRole.ToolTipRole and orientation == Qt.Orientation.Horizontal:
            return f"Column {column_letters(section)} · {self.controller.data_manager.headers[section]}"
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            name = self.controller.data_manager.headers[section]
            return "Disposition" if name == "Dispo" else name
        return str(section + 1)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
            | Qt.ItemFlag.ItemIsDragEnabled
        )
        if self.controller.data_manager.headers[index.column()] in {"QA Status", "Primary Reason"}:
            flags &= ~Qt.ItemFlag.ItemIsEditable
        if hasattr(self.controller, "can_edit_cell") and not self.controller.can_edit_cell(index.row(), self.controller.data_manager.headers[index.column()]):
            flags &= ~Qt.ItemFlag.ItemIsEditable
        return flags

    def _ensure_row(self, row: int) -> None:
        while len(self.controller.data_manager.records) <= row:
            self.controller.data_manager.append_record({}, source_name="Manual Entry")

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        row, col = index.row(), index.column()
        header = self.controller.data_manager.headers[col]
        if header in {"QA Status", "Primary Reason"}:
            return False
        current = self._record(row)
        if clean_missing(value) == self.controller.data_manager.raw_value(row, header):
            return False
        old_count = self.rowCount()
        new_count = max(self.blank_rows, max(len(self.controller.data_manager.records), row + 1) + 20)
        if new_count > old_count:
            self.beginInsertRows(QModelIndex(), old_count, new_count - 1)
        changed = self.controller.edit_cells({(row, self.controller.data_manager.headers[col]): value}, "Edit cell")
        if new_count > old_count:
            self.endInsertRows()
        if changed:
            self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount()-1, self.columnCount()-1))
            self.changed.emit()
        return changed

    def refresh(self):
        self.beginResetModel()
        self.endResetModel()

    def clear_cells(self, indexes: Iterable[QModelIndex]):
        edits = {(idx.row(), self.controller.data_manager.headers[idx.column()]): MISSING_VALUE
                 for idx in indexes if idx.isValid() and idx.row() < len(self.controller.data_manager.records)}
        self.controller.edit_cells(edits, "Clear cells")
        self.refresh()
        self.changed.emit()


class LeadFilterProxyModel(QSortFilterProxyModel):
    filters_changed = Signal()
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.search_text = ""
        self.status_filter = "All"
        self.column_filters: dict[int, set[str]] = {}
        self.column_conditions = {}
        self.setDynamicSortFilter(True)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_search(self, text: str):
        self.search_text = str(text or "").strip().casefold()
        self.refresh_filter()
        self.filters_changed.emit()

    def set_status(self, status: str):
        self.status_filter = status or "All"
        self.refresh_filter()
        self.filters_changed.emit()

    def set_column_filter(self, column: int, allowed: set[str] | None):
        if allowed is None:
            self.column_filters.pop(column, None)
        else:
            self.column_filters[column] = {value_key(value) for value in allowed}
        self.refresh_filter()
        self.filters_changed.emit()

    def set_condition(self, column, rule):
        if rule:
            self.column_conditions[column] = rule
        else:
            self.column_conditions.pop(column, None)
        self.refresh_filter()
        self.filters_changed.emit()

    def clear_filters(self):
        self.search_text = ""
        self.status_filter = "All"
        self.column_filters.clear()
        self.column_conditions.clear()
        self.refresh_filter()
        self.filters_changed.emit()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex):
        return self.accepts_row(source_row)

    def refresh_filter(self):
        # Qt 6.11's supported replacement for invalidateFilter().
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def accepts_row(self, source_row, *, excluding_column=None):
        record_count = len(self.controller.data_manager.records)
        has_filters = bool(self.search_text or self.status_filter != "All" or self.column_filters or self.column_conditions)
        if source_row >= record_count:
            return not has_filters

        record = self.controller.data_manager.records[source_row]
        if self.status_filter == "Disqualified":
            if record.get("QA Status") != "Disqualified":
                return False
        elif self.status_filter != "All" and self.controller.row_states.get(source_row, "Needs validation") != self.status_filter:
            return False
        for col, allowed in self.column_filters.items():
            if col == excluding_column or not 0 <= col < len(self.controller.data_manager.headers):
                continue
            value = str(record.get(self.controller.data_manager.headers[col], MISSING_VALUE))
            if value_key(value) not in allowed:
                return False
        for col, rule in self.column_conditions.items():
            if col != excluding_column and 0 <= col < len(self.controller.data_manager.headers) and not matches_condition(record.get(self.controller.data_manager.headers[col]), rule):
                return False
        if self.search_text:
            haystack = " ".join(str(record.get(h, "")) for h in self.controller.data_manager.headers).casefold()
            if self.search_text not in haystack:
                return False
        return True

    def lessThan(self, left, right):
        count = len(self.controller.data_manager.records)
        if (left.row() >= count) != (right.row() >= count):
            return (left.row() < count) if self.sortOrder() == Qt.SortOrder.AscendingOrder else (left.row() >= count)
        header = self.controller.data_manager.headers[left.column()]
        records = self.controller.data_manager.records
        # Show-formulas mode changes presentation, not numeric/text sort order.
        a = display_value(records[left.row()].get(header)) if left.row() < count else ""
        b = display_value(records[right.row()].get(header)) if right.row() < count else ""
        converter = date_value if "date" in header.casefold() else number
        first, second = converter(a), converter(b)
        if first is not None and second is not None:
            return first < second
        return a.casefold() < b.casefold()

    def column_values(self, column):
        values = {}
        header = self.controller.data_manager.headers[column]
        for row, record in enumerate(self.controller.data_manager.records):
            if self.accepts_row(row, excluding_column=column):
                value = display_value(record.get(header))
                values.setdefault(value_key(value), value)
        return sorted(values.values(), key=lambda value: (not bool(value), value.casefold()))


class LeadCellDelegate(QStyledItemDelegate):
    """Display existing status values as badges without altering cell data."""
    def createEditor(self, parent, option, index):
        from app.ui_qt.widgets.formula_editor import FormulaLineEdit
        editor = FormulaLineEdit(parent)
        table = self.parent()
        if getattr(table, "configure_formula_editor", None):
            table.configure_formula_editor(editor, index)
        return editor

    def paint(self, painter, option, index):
        self._paint_cell(painter, option, index)
        region = getattr(self.parent(), "reference_region", None)
        if region:
            model = index.model()
            cell = model.mapToSource(index) if isinstance(model, QSortFilterProxyModel) else index
            first, last = region
            if first[0] <= cell.row() <= last[0] and first[1] <= cell.column() <= last[1]:
                painter.save(); painter.setPen(QPen(QColor("#0868F9"), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawRect(option.rect.adjusted(1, 1, -2, -2)); painter.restore()

    def _paint_cell(self, painter, option, index):
        field = index.model().headerData(index.column(), Qt.Orientation.Horizontal)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        if field not in {"Disposition", "QA Status"} or not text:
            return super().paint(painter, option, index)
        opt = QStyleOptionViewItem(option); self.initStyleOption(opt, index)
        opt.text = ""
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, option.widget)
        value = str(text).casefold()
        if value in {"connected", "valid", "valid - email generated", "qualified"}:
            background, foreground = "#D5F8EC", "#07694D"
        elif value in {"follow up", "follow-up", "warning", "manual review", "needs validation"}:
            background, foreground = "#FFF0BC", "#805300"
        elif value in {"no answer", "invalid number", "invalid", "disqualified", "suppressed", "outside tal"}:
            background, foreground = "#FFE0E3", "#B02337"
        else:
            background, foreground = "#E7EDF6", "#425676"
        width = min(option.rect.width() - 14, option.fontMetrics.horizontalAdvance(str(text)) + 22)
        rect = QRectF(option.rect.left() + 7, option.rect.center().y() - 12, width, 24)
        painter.save(); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor(background)); painter.drawRoundedRect(rect, 12, 12)
        painter.setPen(QColor(foreground))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, option.fontMetrics.elidedText(str(text), Qt.TextElideMode.ElideRight, max(1, int(width) - 16)))
        painter.restore()


class LeadTableView(QTableView):
    request_filter = Signal(int)
    request_find = Signal()
    request_save = Signal()
    request_validate = Signal()
    request_undo = Signal()
    request_redo = Signal()
    data_mutated = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("leadGrid")
        self.setItemDelegate(LeadCellDelegate(self))
        self.setHorizontalHeader(FilterHeader(self))
        self.horizontalHeader().filter_requested.connect(self.request_filter)
        self.horizontalHeader().column_selected.connect(self.selectColumn)
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
        self.verticalHeader().setDefaultSectionSize(32)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.horizontalHeader().setSectionsMovable(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setDefaultSectionSize(155)
        self.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._header_menu_request)
        self.setCornerButtonEnabled(True)
        self.setTabKeyNavigation(True)
        self.setVerticalScrollMode(QTableView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        QShortcut(QKeySequence("Ctrl+F"), self, activated=self.request_find)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.request_save)
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.request_validate)
        QShortcut(QKeySequence("Alt+Down"), self, activated=lambda: self.request_filter.emit(self.currentIndex().column()) if self.currentIndex().isValid() else None)
        for shortcut in self.findChildren(QShortcut):
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def _header_menu_request(self, pos):
        col = self.horizontalHeader().logicalIndexAt(pos)
        if col >= 0:
            self.request_filter.emit(col)

    def keyPressEvent(self, event):
        model = self.model()
        source = model.sourceModel() if isinstance(model, QSortFilterProxyModel) else model
        if event.key() == Qt.Key.Key_Space and self.state() != QTableView.State.EditingState:
            modifiers = event.modifiers()
            if modifiers in (Qt.KeyboardModifier.ShiftModifier, Qt.KeyboardModifier.ControlModifier) and self.currentIndex().isValid():
                current = self.currentIndex(); selected = self.selectedIndexes()
                selection = QItemSelection()
                if modifiers == Qt.KeyboardModifier.ShiftModifier:
                    rows = sorted({i.row() for i in selected} or {current.row()})
                    columns = self.selection_columns() if hasattr(self, "selection_columns") else [c for c in range(model.columnCount()) if not self.isColumnHidden(c)]
                    for c in columns:
                        selection.select(model.index(rows[0], c), model.index(rows[-1], c))
                else:
                    columns = sorted({i.column() for i in selected} or {current.column()})
                    for c in columns:
                        selection.select(model.index(0, c), model.index(model.rowCount()-1, c))
                self.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
                event.accept(); return
        if event.matches(QKeySequence.StandardKey.Undo):
            self.request_undo.emit()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.request_redo.emit()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selection()
            return
        if event.matches(QKeySequence.StandardKey.Cut):
            if hasattr(self,'authorized_copy'):
                self.authorized_copy(self,True); return
            self.copy_selection()
            if isinstance(source, LeadTableModel):
                src_indexes = [model.mapToSource(i) if isinstance(model, QSortFilterProxyModel) else i for i in self.selectedIndexes()]
                anchor = (src_indexes[0].row(), src_indexes[0].column()) if src_indexes else None
                source.clear_cells(src_indexes)
                self._restore_source_cell(source, anchor)
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_clipboard()
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and not self.state() == QTableView.State.EditingState:
            if isinstance(source, LeadTableModel):
                src_indexes = [model.mapToSource(i) if isinstance(model, QSortFilterProxyModel) else i for i in self.selectedIndexes()]
                anchor = (src_indexes[0].row(), src_indexes[0].column()) if src_indexes else None
                source.clear_cells(src_indexes)
                self._restore_source_cell(source, anchor)
            return
        super().keyPressEvent(event)

    def _restore_source_cell(self, source, anchor):
        if anchor is None: return
        index = source.index(*anchor)
        proxy = self.model()
        visible = proxy.mapFromSource(index) if isinstance(proxy, QSortFilterProxyModel) else index
        if visible.isValid():
            self.setCurrentIndex(visible)

    def copy_selection(self):
        if hasattr(self,'authorized_copy'):
            self.authorized_copy(self,False); return
        indexes = sorted(self.selectedIndexes(), key=lambda i: (i.row(), i.column()))
        if not indexes:
            return
        rows = range(indexes[0].row(), indexes[-1].row() + 1)
        available = self.selection_columns() if hasattr(self, "selection_columns") else [c for c in range(self.model().columnCount()) if not self.isColumnHidden(c)]
        cols = [column for column in available if min(i.column() for i in indexes) <= column <= max(i.column() for i in indexes)]
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
        visual_columns=[self.horizontalHeader().logicalIndex(i) for i in range(source.columnCount())]
        target_columns = [column for column in visual_columns[visual_columns.index(start_col):] if not self.isColumnHidden(column)]
        if max(map(len, reader)) > len(target_columns):
            QMessageBox.information(self, "Add columns before pasting",
                "This selection is wider than the visible columns. Choose All columns and unfreeze identity columns, or use Add Columns, then paste again. No cells were changed.")
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
            headers = source.controller.data_manager.headers
            edits = {}
            for number, (target, row_values) in enumerate(zip(targets, reader), 1):
                for offset, value in enumerate(row_values):
                    col = target_columns[offset]
                    edits[(target, headers[col])] = value
                if number % 500 == 0:
                    progress.setValue(number)
            source.controller.edit_cells(edits, "Paste from Excel")
        finally:
            source.endResetModel()
            progress.setValue(len(reader))
            progress.close()
        source.changed.emit()
        self.data_mutated.emit()
        mapped = source.index(targets[0], start_col)
        visible = proxy.mapFromSource(mapped) if isinstance(proxy, QSortFilterProxyModel) else mapped
        if visible.isValid():
            self.setCurrentIndex(visible)
