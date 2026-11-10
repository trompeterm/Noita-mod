from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_SCHEMA_CACHE: dict[str, Draft202012Validator] = {}


def _schema_path(name: str) -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "schemas" / f"{name}.schema.json"


def get_validator(name: str) -> Draft202012Validator:
    if name not in _SCHEMA_CACHE:
        schema = json.loads(_schema_path(name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        _SCHEMA_CACHE[name] = Draft202012Validator(schema)
    return _SCHEMA_CACHE[name]


def validate_document(name: str, document: dict[str, Any]) -> list[str]:
    validator = get_validator(name)
    errors: list[str] = []
    for error in sorted(validator.iter_errors(document), key=lambda e: e.path):
        path = "/".join(str(part) for part in error.absolute_path)
        location = path or "<root>"
        errors.append(f"{location}: {error.message}")
    return errors


def load_and_validate_json(path: Path, schema_name: str) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_document(schema_name, document)
    if errors:
        raise ValueError(f"Validation failed for {path}:\n" + "\n".join(errors))
    return document
