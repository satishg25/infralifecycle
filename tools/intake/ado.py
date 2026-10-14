"""Azure DevOps work item -> request.v1.

Expected payload: the work item REST shape  {"id": 123, "fields": {"Custom.AppName": ...}}.
EDIT FIELD_MAP to your process template's field reference names.
"""
from .common import IntakeError, build_request

PREFIX = "ADO"
FIELD_MAP = {
    "name": "Custom.AppName", "environment": "Custom.Environment", "sizing": "Custom.Size",
    "image": "Custom.OSImage", "network_profile": "Custom.Network", "middleware": "Custom.Middleware",
    "data_disk_gb": "Custom.DataDiskGB", "owner": "Custom.Owner", "ttl_days": "Custom.TtlDays",
    "change_ref": "Custom.Change",
}


def extract(payload: dict) -> dict:
    if not isinstance(payload, dict) or "id" not in payload:
        raise IntakeError(["ADO payload needs a work item 'id'"])
    wi = payload.get("fields") or {}
    if not isinstance(wi, dict):
        raise IntakeError(["ADO 'fields' must be an object"])
    return build_request(PREFIX, payload["id"], {k: wi.get(v) for k, v in FIELD_MAP.items()})
