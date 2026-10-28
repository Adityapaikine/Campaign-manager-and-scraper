from __future__ import annotations

import re
from dataclasses import dataclass

from app.constants import MISSING_VALUE
from app.core.normalizer import normalize_domain, normalize_email, normalize_name

SUPPORTED_PATTERNS: tuple[str, ...] = (
    "{first}.{last}",
    "{first}_{last}",
    "{first}-{last}",
    "{first}{last}",
    "{f}.{last}",
    "{f}{last}",
    "{first}.{l}",
    "{first}{l}",
    "{last}.{first}",
    "{last}{first}",
    "{last}{f}",
    "{first}",
    "{last}",
)


@dataclass(frozen=True, slots=True)
class PatternMatch:
    pattern: str
    email: str


def _email_name_token(value: object, *, first_name: bool) -> str:
    normalized = normalize_name(value)
    if normalized == MISSING_VALUE:
        return ""
    parts = [re.sub(r"[^a-z0-9]", "", part) for part in normalized.split()]
    parts = [part for part in parts if part]
    if not parts:
        return ""
    # If a middle name was supplied inside the First Name field, business-email
    # formats overwhelmingly use the first token. For Last Name, the last token is
    # the conservative choice. Apostrophes/hyphens are collapsed, e.g. O'Connor -> oconnor.
    return parts[0] if first_name else parts[-1]


def name_tokens(first_name: object, last_name: object) -> dict[str, str]:
    first = _email_name_token(first_name, first_name=True)
    last = _email_name_token(last_name, first_name=False)
    return {
        "first": first,
        "last": last,
        "f": first[:1],
        "l": last[:1],
    }


def render_local_part(pattern: str, first_name: object, last_name: object) -> str:
    if pattern not in SUPPORTED_PATTERNS:
        raise ValueError(f"Unsupported email pattern: {pattern}")
    tokens = name_tokens(first_name, last_name)
    if not tokens["first"] or not tokens["last"]:
        return ""
    try:
        local = pattern.format(**tokens)
    except KeyError as exc:
        raise ValueError(f"Invalid email pattern token: {exc}") from exc
    local = re.sub(r"[^a-z0-9._-]", "", local.casefold())
    local = re.sub(r"([._-])\1+", r"\1", local).strip("._-")
    return local


def generate_email(pattern: str, first_name: object, last_name: object, domain: object) -> str:
    normalized_domain = normalize_domain(domain)
    if normalized_domain == MISSING_VALUE:
        return MISSING_VALUE
    local = render_local_part(pattern, first_name, last_name)
    if not local:
        return MISSING_VALUE
    return f"{local}@{normalized_domain}"


def infer_patterns(
    first_name: object,
    last_name: object,
    email: object,
    company_domain: object | None = None,
) -> tuple[str, ...]:
    normalized_email = normalize_email(email)
    if normalized_email == MISSING_VALUE or "@" not in normalized_email:
        return ()
    local, email_domain = normalized_email.rsplit("@", 1)
    expected_domain = normalize_domain(company_domain) if company_domain is not None else MISSING_VALUE
    if expected_domain != MISSING_VALUE and email_domain != expected_domain:
        return ()

    matches: list[str] = []
    for pattern in SUPPORTED_PATTERNS:
        rendered = render_local_part(pattern, first_name, last_name)
        if rendered and rendered == local:
            matches.append(pattern)
    return tuple(matches)


def infer_best_pattern(
    first_name: object,
    last_name: object,
    email: object,
    company_domain: object | None = None,
) -> str | None:
    matches = infer_patterns(first_name, last_name, email, company_domain)
    # SUPPORTED_PATTERNS is intentionally ordered from more informative/common to
    # less specific formats, which resolves ambiguous one-letter/same-name cases.
    return matches[0] if matches else None
