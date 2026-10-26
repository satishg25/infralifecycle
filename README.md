# platform-kit

A customer-agnostic baseline for request-driven infrastructure automation: **logical request → provider-neutral contracts → pluggable drivers/engines**. Switching customer = switching a *profile*, not editing roles.

**Architecture and flow diagrams:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

> **Status:** core slice only (contracts, dispatcher, mock compute driver, profile). It contains no customer or employer code. Add a `LICENSE` and confirm hosting/IP approval before publishing or sharing beyond yourself.

## Layers

| Layer | Lives in | Customer-specific? |
|---|---|---|
| Request contract | `contracts/request.v1.schema.json` | No (logical values only, no secrets) |
| Resolve | `roles/machine_resolve` | No - maps logical names via the profile catalogue |
| Capability dispatch | `roles/capability_dispatch` | No - capability → driver binding from the profile |
| Drivers (`cap_<capability>_<driver>`) | `roles/cap_compute_mock` (more to come) | Provider-specific by design, isolated here |
| OS baseline + validation | `roles/rhel_baseline`, `roles/validation` | No - consume `machine_result` only |
| Workload roles | `roles/jboss` (EAP 8 standalone, RPM via Satellite; `archive` source is a placeholder), `roles/tomcat` (10.1 standalone, checksum-pinned archive; `rpm`/JWS source is a placeholder) | No |
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
| `azure` | Ansible (`azure.azcollection`) | Private-IP-only RHEL VM in an Azure lab. **Written, not yet run against Azure** - see below |
| `vmware` | Ansible (`community.vmware`) | Clone a RHEL template in vCenter. **Written, not yet run against vCenter** - see below |
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

## GitHub intake: form -> plan (read-only)
1. Create a **private** repo from this code. Regenerate the form for your profile:
   `python tools/gen_issue_form.py profiles/example-lab` (dropdowns come from the profile catalogue).
2. Optional repo **variables**: `PLATFORM_PROFILE_DIR` (default `profiles/example-lab`), `PLAN_PLAYBOOK` (`provision.yml` or `site.yml`), `PLAN_RUNNER` (self-hosted runner label).
3. Open **New issue -> Platform request**. The `plan` workflow parses the form (allow-list parser), validates it against `request.v1`, runs `ansible-playbook --check --diff`, and comments the result. Edit the issue to re-plan.
4. To plan against a real lab VM: use the `example-existing-host`-style profile with `PLAN_PLAYBOOK=site.yml`, a self-hosted runner that can reach the VM, secret `LAB_SSH_KEY` (dedicated low-privilege account) and variable `LAB_SSH_KNOWN_HOSTS` (host key checking stays on).

**What the plan is and is not.** It is a best-effort Ansible *check mode* preview, not `terraform plan`: it shows the resolved request, every gate (policy, catalogue, OS, contract) and the changes modules can predict. Steps that need earlier changes to exist (starting an uninstalled service, the JBoss CLI, validation) are skipped in a plan and run on apply. Nothing is changed. **Apply is not built yet** - it will be a separate workflow with an approval gate (approver != requester, payload hash frozen at approval).

## Azure compute driver (`cap_compute_azure`) - written, NOT yet run against Azure
Same contract as every compute driver, so all four use cases (JBoss/Tomcat, standalone/HA) reuse it unchanged.
- **Profile:** `profiles/example-azure-lab/` (placeholders only: subscription, resource group, subnet id, public key, VM size map). Bind it with `capabilities.compute.driver: azure`.
- **Secure defaults:** private IP only (no public IP, no per-NIC NSG - filter on the subnet), SSH key only (no passwords), encryption at host, managed boot diagnostics, no managed identity unless requested, data disks on stable `/dev/disk/azure/scsi1/lunN` paths.
- **Fail closed:** unknown region/zone, subnet id, image, VM size, reserved admin name, non-public-key or missing `os` disk all stop the run before any resource is touched.
- **Revert guard:** deletes only a VM tagged `managed_by=platform-kit` with the same `request_id`.
- **Scope limits:** resource group must already exist (never created); image is `publisher:offer:sku:version` only (gallery/golden images later); DNS registration is a later capability; in a plan the IP shows as `0.0.0.0` for a VM that does not exist yet, so plan with `provision.yml`, not `site.yml`.
- **Auth:** from the environment (OIDC / managed identity / `az login`); only `subscription_id` and `auth_source` are in the profile. The collection needs its Python SDK (`pip install -r <collection>/requirements.txt`) - put it in the Execution Environment.
- **Checked here:** lint (module parameters validated against `azure.azcollection` 3.21.0 docs), the pure derivation/validation logic (`ansible/tests/azure_prepare.yml`, 7 rejection cases). **Not checked:** any call to Azure, encryption-at-host registration, zone/size availability, idempotent re-apply.
- **Terraform later:** swap `driver: azure` for a Terraform-backed driver returning the same `machine_result.v1`; nothing downstream changes.

## Intake adapters (ServiceNow, ADO, custom app) -> `request.v1`
`tools/intake_adapter.py <servicenow|ado|custom> <payload.json> [--out request.json]` converts a source payload into the same `request.v1` the GitHub form produces. Each adapter in `tools/intake/` only extracts fields; `common.py` does the strict part (allow-list, whole-number check, label->logical value maps, schema validation, request id derived from the source reference, e.g. `RITM0012345` -> `RITM-0012345`). The source can never set `contract`, `request_id` or `topology`.
- **Edit per customer:** `FIELD_MAP` in each adapter (variable / field names) and `VALUE_MAPS` in `common.py` (display labels -> logical values).
- **Payload shapes are assumptions** (ServiceNow `{number, variables}`, ADO work item `{id, fields}`, custom `{reference, ...}`): compare against a real payload before trusting them.
- **Checked here:** fixtures in `tests/intake/`, 14 tests (3 good, 11 rejection cases incl. injection string, unknown label, bad number, privileged fields), and ServiceNow output driven through the mock provision/revert.

## VMware compute driver (`cap_compute_vmware`) - written, NOT yet run against vCenter
- **Profile:** `profiles/example-vmware-lab/` (placeholders only). The datacentre provider is an ASSUMPTION (vSphere); if it is not vSphere, only this role changes.
- **Credentials:** `VMWARE_HOST` / `VMWARE_USER` / `VMWARE_PASSWORD` from the environment (an AAP vCenter credential injects these). TLS verification is on by default.
- **Mapping:** `image` = template name, `placement` = `cluster/datastore`, `network` = port group (DHCP). The datacenter, folder, template, cluster, datastore and port group must pre-exist.
- **Ownership guard:** the VM annotation carries `managed_by=platform-kit request_id=...`; `revert` deletes only a VM whose annotation matches this request.
- **Checked here:** lint, syntax-check, module parameters against `community.vmware` 7.0.0 source, derivation/validation logic and disk-map logic with synthetic output (`ansible/tests/vmware_prepare.yml`). **Not checked:** any vCenter call; guest customisation; `wait_for_ip`; the `/dev/disk/by-id/wwn-0x<uuid>` disk naming (confirm on the first VM); revert on a missing VM (relies on the module error text containing "non-existing"); Galaxy availability of the pinned versions.

## Tomcat (`roles/tomcat`) - run against Rocky Linux 9 containers, NOT yet against RHEL
Thin entry point: `ansible/playbooks/thin/tomcat_standalone.yml` (same flat-variable contract as the JBoss one, plus `run_os_validation`).
- **Source seam:** `tomcat_install_source: archive` (implemented) downloads `tomcat_archive_url` and refuses it unless it matches `tomcat_archive_sha512`; point the URL at your artifact repo. `rpm` (JBoss Web Server from Satellite) fails with a clear message until implemented.
- **Layout:** each version unpacks to `/opt/tomcat/apache-tomcat-<version>`; `/opt/tomcat/current` is a symlink to the active one (upgrade = new version vars, rollback = old ones). Program files are root-owned and group-readable; the `tomcat` account (nologin) can write only `logs`, `temp`, `work`, `webapps`.
- **Secure defaults:** loopback-only HTTP unless `tomcat_bind_address` is set, shutdown port disabled, no AJP, default webapps removed, no error details or server info, no hot deploy, systemd unit with `NoNewPrivileges`/`ProtectSystem`. Validation checks the service, a role-owned `/health/` page, the active version, listener exposure, port 8005 closed, the non-root account and the absence of default webapps.
- **Local lab** (two Rocky Linux 9 containers with systemd on SSH ports 2231/2232, HTTP 8081/8082):
```bash
cd ansible
ansible-playbook playbooks/thin/tomcat_standalone.yml -i ../examples/lab/inventory.yml -e @../examples/lab/tomcat_standalone.vars.yml --check --diff
ansible-playbook playbooks/thin/tomcat_standalone.yml -i ../examples/lab/inventory.yml -e @../examples/lab/tomcat_standalone.vars.yml
```
- **Checked here:** lint (production profile), syntax-check, thin export; on the containers: check-mode plan on a fresh host, install, validation, second run `changed=0`, restart with no SEVERE log lines. **Not checked:** RHEL 8/9 proper, SELinux enforcing, firewalld, the `validation` role on these hosts, the request/profile path (`middleware: tomcat` is not in `request.v1` yet).

- **Rocky Linux 8 lab (2026-10-25):** also passes `lab/run.sh tomcat_standalone --fresh` with ansible-core 2.16 (see below). New option `tomcat_jvm_route` for nodes behind a sticky balancer.

## Tomcat and Apache HA (`tomcat_ha`, `apache_standalone`, `apache_ha`) - tested on Rocky Linux 8 containers, NOT yet on RHEL
Thin entry points in `ansible/playbooks/thin/` (each header lists its flat-variable contract):
- `tomcat_ha.yml` - 2+ `tomcat` nodes (unique `jvmRoute`, bound to their primary IPv4) behind an `apache_httpd` load balancer: sticky sessions, a node that refuses connections is skipped and retried. `run_load_balancer: false` when the platform provides the balancer. No session replication.
- `apache_standalone.yml` - role `apache_httpd`: owns the single `Listen` line, `ServerTokens Prod`, TRACE off, welcome page blanked, own `/health/` page, `httpd -t` before any reload, optional reverse proxy (`apache_httpd_proxy_members`).
- `apache_ha.yml` - roles `apache_httpd` (cluster-managed: configured on every node, never enabled), `pacemaker_cluster` (pcs auth with the password on stdin, cluster once, properties only when they differ, fails closed on fencing) and `apache_ha` (group = `IPaddr2` VIP then `systemd:httpd`, stickiness, VIP drift corrected).

**Local lab** (`lab/`): Rocky Linux 8 containers with systemd on a private Docker network (fixed IPs, VIP 172.30.0.40). One command per use case: plan on a fresh host, apply, second apply must be `changed=0` on every host, then a failover drill for the HA cases (`lab/tests/`).
```bash
# Linux/WSL with Docker; ansible-core 2.16 (RHEL 8 targets), collections from ansible/requirements.yml, passlib
lab/run.sh all --fresh          # or: tomcat_standalone | tomcat_ha | apache_standalone | apache_ha
lab/run.sh down
```
- **RHEL 8 needs ansible-core 2.16**: RHEL 8's system Python is 3.6, which ansible-core 2.17+ cannot manage (`dnf`). AAP 2.5's execution environments ship 2.16. `run.sh` refuses newer versions.
- **Checked here:** all four use cases as above (2026-10-25, ansible-core 2.16.19); lint (production profile). **Not checked:** RHEL proper and its HA repo, SELinux enforcing, firewalld, real fencing devices, the VIP on a real network, `run_os_validation`/`run_baseline` with these playbooks. Details: `docs/MIDDLEWARE-HANDOVER.md`.

## Thin layer for a customer app (Baloise)
`ansible/playbooks/thin/jboss_standalone.yml` takes flat extra variables and assumes the VM exists. `python3 tools/export_thin.py <dir>` copies the roles, all thin playbooks (JBoss, Tomcat, Apache, standalone and HA), example variables and the container lab without any framework code (fails if framework words leak). The export's README is `docs/MIDDLEWARE-HANDOVER.md`; the JBoss notes are `docs/BALOISE-HANDOVER.md`.

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
| Issue-body parser (11 unit tests incl. injection/duplicate/oversize), form generator, check-mode plan on the mock driver | The GitHub workflow itself (`plan.yml`) - never executed; first run on GitHub may need small fixes |
| Management-exposure check logic against sample `ss` output | EAP RPM install from Satellite, CLI changes, `/health/ready`, service account |

## Roadmap (build one slice at a time)
1. ✅ Contracts, dispatcher, mock compute, profile, CI
2. ✅ (code complete, awaiting RHEL test) `rhel_baseline` + `validation`, `existing` driver, `add_host` inventory
3. ✅ (code complete, awaiting RHEL + Satellite test) `jboss` standalone via RPM; ✅ `tomcat` standalone via archive (tested on Rocky 9 and 8 containers); ✅ `tomcat_ha`, `apache_standalone`, `apache_ha` (tested on Rocky 8 containers incl. failover drills); next wire `tomcat` into `request.v1`/profiles, then the jboss `archive` source, TLS role
4. ✅ (written, untested) `azure` and `vmware` compute drivers, intake adapters; next `terraform` driver
5. Enterprise capability drivers with apply/revert pairs (ipam, dns, identity, config_mgmt, cmdb, backup, agents)
6. HA + `lb` capability; AAP launch adapter; intake workflow
