from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping


from app.constants import DATE_FORMAT, MISSING_VALUE, STANDARD_HEADERS
from app.utils.text_utils import clean_missing


@dataclass
class DataManager:
    records: list[dict[str, str]] = field(default_factory=list)
    custom_columns: list[str] = field(default_factory=list)
    formulas: dict[tuple[int, str], str] = field(default_factory=dict)
    formula_errors: dict[tuple[int, str], str] = field(default_factory=dict)

    @property
    def headers(self) -> list[str]:
        return list(STANDARD_HEADERS) + self.custom_columns

    def add_columns(self, names: Iterable[str]) -> list[str]:
        names = [str(name).strip() for name in names]
        seen = {name.casefold() for name in self.headers}
        for name in names:
            if not name or name.startswith(("=", "+", "-", "@")):
                raise ValueError("Use a non-empty column name that does not start with =, +, - or @.")
            if name.casefold() in seen:
                raise ValueError(f'A column named "{name}" already exists.')
            seen.add(name.casefold())
        self.custom_columns.extend(names)
        for record in self.records:
            for name in names:
                record.setdefault(name, MISSING_VALUE)
        return names

    def clear(self) -> None:
        self.records.clear()
        self.formulas.clear()
        self.formula_errors.clear()

    def _blank_record(self) -> dict[str, str]:
        return {header: MISSING_VALUE for header in self.headers}

    def append_record(self, values: Mapping[str, object], source_name: str = "Manual Entry") -> dict[str, str]:
        record = self._blank_record()
        for header in self.headers:
            if header in values:
                record[header] = clean_missing(values[header])
        if record["Date"] == MISSING_VALUE:
            record["Date"] = datetime.now().strftime(DATE_FORMAT)
        if record["Source File Name"] == MISSING_VALUE:
            record["Source File Name"] = clean_missing(source_name)
        self.records.append(record)
        return record

    def extend(self, rows: Iterable[Mapping[str, object]], source_name: str) -> int:
        before = len(self.records)
        for row in rows:
            self.append_record(row, source_name=source_name)
        return len(self.records) - before

    def replace_all(self, rows: Iterable[Mapping[str, object]], source_name: str = "Manual Entry") -> int:
        self.clear()
        return self.extend(rows, source_name)

    def to_dataframe(self) -> "pd.DataFrame":
        import pandas as pd
        if not self.records:
            return pd.DataFrame(columns=self.headers)
        return pd.DataFrame(self.records, columns=self.headers).fillna(MISSING_VALUE)

    def get(self, index: int) -> dict[str, str]:
        return self.records[index]

    def raw_value(self, index: int, column: str) -> str:
        if (index, column) in self.formulas:
            return self.formulas[index, column]
        value = self.records[index].get(column, MISSING_VALUE) if index < len(self.records) else MISSING_VALUE
        # Retain literal equals-prefixed imported/database values on edit and undo.
        return "'" + value if str(value).startswith(("=", "'")) else value

    def update_cell(self, index: int, column: str, value: object, *, allow_formulas=False) -> None:
        value = clean_missing(value)
        cell = (index, column)
        self.formulas.pop(cell, None)
        self.formula_errors.pop(cell, None)
        if allow_formulas and value.startswith("="):
            self.formulas[cell] = value
        elif allow_formulas and value.startswith("'"):
            value = value[1:]
        self.records[index][column] = value

    def recalculate(self):
        if not self.formulas:
            self.formula_errors.clear()
            return set()
        from app.core.formulas import recalculate
        return recalculate(self)

    def formula_payload(self):
        return [{"row": row, "column": column, "expression": expression}
                for (row, column), expression in self.formulas.items()]

    def restore_formulas(self, payload):
        self.formulas.clear()
        for entry in payload or []:
            row, column, expression = entry.get("row"), entry.get("column"), entry.get("expression")
            if (isinstance(row, int) and 0 <= row < len(self.records) and column in self.headers
                    and column not in {"QA Status", "Primary Reason"}
                    and isinstance(expression, str) and expression.startswith("=")):
                self.formulas[row, column] = expression
        return self.recalculate()

    def delete_columns(self, names):
        names = set(names)
        if not names or not names.issubset(set(self.custom_columns)):
            raise ValueError("Only custom columns can be deleted. Use Columns to hide required lead fields.")
        from app.core.formulas import remove_column_references
        headers = self.headers
        deleted = {headers.index(name) for name in names}
        self.formulas = {(row, header): remove_column_references(expr, row, headers.index(header), headers, deleted)
                         for (row, header), expr in self.formulas.items() if header not in names}
        self.custom_columns[:] = [name for name in self.custom_columns if name not in names]
        for record in self.records:
            for name in names:
                record.pop(name, None)
        return self.recalculate()

    def delete_indices(self, indices: list[int]) -> None:
        deleted = {i for i in indices if 0 <= i < len(self.records)}
        if self.formulas and deleted:
            from app.core.formulas import remove_row_references
            headers = self.headers
            self.formulas = {(row - sum(i < row for i in deleted), header):
                             remove_row_references(expr, row, headers.index(header), headers, deleted)
                             for (row, header), expr in self.formulas.items() if row not in deleted}
        for index in sorted(deleted, reverse=True):
            if 0 <= index < len(self.records):
                del self.records[index]
        self.recalculate()
