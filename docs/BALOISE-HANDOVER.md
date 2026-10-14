# Thin layer: JBoss EAP 8 standalone on an existing RHEL 8 VM

A calling application (custom app / AAP job template) runs one playbook with flat extra variables.
No profile, no request file, no framework. The VM must already exist and be in the inventory.

## Run
```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook playbooks/jboss_standalone.yml -i inventory.yml -e @examples/jboss_standalone.vars.yml
ansible-playbook playbooks/jboss_standalone.yml -i inventory.yml -e @examples/jboss_standalone.vars.yml --check --diff   # preview
```

## Input contract (flat extra variables; all optional unless stated)
| Variable | Default | Meaning |
|---|---|---|
| `target_hosts` | `middleware_nodes` | inventory group / host pattern |
| `run_baseline` | `false` | also apply `rhel_baseline` (skip if their VM role already does) |
| `run_validation` | `true` | read-only OS + JBoss validation, evidence JSON under `.state/reports` |
| `rhel_baseline_ntp_servers` | - | **required** when `run_baseline: true` |
| `rhel_baseline_data_volumes` | `[]` | list of `{role, device, vg, lv, mount, fs}`; `device` must be a stable `/dev/disk/by-*` path |
| `jboss_install_source` | `rpm` | `rpm` (Satellite) now; `archive` (internal repo) is a placeholder |
| `jboss_bind_address` | empty | empty = loopback only; else an IPv4 address. The management port is never rebound |
| `jboss_firewall_ports` | `[]` | e.g. `["8080/tcp"]`; nothing opens unless listed |
| other `jboss_*`, `rhel_baseline_*`, `validation_*` | role defaults | see each role's `defaults/main.yml` and `meta/argument_specs.yml` |

Bad input stops the run before any host is touched, with one precise message per check.

## What is in here
`roles/jboss` (the new work), `roles/validation` (read-only checks + evidence), `roles/rhel_baseline`
(only if they have no baseline of their own - then delete its task and role), `playbooks/jboss_standalone.yml`.

## Behaviour to know
- Fails closed: non-RHEL host, missing NTP list (with baseline), bad bind address or port syntax all stop the run.
- Check mode previews package and file changes; steps that need an installed service (start, CLI, validation) are skipped in a preview.
- Idempotent by design: a second run should report `changed=0` on the target (not yet confirmed on a real host).

## NOT yet verified on a real host (confirm on first run)
dnf group install from their Satellite content view, the `jboss-eap8` group name and `eap8-standalone` unit,
EAP_HOME path, the `jboss-cli` interface/welcome-content changes, `/health/ready`, the service account, firewalld
and LVM tasks, and handler behaviour.

## Rewrite checklist when taking this into their repo
Their role/variable naming and prefixes, their Satellite repo/activation details, their baseline (CIS/STIG),
their secrets/credential mechanism (AAP credentials), their inventory source, collections from their automation hub.
