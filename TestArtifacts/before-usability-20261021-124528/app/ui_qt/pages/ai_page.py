from __future__ import annotations

import json

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.constants import STANDARD_HEADERS


class AIPage(QWidget):
    rule_builder_requested = Signal(str)
    normalize_requested = Signal(str)
    qa_requested = Signal(int)
    explain_requested = Signal(int)
    intelligence_requested = Signal()

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        title = QLabel("AI Center")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        subtitle = QLabel("Local Qwen is optional. Exact validation remains deterministic; AI handles interpretation, normalization, QA assistance and explanations.")
        subtitle.setWordWrap(True); subtitle.setObjectName("muted")
        root.addWidget(subtitle)
        self.tabs = QTabWidget(); root.addWidget(self.tabs,1)
        self._build_rules(); self._build_normalize(); self._build_qa(); self._build_intelligence()

    def _build_rules(self):
        w=QWidget(); l=QVBoxLayout(w)
        l.addWidget(QLabel("Describe campaign requirements in natural language:"))
        self.rule_input=QPlainTextEdit(); self.rule_input.setPlaceholderText("Example: Target Director+ Legal and Compliance contacts in US and Canada. Exclude Government. Maximum 5 leads per account.")
        l.addWidget(self.rule_input,1)
        b=QPushButton("Build Suggested Rules"); b.setObjectName("primaryButton"); b.clicked.connect(lambda:self.rule_builder_requested.emit(self.rule_input.toPlainText().strip())); l.addWidget(b)
        self.rule_output=QPlainTextEdit(); self.rule_output.setReadOnly(True); l.addWidget(self.rule_output,1)
        self.tabs.addTab(w,"Rule Builder")

    def _build_normalize(self):
        w=QWidget(); l=QVBoxLayout(w)
        row=QHBoxLayout(); row.addWidget(QLabel("Field")); self.normalize_field=QComboBox(); self.normalize_field.addItems(["Job Title","Industry","Company Size","Revenue","Country","State","City"]); row.addWidget(self.normalize_field); b=QPushButton("Normalize Unique Values"); b.setObjectName("primaryButton"); b.clicked.connect(lambda:self.normalize_requested.emit(self.normalize_field.currentText())); row.addWidget(b); row.addStretch(1); l.addLayout(row)
        self.normalize_output=QTableWidget(0,4); self.normalize_output.setHorizontalHeaderLabels(["Input","Normalized","Confidence","Reason"]); l.addWidget(self.normalize_output,1)
        self.tabs.addTab(w,"Smart Normalization")

    def _build_qa(self):
        w=QWidget(); l=QVBoxLayout(w)
        self.qa_row_label=QLabel("Selected lead row: None"); self.qa_row_label.setObjectName("muted"); l.addWidget(self.qa_row_label)
        row=QHBoxLayout(); self.qa_btn=QPushButton("AI QA Review"); self.qa_btn.setObjectName("primaryButton"); self.explain_btn=QPushButton("Explain Validation"); row.addWidget(self.qa_btn); row.addWidget(self.explain_btn); row.addStretch(1); l.addLayout(row)
        self.qa_btn.clicked.connect(lambda:self.qa_requested.emit(self._row))
        self.explain_btn.clicked.connect(lambda:self.explain_requested.emit(self._row))
        self.qa_output=QPlainTextEdit(); self.qa_output.setReadOnly(True); l.addWidget(self.qa_output,1)
        self.tabs.addTab(w,"QA & Explanation"); self._row=-1

    def _build_intelligence(self):
        w=QWidget(); l=QVBoxLayout(w)
        b=QPushButton("Generate Campaign Intelligence"); b.setObjectName("primaryButton"); b.clicked.connect(self.intelligence_requested); l.addWidget(b)
        self.intelligence_output=QPlainTextEdit(); self.intelligence_output.setReadOnly(True); l.addWidget(self.intelligence_output,1)
        self.tabs.addTab(w,"Campaign Intelligence")

    def set_selected_row(self,row:int):
        self._row=row
        self.qa_row_label.setText(f"Selected lead row: {row+1}" if row>=0 else "Selected lead row: None")
        self.qa_btn.setEnabled(row>=0); self.explain_btn.setEnabled(row>=0)

    def show_rules(self, rules):
        lines=[]
        for r in rules:
            lines.append(f"[{r.status}] {r.category} / {r.field} {r.operator} {r.value}  ({r.confidence:.0%})\n  {r.notes}")
        self.rule_output.setPlainText("\n\n".join(lines) if lines else "No structured rules returned.")

    def show_normalization(self, mapping):
        self.normalize_output.setRowCount(len(mapping))
        for r,(raw,item) in enumerate(mapping.items()):
            vals=[raw,str(item.get("normalized_value",raw)),f"{float(item.get('confidence',0)):.0%}",str(item.get("reason",''))]
            for c,v in enumerate(vals): self.normalize_output.setItem(r,c,QTableWidgetItem(v))
        self.normalize_output.resizeColumnsToContents()

    def show_json(self,target:str,result):
        text=json.dumps(result,ensure_ascii=False,indent=2,default=str)
        if target=="qa": self.qa_output.setPlainText(text)
        else: self.intelligence_output.setPlainText(text)
