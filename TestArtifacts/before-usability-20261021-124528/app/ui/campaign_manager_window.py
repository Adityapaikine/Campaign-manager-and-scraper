from __future__ import annotations

import json
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.core.campaign_manager import CampaignPackageImporter, CampaignProfileStore
from app.core.campaign_models import CampaignProfile, CampaignRule
from app.ai.campaign_reader import QwenCampaignReader


class CampaignManagerWindow(ctk.CTkToplevel):
    def __init__(self, master, *, on_activate=None, on_delete=None, ai_service=None, auto_ai_read: bool = False):
        super().__init__(master)
        self.title("Campaign / Validation Rule Manager")
        self.geometry("1180x780")
        self.minsize(900, 620)
        self.transient(master)
        self.resizable(True, True)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self.importer = CampaignPackageImporter()
        self.store = CampaignProfileStore()
        self.on_activate = on_activate
        self.on_delete = on_delete
        self.ai_service = ai_service
        self.auto_ai_read = bool(auto_ai_read)
        self.profile: CampaignProfile | None = None
        self.rule_widgets: list[tuple[CampaignRule, ctk.StringVar, ctk.StringVar]] = []
        self.file_role_widgets: list[tuple[object, ctk.StringVar]] = []

        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="Campaign Manager", font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=10
        )
        self.status_label = ctk.CTkLabel(header, text="Import a campaign folder or ZIP to begin.")
        self.status_label.grid(row=0, column=1, sticky="w", padx=10)
        ctk.CTkButton(header, text="Import ZIP", width=100, command=self._import_zip).grid(row=0, column=2, padx=4)
        ctk.CTkButton(header, text="Import Folder", width=110, command=self._import_folder).grid(row=0, column=3, padx=4)
        self.save_button = ctk.CTkButton(header, text="Save Profile", width=105, command=self.save_profile, state="disabled")
        self.save_button.grid(row=0, column=4, padx=4)
        self.activate_button = ctk.CTkButton(header, text="Activate Campaign", width=130, command=self.activate_profile, state="disabled")
        self.activate_button.grid(row=0, column=5, padx=(4, 12))

        selector = ctk.CTkFrame(self)
        selector.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        ctk.CTkLabel(selector, text="Saved Campaigns:").pack(side="left", padx=(12, 6), pady=6)
        self.campaign_var = ctk.StringVar(value="")
        self.campaign_menu = ctk.CTkOptionMenu(selector, variable=self.campaign_var, values=["No saved campaigns"], width=360)
        self.campaign_menu.pack(side="left", padx=4, pady=6)
        ctk.CTkButton(selector, text="Open", width=80, command=self._open_selected).pack(side="left", padx=4)
        self.delete_button = ctk.CTkButton(
            selector, text="Delete Campaign", width=120, command=self._delete_selected,
            fg_color="#C62828", hover_color="#8E0000"
        )
        self.delete_button.pack(side="left", padx=4)
        self.ai_enhance_button = ctk.CTkButton(
            selector, text="AI Enhance Specs", width=125, command=self._ai_enhance_rules,
            state="normal" if self.ai_service is not None else "disabled"
        )
        self.ai_enhance_button.pack(side="left", padx=4)
        self.active_label = ctk.CTkLabel(selector, text="Active: None")
        self.active_label.pack(side="right", padx=12)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.overview_tab = self.tabs.add("Overview")
        self.files_tab = self.tabs.add("Files")
        self.rules_tab = self.tabs.add("Extracted Rules")
        self.conflicts_tab = self.tabs.add("Conflicts")
        self.sources_tab = self.tabs.add("Sources")
        for tab in (self.overview_tab, self.files_tab, self.rules_tab, self.conflicts_tab, self.sources_tab):
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

        self.overview_scroll = ctk.CTkScrollableFrame(self.overview_tab)
        self.overview_scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.files_scroll = ctk.CTkScrollableFrame(self.files_tab)
        self.files_scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.rules_scroll = ctk.CTkScrollableFrame(self.rules_tab)
        self.rules_scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.conflicts_scroll = ctk.CTkScrollableFrame(self.conflicts_tab)
        self.conflicts_scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        self.sources_scroll = ctk.CTkScrollableFrame(self.sources_tab)
        self.sources_scroll.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        self._refresh_saved_campaigns()

    def _refresh_saved_campaigns(self) -> None:
        profiles = self.store.list()
        labels = [self._profile_label(p) for p in profiles] or ["No saved campaigns"]
        self.campaign_menu.configure(values=labels)
        if profiles:
            if self.campaign_var.get() not in labels:
                self.campaign_var.set(labels[0])
            self.delete_button.configure(state="normal")
        else:
            self.campaign_var.set("No saved campaigns")
            self.delete_button.configure(state="disabled")
        active = next((p for p in profiles if p.active), None)
        self.active_label.configure(text=f"Active: {active.campaign_id} — {active.campaign_name}" if active else "Active: None")

    @staticmethod
    def _profile_label(profile: CampaignProfile) -> str:
        return f"{profile.campaign_id} — {profile.campaign_name}"

    def _open_selected(self) -> None:
        value = self.campaign_var.get()
        if not value or value == "No saved campaigns":
            return
        campaign_id = value.split("—", 1)[0].strip()
        profile = self.store.get(campaign_id)
        if profile:
            self._set_profile(profile)

    def _delete_selected(self) -> None:
        value = self.campaign_var.get()
        if not value or value == "No saved campaigns":
            messagebox.showinfo("Delete Campaign", "Select a saved campaign first.", parent=self)
            return
        campaign_id = value.split("—", 1)[0].strip()
        profile = self.store.get(campaign_id)
        if profile is None:
            self._refresh_saved_campaigns()
            return

        active_note = (
            "\n\nThis campaign is currently ACTIVE. Its campaign-specific validation, TAL and "
            "suppression bindings will be deactivated."
            if profile.active else ""
        )
        confirmed = messagebox.askyesno(
            "Delete Campaign",
            f"Delete the saved campaign profile?\n\n"
            f"{profile.campaign_id} — {profile.campaign_name}"
            f"{active_note}\n\n"
            "The original campaign ZIP/folder will NOT be deleted.",
            parent=self,
        )
        if not confirmed:
            return

        was_active = self.store.delete(profile.campaign_id)
        if self.profile and self.profile.campaign_id == profile.campaign_id:
            self.profile = None
            self.save_button.configure(state="disabled")
            self.activate_button.configure(state="disabled")
            for frame in (self.overview_scroll, self.files_scroll, self.rules_scroll, self.conflicts_scroll, self.sources_scroll):
                self._clear(frame)
        self._refresh_saved_campaigns()
        if self.on_delete:
            try:
                self.on_delete(profile, was_active)
            except Exception as exc:
                messagebox.showerror("Delete Campaign", str(exc), parent=self)
                return
        self.status_label.configure(text=f"Deleted campaign profile {profile.campaign_id}.")
        messagebox.showinfo(
            "Delete Campaign",
            "Campaign profile deleted. Original source files were left untouched.",
            parent=self,
        )

    def _import_zip(self) -> None:
        path = filedialog.askopenfilename(
            title="Import Campaign ZIP",
            filetypes=[("Campaign ZIP", "*.zip"), ("All files", "*.*")],
            parent=self,
        )
        if path:
            self._start_import(path)

    def _import_folder(self) -> None:
        path = filedialog.askdirectory(title="Import Campaign Folder", parent=self)
        if path:
            self._start_import(path)

    def _start_import(self, path: str) -> None:
        self.status_label.configure(text=f"Reading campaign package: {Path(path).name} ...")
        self.save_button.configure(state="disabled")
        self.activate_button.configure(state="disabled")

        def worker():
            try:
                profile = self.importer.import_package(path)
                self.after(0, lambda: self._import_complete(profile))
            except Exception as exc:
                self.after(0, lambda: self._import_failed(str(exc)))

        threading.Thread(target=worker, daemon=True, name="campaign-import").start()

    def _import_complete(self, profile: CampaignProfile) -> None:
        self._set_profile(profile)
        self._refresh_saved_campaigns()
        self.status_label.configure(
            text=f"Read {len(profile.files)} files and extracted {len(profile.rules)} rule groups. Review before activation."
        )
        if self.auto_ai_read and self.ai_service is not None:
            self.after(200, self._ai_enhance_rules)

    def _import_failed(self, error: str) -> None:
        self.status_label.configure(text="Campaign import failed")
        messagebox.showerror("Campaign Import", error, parent=self)

    def _ai_enhance_rules(self) -> None:
        if not self.profile:
            messagebox.showinfo("AI Campaign Reader", "Open or import a campaign profile first.", parent=self)
            return
        if self.ai_service is None:
            messagebox.showinfo("AI Campaign Reader", "Local Qwen AI is not available.", parent=self)
            return
        self._apply_rule_edits()
        self.status_label.configure(text="Local Qwen is reviewing specification files...")
        self.ai_enhance_button.configure(state="disabled")
        profile = self.profile

        def worker():
            try:
                reader = QwenCampaignReader(self.ai_service)
                suggestions = reader.enhance_profile(profile)
                self.after(0, lambda: self._ai_enhance_complete(suggestions))
            except Exception as exc:
                self.after(0, lambda: self._ai_enhance_failed(str(exc)))

        threading.Thread(target=worker, daemon=True, name="campaign-ai-reader").start()

    def _ai_enhance_complete(self, suggestions: list[CampaignRule]) -> None:
        self.ai_enhance_button.configure(state="normal")
        if not self.profile:
            return
        existing = {(r.field, r.operator, json.dumps(r.value, ensure_ascii=False, sort_keys=True, default=str)) for r in self.profile.rules}
        added = 0
        for rule in suggestions:
            key = (rule.field, rule.operator, json.dumps(rule.value, ensure_ascii=False, sort_keys=True, default=str))
            if key in existing:
                continue
            self.profile.rules.append(rule)
            existing.add(key)
            added += 1
        self.profile.conflicts = self.importer._find_conflicts(self.profile.rules)
        self.store.save(self.profile)
        self._render_rules()
        self._render_conflicts()
        self._render_sources()
        self.status_label.configure(text=f"Qwen review complete: {added} additional rule(s) added for review.")
        self.tabs.set("Extracted Rules")

    def _ai_enhance_failed(self, error: str) -> None:
        self.ai_enhance_button.configure(state="normal")
        self.status_label.configure(text="Qwen campaign review failed")
        messagebox.showerror("AI Campaign Reader", error, parent=self)

    def _clear(self, frame) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def _set_profile(self, profile: CampaignProfile) -> None:
        self.profile = profile
        self.save_button.configure(state="normal")
        self.activate_button.configure(state="normal")
        self._render_overview()
        self._render_files()
        self._render_rules()
        self._render_conflicts()
        self._render_sources()
        self.tabs.set("Overview")

    def _render_overview(self) -> None:
        self._clear(self.overview_scroll)
        if not self.profile:
            return
        self.overview_scroll.grid_columnconfigure(1, weight=1)
        fields = [
            ("Campaign ID", self.profile.campaign_id),
            ("Campaign Name", self.profile.campaign_name),
            ("Source Folder", self.profile.source_root),
            ("Imported", self.profile.imported_at),
            ("Files", str(len(self.profile.files))),
            ("Extracted Rule Groups", str(len(self.profile.rules))),
            ("Conflicts", str(len(self.profile.conflicts))),
            ("Status", "ACTIVE" if self.profile.active else "Saved / not active"),
        ]
        for row, (label, value) in enumerate(fields):
            ctk.CTkLabel(self.overview_scroll, text=label, width=180, anchor="w", font=ctk.CTkFont(weight="bold")).grid(
                row=row, column=0, sticky="nw", padx=12, pady=7
            )
            ctk.CTkLabel(self.overview_scroll, text=value, anchor="w", justify="left", wraplength=760).grid(
                row=row, column=1, sticky="ew", padx=12, pady=7
            )
        guidance = (
            "Auto-reader rule: only explicit requirements are activated automatically. Rules marked 'Needs Review' "
            "are stored but not enforced until you confirm them. This prevents ambiguous source wording from silently "
            "changing lead qualification."
        )
        ctk.CTkLabel(self.overview_scroll, text=guidance, justify="left", wraplength=900).grid(
            row=len(fields), column=0, columnspan=2, sticky="ew", padx=12, pady=(18, 10)
        )
        if self.profile.notes:
            ctk.CTkLabel(self.overview_scroll, text="Reader Warnings", font=ctk.CTkFont(weight="bold")).grid(
                row=len(fields)+1, column=0, sticky="nw", padx=12, pady=8
            )
            ctk.CTkLabel(self.overview_scroll, text=self.profile.notes, justify="left", wraplength=760).grid(
                row=len(fields)+1, column=1, sticky="ew", padx=12, pady=8
            )

    def _render_files(self) -> None:
        self._clear(self.files_scroll)
        self.file_role_widgets.clear()
        if not self.profile:
            return
        headers = ["File", "Detected Role", "Records", "Confidence", "Notes"]
        for col, text in enumerate(headers):
            ctk.CTkLabel(self.files_scroll, text=text, font=ctk.CTkFont(weight="bold")).grid(row=0, column=col, sticky="w", padx=6, pady=6)
        self.files_scroll.grid_columnconfigure(0, weight=3)
        self.files_scroll.grid_columnconfigure(4, weight=2)
        roles = [
            "specification", "tal", "reference_tal", "client_suppression", "internal_suppression",
            "processed_suppression", "competitor_exclusion", "domain_suppression", "domain_limit", "unknown"
        ]
        for row, info in enumerate(self.profile.files, start=1):
            ctk.CTkLabel(self.files_scroll, text=info.relative_path, anchor="w", justify="left", wraplength=310).grid(
                row=row, column=0, sticky="nw", padx=6, pady=5
            )
            role_var = ctk.StringVar(value=info.role)
            ctk.CTkOptionMenu(self.files_scroll, variable=role_var, values=roles, width=180).grid(
                row=row, column=1, sticky="nw", padx=6, pady=5
            )
            self.file_role_widgets.append((info, role_var))
            ctk.CTkLabel(self.files_scroll, text=f"{info.record_count:,}").grid(row=row, column=2, sticky="nw", padx=6, pady=8)
            ctk.CTkLabel(self.files_scroll, text=f"{info.confidence*100:.0f}%").grid(row=row, column=3, sticky="nw", padx=6, pady=8)
            ctk.CTkLabel(self.files_scroll, text=info.notes or "-", anchor="w", justify="left", wraplength=310).grid(
                row=row, column=4, sticky="nw", padx=6, pady=5
            )

    def _render_rules(self) -> None:
        self._clear(self.rules_scroll)
        self.rule_widgets.clear()
        if not self.profile:
            return
        headers = ["Category / Rule", "Extracted Value", "Status", "Confidence", "Source"]
        for col, text in enumerate(headers):
            ctk.CTkLabel(self.rules_scroll, text=text, font=ctk.CTkFont(weight="bold")).grid(row=0, column=col, sticky="w", padx=6, pady=6)
        self.rules_scroll.grid_columnconfigure(1, weight=1)
        for row, rule in enumerate(self.profile.rules, start=1):
            ctk.CTkLabel(self.rules_scroll, text=f"{rule.category}\n{rule.field}", justify="left", width=170, anchor="w").grid(row=row, column=0, sticky="nw", padx=6, pady=5)
            display = "; ".join(str(v) for v in rule.value) if isinstance(rule.value, list) else str(rule.value)
            value_var = ctk.StringVar(value=display)
            ctk.CTkEntry(self.rules_scroll, textvariable=value_var, width=390).grid(row=row, column=1, sticky="ew", padx=6, pady=5)
            status_var = ctk.StringVar(value=rule.status)
            ctk.CTkOptionMenu(
                self.rules_scroll,
                variable=status_var,
                values=["Extracted", "Confirmed", "Needs Review", "Disabled"],
                width=120,
            ).grid(row=row, column=2, sticky="nw", padx=6, pady=5)
            ctk.CTkLabel(self.rules_scroll, text=f"{rule.confidence*100:.0f}%").grid(row=row, column=3, sticky="nw", padx=6, pady=8)
            source_text = ", ".join(sorted({source.file for source in rule.sources})) or rule.notes or "Derived"
            ctk.CTkLabel(self.rules_scroll, text=source_text, wraplength=260, justify="left", anchor="w").grid(row=row, column=4, sticky="nw", padx=6, pady=5)
            self.rule_widgets.append((rule, value_var, status_var))

    def _render_conflicts(self) -> None:
        self._clear(self.conflicts_scroll)
        if not self.profile:
            return
        if not self.profile.conflicts:
            ctk.CTkLabel(self.conflicts_scroll, text="No conflicting scalar requirements were detected.").pack(anchor="w", padx=12, pady=12)
            return
        for index, conflict in enumerate(self.profile.conflicts, start=1):
            card = ctk.CTkFrame(self.conflicts_scroll)
            card.pack(fill="x", padx=8, pady=6)
            ctk.CTkLabel(card, text=f"Conflict {index}: {conflict.rule_key}", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=12, pady=(10,4))
            ctk.CTkLabel(card, text="Values: " + " | ".join(str(v) for v in conflict.values), justify="left", wraplength=900).pack(anchor="w", padx=12, pady=3)
            ctk.CTkLabel(card, text="Sources: " + ", ".join(conflict.sources), justify="left", wraplength=900).pack(anchor="w", padx=12, pady=3)
            action = ctk.CTkFrame(card, fg_color="transparent")
            action.pack(fill="x", padx=12, pady=(5,10))
            selected = ctk.StringVar(value=str(conflict.resolved_value if conflict.resolved else conflict.values[0]))
            ctk.CTkOptionMenu(action, variable=selected, values=[str(v) for v in conflict.values], width=300).pack(side="left", padx=(0,8))
            ctk.CTkButton(
                action, text="Resolve", width=90,
                command=lambda c=conflict, v=selected: self._resolve_conflict(c, v.get())
            ).pack(side="left")
            if conflict.resolved:
                ctk.CTkLabel(action, text="Resolved").pack(side="left", padx=10)

    def _resolve_conflict(self, conflict, selected_text: str) -> None:
        if not self.profile:
            return
        chosen = next((value for value in conflict.values if str(value) == selected_text), selected_text)
        conflict.resolved_value = chosen
        conflict.resolved = True
        for rule in self.profile.rules:
            if rule.key != conflict.rule_key:
                continue
            if str(rule.value) == str(chosen):
                rule.status = "Confirmed"
            else:
                rule.status = "Disabled"
        self.store.save(self.profile)
        self._render_rules()
        self._render_conflicts()
        self.status_label.configure(text=f"Resolved rule conflict: {conflict.rule_key}")

    def _render_sources(self) -> None:
        self._clear(self.sources_scroll)
        if not self.profile:
            return
        for rule in self.profile.rules:
            card = ctk.CTkFrame(self.sources_scroll)
            card.pack(fill="x", padx=8, pady=5)
            ctk.CTkLabel(card, text=f"{rule.category} / {rule.field}", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=12, pady=(9, 3))
            if rule.sources:
                for source in rule.sources[:20]:
                    detail = source.file
                    if source.location:
                        detail += f" — {source.location}"
                    if source.excerpt:
                        detail += f" — {source.excerpt}"
                    ctk.CTkLabel(card, text=detail, justify="left", wraplength=950, anchor="w").pack(fill="x", padx=12, pady=2)
            else:
                ctk.CTkLabel(card, text=rule.notes or "Derived from campaign package name.", anchor="w").pack(fill="x", padx=12, pady=(2,9))

    def _apply_rule_edits(self) -> None:
        if not self.profile:
            return
        for info, role_var in self.file_role_widgets:
            info.role = role_var.get()
        for rule, value_var, status_var in self.rule_widgets:
            raw = value_var.get().strip()
            if isinstance(rule.value, list):
                rule.value = [item.strip() for item in raw.split(";") if item.strip()]
            else:
                rule.value = raw
            rule.status = status_var.get()

    def save_profile(self) -> None:
        if not self.profile:
            return
        self._apply_rule_edits()
        self.store.save(self.profile)
        self._refresh_saved_campaigns()
        self.status_label.configure(text=f"Saved campaign profile {self.profile.campaign_id}.")

    def activate_profile(self) -> None:
        if not self.profile:
            return
        self._apply_rule_edits()
        unresolved = [rule for rule in self.profile.rules if rule.status == "Needs Review"]
        if unresolved:
            proceed = messagebox.askyesno(
                "Activate Campaign",
                f"{len(unresolved)} rule(s) are still marked Needs Review. They will NOT be enforced.\n\nActivate the reviewed rules anyway?",
                parent=self,
            )
            if not proceed:
                return
        self.profile.active = True
        self.store.save(self.profile)
        self.store.activate(self.profile.campaign_id)
        self._refresh_saved_campaigns()
        if self.on_activate:
            try:
                self.on_activate(self.profile)
            except Exception as exc:
                messagebox.showerror("Activate Campaign", str(exc), parent=self)
                return
        self.status_label.configure(text=f"Activated {self.profile.campaign_id} — {self.profile.campaign_name}")
        messagebox.showinfo("Campaign Manager", "Campaign profile activated. Run VALIDATE to apply its active rules.", parent=self)
