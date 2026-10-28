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

    def update_cell(self, index: int, column: str, value: object) -> None:
        self.records[index][column] = clean_missing(value)

    def delete_indices(self, indices: list[int]) -> None:
        for index in sorted(set(indices), reverse=True):
            if 0 <= index < len(self.records):
                del self.records[index]
