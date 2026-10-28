from __future__ import annotations

import customtkinter as ctk


SHORTCUT_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "File & application",
        (
            ("Ctrl+N", "New lead session"),
            ("Ctrl+O", "Import Excel / CSV leads"),
            ("Ctrl+S", "Quick Save"),
            ("Ctrl+Shift+S / F12", "Export / Save As"),
            ("Ctrl+W", "Close Lead Manager"),
            ("Ctrl+Q", "Run lead validation (Quick Analysis equivalent)"),
            ("F1", "Open this shortcut reference"),
        ),
    ),
    (
        "Clipboard & editing",
        (
            ("Ctrl+C / Ctrl+Insert", "Copy selected cells"),
            ("Ctrl+X / Shift+Delete", "Cut selected cells"),
            ("Ctrl+V / Shift+Insert", "Paste into active cell/range"),
            ("Ctrl+Alt+V", "Paste Special - values (data grid stores values only)"),
            ("Delete", "Clear selected cell contents"),
            ("F2 / Backspace / Double-click", "Edit active cell"),
            ("Ctrl+Z", "Undo"),
            ("Ctrl+Y / Ctrl+Shift+Z", "Redo"),
            ("Ctrl+Enter", "Fill selected cells with active-cell value"),
            ("Ctrl+D", "Fill Down"),
            ("Ctrl+R", "Fill Right"),
            ("Ctrl+'", "Copy value from cell above"),
            ("Ctrl+;", "Insert current date"),
            ("Ctrl+Shift+:", "Insert current time"),
        ),
    ),
    (
        "Navigation & selection",
        (
            ("Arrow keys", "Move the active-cell pointer"),
            ("Shift+Arrow", "Extend the selection one cell"),
            ("Ctrl+Arrow", "Jump to edge of the current data region"),
            ("Ctrl+Shift+Arrow", "Extend selection to data-region edge"),
            ("Home", "Move to first column in current row"),
            ("Ctrl+Home", "Move to A1"),
            ("Ctrl+End", "Move to last used cell"),
            ("Page Up / Page Down", "Move one worksheet screen vertically"),
            ("Alt+Page Up / Alt+Page Down", "Move one worksheet screen horizontally"),
            ("Tab / Shift+Tab", "Move right / left"),
            ("Enter / Shift+Enter", "Move down / up"),
            ("Ctrl+Space", "Select current column"),
            ("Shift+Space", "Select current row"),
            ("Ctrl+A / Ctrl+Shift+Space", "Select worksheet"),
            ("Ctrl+Shift+*", "Select current contiguous region"),
            ("Ctrl+Click", "Add non-contiguous selections"),
        ),
    ),
    (
        "Find, Go To & filters",
        (
            ("Ctrl+F", "Find in worksheet"),
            ("Ctrl+H", "Find and Replace"),
            ("Ctrl+G / F5", "Go To a cell using the Name Box"),
            ("Alt+Down", "Open filter menu for active column"),
            ("Ctrl+Shift+L", "Open active filter / clear active filters"),
            ("Ctrl+Shift+F", "Focus Lead Manager global search"),
        ),
    ),
    (
        "Rows & columns",
        (
            ("Ctrl+9", "Hide selected row(s)"),
            ("Ctrl+Shift+9", "Show all hidden rows"),
            ("Ctrl+0", "Hide selected column(s)"),
            ("Ctrl+Shift+0", "Show all hidden columns"),
            ("Mouse drag on header/index", "Resize columns / rows"),
            ("Double-click divider", "Auto-size column / row"),
        ),
    ),
)


class ShortcutHelpWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Excel-style Keyboard Shortcuts")
        self.geometry("760x720")
        self.minsize(650, 520)
        self.transient(master)

        ctk.CTkLabel(
            self,
            text="Excel-style Keyboard Shortcuts",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            self,
            text=(
                "These are the Excel for Windows shortcuts that map meaningfully to the Lead Manager grid. "
                "Excel-only commands for formulas, charts, macros, PivotTables, workbook sheets, Ribbon formatting, "
                "and other unsupported Excel objects are intentionally not remapped."
            ),
            wraplength=710,
            justify="left",
            text_color=("gray30", "gray75"),
        ).pack(anchor="w", padx=18, pady=(0, 10))

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        scroll.grid_columnconfigure(1, weight=1)

        row = 0
        for group, shortcuts in SHORTCUT_GROUPS:
            ctk.CTkLabel(
                scroll,
                text=group,
                font=ctk.CTkFont(size=15, weight="bold"),
            ).grid(row=row, column=0, columnspan=2, sticky="w", padx=8, pady=(12 if row else 4, 5))
            row += 1
            for keys, description in shortcuts:
                ctk.CTkLabel(
                    scroll,
                    text=keys,
                    width=190,
                    anchor="w",
                    font=ctk.CTkFont(family="Consolas", weight="bold"),
                ).grid(row=row, column=0, sticky="nw", padx=(8, 12), pady=3)
                ctk.CTkLabel(
                    scroll,
                    text=description,
                    anchor="w",
                    justify="left",
                    wraplength=460,
                ).grid(row=row, column=1, sticky="nw", padx=(0, 8), pady=3)
                row += 1

        ctk.CTkButton(self, text="Close", width=100, command=self.destroy).pack(pady=(0, 14))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(80, self.focus_force)
