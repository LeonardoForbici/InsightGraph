"""Configuration parser with YAML/JSON parsing and JSON Schema validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator


class ConfigParser:
    def __init__(self, schema_path: str | Path):
        self.schema_path = Path(schema_path)
        self.schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        self.validator = Draft202012Validator(self.schema)

    def parse_yaml(self, raw: str) -> dict[str, Any]:
        payload = yaml.safe_load(raw) or {}
        if not isinstance(payload, dict):
            raise ValueError("YAML payload must be an object")
        self.validate(payload)
        return payload

    def parse_json(self, raw: str) -> dict[str, Any]:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("JSON payload must be an object")
        self.validate(payload)
        return payload

    def validate(self, payload: dict[str, Any]) -> None:
        errors = sorted(self.validator.iter_errors(payload), key=lambda e: e.path)
        if not errors:
            return
        first = errors[0]
        pointer = "/".join(str(x) for x in first.path)
        raise ValueError(f"Invalid config at '{pointer or '$'}': {first.message}")

    def pretty_print(self, payload: dict[str, Any], fmt: str = "yaml") -> str:
        self.validate(payload)
        normalized = json.loads(json.dumps(payload, ensure_ascii=False))
        if fmt == "json":
            return json.dumps(normalized, indent=2, ensure_ascii=False, sort_keys=True)
        if fmt != "yaml":
            raise ValueError("fmt must be 'yaml' or 'json'")
        return yaml.safe_dump(normalized, sort_keys=False, allow_unicode=True)
