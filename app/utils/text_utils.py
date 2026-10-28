from __future__ import annotations

import re

from app.constants import MISSING_VALUE
from app.core.normalizer import (
    clean_text,
    normalize_domain as _normalize_domain,
    normalize_linkedin_url as _normalize_linkedin_url,
)


def clean_missing(value: object) -> str:
    return clean_text(value)


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def normalize_domain(value: object) -> str:
    return _normalize_domain(value)


def normalize_linkedin_url(value: object) -> str:
    return _normalize_linkedin_url(value)


def excel_safe(value: object) -> str:
    text = clean_missing(value)
    if text != MISSING_VALUE and text.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text
