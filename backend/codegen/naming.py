"""Naming conventions shared by every agent so generated code and specs stay consistent."""

import keyword
import re

_UNCOUNTABLE = {"species", "series", "news", "staff", "equipment", "gps", "data", "information", "maintenance",
                "attendance", "software", "feedback", "furniture", "luggage", "personnel", "livestock", "poultry"}

_IRREGULAR_PLURALS = {
    "person": "people",
    "child": "children",
    "man": "men",
    "woman": "women",
    "status": "statuses",
    "address": "addresses",
    "class": "classes",
    "category": "categories",
    "inventory": "inventories",
    "staff": "staff",
    "equipment": "equipment",
    "news": "news",
    "series": "series",
}

# Names that clash with Python keywords, SQLAlchemy declarative attributes or our own generated code.
RESERVED_FIELD_NAMES = {
    "metadata", "registry", "query", "session", "id_", "self", "cls", "type_", "model_config",
    "model_fields", "json", "dict", "copy", "schema", "validate", "fields",
}


def words(text: str) -> list:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(text))
    return [w for w in re.split(r"[^A-Za-z0-9]+", text) if w]


def to_snake(text: str) -> str:
    result = "_".join(w.lower() for w in words(text)) or "item"
    if result[0].isdigit():
        result = f"n_{result}"
    return result


def to_pascal(text: str) -> str:
    result = "".join(
        (w[:1].upper() + w[1:].lower()) if w.isupper() else (w[:1].upper() + w[1:]) for w in words(text)
    )
    if not result:
        return "Item"
    if result[0].isdigit():
        result = f"N{result}"
    return result


def to_camel(text: str) -> str:
    pascal = to_pascal(text)
    return pascal[:1].lower() + pascal[1:]


def to_kebab(text: str) -> str:
    return to_snake(text).replace("_", "-")


def humanize(text: str) -> str:
    parts = words(text)
    if parts and parts[-1].lower() == "id" and len(parts) > 1:
        parts = parts[:-1]
    label = " ".join(p.lower() for p in parts)
    return label[:1].upper() + label[1:] if label else ""


def pluralize(word: str) -> str:
    """Pluralize the last word of a snake/space separated name."""
    if not word:
        return word
    sep = "_" if "_" in word else (" " if " " in word else "")
    head, last = (word.rsplit(sep, 1) if sep else ("", word))
    lower = last.lower()
    if lower in _UNCOUNTABLE:
        plural = last
    elif lower in _IRREGULAR_PLURALS:
        plural = _IRREGULAR_PLURALS[lower]
        plural = plural if last.islower() else plural[:1].upper() + plural[1:]
    elif re.search(r"[^aeiou]y$", lower):
        plural = last[:-1] + "ies"
    elif re.search(r"(s|x|z|ch|sh)$", lower):
        plural = last + "es"
    else:
        plural = last + "s"
    return f"{head}{sep}{plural}" if sep else plural


def singularize(word: str) -> str:
    lower = word.lower()
    for singular, plural in _IRREGULAR_PLURALS.items():
        if lower == plural:
            return singular
    if lower in _UNCOUNTABLE:
        return word
    if lower.endswith("ies") and len(lower) > 4:
        return word[:-3] + "y"
    if re.search(r"(ss|us|is|as)$", lower):
        return word
    if re.search(r"(xes|ches|shes|sses|zes)$", lower) or re.search(r"(?<![aeiou])uses$", lower):
        return word[:-2]
    if lower.endswith("s") and len(lower) > 3:
        return word[:-1]
    return word


def safe_identifier(name: str) -> str:
    """Return a snake_case identifier that is valid in Python, SQL and JavaScript."""
    ident = to_snake(name)
    if keyword.iskeyword(ident) or ident in RESERVED_FIELD_NAMES or ident in {"class", "default", "function", "new", "delete"}:
        ident = f"{ident}_value"
    return ident


def table_name(entity_name: str) -> str:
    return pluralize(to_snake(entity_name))


def route_segment(entity_name: str) -> str:
    return pluralize(to_snake(entity_name)).replace("_", "-")


def fk_field_name(entity_name: str) -> str:
    return f"{to_snake(entity_name)}_id"


def slugify(text: str) -> str:
    return to_kebab(text)[:60] or "app"
