from __future__ import annotations

from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget


class ValidationPage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        title = QLabel("Validation Summary")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        self.summary = QTableWidget(0, 2)
        self.summary.setHorizontalHeaderLabels(["Metric", "Count"])
        root.addWidget(self.summary)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Select a lead in the Leads Workspace to inspect row-level reasons.")
        root.addWidget(self.details, 1)
        self.refresh()

    def refresh(self, row: int | None = None):
        summary = self.controller.validation_summary()
        self.summary.setRowCount(len(summary))
        for r, (key, value) in enumerate(summary.items()):
            self.summary.setItem(r, 0, QTableWidgetItem(key))
            self.summary.setItem(r, 1, QTableWidgetItem(f"{value:,}"))
        self.summary.resizeColumnsToContents()
        if row is None or row not in self.controller.validation_results:
            self.details.setPlainText("Select a validated row in Leads Workspace to view detailed results.")
            return
        result = self.controller.validation_results[row]
        reasons = "\n".join(f"• {x}" for x in result.reasons) or "• None"
        self.details.setPlainText(
            f"Row: {row + 1}\nQA Status: {result.qa_status}\nPrimary Reason: {result.primary_reason}\nValidation category: {result.status}\n"
            f"TAL: {result.tal_status}\n{result.tal_reason}\n\n"
            f"Suppression: {result.suppression_status}\n{result.suppression_reason}\n\n"
            f"Duplicate: {result.duplicate_status}\n\nValidation Reasons:\n{reasons}"
        )
