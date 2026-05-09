#!/usr/bin/env bash
# scripts/bootstrap-runner.sh — One-shot Gitea runner bootstrap for RHEL 9.
# Equivalent to running the gitea-runner Ansible role.
# Usage: sudo bash bootstrap-runner.sh <registration-token>
#
# Get the token from: Gitea → Site Admin → Runners → Create new runner
# Token is single-use — consumed on registration, never stored.
set -euo pipefail

# ── Variables ─────────────────────────────────────────────────────────────────
RUNNER_TOKEN="${1:?Usage: sudo bash bootstrap-runner.sh <registration-token>}"
GITEA_URL="https://gitea.cove.gdit"
ACT_RUNNER_VERSION="0.2.11"
RUNNER_NAME="$(hostname)"
# Labels use act_runner schema: name:host for native execution, name:docker://image for container.
# 'os:linux' and 'arch:amd64' look like schema URIs to act_runner and cause registration failure.
RUNNER_LABELS="self-hosted:host,linux:host"
RUNNER_CAPACITY=2

RUNNER_USER="gitea-runner"
RUNNER_GROUP="gitea-runner"
RUNNER_INSTALL_DIR="/usr/local/bin"
RUNNER_CONFIG_DIR="/etc/act_runner"
RUNNER_DATA_DIR="/var/lib/act_runner"

ARCH="amd64"
DOWNLOAD_URL="https://gitea.com/gitea/act_runner/releases/download/v${ACT_RUNNER_VERSION}/act_runner-${ACT_RUNNER_VERSION}-linux-${ARCH}"

# ── Helpers ───────────────────────────────────────────────────────────────────
info()  { echo "  [ok] $*"; }
step()  { echo; echo "==> $*"; }

# ── Docker CE ─────────────────────────────────────────────────────────────────
step "Installing Docker CE"
dnf install -y dnf-plugins-core
curl -fsSL https://download.docker.com/linux/rhel/docker-ce.repo \
  -o /etc/yum.repos.d/docker-ce.repo
dnf install -y \
  container-selinux \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin
systemctl enable --now docker
info "Docker CE installed and running"

# ── System user and directories ───────────────────────────────────────────────
step "Creating gitea-runner system account"
groupadd --system "${RUNNER_GROUP}" 2>/dev/null || info "group already exists"
useradd  --system \
         --gid "${RUNNER_GROUP}" \
         --no-create-home \
         --home-dir "${RUNNER_DATA_DIR}" \
         --shell /sbin/nologin \
         --comment "Gitea Act Runner service account" \
         "${RUNNER_USER}" 2>/dev/null || info "user already exists"

usermod -aG docker "${RUNNER_USER}"
info "Runner user added to docker group"

install -d -o "${RUNNER_USER}" -g "${RUNNER_GROUP}" -m 0750 "${RUNNER_DATA_DIR}"
install -d -o root              -g "${RUNNER_GROUP}" -m 0750 "${RUNNER_CONFIG_DIR}"
install -d -o "${RUNNER_USER}" -g "${RUNNER_GROUP}" -m 0750 "${RUNNER_DATA_DIR}/cache"
install -d -o "${RUNNER_USER}" -g "${RUNNER_GROUP}" -m 0750 "${RUNNER_DATA_DIR}/workdir"

# ── act_runner binary ─────────────────────────────────────────────────────────
step "Installing act_runner ${ACT_RUNNER_VERSION}"
if "${RUNNER_INSTALL_DIR}/act_runner" --version 2>/dev/null | grep -q "${ACT_RUNNER_VERSION}"; then
  info "act_runner ${ACT_RUNNER_VERSION} already installed"
else
  curl -fsSL "${DOWNLOAD_URL}" -o "${RUNNER_INSTALL_DIR}/act_runner"
  chmod 0755 "${RUNNER_INSTALL_DIR}/act_runner"
  info "act_runner downloaded"
fi

# ── Configuration ─────────────────────────────────────────────────────────────
step "Writing config"
cat > "${RUNNER_CONFIG_DIR}/config.yaml" <<EOF
log:
  level: info

runner:
  file: ${RUNNER_DATA_DIR}/.runner
  capacity: ${RUNNER_CAPACITY}
  timeout: 3h
  insecure: false
  fetch_timeout: 5s
  fetch_interval: 2s

cache:
  enabled: true
  dir: ${RUNNER_DATA_DIR}/cache

container:
  network: bridge
  enable_ipv6: false
  valid_volumes: []
  docker_host: unix:///var/run/docker.sock
  force_pull: false
  force_rebuild: false

host:
  workdir_parent: ${RUNNER_DATA_DIR}/workdir
EOF
chown root:"${RUNNER_GROUP}" "${RUNNER_CONFIG_DIR}/config.yaml"
chmod 0640 "${RUNNER_CONFIG_DIR}/config.yaml"
info "Config written"

# ── Registration ──────────────────────────────────────────────────────────────
step "Registering runner with Gitea"
if [[ -f "${RUNNER_DATA_DIR}/.runner" ]]; then
  info "Runner already registered — skipping"
else
  sudo -u "${RUNNER_USER}" "${RUNNER_INSTALL_DIR}/act_runner" register \
    --no-interactive \
    --config "${RUNNER_CONFIG_DIR}/config.yaml" \
    --instance "${GITEA_URL}" \
    --token   "${RUNNER_TOKEN}" \
    --name    "${RUNNER_NAME}" \
    --labels  "${RUNNER_LABELS}"
  chmod 0600 "${RUNNER_DATA_DIR}/.runner"
  info "Runner registered"
fi

# ── systemd service ───────────────────────────────────────────────────────────
step "Installing systemd service"
cat > /etc/systemd/system/act_runner.service <<EOF
[Unit]
Description=Gitea Act Runner
Documentation=https://gitea.com/gitea/act_runner
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=${RUNNER_USER}
Group=${RUNNER_GROUP}
WorkingDirectory=${RUNNER_DATA_DIR}
ExecStart=${RUNNER_INSTALL_DIR}/act_runner daemon --config ${RUNNER_CONFIG_DIR}/config.yaml
Restart=always
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=${RUNNER_DATA_DIR}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now act_runner
info "act_runner service enabled and started"

echo
echo "Bootstrap complete. Runner '${RUNNER_NAME}' is registered and running."
echo "Check status: systemctl status act_runner"
echo "View logs:    journalctl -u act_runner -f"
