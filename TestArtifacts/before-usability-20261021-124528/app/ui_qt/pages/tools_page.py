from __future__ import annotations

import json

from PySide6.QtWidgets import QLabel, QPushButton, QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget

from app.core.activity_history import list_activity, list_audit
from app.core.diagnostics import diagnostics_report, run_diagnostics
from app.utils.config import LOG_DIR
from app.core.mapping_template_service import MappingTemplateService


class ToolsPage(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller=controller
        root=QVBoxLayout(self); root.setContentsMargins(18,16,18,16)
        title=QLabel("Operations & Diagnostics"); title.setObjectName("pageTitle"); root.addWidget(title)
        self.tabs=QTabWidget(); root.addWidget(self.tabs,1)
        self.activity=QTableWidget(0,4); self.activity.setHorizontalHeaderLabels(["Time","Type","Summary","Details"])
        self.audit=QTableWidget(0,7); self.audit.setHorizontalHeaderLabels(["Time","Record","Field","Old","New","Reason","Confidence"])
        diag=QWidget(); dl=QVBoxLayout(diag); refresh=QPushButton("Run Diagnostics"); refresh.setObjectName("primaryButton"); refresh.clicked.connect(self.run_diagnostics); dl.addWidget(refresh); self.diag=QTextEdit(); self.diag.setReadOnly(True); dl.addWidget(self.diag,1)
        logs=QWidget(); ll=QVBoxLayout(logs); self.log_text=QTextEdit(); self.log_text.setReadOnly(True); lb=QPushButton("Refresh Log"); lb.clicked.connect(self.run_logs); ll.addWidget(lb); ll.addWidget(self.log_text,1)
        mappings=QWidget(); ml=QVBoxLayout(mappings); self.mapping_table=QTableWidget(0,4); self.mapping_table.setHorizontalHeaderLabels(["Name","Kind","Source Signature","Updated"]); ml.addWidget(self.mapping_table,1); self.delete_mapping=QPushButton("Delete Selected Template"); self.delete_mapping.clicked.connect(self._delete_mapping); ml.addWidget(self.delete_mapping)
        self.tabs.addTab(self.activity,"Activity"); self.tabs.addTab(self.audit,"Audit Trail"); self.tabs.addTab(mappings,"Mapping Templates"); self.tabs.addTab(diag,"Diagnostics"); self.tabs.addTab(logs,"Logs")
        timing_page = QWidget(); timing_layout = QVBoxLayout(timing_page)
        timing_button = QPushButton("Refresh timings"); timing_button.clicked.connect(self.refresh_timings)
        timing_layout.addWidget(timing_button)
        self.timings = QTextEdit(); self.timings.setReadOnly(True); timing_layout.addWidget(self.timings, 1)
        self.tabs.addTab(timing_page, "Performance")
        self.refresh()

    def refresh(self):
        events=list_activity(500); self.activity.setRowCount(len(events))
        for r,e in enumerate(events):
            vals=[e.created_at,e.event_type,e.summary,json.dumps(e.details,ensure_ascii=False,default=str)]
            for c,v in enumerate(vals): self.activity.setItem(r,c,QTableWidgetItem(v))
        audits=list_audit(1000); self.audit.setRowCount(len(audits))
        for r,a in enumerate(audits):
            vals=[a.get("changed_at"),a.get("record_key"),a.get("field_name"),a.get("old_value"),a.get("new_value"),a.get("reason"),a.get("confidence")]
            for c,v in enumerate(vals): self.audit.setItem(r,c,QTableWidgetItem("" if v is None else str(v)))
        self.activity.resizeColumnsToContents(); self.audit.resizeColumnsToContents();
        templates=MappingTemplateService().list(); self.mapping_table.setRowCount(len(templates))
        for r,t in enumerate(templates):
            vals=[t.name,t.kind,t.source_signature,t.updated_at]
            for c,v in enumerate(vals): self.mapping_table.setItem(r,c,QTableWidgetItem(v))
        self.mapping_table.resizeColumnsToContents(); self.refresh_diagnostics(); self.refresh_logs()
        self.refresh_timings()

    def refresh_timings(self):
        from suite_bootstrap import ROOT
        paths = [LOG_DIR / "email_performance.json"]
        scraper = list((ROOT / "Output").glob("*.performance.json"))
        if scraper: paths.append(max(scraper, key=lambda path: path.stat().st_mtime))
        sections = []
        labels = {"local_evidence": "Existing company evidence", "local_rows": "Cached and existing results",
                  "public_discovery": "Public searches", "company_website": "Public company pages",
                  "request_wait": "Waiting for website limits",
                  "save_completed_rows": "Saving completed results", "browser_navigation": "Loading web pages",
                  "email_batch": "Parallel email batch", "email": "Individual email lookups",
                  "offsite_enrichment": "Company and location enrichment"}
        for path in paths:
            if not path.exists(): continue
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
                counts = report.get("counts", {})
                lines = ["Lead workspace" if path.name == "email_performance.json" else "Scraper: " + path.stem,
                         f"Total elapsed: {report.get('elapsed_seconds', 0):.1f} seconds"]
                if "total_rows" in report:
                    lines += [f"Completed results: {counts.get('completed_rows', 0):,} / {report['total_rows']:,}",
                              f"Emails added: {counts.get('emails_added', 0):,}",
                              f"Completed rows still without an email: {counts.get('blank_rows', 0):,}",
                              f"Reused saved results: {counts.get('resumed_rows', 0):,}",
                              f"Shared company lookups: {counts.get('company_lookups_reused', 0):,}",
                              f"Unfinished rows: {report.get('unfinished_rows', 0):,}"]
                lines += ["", "Time by stage (concurrent stages overlap):"]
                lines += [f"{labels.get(key, key.replace('_', ' ').capitalize())}: {value:.2f} s"
                          for key, value in sorted(report.get("stage_seconds", {}).items(), key=lambda pair: -pair[1])]
                sections.append("\n".join(lines))
            except (ValueError, OSError):
                sections.append("The latest timing report could not be read.")
        self.timings.setPlainText("\n\n".join(sections) or "Run Find Emails or a Scraper batch to see timings here. Completed rows are saved as the batch progresses.")

    def _delete_mapping(self):
        row=self.mapping_table.currentRow()
        if row<0: return
        name=self.mapping_table.item(row,0).text(); MappingTemplateService().delete(name); self.refresh()

    def run_diagnostics(self):
        runner = getattr(self.window(), "run_worker", None)
        if runner:
            runner(diagnostics_report, started="Checking application health…", finished="Diagnostics complete", on_done=self.diag.setPlainText)
        else:
            self.refresh_diagnostics()

    def run_logs(self):
        runner = getattr(self.window(), "run_worker", None)
        if runner:
            runner(self._read_logs, started="Reading activity log…", finished="Log refreshed", on_done=self.log_text.setPlainText)
        else:
            self.refresh_logs()

    def refresh_diagnostics(self): self.diag.setPlainText(diagnostics_report())
    def refresh_logs(self): self.log_text.setPlainText(self._read_logs())

    @staticmethod
    def _read_logs():
        path=LOG_DIR/"lead_manager.log"
        try:
            lines=path.read_text(encoding="utf-8",errors="replace").splitlines()[-1500:]
            return "\n".join(lines)
        except Exception as exc: return str(exc)
