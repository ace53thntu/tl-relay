"""Read and write the JSON Lines registers the drift scripts share."""
import json


def load_jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(path, items):
    with open(path, "w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def register_field(row, n, key):
    value = row.get(key) if isinstance(row, dict) else None
    if not isinstance(value, str) or value == "":
        raise ValueError(f"row {n}: '{key}' must be a non-empty string")
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
