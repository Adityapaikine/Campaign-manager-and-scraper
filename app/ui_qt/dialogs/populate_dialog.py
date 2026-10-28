"""Choose lookup columns afresh for every population run."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.core.lead_reference import COMPANY_FIELDS, PROSPECT_FIELDS, TABLE_NAME


class PopulateColumnsDialog(QDialog):
    def __init__(self, parent, info, scopes):
        super().__init__(parent)
        self.setWindowTitle("Populate from database")
        self.resize(760, 720)
        self.scopes = scopes
        root = QVBoxLayout(self)
        heading = QLabel("Choose the columns to populate")
        heading.setObjectName("sectionTitle")
        root.addWidget(heading)
        count = f" · {info.count:,} reference leads" if info.count is not None else ""
        summary = QLabel(f"{info.label}{count} · {info.table}")
        summary.setTextFormat(Qt.TextFormat.PlainText)
        summary.setObjectName("muted")
        root.addWidget(summary)
        location = QLabel(str(info.path))
        location.setTextFormat(Qt.TextFormat.PlainText)
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        location.setWordWrap(True)
        location.setObjectName("metricHint")
        root.addWidget(location)

        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Populate"))
        self.scope = QComboBox()
        self.scope.setAccessibleName("Leads to populate")
        for key, label in (("visible", "Visible leads"), ("selected", "Selected leads"), ("all", "All leads in this workspace")):
            self.scope.addItem(f"{label} — {len(scopes[key]):,}", key)
        self.scope.setCurrentIndex(self.scope.findData("selected" if scopes["selected"] else "visible"))
        scope_row.addWidget(self.scope, 1)
        root.addLayout(scope_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        groups = QHBoxLayout(body)
        groups.setContentsMargins(0, 0, 0, 0)
        self.fields = {}
        for title, key, columns in (
            ("Prospect details", "Prospect LinkedIn Link", PROSPECT_FIELDS),
            ("Company details", "Company Website", COMPANY_FIELDS),
        ):
            group = QGroupBox(title)
            layout = QVBoxLayout(group)
            layout.setSpacing(5)
            match = QLabel("Match by " + key)
            match.setWordWrap(True)
            match.setObjectName("muted")
            layout.addWidget(match)
            actions = QHBoxLayout()
            for label, checked in (("Select all", True), ("Clear", False)):
                button = QPushButton(label)
                button.setObjectName("ghostButton")
                button.clicked.connect(lambda _=False, names=columns, value=checked: self.select_fields(names, value))
                actions.addWidget(button)
            actions.addStretch(1)
            layout.addLayout(actions)
            for column in columns:
                check = QCheckBox(column)
                if column not in info.available_fields:
                    check.setEnabled(False)
                    check.setToolTip("Map this database field and its lookup key in Database connection & column mapping first.")
                elif column == "Company Website":
                    check.setToolTip("The current website is the match key. A blank website cannot be looked up. Enable replacement to use the saved URL spelling.")
                check.toggled.connect(self.update_submit)
                self.fields[column] = check
                layout.addWidget(check)
            layout.addStretch(1)
            groups.addWidget(group, 1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        self.overwrite = QCheckBox("Replace existing values in the selected columns")
        self.overwrite.setToolTip("Off by default: only blank cells are filled. Empty database values never erase a lead value.")
        root.addWidget(self.overwrite)
        note = QLabel("Only checked columns are populated. Missing matches and conflicting saved values are skipped. "
                      "A blank Company Website cannot be filled because it is also the company match key. "
                      "You can undo the entire population with Ctrl+Z.")
        note.setWordWrap(True)
        note.setObjectName("muted")
        root.addWidget(note)
        self.selection_hint = QLabel()
        self.selection_hint.setObjectName("metricHint")
        root.addWidget(self.selection_hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.submit = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.submit.setText("Populate")
        self.submit.setObjectName("primaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.scope.currentIndexChanged.connect(self.update_submit)
        self.update_submit()

    def select_fields(self, names, checked):
        for name in names:
            if self.fields[name].isEnabled():
                self.fields[name].setChecked(checked)

    def selected_columns(self):
        return [name for name, widget in self.fields.items() if widget.isEnabled() and widget.isChecked()]

    def selected_rows(self):
        return list(self.scopes[self.scope.currentData()])

    def update_submit(self, *_):
        if not hasattr(self, "submit"):
            return
        count = len(self.selected_columns())
        rows = len(self.selected_rows())
        self.selection_hint.setText(f"{count} columns selected · {rows:,} leads")
        self.submit.setEnabled(bool(count and rows))

    def accept(self):
        if self.selected_columns() and self.selected_rows():
            super().accept()
