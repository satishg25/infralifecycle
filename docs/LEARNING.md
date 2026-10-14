# Learning Ansible through this repo

Read the file, run it, break it on purpose. Each concept maps to something real here.

| # | Concept | Where to look | Try this |
|---|---|---|---|
| 1 | Inventory, `localhost`, `connection: local` | `ansible/inventories/lab/hosts.yml` | Run with `-i localhost,` and compare |
| 2 | Variables & precedence (`-e` beats everything) | `playbooks/provision.yml` (`platform_action`) | Override with `-e platform_action=revert` |
| 3 | Idempotency: `ok` vs `changed` | `roles/cap_compute_mock/tasks/apply.yml` | Apply twice; edit the state file by hand; apply again |
| 4 | Check mode = "plan" | any playbook | `--check --diff` on a fresh checkout |
| 5 | Role layout: `tasks/`, `defaults/`, `vars/`, `meta/` | `roles/cap_compute_mock/` | Override `cap_compute_mock_state_dir` with `-e` |
| 6 | `assert` for fail-fast validation | `roles/machine_resolve/tasks/main.yml` | Set `"sizing": "huge"` in a request |
| 7 | Role argument specs (input contracts) | `roles/cap_compute_mock/meta/argument_specs.yml` | Remove a required field from the spec input |
| 8 | `include_role` / `tasks_from` (dynamic dispatch) | `roles/capability_dispatch/tasks/main.yml` | Add a second driver, switch it in the profile |
| 9 | Jinja2 filters (`combine`, `zip`, `hash`, `to_nice_json`) | `tasks/_result.yml` | Print intermediate values with `debug` |
| 10 | Linting as a teacher | `cd ansible && ansible-lint` | Introduce a bare `command:` and read the rule |
| 11 | Templates (Jinja2 files) + handlers | `rhel_baseline/templates/chrony.conf.j2`, `tasks/time.yml`, `handlers/main.yml` | Change an NTP server, re-run: only then does chronyd restart |
| 12 | `import_tasks` + tags for controlled reruns | `rhel_baseline/tasks/main.yml` | `--tags baseline_storage` |
| 13 | Dynamic inventory with `add_host`, `hostvars` | `playbooks/configure.yml` | Print `hostvars` of the new host |
| 14 | Collections, pinned in `requirements.yml` | `ansible/requirements.yml` | `ansible-galaxy collection list` |
| 15 | Facts (`ansible_facts[...]`), fail-closed `assert` | `rhel_baseline/tasks/assert.yml` | Run on a non-RHEL box and read the error |
| 16 | Accumulating results, `delegate_to`, evidence files | `roles/validation/tasks/main.yml` | Run `tests/validation_readonly.yml` |
| 17 | Safe modules: `validate:`, `force: false` | `tasks/ssh.yml`, `tasks/storage.yml` | Read why these cannot lock you out or wipe data |
| 18 | Pluggable behaviour via a variable (`include_tasks: install_{{ x }}.yml`) | `roles/jboss/tasks/main.yml` | Implement `install_archive.yml` |
| 19 | Idempotent READ -> compare -> WRITE for non-module tools (CLI) | `roles/jboss/tasks/configure.yml` | Run twice; second run should skip the writes |
| 20 | Testing pure logic in isolation | `tests/ss_loopback.yml` | Add a failing case and watch it caught |
| 21 | Check mode (`--check --diff`) and its limits; `check_mode: false`, `ansible_check_mode` | `roles/jboss/tasks/install_rpm.yml`, `main.yml` | Plan on a fresh host and see what is skipped |
| 22 | Treating input as hostile (allow-list parse -> schema -> JSON file) | `tools/issue_to_request.py`, `tests/test_issue_parser.py` | Add a nasty test case |

## Next concepts
`become` deep-dive, `block/rescue/always`, Execution Environments (`ansible-builder`), Molecule with UBI-init, then AAP (project / job template / credentials / survey / workflow).

## Habits worth building from day one
- Prefer a module over `command`/`shell`; if you must use them, add `changed_when` and `creates`/`removes`.
- Name every task; start names with a verb.
- Use FQCNs (`ansible.builtin.copy`), never short names.
- Run twice. The second run must show `changed=0`.
- `no_log: true` on any task touching secrets (and test that the failure message is still useful).

Toolchain: `pip install ansible-dev-tools` (adds navigator, builder, creator, molecule) and the VS Code *Ansible* extension.
