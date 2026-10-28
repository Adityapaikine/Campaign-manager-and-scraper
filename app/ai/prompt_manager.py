from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PromptSpec:
    name: str
    version: str
    system: str
    instruction: str


PROMPTS: dict[str, PromptSpec] = {
    "campaign_requirements": PromptSpec(
        "campaign_requirements",
        "2.0",
        (
            "You extract B2B campaign requirements into strict JSON. Never invent a requirement. "
            "Distinguish inclusions, exclusions, caps, required fields, and ambiguous instructions. "
            "If wording is ambiguous, lower confidence and set review_required=true."
        ),
        (
            "Return JSON with key rules, an array of objects. Each object must contain: category, field, "
            "operator, value, confidence (0-1), review_required (boolean), reason, source_excerpt. "
            "Use field names such as allowed_countries, excluded_countries, allowed_industries, "
            "excluded_industries, job_title_keywords, excluded_job_title_keywords, minimum_seniority, "
            "job_functions, excluded_job_functions, company_size, revenue, required_fields, "
            "domain_cap_default, account_cap_default, business_email_required, tal_required, "
            "previous_delivery_suppression, lead_goal, client, campaign_id, campaign_name."
        ),
    ),
    "rule_builder": PromptSpec(
        "rule_builder",
        "1.0",
        "Convert user campaign instructions into deterministic validation rules. Do not invent rules.",
        (
            "Return JSON with key rules. Each rule: category, field, operator, value, confidence, "
            "review_required, reason. Use explicit inclusion/exclusion semantics."
        ),
    ),
    "normalize_value": PromptSpec(
        "normalize_value",
        "1.0",
        "Normalize B2B lead data conservatively. Preserve meaning and never fabricate unavailable facts.",
        (
            "Input may contain one value or a values array. Return JSON with key items, an array of objects. "
            "Each item must contain input, normalized_value, confidence, reason, job_level, job_function when relevant. "
            "Only fill fields supported by the supplied input text."
        ),
    ),
    "enrich_record": PromptSpec(
        "enrich_record",
        "1.0",
        (
            "Suggest missing B2B lead fields using only supplied evidence. Do not claim external research. "
            "Unknown values must remain '-'."
        ),
        (
            "Return JSON with suggestions mapping field names to {value, confidence, reason, evidence}. "
            "Focus on Job Level, Job Function, Industry, Company Size, Revenue, City, State, Country, SIC Code, NAICS Code."
        ),
    ),
    "research_company": PromptSpec(
        "research_company",
        "1.0",
        "Synthesize company information only from the supplied search snippets and existing record. Never invent facts beyond that evidence.",
        "Return JSON with suggestions mapping fields to {value, confidence, reason, evidence_urls}. Focus on Company Website, Industry, Company Size, Revenue, Address, City, State, Country, SIC Code, NAICS Code.",
    ),
    "qa_review": PromptSpec(
        "qa_review",
        "1.0",
        "Act as a conservative B2B QA assistant. Explain issues; do not override deterministic exclusions.",
        (
            "Return JSON with assessment, confidence, summary, recommendations (array), and field_reviews (array)."
        ),
    ),
    "duplicate_review": PromptSpec(
        "duplicate_review",
        "1.0",
        "Assess whether two B2B lead records may represent the same person or company. Be conservative.",
        "Return JSON with possible_duplicate, confidence, reasons (array), and recommended_action.",
    ),
    "validation_explanation": PromptSpec(
        "validation_explanation",
        "1.0",
        "Explain validation outcomes clearly to an operations/QA user without changing the rules.",
        "Return JSON with summary, primary_issue, explanation, next_actions (array).",
    ),
    "campaign_insights": PromptSpec(
        "campaign_insights",
        "1.0",
        "Analyze structured campaign metrics. Do not suggest changing client rules unless explicitly framed as an option for human review.",
        "Return JSON with summary, bottlenecks (array), observations (array), recommendations (array).",
    ),
    "management_report": PromptSpec(
        "management_report",
        "1.0",
        "Write a concise management-friendly campaign operations report from structured metrics only.",
        "Return JSON with executive_summary, progress, constraints, data_quality, recommendations, next_actions.",
    ),
}


def get_prompt(name: str) -> PromptSpec:
    try:
        return PROMPTS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown AI prompt: {name}") from exc
