from __future__ import annotations

import customtkinter as ctk

from app.utils.config import LOG_DIR


class LogsWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Application Logs")
        self.geometry("900x550")
        self.text = ctk.CTkTextbox(self)
        self.text.pack(fill="both", expand=True, padx=12, pady=12)
        log_file = LOG_DIR / "lead_manager.log"
        content = log_file.read_text(encoding="utf-8", errors="replace") if log_file.exists() else "No logs yet."
        self.text.insert("1.0", content)
        self.text.configure(state="disabled")
