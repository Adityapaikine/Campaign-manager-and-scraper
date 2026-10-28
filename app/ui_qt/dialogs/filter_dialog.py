from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout, QComboBox, QFormLayout,
)
from app.core.column_filter import display_value, value_key, number, date_value


class ColumnFilterDialog(QDialog):
    def __init__(self, parent, title: str, values: list[str], selected: set[str] | None = None, condition=None):
        super().__init__(parent)
        self.setWindowTitle(f"Filter — {title}")
        self.resize(410, 640)
        self.values = list(values)
        self.selected = {value_key(value) for value in (values if selected is None else selected)}
        self.sort_order = None
        self.clear_requested = False

        layout = QVBoxLayout(self)
        sorting = QHBoxLayout()
        for label, order in (("Sort A to Z / Smallest first", Qt.SortOrder.AscendingOrder),
                             ("Sort Z to A / Largest first", Qt.SortOrder.DescendingOrder)):
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, value=order: self._sort(value))
            sorting.addWidget(button)
        layout.addLayout(sorting)
        clear_filter = QPushButton("Clear filter from this column")
        clear_filter.clicked.connect(self._clear_filter)
        layout.addWidget(clear_filter)
        form = QFormLayout()
        self.rule_type = QComboBox()
        for name, kind in (("Text filters", "text"), ("Number filters", "number"), ("Date filters", "date")):
            self.rule_type.addItem(name, kind)
        self.operator = QComboBox()
        self.argument = QLineEdit()
        self.argument.setPlaceholderText("Value (dates: DD-MMM-YYYY)")
        form.addRow("Filter type", self.rule_type)
        form.addRow("Condition", self.operator)
        form.addRow("Value", self.argument)
        layout.addLayout(form)
        self.rule_type.currentIndexChanged.connect(self._operators)
        self.operator.currentIndexChanged.connect(lambda: self.argument.setEnabled(self.operator.currentData() not in {"all", "blank", "not_blank"}))
        self._operators()
        if condition:
            self.rule_type.setCurrentIndex(max(0, self.rule_type.findData(condition.get("type", "text"))))
            self.operator.setCurrentIndex(max(0, self.operator.findData(condition.get("operator", "all"))))
            self.argument.setText(condition.get("value", ""))
        layout.addWidget(QLabel("Search values"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search...")
        layout.addWidget(self.search)

        actions = QHBoxLayout()
        self.select_all = QPushButton("Select All")
        self.clear_all = QPushButton("Select None")
        actions.addWidget(self.select_all)
        actions.addWidget(self.clear_all)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.list = QListWidget()
        for value in self.values:
            item = QListWidgetItem(display_value(value) or "(Blanks)")
            item.setData(Qt.ItemDataRole.UserRole, value_key(value))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if value_key(value) in self.selected else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        layout.addWidget(self.list, 1)
        self.message = QLabel("Search narrows the values applied with OK. Filters on other columns stay active.")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.search.textChanged.connect(self._filter)
        self.select_all.clicked.connect(lambda: self._set_visible(Qt.CheckState.Checked))
        self.clear_all.clicked.connect(lambda: self._set_visible(Qt.CheckState.Unchecked))

    def _operators(self):
        self.operator.clear()
        choices = [("No condition", "all"), ("Equals", "equals"), ("Does not equal", "not_equals")]
        if self.rule_type.currentData() == "text":
            choices += [("Contains", "contains"), ("Does not contain", "not_contains"), ("Begins with", "starts"), ("Ends with", "ends")]
        else:
            choices += [("Greater than / After", "gt"), ("Greater than or equal", "gte"), ("Less than / Before", "lt"), ("Less than or equal", "lte")]
        choices += [("Blanks", "blank"), ("Non-blanks", "not_blank")]
        for label, value in choices:
            self.operator.addItem(label, value)

    def condition(self):
        operator = self.operator.currentData()
        return None if operator == "all" else {"operator": operator, "type": self.rule_type.currentData(), "value": self.argument.text().strip()}

    def _sort(self, order):
        self.sort_order = order
        super().accept()

    def _clear_filter(self):
        self.clear_requested = True
        super().accept()

    def accept(self):
        condition = self.condition()
        if condition and condition["operator"] not in {"blank", "not_blank"}:
            convert = {"number": number, "date": date_value}.get(condition["type"])
            if convert and convert(condition["value"]) is None:
                self.message.setText("Enter a valid number or date for this condition.")
                self.argument.setFocus()
                return
        super().accept()

    def _filter(self, text: str):
        needle = text.casefold().strip()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(bool(needle and needle not in item.text().casefold()))

    def _set_visible(self, state):
        for i in range(self.list.count()):
            item = self.list.item(i)
            if not item.isHidden():
                item.setCheckState(state)

    def selected_values(self) -> set[str]:
        return {
            self.list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list.count())
            if self.list.item(i).checkState() == Qt.CheckState.Checked and not self.list.item(i).isHidden()
        }
