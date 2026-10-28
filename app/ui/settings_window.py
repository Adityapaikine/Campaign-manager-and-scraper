from __future__ import annotations

import threading
import customtkinter as ctk
from tkinter import colorchooser, filedialog, messagebox

from app.services.search_provider import configured_provider_names
from app.ai.qwen_runtime import QwenRuntimeManager
from app.ui.theme import (
    APPEARANCE_MODES,
    COLOR_SCHEMES,
    DEFAULT_VALIDATION_COLORS,
    get_palette,
    normalize_hex_color,
)


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Settings")
        self.geometry("980x760")
        self.minsize(900, 700)
        self.transient(master)
        self.resizable(True, True)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        palette = get_palette(str(getattr(master, "color_scheme", "Excel Green")))

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Lead Manager Settings",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Organized by category so every option is easy to find and edit.",
            text_color=("gray35", "gray70"),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.tabview = ctk.CTkTabview(
            self,
            segmented_button_selected_color=palette["accent"],
            segmented_button_selected_hover_color=palette["hover"],
        )
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 8))

        self.appearance_content = self.tabview.add("Appearance")
        self.qwen_content = self.tabview.add("Local Qwen")
        self.validation_content = self.tabview.add("Validation")
        self.email_content = self.tabview.add("Email Discovery")
        self.performance_content = self.tabview.add("Performance & Recovery")
        self.production_content = self.tabview.add("Production & Export")

        self.appearance_content = self._make_scrollable_tab(self.appearance_content)
        self.qwen_content = self._make_scrollable_tab(self.qwen_content)
        self.validation_content = self._make_scrollable_tab(self.validation_content)
        self.email_content = self._make_scrollable_tab(self.email_content)
        self.performance_content = self._make_scrollable_tab(self.performance_content)
        self.production_content = self._make_scrollable_tab(self.production_content)

        self._build_variables(master)
        self._build_appearance_tab()
        self._build_qwen_tab()
        self._build_validation_tab()
        self._build_email_tab()
        self._build_performance_tab()
        self._build_production_tab()
        self._build_footer()

        self.after(50, lambda: self.tabview.set("Appearance"))

    def _make_scrollable_tab(self, tab):
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_columnconfigure(0, weight=1)
        frame = ctk.CTkScrollableFrame(tab, corner_radius=8)
        frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        frame.grid_columnconfigure(0, weight=1)
        return frame

    def _build_variables(self, master) -> None:
        self.appearance_mode_var = ctk.StringVar(value=str(getattr(master, "appearance_mode", "System")))
        self.color_scheme_var = ctk.StringVar(value=str(getattr(master, "color_scheme", "Excel Green")))
        self.qwen_enabled_var = ctk.BooleanVar(value=bool(getattr(master, "qwen_enabled", False)))
        self.qwen_auto_start_var = ctk.BooleanVar(value=bool(getattr(master, "qwen_auto_start", False)))
        self.qwen_folder_var = ctk.StringVar(value=str(getattr(master, "qwen_folder", "")))
        self.qwen_executable_var = ctk.StringVar(value=str(getattr(master, "qwen_executable", "")))
        self.qwen_model_var = ctk.StringVar(value=str(getattr(master, "qwen_model", "")))
        self.qwen_host_var = ctk.StringVar(value=str(getattr(master, "qwen_host", "127.0.0.1")))
        self.qwen_port_var = ctk.StringVar(value=str(int(getattr(master, "qwen_port", 8080))))
        self.qwen_extra_args_var = ctk.StringVar(value=str(getattr(master, "qwen_extra_args", "")))
        self.ai_features_enabled_var = ctk.BooleanVar(value=bool(getattr(master, "ai_features_enabled", True)))
        self.ai_start_on_demand_var = ctk.BooleanVar(value=bool(getattr(master, "ai_start_on_demand", True)))
        self.ai_cache_enabled_var = ctk.BooleanVar(value=bool(getattr(master, "ai_cache_enabled", True)))
        self.ai_cache_days_var = ctk.StringVar(value=str(int(getattr(master, "ai_cache_days", 180))))
        self.ai_min_confidence_var = ctk.StringVar(value=str(int(getattr(master, "ai_min_confidence", 75))))
        self.ai_max_prompt_chars_var = ctk.StringVar(value=str(int(getattr(master, "ai_max_prompt_chars", 12000))))
        self.ai_max_parallel_calls_var = ctk.StringVar(value=str(int(getattr(master, "ai_max_parallel_calls", 1))))
        self.ai_request_timeout_var = ctk.StringVar(value=str(int(getattr(master, "ai_request_timeout", 90))))
        self.qwen_stop_on_exit_var = ctk.BooleanVar(value=bool(getattr(master, "qwen_stop_on_exit", True)))
        self.ai_campaign_auto_read_var = ctk.BooleanVar(value=bool(getattr(master, "ai_campaign_auto_read", False)))
        self.require_tal_var = ctk.BooleanVar(value=bool(getattr(master, "require_tal_match", True)))
        self.enable_suppression_var = ctk.BooleanVar(value=bool(getattr(master, "enable_suppression", True)))
        self.enable_tal_fuzzy_var = ctk.BooleanVar(value=bool(getattr(master, "enable_tal_fuzzy_match", True)))
        self.enable_suppression_fuzzy_var = ctk.BooleanVar(value=bool(getattr(master, "enable_suppression_fuzzy_match", True)))
        self.outside_tal_color_var = ctk.StringVar(
            value=normalize_hex_color(
                str(getattr(master, "outside_tal_color", DEFAULT_VALIDATION_COLORS["outside_tal"])),
                DEFAULT_VALIDATION_COLORS["outside_tal"],
            )
        )
        self.suppression_match_color_var = ctk.StringVar(
            value=normalize_hex_color(
                str(getattr(master, "suppression_match_color", DEFAULT_VALIDATION_COLORS["suppressed"])),
                DEFAULT_VALIDATION_COLORS["suppressed"],
            )
        )

        self.minimum_confidence_var = ctk.StringVar(
            value=str(int(getattr(master, "minimum_email_confidence", 75)))
        )
        self.revalidate_existing_var = ctk.BooleanVar(
            value=bool(getattr(master, "revalidate_existing_emails", False))
        )
        self.enable_search_var = ctk.BooleanVar(
            value=bool(getattr(master, "email_search_enabled", False))
        )
        self.search_provider_var = ctk.StringVar(value=str(getattr(master, "search_provider_name", "Auto")))
        self.max_workers_var = ctk.StringVar(value=str(int(getattr(master, "email_search_max_workers", 4))))
        self.timeout_var = ctk.StringVar(value=str(int(getattr(master, "email_search_timeout", 15))))
        self.retries_var = ctk.StringVar(value=str(int(getattr(master, "email_search_retries", 2))))
        self.cache_days_var = ctk.StringVar(value=str(int(getattr(master, "email_discovery_cache_days", 30))))

        self.autosave_seconds_var = ctk.StringVar(
            value=str(int(getattr(master, "autosave_interval_seconds", 60)))
        )
        self.checkpoint_records_var = ctk.StringVar(
            value=str(int(getattr(master, "autosave_record_interval", 100)))
        )
        self.checkpoint_keep_var = ctk.StringVar(
            value=str(int(getattr(master, "checkpoint_keep_last", 5)))
        )

        self.export_valid_only_var = ctk.BooleanVar(
            value=bool(getattr(master, "export_valid_only", False))
        )
        self.include_validation_details_var = ctk.BooleanVar(
            value=bool(getattr(master, "include_validation_details", True))
        )
        self.default_export_folder_var = ctk.StringVar(
            value=str(getattr(master, "default_export_folder", ""))
        )

    def _section_frame(self, parent, title: str, subtitle: str | None = None) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", padx=12, pady=10)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            frame,
            text=title,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(14, 4))
        if subtitle:
            ctk.CTkLabel(
                frame,
                text=subtitle,
                wraplength=860,
                justify="left",
                text_color=("gray35", "gray70"),
            ).pack(anchor="w", padx=16, pady=(0, 10))
        return frame

    def _labeled_entry(self, parent, label: str, variable: ctk.StringVar, width: int = 120, suffix: str | None = None):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(row, text=label, width=240, anchor="w").pack(side="left")
        ctk.CTkEntry(row, textvariable=variable, width=width).pack(side="left", padx=(8, 4))
        if suffix:
            ctk.CTkLabel(row, text=suffix).pack(side="left")
        return row

    def _build_appearance_tab(self) -> None:
        frame = self._section_frame(
            self.appearance_content,
            "Application Appearance",
            "Choose the overall light/dark mode and the accent colour used for buttons and key actions.",
        )

        mode_row = ctk.CTkFrame(frame, fg_color="transparent")
        mode_row.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(mode_row, text="Appearance mode", width=240, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(
            mode_row,
            variable=self.appearance_mode_var,
            values=APPEARANCE_MODES,
            width=180,
        ).pack(side="left", padx=(8, 0))

        scheme_row = ctk.CTkFrame(frame, fg_color="transparent")
        scheme_row.pack(fill="x", padx=16, pady=8)
        ctk.CTkLabel(scheme_row, text="Colour scheme", width=240, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(
            scheme_row,
            variable=self.color_scheme_var,
            values=list(COLOR_SCHEMES),
            width=220,
            command=lambda _value: self._refresh_colour_preview(),
        ).pack(side="left", padx=(8, 0))

        preview = self._section_frame(self.appearance_content, "Colour Preview")
        self.preview_frame = ctk.CTkFrame(preview, fg_color="transparent")
        self.preview_frame.pack(fill="x", padx=16, pady=(0, 14))
        self.preview_swatch = ctk.CTkFrame(self.preview_frame, width=110, height=42, corner_radius=8)
        self.preview_swatch.pack(side="left", padx=(0, 12))
        self.preview_swatch.pack_propagate(False)
        self.preview_label = ctk.CTkLabel(self.preview_frame, text="")
        self.preview_label.pack(side="left")
        self._refresh_colour_preview()

        note = self._section_frame(
            self.appearance_content,
            "Theme Behaviour",
            "The selected theme is saved automatically and restored the next time the application starts.",
        )
        ctk.CTkLabel(
            note,
            text=(
                "Excel Green keeps the worksheet-style visual language. Professional Blue, Teal, Purple, Orange, "
                "and Slate are alternative accents for different teams or preferences. Validation status colours "
                "remain semantic so errors/warnings stay easy to recognise."
            ),
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _refresh_colour_preview(self) -> None:
        scheme = self.color_scheme_var.get()
        palette = COLOR_SCHEMES.get(scheme, COLOR_SCHEMES["Excel Green"])
        if hasattr(self, "preview_swatch"):
            self.preview_swatch.configure(fg_color=palette["accent"])
        if hasattr(self, "preview_label"):
            self.preview_label.configure(text=f"{scheme}  •  {palette['accent']}")

    def _build_qwen_tab(self) -> None:
        frame = self._section_frame(
            self.qwen_content,
            "Local Qwen Runtime",
            "Run Qwen locally with the application. Portable runtime files beside the app are preferred; otherwise choose a Qwen/LLAMA folder on this PC.",
        )
        ctk.CTkCheckBox(
            frame, text="Enable Local Qwen", variable=self.qwen_enabled_var
        ).pack(anchor="w", padx=16, pady=(6, 4))
        ctk.CTkCheckBox(
            frame, text="Automatically start Qwen when B2B Lead Manager opens", variable=self.qwen_auto_start_var
        ).pack(anchor="w", padx=16, pady=(4, 12))

        folder_row = ctk.CTkFrame(frame, fg_color="transparent")
        folder_row.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(folder_row, text="Qwen / LLAMA folder", width=190, anchor="w").pack(side="left")
        ctk.CTkEntry(folder_row, textvariable=self.qwen_folder_var).pack(side="left", fill="x", expand=True, padx=(8, 6))
        ctk.CTkButton(folder_row, text="Browse", width=84, command=self._browse_qwen_folder).pack(side="left")

        exe_row = ctk.CTkFrame(frame, fg_color="transparent")
        exe_row.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(exe_row, text="Executable (optional)", width=190, anchor="w").pack(side="left")
        ctk.CTkEntry(exe_row, textvariable=self.qwen_executable_var).pack(side="left", fill="x", expand=True, padx=(8, 0))

        model_row = ctk.CTkFrame(frame, fg_color="transparent")
        model_row.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(model_row, text="GGUF model (optional)", width=190, anchor="w").pack(side="left")
        ctk.CTkEntry(model_row, textvariable=self.qwen_model_var).pack(side="left", fill="x", expand=True, padx=(8, 0))

        server_row = ctk.CTkFrame(frame, fg_color="transparent")
        server_row.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(server_row, text="Host", width=190, anchor="w").pack(side="left")
        ctk.CTkEntry(server_row, textvariable=self.qwen_host_var, width=150).pack(side="left", padx=(8, 18))
        ctk.CTkLabel(server_row, text="Port").pack(side="left")
        ctk.CTkEntry(server_row, textvariable=self.qwen_port_var, width=90).pack(side="left", padx=(8, 0))

        args_row = ctk.CTkFrame(frame, fg_color="transparent")
        args_row.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(args_row, text="Extra launch arguments", width=190, anchor="w").pack(side="left")
        ctk.CTkEntry(args_row, textvariable=self.qwen_extra_args_var).pack(side="left", fill="x", expand=True, padx=(8, 0))

        ctk.CTkLabel(
            frame,
            text=(
                "Leave Executable and Model blank to auto-detect llama-server/llamafile and a Qwen .gguf model. "
                "For a portable deployment, place those files under runtime\\qwen beside the application."
            ),
            wraplength=840, justify="left", text_color=("gray35", "gray70")
        ).pack(anchor="w", padx=16, pady=(6, 12))

        ai_controls = self._section_frame(
            self.qwen_content,
            "Production AI Controls — Lightweight Mode",
            "These controls keep local AI optional, cached, and low-overhead. Recommended defaults are optimized for smooth startup and shutdown.",
        )
        ctk.CTkCheckBox(ai_controls, text="Enable Qwen AI features", variable=self.ai_features_enabled_var).pack(anchor="w", padx=16, pady=(6, 4))
        ctk.CTkCheckBox(ai_controls, text="Start Qwen only when an AI feature is used", variable=self.ai_start_on_demand_var).pack(anchor="w", padx=16, pady=4)
        ctk.CTkCheckBox(ai_controls, text="Cache AI responses locally to avoid repeated model calls", variable=self.ai_cache_enabled_var).pack(anchor="w", padx=16, pady=4)
        ctk.CTkCheckBox(ai_controls, text="Stop Qwen automatically when the application closes", variable=self.qwen_stop_on_exit_var).pack(anchor="w", padx=16, pady=4)
        ctk.CTkCheckBox(ai_controls, text="Automatically run Qwen requirement reader after campaign import", variable=self.ai_campaign_auto_read_var).pack(anchor="w", padx=16, pady=(4, 10))

        ai_grid = ctk.CTkFrame(ai_controls, fg_color="transparent")
        ai_grid.pack(fill="x", padx=16, pady=(0, 12))
        for col in range(4):
            ai_grid.grid_columnconfigure(col, weight=1)
        ctk.CTkLabel(ai_grid, text="AI minimum confidence (%)").grid(row=0, column=0, sticky="w", pady=5)
        ctk.CTkEntry(ai_grid, textvariable=self.ai_min_confidence_var, width=90).grid(row=0, column=1, sticky="w", pady=5)
        ctk.CTkLabel(ai_grid, text="AI cache days").grid(row=0, column=2, sticky="w", padx=(12, 0), pady=5)
        ctk.CTkEntry(ai_grid, textvariable=self.ai_cache_days_var, width=90).grid(row=0, column=3, sticky="w", pady=5)
        ctk.CTkLabel(ai_grid, text="Max prompt characters").grid(row=1, column=0, sticky="w", pady=5)
        ctk.CTkEntry(ai_grid, textvariable=self.ai_max_prompt_chars_var, width=100).grid(row=1, column=1, sticky="w", pady=5)
        ctk.CTkLabel(ai_grid, text="Parallel Qwen calls").grid(row=1, column=2, sticky="w", padx=(12, 0), pady=5)
        ctk.CTkEntry(ai_grid, textvariable=self.ai_max_parallel_calls_var, width=90).grid(row=1, column=3, sticky="w", pady=5)
        ctk.CTkLabel(ai_grid, text="AI request timeout (sec)").grid(row=2, column=0, sticky="w", pady=5)
        ctk.CTkEntry(ai_grid, textvariable=self.ai_request_timeout_var, width=100).grid(row=2, column=1, sticky="w", pady=5)
        ctk.CTkLabel(
            ai_controls,
            text="For most systems keep Parallel Qwen calls = 1. The app deduplicates values before AI processing and reuses SQLite cache/approved knowledge.",
            wraplength=840, justify="left", text_color=("gray35", "gray70")
        ).pack(anchor="w", padx=16, pady=(0, 12))

        runtime = self._section_frame(self.qwen_content, "Runtime Status")
        self.qwen_status_label = ctk.CTkLabel(runtime, text="Checking local Qwen...", anchor="w", justify="left", wraplength=840)
        self.qwen_status_label.pack(fill="x", padx=16, pady=(4, 8))
        self.qwen_detected_label = ctk.CTkLabel(runtime, text="", anchor="w", justify="left", wraplength=840)
        self.qwen_detected_label.pack(fill="x", padx=16, pady=(0, 10))
        actions = ctk.CTkFrame(runtime, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(actions, text="Refresh Status", width=110, command=self._refresh_qwen_settings_status).pack(side="left", padx=(0, 6))
        ctk.CTkButton(actions, text="Start Qwen", width=100, command=lambda: self._qwen_action("start")).pack(side="left", padx=6)
        ctk.CTkButton(actions, text="Stop Qwen", width=100, command=lambda: self._qwen_action("stop")).pack(side="left", padx=6)
        ctk.CTkButton(actions, text="Restart Qwen", width=110, command=lambda: self._qwen_action("restart")).pack(side="left", padx=6)
        self.after(100, self._refresh_qwen_settings_status)

    def _browse_qwen_folder(self) -> None:
        path = filedialog.askdirectory(title="Select Qwen / LLAMA Folder", parent=self)
        if path:
            self.qwen_folder_var.set(path)
            self.qwen_executable_var.set("")
            self.qwen_model_var.set("")
            self._refresh_qwen_settings_status()

    def _qwen_preview_manager(self) -> QwenRuntimeManager:
        try:
            port = int(self.qwen_port_var.get().strip())
        except ValueError:
            port = 8080
        return QwenRuntimeManager(
            folder=self.qwen_folder_var.get().strip(),
            executable=self.qwen_executable_var.get().strip(),
            model=self.qwen_model_var.get().strip(),
            host=self.qwen_host_var.get().strip() or "127.0.0.1",
            port=port,
            extra_args=self.qwen_extra_args_var.get().strip(),
        )

    def _refresh_qwen_settings_status(self) -> None:
        if getattr(self, "_qwen_settings_probe_pending", False):
            return
        self._qwen_settings_probe_pending = True
        self.qwen_status_label.configure(text="Checking local Qwen...")
        manager = self._qwen_preview_manager()

        def worker():
            try:
                info = manager.discover(probe=True)
                self.after(0, lambda: self._apply_qwen_settings_status(info))
            except Exception as exc:
                self.after(0, lambda: self._apply_qwen_settings_error(str(exc)))

        threading.Thread(target=worker, daemon=True, name="qwen-settings-status").start()

    def _apply_qwen_settings_status(self, info) -> None:
        self._qwen_settings_probe_pending = False
        state = "READY" if info.reachable else ("RUNNING / STARTING" if info.running else "STOPPED")
        self.qwen_status_label.configure(text=f"{state} — {info.message}")
        self.qwen_detected_label.configure(
            text=(
                f"Folder: {info.folder or 'Not detected'}\n"
                f"Executable: {info.executable or 'Not detected'}\n"
                f"Model: {info.model or 'Not detected'}\n"
                f"Endpoint: http://{info.host}:{info.port}"
            )
        )
        if info.folder and not self.qwen_folder_var.get().strip():
            self.qwen_folder_var.set(info.folder)
        if info.executable and not self.qwen_executable_var.get().strip():
            self.qwen_executable_var.set(info.executable)
        if info.model and not self.qwen_model_var.get().strip():
            self.qwen_model_var.set(info.model)

    def _apply_qwen_settings_error(self, error: str) -> None:
        self._qwen_settings_probe_pending = False
        self.qwen_status_label.configure(text=f"Qwen status error: {error}")

    def _apply_qwen_config(self) -> bool:
        try:
            port = int(self.qwen_port_var.get().strip())
        except ValueError:
            messagebox.showerror("Local Qwen", "Qwen port must be a whole number.", parent=self)
            return False
        if not 1 <= port <= 65535:
            messagebox.showerror("Local Qwen", "Qwen port must be between 1 and 65535.", parent=self)
            return False
        callback = getattr(self.master, "configure_qwen_runtime", None)
        if callback:
            callback(
                folder=self.qwen_folder_var.get().strip(),
                executable=self.qwen_executable_var.get().strip(),
                model=self.qwen_model_var.get().strip(),
                host=self.qwen_host_var.get().strip() or "127.0.0.1",
                port=port,
                extra_args=self.qwen_extra_args_var.get().strip(),
                enabled=self.qwen_enabled_var.get(),
                auto_start=self.qwen_auto_start_var.get(),
            )
        return True

    def _qwen_action(self, action: str) -> None:
        if not 0 <= ai_min_confidence <= 100:
            messagebox.showerror("Settings", "AI minimum confidence must be between 0 and 100.", parent=self)
            return
        if not 0 <= ai_cache_days <= 3650:
            messagebox.showerror("Settings", "AI cache days must be between 0 and 3650.", parent=self)
            return
        if not 2000 <= ai_max_prompt_chars <= 100000:
            messagebox.showerror("Settings", "Max prompt characters must be between 2,000 and 100,000.", parent=self)
            return
        if not 1 <= ai_max_parallel_calls <= 4:
            messagebox.showerror("Settings", "Parallel Qwen calls must be between 1 and 4. Use 1 for lightweight operation.", parent=self)
            return
        if not 10 <= ai_request_timeout <= 600:
            messagebox.showerror("Settings", "AI request timeout must be between 10 and 600 seconds.", parent=self)
            return

        if not self._apply_qwen_config():
            return
        ai_callback = getattr(self.master, "configure_ai_controls", None)
        if ai_callback:
            ai_callback(
                enabled=self.ai_features_enabled_var.get(),
                start_on_demand=self.ai_start_on_demand_var.get(),
                cache_enabled=self.ai_cache_enabled_var.get(),
                cache_days=ai_cache_days,
                minimum_confidence=ai_min_confidence,
                max_prompt_chars=ai_max_prompt_chars,
                max_parallel_calls=ai_max_parallel_calls,
                request_timeout=ai_request_timeout,
                stop_on_exit=self.qwen_stop_on_exit_var.get(),
                campaign_auto_read=self.ai_campaign_auto_read_var.get(),
            )
        if action == "start":
            self.qwen_enabled_var.set(True)
            self.master.qwen_enabled = True
            self.master.start_qwen()
        elif action == "stop":
            self.qwen_enabled_var.set(False)
            self.master.qwen_enabled = False
            self.master.stop_qwen()
        else:
            self.qwen_enabled_var.set(True)
            self.master.qwen_enabled = True
            self.master.restart_qwen()
        self.after(900, self._refresh_qwen_settings_status)

    def _build_validation_tab(self) -> None:
        frame = self._section_frame(
            self.validation_content,
            "Validation Rules",
            "Choose how lead records should be checked when you run Validate.",
        )
        ctk.CTkCheckBox(
            frame,
            text="Require TAL match when an Account/TAL list is loaded",
            variable=self.require_tal_var,
        ).pack(anchor="w", padx=16, pady=8)
        ctk.CTkCheckBox(
            frame,
            text="Enable suppression matching when a Suppression list is loaded",
            variable=self.enable_suppression_var,
        ).pack(anchor="w", padx=16, pady=(4, 8))
        ctk.CTkCheckBox(
            frame,
            text="Enable fuzzy matching for TAL company names (92%+ similarity → Possible Match)",
            variable=self.enable_tal_fuzzy_var,
        ).pack(anchor="w", padx=16, pady=(4, 8))
        ctk.CTkCheckBox(
            frame,
            text="Enable fuzzy matching for Suppression company/prospect names (review only)",
            variable=self.enable_suppression_fuzzy_var,
        ).pack(anchor="w", padx=16, pady=(4, 14))

        colours = self._section_frame(
            self.validation_content,
            "Validation Row Colours",
            "Rows outside the TAL are red by default. Suppression matches are orange by default. Choose any colour you prefer.",
        )
        self._build_validation_colour_row(
            colours,
            label="Outside TAL / TAL not mapped",
            variable=self.outside_tal_color_var,
            key="outside_tal",
        )
        self._build_validation_colour_row(
            colours,
            label="Suppression matched",
            variable=self.suppression_match_color_var,
            key="suppressed",
        )
        reset_row = ctk.CTkFrame(colours, fg_color="transparent")
        reset_row.pack(fill="x", padx=16, pady=(6, 14))
        ctk.CTkButton(
            reset_row,
            text="Reset Validation Colours",
            width=190,
            command=self._reset_validation_colours,
        ).pack(side="left")
        ctk.CTkLabel(
            reset_row,
            text="Colour changes apply after clicking Apply.",
            text_color=("gray35", "gray70"),
        ).pack(side="left", padx=(12, 0))

        tips = self._section_frame(
            self.validation_content,
            "Quick Guidance",
            "Recommended defaults for most production use.",
        )
        bullet_text = (
            "• Keep TAL matching enabled when the campaign must stay inside a target account list.\n"
            "• Keep suppression enabled to prevent previously blocked leads from being exported.\n"
            "• If you are only cleaning data without campaign restrictions, TAL can be turned off temporarily."
        )
        ctk.CTkLabel(tips, text=bullet_text, justify="left", wraplength=860).pack(
            anchor="w", padx=16, pady=(0, 14)
        )

    def _build_validation_colour_row(self, parent, *, label: str, variable: ctk.StringVar, key: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=7)
        ctk.CTkLabel(row, text=label, width=240, anchor="w").pack(side="left")
        swatch = ctk.CTkFrame(row, width=46, height=30, corner_radius=6, fg_color=variable.get())
        swatch.pack(side="left", padx=(8, 10))
        swatch.pack_propagate(False)
        entry = ctk.CTkEntry(row, textvariable=variable, width=110)
        entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row,
            text="Choose Colour",
            width=130,
            command=lambda: self._choose_validation_colour(variable, swatch),
        ).pack(side="left")
        variable.trace_add("write", lambda *_args, v=variable, s=swatch: self._update_colour_swatch(v, s))
        if not hasattr(self, "validation_colour_swatches"):
            self.validation_colour_swatches = {}
        self.validation_colour_swatches[key] = swatch

    def _choose_validation_colour(self, variable: ctk.StringVar, swatch: ctk.CTkFrame) -> None:
        _rgb, chosen = colorchooser.askcolor(color=variable.get(), parent=self, title="Choose validation colour")
        if chosen:
            variable.set(chosen.upper())
            swatch.configure(fg_color=chosen)

    def _update_colour_swatch(self, variable: ctk.StringVar, swatch: ctk.CTkFrame) -> None:
        value = variable.get().strip()
        if len(value) == 7 and value.startswith("#"):
            try:
                int(value[1:], 16)
                swatch.configure(fg_color=value)
            except ValueError:
                pass

    def _reset_validation_colours(self) -> None:
        self.outside_tal_color_var.set(DEFAULT_VALIDATION_COLORS["outside_tal"])
        self.suppression_match_color_var.set(DEFAULT_VALIDATION_COLORS["suppressed"])

    def _build_email_tab(self) -> None:
        frame = self._section_frame(
            self.email_content,
            "Email Discovery",
            "Configure confidence threshold, public web search, and discovery performance.",
        )
        self._labeled_entry(frame, "Minimum auto-fill confidence", self.minimum_confidence_var, width=90, suffix="%")
        ctk.CTkCheckBox(
            frame,
            text="Revalidate Existing Emails (otherwise existing values are preserved)",
            variable=self.revalidate_existing_var,
        ).pack(anchor="w", padx=16, pady=(8, 4))
        ctk.CTkCheckBox(
            frame,
            text="Enable public web search for missing/low-confidence company patterns",
            variable=self.enable_search_var,
        ).pack(anchor="w", padx=16, pady=(4, 10))

        provider_row = ctk.CTkFrame(frame, fg_color="transparent")
        provider_row.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(provider_row, text="Search provider:", width=240, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(
            provider_row,
            variable=self.search_provider_var,
            values=["Auto", "Brave", "Serper", "SerpAPI", "Disabled"],
            width=180,
        ).pack(side="left", padx=(8, 0))

        grid = ctk.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(8, 6))
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1)

        ctk.CTkLabel(grid, text="Maximum workers:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=6)
        ctk.CTkEntry(grid, textvariable=self.max_workers_var, width=90).grid(row=0, column=1, sticky="w", pady=6)
        ctk.CTkLabel(grid, text="Timeout (sec)").grid(row=0, column=2, sticky="w", padx=(12, 8), pady=6)
        ctk.CTkEntry(grid, textvariable=self.timeout_var, width=90).grid(row=0, column=3, sticky="w", pady=6)

        ctk.CTkLabel(grid, text="Retries").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        ctk.CTkEntry(grid, textvariable=self.retries_var, width=90).grid(row=1, column=1, sticky="w", pady=6)
        ctk.CTkLabel(grid, text="Discovery cache (days):").grid(row=1, column=2, sticky="w", padx=(12, 8), pady=6)
        ctk.CTkEntry(grid, textvariable=self.cache_days_var, width=90).grid(row=1, column=3, sticky="w", pady=6)

        configured = ", ".join(configured_provider_names())
        info = self._section_frame(
            self.email_content,
            "Provider Notes",
            None,
        )
        ctk.CTkLabel(
            info,
            text=(
                "API keys are read from the local .env file and are never shown here. "
                f"Currently configured providers detected: {configured}. Auto chooses the first configured provider."
            ),
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 8))
        ctk.CTkLabel(
            info,
            text=(
                "Search runs once per unique company domain and uses cache before sending any new request. "
                "Public evidence can support a naming pattern, but it does not prove a generated mailbox exists."
            ),
            wraplength=860,
            justify="left",
            text_color=("gray35", "gray70"),
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _build_performance_tab(self) -> None:
        frame = self._section_frame(
            self.performance_content,
            "Performance & Recovery — Phase 6",
            "Control autosave, checkpoints, and long-running job recovery.",
        )
        grid = ctk.CTkFrame(frame, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(4, 10))
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1)

        ctk.CTkLabel(grid, text="Autosave every (sec):").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=6)
        ctk.CTkEntry(grid, textvariable=self.autosave_seconds_var, width=100).grid(row=0, column=1, sticky="w", pady=6)
        ctk.CTkLabel(grid, text="Checkpoint every N records:").grid(row=0, column=2, sticky="w", padx=(12, 8), pady=6)
        ctk.CTkEntry(grid, textvariable=self.checkpoint_records_var, width=100).grid(row=0, column=3, sticky="w", pady=6)

        ctk.CTkLabel(grid, text="Keep recent checkpoints:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        ctk.CTkEntry(grid, textvariable=self.checkpoint_keep_var, width=100).grid(row=1, column=1, sticky="w", pady=6)

        ctk.CTkLabel(
            frame,
            text=(
                "Long validation and email jobs run outside the Tk UI thread. Use the main-screen Pause, Resume "
                "and Cancel controls during large jobs. Checkpoints are compressed and can be used to recover "
                "an interrupted session on the next launch."
            ),
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _build_production_tab(self) -> None:
        frame = self._section_frame(
            self.production_content,
            "Production & Export",
            "Choose default export behavior and QA output options.",
        )
        ctk.CTkCheckBox(
            frame,
            text="Export Valid / Valid - Email Generated records only by default",
            variable=self.export_valid_only_var,
        ).pack(anchor="w", padx=16, pady=8)
        ctk.CTkCheckBox(
            frame,
            text="Include Validation Details as a separate QA worksheet",
            variable=self.include_validation_details_var,
        ).pack(anchor="w", padx=16, pady=(4, 10))
        export_row = ctk.CTkFrame(frame, fg_color="transparent")
        export_row.pack(fill="x", padx=16, pady=(2, 12))
        export_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(export_row, text="Default export folder", width=240, anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(export_row, textvariable=self.default_export_folder_var).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        ctk.CTkLabel(
            frame,
            text=(
                "Tip: keep Validation Details enabled for QA review, while the main Lead Data sheet continues to use "
                "the fixed production schema."
            ),
            wraplength=860,
            justify="left",
            text_color=("gray35", "gray70"),
        ).pack(anchor="w", padx=16, pady=(0, 14))

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self)
        footer.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 18))
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            footer,
            text="Use the tabs above to review every option clearly. Appearance and other settings are saved when you click Apply.",
            text_color=("gray35", "gray70"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=12)
        actions = ctk.CTkFrame(footer, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e", padx=14, pady=10)
        ctk.CTkButton(actions, text="Cancel", width=110, command=self.destroy).pack(side="right", padx=(8, 0))
        palette = get_palette(self.color_scheme_var.get())
        ctk.CTkButton(
            actions, text="Apply", width=120, command=self._apply,
            fg_color=palette["accent"], hover_color=palette["hover"]
        ).pack(side="right")

    def _apply(self) -> None:
        try:
            minimum = int(self.minimum_confidence_var.get().strip())
            max_workers = int(self.max_workers_var.get().strip())
            timeout = int(self.timeout_var.get().strip())
            retries = int(self.retries_var.get().strip())
            cache_days = int(self.cache_days_var.get().strip())
            autosave_seconds = int(self.autosave_seconds_var.get().strip())
            checkpoint_records = int(self.checkpoint_records_var.get().strip())
            checkpoint_keep = int(self.checkpoint_keep_var.get().strip())
            ai_cache_days = int(self.ai_cache_days_var.get().strip())
            ai_min_confidence = int(self.ai_min_confidence_var.get().strip())
            ai_max_prompt_chars = int(self.ai_max_prompt_chars_var.get().strip())
            ai_max_parallel_calls = int(self.ai_max_parallel_calls_var.get().strip())
            ai_request_timeout = int(self.ai_request_timeout_var.get().strip())
        except ValueError:
            messagebox.showerror(
                "Settings",
                "Confidence, workers, timeout, retries, cache days and checkpoint settings must be whole numbers.",
                parent=self,
            )
            return
        for label, raw_value in (
            ("Outside TAL colour", self.outside_tal_color_var.get()),
            ("Suppression colour", self.suppression_match_color_var.get()),
        ):
            value = raw_value.strip()
            if not (len(value) == 7 and value.startswith("#")):
                messagebox.showerror("Settings", f"{label} must use a hex colour such as #FFC7CE.", parent=self)
                return
            try:
                int(value[1:], 16)
            except ValueError:
                messagebox.showerror("Settings", f"{label} must use a valid hex colour.", parent=self)
                return

        if not 0 <= minimum <= 100:
            messagebox.showerror("Settings", "Minimum confidence must be between 0 and 100.", parent=self)
            return
        if not 1 <= max_workers <= 16:
            messagebox.showerror("Settings", "Maximum workers must be between 1 and 16.", parent=self)
            return
        if not 2 <= timeout <= 120:
            messagebox.showerror("Settings", "Timeout must be between 2 and 120 seconds.", parent=self)
            return
        if not 0 <= retries <= 6:
            messagebox.showerror("Settings", "Retries must be between 0 and 6.", parent=self)
            return
        if not 0 <= cache_days <= 365:
            messagebox.showerror("Settings", "Discovery cache days must be between 0 and 365.", parent=self)
            return
        if not 15 <= autosave_seconds <= 3600:
            messagebox.showerror("Settings", "Autosave interval must be between 15 and 3600 seconds.", parent=self)
            return
        if not 10 <= checkpoint_records <= 5000:
            messagebox.showerror("Settings", "Checkpoint record interval must be between 10 and 5000.", parent=self)
            return
        if not 2 <= checkpoint_keep <= 20:
            messagebox.showerror("Settings", "Recent checkpoints to keep must be between 2 and 20.", parent=self)
            return

        if not self._apply_qwen_config():
            return

        callback7 = getattr(self.master, "apply_phase7_settings", None)
        if callback7:
            callback7(
                require_tal_match=self.require_tal_var.get(),
                enable_suppression=self.enable_suppression_var.get(),
                enable_tal_fuzzy_match=self.enable_tal_fuzzy_var.get(),
                enable_suppression_fuzzy_match=self.enable_suppression_fuzzy_var.get(),
                minimum_email_confidence=minimum,
                revalidate_existing_emails=self.revalidate_existing_var.get(),
                email_search_enabled=self.enable_search_var.get(),
                search_provider_name=self.search_provider_var.get(),
                email_search_max_workers=max_workers,
                email_search_timeout=timeout,
                email_search_retries=retries,
                email_discovery_cache_days=cache_days,
                autosave_interval_seconds=autosave_seconds,
                autosave_record_interval=checkpoint_records,
                checkpoint_keep_last=checkpoint_keep,
                export_valid_only=self.export_valid_only_var.get(),
                include_validation_details=self.include_validation_details_var.get(),
                default_export_folder=self.default_export_folder_var.get().strip(),
                appearance_mode=self.appearance_mode_var.get(),
                color_scheme=self.color_scheme_var.get(),
                outside_tal_color=self.outside_tal_color_var.get().strip().upper(),
                suppression_match_color=self.suppression_match_color_var.get().strip().upper(),
            )
            self.destroy()
            return

        callback6 = getattr(self.master, "apply_phase6_settings", None)
        if callback6:
            callback6(
                require_tal_match=self.require_tal_var.get(),
                enable_suppression=self.enable_suppression_var.get(),
                minimum_email_confidence=minimum,
                revalidate_existing_emails=self.revalidate_existing_var.get(),
                email_search_enabled=self.enable_search_var.get(),
                search_provider_name=self.search_provider_var.get(),
                email_search_max_workers=max_workers,
                email_search_timeout=timeout,
                email_search_retries=retries,
                email_discovery_cache_days=cache_days,
                autosave_interval_seconds=autosave_seconds,
                autosave_record_interval=checkpoint_records,
                checkpoint_keep_last=checkpoint_keep,
            )
            self.destroy()
            return

        callback = getattr(self.master, "apply_phase5_settings", None)
        if callback:
            callback(
                require_tal_match=self.require_tal_var.get(),
                enable_suppression=self.enable_suppression_var.get(),
                minimum_email_confidence=minimum,
                revalidate_existing_emails=self.revalidate_existing_var.get(),
                email_search_enabled=self.enable_search_var.get(),
                search_provider_name=self.search_provider_var.get(),
                email_search_max_workers=max_workers,
                email_search_timeout=timeout,
                email_search_retries=retries,
                email_discovery_cache_days=cache_days,
            )
        else:
            legacy = getattr(self.master, "apply_phase4_settings", None)
            if legacy:
                legacy(
                    require_tal_match=self.require_tal_var.get(),
                    enable_suppression=self.enable_suppression_var.get(),
                    minimum_email_confidence=minimum,
                    revalidate_existing_emails=self.revalidate_existing_var.get(),
                )
        self.destroy()
