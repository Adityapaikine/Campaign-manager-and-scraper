from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from app.core.mapping_template_service import MappingTemplateService


class MappingTemplatesWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Saved Mapping Templates")
        self.geometry("820x560")
        self.minsize(660, 440)
        self.transient(master)
        self.service = MappingTemplateService()

        ctk.CTkLabel(self, text="Saved Mapping Templates", font=ctk.CTkFont(size=20, weight="bold")).pack(
            anchor="w", padx=18, pady=(16, 8)
        )
        ctk.CTkLabel(
            self,
            text="Templates are created from the import mapping windows and can be reused for files with the same structure.",
            wraplength=760,
            justify="left",
        ).pack(fill="x", padx=18, pady=(0, 8))
        self.body = ctk.CTkScrollableFrame(self)
        self.body.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkButton(footer, text="Refresh", width=90, command=self.refresh).pack(side="right")
        self.refresh()

    def refresh(self) -> None:
        for child in self.body.winfo_children():
            child.destroy()
        templates = self.service.list()
        if not templates:
            ctk.CTkLabel(self.body, text="No mapping templates saved yet.").pack(anchor="w", padx=8, pady=8)
            return
        for template in templates:
            row = ctk.CTkFrame(self.body)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=template.name, width=220, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8, pady=8)
            ctk.CTkLabel(row, text=template.kind.title(), width=100, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=f"{len(template.mapping)} mapped fields", width=150, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=template.updated_at, anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="Delete", width=70, fg_color="#B3261E", hover_color="#8C1D18", command=lambda name=template.name: self.delete(name)).pack(side="right", padx=8)

    def delete(self, name: str) -> None:
        if messagebox.askyesno("Delete template", f"Delete mapping template '{name}'?", parent=self):
            self.service.delete(name)
            self.refresh()
