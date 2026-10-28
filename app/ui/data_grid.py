from __future__ import annotations

import re
import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Callable

from tksheet import Sheet

from app.constants import STANDARD_HEADERS


GridChangeCallback = Callable[[list[list[str]], list[int | None], str], None]
FilterRequestCallback = Callable[[int, int, int], None]


class DataGrid(ttk.Frame):
    """Excel-style lead worksheet backed by tksheet.

    The table keeps the application's fixed 42-column schema while providing
    familiar spreadsheet interaction: active-cell pointer, F2/double-click edit,
    Tab/Enter movement, name box, multi-range selection, clipboard,
    fill-down/fill-right and per-column filter launchers.
    """

    MIN_VISIBLE_ROWS = 40
    EXTRA_BLANK_ROWS = 12
    FILTER_HITBOX_PIXELS = 28

    EXCEL_GREEN = "#217346"
    EXCEL_LIGHT_GREEN = "#E2F0D9"
    EXCEL_HEADER = "#F3F3F3"
    EXCEL_GRID = "#D9D9D9"

    DEFAULT_STATE_COLORS = {
        "Valid": "#e8f5e9",
        "Valid - Email Generated": "#d9f2e3",
        "Warning": "#fff8e1",
        "Invalid": "#ffebee",
        "Suppressed": "#FFD59A",
        "Outside TAL": "#FFC7CE",
        "Duplicate": "#ede7f6",
        "Manual Review": "#e3f2fd",
        "Email Found": "#e0f2f1",
        "Email Not Found": "#f5f5f5",
    }

    def __init__(
        self,
        master: tk.Misc,
        on_grid_change: GridChangeCallback,
        on_paste: Callable[[], None] | None = None,
        on_filter_request: FilterRequestCallback | None = None,
    ) -> None:
        super().__init__(master)
        self.on_grid_change = on_grid_change
        self.on_paste = on_paste
        self.on_filter_request = on_filter_request
        self._row_ids: list[int | None] = []
        self._loading = False
        self._filtered_columns: set[int] = set()
        self.state_colors = dict(self.DEFAULT_STATE_COLORS)

        self._build_formula_bar()

        self.sheet = Sheet(
            self,
            headers=self._header_labels(),
            data=[],
            show_header=True,
            show_row_index=True,
            show_x_scrollbar=True,
            show_y_scrollbar=True,
            default_row_index="numbers",
            default_column_width=155,
            default_row_height=25,
            default_header_height=34,
            paste_can_expand_x=False,
            paste_can_expand_y=True,
            show_selected_cells_border=True,
            show_vertical_grid=True,
            show_horizontal_grid=True,
            horizontal_grid_to_end_of_window=True,
            vertical_grid_to_end_of_window=True,
            edit_cell_tab="right",
            edit_cell_return="down",
            rounded_boxes=False,
            auto_resize_row_index=True,
            startup_select=(0, 0, "cells"),
            table_bg="#FFFFFF",
            table_grid_fg=self.EXCEL_GRID,
            table_fg="#111111",
            table_selected_cells_border_fg=self.EXCEL_GREEN,
            table_selected_box_cells_fg=self.EXCEL_GREEN,
            table_selected_box_rows_fg=self.EXCEL_GREEN,
            table_selected_box_columns_fg=self.EXCEL_GREEN,
            table_selected_cells_bg="#F4FBF6",
            table_selected_cells_fg="#111111",
            table_selected_rows_border_fg=self.EXCEL_GREEN,
            table_selected_rows_bg="#F4FBF6",
            table_selected_columns_border_fg=self.EXCEL_GREEN,
            table_selected_columns_bg="#F4FBF6",
            header_bg=self.EXCEL_HEADER,
            header_grid_fg="#C8C8C8",
            header_border_fg="#C8C8C8",
            header_fg="#111111",
            header_selected_columns_bg="#DDEBDD",
            header_selected_columns_fg="#111111",
            index_bg=self.EXCEL_HEADER,
            index_grid_fg="#C8C8C8",
            index_border_fg="#C8C8C8",
            index_fg="#111111",
            index_selected_rows_bg="#DDEBDD",
            index_selected_rows_fg="#111111",
            top_left_bg=self.EXCEL_HEADER,
            top_left_fg="#777777",
        )
        self.sheet.pack(fill="both", expand=True)

        # Enable interactions without allowing the fixed standard columns to be
        # inserted, removed, renamed or dragged out of order.
        self.sheet.enable_bindings(
            "single_select",
            "drag_select",
            "column_select",
            "row_select",
            "column_width_resize",
            "double_click_column_resize",
            "row_height_resize",
            "double_click_row_resize",
            "arrowkeys",
            "right_click_popup_menu",
            "rc_select",
            "copy",
            "cut",
            "paste",
            "delete",
            "undo",
            "edit_cell",
            "find",
        )
        self.sheet.enable_bindings("ctrl_select")

        # Preserve the fixed export/header schema: headers are display-only.
        try:
            self.sheet.readonly(self.sheet.span(None, header=True, table=False))
        except Exception:
            pass

        self.sheet.edit_validation(self._validate_edit)
        self.sheet.extra_bindings("all_modified_events", self._sheet_modified)
        self.sheet.extra_bindings("all_select_events", self._selection_changed)
        self.sheet.extra_bindings("end_edit_cell", self._end_edit_cell)

        # Excel-style worksheet keyboard layer. Built-in tksheet bindings handle
        # the basic clipboard/edit commands; this adds the wider set of Excel
        # navigation, selection and data-entry accelerators that are meaningful
        # for this fixed-schema lead worksheet.
        self._register_excel_shortcuts()

        # Filter launcher: left-click the small right-edge area of a header, or
        # right-click a header. The displayed ▾ mirrors Excel's AutoFilter cue.
        self.sheet.bind("<ButtonRelease-1>", self._header_arrow_click, add="+")
        self.sheet.bind("<Button-3>", self._header_right_click, add="+")

        try:
            self.sheet.popup_menu_add_command(
                label="Filter this column...",
                func=lambda _event=None: self._open_active_filter(),
            )
            self.sheet.popup_menu_add_command(
                label="Fill Down (Ctrl+D)",
                func=lambda _event=None: self._fill_down(),
            )
            self.sheet.popup_menu_add_command(
                label="Fill Right (Ctrl+R)",
                func=lambda _event=None: self._fill_right(),
            )
            self.sheet.popup_menu_add_command(
                label="Delete selected row(s)",
                func=lambda _event=None: self.event_generate("<<DeleteRows>>"),
            )
        except Exception:
            pass

        self.after_idle(self._sync_formula_bar)

    def _bind_shortcut(self, sequence: str, callback: Callable[[tk.Event | None], str | None]) -> None:
        """Bind a key sequence to the sheet without replacing tksheet defaults."""
        try:
            self.sheet.bind(sequence, callback, add="+")
        except Exception:
            # A few keysyms vary between Tk builds. A missing alias should not
            # prevent the application from starting.
            pass

    def _emit(self, virtual_event: str) -> str:
        self.event_generate(virtual_event)
        return "break"

    def _register_excel_shortcuts(self) -> None:
        # Editing / clipboard aliases.
        self._bind_shortcut("<F2>", self._open_editor)
        self._bind_shortcut("<BackSpace>", self._open_editor)
        self._bind_shortcut("<Control-Insert>", lambda _e: self._copy_alias())
        self._bind_shortcut("<Shift-Insert>", lambda _e: self._paste_alias())
        self._bind_shortcut("<Shift-Delete>", lambda _e: self._cut_alias())
        self._bind_shortcut("<Control-Alt-v>", lambda _e: self._paste_special_values())
        self._bind_shortcut("<Control-Alt-V>", lambda _e: self._paste_special_values())
        self._bind_shortcut("<Control-y>", lambda _e: self._redo_alias())
        self._bind_shortcut("<Control-Y>", lambda _e: self._redo_alias())
        self._bind_shortcut("<Control-Shift-z>", lambda _e: self._redo_alias())
        self._bind_shortcut("<Control-Shift-Z>", lambda _e: self._redo_alias())
        self._bind_shortcut("<Control-Return>", self._fill_selection_with_active)
        self._bind_shortcut("<Control-KP_Enter>", self._fill_selection_with_active)
        self._bind_shortcut("<Control-d>", self._fill_down)
        self._bind_shortcut("<Control-D>", self._fill_down)
        self._bind_shortcut("<Control-r>", self._fill_right)
        self._bind_shortcut("<Control-R>", self._fill_right)
        self._bind_shortcut("<Control-apostrophe>", self._copy_from_above)
        self._bind_shortcut("<Control-Shift-quotedbl>", self._copy_from_above)
        self._bind_shortcut("<Control-semicolon>", self._insert_current_date)
        self._bind_shortcut("<Control-Shift-semicolon>", self._insert_current_time)
        self._bind_shortcut("<Control-colon>", self._insert_current_time)

        # Cell movement / selection.
        self._bind_shortcut("<Home>", self._move_home)
        self._bind_shortcut("<Control-Home>", self._move_sheet_home)
        self._bind_shortcut("<Control-End>", self._move_last_used)
        self._bind_shortcut("<Control-Left>", lambda _e: self._jump_data_edge(0, -1, False))
        self._bind_shortcut("<Control-Right>", lambda _e: self._jump_data_edge(0, 1, False))
        self._bind_shortcut("<Control-Up>", lambda _e: self._jump_data_edge(-1, 0, False))
        self._bind_shortcut("<Control-Down>", lambda _e: self._jump_data_edge(1, 0, False))
        self._bind_shortcut("<Control-Shift-Left>", lambda _e: self._jump_data_edge(0, -1, True))
        self._bind_shortcut("<Control-Shift-Right>", lambda _e: self._jump_data_edge(0, 1, True))
        self._bind_shortcut("<Control-Shift-Up>", lambda _e: self._jump_data_edge(-1, 0, True))
        self._bind_shortcut("<Control-Shift-Down>", lambda _e: self._jump_data_edge(1, 0, True))
        self._bind_shortcut("<Control-space>", self._select_current_column)
        self._bind_shortcut("<Shift-space>", self._select_current_row)
        self._bind_shortcut("<Control-Shift-space>", self._select_all_cells)
        self._bind_shortcut("<Control-a>", self._select_all_cells)
        self._bind_shortcut("<Control-A>", self._select_all_cells)
        self._bind_shortcut("<Control-Shift-asterisk>", self._select_current_region)
        self._bind_shortcut("<Control-Shift-KP_Multiply>", self._select_current_region)
        self._bind_shortcut("<Shift-Return>", lambda _e: self._move_relative(-1, 0))
        self._bind_shortcut("<Shift-KP_Enter>", lambda _e: self._move_relative(-1, 0))
        self._bind_shortcut("<Shift-Tab>", lambda _e: self._move_relative(0, -1))
        self._bind_shortcut("<Alt-Prior>", lambda _e: self._horizontal_page(-1))
        self._bind_shortcut("<Alt-Next>", lambda _e: self._horizontal_page(1))

        # Find / Go To / Filter.
        self._bind_shortcut("<F5>", self._focus_name_box)
        self._bind_shortcut("<Control-g>", self._focus_name_box)
        self._bind_shortcut("<Control-G>", self._focus_name_box)
        self._bind_shortcut("<Control-h>", self._open_replace_dialog)
        self._bind_shortcut("<Control-H>", self._open_replace_dialog)
        self._bind_shortcut("<Alt-Down>", self._open_active_filter)
        self._bind_shortcut("<Alt-KeyPress-Down>", self._open_active_filter)
        self._bind_shortcut("<Control-Shift-l>", lambda _e: self._emit("<<ToggleFilters>>"))
        self._bind_shortcut("<Control-Shift-L>", lambda _e: self._emit("<<ToggleFilters>>"))

        # Row / column visibility.
        self._bind_shortcut("<Control-Key-9>", self._hide_selected_rows)
        self._bind_shortcut("<Control-Key-0>", self._hide_selected_columns)
        self._bind_shortcut("<Control-Shift-Key-9>", self._show_all_rows)
        self._bind_shortcut("<Control-Shift-Key-0>", self._show_all_columns)

        # Workbook-like application commands mapped to the equivalent Lead Manager action.
        self._bind_shortcut("<Control-n>", lambda _e: self._emit("<<NewSession>>"))
        self._bind_shortcut("<Control-N>", lambda _e: self._emit("<<NewSession>>"))
        self._bind_shortcut("<Control-o>", lambda _e: self._emit("<<ImportLeads>>"))
        self._bind_shortcut("<Control-O>", lambda _e: self._emit("<<ImportLeads>>"))
        self._bind_shortcut("<Control-s>", lambda _e: self._emit("<<QuickSave>>"))
        self._bind_shortcut("<Control-S>", lambda _e: self._emit("<<QuickSave>>"))
        self._bind_shortcut("<Control-Shift-s>", lambda _e: self._emit("<<ExportData>>"))
        self._bind_shortcut("<Control-Shift-S>", lambda _e: self._emit("<<ExportData>>"))
        self._bind_shortcut("<F12>", lambda _e: self._emit("<<ExportData>>"))
        self._bind_shortcut("<Control-w>", lambda _e: self._emit("<<CloseWindow>>"))
        self._bind_shortcut("<Control-W>", lambda _e: self._emit("<<CloseWindow>>"))
        self._bind_shortcut("<Control-q>", lambda _e: self._emit("<<ValidateRows>>"))
        self._bind_shortcut("<Control-Q>", lambda _e: self._emit("<<ValidateRows>>"))
        self._bind_shortcut("<F1>", lambda _e: self._emit("<<ShortcutHelp>>"))

        # App-specific convenience shortcut retained from the previous build.
        self._bind_shortcut("<Control-Shift-f>", lambda _e: self._emit("<<FocusSearch>>"))
        self._bind_shortcut("<Control-Shift-F>", lambda _e: self._emit("<<FocusSearch>>"))

    def _copy_alias(self) -> str:
        self.sheet.copy()
        return "break"

    def _paste_alias(self) -> str:
        self.sheet.paste()
        return "break"

    def _cut_alias(self) -> str:
        self.sheet.cut()
        return "break"

    def _paste_special_values(self) -> str:
        # The Lead Manager stores plain cell values only, so Paste Special ->
        # Values is intentionally equivalent to normal paste.
        self.sheet.paste()
        return "break"

    def _redo_alias(self) -> str:
        try:
            self.sheet.redo()
        except Exception:
            pass
        return "break"

    @staticmethod
    def _is_blank(value: object) -> bool:
        return value is None or str(value).strip() in {"", "-"}

    def _current_cell(self) -> tuple[int, int] | None:
        selected = self.sheet.get_currently_selected()
        if not selected or not isinstance(selected.row, int) or not isinstance(selected.column, int):
            return None
        return selected.row, selected.column

    def _move_relative(self, dr: int, dc: int) -> str:
        current = self._current_cell()
        if current is None:
            return "break"
        row, col = current
        max_row = max(0, len(self._row_ids) - 1)
        row = max(0, min(max_row, row + dr))
        col = max(0, min(len(STANDARD_HEADERS) - 1, col + dc))
        self.select_cell(row, col)
        self.focus_canvas()
        return "break"

    def _move_home(self, _event: tk.Event | None = None) -> str:
        current = self._current_cell()
        if current is not None:
            self.select_cell(current[0], 0)
            self.focus_canvas()
        return "break"

    def _move_sheet_home(self, _event: tk.Event | None = None) -> str:
        self.select_cell(0, 0)
        self.focus_canvas()
        return "break"

    def _last_used_cell(self) -> tuple[int, int]:
        matrix = self._matrix()
        last_row = 0
        last_col = 0
        for row_index, row in enumerate(matrix):
            for col_index, value in enumerate(row[: len(STANDARD_HEADERS)]):
                if not self._is_blank(value):
                    last_row = max(last_row, row_index)
                    last_col = max(last_col, col_index)
        return last_row, last_col

    def _move_last_used(self, _event: tk.Event | None = None) -> str:
        row, col = self._last_used_cell()
        self.select_cell(row, col)
        self.focus_canvas()
        return "break"

    def _edge_target(self, row: int, col: int, dr: int, dc: int) -> tuple[int, int]:
        matrix = self._matrix()
        max_row = max(0, len(matrix) - 1)
        max_col = len(STANDARD_HEADERS) - 1
        current_blank = self._is_blank(matrix[row][col])
        r, c = row, col

        while True:
            nr, nc = r + dr, c + dc
            if not (0 <= nr <= max_row and 0 <= nc <= max_col):
                return r, c
            next_blank = self._is_blank(matrix[nr][nc])
            if current_blank:
                r, c = nr, nc
                if not next_blank:
                    return r, c
            else:
                if next_blank:
                    return r, c
                r, c = nr, nc

    def _jump_data_edge(self, dr: int, dc: int, extend: bool) -> str:
        current = self._current_cell()
        if current is None:
            return "break"
        row, col = current
        target_row, target_col = self._edge_target(row, col, dr, dc)
        if extend:
            self.sheet.boxes = [(
                (
                    min(row, target_row),
                    min(col, target_col),
                    max(row, target_row) + 1,
                    max(col, target_col) + 1,
                ),
                "cells",
            )]
            try:
                self.sheet.set_currently_selected(target_row, target_col)
                self.sheet.see(target_row, target_col)
            except Exception:
                pass
            self._sync_formula_bar()
        else:
            self.select_cell(target_row, target_col)
        self.focus_canvas()
        return "break"

    def _select_current_column(self, _event: tk.Event | None = None) -> str:
        current = self._current_cell()
        if current is not None:
            self.sheet.select_column(current[1])
            self._sync_formula_bar()
        return "break"

    def _select_current_row(self, _event: tk.Event | None = None) -> str:
        current = self._current_cell()
        if current is not None:
            self.sheet.select_row(current[0])
            self._sync_formula_bar()
        return "break"

    def _select_all_cells(self, _event: tk.Event | None = None) -> str:
        try:
            self.sheet.select_all()
        except Exception:
            pass
        self._sync_formula_bar()
        return "break"

    def _select_current_region(self, _event: tk.Event | None = None) -> str:
        current = self._current_cell()
        if current is None:
            return "break"
        matrix = self._matrix()
        start_r, start_c = current
        if self._is_blank(matrix[start_r][start_c]):
            self.select_cell(start_r, start_c)
            return "break"

        stack = [(start_r, start_c)]
        seen: set[tuple[int, int]] = set()
        max_row = len(matrix)
        max_col = len(STANDARD_HEADERS)
        while stack:
            r, c = stack.pop()
            if (r, c) in seen or not (0 <= r < max_row and 0 <= c < max_col):
                continue
            if self._is_blank(matrix[r][c]):
                continue
            seen.add((r, c))
            stack.extend(((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)))

        if not seen:
            return "break"
        rows = [r for r, _ in seen]
        cols = [c for _, c in seen]
        r1, r2 = min(rows), max(rows) + 1
        c1, c2 = min(cols), max(cols) + 1
        self.sheet.boxes = [((r1, c1, r2, c2), "cells")]
        try:
            self.sheet.set_currently_selected(start_r, start_c)
        except Exception:
            pass
        self._sync_formula_bar()
        return "break"

    def _fill_selection_with_active(self, _event: tk.Event | None = None) -> str:
        current = self._current_cell()
        cells = self.selected_cells()
        if current is None or not cells:
            return "break"
        value = self.sheet.get_cell_data(current[0], current[1], get_displayed=False)
        for row, col in sorted(cells):
            address = f"{self._excel_column_name(col)}{row + 1}"
            self.sheet.set_data(address, data=value, undo=True, emit_event=True, redraw=False)
        self.sheet.redraw()
        return "break"

    def _copy_from_above(self, _event: tk.Event | None = None) -> str:
        current = self._current_cell()
        if current is None or current[0] <= 0:
            self.bell()
            return "break"
        row, col = current
        value = self.sheet.get_cell_data(row - 1, col, get_displayed=False)
        address = f"{self._excel_column_name(col)}{row + 1}"
        self.sheet.set_data(address, data=value, undo=True, emit_event=True, redraw=True)
        self.select_cell(row, col)
        return "break"

    def _set_active_value(self, value: str) -> str:
        current = self._current_cell()
        if current is None:
            return "break"
        row, col = current
        address = f"{self._excel_column_name(col)}{row + 1}"
        self.sheet.set_data(address, data=value, undo=True, emit_event=True, redraw=True)
        self.select_cell(row, col)
        return "break"

    def _insert_current_date(self, _event: tk.Event | None = None) -> str:
        return self._set_active_value(datetime.now().strftime("%d-%b-%Y"))

    def _insert_current_time(self, _event: tk.Event | None = None) -> str:
        return self._set_active_value(datetime.now().strftime("%H:%M"))

    def _focus_name_box(self, _event: tk.Event | None = None) -> str:
        self.name_box.focus_set()
        self.name_box.selection_range(0, "end")
        return "break"

    def _open_replace_dialog(self, _event: tk.Event | None = None) -> str:
        dialog = tk.Toplevel(self)
        dialog.title("Find and Replace")
        dialog.transient(self.winfo_toplevel())
        dialog.resizable(False, False)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        ttk.Label(frame, text="Find what:").grid(row=0, column=0, sticky="w", pady=4)
        find_var = tk.StringVar()
        find_entry = ttk.Entry(frame, textvariable=find_var, width=36)
        find_entry.grid(row=0, column=1, columnspan=3, sticky="ew", pady=4)
        ttk.Label(frame, text="Replace with:").grid(row=1, column=0, sticky="w", pady=4)
        replace_var = tk.StringVar()
        ttk.Entry(frame, textvariable=replace_var, width=36).grid(row=1, column=1, columnspan=3, sticky="ew", pady=4)
        match_case = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="Match case", variable=match_case).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 8))
        status_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=status_var, foreground="#666666").grid(row=3, column=0, columnspan=4, sticky="w", pady=(0, 8))

        def matches(value: object, needle: str) -> bool:
            text = "" if value is None else str(value)
            if match_case.get():
                return needle in text
            return needle.casefold() in text.casefold()

        def find_next() -> None:
            needle = find_var.get()
            if not needle:
                self.bell()
                return
            current = self._current_cell() or (0, 0)
            total_rows = len(self._matrix())
            total_cols = len(STANDARD_HEADERS)
            start = current[0] * total_cols + current[1]
            for offset in range(1, total_rows * total_cols + 1):
                idx = (start + offset) % (total_rows * total_cols)
                r, c = divmod(idx, total_cols)
                value = self.sheet.get_cell_data(r, c, get_displayed=False)
                if matches(value, needle):
                    self.select_cell(r, c)
                    status_var.set(f"Found at {self._excel_column_name(c)}{r + 1}")
                    return
            status_var.set("No matching cell found")
            self.bell()

        def replace_one() -> None:
            needle = find_var.get()
            if not needle:
                return
            current = self._current_cell()
            if current is None:
                return
            r, c = current
            old = self.sheet.get_cell_data(r, c, get_displayed=False)
            old_text = "" if old is None else str(old)
            if matches(old_text, needle):
                if match_case.get():
                    new_text = old_text.replace(needle, replace_var.get())
                else:
                    new_text = re.sub(re.escape(needle), replace_var.get(), old_text, flags=re.IGNORECASE)
                address = f"{self._excel_column_name(c)}{r + 1}"
                self.sheet.set_data(address, data=new_text, undo=True, emit_event=True, redraw=True)
            find_next()

        def replace_all() -> None:
            needle = find_var.get()
            if not needle:
                return
            count = 0
            for r, row in enumerate(self._matrix()):
                for c, old in enumerate(row[: len(STANDARD_HEADERS)]):
                    old_text = "" if old is None else str(old)
                    if not matches(old_text, needle):
                        continue
                    if match_case.get():
                        new_text = old_text.replace(needle, replace_var.get())
                    else:
                        new_text = re.sub(re.escape(needle), replace_var.get(), old_text, flags=re.IGNORECASE)
                    address = f"{self._excel_column_name(c)}{r + 1}"
                    self.sheet.set_data(address, data=new_text, undo=True, emit_event=True, redraw=False)
                    count += 1
            if count:
                self.sheet.redraw()
            status_var.set(f"Replaced {count} occurrence(s)")

        ttk.Button(frame, text="Find Next", command=find_next).grid(row=4, column=0, padx=3, pady=3)
        ttk.Button(frame, text="Replace", command=replace_one).grid(row=4, column=1, padx=3, pady=3)
        ttk.Button(frame, text="Replace All", command=replace_all).grid(row=4, column=2, padx=3, pady=3)
        ttk.Button(frame, text="Close", command=dialog.destroy).grid(row=4, column=3, padx=3, pady=3)
        find_entry.focus_set()
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        return "break"

    def _horizontal_page(self, direction: int) -> str:
        try:
            left, right = self.sheet.get_xview()
            span = max(0.05, right - left)
            target = max(0.0, min(1.0, left + direction * span * 0.9))
            self.sheet.set_xview(target, option="moveto")
        except Exception:
            pass
        return "break"

    def _hide_selected_rows(self, _event: tk.Event | None = None) -> str:
        try:
            rows = self.sheet.get_selected_rows(get_cells_as_rows=True)
            if rows:
                self.sheet.hide_rows(rows)
        except Exception:
            pass
        return "break"

    def _hide_selected_columns(self, _event: tk.Event | None = None) -> str:
        try:
            columns = self.sheet.get_selected_columns(get_cells_as_columns=True)
            if columns:
                self.sheet.hide_columns(columns)
        except Exception:
            pass
        return "break"

    def _show_all_rows(self, _event: tk.Event | None = None) -> str:
        try:
            self.sheet.display_rows("all", redraw=True)
        except Exception:
            pass
        return "break"

    def _show_all_columns(self, _event: tk.Event | None = None) -> str:
        try:
            self.sheet.display_columns("all", redraw=True)
        except Exception:
            pass
        return "break"

    def _build_formula_bar(self) -> None:
        # Keep the compact Excel-style Name Box for A1/F5 navigation, but remove
        # the visible fx/formula input field. Cell values are edited directly in
        # the worksheet with F2, double-click, or normal typing.
        bar = ttk.Frame(self, padding=(0, 0, 0, 4))
        bar.pack(fill="x")

        self.name_var = tk.StringVar(value="A1")
        self.name_box = ttk.Entry(bar, textvariable=self.name_var, width=10, justify="center")
        self.name_box.pack(side="left", padx=(0, 8))
        self.name_box.bind("<Return>", self._goto_name_box)
        self.name_box.bind("<Escape>", lambda _e: self._sync_formula_bar())

        # Retain the variable for backward compatibility with internal methods,
        # but intentionally do not render a formula-entry widget.
        self.formula_var = tk.StringVar(value="")

        self.cell_hint_var = tk.StringVar(value="F2 edit • Tab/Shift+Tab move • Ctrl+G Go To • Alt+↓ filter • F1 shortcuts")
        ttk.Label(bar, textvariable=self.cell_hint_var, foreground="#666666").pack(side="left", fill="x", expand=True, padx=(4, 2))

    @staticmethod
    def _event_value(event: object, name: str, default: object = None) -> object:
        if hasattr(event, name):
            return getattr(event, name)
        if isinstance(event, dict):
            return event.get(name, default)
        return default

    @staticmethod
    def _excel_column_name(index: int) -> str:
        index += 1
        letters: list[str] = []
        while index:
            index, rem = divmod(index - 1, 26)
            letters.append(chr(65 + rem))
        return "".join(reversed(letters))

    @staticmethod
    def _excel_column_index(letters: str) -> int:
        result = 0
        for char in letters.upper():
            result = result * 26 + (ord(char) - 64)
        return result - 1

    def _header_labels(self) -> list[str]:
        labels: list[str] = []
        for index, header in enumerate(STANDARD_HEADERS):
            letter = self._excel_column_name(index)
            arrow = "▼" if index in self._filtered_columns else "▾"
            labels.append(f"{letter} · {header}  {arrow}")
        return labels

    def set_filtered_columns(self, columns: set[int]) -> None:
        self._filtered_columns = set(columns)
        try:
            self.sheet.headers(self._header_labels(), reset_col_positions=False, redraw=False)
            for column in range(len(STANDARD_HEADERS)):
                bg = self.EXCEL_LIGHT_GREEN if column in self._filtered_columns else self.EXCEL_HEADER
                self.sheet.highlight_cells(column=column, canvas="header", bg=bg, fg="#111111", redraw=False)
            self.sheet.redraw()
        except Exception:
            pass

    def _validate_edit(self, event: object) -> str | None:
        value = self._event_value(event, "value", "")
        if value is None or str(value).strip() == "":
            return "-"
        return str(value)

    def _matrix(self) -> list[list[str]]:
        data = self.sheet.data
        return [[str(value) if value is not None else "-" for value in row] for row in data]

    @staticmethod
    def _row_has_user_data(values: list[str]) -> bool:
        for value in values:
            text = "" if value is None else str(value).strip()
            if text and text != "-":
                return True
        return False

    @classmethod
    def _worksheet_row_count(cls, record_count: int) -> int:
        return max(cls.MIN_VISIBLE_ROWS, record_count + cls.EXTRA_BLANK_ROWS)

    @staticmethod
    def _extract_row_move_map(event: object) -> dict[int, int]:
        moved = DataGrid._event_value(event, "moved", {})
        if hasattr(moved, "rows"):
            rows = moved.rows
        elif isinstance(moved, dict):
            rows = moved.get("rows", {})
        else:
            rows = {}

        if hasattr(rows, "data"):
            data_map = rows.data
        elif isinstance(rows, dict):
            data_map = rows.get("data", {})
        else:
            data_map = {}

        if not isinstance(data_map, dict):
            return {}
        result: dict[int, int] = {}
        for old, new in data_map.items():
            try:
                result[int(old)] = int(new)
            except (TypeError, ValueError):
                continue
        return result

    def _apply_row_move_map(self, move_map: dict[int, int]) -> None:
        if not move_map or not self._row_ids:
            return
        reordered: list[int | None] = [None] * len(self._row_ids)
        placed_old: set[int] = set()
        for old, new in move_map.items():
            if 0 <= old < len(self._row_ids) and 0 <= new < len(reordered):
                reordered[new] = self._row_ids[old]
                placed_old.add(old)

        remaining = [self._row_ids[i] for i in range(len(self._row_ids)) if i not in placed_old]
        remaining_iter = iter(remaining)
        for i, value in enumerate(reordered):
            if value is None:
                try:
                    reordered[i] = next(remaining_iter)
                except StopIteration:
                    break
        self._row_ids = reordered

    def _sheet_modified(self, event: object) -> None:
        if self._loading:
            return
        self._apply_row_move_map(self._extract_row_move_map(event))

        matrix = self._matrix()
        if len(self._row_ids) < len(matrix):
            self._row_ids.extend([None] * (len(matrix) - len(self._row_ids)))
        elif len(self._row_ids) > len(matrix):
            self._row_ids = self._row_ids[: len(matrix)]

        event_name = str(self._event_value(event, "eventname", "edit_table"))
        self.on_grid_change(matrix, list(self._row_ids), event_name)
        self.after_idle(self._sync_formula_bar)

    def _selection_changed(self, _event: object = None) -> None:
        self.after_idle(self._sync_formula_bar)
        self.after_idle(lambda: self.event_generate("<<GridSelectionChanged>>"))

    def _end_edit_cell(self, _event: object = None) -> None:
        self.after_idle(self._sync_formula_bar)

    def _sync_formula_bar(self) -> None:
        if not hasattr(self, "sheet"):
            return
        selected = self.sheet.get_currently_selected()
        if not selected or not isinstance(selected.row, int) or not isinstance(selected.column, int):
            return
        row, column = selected.row, selected.column
        self.name_var.set(f"{self._excel_column_name(column)}{row + 1}")
        try:
            value = self.sheet.get_cell_data(row, column, get_displayed=False)
        except Exception:
            value = ""
        text = "" if value is None or str(value) == "-" else str(value)
        self.formula_var.set(text)
        header = STANDARD_HEADERS[column] if 0 <= column < len(STANDARD_HEADERS) else ""
        self.cell_hint_var.set(f"{header}  •  F2 edit  •  Tab/Shift+Tab move  •  Alt+↓ filter  •  F1 shortcuts")

    def _goto_name_box(self, _event: tk.Event | None = None) -> str:
        match = re.fullmatch(r"\s*\$?([A-Za-z]+)\$?(\d+)\s*", self.name_var.get())
        if not match:
            self.bell()
            self._sync_formula_bar()
            return "break"
        column = self._excel_column_index(match.group(1))
        row = int(match.group(2)) - 1
        if not (0 <= column < len(STANDARD_HEADERS) and 0 <= row < len(self._row_ids)):
            self.bell()
            self._sync_formula_bar()
            return "break"
        self.select_cell(row, column)
        self.focus_canvas()
        return "break"

    def _commit_formula_bar(self, _event: tk.Event | None = None) -> str:
        selected = self.sheet.get_currently_selected()
        if not selected or not isinstance(selected.row, int) or not isinstance(selected.column, int):
            return "break"
        value = self.formula_var.get().strip() or "-"
        address = f"{self._excel_column_name(selected.column)}{selected.row + 1}"
        try:
            self.sheet.set_data(address, data=value, undo=True, emit_event=True, redraw=True)
        except Exception:
            # Compatibility fallback for tksheet point releases.
            self.sheet[address].data = value
            self._sheet_modified({"eventname": "formula_bar_edit"})
        self.select_cell(selected.row, selected.column)
        self.focus_canvas()
        return "break"

    def _open_editor(self, _event: tk.Event | None = None) -> str:
        try:
            self.sheet.open_cell()
        except Exception:
            pass
        return "break"

    def _request_filter(self, column: int, x: int | None = None, y: int | None = None) -> None:
        if self.on_filter_request is None or not (0 <= column < len(STANDARD_HEADERS)):
            return
        px = self.winfo_pointerx() if x is None else x
        py = self.winfo_pointery() if y is None else y
        self.on_filter_request(column, px, py)

    def _header_arrow_click(self, event: tk.Event) -> str | None:
        try:
            if self.sheet.identify_region(event) != "header":
                return None
            column = self.sheet.identify_column(event, exclude_header=False, allow_end=False)
            if column is None:
                return None
            positions = self.sheet.get_column_widths(canvas_positions=True)
            if column + 1 >= len(positions):
                return None
            canvas_x = event.widget.canvasx(event.x) if hasattr(event.widget, "canvasx") else event.x
            distance_from_right = positions[column + 1] - canvas_x
            if 0 <= distance_from_right <= self.FILTER_HITBOX_PIXELS:
                self._request_filter(column, event.x_root, event.y_root)
                return "break"
        except Exception:
            return None
        return None

    def _header_right_click(self, event: tk.Event) -> str | None:
        try:
            if self.sheet.identify_region(event) != "header":
                return None
            column = self.sheet.identify_column(event, exclude_header=False, allow_end=False)
            if column is None:
                return None
            self._request_filter(column, event.x_root, event.y_root)
            return "break"
        except Exception:
            return None

    def _open_active_filter(self, _event: tk.Event | None = None) -> str:
        selected = self.sheet.get_currently_selected()
        if selected and isinstance(selected.column, int):
            self._request_filter(selected.column)
        return "break"

    def _fill_down(self, _event: tk.Event | None = None) -> str:
        cells = self.selected_cells()
        if not cells:
            return "break"
        by_column: dict[int, list[int]] = {}
        for row, column in cells:
            by_column.setdefault(column, []).append(row)
        changed = False
        for column, rows in by_column.items():
            rows = sorted(set(rows))
            if len(rows) < 2:
                continue
            source = self.sheet.get_cell_data(rows[0], column, get_displayed=False)
            for row in rows[1:]:
                address = f"{self._excel_column_name(column)}{row + 1}"
                self.sheet.set_data(address, data=source, undo=True, emit_event=True, redraw=False)
                changed = True
        if changed:
            self.sheet.redraw()
        return "break"

    def _fill_right(self, _event: tk.Event | None = None) -> str:
        cells = self.selected_cells()
        if not cells:
            return "break"
        by_row: dict[int, list[int]] = {}
        for row, column in cells:
            by_row.setdefault(row, []).append(column)
        changed = False
        for row, columns in by_row.items():
            columns = sorted(set(columns))
            if len(columns) < 2:
                continue
            source = self.sheet.get_cell_data(row, columns[0], get_displayed=False)
            for column in columns[1:]:
                address = f"{self._excel_column_name(column)}{row + 1}"
                self.sheet.set_data(address, data=source, undo=True, emit_event=True, redraw=False)
                changed = True
        if changed:
            self.sheet.redraw()
        return "break"

    def set_validation_colors(self, *, outside_tal: str | None = None, suppressed: str | None = None) -> None:
        """Update configurable validation row highlights without changing other state colours."""
        if outside_tal:
            self.state_colors["Outside TAL"] = outside_tal
        if suppressed:
            self.state_colors["Suppressed"] = suppressed

    def load_rows(
        self,
        rows: list[dict[str, str]],
        states: dict[int, str] | None = None,
        row_ids: list[int] | None = None,
    ) -> None:
        states = states or {}
        ids = row_ids if row_ids is not None else list(range(len(rows)))
        data = [[row.get(header, "-") for header in STANDARD_HEADERS] for row in rows]

        worksheet_rows = self._worksheet_row_count(len(data))
        blank_row_count = worksheet_rows - len(data)
        data.extend([[""] * len(STANDARD_HEADERS) for _ in range(blank_row_count)])
        display_ids: list[int | None] = [int(row_id) for row_id in ids]
        display_ids.extend([None] * blank_row_count)

        selected = self.sheet.get_currently_selected()
        selected_row = selected.row if selected else None
        selected_col = selected.column if selected else None

        self._loading = True
        try:
            self._row_ids = display_ids
            self.sheet.set_sheet_data(
                data,
                reset_col_positions=False,
                reset_row_positions=True,
                reset_highlights=True,
                keep_formatting=False,
            )
            self.sheet.headers(self._header_labels(), reset_col_positions=False, redraw=False)
            self.sheet.row_index([str(i + 1) for i in range(len(data))], reset_row_positions=False)

            for display_row, row_id in enumerate(display_ids):
                if row_id is None:
                    continue
                state = states.get(row_id)
                bg = self.state_colors.get(state or "")
                if bg:
                    self.sheet.highlight_rows(display_row, bg=bg, redraw=False)

            for column in range(len(STANDARD_HEADERS)):
                bg = self.EXCEL_LIGHT_GREEN if column in self._filtered_columns else self.EXCEL_HEADER
                self.sheet.highlight_cells(column=column, canvas="header", bg=bg, fg="#111111", redraw=False)

            if data:
                row = min(selected_row if isinstance(selected_row, int) else 0, len(data) - 1)
                col = min(selected_col if isinstance(selected_col, int) else 0, len(STANDARD_HEADERS) - 1)
                self.sheet.select_cell(row, col, redraw=False, run_binding_func=False)
            self.sheet.redraw()
        finally:
            self._loading = False
        self.after_idle(self._sync_formula_bar)

    def set_row_id(self, display_row: int, original_row_id: int) -> None:
        if display_row < 0:
            return
        if display_row >= len(self._row_ids):
            self._row_ids.extend([None] * (display_row + 1 - len(self._row_ids)))
        self._row_ids[display_row] = original_row_id
        try:
            labels = [str(display_row + 1) for display_row in range(len(self._row_ids))]
            self.sheet.row_index(labels, reset_row_positions=False)
        except Exception:
            pass

    def sort_by(self, header: str) -> None:
        try:
            column = STANDARD_HEADERS.index(header)
        except ValueError:
            return
        self.sheet.sort_rows_by_column(column=column)

    def selected_indices(self) -> list[int]:
        displayed_rows: set[int] = set()
        try:
            displayed_rows.update(self.sheet.get_selected_rows(get_cells_as_rows=True))
        except Exception:
            try:
                displayed_rows.update(self.sheet.get_selected_rows())
                displayed_rows.update(row for row, _col in self.sheet.get_selected_cells())
            except Exception:
                pass

        result: list[int] = []
        for display_row in sorted(displayed_rows):
            if 0 <= display_row < len(self._row_ids):
                row_id = self._row_ids[display_row]
                if row_id is not None:
                    result.append(row_id)
        return result

    def visible_indices(self) -> list[int]:
        return [row_id for row_id in self._row_ids if row_id is not None]

    @property
    def paste_start_column(self) -> int:
        selected = self.sheet.get_currently_selected()
        if selected and isinstance(selected.column, int):
            return max(0, min(selected.column, len(STANDARD_HEADERS) - 1))
        return 0

    @property
    def active_row_index(self) -> int | None:
        selected = self.sheet.get_currently_selected()
        if not selected or not isinstance(selected.row, int):
            return None
        if 0 <= selected.row < len(self._row_ids):
            return self._row_ids[selected.row]
        return None

    def focus_canvas(self) -> None:
        self.sheet.focus_set("table")

    def select_cell(self, display_row: int, column: int) -> None:
        if display_row < 0 or column < 0:
            return
        self.sheet.select_cell(display_row, column)
        try:
            self.sheet.see(display_row, column)
        except Exception:
            pass
        self._sync_formula_bar()

    def selected_cells(self) -> set[tuple[int, int]]:
        try:
            return set(self.sheet.get_selected_cells(get_rows=True, get_columns=True))
        except Exception:
            try:
                return set(self.sheet.get_selected_cells())
            except Exception:
                return set()

    def copy(self) -> None:
        self.sheet.copy()

    def cut(self) -> None:
        self.sheet.cut()

    def paste(self) -> None:
        self.sheet.paste()

    def undo(self) -> None:
        self.sheet.undo()

    def redo(self) -> None:
        self.sheet.redo()
