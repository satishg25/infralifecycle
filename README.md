# platform-kit

A customer-agnostic baseline for request-driven infrastructure automation: **logical request → provider-neutral contracts → pluggable drivers/engines**. Switching customer = switching a *profile*, not editing roles.

> **Status:** core slice only (contracts, dispatcher, mock compute driver, profile). It contains no customer or employer code. Add a `LICENSE` and confirm hosting/IP approval before publishing or sharing beyond yourself.

## Layers

| Layer | Lives in | Customer-specific? |
|---|---|---|
| Request contract | `contracts/request.v1.schema.json` | No (logical values only, no secrets) |
| Resolve | `roles/machine_resolve` | No - maps logical names via the profile catalogue |
| Capability dispatch | `roles/capability_dispatch` | No - capability → driver binding from the profile |
| Drivers (`cap_<capability>_<driver>`) | `roles/cap_compute_mock` (more to come) | Provider-specific by design, isolated here |
| OS baseline + validation | `roles/rhel_baseline`, `roles/validation` | No - consume `machine_result` only |
| Workload roles | `roles/jboss` (EAP 8 standalone, RPM via Satellite; `archive` source is a placeholder), `tomcat` next | No |
| **Profile** | `profiles/<customer>/` | **Yes - the only thing that changes** |

## Contracts
- `machine_spec.v1` - provider-neutral input to compute drivers (CPU/RAM, logical refs, disks by role, tags).
- `machine_result.v1` - the ONLY thing downstream roles may consume (`fqdn`, `ip`, `disk_map` by-id paths, `state_ref`).
- Enforced twice: driver **inputs** via `meta/argument_specs.yml`, driver **outputs** by the dispatcher.

## Engines (how Ansible-for-datacentre and Terraform-for-cloud become one platform)
The `compute` capability has interchangeable drivers behind the same contract:

| Driver | Engine | Use |
|---|---|---|
| `mock` | Ansible | CI, learning, no infra (refused unless `policy.allow_mock: true`) |
| `existing` | Ansible | Bring-your-own-host: run baseline/workload roles against any RHEL 8 VM you already have |
| `azure`, `vmware` (planned) | Ansible modules | Datacentre / lab VMs |
| `terraform` (planned) | `cloud.terraform` wrapping a module whose variables = `machine_spec`, outputs = `machine_result` | Cloud, where state/destroy matter |

Request intake (issue form / portal) and orchestration (Actions → AAP) stay engine-neutral and call the same playbooks.

## Run it
```bash
pip install -r requirements-dev.txt
python tools/validate_contract.py contracts/request.v1.schema.json profiles/example-lab/sample-request.json
cd ansible
P="-e profile_dir=../profiles/example-lab -e request_file=../profiles/example-lab/sample-request.json"
ansible-playbook playbooks/provision.yml $P -e platform_action=apply      # repeat: changed=0
ansible-playbook playbooks/provision.yml $P -e platform_action=validate
ansible-playbook playbooks/provision.yml $P -e platform_action=revert
ansible-playbook playbooks/provision.yml $P --check --diff                # "plan"
```

## Test the baseline on a real RHEL 8 VM
The mock driver's IPs are unreachable on purpose. To exercise `rhel_baseline` + `validation` for real:
1. Create a RHEL 8 VM (e.g. Azure lab) with an **empty extra data disk**, and a non-root sudo user with your SSH key.
2. Copy `profiles/example-existing-host/`, then set `fqdn`, `ip`, `access.user`, `baseline.ntp_servers`, and the two `disk_map` by-id paths (`ls -l /dev/disk/by-id/`).
3. Install collections: `ansible-galaxy collection install -r ansible/requirements.yml`
4. Plan, then apply:
```bash
cd ansible
P="-e profile_dir=../profiles/my-vm -e request_file=../profiles/my-vm/sample-request.json"
ansible-playbook playbooks/site.yml $P --check --diff   # check mode: expect some skips on a fresh host
ansible-playbook playbooks/site.yml $P
ansible-playbook playbooks/site.yml $P                  # second run: changed=0 on the target
```
Evidence lands in `ansible/.state/reports/<host>.json`. Use `--tags baseline_storage` etc. for controlled reruns.

## Add a driver
1. Create `roles/cap_<capability>_<driver>/` with `tasks/{apply,validate,revert}.yml`.
2. Declare inputs in `meta/argument_specs.yml` (one block per entry point).
3. Set `cap_result` to the capability's result contract; the dispatcher rejects anything else.
4. Bind it in a profile: `capabilities.<capability>.driver: <driver>`.

## Add a customer
Copy `profiles/example-lab/`, set `policy.allow_mock: false`, bind real drivers, fill the catalogue. Keep real profiles in **private, separate repos**; pin this repo's version.

## Conventions
- Variables set inside roles are prefixed with the role name (`ansible-lint` production profile enforced). Two public contract names are exempted deliberately: `machine_spec`, `cap_result`.
- Secrets never appear in requests, profiles, results or logs - profiles hold *references* only.
- Fail closed: unknown logical values, disallowed environments, unbound capabilities and non-conforming driver output all stop the run.

## What has and has not been tested
| Verified here (Ubuntu sandbox, ansible-core 2.21) | Needs a real RHEL 8 host - NOT yet run |
|---|---|
| Lint (production profile), syntax-check, argument specs | dnf/chrony/firewalld/LVM/sysctl/sshd tasks |
| Mock lifecycle + idempotency, failure gates | Storage on a real by-id disk, mounts |
| `add_host` + volume mapping, template rendering | Handlers firing on change; second-run `changed=0` |
| Baseline and jboss fail closed on non-RHEL; bad `jboss_install_source` and bind address rejected | `validation` PASS results on a hardened host |
| Management-exposure check logic against sample `ss` output | EAP RPM install from Satellite, CLI changes, `/health/ready`, service account |

## Roadmap (build one slice at a time)
1. ✅ Contracts, dispatcher, mock compute, profile, CI
2. ✅ (code complete, awaiting RHEL test) `rhel_baseline` + `validation`, `existing` driver, `add_host` inventory
3. ✅ (code complete, awaiting RHEL + Satellite test) `jboss` standalone via RPM; next `tomcat`, then the `archive` source, TLS role
4. Real compute driver(s); `terraform` driver
5. Enterprise capability drivers with apply/revert pairs (ipam, dns, identity, config_mgmt, cmdb, backup, agents)
6. HA + `lb` capability; AAP launch adapter; intake workflow
