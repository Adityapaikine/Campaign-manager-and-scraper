from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QLabel, QTextEdit, QVBoxLayout, QWidget, QHBoxLayout, QPushButton


class ValidationDrawer(QWidget):
    revalidate_requested = Signal(int)
    next_issue_requested = Signal()
    edit_field_requested = Signal(int, str)
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller=controller
        self.current_row = None
        self.suggested_field = "Company Name"
        root=QVBoxLayout(self); root.setContentsMargins(12,12,12,12)
        title=QLabel("Validation Summary"); title.setObjectName("sectionTitle"); root.addWidget(title)
        form=QFormLayout(); self.labels={}
        for key in ("Total Records","Valid","Warnings","Invalid","Suppressed","Outside TAL","Duplicates","Missing Email","Emails Found","Manual Review", "Needs validation"):
            label=QLabel("0"); self.labels[key]=label; form.addRow(key,label)
        root.addLayout(form)
        detail_title=QLabel("Selected Record"); detail_title.setObjectName("sectionTitle"); root.addWidget(detail_title)
        self.detail=QTextEdit(); self.detail.setReadOnly(True); self.detail.setMinimumWidth(300); root.addWidget(self.detail,1)
        actions = QHBoxLayout()
        self.edit_button = QPushButton("Go to field")
        self.edit_button.clicked.connect(lambda: self.edit_field_requested.emit(self.current_row, self.suggested_field) if self.current_row is not None else None)
        self.revalidate_button = QPushButton("Recheck row")
        self.revalidate_button.clicked.connect(lambda: self.revalidate_requested.emit(self.current_row) if self.current_row is not None else None)
        next_button = QPushButton("Next issue"); next_button.clicked.connect(self.next_issue_requested)
        actions.addWidget(self.edit_button); actions.addWidget(self.revalidate_button); actions.addWidget(next_button)
        root.addLayout(actions)
        self.refresh()

    def refresh(self,row:int|None=None):
        row = row if row is not None and 0 <= row < len(self.controller.data_manager.records) else None
        self.current_row = row
        self.suggested_field = "Company Name"
        self.edit_button.setEnabled(row is not None)
        self.revalidate_button.setEnabled(row is not None)
        summary=self.controller.validation_summary()
        for k,l in self.labels.items(): l.setText(f"{summary.get(k,0):,}")
        email = self.controller.email_results.get(row)
        email_text = ""
        if email:
            email_text = (f"\n\nEmail result: {email.status}\nCandidate: {email.candidate}\n"
                          f"Confidence: {email.confidence}%\n{email.reason}\n"
                          + "\n".join(email.evidence_sources))
        if row is None or row not in self.controller.validation_results:
            pending = row is not None and row < len(self.controller.data_manager.records)
            self.detail.setPlainText(f"Row: {row+1}\nNeeds validation. This row is new or has changed. Click Recheck row to refresh its QA result.{email_text}"
                                    if pending else "Select a lead row to see its validation or email results.")
            return
        result=self.controller.validation_results[row]
        reasons="\n".join(f"• {x}" for x in result.reasons) or "• None"
        tal = self.controller.tal_data or getattr(self.controller.validator.tal_validator, "data", None)
        suppression = self.controller.suppression_data
        sources = f"TAL list: {tal.source_name if tal else 'None'}\nSuppression list: {suppression.source_name if suppression else ('Active campaign references' if self.controller.validator.suppression_validator else 'None')}"
        field = next((issue.field for issue in result.issues if issue.field), "Company Name")
        if result.status == "Outside TAL":
            action = "Check Company Name and Company Website against the saved TAL. Correct inaccurate lead details or replace an incorrect TAL, then recheck."
            field = "Company Name"
        elif result.status == "Suppressed":
            action = "Review the matched identifier below. Keep this lead excluded unless the lead details or suppression list are incorrect."
            field = next((column for match, column in (("Email", "Business Email ID"), ("LinkedIn", "Prospect LinkedIn Link"),
                          ("Domain", "Company Website"), ("Company", "Company Name"), ("Prospect Name", "First Name"))
                          if match in result.suppression_status), "Company Name")
        elif result.status == "Duplicate":
            action = "Compare this lead with the matching row numbers below. Correct an incorrect identifier, then recheck the affected rows."
            field = "Business Email ID" if "Business Email ID" in reasons else ("Prospect LinkedIn Link" if "LinkedIn" in reasons else "First Name")
        elif result.status == "Manual Review":
            action = "Check the possible match against the source list. Similar names alone are not confirmed matches. Correct the details and recheck."
        elif result.status.startswith("Valid"):
            action = "This row passed the current validation rules. It is available in Qualified exports."
        else:
            action = "Correct the missing or invalid fields listed below, then click Recheck row."
        self.suggested_field = field
        self.detail.setPlainText(
            f"Row: {row+1}\nQA Status: {result.qa_status}\nPrimary Reason: {result.primary_reason}\nValidation category: {result.status}\n\nTAL: {result.tal_status}\n{result.tal_reason}\n\n"
            f"Suppression: {result.suppression_status}\n{result.suppression_reason}\n\n{sources}\n\nNext step:\n{action}\n\nDuplicate: {result.duplicate_status}\n\nReasons:\n{reasons}{email_text}"
        )
