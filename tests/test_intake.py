"""Intake adapter tests. Run: python -m unittest discover -s tests"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from intake import ado, custom, servicenow  # noqa: E402
from intake.common import IntakeError  # noqa: E402

FX = ROOT / "tests" / "intake"


def load(name):
    return json.loads((FX / name).read_text())


class Good(unittest.TestCase):
    def test_servicenow(self):
        r = servicenow.extract(load("servicenow.json"))
        self.assertEqual(r["request_id"], "RITM-0012345")
        self.assertEqual((r["sizing"], r["environment"], r["middleware"], r["image"]),
                         ("medium", "lab", "jboss", "rhel8-std"))
        self.assertEqual((r["data_disk_gb"], r["ttl_days"]), (200, 7))

    def test_ado(self):
        r = ado.extract(load("ado.json"))
        self.assertEqual(r["request_id"], "ADO-0123")
        self.assertEqual((r["environment"], r["sizing"], r["middleware"], r["ttl_days"]),
                         ("dev", "small", "none", 14))

    def test_custom(self):
        r = custom.extract(load("custom.json"))
        self.assertEqual(r["request_id"], "APP-000123")
        self.assertEqual(r["sizing"], "large")

    def test_cli_output_passes_contract_gate(self):
        for src, f in (("servicenow", "servicenow.json"), ("ado", "ado.json"), ("custom", "custom.json")):
            out = ROOT / ".state" / f"intake_{src}.json"
            p = subprocess.run([sys.executable, str(ROOT / "tools/intake_adapter.py"), src, str(FX / f),
                                "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            v = subprocess.run([sys.executable, str(ROOT / "tools/validate_contract.py"),
                                str(ROOT / "contracts/request.v1.schema.json"), str(out)])
            self.assertEqual(v.returncode, 0)


class Bad(unittest.TestCase):
    def fails(self, fn, payload, needle):
        with self.assertRaises(IntakeError) as cm:
            fn(payload)
        self.assertIn(needle, " | ".join(cm.exception.errors))

    def sn(self, **over):
        p = load("servicenow.json")
        p["variables"].update(over)
        return p

    def test_missing_required(self):
        p = load("servicenow.json")
        del p["variables"]["u_size"]
        self.fails(servicenow.extract, p, "Missing required field: 'sizing'")

    def test_injection_string_rejected_by_schema(self):
        self.fails(servicenow.extract, self.sn(u_app_name="x; rm -rf /"), "name")

    def test_unknown_size_label(self):
        self.fails(servicenow.extract, self.sn(u_size="Gigantic"), "sizing")

    def test_bad_number(self):
        self.fails(servicenow.extract, self.sn(u_ttl_days="7 days"), "must be a whole number")

    def test_out_of_range(self):
        self.fails(servicenow.extract, self.sn(u_ttl_days="500"), "ttl_days")

    def test_multiline(self):
        self.fails(servicenow.extract, self.sn(u_owner="a\nb"), "single line")

    def test_no_reference(self):
        self.fails(servicenow.extract, {"variables": {}}, "needs a 'number'")
        self.fails(ado.extract, {"fields": {}}, "work item 'id'")

    def test_unparseable_reference(self):
        self.fails(custom.extract, {"reference": "no-digits"}, "Cannot derive a request id")

    def test_custom_cannot_set_privileged_fields(self):
        p = load("custom.json")
        p["request_id"] = "ABC-9999"
        p["contract"] = "x"
        self.fails(custom.extract, p, "Field not accepted from intake")

    def test_object_value_rejected(self):
        p = load("custom.json")
        p["name"] = {"$ne": 1}
        self.fails(custom.extract, p, "unsupported value type")


if __name__ == "__main__":
    unittest.main()
