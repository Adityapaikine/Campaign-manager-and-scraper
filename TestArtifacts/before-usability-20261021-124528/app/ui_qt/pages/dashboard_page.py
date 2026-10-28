from __future__ import annotations

from collections import Counter

from PySide6.QtWidgets import QGridLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.ui_qt.widgets.cards import MetricCard


class DashboardPage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        title = QLabel("Dashboard")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        self.metrics = QGridLayout()
        self.cards = {
            "records": MetricCard("Total Records"),
            "valid": MetricCard("Valid"),
            "issues": MetricCard("Needs Attention"),
            "email": MetricCard("Email Coverage"),
        }
        for i, card in enumerate(self.cards.values()):
            self.metrics.addWidget(card, 0, i)
        root.addLayout(self.metrics)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Status", "Count"])
        root.addWidget(self.table, 1)
        self.refresh()

    def refresh(self):
        summary = self.controller.validation_summary()
        total = summary["Total Records"]
        valid = summary["Valid"]
        issues = total - valid if self.controller.row_states else 0
        email = summary["Emails Found"]
        coverage = (email / total * 100.0) if total else 0.0
        self.cards["records"].set_value(f"{total:,}")
        self.cards["valid"].set_value(f"{valid:,}")
        self.cards["issues"].set_value(f"{issues:,}")
        self.cards["email"].set_value(f"{coverage:.1f}%", f"{email:,} populated")
        statuses = Counter(self.controller.row_states.values())
        self.table.setRowCount(len(statuses))
        for r, (status, count) in enumerate(statuses.most_common()):
            self.table.setItem(r, 0, QTableWidgetItem(status))
            self.table.setItem(r, 1, QTableWidgetItem(f"{count:,}"))
        self.table.resizeColumnsToContents()
