from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                              QFormLayout, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget)

from app.core.campaign_dashboard import STATUSES, daily_target


class CampaignPlanDialog(QDialog):
    def __init__(self, parent, campaign):
        super().__init__(parent)
        self.setWindowTitle("Campaign plan & delivery"); self.resize(520, 480)
        root = QVBoxLayout(self)
        title = QLabel(f"{campaign.campaign_name} · {campaign.campaign_id}")
        title.setTextFormat(Qt.TextFormat.PlainText); title.setWordWrap(True); title.setObjectName("sectionTitle")
        root.addWidget(title)
        note = QLabel("Set the allocation and schedule, then update the cumulative delivered total as you complete deliveries. Exporting leads does not change this count.")
        note.setWordWrap(True); note.setObjectName("muted"); root.addWidget(note)
        form = QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow); root.addLayout(form)
        self.allocation = QSpinBox(); self.delivered = QSpinBox()
        for control, value, name in ((self.allocation, campaign.allocation, "Total allocation"), (self.delivered, campaign.delivered, "Delivered leads")):
            control.setRange(-1, 1_000_000_000); control.setSpecialValueText("Not set")
            control.setGroupSeparatorShown(True); control.setValue(value if value is not None else -1)
            control.setAccessibleName(name)
        form.addRow("Total allocation", self.allocation)
        self.start_enabled, self.start = self.date_field(form, "Start date", campaign.start)
        self.end_enabled, self.end = self.date_field(form, "End date", campaign.end)
        form.addRow("Delivered leads", self.delivered)
        self.status = QComboBox(); self.status.addItems(["Not set", *STATUSES]); self.status.setCurrentText(campaign.status or "Not set")
        self.status.setAccessibleName("Campaign status"); form.addRow("Status", self.status)
        self.preview = QLabel(); self.preview.setWordWrap(True); root.addWidget(self.preview)
        self.error = QLabel(); self.error.setWordWrap(True); self.error.setStyleSheet("color: #B02337;"); root.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primaryButton")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.allocation.valueChanged.connect(self.refresh_preview); self.delivered.valueChanged.connect(self.refresh_preview)
        self.start.dateChanged.connect(self.refresh_preview); self.end.dateChanged.connect(self.refresh_preview)
        self.start_enabled.toggled.connect(self.refresh_preview); self.end_enabled.toggled.connect(self.refresh_preview)
        self.refresh_preview()

    def date_field(self, form, name, value):
        holder = QWidget(); row = QHBoxLayout(holder); row.setContentsMargins(0, 0, 0, 0)
        enabled = QCheckBox("Set"); enabled.setChecked(value is not None); enabled.setAccessibleName(f"Set {name.lower()}")
        editor = QDateEdit(); editor.setCalendarPopup(True); editor.setDisplayFormat("dd-MMM-yyyy")
        selected = value or date.today(); editor.setDate(QDate(selected.year, selected.month, selected.day))
        editor.setEnabled(enabled.isChecked()); enabled.toggled.connect(editor.setEnabled)
        editor.setAccessibleName(name); row.addWidget(enabled); row.addWidget(editor, 1); form.addRow(name, holder)
        return enabled, editor

    def values(self):
        return {"allocation": self.allocation.value() if self.allocation.value() >= 0 else None,
                "delivered": self.delivered.value() if self.delivered.value() >= 0 else None,
                "start": self.start.date().toPython() if self.start_enabled.isChecked() else None,
                "end": self.end.date().toPython() if self.end_enabled.isChecked() else None,
                "status": self.status.currentText() if self.status.currentText() in STATUSES else None}

    def refresh_preview(self, *_):
        values = self.values(); target = daily_target(values["allocation"], values["start"], values["end"])
        if values["start"] and values["end"] and values["end"] < values["start"]:
            self.preview.setText("End date must be on or after start date.")
        elif target is None:
            self.preview.setText("Set an allocation and both dates to see the daily delivery target.")
        else:
            days = (values["end"] - values["start"]).days + 1
            self.preview.setText(f"Average leads per day: {target:,}\n{values['allocation']:,} leads ÷ {days:,} calendar days, rounded up. Both dates are included.")

    def accept(self):
        values = self.values()
        if values["start"] and values["end"] and values["end"] < values["start"]:
            self.error.setText("End date cannot be before start date."); return
        super().accept()
