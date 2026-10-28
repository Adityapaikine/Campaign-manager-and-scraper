from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox, simpledialog

from app.core.mapping_template_service import MappingTemplateService
from app.utils.text_utils import normalize_header


class ColumnMappingDialog(ctk.CTkToplevel):
    """Modal source-column mapper with Phase-7 persistent templates."""

    IGNORE = "— Ignore —"
    AUTO = "— Auto-detected —"

    def __init__(
        self,
        master,
        *,
        title: str,
        columns: list[str],
        target_fields: tuple[str, ...] | list[str],
        detected_mapping: dict[str, str] | None = None,
        required_any: set[str] | None = None,
        template_kind: str | None = None,
    ) -> None:
        super().__init__(master)
        self.title(title)
        self.geometry("720x700")
        self.minsize(600, 500)
        self.transient(master)
        self.grab_set()
        self.result: dict[str, str] | None = None
        self._required_any = set(required_any or set())
        self._vars: dict[str, ctk.StringVar] = {}
        self._columns = list(columns)
        self._template_kind = template_kind
        self._target_fields = list(target_fields)
        self._template_service = MappingTemplateService() if template_kind else None

        ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=19, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            self,
            text="Confirm the detected columns. Change any mapping before loading the file.",
            anchor="w",
        ).pack(fill="x", padx=18, pady=(0, 8))

        if self._template_service is not None:
            template_frame = ctk.CTkFrame(self)
            template_frame.pack(fill="x", padx=18, pady=(0, 8))
            ctk.CTkLabel(template_frame, text="Saved template:", width=120, anchor="w").pack(side="left", padx=(8, 4), pady=7)
            template_names = [self.AUTO, *[item.name for item in self._template_service.list(template_kind)]]
            self.template_var = ctk.StringVar(value=self.AUTO)
            self.template_menu = ctk.CTkOptionMenu(template_frame, values=template_names, variable=self.template_var, width=240)
            self.template_menu.pack(side="left", padx=4, pady=7)
            ctk.CTkButton(template_frame, text="Load", width=70, command=self._load_template).pack(side="left", padx=4)
            ctk.CTkButton(template_frame, text="Save Current", width=110, command=self._save_template).pack(side="left", padx=4)

        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=18)
        ctk.CTkLabel(header, text="Source column", width=300, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8, pady=7)
        ctk.CTkLabel(header, text="Use as", width=300, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=8, pady=7)

        body = ctk.CTkScrollableFrame(self)
        body.pack(fill="both", expand=True, padx=18, pady=(4, 10))
        options = [self.IGNORE, *self._target_fields]
        detected_mapping = detected_mapping or {}
        best_template = self._template_service.best_match(kind=template_kind, columns=self._columns) if self._template_service else None
        initial_mapping = (
            self._adapt_template_mapping(best_template.mapping)
            if best_template is not None
            else detected_mapping
        )
        if best_template is not None:
            self.template_var.set(best_template.name)
        for source in columns:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=source, width=300, anchor="w").pack(side="left", padx=6)
            value = initial_mapping.get(source, self.IGNORE)
            if value not in options:
                value = self.IGNORE
            var = ctk.StringVar(value=value)
            self._vars[source] = var
            ctk.CTkOptionMenu(row, values=options, variable=var, width=300).pack(side="left", padx=6)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 16))
        ctk.CTkButton(footer, text="Cancel", width=100, command=self._cancel).pack(side="right", padx=(6, 0))
        ctk.CTkButton(footer, text="Use Mapping", width=120, command=self._accept).pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after(50, self.focus_force)

    def _adapt_template_mapping(self, mapping: dict[str, str]) -> dict[str, str]:
        """Apply a saved mapping to equivalent headers with case/spacing changes."""
        normalized = {normalize_header(source): target for source, target in mapping.items()}
        return {
            source: normalized[normalize_header(source)]
            for source in self._columns
            if normalize_header(source) in normalized
        }

    def _current_mapping(self) -> dict[str, str]:
        return {
            source: var.get()
            for source, var in self._vars.items()
            if var.get() != self.IGNORE
        }

    def _validate_mapping(self, mapping: dict[str, str], *, warn: bool = True) -> bool:
        if not mapping:
            if warn:
                messagebox.showwarning("Column mapping", "Map at least one column before continuing.", parent=self)
            return False
        targets = list(mapping.values())
        duplicates = sorted({target for target in targets if targets.count(target) > 1})
        if duplicates:
            if warn:
                messagebox.showwarning(
                    "Column mapping",
                    "Each target field can only be mapped once. Duplicate mapping: " + ", ".join(duplicates),
                    parent=self,
                )
            return False
        if self._required_any and not (set(targets) & self._required_any):
            if warn:
                messagebox.showwarning(
                    "Column mapping",
                    "Map at least one of: " + ", ".join(sorted(self._required_any)),
                    parent=self,
                )
            return False
        return True

    def _load_template(self) -> None:
        if self._template_service is None:
            return
        name = self.template_var.get()
        if name == self.AUTO:
            return
        template = self._template_service.get(name)
        if template is None:
            messagebox.showwarning("Mapping template", "The selected template no longer exists.", parent=self)
            return
        adapted = self._adapt_template_mapping(template.mapping)
        for source, var in self._vars.items():
            target = adapted.get(source, self.IGNORE)
            var.set(target if target in [self.IGNORE, *self._target_fields] else self.IGNORE)

    def _save_template(self) -> None:
        if self._template_service is None or not self._template_kind:
            return
        mapping = self._current_mapping()
        if not self._validate_mapping(mapping):
            return
        name = simpledialog.askstring("Save Mapping Template", "Template name:", parent=self)
        if not name:
            return
        try:
            self._template_service.save(
                name=name,
                kind=self._template_kind,
                mapping=mapping,
                source_columns=self._columns,
            )
        except Exception as exc:
            messagebox.showerror("Mapping template", str(exc), parent=self)
            return
        names = [self.AUTO, *[item.name for item in self._template_service.list(self._template_kind)]]
        self.template_menu.configure(values=names)
        self.template_var.set(name.strip())
        messagebox.showinfo("Mapping template", f"Saved template '{name.strip()}'.", parent=self)

    def _accept(self) -> None:
        mapping = self._current_mapping()
        if not self._validate_mapping(mapping):
            return
        self.result = mapping
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    def show(self) -> dict[str, str] | None:
        self.wait_window()
        return self.result
