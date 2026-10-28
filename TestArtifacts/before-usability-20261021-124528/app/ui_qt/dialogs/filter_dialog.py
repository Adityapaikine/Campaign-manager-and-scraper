from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QVBoxLayout,
)


class ColumnFilterDialog(QDialog):
    def __init__(self, parent, title: str, values: list[str], selected: set[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Filter — {title}")
        self.resize(360, 500)
        self.values = list(values)
        self.selected = set(selected or values)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Search values"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search...")
        layout.addWidget(self.search)

        actions = QHBoxLayout()
        self.select_all = QPushButton("Select All")
        self.clear_all = QPushButton("Clear All")
        actions.addWidget(self.select_all)
        actions.addWidget(self.clear_all)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.list = QListWidget()
        for value in self.values:
            item = QListWidgetItem(value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if value in self.selected else Qt.CheckState.Unchecked)
            self.list.addItem(item)
        layout.addWidget(self.list, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.search.textChanged.connect(self._filter)
        self.select_all.clicked.connect(lambda: self._set_visible(Qt.CheckState.Checked))
        self.clear_all.clicked.connect(lambda: self._set_visible(Qt.CheckState.Unchecked))

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
            self.list.item(i).text()
            for i in range(self.list.count())
            if self.list.item(i).checkState() == Qt.CheckState.Checked
        }
