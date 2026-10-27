# Use case: plain RHEL HA cluster (Pacemaker, resources from data)

Two or more RHEL 8/9 VMs in one subnet form a Pacemaker/Corosync cluster with fencing, then run
the resources you list (floating IP, services, filesystems) in groups, with location preferences.
**What runs is data**, so the same roles serve an Azure test bed and a datacentre: only variables
differ. Back to the [use-case index](README.md).

## Files to copy

| Repo path | Copy to (your project) |
|---|---|
| `ansible/roles/pacemaker_cluster/` (whole folder) | `roles/pacemaker_cluster/` |
| `ansible/roles/ha_preflight/` (whole folder: read-only checks before the build) | `roles/ha_preflight/` |
| `ansible/roles/rhel_ha/` (whole folder: defaults, meta, 6 task files) | `roles/rhel_ha/` |
| `ansible/playbooks/thin/rhel_ha.yml` | `playbooks/rhel_ha.yml` |
| `examples/thin/rhel_ha.datacenter.vars.yml`, `rhel_ha.azure-lab.vars.yml` | starting points |

**Collections:** `ansible.posix` (firewalld). **Controller:** `passlib`.
**On the VMs:** the RHEL High Availability repository (Satellite content view), both nodes in the same subnet.

## What changes between environments

| Concern | Azure test bed | Datacentre | Where it lives |
|---|---|---|---|
| Fencing | none (lab) or `fence_azure_arm` with a managed identity | `fence_vmware_rest` (vSphere) or `fence_ipmilan` / `fence_redfish` (physical) | `pacemaker_cluster_fence_devices` |
| Floating IP | **not usable**: `IPaddr2` is not routable on Azure; real Azure needs an internal load balancer + `azure-lb` | `ocf:heartbeat:IPaddr2` | a resource in `rhel_ha_resources` |
| Shared storage | usually none (use `Dummy`) | `LVM-activate` + `Filesystem` resources | resources in the same group |
| HA repo | check it exists; not in standard pay-as-you-go images as far as I know | Satellite content view | `pacemaker_cluster_enable_repos` |
| Firewall | NSG only (firewalld off) | `high-availability` service | `pacemaker_cluster_firewall_services` |

## Preflight (runs first, changes nothing)

`ha_preflight` checks every node and reports **all** problems at once, then stops before any cluster
change: platform (RHEL 8/9), node list (2+, unique names and addresses), that each node name resolves
from every node to the right address (never loopback), TCP reachability between the nodes, time
synchronisation, that the cluster packages are installed or available from the enabled repositories
(the High Availability repo), and that any shared devices exist. Turn it off with `run_preflight: false`.
The cluster ports (2224/tcp, 5404-5405/udp) only open once the software runs, so the cluster build proves them.

## Resource model

```yaml
rhel_ha_resources:          # order = start order inside a group; stop is the reverse
  - {name: app-vip, type: "ocf:heartbeat:IPaddr2", group: app, params: {ip: 192.0.2.50, cidr_netmask: "24"}}
  - {name: app-svc, type: "systemd:myapp",         group: app}
rhel_ha_constraints:        # location preferences (groups already give order + colocation)
  - {resource: app, node: node1, score: "100"}
```
- `type` is `ocf:<provider>:<agent>` or `systemd:<unit>` only; names and parameter keys are allow-listed.
- Parameters are corrected on every run (drift); `meta` is applied at creation only.
- A `systemd:` unit is left **disabled at boot** on every node by the role (`rhel_ha_disable_managed_services`), because the cluster must be the only thing that starts it. It must already be installed.
- A changed constraint score replaces the old one.

## Run

```bash
ansible-playbook playbooks/rhel_ha.yml -i <inventory> -e @<vars> -e @<vault> --check --diff
ansible-playbook playbooks/rhel_ha.yml -i <inventory> -e @<vars> -e @<vault>
ansible-playbook playbooks/rhel_ha.yml -i <inventory> -e @<vars> -e @<vault>   # changed=0
```
Fencing is fail-closed: the run stops unless devices are listed, or **both**
`pacemaker_cluster_stonith_enabled: false` and `pacemaker_cluster_allow_no_fencing: true` (lab only).

## Failover drill (lab only: changes cluster state)

```bash
sudo pcs status
sudo pcs node standby <active node>     # the group moves; check with: sudo pcs status
sudo pcs node unstandby <node>          # stickiness keeps it where it is
```

## Checked and not checked

- **Checked:** ansible-lint production profile, syntax-check of both example profiles, the preflight against stand-in facts and tools (each failure mode reported, nothing changed), the role's control flow against a stand-in for `pcs`/`crm_resource`/`cibadmin` (apply, second run `changed=0`, drift repair, constraint score replacement, check mode, 7 rejected inputs with no write issued), handover export without framework leaks.
- **Not checked:** any real Pacemaker. The exact `pcs` syntax for RHEL 8.10 / 9, resource start, failover, fencing and the systemd-unit path have not been run against a real cluster.
