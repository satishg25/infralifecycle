#!/usr/bin/env python3
"""Strictly convert a GitHub Issue Form body into request.json (request.v1).

SECURITY: the issue body is untrusted input. This script
  * receives it via environment variables only (never shell interpolation),
  * accepts ONLY the headings defined in form_fields.py (anything else is an error),
  * never evaluates or templates any value, and
  * leaves final validation to request.v1.schema.json (run right after, before any credential).
Exit 0 = request.json written; exit 1 = errors printed (one per line, safe to post as a comment).
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from form_fields import (CONFIRM_TEXT, FIELDS, FORM_TO_REQUEST_VALUE, INT_FIELDS,  # noqa: E402
                         LABEL_TO_FIELD, NO_RESPONSE)

MAX_BODY = 20_000


def parse_sections(body: str) -> tuple[dict[str, str], list[str]]:
    errors: list[str] = []
    sections: dict[str, str] = {}
    parts = re.split(r"(?m)^###\s+(.+?)\s*$", body.replace("\r\n", "\n"))
    # parts = [preamble, heading1, text1, heading2, text2, ...]
    if parts[0].strip():
        errors.append("Unexpected text before the first form field - submit the issue using the form")
    for heading, text in zip(parts[1::2], parts[2::2]):
        if heading not in LABEL_TO_FIELD:
            errors.append(f"Unknown form field: '{heading[:60]}'")
        elif heading in sections:
            errors.append(f"Duplicate form field: '{heading}'")
        else:
            sections[heading] = text.strip()
    return sections, errors


def convert(body: str, issue_number: int) -> tuple[dict, list[str]]:
    errors: list[str] = []
    if len(body) > MAX_BODY:
        return {}, [f"Issue body is too large (> {MAX_BODY} characters)"]
    sections, errors = parse_sections(body)
    request: dict = {"contract": "request.v1", "request_id": f"REQ-{issue_number:04d}", "topology": "standalone"}
    for field, label, kind, required in FIELDS:
        raw = sections.get(label)
        if raw is None or raw == NO_RESPONSE or raw == "":
            if required:
                errors.append(f"Missing required field: '{label}'")
            continue
        if kind == "checkbox":
            if not re.search(r"(?m)^- \[[xX]\] " + re.escape(CONFIRM_TEXT) + r"\s*$", raw):
                errors.append("The confirmation checkbox must be ticked")
            continue
        if "\n" in raw:
            errors.append(f"Field '{label}' must be a single line")
            continue
        if field in INT_FIELDS:
            if not re.fullmatch(r"[0-9]{1,5}", raw):
                errors.append(f"Field '{label}' must be a whole number")
                continue
            request[field] = int(raw)
        else:
            request[field] = FORM_TO_REQUEST_VALUE.get(field, {}).get(raw, raw)
    return request, errors


def main() -> int:
    body = os.environ.get("ISSUE_BODY", "")
    try:
        number = int(os.environ["ISSUE_NUMBER"])
    except (KeyError, ValueError):
        print("ISSUE_NUMBER missing or not a number")
        return 1
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "build/request.json")
    request, errors = convert(body, number)
    if errors:
        print("\n".join(errors))
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(request, indent=2) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
