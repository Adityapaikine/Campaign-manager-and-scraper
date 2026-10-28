from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QTextEdit, QVBoxLayout, QWidget


class ValidationDrawer(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller=controller
        root=QVBoxLayout(self); root.setContentsMargins(12,12,12,12)
        title=QLabel("Validation Summary"); title.setObjectName("sectionTitle"); root.addWidget(title)
        form=QFormLayout(); self.labels={}
        for key in ("Total Records","Valid","Warnings","Invalid","Suppressed","Outside TAL","Duplicates","Missing Email","Emails Found","Manual Review"):
            label=QLabel("0"); self.labels[key]=label; form.addRow(key,label)
        root.addLayout(form)
        detail_title=QLabel("Selected Record"); detail_title.setObjectName("sectionTitle"); root.addWidget(detail_title)
        self.detail=QTextEdit(); self.detail.setReadOnly(True); self.detail.setMinimumWidth(300); root.addWidget(self.detail,1)
        self.refresh()

    def refresh(self,row:int|None=None):
        summary=self.controller.validation_summary()
        for k,l in self.labels.items(): l.setText(f"{summary.get(k,0):,}")
        email = self.controller.email_results.get(row)
        email_text = ""
        if email:
            email_text = (f"\n\nEmail result: {email.status}\nCandidate: {email.candidate}\n"
                          f"Confidence: {email.confidence}%\n{email.reason}\n"
                          + "\n".join(email.evidence_sources))
        if row is None or row not in self.controller.validation_results:
            self.detail.setPlainText(f"Row: {row+1}{email_text}" if email else
                                    "Select a lead row to see its validation or email results.")
            return
        result=self.controller.validation_results[row]
        reasons="\n".join(f"• {x}" for x in result.reasons) or "• None"
        self.detail.setPlainText(
            f"Row: {row+1}\nQA Status: {result.qa_status}\nPrimary Reason: {result.primary_reason}\nValidation category: {result.status}\n\nTAL: {result.tal_status}\n{result.tal_reason}\n\n"
            f"Suppression: {result.suppression_status}\n{result.suppression_reason}\n\nDuplicate: {result.duplicate_status}\n\nReasons:\n{reasons}{email_text}"
        )
