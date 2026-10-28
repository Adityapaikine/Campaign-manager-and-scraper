"""Shared Excel-style value and condition filtering, independent of the UI."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import fnmatch

from app.constants import MISSING_VALUE


def display_value(value):
    text = str(value if value is not None else "").strip()
    return "" if text == MISSING_VALUE else text


def value_key(value):
    return display_value(value).casefold()


def number(value):
    text = display_value(value).replace(",", "").replace("$", "").replace("₹", "").strip()
    try:
        result = Decimal(text.rstrip("%"))
        if not result.is_finite():
            return None
        return result / 100 if text.endswith("%") else result
    except InvalidOperation:
        return None


def date_value(value):
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(display_value(value), fmt)
        except ValueError:
            pass
    return None


def matches_condition(value, rule):
    if not rule or rule.get("operator", "all") == "all":
        return True
    op, argument = rule["operator"], rule.get("value", "")
    text, needle = value_key(value), str(argument).strip().casefold()
    if op == "blank": return not text
    if op == "not_blank": return bool(text)
    if op == "contains": return needle in text
    if op == "not_contains": return needle not in text
    if op == "starts": return text.startswith(needle)
    if op == "ends": return text.endswith(needle)
    if op in {"equals", "not_equals"} and rule.get("type", "text") == "text":
        matched = fnmatch.fnmatchcase(text, needle) if any(c in needle for c in "*?") else text == needle
        return matched if op == "equals" else not matched
    converter = date_value if rule.get("type") == "date" else number
    left, right = converter(value), converter(argument)
    if left is None or right is None: return False
    if op == "equals": return left == right
    if op == "not_equals": return left != right
    if op == "gt": return left > right
    if op == "gte": return left >= right
    if op == "lt": return left < right
    if op == "lte": return left <= right
    return False
