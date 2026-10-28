from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import simpledialog, ttk
from typing import Callable, Iterable


@dataclass(frozen=True)
class TextFilter:
    """Excel-style text filter applied in addition to checked values."""

    operator: str
    value: str

    def matches(self, candidate: object) -> bool:
        text = "" if candidate is None else str(candidate)
        needle = self.value
        lhs = text.casefold()
        rhs = needle.casefold()
        if self.operator == "equals":
            return lhs == rhs
        if self.operator == "not_equals":
            return lhs != rhs
        if self.operator == "contains":
            return rhs in lhs
        if self.operator == "not_contains":
            return rhs not in lhs
        if self.operator == "begins_with":
            return lhs.startswith(rhs)
        if self.operator == "ends_with":
            return lhs.endswith(rhs)
        return True


class ExcelFilterPopup(tk.Toplevel):
    """Excel-inspired filter menu with sorting, search and multi-value selection."""

    MAX_VISIBLE_VALUES = 1500
    BLANK_DISPLAY = "(Blanks)"

    def __init__(
        self,
        master: tk.Misc,
        *,
        column_name: str,
        values: Iterable[str],
        active_values: set[str] | None,
        active_text_filter: TextFilter | None,
        x: int,
        y: int,
        on_apply: Callable[[set[str] | None, TextFilter | None], None],
        on_clear: Callable[[], None],
        on_sort_ascending: Callable[[], None],
        on_sort_descending: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self.withdraw()
        self.column_name = column_name
        self.on_apply = on_apply
        self.on_clear = on_clear
        self.on_sort_ascending = on_sort_ascending
        self.on_sort_descending = on_sort_descending
        self.active_text_filter = active_text_filter

        normalized = {self._normalize(v) for v in values}
        self.all_values = sorted(normalized, key=self._sort_key)
        if active_values is None:
            self.selected_values = set(self.all_values)
        else:
            self.selected_values = {self._normalize(v) for v in active_values}

        self.title(f"Filter - {column_name}")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.configure(bg="#f2f2f2")

        self.search_var = tk.StringVar()
        self.select_all_var = tk.BooleanVar(value=self._all_visible_selected())
        self.filter_info_var = tk.StringVar(value=self._text_filter_caption())

        self._build()
        self.update_idletasks()

        # Keep the popup on-screen when invoked near the right/bottom edge.
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = max(self.winfo_reqwidth(), 310)
        height = max(self.winfo_reqheight(), 430)
        px = min(max(0, x), max(0, screen_w - width - 8))
        py = min(max(0, y), max(0, screen_h - height - 50))
        self.geometry(f"+{px}+{py}")
        self.deiconify()
        self.lift()
        self.search_entry.focus_set()

    @staticmethod
    def _normalize(value: object) -> str:
        text = "" if value is None else str(value).strip()
        return text if text else "-"

    @classmethod
    def _display(cls, value: str) -> str:
        return cls.BLANK_DISPLAY if value == "-" else value

    @classmethod
    def _sort_key(cls, value: str) -> tuple[int, str]:
        return (1 if value == "-" else 0, cls._display(value).casefold())

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=6)
        outer.pack(fill="both", expand=True)

        sort_a = ttk.Button(outer, text="A→Z   Sort A to Z", command=self._sort_a_to_z)
        sort_a.pack(fill="x", pady=(0, 2))
        sort_z = ttk.Button(outer, text="Z→A   Sort Z to A", command=self._sort_z_to_a)
        sort_z.pack(fill="x", pady=2)

        ttk.Separator(outer).pack(fill="x", pady=6)

        clear_state = "normal" if self._has_active_filter() else "disabled"
        clear_btn = ttk.Button(
            outer,
            text=f'Clear Filter From "{self.column_name}"',
            command=self._clear,
            state=clear_state,
        )
        clear_btn.pack(fill="x", pady=2)

        text_filter_button = ttk.Menubutton(outer, text="Text Filters   ▸")
        menu = tk.Menu(text_filter_button, tearoff=False)
        menu.add_command(label="Equals...", command=lambda: self._set_text_filter("equals"))
        menu.add_command(label="Does Not Equal...", command=lambda: self._set_text_filter("not_equals"))
        menu.add_separator()
        menu.add_command(label="Contains...", command=lambda: self._set_text_filter("contains"))
        menu.add_command(label="Does Not Contain...", command=lambda: self._set_text_filter("not_contains"))
        menu.add_separator()
        menu.add_command(label="Begins With...", command=lambda: self._set_text_filter("begins_with"))
        menu.add_command(label="Ends With...", command=lambda: self._set_text_filter("ends_with"))
        menu.add_separator()
        menu.add_command(label="Clear Text Filter", command=self._clear_text_filter)
        text_filter_button.configure(menu=menu)
        text_filter_button.pack(fill="x", pady=2)

        self.filter_info = ttk.Label(outer, textvariable=self.filter_info_var, foreground="#666666")
        self.filter_info.pack(fill="x", pady=(0, 4))

        ttk.Separator(outer).pack(fill="x", pady=(2, 6))

        search_frame = ttk.Frame(outer)
        search_frame.pack(fill="x")
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side="left", fill="x", expand=True)
        ttk.Label(search_frame, text="⌕", width=3, anchor="center").pack(side="right")
        self.search_entry.bind("<KeyRelease>", lambda _e: self._refresh_tree())

        self.select_all = ttk.Checkbutton(
            outer,
            text="(Select All)",
            variable=self.select_all_var,
            command=self._toggle_select_all,
        )
        self.select_all.pack(anchor="w", pady=(6, 2))

        list_frame = ttk.Frame(outer)
        list_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(list_frame, show="tree", columns=("value",), displaycolumns=(), height=13, selectmode="none")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self._toggle_tree_item)
        self.tree.bind("<space>", self._toggle_focused_item)

        count_frame = ttk.Frame(outer)
        count_frame.pack(fill="x", pady=(4, 2))
        self.count_label = ttk.Label(count_frame, text="")
        self.count_label.pack(side="left")

        ttk.Separator(outer).pack(fill="x", pady=6)
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="OK", command=self._apply, width=12).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Cancel", command=self.destroy, width=12).pack(side="right")

        self.bind("<Return>", lambda _e: self._apply())
        self.bind("<Escape>", lambda _e: self.destroy())
        self._refresh_tree()

    def _has_active_filter(self) -> bool:
        return self.active_text_filter is not None or self.selected_values != set(self.all_values)

    def _text_filter_caption(self) -> str:
        if self.active_text_filter is None:
            return ""
        names = {
            "equals": "Equals",
            "not_equals": "Does not equal",
            "contains": "Contains",
            "not_contains": "Does not contain",
            "begins_with": "Begins with",
            "ends_with": "Ends with",
        }
        return f'{names.get(self.active_text_filter.operator, "Filter")}: "{self.active_text_filter.value}"'

    def _visible_values(self) -> list[str]:
        query = self.search_var.get().strip().casefold()
        if not query:
            return self.all_values[: self.MAX_VISIBLE_VALUES]
        return [
            value
            for value in self.all_values
            if query in self._display(value).casefold()
        ][: self.MAX_VISIBLE_VALUES]

    def _all_visible_selected(self) -> bool:
        visible = self._visible_values() if hasattr(self, "search_var") else self.all_values
        return bool(visible) and all(value in self.selected_values for value in visible)

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        visible = self._visible_values()
        for value in visible:
            checked = value in self.selected_values
            prefix = "☑" if checked else "☐"
            self.tree.insert("", "end", iid=self._iid(value), text=f"{prefix}  {self._display(value)}", values=(value,))

        self.select_all_var.set(bool(visible) and all(v in self.selected_values for v in visible))
        suffix = "" if len(self.all_values) <= self.MAX_VISIBLE_VALUES or self.search_var.get().strip() else f" (showing first {self.MAX_VISIBLE_VALUES:,})"
        self.count_label.configure(text=f"{len(visible):,} value(s){suffix}")

    @staticmethod
    def _iid(value: str) -> str:
        # Treeview item IDs cannot be empty. A deterministic escaped ID avoids duplicates.
        return "v:" + value.encode("utf-8", errors="replace").hex()

    def _toggle_tree_item(self, event: tk.Event) -> str | None:
        iid = self.tree.identify_row(event.y)
        if not iid:
            return None
        self.tree.focus(iid)
        value = bytes.fromhex(iid[2:]).decode("utf-8", errors="replace")
        if value in self.selected_values:
            self.selected_values.remove(value)
        else:
            self.selected_values.add(value)
        self._refresh_tree()
        return "break"

    def _toggle_focused_item(self, _event: tk.Event) -> str:
        iid = self.tree.focus()
        if iid:
            value = bytes.fromhex(iid[2:]).decode("utf-8", errors="replace")
            if value in self.selected_values:
                self.selected_values.remove(value)
            else:
                self.selected_values.add(value)
            self._refresh_tree()
        return "break"

    def _toggle_select_all(self) -> None:
        visible = self._visible_values()
        if self.select_all_var.get():
            self.selected_values.update(visible)
        else:
            self.selected_values.difference_update(visible)
        self._refresh_tree()

    def _set_text_filter(self, operator: str) -> None:
        prompt_names = {
            "equals": "Equals",
            "not_equals": "Does Not Equal",
            "contains": "Contains",
            "not_contains": "Does Not Contain",
            "begins_with": "Begins With",
            "ends_with": "Ends With",
        }
        current = self.active_text_filter.value if self.active_text_filter and self.active_text_filter.operator == operator else ""
        value = simpledialog.askstring(
            f"{prompt_names[operator]} - {self.column_name}",
            f"Show rows where {self.column_name} {prompt_names[operator].lower()}:\n",
            parent=self,
            initialvalue=current,
        )
        if value is None:
            return
        self.active_text_filter = TextFilter(operator=operator, value=value)
        self.filter_info_var.set(self._text_filter_caption())

    def _clear_text_filter(self) -> None:
        self.active_text_filter = None
        self.filter_info_var.set("")

    def _sort_a_to_z(self) -> None:
        self.on_sort_ascending()
        self.destroy()

    def _sort_z_to_a(self) -> None:
        self.on_sort_descending()
        self.destroy()

    def _clear(self) -> None:
        self.on_clear()
        self.destroy()

    def _apply(self) -> None:
        all_values = set(self.all_values)
        selected: set[str] | None
        if self.selected_values == all_values:
            selected = None
        else:
            selected = set(self.selected_values)
        self.on_apply(selected, self.active_text_filter)
        self.destroy()
