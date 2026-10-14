"""Custom app -> request.v1. The app posts flat JSON using request field names directly:
  {"reference": "APP-000123", "name": "sample-app01", "sizing": "medium", ...}
"""
from .common import ALLOWED, IntakeError, build_request

PREFIX = "APP"


def extract(payload: dict) -> dict:
    if not isinstance(payload, dict) or "reference" not in payload:
        raise IntakeError(["Custom payload needs a 'reference'"])
    fields = {k: v for k, v in payload.items() if k != "reference"}
    return build_request(PREFIX, payload["reference"], fields)
