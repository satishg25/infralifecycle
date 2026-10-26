# Thin layer: Tomcat and Apache httpd, standalone and HA, on existing RHEL 8/9 VMs

A calling application (custom app / AAP job template) runs one playbook with flat extra variables.
No profile, no request file, no framework. The VMs must already exist and be in the inventory.

| Playbook | What it builds | Inventory groups (defaults) |
|---|---|---|
| `playbooks/tomcat_standalone.yml` | Tomcat 10.1 on one node | `middleware_nodes` |
| `playbooks/tomcat_ha.yml` | 2+ Tomcat nodes (unique `jvmRoute`) behind an Apache load balancer: sticky sessions, a stopped node is skipped | `tomcat_nodes`, `tomcat_lb` |
| `playbooks/apache_standalone.yml` | Apache httpd 2.4 web server (optionally a reverse proxy) | `web_nodes` |
| `playbooks/apache_ha.yml` | Active/passive Apache on a 2-node Pacemaker cluster: floating IP + httpd move together | `web_cluster` |
| `playbooks/jboss_standalone.yml` | JBoss EAP 8 - see `docs/jboss_standalone.md` | `middleware_nodes` |

Each playbook's header lists its full input contract (flat variables, defaults, which are required).
Bad input stops the run before any host is touched, with one precise message per check.

To take a single use case into an existing project (files to copy, appending it to their
`site.yml`), see `docs/usecases/` - one page per use case.

## Run
```bash
ansible-galaxy collection install -r requirements.yml
ansible-playbook playbooks/apache_ha.yml -i inventory.yml -e @examples/apache_ha.vars.yml -e @vault.yml --check --diff  # preview
ansible-playbook playbooks/apache_ha.yml -i inventory.yml -e @examples/apache_ha.vars.yml -e @vault.yml
```
In AAP: one job template per playbook; the hacluster password and fence credentials are AAP
credentials (or a Vault credential), never survey fields.

## RHEL 8 needs ansible-core 2.16
RHEL 8's system Python is 3.6. ansible-core 2.17 and later cannot manage it (the `dnf` module
needs that Python). Run these playbooks with ansible-core 2.16 against RHEL 8 - that is what
AAP 2.5's supported execution environments ship. RHEL 9 works with 2.16 and later.
The controller (or execution environment) needs `passlib` for the hacluster password hash.

## What each role does (secure defaults)
- **tomcat**: checksum-pinned archive, `/opt/tomcat/current` symlink (upgrade/rollback by version vars), non-root `tomcat` account, shutdown port disabled, no AJP, default webapps removed, no error details, systemd hardening, loopback-only unless `tomcat_bind_address` is set. New: `tomcat_jvm_route`.
- **apache_httpd**: owns the single `Listen` line, `ServerTokens Prod`, no signature, TRACE off, `nosniff`, default welcome page blanked, own `/health/` page, `httpd -t` before any reload (a bad config fails the run and the running server keeps its old config). Optional balancer (`apache_httpd_proxy_members`), SELinux `httpd_can_network_connect` set only when proxying. `apache_httpd_cluster_managed: true` = configure on every node but never start/enable (the cluster does).
- **pacemaker_cluster**: installs pacemaker/pcs, authenticates nodes (password via stdin, never on the command line or in the log), creates the cluster once, sets properties only when they differ. Fails closed on fencing: production needs `pacemaker_cluster_fence_devices`; disabling fencing needs two explicit switches.
- **apache_ha**: one resource group = `IPaddr2` VIP then `systemd:httpd`, stickiness 100 (no fail-back), corrects VIP drift.
- Every role has `tasks_from: validate` - read-only checks used by the playbooks after the change.

## Tested (container lab, Rocky Linux 8 = RHEL 8 rebuild, ansible-core 2.16.19)
For every playbook, `lab/run.sh <use case> --fresh` ran on new containers:
plan (`--check --diff`) on a fresh host -> apply -> **second apply `changed=0` on every host** -> validation.
- **tomcat_ha** drill: a session cookie for node 2 stays on node 2; Tomcat stopped on node 1 -> every request answered by node 2; node 1 restarted -> the balancer uses it again.
- **apache_ha** drill: active node put in standby -> VIP + httpd move to the other node and the VIP keeps answering -> node back -> group stays (stickiness).
- Lint: `ansible-lint` production profile clean.

Re-run it yourself on Linux/WSL with Docker: `lab/run.sh all --fresh` (see the header of `lab/run.sh`).

## NOT verified - confirm on the first real hosts
- RHEL proper: Satellite repos (incl. the High Availability repo), subscription, RHEL 9.
- SELinux enforcing and firewalld (the containers have neither): the `seboolean` and `firewalld` tasks, the `high-availability` firewalld service.
- **Fencing**: `pacemaker_cluster_fence_devices` creation and a real fence action (containers have nothing to fence). Test a fence with `pcs stonith fence <node>` in their environment.
- The VIP on their network (ARP/gratuitous ARP through their switches, VMware/cloud anti-spoofing rules).
- The OS validation role (`run_os_validation`) on these hosts; `run_baseline`.
- Tomcat session replication is not configured: on a node failure, its users log in again.

## Rewrite checklist when taking this into their repo
Their role/variable naming and prefixes, their Satellite repo/activation details, their artifact
repo URL for Tomcat, their baseline (CIS/STIG), their fence agent and its options, their
secrets/credential mechanism (AAP credentials), their inventory source, collections from their
automation hub, their load balancer (set `run_load_balancer: false` if they have one).
