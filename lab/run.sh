#!/usr/bin/env bash
# Local lab driver: build/start the containers a use case needs, then
#   1. plan   (--check --diff; on a fresh container this is the "new host" preview)
#   2. apply
#   3. apply again - every host must report changed=0 (idempotency gate)
#   4. lab/tests/<use case>.yml if present (failover drills for the HA cases)
#
# Usage:  lab/run.sh <use case>... [--fresh]      use cases: tomcat_standalone tomcat_ha
#         lab/run.sh all [--fresh]                           apache_standalone apache_ha
#         lab/run.sh down                         remove all lab containers
#   --fresh  recreate the containers first (tests the first-install path and the plan on a new host)
#
# Needs: Linux/WSL with Docker, ansible-playbook on PATH (or ANSIBLE_BIN_DIR=<venv>/bin), the
# collections from ansible/requirements.yml, and an SSH key in ~/.ssh/id_ed25519(.pub).
# The nodes are Rocky Linux 8 (Python 3.6): use ansible-core 2.16 - the last release that manages
# RHEL 8 - which is also what AAP 2.5 runs. Newer ansible-core fails on these hosts.
set -euo pipefail

LAB="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$LAB")"
PROJECT=infralifecycle-lab
COMPOSE=(docker compose -f "$LAB/compose.yml" -p "$PROJECT")
BIN="${ANSIBLE_BIN_DIR:+$ANSIBLE_BIN_DIR/}"
KEY="${LAB_SSH_KEY:-$HOME/.ssh/id_ed25519}"
# Works in this repo (ansible/playbooks/thin) and in the export_thin.py handover (playbooks/).
if [[ -d "$ROOT/ansible/playbooks/thin" ]]; then WORK="$ROOT/ansible"; PLAYBOOKS=playbooks/thin
else WORK="$ROOT"; PLAYBOOKS=playbooks; fi
# Named explicitly: Ansible ignores an ansible.cfg in a world-writable directory (e.g. /mnt/c on WSL).
export ANSIBLE_CONFIG="${ANSIBLE_CONFIG:-$WORK/ansible.cfg}"

declare -A NODES=(
  [tomcat_standalone]="tc1"
  [tomcat_ha]="tcha1 tcha2 tclb"
  [apache_standalone]="ap1"
  [apache_ha]="apha1 apha2"
)
declare -A ADDR=(
  [tc1]=172.30.0.11 [tcha1]=172.30.0.21 [tcha2]=172.30.0.22 [tclb]=172.30.0.20
  [ap1]=172.30.0.31 [apha1]=172.30.0.41 [apha2]=172.30.0.42
)

log() { printf '\n=== %s\n' "$*"; }

if [[ "${1:-}" == down ]]; then
  "${COMPOSE[@]}" down --remove-orphans
  exit 0
fi

fresh=false
cases=()
for arg in "$@"; do
  case "$arg" in
    --fresh) fresh=true ;;
    all) cases+=(tomcat_standalone tomcat_ha apache_standalone apache_ha) ;;
    *) [[ -n "${NODES[$arg]:-}" ]] || { echo "unknown use case: $arg" >&2; exit 2; }; cases+=("$arg") ;;
  esac
done
(( ${#cases[@]} )) || { sed -n '2,18p' "$0"; exit 2; }

version="$("${BIN}ansible-playbook" --version | sed -n '1s/.*core \([0-9]*\.[0-9]*\).*/\1/p')"
if [[ "$(printf '%s\n2.16\n' "$version" | sort -V | tail -1)" != 2.16 ]]; then
  echo "ansible-core $version cannot manage the Rocky/RHEL 8 lab nodes - use 2.16 (ANSIBLE_BIN_DIR=<venv>/bin)" >&2
  exit 2
fi

# The image takes your public key; the private key never leaves ~/.ssh.
mkdir -p "$LAB/.build" "$LAB/.state"
cp "$KEY.pub" "$LAB/.build/authorized_keys"

# Lab-only cluster password, generated once and kept out of git (lab/.state is ignored).
if [[ ! -s "$LAB/.state/secrets.yml" ]]; then
  umask 077
  printf -- '---\npacemaker_cluster_password: "%s"\n' "$(head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9')" > "$LAB/.state/secrets.yml"
fi

nodes=()
for c in "${cases[@]}"; do read -ra n <<< "${NODES[$c]}"; nodes+=("${n[@]}"); done

log "Build image and start: ${nodes[*]}"
"${COMPOSE[@]}" build --quiet tc1
$fresh && "${COMPOSE[@]}" rm -sf "${nodes[@]}"
"${COMPOSE[@]}" up -d --no-deps "${nodes[@]}"

# Fresh containers have new host keys: record them (host key checking stays on).
for n in "${nodes[@]}"; do
  ip="${ADDR[$n]}"
  for _ in $(seq 30); do ssh-keyscan -T 2 -t ed25519 "$ip" > "$LAB/.state/$n.key" 2>/dev/null && [[ -s "$LAB/.state/$n.key" ]] && break; sleep 1; done
  [[ -s "$LAB/.state/$n.key" ]] || { echo "sshd on $n ($ip) did not come up" >&2; exit 1; }
  ssh-keygen -R "$ip" >/dev/null 2>&1 || true
  cat "$LAB/.state/$n.key" >> "$HOME/.ssh/known_hosts"
done

cd "$WORK"
run() {  # run <use case> <extra ansible-playbook args...>
  local uc="$1"; shift
  "${BIN}ansible-playbook" "$PLAYBOOKS/$uc.yml" -i "$LAB/inventory.yml" \
    -e "@$LAB/vars/$uc.yml" -e "@$LAB/.state/secrets.yml" --private-key "$KEY" "$@"
}

for uc in "${cases[@]}"; do
  log "$uc: plan (--check --diff)"
  run "$uc" --check --diff

  log "$uc: apply"
  run "$uc"

  log "$uc: apply again (must be changed=0 everywhere)"
  run "$uc" | tee "$LAB/.state/$uc.second.log"
  if grep -E '^[A-Za-z0-9_.-]+ +: ok=' "$LAB/.state/$uc.second.log" | grep -vE 'changed=0 '; then
    echo "IDEMPOTENCY FAILED for $uc (hosts above changed on the second run)" >&2
    exit 1
  fi

  if [[ -f "$LAB/tests/$uc.yml" ]]; then
    log "$uc: lab drill (lab/tests/$uc.yml)"
    "${BIN}ansible-playbook" "$LAB/tests/$uc.yml" -i "$LAB/inventory.yml" \
      -e "@$LAB/vars/$uc.yml" --private-key "$KEY"
  fi
  log "$uc: PASSED"
done
