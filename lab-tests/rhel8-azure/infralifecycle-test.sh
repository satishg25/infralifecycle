#!/usr/bin/env bash
# Run on the ANSIBLE CONTROLLER. Stages: bootstrap | preflight | tomcat | apache | all
# Override: TARGET=... ANSIBLE_USER=... PY=python3.12 FW=0 ./infralifecycle-test.sh tomcat
set -euo pipefail

TARGET="${TARGET:?set TARGET=<target ip>}"
ANSIBLE_USER="${ANSIBLE_USER:-$(id -un)}"
PY="${PY:-python3.11}"
FW="${FW:-1}"
VENV="$HOME/.venvs/ansible216"
REPO="$HOME/infralifecycle"
T="$REPO/.test"
A="$VENV/bin"

export ANSIBLE_CONFIG="$REPO/ansible/ansible.cfg"
log() { printf '\n=== %s\n' "$*"; }

bootstrap() {
  sudo dnf install -y git "$PY" "${PY}-pip" >/dev/null
  "$PY" -m venv "$VENV"
  "$A/pip" install -q -U pip
  "$A/pip" install -q 'ansible-core>=2.16,<2.17' passlib ansible-lint
  [[ -d "$REPO/.git" ]] || git clone --depth 1 https://github.com/satishg25/infralifecycle "$REPO"
  "$A/ansible-galaxy" collection install 'ansible.posix:==2.2.2' 'community.general:==13.5.0'
  mkdir -p "$T"
  ssh-keyscan -T 5 -H "$TARGET" >> "$HOME/.ssh/known_hosts" 2>/dev/null || true
  cat > "$T/inventory.yml" <<EOF
---
all:
  vars:
    ansible_user: ${ANSIBLE_USER}
  children:
    middleware_nodes: {hosts: {"${TARGET}": {}}}
    web_nodes:        {hosts: {"${TARGET}": {}}}
EOF
  local fw_t='[]' fw_a='[]'
  [[ "$FW" == 1 ]] && { fw_t='["8080/tcp"]'; fw_a='["80/tcp"]'; }
  cat > "$T/tomcat.vars.yml" <<EOF
---
target_hosts: middleware_nodes
run_baseline: false
run_validation: true
run_os_validation: false
tomcat_install_source: archive
tomcat_bind_address: "${TARGET}"
tomcat_firewall_ports: ${fw_t}
EOF
  cat > "$T/apache.vars.yml" <<EOF
---
target_hosts: web_nodes
run_baseline: false
run_validation: true
run_os_validation: false
apache_httpd_server_name: "${TARGET}"
apache_httpd_listen_port: 80
apache_httpd_firewall_ports: ${fw_a}
EOF
  "$A/ansible" --version | head -1
}

preflight() {
  log "Controller -> target: SSH, sudo, Python, OS"
  ssh -o BatchMode=yes "${ANSIBLE_USER}@${TARGET}" 'cat /etc/redhat-release; python3 --version; sudo -n true && echo sudo-ok; getenforce; systemctl is-active firewalld; df -h / | tail -1'
  log "Target egress + repos the roles depend on"
  ssh "${ANSIBLE_USER}@${TARGET}" 'curl -sSI -m 10 https://archive.apache.org/dist/tomcat/tomcat-10/v10.1.60/bin/apache-tomcat-10.1.60.tar.gz | head -1 || echo "NO EGRESS to archive.apache.org - set tomcat_archive_url to an internal mirror"; sudo dnf -q list available java-17-openjdk-headless httpd 2>&1 | tail -3'
  log "Ansible ping"
  "$A/ansible" all -i "$T/inventory.yml" -m ansible.builtin.ping
}

run_case() {
  local pb="$REPO/ansible/playbooks/thin/$1.yml" vars="$T/$2" ; cd "$REPO/ansible"
  local common=(-i "$T/inventory.yml" -e "@$vars")
  log "$1: syntax-check"; "$A/ansible-playbook" "$pb" "${common[@]}" --syntax-check
  log "$1: plan (--check --diff)"
  "$A/ansible-playbook" "$pb" "${common[@]}" --check --diff
  log "$1: apply"; "$A/ansible-playbook" "$pb" "${common[@]}"
  log "$1: re-apply - must be changed=0 failed=0"
  "$A/ansible-playbook" "$pb" "${common[@]}" | tee "$T/$1.second.log"
  grep -E "^${TARGET//./\\.}\s+:" "$T/$1.second.log" | grep -q 'changed=0 .*failed=0' \
    && echo "IDEMPOTENT: PASS" || { echo "IDEMPOTENT: FAIL (see $T/$1.second.log)"; return 1; }
}

tomcat() {
  run_case tomcat_standalone tomcat.vars.yml
  log "tomcat: external reachability from the controller"
  curl -sS -m 10 -i "http://${TARGET}:8080/health/" | head -5
}
apache() {
  run_case apache_standalone apache.vars.yml
  log "apache: external reachability from the controller"
  curl -sS -m 10 -i "http://${TARGET}/health/" | head -5
  curl -sS -m 10 -X TRACE -o /dev/null -w 'TRACE -> HTTP %{http_code} (expect 403/405)\n' "http://${TARGET}/"
}

case "${1:-}" in
  bootstrap) bootstrap ;; preflight) preflight ;; tomcat) tomcat ;; apache) apache ;;
  all) bootstrap; preflight; tomcat; apache ;;
  *) sed -n '2,3p' "$0"; exit 2 ;;
esac
