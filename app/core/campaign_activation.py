from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterable

from app.constants import MISSING_VALUE
from app.core.campaign_manager import CampaignReferenceLoader
from app.core.campaign_models import CampaignFileInfo, CampaignProfile
from app.core.reference_lists import ReferenceData, available_fields, detect_reference_mapping
from app.core.suppression_validator import SuppressionResult, SuppressionValidator
from app.core.tal_validator import TALValidator
from app.utils.text_utils import clean_missing


SUPPRESSION_ROLES = {
    "client_suppression",
    "internal_suppression",
    "processed_suppression",
    "competitor_exclusion",
    "domain_suppression",
}


def _reference_from_campaign_file(info: CampaignFileInfo, kind: str) -> ReferenceData:
    headers, rows = CampaignReferenceLoader.read_rows(info)
    mapping = detect_reference_mapping(headers, kind)  # type: ignore[arg-type]
    targets = set(mapping.values())

    # Content/role-based fallback for one-column campaign files.
    if not mapping and len(headers) == 1:
        if kind == "tal":
            mapping[headers[0]] = "Domain"
        elif info.role in SUPPRESSION_ROLES:
            mapping[headers[0]] = "Email" if info.role != "domain_suppression" else "Domain"
    if kind == "tal" and not ({"Company Name", "Domain"} & set(mapping.values())):
        # Prefer a web/domain-looking source column when automatic aliases missed it.
        for header in headers:
            normalized = "".join(ch for ch in header.casefold() if ch.isalnum())
            if any(token in normalized for token in ("domain", "website", "webaddress")):
                mapping[header] = "Domain"
                break
    if kind == "suppression" and not mapping:
        raise ValueError(f"No suppression fields could be inferred from {info.relative_path}")
    if kind == "tal" and not mapping:
        raise ValueError(f"No TAL fields could be inferred from {info.relative_path}")

    valid_fields = available_fields(kind)  # type: ignore[arg-type]
    records: list[dict[str, str]] = []
    for row in rows:
        record = {field: MISSING_VALUE for field in valid_fields}
        for source, target in mapping.items():
            if source in row and target in record:
                record[target] = clean_missing(row.get(source))
        if kind == "suppression" and record.get("Prospect Name") == MISSING_VALUE:
            parts = [record.get("First Name"), record.get("Last Name")]
            combined = " ".join(part for part in parts if part and part != MISSING_VALUE).strip()
            if combined:
                record["Prospect Name"] = combined
        if any(value != MISSING_VALUE for value in record.values()):
            records.append(record)

    return ReferenceData(
        kind=kind,  # type: ignore[arg-type]
        source_path=info.absolute_path,
        source_name=Path(info.absolute_path).name,
        columns=tuple(headers),
        mapping=mapping,
        records=tuple(records),
    )


class CompositeSuppressionValidator:
    """Preserve suppression source provenance while respecting global match priority."""

    _RANK = {
        "Suppressed - Email": 100,
        "Suppressed - LinkedIn": 90,
        "Suppressed - Domain": 80,
        "Suppressed - Company": 70,
        "Suppressed - Prospect Name": 60,
        "Possible Suppression Match": 20,
        "Not Suppressed": 0,
    }

    def __init__(self, validators: Iterable[tuple[str, str, SuppressionValidator]]) -> None:
        self.validators = list(validators)

    @property
    def fuzzy_enabled(self) -> bool:
        return all(validator.fuzzy_enabled for _, _, validator in self.validators) if self.validators else False

    @fuzzy_enabled.setter
    def fuzzy_enabled(self, value: bool) -> None:
        for _, _, validator in self.validators:
            validator.fuzzy_enabled = bool(value)

    def match(self, record: dict[str, str]) -> SuppressionResult:
        best = SuppressionResult("Not Suppressed", "Suppression: no match")
        best_rank = 0
        for source_type, source_file, validator in self.validators:
            result = validator.match(record)
            rank = self._RANK.get(result.status, 0)
            if rank > best_rank:
                best_rank = rank
                source_label = source_type.replace("_", " ").title()
                best = replace(
                    result,
                    reason=f"{result.reason} | Source: {source_label} — {source_file}",
                    source_type=source_type,
                    source_file=source_file,
                )
        return best


def build_campaign_validators(
    profile: CampaignProfile,
    *,
    tal_fuzzy_enabled: bool = True,
    suppression_fuzzy_enabled: bool = True,
) -> tuple[TALValidator | None, CompositeSuppressionValidator | None, list[str]]:
    warnings: list[str] = []
    tal_validator: TALValidator | None = None

    tal_info = next((item for item in profile.files if item.role == "tal"), None)
    if tal_info:
        try:
            tal_data = _reference_from_campaign_file(tal_info, "tal")
            tal_validator = TALValidator(tal_data, fuzzy_enabled=tal_fuzzy_enabled)
        except Exception as exc:
            warnings.append(f"TAL activation failed for {tal_info.relative_path}: {exc}")

    suppression_validators: list[tuple[str, str, SuppressionValidator]] = []
    for info in profile.files:
        if info.role not in SUPPRESSION_ROLES:
            continue
        try:
            data = _reference_from_campaign_file(info, "suppression")
            suppression_validators.append(
                (
                    info.role,
                    info.relative_path,
                    SuppressionValidator(data, fuzzy_enabled=suppression_fuzzy_enabled),
                )
            )
        except Exception as exc:
            warnings.append(f"Suppression activation failed for {info.relative_path}: {exc}")

    composite = CompositeSuppressionValidator(suppression_validators) if suppression_validators else None
    return tal_validator, composite, warnings
