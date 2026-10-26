# platform-kit architecture

How the framework turns a request into a configured, validated server, and how its reusable
middleware layer (Tomcat, Apache httpd, JBoss; standalone and HA) is built, tested and handed
over. Diagrams are [Mermaid](https://mermaid.js.org/) and render on GitHub.

> Status labels used below: **tested** (run end to end, see [Status](#11-status)), **written**
> (code complete, never run against the real target), **planned** (not built).

---

## 1. Design principles

| Principle | What it means in the code |
|---|---|
| **Logical request, physical profile** | A request says `sizing: medium`, never `Standard_D4s_v5`. Only the customer *profile* maps logical names to real ones. Switching customer = switching profile, not editing roles. |
| **Contracts between layers** | `request.v1` → `machine_spec.v1` → `machine_result.v1`. Each layer reads only the contract in front of it, so a provider change never ripples into OS or middleware roles. |
| **Pluggable drivers** | A capability (`compute`, later `dns`, `cmdb`, ...) has interchangeable drivers (`mock`, `existing`, `azure`, `vmware`, later `terraform`) behind one contract. |
| **Fail closed** | Unknown values, disallowed environments, unbound capabilities, missing fencing, unpinned downloads: the run stops before touching anything, with one precise message. |
| **Plan before apply** | Every playbook supports `--check --diff`; roles detect a brand-new host and say what they *would* do instead of failing. |
| **Idempotent by proof** | A second run must report `changed=0`; CI and the lab enforce it. |
| **Secrets never in data** | Requests, profiles, vars files and results hold references only. Secrets come from AAP credentials / Vault and are passed with `no_log` or on stdin. |
| **Thin layer is framework-free** | The middleware roles and thin playbooks run on their own with flat variables, so they can be copied into a customer's repo. |

---

## 2. Big picture

```mermaid
flowchart TB
    subgraph intake["1 - Intake (engine-neutral)"]
        GH["GitHub Issue Form"]
        SN["ServiceNow RITM"]
        ADO["Azure DevOps work item"]
        CU["Custom portal"]
    end

    subgraph contract["2 - Request contract"]
        AD["tools/intake_adapter.py<br/>tools/issue_to_request.py<br/>allow-list parse"]
        REQ[("request.v1<br/>JSON Schema")]
    end

    subgraph orch["3 - Orchestration"]
        PLAN["plan workflow<br/>(GitHub Actions, check mode)"]
        AAP["AAP job / workflow templates<br/>(apply - planned)"]
    end

    subgraph fw["4 - Framework playbooks"]
        PROV["provision.yml<br/>resolve + compute"]
        CONF["configure.yml<br/>baseline + middleware"]
    end

    subgraph caps["5 - Capability drivers"]
        DISP["capability_dispatch"]
        MOCK["cap_compute_mock"]
        EXIST["cap_compute_existing"]
        AZ["cap_compute_azure"]
        VM["cap_compute_vmware"]
    end

    subgraph host["6 - Target hosts (RHEL 8/9)"]
        BASE["rhel_baseline"]
        MW["middleware roles<br/>tomcat / apache_httpd / jboss<br/>pacemaker_cluster / apache_ha"]
        VAL["validation + role validate<br/>evidence report"]
    end

    PROFILE[("Customer profile<br/>profile.yml + catalogue.yml")]
    THIN["Thin playbooks<br/>(flat vars, no framework)"]
    CALLER["Customer app / AAP job template"]

    GH & SN & ADO & CU --> AD --> REQ
    REQ --> PLAN & AAP
    PLAN --> PROV
    AAP --> PROV --> CONF
    PROFILE -.-> PROV & CONF & DISP
    PROV --> DISP --> MOCK & EXIST & AZ & VM
    CONF --> BASE --> MW --> VAL
    CALLER --> THIN --> MW
```

There are **two ways in**:

1. **Framework path** - a logical request flows through contracts, the profile and a compute driver, then the host is configured. Used when the platform owns the whole lifecycle.
2. **Thin path** - a caller (the customer's own AAP job template or app) runs one thin playbook with flat variables against VMs that already exist. Used to hand middleware automation to a customer whose platform already builds the VMs.

Both paths use the **same** OS and middleware roles.

---

## 3. Request intake and the plan workflow

```mermaid
sequenceDiagram
    autonumber
    actor U as Requester
    participant I as Issue Form / ServiceNow / ADO
    participant P as Parser + adapter<br/>(allow-list)
    participant S as JSON Schema<br/>request.v1
    participant W as plan workflow<br/>(GitHub Actions)
    participant A as ansible-playbook<br/>--check --diff
    U->>I: fill the form (logical values only)
    I->>W: issue opened / edited
    W->>W: only OWNER / MEMBER / COLLABORATOR,<br/>code from the default branch
    W->>P: issue body via env var
    P-->>W: request.json (no request_id/contract/topology from the user)
    W->>S: validate
    alt invalid
        S-->>U: comment: precise validation error
    else valid
        W->>A: provision.yml (or site.yml) with repo-chosen profile
        A-->>W: plan log (nothing changed)
        W-->>U: comment: resolved request + plan
    end
    Note over W,A: Apply is planned as a separate workflow with an<br/>approval gate (approver != requester, payload hash frozen)
```

- Adapters only **extract** fields; `tools/intake/common.py` does the strict part (allow-list, value maps, schema). The source can never set `contract`, `request_id` or `topology`.
- Which profile and playbook are planned comes from **repo variables**, never from the issue.
- Status: parser and adapters **tested** (unit tests); the `plan` workflow is **written** (never executed on GitHub); apply is **planned**.

---

## 4. Contracts

```mermaid
classDiagram
    direction LR
    class request_v1 {
        contract = request.v1
        request_id : ABC-0001
        name
        environment : lab|dev|test|prod
        sizing : logical
        image : logical
        network_profile : logical
        placement : logical
        data_disk_gb
        owner
        ttl_days
        middleware
        topology
    }
    class machine_spec_v1 {
        contract = machine_spec.v1
        name
        cpu
        memory_gb
        image_ref : physical
        placement_ref : physical
        network_ref : physical
        disks : role, size_gb, mount, fs
        tags : request_id, environment, owner, ttl_days, managed_by
    }
    class machine_result_v1 {
        contract = machine_result.v1
        state : present|absent
        id
        fqdn
        ip
        disk_map : role -> /dev/disk/by-*
        state_ref
    }
    class profile {
        policy : allow_mock, allowed_environments
        access : user, connection
        baseline : ntp_servers, firewall_ports
        middleware : per product settings
        capabilities : capability -> driver + config
    }
    class catalogue {
        sizing : name -> cpu, memory
        images : name -> image ref
        placement : name -> placement ref
        networks : name -> network ref
        defaults
    }
    request_v1 --> machine_spec_v1 : machine_resolve
    profile ..> machine_spec_v1 : policy
    catalogue ..> machine_spec_v1 : logical to physical
    machine_spec_v1 --> machine_result_v1 : compute driver
```

| Contract | Produced by | Consumed by | Enforced by |
|---|---|---|---|
| `request.v1` | intake adapters | `machine_resolve` | JSON Schema (`contracts/request.v1.schema.json`) |
| `machine_spec.v1` | `machine_resolve` | compute drivers | each driver's `meta/argument_specs.yml` |
| `machine_result.v1` | compute drivers | `configure.yml`, OS and middleware roles | `capability_dispatch` (`validate_argument_spec` on every driver output) |

`machine_result.v1` is the **only** thing downstream roles may read about a machine, so a VMware
VM and an Azure VM look identical to `rhel_baseline`. Disks are addressed by role through stable
`/dev/disk/by-*` paths, never `/dev/sdX`.

---

## 5. Provision: resolve and dispatch

```mermaid
flowchart TD
    START(["provision.yml<br/>-e profile_dir -e request_file<br/>-e platform_action=apply|validate|revert"]) --> LOAD["Load profile.yml + catalogue.yml<br/>Load request.json"]
    LOAD --> R1{"environment in<br/>policy.allowed_environments?"}
    R1 -- no --> X1["FAIL: environment not allowed"]
    R1 -- yes --> R2{"every logical name<br/>in the catalogue?"}
    R2 -- no --> X2["FAIL: unknown sizing / image /<br/>network / placement (lists known values)"]
    R2 -- yes --> SPEC["machine_resolve builds machine_spec.v1"]
    SPEC --> D1{"capability bound<br/>in the profile?"}
    D1 -- no --> X3["FAIL: no binding for compute"]
    D1 -- yes --> D2{"driver is mock and<br/>policy.allow_mock false?"}
    D2 -- yes --> X4["FAIL: mock not permitted"]
    D2 -- no --> DRV["include_role cap_compute_DRIVER<br/>tasks_from: apply | validate | revert"]
    DRV --> CHK{"cap_result matches<br/>machine_result.v1?"}
    CHK -- no --> X5["FAIL: driver broke the contract"]
    CHK -- yes --> OUT(["capability_dispatch_results.compute"])
```

Every driver implements the same three entry points:

| Entry point | Meaning |
|---|---|
| `apply` | make the machine exist as specified (idempotent) |
| `validate` | read-only: does it exist and match? |
| `revert` | delete it - only if it carries this request's ownership tag/annotation |

| Driver | Engine | Status |
|---|---|---|
| `mock` | Ansible, local state file | **tested** (CI: apply, re-apply `changed=0`, validate, revert) |
| `existing` | Ansible, bring-your-own host | **written**, used for real-VM baseline tests |
| `azure` | `azure.azcollection` | **written** (logic tests only), private IP only, SSH key only |
| `vmware` | `community.vmware` | **written** (logic tests only), annotation ownership guard |
| `terraform` | `cloud.terraform` | **planned** - same contracts, so nothing downstream changes |

---

## 6. Configure: from machine result to configured host

```mermaid
sequenceDiagram
    autonumber
    participant L as localhost<br/>(EE / controller)
    participant H as New host
    L->>L: assert compute result state == present
    L->>L: map spec disks + driver disk_map<br/>to volume list (vg_role / lv_role)
    L->>H: add_host into middleware_nodes<br/>(fqdn, ip, access user from profile)
    L->>H: rhel_baseline<br/>packages, chrony, sshd, sysctl, firewall, LVM storage
    H-->>L: changed / ok
    L->>H: validation (read-only)<br/>services, mounts, sysctl, sshd
    H-->>L: evidence JSON in .state/reports/HOST.json
    L->>H: middleware role chosen by request.middleware<br/>(jboss today)
    L->>H: role validate (read-only)
```

`site.yml` = `provision.yml` (apply) + `configure.yml`. Nothing in `configure.yml` knows which
provider built the host.

---

## 7. The thin layer

The thin layer is what gets copied to a customer. It has no profile, no request file and no
dispatcher: flat variables in, roles applied, read-only validation out.

### 7.1 Anatomy of a thin playbook

```mermaid
flowchart LR
    subgraph p1["Play 1 - localhost, tags: always"]
        V1["Check host patterns are plain"]
        V2["Check booleans are true/false"]
        V3["Check required values<br/>(NTP if baseline, VIP, password...)"]
        V4["Check explicit decisions<br/>(fencing, cluster ownership)"]
    end
    subgraph p2["Play 2+ - target hosts, become"]
        B["rhel_baseline<br/>(only if run_baseline)"]
        R["product role(s)<br/>main.yml"]
        OV["validation role<br/>(if run_os_validation)"]
        RV["role tasks_from: validate"]
    end
    IN(["-e @vars.yml<br/>-e @vault.yml"]) --> V1 --> V2 --> V3 --> V4 --> B --> R --> OV --> RV --> OUT(["PLAY RECAP<br/>second run: changed=0"])
```

Bad input stops the run in play 1, **before any host is touched**. Validation steps are skipped in
check mode (they need the real state).

### 7.2 Anatomy of a product role

```mermaid
flowchart LR
    A["assert.yml<br/>platform + every input<br/>held to strict patterns"] --> I["install*.yml<br/>package / pinned archive<br/>+ preview_blind detection"]
    I --> C["configure.yml<br/>templates and files only<br/>notify one handler"]
    C --> S["service.yml<br/>flush handlers, start, wait<br/>(or hand over to cluster)"]
    S --> F["firewall.yml<br/>only ports the caller lists"]
    VAL["validate.yml<br/>read-only checks"]
    F -. "separate entry point<br/>tasks_from: validate" .-> VAL
```

- `meta/argument_specs.yml` declares every input for `main` and `validate`.
- Variables are prefixed with the role name (ansible-lint production profile).
- **preview_blind**: in check mode on a host where the product is not installed yet, the role
  prints what it would install and skips the steps that need files on disk, instead of failing.

### 7.3 Role map

```mermaid
flowchart TB
    subgraph os["OS layer"]
        RB["rhel_baseline"]
        VA["validation"]
    end
    subgraph mw["Middleware roles"]
        TC["tomcat<br/>archive (sha512 pinned) / rpm seam"]
        AH["apache_httpd<br/>web server, reverse proxy,<br/>load balancer, cluster-managed mode"]
        JB["jboss<br/>EAP 8 via RPM"]
    end
    subgraph ha["HA roles"]
        PC["pacemaker_cluster<br/>pcs auth, setup, properties, fencing"]
        AHA["apache_ha<br/>VIP + httpd resource group"]
    end
    subgraph thin["Thin playbooks"]
        T1["tomcat_standalone.yml"]
        T2["tomcat_ha.yml"]
        T3["apache_standalone.yml"]
        T4["apache_ha.yml"]
        T5["jboss_standalone.yml"]
    end
    T1 --> TC
    T2 --> TC & AH
    T3 --> AH
    T4 --> AH & PC & AHA
    T5 --> JB
    T1 & T2 & T3 & T4 & T5 -. optional .-> RB & VA
```

---

## 8. Middleware topologies

### 8.1 Tomcat standalone (`tomcat_standalone.yml`)

```mermaid
flowchart LR
    C(["Client or local proxy"]) -->|"8080 (loopback unless<br/>tomcat_bind_address set)"| T
    subgraph VM["RHEL VM"]
        T["Tomcat 10.1 - systemd unit<br/>user: tomcat (nologin)<br/>/opt/tomcat/current -> apache-tomcat-VERSION"]
        H["/health/ page owned by the role"]
        T --- H
    end
```

Secure defaults: shutdown port disabled, no AJP, default webapps removed, no error details, no
hot deploy, `NoNewPrivileges` / `ProtectSystem`. Upgrade = new version variables (new directory,
symlink flip); rollback = old variables.

### 8.2 Tomcat HA (`tomcat_ha.yml`)

```mermaid
flowchart LR
    C(["Clients"]) -->|":80"| LB
    subgraph LBN["tomcat_lb host"]
        LB["apache_httpd<br/>balancer://app<br/>sticky on JSESSIONID suffix<br/>own page: /lb-health/"]
    end
    subgraph N1["tomcat_nodes[0]"]
        T1["Tomcat<br/>jvmRoute = node1<br/>bind = primary IPv4"]
    end
    subgraph N2["tomcat_nodes[1]"]
        T2["Tomcat<br/>jvmRoute = node2<br/>bind = primary IPv4"]
    end
    LB -->|"route=node1"| T1
    LB -->|"route=node2"| T2
```

- Each node gets a unique `jvmRoute`; Tomcat appends it to the session id
  (`JSESSIONID=abc.node2`) and the balancer keeps that session on `node2`.
- A node that refuses connections is skipped and retried after `apache_httpd_proxy_retry` seconds.
- `run_load_balancer: false` when the platform has its own balancer (F5, NetScaler, cloud LB):
  point it at each node's bind address and `/health/`.
- Sessions are **not** replicated: users of a failed node log in again.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant LB as Apache balancer
    participant N1 as Tomcat node1
    participant N2 as Tomcat node2
    C->>LB: GET / (no session)
    LB->>N1: round robin
    N1-->>C: Set-Cookie JSESSIONID=abc.node1
    C->>LB: GET / Cookie JSESSIONID=abc.node1
    LB->>N1: sticky: route node1
    Note over N1: node1 stops
    C->>LB: GET / Cookie JSESSIONID=abc.node1
    LB-xN1: connection refused
    LB->>N2: fail over to the next member
    N2-->>C: 200 (new session)
    Note over LB,N1: node1 retried after proxy_retry seconds, rejoins when it answers
```

### 8.3 Apache standalone (`apache_standalone.yml`)

```mermaid
flowchart LR
    C(["Clients"]) -->|":80"| A
    subgraph VM["RHEL VM"]
        A["httpd 2.4<br/>Listen owned by the role<br/>ServerTokens Prod, TRACE off<br/>welcome page blanked"]
        D["DocumentRoot + /health/"]
        P["optional: balancer://app<br/>(apache_httpd_proxy_members)"]
        A --- D
        A -.- P
    end
```

Every config change runs `httpd -t` **before** the reload handler, so a bad config fails the run
and the running server keeps its previous config.

### 8.4 Apache HA (`apache_ha.yml`)

```mermaid
flowchart TB
    C(["Clients / DNS"]) -->|"VIP :80"| VIP
    subgraph CL["Pacemaker / Corosync cluster (2 nodes, one subnet)"]
        direction LR
        subgraph A1["node 1 - active"]
            VIP["apache-vip<br/>ocf:heartbeat:IPaddr2"]
            WEB["apache-web<br/>systemd:httpd"]
            VIP --> WEB
        end
        subgraph A2["node 2 - standby"]
            I2["httpd installed and configured,<br/>disabled at boot, stopped"]
        end
        FN["Fence devices (STONITH)<br/>required for production"]
    end
    A1 <-->|"corosync 5404-5405/udp<br/>pcsd 2224/tcp"| A2
    FN -. "power off a node<br/>that stops responding" .-> A1 & A2
```

- `apache-group` = VIP first, then httpd; started together on one node, stopped in reverse.
- `resource-stickiness=100`: after a failover the group stays where it is when the failed node
  returns (no second outage from fail-back).
- httpd is installed and configured on **both** nodes (`apache_httpd_cluster_managed: true`) but
  never enabled at boot; only the cluster starts it. Config reloads go only to the node where
  it runs.

How the playbook builds it:

```mermaid
sequenceDiagram
    autonumber
    participant C as Controller
    participant N1 as node1 (first play host)
    participant N2 as node2
    C->>C: play 1: VIP, password, explicit fencing decision
    par every node
        C->>N1: apache_httpd (cluster-managed): install, configure, httpd -t, disable unit
        C->>N2: apache_httpd (cluster-managed): install, configure, httpd -t, disable unit
    end
    par every node
        C->>N1: pacemaker_cluster: packages, firewall, hacluster password, pcsd
        C->>N2: pacemaker_cluster: packages, firewall, hacluster password, pcsd
    end
    C->>N1: pcs host auth (password on stdin) - only nodes not yet trusted
    C->>N1: pcs cluster setup --start --enable - only if no corosync.conf
    N1->>N2: pcs pushes config and starts the cluster
    C->>N1: wait for quorum (crm_node -q)
    C->>N1: properties: read with crm_attribute, set with pcs only if different
    C->>N1: fence devices: create the missing ones (argv, no_log)
    C->>N1: apache_ha: create VIP + httpd in the group if missing,<br/>correct VIP drift, set stickiness, wait until running
    C->>N1: validate: quorum, members, fencing, group on exactly one node
    C->>N2: validate: httpd unit disabled, VIP health page answers OK
```

Failover:

```mermaid
stateDiagram-v2
    [*] --> Node1Active: cluster starts group
    Node1Active --> Moving: node1 fails or is put in standby
    Moving --> Node2Active: VIP moves, then httpd starts on node2
    Node2Active --> Node2Active: node1 returns (stickiness keeps the group)
    Node2Active --> Moving2: node2 fails
    Moving2 --> Node1Active
    note right of Moving
        With fencing: a node that stops responding
        is powered off before its resources move,
        so the VIP is never active twice.
    end note
```

---

## 9. Testing and quality gates

### 9.1 CI (every push and pull request)

```mermaid
flowchart LR
    PR(["push / PR"]) --> C1["Contracts:<br/>sample requests conform"]
    C1 --> C2["Issue form in step<br/>with the profile"]
    C2 --> C3["Parser + adapter<br/>unit tests"]
    C3 --> C4["ansible-lint<br/>production profile"]
    C4 --> C5["syntax-check<br/>framework + thin playbooks"]
    C5 --> C6["Logic tests: templates,<br/>azure / vmware derivation,<br/>ss loopback parsing"]
    C6 --> C7["Thin export: no framework words,<br/>syntax-check, lint"]
    C7 --> C8["Mock lifecycle:<br/>apply, re-apply changed=0,<br/>validate, revert"]
    C8 --> OK(["green"])
```

CI never holds deployment credentials (`permissions: contents: read`).

### 9.2 Container lab (`lab/run.sh`, run locally on Linux / WSL with Docker)

```mermaid
flowchart TB
    subgraph net["Docker network 172.30.0.0/24 - Rocky Linux 8 + systemd (privileged, lab only)"]
        tc1["tc1 .11<br/>Tomcat standalone"]
        tclb["tclb .20<br/>Apache balancer"]
        tcha1["tcha1 .21"]
        tcha2["tcha2 .22"]
        ap1["ap1 .31<br/>Apache standalone"]
        apha1["apha1 .41"]
        apha2["apha2 .42"]
        vip(("VIP .40"))
    end
    tclb --> tcha1 & tcha2
    vip -.-> apha1 & apha2
    WSL["WSL controller<br/>ansible-core 2.16"] -->|ssh| net
```

```mermaid
flowchart LR
    S(["lab/run.sh USE_CASE --fresh"]) --> V{"ansible-core<br/>2.16?"}
    V -- no --> STOP["refuse: RHEL 8 needs 2.16"]
    V -- yes --> B["build image, recreate<br/>only the needed containers"]
    B --> K["record new host keys<br/>(host key checking stays on)"]
    K --> P1["1. plan<br/>--check --diff on a fresh host"]
    P1 --> P2["2. apply"]
    P2 --> P3["3. apply again"]
    P3 --> G{"changed=0 on<br/>every host?"}
    G -- no --> FAIL["IDEMPOTENCY FAILED"]
    G -- yes --> P4["4. drill<br/>lab/tests/USE_CASE.yml<br/>(HA cases)"]
    P4 --> PASS(["PASSED"])
```

| Drill | Steps | Proves |
|---|---|---|
| `tests/tomcat_ha.yml` | cookie for node2 → stop Tomcat on node1 → 6 requests → start node1 | sticky sessions, failover, rejoin |
| `tests/apache_ha.yml` | standby the active node → VIP check → unstandby | VIP + httpd move together, VIP keeps answering, stickiness |

**Why ansible-core 2.16:** RHEL 8's system Python is 3.6. ansible-core 2.17+ cannot run modules
there (`dnf` needs that Python's bindings). AAP 2.5's supported execution environments ship 2.16,
so the lab matches what a customer's AAP would run.

---

## 10. Delivery: AAP and customer handover

### 10.1 Running in AAP

```mermaid
flowchart LR
    subgraph AAPC["AAP controller"]
        JT["Job template per thin playbook<br/>(or per framework playbook)"]
        INV["Inventory source<br/>(customer CMDB / vCenter / static)"]
        CRED["Credentials:<br/>machine SSH key, Vault,<br/>hacluster password, fence creds"]
        EE["Execution environment<br/>ansible-core 2.16, pinned collections,<br/>passlib"]
        SUR["Survey: flat, non-secret vars only"]
    end
    JT --> INV & CRED & EE & SUR
    JT --> RUN["ansible-playbook playbooks/X.yml<br/>-e survey vars + credential vars"]
    RUN --> HOSTS["RHEL 8/9 VMs"]
```

A typical customer workflow template: *their* VM provisioning job → the thin playbook job →
*their* CMDB / monitoring onboarding job.

### 10.2 Handover export

```mermaid
flowchart LR
    REPO["this repo"] -->|"python tools/export_thin.py OUT"| CHK{"framework words<br/>in any YAML?"}
    CHK -- yes --> STOP["FRAMEWORK LEAK - export fails"]
    CHK -- no --> PKG
    subgraph PKG["OUT/ - self-contained"]
        R1["roles/<br/>tomcat, apache_httpd, pacemaker_cluster,<br/>apache_ha, jboss, validation, rhel_baseline"]
        R2["playbooks/<br/>5 thin playbooks"]
        R3["examples/ + inventory.yml"]
        R4["lab/ - same container tests"]
        R5["README.md = MIDDLEWARE-HANDOVER.md<br/>ansible.cfg, requirements.yml, .ansible-lint"]
    end
    PKG --> CUST["customer repo<br/>rewrite to their conventions<br/>(checklist in the README)"]
```

The receiving team can re-run `lab/run.sh all --fresh` inside the export to see the same results
before adapting names, repos and credentials.

---

## 11. Status

| Area | Status | Evidence |
|---|---|---|
| Contracts, dispatcher, profile, mock driver | **tested** | CI mock lifecycle incl. idempotency |
| Intake parser, adapters (GitHub, ServiceNow, ADO, custom) | **tested** | unit tests with injection / bad-value cases |
| `plan` workflow | **written** | never executed on GitHub |
| Apply workflow with approval gate | **planned** | - |
| `existing`, `azure`, `vmware` compute drivers | **written** | logic tests only; no real cloud / vCenter call |
| `terraform` driver, enterprise capabilities (dns, ipam, cmdb, backup, ...) | **planned** | - |
| `rhel_baseline`, `validation` | **written** | template / logic tests; not on a hardened RHEL host |
| `jboss` standalone | **written** | not run against Satellite / EAP |
| `tomcat` standalone | **tested** | Rocky 9 and Rocky 8 containers |
| `tomcat_ha`, `apache_standalone`, `apache_ha` | **tested** | Rocky 8 containers incl. failover drills, run from the export |
| Real RHEL, SELinux enforcing, firewalld, real fencing, VIP on a real network | **not yet** | confirm on the first customer hosts |

---

## 12. Extending the framework

| To add | Do this |
|---|---|
| A compute driver | `roles/cap_compute_<driver>/tasks/{apply,validate,revert}.yml`, inputs in `meta/argument_specs.yml`, set `cap_result` to `machine_result.v1`, bind it in a profile. |
| A new capability | add its result spec to `capability_dispatch/vars/main.yml` (and a JSON schema in `contracts/`), then drivers as above. |
| A customer | copy `profiles/example-lab/`, set `policy.allow_mock: false`, bind real drivers, fill the catalogue. Keep real profiles in a private repo. |
| A middleware use case | a role following section 7.2 (assert / install / configure / service / firewall / validate, argument specs, role-prefixed vars), a thin playbook following 7.1, lab vars + a container entry + an optional drill, then add both to `tools/export_thin.py`. |

## 13. Repository map

```text
contracts/            JSON Schemas: request.v1, machine_spec.v1, machine_result.v1
profiles/<name>/      profile.yml + catalogue.yml (the only customer-specific inputs)
tools/                intake adapters, issue parser, form generator, contract validator, export_thin.py
ansible/playbooks/    provision.yml, configure.yml, site.yml   (framework path)
ansible/playbooks/thin/  tomcat_*, apache_*, jboss_standalone  (thin path)
ansible/roles/        machine_resolve, capability_dispatch, cap_compute_*   (framework)
                      rhel_baseline, validation                             (OS)
                      tomcat, apache_httpd, jboss, pacemaker_cluster, apache_ha (middleware)
ansible/tests/        logic tests that need no host
lab/                  container lab: Dockerfile, compose.yml, inventory, vars, drills, run.sh
examples/             flat-variable examples for the thin playbooks
docs/                 this file, handover guides, learning notes
.github/workflows/    ci.yml (quality gates), plan.yml (request -> plan comment)
```
