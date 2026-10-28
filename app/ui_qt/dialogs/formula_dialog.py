"""Searchable function library and explicit custom-column removal."""
import inspect

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                              QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout)

from app.core.formulas import function_catalog

EXAMPLES = {
    "SUM": '=SUM(A1:A10)', "AVERAGE": '=AVERAGE(A1:A10)', "COUNT": '=COUNT(A1:A10)',
    "COUNTA": '=COUNTA(A1:A10)', "IF": '=IF([Revenue]>1000,"High","Low")',
    "IFERROR": '=IFERROR(A1/B1,0)', "COUNTIF": '=COUNTIF([Country],"India")',
    "SUMIF": '=SUMIF(A1:A10,">100",B1:B10)', "ROUND": '=ROUND(A1,2)',
    "TEXTJOIN": '=TEXTJOIN(" ",TRUE,[First Name],[Last Name])',
    "CONCAT": '=CONCAT([First Name]," ",[Last Name])', "TRIM": '=TRIM([Company Name])',
    "LOWER": '=LOWER([Business Email ID])', "UPPER": '=UPPER([Country])',
    "PROPER": '=PROPER([First Name])', "LEFT": '=LEFT([Zip Code],3)',
    "RIGHT": '=RIGHT([Phone Number],4)', "LEN": '=LEN([Company Name])',
    "VLOOKUP": '=VLOOKUP(A1,B1:D10,3,FALSE)', "XLOOKUP": '=XLOOKUP(A1,B1:B10,C1:C10,"Missing")',
    "INDEX": '=INDEX(A1:C10,2,3)', "MATCH": '=MATCH(A1,B1:B10,0)',
    "DATE": '=DATE(2026,10,24)', "TODAY": '=TEXT(TODAY(),"yyyy-mm-dd")',
    "NOW": '=TEXT(NOW(),"yyyy-mm-dd hh:mm")', "TEXT": '=TEXT([Revenue],"#,##0.00")',
    "PMT": '=PMT(0.08/12,60,100000)', "ROUNDUP": '=ROUNDUP(A1,0)',
    "LET": '=LET(amount,100,amount*1.1)',
    "LAMBDA": '=SUM(MAKEARRAY(2,2,LAMBDA(r,c,r+c)))',
    "HLOOKUP": '=HLOOKUP(A1,B1:F3,3,FALSE)',
}

SIGNATURES = {
    "HLOOKUP": "lookup_value, table_array, row_index_num, [range_lookup]",
    "VLOOKUP": "lookup_value, table_array, col_index_num, [range_lookup]",
    "XLOOKUP": "lookup_value, lookup_array, return_array, [if_not_found], [match_mode], [search_mode]",
    "LOOKUP": "lookup_value, lookup_vector, [result_vector]",
    "SUM": "number1, [number2], …", "AVERAGE": "number1, [number2], …",
    "IF": "logical_test, value_if_true, [value_if_false]", "IFERROR": "value, value_if_error",
    "LET": "name1, value1, calculation", "LAMBDA": "parameter1, …, calculation",
    "SUMIF": "range, criteria, [sum_range]", "COUNTIF": "range, criteria",
    "MUNIT": "dimension", "ROW": "[reference]", "COLUMN": "[reference]",
}


class FormulaDialog(QDialog):
    def __init__(self, parent=None, category=None):
        super().__init__(parent)
        self.setWindowTitle("Insert function")
        self.resize(620, 540)
        root = QVBoxLayout(self)
        self.catalog = function_catalog()
        title = QLabel(f"Function library · {len(self.catalog)} available functions")
        title.setObjectName("sectionTitle"); root.addWidget(title)
        row = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Search a function, e.g. SUM, IF or XLOOKUP")
        self.search.setAccessibleName("Search functions"); row.addWidget(self.search, 1)
        self.category = QComboBox(); self.category.addItems(["All categories", *sorted(set(self.catalog.values()))])
        self.category.setAccessibleName("Function category"); row.addWidget(self.category)
        root.addLayout(row)
        self.functions = QListWidget(); self.functions.setAccessibleName("Available functions"); root.addWidget(self.functions, 1)
        self.description = QLabel(); self.description.setWordWrap(True)
        self.description.setTextFormat(Qt.TextFormat.PlainText); self.description.setMinimumHeight(90)
        root.addWidget(self.description)
        note = QLabel("One result per lead cell. Arrays can be used inside SUM, INDEX or TEXTJOIN. "
                      "Worksheet row 1 is the first lead; dates calculate as Excel serial numbers unless formatted with TEXT.")
        note.setWordWrap(True); note.setObjectName("muted"); root.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Insert function")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.search.textChanged.connect(self.filter_functions)
        self.category.currentTextChanged.connect(self.filter_functions)
        self.functions.currentItemChanged.connect(self.describe)
        self.functions.itemDoubleClicked.connect(lambda _: self.accept())
        if category:
            self.category.setCurrentText(category)
        self.filter_functions(); self.search.setFocus()

    def filter_functions(self, *_):
        query = self.search.text().strip().upper()
        category = self.category.currentText()
        self.functions.clear()
        for name, group in self.catalog.items():
            if query in name and (category == "All categories" or category == group):
                self.functions.addItem(name)
        if self.functions.count():
            self.functions.setCurrentRow(0)

    def describe(self, item, *_):
        if not item:
            self.description.setText("No matching functions. Try another name or category."); return
        name = item.text()
        import formulas
        fn = formulas.get_functions().get(name)
        if isinstance(fn, dict):
            fn = fn["function"]
        try:
            signature = inspect.signature(fn)
            parameters = [p for p in signature.parameters.values() if p.kind != p.KEYWORD_ONLY]
            arguments = ", ".join(("[" + p.name + "]") if p.default != p.empty else p.name
                                  for p in parameters if p.name not in {"cell"})
        except (ValueError, TypeError):
            arguments = "arguments"
        arguments = SIGNATURES.get(name, arguments)
        self.description.setText(f"{name}({arguments})\nCategory: {self.catalog[name]}\n"
                                 + (f"Example: {EXAMPLES[name]}" if name in EXAMPLES else "Select Insert, then enter your cell references or values."))

    def selected_function(self):
        return self.functions.currentItem().text() if self.functions.currentItem() else None


class DeleteColumnsDialog(QDialog):
    def __init__(self, parent, manager):
        super().__init__(parent)
        self.setWindowTitle("Delete custom columns"); self.resize(490, 430)
        root = QVBoxLayout(self)
        note = QLabel("Choose custom columns to remove, including their values and formulas. "
                      "You can undo this change. Required lead fields can be hidden using Columns in the view toolbar.")
        note.setWordWrap(True); root.addWidget(note)
        self.columns = QListWidget(); root.addWidget(self.columns, 1)
        for name in manager.custom_columns:
            item = QListWidgetItem(name); item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked); self.columns.addItem(item)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Delete selected columns")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def selected_columns(self):
        return [self.columns.item(i).text() for i in range(self.columns.count())
                if self.columns.item(i).checkState() == Qt.CheckState.Checked]
