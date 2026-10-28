from __future__ import annotations

from pathlib import Path
import csv


from app.constants import MISSING_VALUE, STANDARD_HEADERS
from app.utils.text_utils import clean_missing, normalize_header


def _pandas():
    # Pandas is intentionally imported only when an import/export operation needs it.
    # This saves a noticeable amount of desktop startup time.
    import pandas as pd
    return pd

HEADER_ALIASES: dict[str, str] = {
    "fname": "First Name",
    "firstname": "First Name",
    "lname": "Last Name",
    "lastname": "Last Name",
    "organization": "Company Name",
    "organisation": "Company Name",
    "company": "Company Name",
    "companyname": "Company Name",
    "url": "Company Website",
    "website": "Company Website",
    "domain": "Company Website",
    "companywebsite": "Company Website",
    "email": "Business Email ID",
    "emailaddress": "Business Email ID",
    "businessemail": "Business Email ID",
    "businessemailid": "Business Email ID",
    "workemail": "Business Email ID",
    "linkedin": "Prospect LinkedIn Link",
    "linkedinurl": "Prospect LinkedIn Link",
    "linkedinlink": "Prospect LinkedIn Link",
    "profileurl": "Prospect LinkedIn Link",
    "prospectlinkedinlink": "Prospect LinkedIn Link",
}
for _header in STANDARD_HEADERS:
    HEADER_ALIASES.setdefault(normalize_header(_header), _header)


def detect_mapping(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for source in columns:
        target = HEADER_ALIASES.get(normalize_header(source))
        if target:
            mapping[source] = target
    return mapping


def _read_delimited_text(path: Path) -> "pd.DataFrame":
    """Read CSV/TXT exported by Excel without assuming UTF-8."""
    pd = _pandas()
    errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                sample = handle.read(8192)
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
            except csv.Error:
                delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
            return pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                encoding=encoding,
                sep=delimiter,
                engine="python",
            )
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
        except pd.errors.ParserError as exc:
            errors.append(f"{encoding}: {exc}")
    raise ValueError(
        "Unable to read the text file using UTF-8, Windows-1252 or Latin-1. "
        + " | ".join(errors[-3:])
    )


def read_source_table(path: str | Path) -> "pd.DataFrame":
    """Read a supported Excel/CSV/TXT source into a string DataFrame."""
    pd = _pandas()
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(path, dtype=str, keep_default_na=False, engine="openpyxl")
    if suffix in {".csv", ".txt", ".tsv"}:
        return _read_delimited_text(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def _remove_empty_rows(df):
    """Ignore empty/formatted worksheet rows without treating 0 or 'NA' as empty."""
    if df.empty:
        return df.reset_index(drop=True)
    populated = df.notna() & df.astype(str).apply(lambda column: column.str.strip().ne(""))
    return df.loc[populated.any(axis=1)].reset_index(drop=True)


def read_import_tables(path: str | Path) -> dict[str, "pd.DataFrame"]:
    """Read lead-import worksheets with real row counts for the sheet selector."""
    path = Path(path)
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        tables = _pandas().read_excel(path, sheet_name=None, dtype=str,
                                     keep_default_na=False, engine="openpyxl")
    else:
        tables = {path.name: read_source_table(path)}
    result = {}
    for name, table in tables.items():
        table = _remove_empty_rows(table)
        table.columns = [str(column) for column in table.columns]
        table.attrs["source_sheet"] = name if path.suffix.lower() in {".xlsx", ".xlsm"} else ""
        result[name] = table
    if not any(len(table) for table in result.values()):
        raise ValueError("This file contains column headings but no data rows. Choose a file with lead data below the headings.")
    return result


def _read(path: Path) -> "pd.DataFrame":
    """Backward-compatible internal alias."""
    return read_source_table(path)


def import_records(path: str | Path, manual_mapping: dict[str, str] | None = None, *, custom_columns=(), dataframe=None) -> tuple[list[dict[str, str]], dict[str, str]]:
    source = Path(path)
    df = _remove_empty_rows(_read(source) if dataframe is None else dataframe.copy())
    if df.empty:
        raise ValueError("The selected worksheet or CSV contains no data rows. Choose a populated worksheet or another file.")
    df.columns = [str(c) for c in df.columns]
    mapping = dict(manual_mapping) if manual_mapping is not None else detect_mapping(list(df.columns))
    for column in custom_columns:
        if column in df.columns and manual_mapping is None:
            mapping[column] = column
    if not mapping:
        raise ValueError("No recognizable columns were found. A manual mapping is required.")
    headers = list(STANDARD_HEADERS) + list(custom_columns)
    seen = set()
    for source_col, target_col in mapping.items():
        if source_col not in df.columns or target_col not in headers:
            raise ValueError(f'Invalid column mapping: "{source_col}" to "{target_col}".')
        if target_col.casefold() in seen:
            raise ValueError(f'More than one source column maps to "{target_col}". Map each column once or choose Ignore.')
        seen.add(target_col.casefold())

    rows: list[dict[str, str]] = []
    for _, series in df.iterrows():
        row = {header: MISSING_VALUE for header in headers}
        for source_col, target_col in mapping.items():
            if source_col in df.columns and target_col in row:
                row[target_col] = clean_missing(series[source_col])
        rows.append(row)
    return rows, mapping
