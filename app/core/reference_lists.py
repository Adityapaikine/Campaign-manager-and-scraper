from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


from app.constants import MISSING_VALUE
from app.excel.importer import read_source_table
from app.utils.text_utils import clean_missing, normalize_header

ReferenceKind = Literal["tal", "suppression"]

TAL_FIELDS: tuple[str, ...] = ("Company Name", "Domain")
SUPPRESSION_FIELDS: tuple[str, ...] = (
    "Email",
    "Company Name",
    "Domain",
    "Prospect Name",
    "First Name",
    "Last Name",
    "LinkedIn URL",
)

_DOMAIN_ALIASES = {
    "domain", "website", "companywebsite", "url", "web", "accountdomain",
    "companydomain", "companyurl", "accountwebsite", "domainname", "webaddress",
}
_COMPANY_ALIASES = {
    "company", "companyname", "account", "accountname", "organization",
    "organisation", "organizationname", "organisationname",
}
_EMAIL_ALIASES = {
    "email", "emailaddress", "businessemail", "businessemailid", "workemail",
    "professionalemail", "corporateemail",
}
_LINKEDIN_ALIASES = {
    "linkedin", "linkedinurl", "linkedinlink", "profileurl", "prospectlinkedinlink",
    "linkedinprofile", "linkedinprofileurl", "linkedinleadvalidationurl", "leadvalidationurl",
}
_NAME_ALIASES = {
    "prospectname", "fullname", "contactname", "name", "personname", "leadname",
}
_FIRST_NAME_ALIASES = {"firstname", "fname", "givenname", "forename"}
_LAST_NAME_ALIASES = {"lastname", "lname", "surname", "familyname"}


def _canonical_aliases(kind: ReferenceKind) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for item in _COMPANY_ALIASES:
        aliases[item] = "Company Name"
    for item in _DOMAIN_ALIASES:
        aliases[item] = "Domain"
    if kind == "suppression":
        for item in _EMAIL_ALIASES:
            aliases[item] = "Email"
        for item in _LINKEDIN_ALIASES:
            aliases[item] = "LinkedIn URL"
        for item in _NAME_ALIASES:
            aliases[item] = "Prospect Name"
        for item in _FIRST_NAME_ALIASES:
            aliases[item] = "First Name"
        for item in _LAST_NAME_ALIASES:
            aliases[item] = "Last Name"
    return aliases


def available_fields(kind: ReferenceKind) -> tuple[str, ...]:
    return TAL_FIELDS if kind == "tal" else SUPPRESSION_FIELDS


def detect_reference_mapping(columns: list[str], kind: ReferenceKind) -> dict[str, str]:
    aliases = _canonical_aliases(kind)
    mapping: dict[str, str] = {}
    used_targets: set[str] = set()
    for source in columns:
        target = aliases.get(normalize_header(source))
        if target and target not in used_targets:
            mapping[source] = target
            used_targets.add(target)
    return mapping


@dataclass(frozen=True, slots=True)
class ReferenceData:
    kind: ReferenceKind
    source_path: str
    source_name: str
    columns: tuple[str, ...]
    mapping: dict[str, str]
    records: tuple[dict[str, str], ...]

    @property
    def count(self) -> int:
        return len(self.records)


def preview_reference_file(path: str | Path) -> tuple["pd.DataFrame", dict[str, str]]:
    source = Path(path)
    df = read_source_table(source)
    df.columns = [str(column) for column in df.columns]
    # Kind is not known here; caller should run detection for its own kind.
    return df, {}


def load_reference_data(
    path: str | Path,
    kind: ReferenceKind,
    mapping: dict[str, str] | None = None,
    *, dataframe=None,
) -> ReferenceData:
    if kind not in {"tal", "suppression"}:
        raise ValueError("Unknown reference list type")
    source = Path(path)
    df = read_source_table(source) if dataframe is None else dataframe.copy()
    df.columns = [str(column) for column in df.columns]
    chosen = mapping if mapping is not None else detect_reference_mapping(list(df.columns), kind)

    valid_targets = set(available_fields(kind))
    chosen = {
        source_col: target
        for source_col, target in chosen.items()
        if source_col in df.columns and target in valid_targets
    }
    if not chosen:
        raise ValueError("No usable columns are mapped. Please map at least one supported field.")
    if len(chosen.values()) != len(set(chosen.values())):
        raise ValueError("Two source columns map to the same field. Choose a different field or (Ignore).")
    if kind == "tal" and not ({"Company Name", "Domain"} & set(chosen.values())):
        raise ValueError("A TAL/Account List must map Company Name, Domain, or both.")

    records: list[dict[str, str]] = []
    for _, series in df.iterrows():
        record = {field: MISSING_VALUE for field in available_fields(kind)}
        for source_col, target in chosen.items():
            record[target] = clean_missing(series[source_col])
        if kind == "suppression":
            if record["Prospect Name"] == MISSING_VALUE:
                first = record["First Name"]
                last = record["Last Name"]
                parts = [part for part in (first, last) if part != MISSING_VALUE]
                if parts:
                    record["Prospect Name"] = " ".join(parts)
        # Ignore completely blank rows.
        if any(value != MISSING_VALUE for value in record.values()):
            records.append(record)

    if not records:
        raise ValueError("The selected file contains no usable TAL/Suppression records.")

    return ReferenceData(
        kind=kind,
        source_path=str(source),
        source_name=source.name,
        columns=tuple(df.columns),
        mapping=dict(chosen),
        records=tuple(records),
    )
