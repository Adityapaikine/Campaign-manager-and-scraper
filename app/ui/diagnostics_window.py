from __future__ import annotations

from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.core.diagnostics import diagnostics_report


class DiagnosticsWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("System Diagnostics")
        self.geometry("980x650")
        self.minsize(760, 500)
        self.transient(master)
        ctk.CTkLabel(self, text="System Diagnostics", font=ctk.CTkFont(size=21, weight="bold")).pack(
            anchor="w", padx=18, pady=(16, 8)
        )
        ctk.CTkLabel(
            self,
            text="No API keys or lead records are included in this report.",
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 8))
        self.text = ctk.CTkTextbox(self, wrap="none")
        self.text.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(footer, text="Save Report", width=110, command=self.save_report).pack(side="right", padx=(8, 0))
        ctk.CTkButton(footer, text="Copy", width=90, command=self.copy_report).pack(side="right", padx=(8, 0))
        ctk.CTkButton(footer, text="Run Again", width=100, command=self.refresh).pack(side="right")
        self.refresh()

    def refresh(self) -> None:
        report = diagnostics_report()
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", report)
        self.text.configure(state="disabled")

    def copy_report(self) -> None:
        report = self.text.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(report)
        messagebox.showinfo("Diagnostics", "Diagnostic report copied to the clipboard.", parent=self)

    def save_report(self) -> None:
        path = filedialog.asksaveasfilename(title="Save Diagnostic Report", defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(self.text.get("1.0", "end-1c"))
        messagebox.showinfo("Diagnostics", f"Report saved to:\n{path}", parent=self)
