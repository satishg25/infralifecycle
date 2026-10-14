"""Shared core for intake adapters: source payload -> request.v1.

Each adapter only EXTRACTS a flat {request_field: raw_value} dict plus a request_id from its
source payload. This module does the strict part: allow-list, type coercion, label->logical
value maps, schema validation. Source payloads are untrusted; nothing is evaluated or templated.
"""
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts" / "request.v1.schema.json").read_text())

# Fields an intake source may set. request_id/contract/topology are set here, never by the source.
ALLOWED = {"name", "environment", "sizing", "image", "network_profile", "placement", "middleware",
           "node_count", "data_disk_gb", "owner", "ttl_days", "change_ref"}
INT_FIELDS = {"node_count", "data_disk_gb", "ttl_days"}
REQUIRED = {"name", "environment", "sizing", "image", "network_profile"}

# Catalogue-item display labels -> logical values. EDIT per customer catalogue item.
VALUE_MAPS = {
    "sizing": {"Small": "small", "Medium": "medium", "Large": "large"},
    "environment": {"Lab": "lab", "Development": "dev", "Test": "test", "Production": "prod"},
    "middleware": {"None": "none", "No middleware": "none", "JBoss": "jboss", "JBoss EAP": "jboss"},
    "image": {"RHEL 8": "rhel8-std", "RHEL 8 Standard": "rhel8-std"},
}


class IntakeError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def request_id(prefix: str, raw: object) -> str:
    """Build a request_id matching ^[A-Z]{2,6}-[0-9]{4,8}$ from a source reference.

    Takes the trailing digits of the source reference (RITM0012345 -> 0012345) and pads to 4.
    """
    digits = re.search(r"([0-9]{1,8})$", str(raw).strip())
    if not digits:
        raise IntakeError([f"Cannot derive a request id from reference {str(raw)[:40]!r}"])
    return f"{prefix}-{digits.group(1).zfill(4)}"


def build_request(prefix: str, ref: object, fields: dict) -> dict:
    errors: list[str] = []
    try:
        rid = request_id(prefix, ref)
    except IntakeError as exc:
        return _raise(exc.errors)
    req: dict = {"contract": "request.v1", "request_id": rid, "topology": "standalone"}
    for key in fields:
        if key not in ALLOWED:
            errors.append(f"Field not accepted from intake: {str(key)[:40]!r}")
    for key in sorted(ALLOWED & set(fields)):
        raw = fields[key]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            continue
        if isinstance(raw, bool) or not isinstance(raw, (str, int)):
            errors.append(f"Field '{key}' has an unsupported value type")
            continue
        raw = str(raw).strip()
        if "\n" in raw or "\r" in raw:
            errors.append(f"Field '{key}' must be a single line")
            continue
        raw = VALUE_MAPS.get(key, {}).get(raw, raw)
        if key in INT_FIELDS:
            if not re.fullmatch(r"[0-9]{1,5}", raw):
                errors.append(f"Field '{key}' must be a whole number")
                continue
            req[key] = int(raw)
        else:
            req[key] = raw
    for key in sorted(REQUIRED - set(req)):
        errors.append(f"Missing required field: '{key}'")
    for err in sorted(Draft202012Validator(SCHEMA).iter_errors(req), key=lambda e: list(e.path)):
        loc = "/".join(str(p) for p in err.path) or "<root>"
        msg = f"{loc}: {err.message}"[:200]
        if msg not in errors and not msg.endswith("is a required property"):
            errors.append(msg)
    if errors:
        return _raise(errors)
    return req


def _raise(errors):
    raise IntakeError(errors)
