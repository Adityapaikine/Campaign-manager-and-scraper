"""Selected-lead presentation, using the worksheet's existing edit history."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QTabWidget, QTextEdit, QVBoxLayout, QWidget, QSizePolicy,
)

from app.core.column_filter import display_value
from app.ui_qt.widgets.icons import icon


EDIT_FIELDS = (
    "First Name", "Last Name", "Company Name", "Job Title", "Phone Number",
    "Business Email ID", "Company Website", "Campaign Name", "Agent Name",
    "Calling Agent Name", "Date", "Dispo", "Comment", "Notes",
)


def plain_label(text="", style=None):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if style:
        label.setObjectName(style)
    return label


class LeadEditDialog(QDialog):
    """A modal form keeps an unfinished edit attached to the selected source row."""
    def __init__(self, parent, record):
        super().__init__(parent)
        self.setWindowTitle("Edit lead")
        self.resize(530, 690)
        layout = QVBoxLayout(self)
        layout.addWidget(plain_label("Edit lead information", "sectionTitle"))
        layout.addWidget(plain_label("Changes use the worksheet's Undo / Redo. Revalidate after editing.", "muted"))
        scroll = QScrollArea(); self.scroll = scroll; scroll.setWidgetResizable(True)
        body = QWidget(); form = QFormLayout(body)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.fields = {}
        for field in EDIT_FIELDS:
            value = display_value(record.get(field))
            if field in {"Comment", "Notes"}:
                editor = QTextEdit(); editor.setAcceptRichText(False); editor.setPlainText(value)
                editor.setFixedHeight(85)
            else:
                editor = QLineEdit(value)
            editor.setAccessibleName("Disposition" if field == "Dispo" else field)
            self.fields[field] = editor
            form.addRow("Disposition" if field == "Dispo" else field, editor)
        scroll.setWidget(body); layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save changes")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primaryButton")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return {field: editor.toPlainText() if isinstance(editor, QTextEdit) else editor.text()
                for field, editor in self.fields.items()}

    def focus_field(self, field):
        editor = self.fields[field]
        editor.setFocus()
        self.scroll.ensureWidgetVisible(editor)


class LeadDetailsPanel(QFrame):
    close_requested = Signal()
    edit_requested = Signal(int)
    recheck_requested = Signal(int)
    notes_requested = Signal(int)

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.current_row = None
        self.setObjectName("detailsCard")
        self.setMinimumWidth(300)
        self.setMaximumWidth(400)
        root = QVBoxLayout(self); root.setContentsMargins(16, 14, 16, 14); root.setSpacing(8)
        heading = QHBoxLayout()
        heading.addWidget(plain_label("Lead details", "sectionTitle"), 1)
        close = QPushButton(); close.setIcon(icon("close")); close.setObjectName("ghostButton")
        close.setFixedSize(28, 28); close.setToolTip("Hide lead details"); close.setAccessibleName("Hide lead details")
        close.clicked.connect(self.close_requested); heading.addWidget(close); root.addLayout(heading)
        root.addWidget(plain_label("Selected lead information and actions", "muted"))
        identity = QHBoxLayout(); identity.setSpacing(12)
        self.avatar = plain_label("—", "leadAvatar"); self.avatar.setFixedSize(48, 48)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter); identity.addWidget(self.avatar)
        names = QVBoxLayout(); names.setSpacing(3)
        self.name = plain_label("Select a lead", "sectionTitle")
        self.company = plain_label("Choose any cell in the worksheet.", "muted")
        names.addWidget(self.name); names.addWidget(self.company); identity.addLayout(names, 1)
        root.addLayout(identity)
        self.status = plain_label("No lead selected", "statusPill"); root.addWidget(self.status)
        self.tabs = QTabWidget(); root.addWidget(self.tabs, 1)
        self.overview = QScrollArea(); self.overview.setWidgetResizable(True)
        self.overview.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(); body.setObjectName("detailsBody")
        overview = QVBoxLayout(body); overview.setContentsMargins(0, 8, 3, 0); overview.setSpacing(8)
        info = QFrame(); info.setObjectName("infoCard")
        info_layout = QVBoxLayout(info); info_layout.setSpacing(8)
        title = QHBoxLayout(); title.addWidget(plain_label("Lead information", "sectionTitle"), 1)
        self.edit_button = QPushButton("Edit"); self.edit_button.setIcon(icon("edit"))
        self.edit_button.clicked.connect(lambda: self.edit_requested.emit(self.current_row) if self.current_row is not None else None)
        title.addWidget(self.edit_button); info_layout.addLayout(title)
        form = QFormLayout(); form.setHorizontalSpacing(10); form.setVerticalSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.values = {}
        for field, title in (("Phone Number", "Phone"), ("Business Email ID", "Email"), ("Job Title", "Job title"),
                             ("Campaign Name", "Campaign"), ("Agent Name", "Agent"),
                             ("Calling Agent Name", "Caller"), ("Date", "Date")):
            label = plain_label("—"); label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.values[field] = label; form.addRow(plain_label(title, "muted"), label)
        info_layout.addLayout(form); overview.addWidget(info)
        self.disposition = plain_label("—", "dispositionValue")
        self.comment = plain_label("No comment yet.")
        for title, widget in (("Disposition", self.disposition), ("Comment", self.comment)):
            overview.addWidget(plain_label(title, "fieldTitle")); overview.addWidget(widget)
        overview.addStretch(1); self.overview.setWidget(body)
        self.tabs.addTab(self.overview, "Overview")
        self.validation = QTextEdit(); self.validation.setReadOnly(True)
        self.tabs.addTab(self.validation, "Validation")
        self.notes = QTextEdit(); self.notes.setReadOnly(True)
        self.tabs.addTab(self.notes, "Notes")
        self.edit_full_button = QPushButton("Edit lead"); self.edit_full_button.setObjectName("primaryButton")
        self.edit_full_button.setIcon(icon("edit", "#FFFFFF"))
        self.edit_full_button.clicked.connect(self.edit_button.click); root.addWidget(self.edit_full_button)
        actions = QHBoxLayout()
        self.recheck_button = QPushButton("Recheck row"); self.recheck_button.setIcon(icon("validation"))
        self.recheck_button.clicked.connect(lambda: self.recheck_requested.emit(self.current_row) if self.current_row is not None else None)
        self.notes_button = QPushButton("Edit notes")
        self.notes_button.clicked.connect(lambda: self.notes_requested.emit(self.current_row) if self.current_row is not None else None)
        actions.addWidget(self.recheck_button); actions.addWidget(self.notes_button); root.addLayout(actions)
        self.set_busy(False)
        self.refresh()

    def set_busy(self, busy):
        self._busy = busy
        for button in (self.edit_button, self.edit_full_button, self.recheck_button, self.notes_button):
            button.setEnabled(not busy and self.current_row is not None)

    def refresh(self, row=None):
        records = self.controller.data_manager.records
        self.current_row = row if row is not None and 0 <= row < len(records) else None
        record = records[self.current_row] if self.current_row is not None else {}
        first, last = (display_value(record.get(field)) for field in ("First Name", "Last Name"))
        self.avatar.setText(((first[:1] + last[:1]).upper() or "—"))
        self.name.setText(" ".join(part for part in (first, last) if part) or ("Unnamed lead" if record else "Select a lead"))
        self.company.setText(display_value(record.get("Company Name")) or ("Company not entered" if record else "Choose any cell in the worksheet."))
        state = self.controller.row_states.get(self.current_row) or "Needs validation"
        self.status.setText(state if record else "No lead selected")
        for field, label in self.values.items():
            value = display_value(record.get(field))
            label.setText(value or "—"); label.setToolTip(value)
        self.disposition.setText(display_value(record.get("Dispo")) or "Not set")
        self.comment.setText(display_value(record.get("Comment")) or "No comment yet.")
        self.notes.setPlainText(display_value(record.get("Notes")) or "No notes yet. Use Edit notes to add a note to this lead.")
        result = self.controller.validation_results.get(self.current_row)
        if result:
            self.validation.setPlainText(
                f"QA status: {result.qa_status}\nPrimary reason: {result.primary_reason}\n\n"
                f"TAL: {result.tal_status}\n{result.tal_reason}\n\n"
                f"Suppression: {result.suppression_status}\n{result.suppression_reason}\n\n"
                + ("\n".join(f"• {reason}" for reason in result.reasons) or "No validation issues.")
            )
        else:
            self.validation.setPlainText("This lead needs validation. Use Recheck row to run the existing validation rules."
                                         if record else "Select a lead to see its validation results.")
        self.set_busy(self._busy)
