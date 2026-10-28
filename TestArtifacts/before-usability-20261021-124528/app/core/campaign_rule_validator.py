from __future__ import annotations

import re
from dataclasses import dataclass

from app.constants import MISSING_VALUE
from app.core.campaign_models import CampaignProfile, CampaignRule
from app.core.normalizer import clean_text, normalize_country, normalize_industry


@dataclass(frozen=True, slots=True)
class CampaignRuleIssue:
    code: str
    message: str
    severity: str = "error"
    field: str | None = None


_SENIORITY_RANK = {
    "intern": 0,
    "entry": 1,
    "associate": 2,
    "senior": 3,
    "manager": 4,
    "senior manager": 5,
    "director": 6,
    "senior director": 7,
    "vp": 8,
    "vice president": 8,
    "svp": 9,
    "evp": 10,
    "c level": 11,
    "c-level": 11,
    "chief": 11,
    "owner": 11,
    "partner": 11,
}


def _rank_requirement(text: str) -> int | None:
    value = text.casefold().strip()
    if value.endswith("+"):
        value = value[:-1].strip()
    # specific before broad
    for label in ("senior director", "senior manager", "vice president", "director", "manager", "svp", "evp", "vp", "chief", "c-level", "c level", "partner", "owner"):
        if label in value:
            return _SENIORITY_RANK[label]
    return None


def _record_seniority_rank(record: dict[str, str]) -> int | None:
    combined = f"{record.get('Job Level', '')} {record.get('Job Title', '')}".casefold()
    candidates: list[int] = []
    # Match specific seniority tokens from highest to lowest.
    patterns = [
        (r"\bchief\b|\bc[a-z]{1,4}o\b|\bc-level\b", 11),
        (r"\bevp\b|executive vice president", 10),
        (r"\bsvp\b|senior vice president", 9),
        (r"\bvp\b|vice president", 8),
        (r"senior director", 7),
        (r"\bdirector\b", 6),
        (r"senior manager", 5),
        (r"\bmanager\b", 4),
        (r"\bpartner\b|\bowner\b", 11),
    ]
    for pattern, rank in patterns:
        if re.search(pattern, combined):
            candidates.append(rank)
    return max(candidates) if candidates else None


class CampaignRuleValidator:
    """Validate lead fields against an activated, reviewed campaign profile.

    Rules marked Disabled or Needs Review are never enforced automatically.
    Extracted and Confirmed rules are enforceable because they came from explicit
    source requirements or were confirmed by the user.
    """

    def __init__(self, profile: CampaignProfile | None = None) -> None:
        self.profile = profile

    def configure(self, profile: CampaignProfile | None) -> None:
        self.profile = profile

    def validate(self, record: dict[str, str]) -> list[CampaignRuleIssue]:
        if self.profile is None:
            return []
        issues: list[CampaignRuleIssue] = []
        for rule in self.profile.rules:
            if rule.status not in {"Confirmed", "Extracted"}:
                continue
            if rule.field in {"campaign_id", "campaign_name", "client", "cpc", "lead_goal", "start_date", "end_date"}:
                continue
            handler = getattr(self, f"_check_{rule.field}", None)
            if handler:
                issue = handler(record, rule)
                if issue:
                    if isinstance(issue, list):
                        issues.extend(issue)
                    else:
                        issues.append(issue)
        return issues

    @staticmethod
    def _check_allowed_countries(record: dict[str, str], rule: CampaignRule):
        current = normalize_country(record.get("Country"))
        if current == MISSING_VALUE:
            return CampaignRuleIssue("campaign_country_missing", "Campaign rule: Country is required for geography validation", "warning", "Country")
        allowed = {normalize_country(value) for value in (rule.value or [])}
        if current not in allowed:
            return CampaignRuleIssue(
                "campaign_geo_not_allowed",
                f"Campaign rule: Country '{clean_text(record.get('Country'))}' is outside the allowed geography",
                "error",
                "Country",
            )
        return None

    @staticmethod
    def _check_allowed_industries(record: dict[str, str], rule: CampaignRule):
        current = normalize_industry(record.get("Industry"))
        if current == MISSING_VALUE:
            return CampaignRuleIssue("campaign_industry_missing", "Campaign rule: Industry is required for industry validation", "warning", "Industry")
        allowed = {normalize_industry(value) for value in (rule.value or [])}
        if current not in allowed:
            return CampaignRuleIssue(
                "campaign_industry_not_allowed",
                f"Campaign rule: Industry '{clean_text(record.get('Industry'))}' is not in the campaign industry list",
                "error",
                "Industry",
            )
        return None

    @staticmethod
    def _check_job_title_keywords(record: dict[str, str], rule: CampaignRule):
        title = clean_text(record.get("Job Title"))
        if title == MISSING_VALUE:
            return CampaignRuleIssue("campaign_job_title_missing", "Campaign rule: Job Title is required for keyword validation", "warning", "Job Title")
        folded = title.casefold()
        keywords = [str(value).strip() for value in (rule.value or []) if str(value).strip()]
        if keywords and not any(keyword.casefold() in folded for keyword in keywords):
            return CampaignRuleIssue(
                "campaign_job_title_not_allowed",
                "Campaign rule: Job Title does not contain any approved campaign keyword",
                "error",
                "Job Title",
            )
        return None

    @staticmethod
    def _check_job_functions(record: dict[str, str], rule: CampaignRule):
        current = clean_text(record.get("Job Function"))
        if current == MISSING_VALUE:
            return CampaignRuleIssue("campaign_job_function_missing", "Campaign rule: Job Function is required", "warning", "Job Function")
        allowed = {str(value).casefold().strip() for value in (rule.value or [])}
        if current.casefold() not in allowed:
            return CampaignRuleIssue("campaign_job_function_not_allowed", f"Campaign rule: Job Function '{current}' is not allowed", "error", "Job Function")
        return None

    @staticmethod
    def _check_minimum_seniority(record: dict[str, str], rule: CampaignRule):
        required = _rank_requirement(str(rule.value or ""))
        if required is None:
            return None
        actual = _record_seniority_rank(record)
        if actual is None:
            return CampaignRuleIssue(
                "campaign_seniority_unknown",
                f"Campaign rule: Unable to determine whether the record meets minimum seniority '{rule.value}'",
                "manual",
                "Job Level",
            )
        if actual < required:
            return CampaignRuleIssue(
                "campaign_seniority_too_low",
                f"Campaign rule: Prospect is below required seniority '{rule.value}'",
                "error",
                "Job Level",
            )
        return None


    @staticmethod
    def _check_excluded_countries(record: dict[str, str], rule: CampaignRule):
        current = normalize_country(record.get("Country"))
        excluded = {normalize_country(value) for value in (rule.value or [])}
        if current != MISSING_VALUE and current in excluded:
            return CampaignRuleIssue("campaign_geo_excluded", f"Campaign rule: Country '{clean_text(record.get('Country'))}' is explicitly excluded", "error", "Country")
        return None

    @staticmethod
    def _check_excluded_industries(record: dict[str, str], rule: CampaignRule):
        current = normalize_industry(record.get("Industry"))
        excluded = {normalize_industry(value) for value in (rule.value or [])}
        if current != MISSING_VALUE and current in excluded:
            return CampaignRuleIssue("campaign_industry_excluded", f"Campaign rule: Industry '{clean_text(record.get('Industry'))}' is explicitly excluded", "error", "Industry")
        return None

    @staticmethod
    def _check_excluded_job_title_keywords(record: dict[str, str], rule: CampaignRule):
        title = clean_text(record.get("Job Title"))
        if title == MISSING_VALUE:
            return None
        folded = title.casefold()
        matches = [str(value).strip() for value in (rule.value or []) if str(value).strip() and str(value).strip().casefold() in folded]
        if matches:
            return CampaignRuleIssue("campaign_job_title_excluded", f"Campaign rule: Job Title contains excluded keyword '{matches[0]}'", "error", "Job Title")
        return None

    @staticmethod
    def _check_excluded_job_functions(record: dict[str, str], rule: CampaignRule):
        current = clean_text(record.get("Job Function"))
        excluded = {str(value).casefold().strip() for value in (rule.value or [])}
        if current != MISSING_VALUE and current.casefold() in excluded:
            return CampaignRuleIssue("campaign_job_function_excluded", f"Campaign rule: Job Function '{current}' is excluded", "error", "Job Function")
        return None

    @staticmethod
    def _check_business_email_required(record: dict[str, str], rule: CampaignRule):
        required = str(rule.value).strip().casefold() not in {"false", "0", "no", "off", "-"}
        if required and clean_text(record.get("Business Email ID")) == MISSING_VALUE:
            return CampaignRuleIssue("campaign_business_email_required", "Campaign rule: Business Email ID is required", "error", "Business Email ID")
        return None

    @staticmethod
    def _check_company_size(record: dict[str, str], rule: CampaignRule):
        current = clean_text(record.get("Company Size"))
        if current == MISSING_VALUE:
            return CampaignRuleIssue("campaign_company_size_missing", "Campaign rule: Company Size is required", "warning", "Company Size")
        allowed = [str(value).casefold().replace(",", "").strip() for value in (rule.value if isinstance(rule.value, list) else [rule.value]) if str(value).strip()]
        candidate = current.casefold().replace(",", "")
        if allowed and not any(value in candidate or candidate in value for value in allowed):
            return CampaignRuleIssue("campaign_company_size_not_allowed", f"Campaign rule: Company Size '{current}' is outside the configured campaign size rule", "manual", "Company Size")
        return None

    @staticmethod
    def _check_revenue(record: dict[str, str], rule: CampaignRule):
        current = clean_text(record.get("Revenue"))
        if current == MISSING_VALUE:
            return CampaignRuleIssue("campaign_revenue_missing", "Campaign rule: Revenue is required for this campaign rule", "warning", "Revenue")
        allowed = [str(value).casefold().replace(",", "").strip() for value in (rule.value if isinstance(rule.value, list) else [rule.value]) if str(value).strip()]
        candidate = current.casefold().replace(",", "")
        if allowed and not any(value in candidate or candidate in value for value in allowed):
            return CampaignRuleIssue("campaign_revenue_not_allowed", f"Campaign rule: Revenue '{current}' does not match the configured campaign revenue rule", "manual", "Revenue")
        return None

    @staticmethod
    def _check_required_fields(record: dict[str, str], rule: CampaignRule):
        issues = []
        for field_name in rule.value or []:
            if clean_text(record.get(str(field_name))) == MISSING_VALUE:
                issues.append(
                    CampaignRuleIssue(
                        "campaign_required_field_missing",
                        f"Campaign rule: Missing required field {field_name}",
                        "error",
                        str(field_name),
                    )
                )
        return issues
