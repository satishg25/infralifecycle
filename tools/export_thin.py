#!/usr/bin/env python3
"""Export the customer-handover subset: roles + thin playbooks only (no framework layers).

The result runs on its own - no profile, no request file, no dispatcher. Use it to lift the
relevant YAML into a customer's repo, then rewrite to their conventions.

Usage: export_thin.py <out_dir> [--force]
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROLES = ["jboss", "validation", "rhel_baseline"]          # add tomcat here when it exists
PLAYBOOKS = {"ansible/playbooks/thin/jboss_standalone.yml": "playbooks/jboss_standalone.yml"}
FRAMEWORK_WORDS = ("capability_dispatch", "machine_resolve", "machine_spec", "machine_result", "profile_dir", "cap_cfg")

CFG = """[defaults]
roles_path = roles
inventory = inventory.yml
callback_result_format = yaml
"""
REQS = """---
collections:
  - name: ansible.posix
    version: "==2.2.2"
  - name: community.general
    version: "==13.5.0"
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--force", action="store_true", help="overwrite a non-empty out dir")
    args = ap.parse_args()
    out: Path = args.out
    if out.exists() and any(out.iterdir()) and not args.force:
        print(f"{out} is not empty (use --force)")
        return 1
    out.mkdir(parents=True, exist_ok=True)
    for role in ROLES:
        shutil.copytree(ROOT / "ansible/roles" / role, out / "roles" / role, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__"))
    for src, dst in PLAYBOOKS.items():
        (out / dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / src, out / dst)
    shutil.copytree(ROOT / "examples/baloise", out / "examples", dirs_exist_ok=True)
    shutil.copy(ROOT / "examples/baloise/inventory.yml", out / "inventory.yml")
    shutil.copy(ROOT / ".ansible-lint", out / ".ansible-lint")
    shutil.copy(ROOT / "docs/BALOISE-HANDOVER.md", out / "README.md")
    (out / "ansible.cfg").write_text(CFG)
    (out / "requirements.yml").write_text(REQS)
    leaks = [str(p.relative_to(out)) for p in out.rglob("*.yml") if any(w in p.read_text() for w in FRAMEWORK_WORDS)]
    if leaks:
        print("FRAMEWORK LEAK in: " + ", ".join(leaks))
        return 1
    print(f"exported to {out}: roles {ROLES}, playbooks {list(PLAYBOOKS.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
