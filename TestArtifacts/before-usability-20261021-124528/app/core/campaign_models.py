from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class RuleSource:
    file: str
    location: str = ""
    excerpt: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleSource":
        return cls(
            file=str(data.get("file") or ""),
            location=str(data.get("location") or ""),
            excerpt=str(data.get("excerpt") or ""),
        )


@dataclass(slots=True)
class CampaignRule:
    category: str
    field: str
    operator: str
    value: Any
    confidence: float = 1.0
    status: str = "Extracted"  # Extracted | Confirmed | Needs Review | Disabled
    notes: str = ""
    sources: list[RuleSource] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.category}:{self.field}:{self.operator}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "field": self.field,
            "operator": self.operator,
            "value": self.value,
            "confidence": float(self.confidence),
            "status": self.status,
            "notes": self.notes,
            "sources": [asdict(source) for source in self.sources],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CampaignRule":
        return cls(
            category=str(data.get("category") or "Other"),
            field=str(data.get("field") or ""),
            operator=str(data.get("operator") or "equals"),
            value=data.get("value"),
            confidence=float(data.get("confidence") or 0.0),
            status=str(data.get("status") or "Extracted"),
            notes=str(data.get("notes") or ""),
            sources=[RuleSource.from_dict(item) for item in data.get("sources") or []],
        )


@dataclass(slots=True)
class CampaignFileInfo:
    relative_path: str
    absolute_path: str
    role: str
    format: str
    record_count: int = 0
    confidence: float = 0.0
    notes: str = ""
    columns: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CampaignFileInfo":
        return cls(
            relative_path=str(data.get("relative_path") or ""),
            absolute_path=str(data.get("absolute_path") or ""),
            role=str(data.get("role") or "unknown"),
            format=str(data.get("format") or ""),
            record_count=int(data.get("record_count") or 0),
            confidence=float(data.get("confidence") or 0.0),
            notes=str(data.get("notes") or ""),
            columns=[str(x) for x in data.get("columns") or []],
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(slots=True)
class CampaignConflict:
    rule_key: str
    values: list[Any]
    sources: list[str]
    resolved_value: Any = None
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CampaignConflict":
        return cls(
            rule_key=str(data.get("rule_key") or ""),
            values=list(data.get("values") or []),
            sources=[str(x) for x in data.get("sources") or []],
            resolved_value=data.get("resolved_value"),
            resolved=bool(data.get("resolved", False)),
        )


@dataclass(slots=True)
class CampaignProfile:
    campaign_id: str
    campaign_name: str
    source_root: str
    files: list[CampaignFileInfo] = field(default_factory=list)
    rules: list[CampaignRule] = field(default_factory=list)
    conflicts: list[CampaignConflict] = field(default_factory=list)
    imported_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    active: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "campaign_name": self.campaign_name,
            "source_root": self.source_root,
            "files": [item.to_dict() for item in self.files],
            "rules": [item.to_dict() for item in self.rules],
            "conflicts": [item.to_dict() for item in self.conflicts],
            "imported_at": self.imported_at,
            "active": self.active,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CampaignProfile":
        return cls(
            campaign_id=str(data.get("campaign_id") or ""),
            campaign_name=str(data.get("campaign_name") or ""),
            source_root=str(data.get("source_root") or ""),
            files=[CampaignFileInfo.from_dict(item) for item in data.get("files") or []],
            rules=[CampaignRule.from_dict(item) for item in data.get("rules") or []],
            conflicts=[CampaignConflict.from_dict(item) for item in data.get("conflicts") or []],
            imported_at=str(data.get("imported_at") or datetime.now().isoformat(timespec="seconds")),
            active=bool(data.get("active", False)),
            notes=str(data.get("notes") or ""),
        )

    def rule(self, field_name: str, *, include_unconfirmed: bool = True) -> CampaignRule | None:
        for rule in self.rules:
            if rule.field != field_name:
                continue
            if rule.status == "Disabled":
                continue
            if not include_unconfirmed and rule.status not in {"Confirmed", "Extracted"}:
                continue
            return rule
        return None
