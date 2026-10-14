#!/usr/bin/env python3
"""Validate a JSON/YAML document against a contract schema.

Usage: validate_contract.py <schema.json> <document.(json|yml)>
Exit 0 = valid, 1 = invalid (all errors printed), 2 = usage/IO error.
Used by CI and by the intake workflow BEFORE any credentials are touched.
"""
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


def load(path: Path):
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        schema, doc = load(Path(argv[1])), load(Path(argv[2]))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(doc), key=lambda e: list(e.path))
    for err in errors:
        loc = "/".join(str(p) for p in err.path) or "<root>"
        print(f"INVALID {loc}: {err.message}")
    if not errors:
        print(f"OK {argv[2]} conforms to {schema.get('$id', argv[1])}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
