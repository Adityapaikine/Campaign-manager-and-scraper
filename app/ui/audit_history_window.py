from __future__ import annotations

import csv
import json
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.core.activity_history import list_activity, list_audit


class AuditHistoryWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Audit & Activity History")
        self.geometry("1120x690")
        self.minsize(820, 520)
        self.transient(master)

        ctk.CTkLabel(self, text="Audit & Activity History", font=ctk.CTkFont(size=21, weight="bold")).pack(
            anchor="w", padx=18, pady=(16, 8)
        )
        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        tabs.add("Activity")
        tabs.add("Field Audit")
        self.activity_box = ctk.CTkTextbox(tabs.tab("Activity"), wrap="none")
        self.activity_box.pack(fill="both", expand=True, padx=8, pady=8)
        self.audit_box = ctk.CTkTextbox(tabs.tab("Field Audit"), wrap="none")
        self.audit_box.pack(fill="both", expand=True, padx=8, pady=8)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(footer, text="Export Activity CSV", width=145, command=self.export_activity).pack(side="right", padx=(8, 0))
        ctk.CTkButton(footer, text="Export Audit CSV", width=135, command=self.export_audit).pack(side="right", padx=(8, 0))
        ctk.CTkButton(footer, text="Refresh", width=90, command=self.refresh).pack(side="right")
        self.refresh()

    def refresh(self) -> None:
        events = list_activity(limit=1000)
        activity_lines = ["TIME                 TYPE               SUMMARY", "-" * 108]
        for item in events:
            details = json.dumps(item.details, ensure_ascii=False, sort_keys=True)
            activity_lines.append(f"{item.created_at:<20} {item.event_type:<18} {item.summary}")
            if details != "{}":
                activity_lines.append(f"    {details}")
        if len(activity_lines) == 2:
            activity_lines.append("No activity history yet.")
        self._set(self.activity_box, "\n".join(activity_lines))

        audits = list_audit(limit=2000)
        audit_lines = ["TIME                 FIELD                    OLD -> NEW | REASON", "-" * 118]
        for item in audits:
            audit_lines.append(
                f"{str(item['changed_at']):<20} {str(item['field_name']):<24} "
                f"{item['old_value']} -> {item['new_value']} | {item['reason']}"
            )
        if len(audit_lines) == 2:
            audit_lines.append("No field-level automated changes have been recorded yet.")
        self._set(self.audit_box, "\n".join(audit_lines))

    @staticmethod
    def _set(box: ctk.CTkTextbox, text: str) -> None:
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text)
        box.configure(state="disabled")

    def export_activity(self) -> None:
        path = filedialog.asksaveasfilename(title="Export Activity History", defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        events = list_activity(limit=5000)
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["ID", "Created At", "Event Type", "Summary", "Details"])
            for item in events:
                writer.writerow([item.id, item.created_at, item.event_type, item.summary, json.dumps(item.details, ensure_ascii=False)])
        messagebox.showinfo("Export complete", f"Activity history exported to:\n{path}", parent=self)

    def export_audit(self) -> None:
        path = filedialog.asksaveasfilename(title="Export Field Audit", defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        rows = list_audit(limit=10000)
        with open(path, "w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=["id", "record_key", "field_name", "old_value", "new_value", "reason", "confidence", "changed_at"])
            writer.writeheader()
            writer.writerows(rows)
        messagebox.showinfo("Export complete", f"Field audit exported to:\n{path}", parent=self)
