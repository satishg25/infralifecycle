#!/usr/bin/env python3
"""Convert a source payload to request.v1.   Usage: intake_adapter.py <servicenow|ado|custom> <payload.json> [--out FILE]
Exit 0 = request written/printed; 1 = rejected (errors printed, one per line)."""
import argparse
import importlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from intake.common import IntakeError  # noqa: E402

SOURCES = ("servicenow", "ado", "custom")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=SOURCES)
    ap.add_argument("payload")
    ap.add_argument("--out")
    args = ap.parse_args()
    try:
        payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
        req = importlib.import_module(f"intake.{args.source}").extract(payload)
    except (OSError, ValueError) as exc:
        print(f"cannot read payload: {exc}")
        return 1
    except IntakeError as exc:
        print("\n".join(exc.errors))
        return 1
    text = json.dumps(req, indent=2) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text)
        print(f"wrote {args.out}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
