from __future__ import annotations

COLOR_SCHEMES: dict[str, dict[str, str]] = {
    "Excel Green": {
        "accent": "#217346",
        "hover": "#185C37",
        "strong": "#0F5C36",
    },
    "Professional Blue": {
        "accent": "#1565C0",
        "hover": "#0D47A1",
        "strong": "#0B3D91",
    },
    "Teal": {
        "accent": "#00897B",
        "hover": "#00695C",
        "strong": "#005B50",
    },
    "Purple": {
        "accent": "#6A1B9A",
        "hover": "#4A148C",
        "strong": "#3F0F78",
    },
    "Orange": {
        "accent": "#EF6C00",
        "hover": "#E65100",
        "strong": "#BF4700",
    },
    "Slate": {
        "accent": "#455A64",
        "hover": "#37474F",
        "strong": "#263238",
    },
}

APPEARANCE_MODES = ["System", "Light", "Dark"]
DEFAULT_COLOR_SCHEME = "Excel Green"
DEFAULT_APPEARANCE_MODE = "System"


def get_palette(name: str | None) -> dict[str, str]:
    return COLOR_SCHEMES.get(name or DEFAULT_COLOR_SCHEME, COLOR_SCHEMES[DEFAULT_COLOR_SCHEME])

DEFAULT_VALIDATION_COLORS: dict[str, str] = {
    "outside_tal": "#FFC7CE",
    "suppressed": "#FFD59A",
}


def normalize_hex_color(value: str | None, fallback: str) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
            return text.upper()
        except ValueError:
            pass
    return fallback.upper()
