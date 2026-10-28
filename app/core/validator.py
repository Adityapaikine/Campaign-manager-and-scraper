from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from app.constants import MISSING_VALUE, REQUIRED_FIELDS
from app.core.batch_control import BatchCancelled, BatchControl
from app.core.duplicate_checker import DuplicateChecker, DuplicateResult
from app.core.normalizer import (
    NormalizedRecord,
    clean_text,
    is_generic_email_domain,
    is_valid_domain,
    is_valid_email,
    normalize_domain,
    normalize_record,
    normalize_url,
)
from app.core.suppression_validator import SuppressionResult, SuppressionValidator
from app.core.tal_validator import TALResult, TALValidator
from app.core.campaign_rule_validator import CampaignRuleValidator
from app.core.campaign_models import CampaignProfile
from app.core.domain_cap_engine import DomainCapEngine

URL_FIELDS: tuple[str, ...] = (
    "Industry Link",
    "Address Link",
    "Phone Number Link",
    "Revenue Link",
    "SIC/NAICS Code Link",
)


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: str  # info | warning | manual | error | duplicate | suppressed | outside_tal
    field: str | None = None


@dataclass(slots=True)
class ValidationResult:
    status: str
    reasons: list[str]
    issues: list[ValidationIssue] = field(default_factory=list)
    normalized: dict[str, str] = field(default_factory=dict)
    duplicate_status: str = "Unique"
    duplicate_rows: tuple[int, ...] = ()
    tal_status: str = "Not Loaded"
    tal_reason: str = "TAL: no list loaded"
    suppression_status: str = "Not Loaded"
    suppression_reason: str = "Suppression: no list loaded"

    @property
    def qa_status(self) -> str:
        return "Disqualified" if self.status in {"Suppressed", "Outside TAL"} else self.status

    @property
    def primary_reason(self) -> str:
        if self.status == "Suppressed":
            return "Suppression matched"
        if self.status == "Outside TAL":
            return "Tal not Mapped"
        return self.reasons[0] if self.reasons else MISSING_VALUE


class ValidationEngine:
    """Central Phase-3 validation engine.

    Normalization remains non-destructive. TAL and suppression engines are optional
    and can be replaced/cleared without touching worksheet values.
    """

    def __init__(
        self,
        duplicate_checker: DuplicateChecker | None = None,
        tal_validator: TALValidator | None = None,
        suppression_validator: SuppressionValidator | None = None,
        *,
        require_tal_match: bool = True,
        enable_suppression: bool = True,
        campaign_profile: CampaignProfile | None = None,
    ) -> None:
        self.duplicate_checker = duplicate_checker or DuplicateChecker()
        self.tal_validator = tal_validator
        self.suppression_validator = suppression_validator
        self.require_tal_match = require_tal_match
        self.enable_suppression = enable_suppression
        self.campaign_rule_validator = CampaignRuleValidator(campaign_profile)
        self.last_run_cancelled = False

    def configure_tal(self, validator: TALValidator | None, *, require_match: bool | None = None) -> None:
        self.tal_validator = validator
        if require_match is not None:
            self.require_tal_match = bool(require_match)

    def configure_suppression(self, validator: SuppressionValidator | None, *, enabled: bool | None = None) -> None:
        self.suppression_validator = validator
        if enabled is not None:
            self.enable_suppression = bool(enabled)

    def configure_campaign(self, profile: CampaignProfile | None) -> None:
        self.campaign_rule_validator.configure(profile)


    def validate_records(
        self,
        records: list[dict[str, str]],
        *,
        control: BatchControl | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        progress_interval: int = 25,
    ) -> list[ValidationResult]:
        """Validate a batch with optional cooperative pause/cancel support.

        The return value remains a plain list for backward compatibility. When a
        cancellation occurs, the list contains the already processed prefix and
        ``last_run_cancelled`` is set to ``True``.
        """
        self.last_run_cancelled = False
        duplicate_results = self.duplicate_checker.check(records)
        results: list[ValidationResult] = []
        total = len(records)
        interval = max(1, int(progress_interval))
        for index, record in enumerate(records):
            try:
                if control is not None:
                    control.checkpoint()
            except BatchCancelled:
                self.last_run_cancelled = True
                break
            results.append(self.validate(record, duplicate_result=duplicate_results[index]))
            done = index + 1
            if progress_callback and (done == total or done % interval == 0):
                progress_callback(done, total)
        if results:
            self._apply_campaign_caps(records[:len(results)], results)
        return results

    def validate(
        self,
        record: dict[str, str],
        *,
        duplicate_result: DuplicateResult | None = None,
    ) -> ValidationResult:
        normalized_record: NormalizedRecord = normalize_record(record)
        issues: list[ValidationIssue] = []

        # Phase 3 follows the inexpensive-exclusion-first workflow.
        suppression_result = self._suppression_result(record)
        if suppression_result.is_suppressed:
            issues.append(
                ValidationIssue(
                    code="suppressed",
                    message=suppression_result.reason,
                    severity="suppressed",
                )
            )
        elif suppression_result.is_possible:
            issues.append(
                ValidationIssue(
                    code="possible_suppression",
                    message=suppression_result.reason,
                    severity="manual",
                )
            )

        tal_result = self._tal_result(record)
        if self.tal_validator is not None:
            if tal_result.status == "Not in TAL" and self.require_tal_match:
                issues.append(
                    ValidationIssue(
                        code="outside_tal",
                        message=tal_result.reason,
                        severity="outside_tal",
                    )
                )
            elif tal_result.status == "Possible Match":
                issues.append(
                    ValidationIssue(
                        code="possible_tal_match",
                        message=tal_result.reason,
                        severity="manual",
                    )
                )

        # Campaign-specific rules extracted/confirmed through Campaign Manager.
        for campaign_issue in self.campaign_rule_validator.validate(record):
            issues.append(
                ValidationIssue(
                    code=campaign_issue.code,
                    message=campaign_issue.message,
                    severity=campaign_issue.severity,
                    field=campaign_issue.field,
                )
            )

        # Required fields.
        for field_name in REQUIRED_FIELDS:
            if clean_text(record.get(field_name)) == MISSING_VALUE:
                issues.append(
                    ValidationIssue(
                        code="required_missing",
                        message=f"Missing {field_name}",
                        severity="error",
                        field=field_name,
                    )
                )

        # Company Website / domain validation.
        website = clean_text(record.get("Company Website"))
        if website != MISSING_VALUE:
            domain = normalize_domain(website)
            if domain == MISSING_VALUE or not is_valid_domain(domain):
                issues.append(
                    ValidationIssue(
                        code="invalid_domain",
                        message="Invalid Company Website / Domain",
                        severity="error",
                        field="Company Website",
                    )
                )
            elif is_generic_email_domain(domain):
                issues.append(
                    ValidationIssue(
                        code="generic_company_domain",
                        message=f"Generic email provider used as Company Website: {domain}",
                        severity="manual",
                        field="Company Website",
                    )
                )

        linkedin = clean_text(record.get("Prospect LinkedIn Link"))
        if linkedin != MISSING_VALUE and normalized_record.get("Prospect LinkedIn Link") == MISSING_VALUE:
            issues.append(
                ValidationIssue(
                    code="invalid_linkedin",
                    message="Invalid LinkedIn profile URL",
                    severity="warning",
                    field="Prospect LinkedIn Link",
                )
            )

        email = clean_text(record.get("Business Email ID"))
        if email != MISSING_VALUE and not is_valid_email(email):
            issues.append(
                ValidationIssue(
                    code="invalid_email",
                    message="Invalid Business Email syntax/domain",
                    severity="error",
                    field="Business Email ID",
                )
            )

        for field_name in URL_FIELDS:
            value = clean_text(record.get(field_name))
            if value != MISSING_VALUE and normalize_url(value) == MISSING_VALUE:
                issues.append(
                    ValidationIssue(
                        code="invalid_url",
                        message=f"Invalid URL in {field_name}",
                        severity="warning",
                        field=field_name,
                    )
                )

        duplicate_result = duplicate_result or DuplicateResult("Unique")
        if duplicate_result.is_exact:
            row_numbers = ", ".join(str(index + 1) for index in duplicate_result.duplicate_rows)
            issues.append(
                ValidationIssue(
                    code="exact_duplicate",
                    message=f"Exact duplicate via {duplicate_result.matched_on}; matching row(s): {row_numbers}",
                    severity="duplicate",
                )
            )
        elif duplicate_result.is_possible:
            row_numbers = ", ".join(str(index + 1) for index in duplicate_result.duplicate_rows)
            issues.append(
                ValidationIssue(
                    code="possible_duplicate",
                    message=f"Possible duplicate via {duplicate_result.matched_on}; matching row(s): {row_numbers}",
                    severity="manual",
                )
            )

        status = self._final_status(issues)
        if status == "Valid" and clean_text(record.get("Email Status")) == "Generated":
            status = "Valid - Email Generated"
        reasons = [issue.message for issue in issues]
        if not reasons:
            reasons = ["Phase-3 validation passed"]

        return ValidationResult(
            status=status,
            reasons=reasons,
            issues=issues,
            normalized=dict(normalized_record.values),
            duplicate_status=duplicate_result.status,
            duplicate_rows=duplicate_result.duplicate_rows,
            tal_status=tal_result.status,
            tal_reason=tal_result.reason,
            suppression_status=suppression_result.status,
            suppression_reason=suppression_result.reason,
        )

    def _apply_campaign_caps(self, records: list[dict[str, str]], results: list[ValidationResult]) -> None:
        profile = self.campaign_rule_validator.profile
        if profile is None:
            return
        caps: dict[str, int] = {}
        default_cap: int | None = None
        for rule in profile.rules:
            if rule.status not in {"Confirmed", "Extracted"}:
                continue
            if rule.field in {"domain_limits", "domain_caps"} and isinstance(rule.value, dict):
                for domain, raw in rule.value.items():
                    try:
                        caps[str(domain)] = int(float(raw))
                    except (TypeError, ValueError):
                        continue
            elif rule.field in {"domain_cap_default", "account_cap_default"}:
                try:
                    default_cap = int(float(rule.value))
                except (TypeError, ValueError):
                    pass
        if not caps and default_cap is None:
            return
        engine = DomainCapEngine(caps, default_cap)
        used: dict[str, int] = {}
        eligible = {"Valid", "Valid - Email Generated", "Warning", "Manual Review"}
        for record, result in zip(records, results):
            domain = normalize_domain(record.get("Company Website"))
            if domain == MISSING_VALUE:
                continue
            cap = engine.cap_for(domain)
            if cap is None:
                continue
            current = used.get(domain, 0)
            if result.status in eligible:
                if current >= cap:
                    issue = ValidationIssue(
                        code="campaign_domain_cap_reached",
                        message=f"Campaign rule: Domain cap reached for {domain} (limit {cap})",
                        severity="error",
                        field="Company Website",
                    )
                    result.issues.append(issue)
                    result.reasons.append(issue.message)
                    result.status = self._final_status(result.issues)
                else:
                    used[domain] = current + 1

    def _tal_result(self, record: dict[str, str]) -> TALResult:
        if self.tal_validator is None:
            return TALResult("Not Loaded", "TAL: no list loaded")
        return self.tal_validator.match(record)

    def _suppression_result(self, record: dict[str, str]) -> SuppressionResult:
        if self.suppression_validator is None:
            return SuppressionResult("Not Loaded", "Suppression: no list loaded")
        if not self.enable_suppression:
            return SuppressionResult("Disabled", "Suppression: matching disabled in Settings")
        return self.suppression_validator.match(record)

    @staticmethod
    def _final_status(issues: list[ValidationIssue]) -> str:
        severities = {issue.severity for issue in issues}
        # Exclusion states take precedence because they block approval by default.
        # The complete reason list still preserves structural/duplicate issues.
        if "suppressed" in severities:
            return "Suppressed"
        if "outside_tal" in severities:
            return "Outside TAL"
        if "error" in severities:
            return "Invalid"
        if "duplicate" in severities:
            return "Duplicate"
        if "manual" in severities:
            return "Manual Review"
        if "warning" in severities:
            return "Warning"
        return "Valid"


BasicValidator = ValidationEngine
