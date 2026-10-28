"""Compact spreadsheet controls for the native lead worksheet."""
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QCompleter, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                              QMenu, QMessageBox, QPushButton, QToolButton, QWidget)

from app.constants import MISSING_VALUE
from app.core.formulas import function_catalog, translate_formula, FormulaError
from app.ui_qt.dialogs.formula_dialog import FormulaDialog, DeleteColumnsDialog
from app.ui_qt.widgets.lead_table import column_letters
from app.ui_qt.widgets.icons import icon
from app.ui_qt.widgets.formula_editor import FormulaLineEdit


class FormulaTools:
    def build_formula_bar(self, layout):
        self.formula_bar = QWidget(); self.formula_bar.setObjectName("formulaBar")
        row = QHBoxLayout(self.formula_bar); row.setContentsMargins(8, 4, 8, 5); row.setSpacing(6)
        self.formula_address = QLabel("—"); self.formula_address.setMinimumWidth(42)
        self.formula_address.setAccessibleName("Selected cell address"); row.addWidget(self.formula_address)
        self.formula_button = QToolButton(); self.formula_button.setText("ƒx Formulas")
        self.formula_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.formula_button)
        menu.addAction("Insert function…    Shift+F3", self.insert_function)
        menu.addAction("Insert column reference…", self.insert_column_reference)
        common = menu.addMenu("Quick functions")
        for name in ("SUM", "AVERAGE", "COUNT", "IF", "IFERROR", "XLOOKUP", "CONCAT", "TRIM", "LOWER", "TEXT", "TODAY"):
            common.addAction(name, lambda name=name: self.insert_named_function(name))
        for category in sorted(set(function_catalog().values())):
            menu.addAction(category + "…", lambda category=category: self.insert_function(category))
        menu.addSeparator()
        menu.addAction("Fill down    Ctrl+D", self.fill_down)
        menu.addAction("Fill right    Ctrl+R", self.fill_right)
        menu.addAction("Replace selected formulas with values", self.formulas_to_values)
        self.show_formulas_action = menu.addAction("Show formulas    Ctrl+`")
        self.show_formulas_action.setCheckable(True); self.show_formulas_action.toggled.connect(self.toggle_formulas)
        menu.addAction("Recalculate    F9", self.calculate_now)
        menu.addSeparator()
        menu.addAction("Add columns…", self.add_columns)
        menu.addAction("Delete custom columns…", self.delete_columns)
        menu.addAction("Formula help & shortcuts…", self.formula_help)
        self.formula_button.setMenu(menu); row.addWidget(self.formula_button)
        self.formula_entry = FormulaLineEdit()
        self.formula_entry.resolve_reference = self.resolve_formula_reference
        self.formula_entry.highlight_reference = self.highlight_formula_reference
        self.formula_entry.setAccessibleName("Formula bar")
        self.formula_entry.setPlaceholderText('Value or formula · type = then use arrow keys to pick cells')
        self.formula_entry.setToolTip("Arrows pick cells after = or an operator · F2 toggles text navigation · Enter applies · Esc cancels · F4 locks references")
        self.formula_entry.returnPressed.connect(self.apply_formula_entry)
        self.formula_entry.installEventFilter(self)
        completer = QCompleter(["=" + name + "(" for name in function_catalog()], self.formula_entry)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.formula_entry.setCompleter(completer)
        row.addWidget(self.formula_entry, 1)
        apply = QPushButton(); apply.setIcon(icon("check", "#0868F9")); apply.setFixedWidth(30); apply.setAccessibleName("Apply formula")
        apply.setToolTip("Apply to selected cell · Enter"); apply.clicked.connect(self.apply_formula_entry); row.addWidget(apply)
        layout.addWidget(self.formula_bar)
        self._formula_target = None
        for sequence, callback in (("Ctrl+Shift+F", self.focus_formula), ("Shift+F3", self.insert_function),
                                   ("F9", self.calculate_now), ("Ctrl+`", self.show_formulas_action.trigger),
                                   ("Ctrl+D", self.fill_down), ("Ctrl+R", self.fill_right)):
            shortcut = QShortcut(QKeySequence(sequence), self, activated=callback)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def connect_formula_bar(self):
        for table in (self.table, self.frozen_table):
            table.configure_formula_editor = self.configure_formula_editor
            table.itemDelegate().closeEditor.connect(lambda *_: self.sync_formula_bar())
        self.table.selectionModel().currentChanged.connect(self.sync_formula_bar)
        self.model.changed.connect(self.sync_formula_bar)
        self.sync_formula_bar()

    def sync_formula_bar(self, *_):
        if not hasattr(self, "formula_entry"):
            return
        index = self.proxy.mapToSource(self.table.currentIndex())
        self._formula_target = (index.row(), index.column()) if index.isValid() else None
        self.formula_entry.origin = self._formula_target
        self.formula_entry.text_navigation = False
        if not index.isValid():
            self.formula_address.setText("—"); self.formula_entry.clear(); self.formula_entry.setEnabled(False); return
        manager = self.controller.data_manager
        header = manager.headers[index.column()]
        self.formula_address.setText(f"{column_letters(index.column())}{index.row() + 1}")
        self.formula_address.setToolTip(header + " · original worksheet row (unaffected by sorting)")
        raw = manager.raw_value(index.row(), header)
        self.formula_entry.setText("" if raw == MISSING_VALUE else raw)
        self.formula_entry.setEnabled(not self._data_busy and header not in {"QA Status", "Primary Reason"})
        self.formula_entry.setToolTip(manager.formula_errors.get((index.row(), header),
            "Arrows pick cells after = or an operator · F2 toggles text navigation · Enter applies · Esc cancels · F4 locks references"))

    def configure_formula_editor(self, editor, index):
        source = self.proxy.mapToSource(index)
        editor.origin = (source.row(), source.column())
        editor.resolve_reference = self.resolve_formula_reference
        editor.highlight_reference = self.highlight_formula_reference
        editor.draft_changed.connect(self.formula_entry.setText)

    def resolve_formula_reference(self, previous, key):
        if self._data_busy:
            return None
        index = self.proxy.mapFromSource(self.model.index(*previous))
        if not index.isValid():
            return None
        # Frozen identity fields are physically to the left of the scrolling
        # pane, even when their original worksheet columns occur later.
        columns = [c for view in (self.frozen_table, self.table)
                   for c in (view.horizontalHeader().logicalIndex(i) for i in range(self.model.columnCount())) if not view.isColumnHidden(c)]
        row, column = index.row(), index.column()
        if key in {Qt.Key.Key_Left, Qt.Key.Key_Right}:
            if column not in columns:
                return None
            position = columns.index(column) + (-1 if key == Qt.Key.Key_Left else 1)
            if not 0 <= position < len(columns):
                return None
            column = columns[position]
        else:
            row += -1 if key == Qt.Key.Key_Up else 1
            if not 0 <= row < self.proxy.rowCount():
                return None
        target = self.proxy.index(row, column)
        source = self.proxy.mapToSource(target)
        table = self.frozen_table if not self.frozen_table.isColumnHidden(column) else self.table
        table.scrollTo(target)
        return source.row(), source.column()

    def highlight_formula_reference(self, region):
        if hasattr(self, "frozen_table"):
            for table in (self.table, self.frozen_table):
                table.reference_region = region
                table.viewport().update()

    def focus_formula(self):
        if self._data_busy:
            return
        if not self.table.currentIndex().isValid():
            self.table.setCurrentIndex(self.proxy.index(0, 0))
        self.formula_entry.setFocus(); self.formula_entry.selectAll()

    def apply_formula_entry(self):
        if self._data_busy or not self._formula_target or not self.formula_entry.isEnabled():
            return
        row, column = self._formula_target
        self.model.setData(self.model.index(row, column), self.formula_entry.text())
        self.restore_cell(row, column); self.sync_formula_bar()

    def insert_named_function(self, name):
        if self._data_busy:
            return
        if not self.table.currentIndex().isValid():
            self.table.setCurrentIndex(self.proxy.index(0, 0))
        if not self.formula_entry.isEnabled():
            return
        if name in {"TODAY", "NOW", "PI", "RAND", "TRUE", "FALSE", "ROW", "COLUMN"}:
            text = name + "()"
        else:
            text = name + "("
        if self.formula_entry.text().startswith("="):
            if self.formula_entry.selectedText().startswith("="):
                self.formula_entry.insert("=" + text)
            else:
                if self.formula_entry.cursorPosition() == 0:
                    self.formula_entry.setCursorPosition(len(self.formula_entry.text()))
                self.formula_entry.insert(text)
        else:
            self.formula_entry.setText("=" + text)
        self.formula_entry.setFocus()

    def insert_column_reference(self):
        if self._data_busy:
            return
        headers = [header for header in self.controller.data_manager.headers if header not in {"QA Status", "Primary Reason"}]
        name, accepted = QInputDialog.getItem(self, "Insert column reference", "Choose a column from the same lead row:", headers, 0, False)
        if accepted:
            if not self.table.currentIndex().isValid():
                self.table.setCurrentIndex(self.proxy.index(0, 0))
            if not self.formula_entry.isEnabled():
                return
            text = f"[{name}]"
            if self.formula_entry.text().startswith("="):
                self.formula_entry.insert(("=" if self.formula_entry.selectedText().startswith("=") else "") + text)
            else:
                self.formula_entry.setText("=" + text)
            self.formula_entry.setFocus()

    def insert_function(self, category=None):
        if self._data_busy:
            return
        dialog = FormulaDialog(self, category if isinstance(category, str) else None)
        if dialog.exec() and dialog.selected_function():
            self.insert_named_function(dialog.selected_function())

    def fill_down(self):
        self._fill_selection(False)

    def fill_right(self):
        self._fill_selection(True)

    def _fill_selection(self, across):
        if self._data_busy:
            return
        indexes = sorted(self.table.selectedIndexes(), key=lambda i: (i.row(), i.column()))
        groups = {}
        for index in indexes:
            groups.setdefault(index.row() if across else index.column(), []).append(index)
        edits = {}; manager = self.controller.data_manager
        try:
            for group in groups.values():
                source = self.proxy.mapToSource(group[0]); header = manager.headers[source.column()]
                raw = manager.raw_value(source.row(), header)
                for index in group[1:]:
                    target = self.proxy.mapToSource(index)
                    value = translate_formula(raw, (source.row(), source.column()), (target.row(), target.column()), manager.headers) if (source.row(), header) in manager.formulas else raw
                    edits[target.row(), manager.headers[target.column()]] = value
            if self.controller.edit_cells(edits, "Fill right" if across else "Fill down"):
                self.refresh()
        except FormulaError as exc:
            QMessageBox.information(self, "Fill selection", str(exc))

    def formulas_to_values(self):
        if self._data_busy:
            return
        manager = self.controller.data_manager
        cells = [self.proxy.mapToSource(index) for index in self.table.selectedIndexes()]
        edits = {(i.row(), manager.headers[i.column()]): manager.records[i.row()][manager.headers[i.column()]]
                 for i in cells if (i.row(), manager.headers[i.column()]) in manager.formulas}
        if self.controller.edit_cells(edits, "Replace formulas with values", allow_formulas=False):
            self.refresh()

    def toggle_formulas(self, show):
        self.model.show_formulas = show
        self.model.dataChanged.emit(self.model.index(0, 0), self.model.index(self.model.rowCount()-1, self.model.columnCount()-1))

    def calculate_now(self):
        if not self._data_busy:
            self.controller.recalculate_formulas(); self.refresh()

    def delete_columns(self):
        if self._data_busy:
            return
        if not self.controller.data_manager.custom_columns:
            QMessageBox.information(self, "Delete columns", "There are no custom columns yet. Use Add columns to create them. Required lead fields can be hidden with Columns in the view toolbar.")
            return
        dialog = DeleteColumnsDialog(self, self.controller.data_manager)
        if dialog.exec() and (names := dialog.selected_columns()):
            self.model.beginResetModel()
            try:
                self.controller.change_columns(names, delete=True)
                # Numeric filter positions after a removed column would target a different field.
                self.proxy.column_filters.clear(); self.proxy.column_conditions.clear()
            except ValueError as exc:
                QMessageBox.information(self,'Delete columns',str(exc))
            finally:
                self.model.endResetModel()
            self.refresh(); self.columns_added.emit()

    def formula_key_event(self, event):
        if event.type() != QEvent.Type.KeyPress:
            return False
        if event.key() == Qt.Key.Key_Escape:
            self.sync_formula_bar(); self.table.setFocus(); return True
        if event.key() == Qt.Key.Key_F4:
            import re
            text, cursor = self.formula_entry.text(), self.formula_entry.cursorPosition()
            for match in re.finditer(r"(?<![\w])\$?([A-Za-z]{1,3})\$?([1-9][0-9]*)(?![\w])", text):
                if match.start() <= cursor <= match.end():
                    col, row = match.groups(); versions = [col+row, "$"+col+"$"+row, col+"$"+row, "$"+col+row]
                    replacement = versions[(versions.index(match.group()) + 1) % 4]
                    self.formula_entry.setText(text[:match.start()] + replacement + text[match.end():])
                    self.formula_entry.setCursorPosition(match.start()+len(replacement)); break
            return True
        return False

    def formula_help(self):
        export_note=('Team exports and clipboard copies contain server-authorized values. Saved private sheets retain expressions. '
                     if hasattr(self.controller,'client') else 'Export writes calculated lead values and a Worksheet Formulas sheet containing expression text. ')
        QMessageBox.information(self, "Formulas & shortcuts",
            'Start a cell with =, for example =column1+column2. A matching header takes priority over column positions.\n\n'
            'Use =[Revenue]*10%, =[First Name]&" "&[Last Name], =SUM(A1:A10), or =IFERROR(A1/B1,0). '
            'Named columns mean this lead row; A1 refers to original worksheet row 1. Sorting and filtering do not change references. '
            'Use $A$1 to lock a reference when filling. Prefix a literal equals sign with an apostrophe.\n\n'
            'After = or an operator, use arrow keys to pick a cell; keep moving to change that reference. '
            'Type + and pick another cell, then Enter to calculate. Shift+arrows extend a range. '
            'F2 while editing toggles between reference picking and moving the text cursor. Esc cancels the draft.\n\n'
            'Ctrl+Shift+F: formula bar · Shift+F3: function library · F2: edit cell · F4 in formula bar: lock reference · '
            'Ctrl+D / Ctrl+R: fill selected cells down / right · Ctrl+`: show formulas · F9: recalculate · Ctrl+Z / Ctrl+Y: undo / redo.\n\n'
            'Shift+Space: select visible row cells · Ctrl+Space: select visible column cells. These selection shortcuts do not intercept text editing.\n\n'
            'Formulas recalculate after worksheet edits and are saved with the workspace. '+export_note+'Ordinary copy copies the displayed values.\n\n'
            'The function library lists available engine functions. VBA, external workbook references, dynamic spill output, '
            'INDIRECT and OFFSET are not supported. Arrays may be consumed inside scalar formulas. '
            'QA Status and Primary Reason are validation outputs, so they cannot be formula inputs or targets.')
