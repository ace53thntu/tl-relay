"""Read and write the JSON Lines registers the drift scripts share."""
import json
import unicodedata


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(path, items):
    with open(path, "w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def bad_char(value):
    for ch in value:
        if unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp"):
            return ch
    return None


def register_field(row, n, key):
    value = row.get(key) if isinstance(row, dict) else None
    if not isinstance(value, str) or value == "":
        raise ValueError(f"row {n}: '{key}' must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"row {n}: '{key}' must not carry surrounding whitespace")
    ch = bad_char(value)
    if ch is not None:
        raise ValueError(f"row {n}: '{key}' holds U+{ord(ch):04X}")
    return value


def register_text(row, n, key):
    value = row.get(key) if isinstance(row, dict) else None
    if not isinstance(value, str):
        raise ValueError(f"row {n}: '{key}' must be a string")
    return value


def unique_ids(ids):
    first = {}
    for n, value in enumerate(ids, 1):
        if value in first:
            raise ValueError(f"row {n}: id '{value}' repeats row {first[value]}")
        first[value] = n


def require_columns(fieldnames, names):
    for name in names:
        if not fieldnames or name not in fieldnames:
            raise ValueError(f"missing column {name}")
