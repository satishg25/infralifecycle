"""ServiceNow RITM -> request.v1.

Expected payload (e.g. from a Flow Designer REST step or the Table API sc_req_item +
variables), edit FIELD_MAP to your catalogue item's variable names:
  {"number": "RITM0012345", "variables": {"u_app_name": "sample-app01", ...}}
A variable may be a plain value or {"value": ..., "display_value": ...}; the raw value is used.
"""
from .common import IntakeError, build_request

PREFIX = "RITM"
# request field <- ServiceNow catalogue variable name   (EDIT per catalogue item)
FIELD_MAP = {
    "name": "u_app_name", "environment": "u_environment", "sizing": "u_size",
    "image": "u_os_image", "network_profile": "u_network", "middleware": "u_middleware",
    "data_disk_gb": "u_data_disk_gb", "owner": "u_owner", "ttl_days": "u_ttl_days",
    "change_ref": "u_change",
}


def extract(payload: dict) -> dict:
    if not isinstance(payload, dict) or "number" not in payload:
        raise IntakeError(["ServiceNow payload needs a 'number' (RITM reference)"])
    variables = payload.get("variables") or {}
    if not isinstance(variables, dict):
        raise IntakeError(["ServiceNow 'variables' must be an object"])
    fields = {}
    for req_field, var in FIELD_MAP.items():
        val = variables.get(var)
        fields[req_field] = val.get("value") if isinstance(val, dict) else val
    return build_request(PREFIX, payload["number"], fields)
