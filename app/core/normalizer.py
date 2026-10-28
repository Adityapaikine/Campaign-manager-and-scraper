from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from app.constants import MISSING_VALUE

GENERIC_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.uk",
        "hotmail.com",
        "hotmail.co.uk",
        "outlook.com",
        "live.com",
        "msn.com",
        "icloud.com",
        "me.com",
        "aol.com",
        "proton.me",
        "protonmail.com",
    }
)

_COMPANY_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "llc", "llp",
    "ltd", "limited", "plc", "gmbh", "ag", "sa", "sas", "bv", "nv", "pty",
    "pvt", "private", "holdings", "holding",
}

_PREFIXES = {"mr", "mrs", "ms", "miss", "dr", "prof", "sir"}
_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md"}

_COUNTRY_ALIASES = {
    "us": "united states",
    "usa": "united states",
    "u s": "united states",
    "united states of america": "united states",
    "uk": "united kingdom",
    "gb": "united kingdom",
    "great britain": "united kingdom",
    "uae": "united arab emirates",
}


@dataclass(frozen=True, slots=True)
class NormalizedRecord:
    values: dict[str, str]

    def get(self, field: str, default: str = MISSING_VALUE) -> str:
        return self.values.get(field, default)


def clean_text(value: object) -> str:
    if value is None:
        return MISSING_VALUE
    text = str(value).strip()
    if not text or text.casefold() in {"none", "null", "nan", "n/a", "undefined"}:
        return MISSING_VALUE
    return text


def _ascii_fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_whitespace(value: object) -> str:
    text = clean_text(value)
    if text == MISSING_VALUE:
        return MISSING_VALUE
    return re.sub(r"\s+", " ", text).strip()


def normalize_name(value: object) -> str:
    """Return a comparison-safe lowercase name without modifying source data."""
    text = normalize_whitespace(value)
    if text == MISSING_VALUE:
        return MISSING_VALUE
    text = _ascii_fold(text).casefold()
    text = text.replace("’", "'")
    text = re.sub(r"[^a-z0-9'\-\s]", " ", text)
    tokens = [token.strip(".'-") for token in re.split(r"\s+", text) if token.strip(".'-")]
    while tokens and tokens[0] in _PREFIXES:
        tokens.pop(0)
    while tokens and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens) if tokens else MISSING_VALUE


def normalize_company_name(value: object) -> str:
    text = normalize_whitespace(value)
    if text == MISSING_VALUE:
        return MISSING_VALUE
    text = _ascii_fold(text).casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [token for token in re.split(r"\s+", text) if token]
    while tokens and tokens[-1] in _COMPANY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens) if tokens else MISSING_VALUE


def normalize_domain(value: object) -> str:
    text = clean_text(value)
    if text == MISSING_VALUE:
        return MISSING_VALUE

    candidate = text.strip().lower()
    # Accept an email address as a convenience when the caller is extracting a
    # domain for validation/comparison. This is not used to overwrite source data.
    if "@" in candidate and "/" not in candidate:
        candidate = candidate.rsplit("@", 1)[-1]
    if "://" not in candidate:
        candidate = "https://" + candidate
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return MISSING_VALUE

    host = (parsed.hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return MISSING_VALUE
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return MISSING_VALUE


def is_valid_domain(value: object, *, require_public_style: bool = True) -> bool:
    domain = normalize_domain(value)
    if domain == MISSING_VALUE or len(domain) > 253:
        return False
    try:
        ipaddress.ip_address(domain)
        return False
    except ValueError:
        pass
    if require_public_style and "." not in domain:
        return False
    labels = domain.split(".")
    for label in labels:
        if not 1 <= len(label) <= 63:
            return False
        if label.startswith("-") or label.endswith("-"):
            return False
        if not re.fullmatch(r"[a-z0-9-]+", label):
            return False
    tld = labels[-1]
    if tld.startswith("xn--"):
        return len(tld) > 4
    return bool(re.fullmatch(r"[a-z]{2,63}", tld))


def is_generic_email_domain(value: object) -> bool:
    domain = normalize_domain(value)
    return domain in GENERIC_EMAIL_DOMAINS


def normalize_url(value: object) -> str:
    text = clean_text(value)
    if text == MISSING_VALUE:
        return MISSING_VALUE
    candidate = text.strip()
    if "://" not in candidate:
        candidate = "https://" + candidate
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return MISSING_VALUE
    if parsed.scheme.casefold() not in {"http", "https"}:
        return MISSING_VALUE
    host = (parsed.hostname or "").lower().strip(".")
    if not host:
        return MISSING_VALUE
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return MISSING_VALUE
    if not is_valid_domain(host):
        return MISSING_VALUE
    netloc = host
    if parsed.port:
        netloc += f":{parsed.port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "")
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


def normalize_linkedin_url(value: object) -> str:
    text = clean_text(value)
    if text == MISSING_VALUE:
        return MISSING_VALUE
    candidate = text.strip()
    if "://" not in candidate:
        candidate = "https://" + candidate
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return MISSING_VALUE
    host = (parsed.hostname or "").casefold()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/{2,}", "/", parsed.path or "").rstrip("/")
    if host != "linkedin.com" or not re.fullmatch(r"/in/[^/]+", path, flags=re.IGNORECASE):
        return MISSING_VALUE
    return f"https://www.linkedin.com{path}"


def normalize_email(value: object) -> str:
    text = clean_text(value)
    if text == MISSING_VALUE:
        return MISSING_VALUE
    text = text.strip().casefold()
    if text.startswith("mailto:"):
        text = text[7:]
    return text


def is_valid_email(value: object) -> bool:
    email = normalize_email(value)
    if email == MISSING_VALUE or len(email) > 254 or email.count("@") != 1:
        return False
    local, domain = email.rsplit("@", 1)
    if not local or len(local) > 64:
        return False
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    if not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local, flags=re.IGNORECASE):
        return False
    return is_valid_domain(domain)


def normalize_phone(value: object) -> str:
    text = clean_text(value)
    if text == MISSING_VALUE:
        return MISSING_VALUE
    has_plus = text.lstrip().startswith("+")
    digits = re.sub(r"\D", "", text)
    if not digits:
        return MISSING_VALUE
    return ("+" if has_plus else "") + digits


def normalize_country(value: object) -> str:
    text = normalize_whitespace(value)
    if text == MISSING_VALUE:
        return MISSING_VALUE
    folded = _ascii_fold(text).casefold().replace(".", "")
    folded = re.sub(r"\s+", " ", folded).strip()
    return _COUNTRY_ALIASES.get(folded, folded)


def normalize_location_text(value: object) -> str:
    text = normalize_whitespace(value)
    if text == MISSING_VALUE:
        return MISSING_VALUE
    return _ascii_fold(text).casefold()


def normalize_employee_size(value: object) -> str:
    text = normalize_whitespace(value)
    if text == MISSING_VALUE:
        return MISSING_VALUE
    return text.casefold().replace(",", "").replace("employees", "").strip()


def normalize_revenue(value: object) -> str:
    text = normalize_whitespace(value)
    if text == MISSING_VALUE:
        return MISSING_VALUE
    return re.sub(r"\s+", "", text.casefold().replace(",", ""))


def normalize_industry(value: object) -> str:
    text = normalize_whitespace(value)
    if text == MISSING_VALUE:
        return MISSING_VALUE
    text = _ascii_fold(text).casefold()
    text = re.sub(r"[^a-z0-9&/+\-\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip() or MISSING_VALUE


def normalize_record(record: dict[str, str]) -> NormalizedRecord:
    values = {key: clean_text(value) for key, value in record.items()}
    values["First Name"] = normalize_name(record.get("First Name"))
    values["Last Name"] = normalize_name(record.get("Last Name"))
    values["Company Name"] = normalize_company_name(record.get("Company Name"))
    values["Company Website"] = normalize_domain(record.get("Company Website"))
    values["Business Email ID"] = normalize_email(record.get("Business Email ID"))
    values["Prospect LinkedIn Link"] = normalize_linkedin_url(record.get("Prospect LinkedIn Link"))
    values["Phone Number"] = normalize_phone(record.get("Phone Number"))
    values["Country"] = normalize_country(record.get("Country"))
    values["State"] = normalize_location_text(record.get("State"))
    values["City"] = normalize_location_text(record.get("City"))
    values["Company Size"] = normalize_employee_size(record.get("Company Size"))
    values["See All Company Size"] = normalize_employee_size(record.get("See All Company Size"))
    values["Revenue"] = normalize_revenue(record.get("Revenue"))
    values["Industry"] = normalize_industry(record.get("Industry"))
    return NormalizedRecord(values)
