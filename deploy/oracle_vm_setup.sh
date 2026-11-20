#!/usr/bin/env bash
# MH3U Revival server: one-command setup for a fresh Oracle Cloud VM.
#
# For Ubuntu 22.04/24.04 or Oracle Linux 9, on x86 (VM.Standard.E2.1.Micro) or Arm
# (VM.Standard.A1.Flex). Safe to run again: it updates both repos, keeps your settings
# and restarts the server.
#
#   sudo bash oracle_vm_setup.sh [PUBLIC_IP] [RELAY_MODE]
#
#   PUBLIC_IP   the VM's public IP from the Oracle console (detected if left out)
#   RELAY_MODE  force = every hunt link goes through this VM (default on first run)
#               auto  = only links that need it; off = no relay
#
# FIRST open these ports in the Oracle console: the VCN's security list, ingress rules,
# source 0.0.0.0/0: UDP 1223-1224, 10025 and 27100-27387 (the game), and TCP 8080 (the
# status page the launcher and Discord read; see MH3U_STATUS_PORT). This script opens
# the same ports in the VM's own firewall. Both are needed.
#
# What it sets up:
#   /opt/mh3u/mh3u-revival              the server
#   /opt/mh3u/external/NintendoClients  the patched library it needs (mh3u-revival branch)
#   /opt/mh3u/venv                      Python 3.13 (uv installs it into /opt/mh3u/python)
#   /etc/mh3u.env                       server settings (MH3U_* variables; readable
#                                       by root only, as it can hold Discord webhooks)
#   /var/lib/mh3u                       state the server keeps (Discord message id)
#   /swapfile                           1 GB of swap on small VMs, as a safety net
#   mh3u.service                        runs as user "mh3u", restarts if it crashes
#
# Afterwards:
#   journalctl -u mh3u -f               live log (a STATUS line every 60 s)
#   sudo systemctl restart mh3u         after editing /etc/mh3u.env
set -euo pipefail

ROOT=/opt/mh3u
ENV_FILE=/etc/mh3u.env
UNIT=/etc/systemd/system/mh3u.service
SERVER_REPO=https://github.com/Matt-Wood-23/mh3u-revival.git
NC_REPO=https://github.com/Matt-Wood-23/NintendoClients.git
NC_BRANCH=mh3u-revival
PY_VERSION=3.13
# 27100-27387 is the default relay pool (MH3U_RELAY_PORT_START/_END). Widen both
# firewalls if you widen the pool.
UDP_PORTS="1223,1224,10025,27100:27387"
DEFAULT_STATUS_PORT=8080

say() { printf '\n== %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run it with sudo"

PUBLIC_IP="${1:-}"
RELAY_MODE="${2:-}"
case "$RELAY_MODE" in ""|force|auto|off) ;; *) die "relay mode must be force, auto or off" ;; esac
if [ -n "$PUBLIC_IP" ] && ! [[ "$PUBLIC_IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]]; then
  die "'$PUBLIC_IP' isn't an IPv4 address"
fi

say "packages"
if command -v apt-get >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  # A new Ubuntu VM installs its own updates right after boot. Wait for them instead
  # of failing with "Could not get lock".
  if command -v cloud-init >/dev/null; then
    echo "waiting for first-boot setup to finish..."
    timeout 600 cloud-init status --wait >/dev/null 2>&1 || true
  fi
  APT=(apt-get -q -o DPkg::Lock::Timeout=600)
  for _ in 1 2 3 4 5 6; do
    "${APT[@]}" update && break
    echo "apt is busy; trying again in 20 s"
    sleep 20
  done
  "${APT[@]}" install -y git curl ca-certificates python3-venv
elif command -v dnf >/dev/null; then
  dnf install -y -q git curl python3
else
  die "no apt-get or dnf found; this script supports Ubuntu and Oracle Linux"
fi

say "swap"
MEM_MB="$(awk '/^MemTotal:/ { print int($2 / 1024) }' /proc/meminfo)"
if [ -n "$(swapon --show --noheadings 2>/dev/null)" ]; then
  echo "swap already on"
elif [ "$MEM_MB" -ge 4096 ]; then
  echo "${MEM_MB} MB of RAM; no swap needed"
else
  # A safety net for a 1-2 GB VM: a memory spike slows the server down instead of
  # getting it killed.
  fallocate -l 1G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=1024 status=none
  chmod 600 /swapfile
  mkswap -q /swapfile
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "1 GB swap file on (${MEM_MB} MB of RAM)"
fi

say "user and folders"
id mh3u >/dev/null 2>&1 || useradd --system --home-dir "$ROOT" --no-create-home \
  --shell /usr/sbin/nologin mh3u
mkdir -p "$ROOT/external"

say "code"
fetch() {  # fetch <repo url> <dir> [branch]
  if [ -d "$2/.git" ]; then
    git -C "$2" pull --ff-only
  elif [ -n "${3:-}" ]; then
    git clone --branch "$3" "$1" "$2"
  else
    git clone "$1" "$2"
  fi
}
fetch "$SERVER_REPO" "$ROOT/mh3u-revival"
fetch "$NC_REPO" "$ROOT/external/NintendoClients" "$NC_BRANCH"

say "Python $PY_VERSION"
if [ ! -x "$ROOT/tools/bin/uv" ]; then
  python3 -m venv "$ROOT/tools"
  "$ROOT/tools/bin/pip" install -q --upgrade pip
  "$ROOT/tools/bin/pip" install -q uv
fi
export UV_PYTHON_INSTALL_DIR="$ROOT/python"
[ -x "$ROOT/venv/bin/python" ] || "$ROOT/tools/bin/uv" venv -q --python "$PY_VERSION" "$ROOT/venv"
# requirements.txt has a relative path (./vendor/netifaces_stub), so install from the repo.
(cd "$ROOT/mh3u-revival" &&
  "$ROOT/tools/bin/uv" pip install -q --python "$ROOT/venv/bin/python" -r requirements.txt)
"$ROOT/venv/bin/python" - "$ROOT/external/NintendoClients" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
import nintendo, anynet  # noqa: F401  (fails here, not in the service, if setup broke)
print("Python", sys.version.split()[0], "- imports OK")
PY

say "settings ($ENV_FILE)"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<'EOF'
# MH3U Revival server settings. After editing: sudo systemctl restart mh3u
# Any MH3U_* variable from config.py or limits.py works here. The defaults suit a
# small group; for a big community raise these (defaults shown):
#   MH3U_MAX_CONNECTIONS=128
#   MH3U_MAX_ROOMS=48
#   MH3U_MAX_CONNECTIONS_PER_IP=16
#   MH3U_SHOUT_BROADCAST_FALLBACK=1   (set 0 on a big server)
# More rooms under relay "force" also need a bigger relay pool
# (MH3U_RELAY_PORT_START/_END, 6 ports per room) opened in both firewalls.

# Discord (optional). Channel settings > Integrations > Webhooks > New Webhook > Copy URL.
#   MH3U_DISCORD_STATUS_WEBHOOK=   one message kept up to date with player/room counts
#   MH3U_DISCORD_ALERT_WEBHOOK=    a post when the server starts, stops or comes back
#                                  after a crash
#   MH3U_SERVER_NAME=              the name those messages use

# Log to the journal only (journalctl -u mh3u), not a file.
MH3U_LOG_FILE=
PYTHONUNBUFFERED=1
EOF
fi
get_env() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1; }
set_env() {  # replace the KEY= line, or add one
  if grep -q "^$1=" "$ENV_FILE"; then
    sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"
  else
    echo "$1=$2" >> "$ENV_FILE"
  fi
}
if [ -z "$PUBLIC_IP" ]; then
  PUBLIC_IP="$(get_env MH3U_ADVERTISE)"
fi
if [ -z "$PUBLIC_IP" ]; then
  PUBLIC_IP="$(curl -4 -s --max-time 5 https://ifconfig.me || true)"
  [[ "$PUBLIC_IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] ||
    die "couldn't detect the public IP; run again with it as the first argument"
  echo "detected public IP: $PUBLIC_IP"
fi
[ -n "$RELAY_MODE" ] || RELAY_MODE="$(get_env MH3U_RELAY)"
[ -n "$RELAY_MODE" ] || RELAY_MODE=force
set_env MH3U_ADVERTISE "$PUBLIC_IP"
set_env MH3U_RELAY "$RELAY_MODE"
# The status page is on unless you set MH3U_STATUS_PORT=0 yourself.
grep -q '^MH3U_STATUS_PORT=' "$ENV_FILE" || set_env MH3U_STATUS_PORT "$DEFAULT_STATUS_PORT"
# Admin port for announcements and planned restarts: 127.0.0.1 only, never opened in a
# firewall. Use it over SSH (docs/HOSTING.md, "Announcements and planned restarts").
grep -q '^MH3U_ADMIN_PORT=' "$ENV_FILE" || set_env MH3U_ADMIN_PORT 8081
STATUS_PORT="$(get_env MH3U_STATUS_PORT)"
[[ "$STATUS_PORT" =~ ^[0-9]+$ ]] || STATUS_PORT=0
# systemd reads this file as root, so the server doesn't need to; webhook URLs are secrets.
chown root:root "$ENV_FILE"
chmod 600 "$ENV_FILE"
grep -v '^#' "$ENV_FILE" | grep . | sed -E 's#^(MH3U_DISCORD_[A-Z_]*WEBHOOK=).+#\1(set, hidden)#'

say "VM firewall"
if command -v firewall-cmd >/dev/null && firewall-cmd --state >/dev/null 2>&1; then
  for p in 1223-1224/udp 10025/udp 27100-27387/udp; do
    firewall-cmd -q --permanent --add-port="$p"
  done
  if [ "$STATUS_PORT" -gt 0 ]; then
    firewall-cmd -q --permanent --add-port="$STATUS_PORT/tcp"
  fi
  firewall-cmd -q --reload
  echo "firewalld: UDP 1223-1224, 10025, 27100-27387 open"
  if [ "$STATUS_PORT" -gt 0 ]; then
    echo "firewalld: TCP $STATUS_PORT (status page) open"
  fi
elif command -v iptables >/dev/null; then
  allow() {  # allow <description> <iptables match...>
    local what="$1"
    shift
    local rule=("$@" -j ACCEPT)
    if iptables -C INPUT "${rule[@]}" 2>/dev/null; then
      echo "iptables: $what already open"
      return
    fi
    # Oracle's Ubuntu images end INPUT with a REJECT rule; ours has to go above it.
    local n
    n="$(iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" { print $1; exit }')"
    if [ -n "$n" ]; then
      iptables -I INPUT "$n" "${rule[@]}"
    else
      iptables -A INPUT "${rule[@]}"
    fi
    echo "iptables: $what open"
  }
  allow "UDP $UDP_PORTS" -p udp -m multiport --dports "$UDP_PORTS"
  if [ "$STATUS_PORT" -gt 0 ]; then
    allow "TCP $STATUS_PORT (status page)" -p tcp -m state --state NEW --dport "$STATUS_PORT"
  fi
  if ! command -v netfilter-persistent >/dev/null && command -v apt-get >/dev/null; then
    "${APT[@]}" install -y iptables-persistent
  fi
  if command -v netfilter-persistent >/dev/null; then
    netfilter-persistent save >/dev/null 2>&1 && echo "iptables: saved for reboots"
  else
    echo "WARNING: couldn't save the iptables rule; it will be gone after a reboot"
  fi
else
  echo "no firewalld or iptables found; check the VM's firewall yourself"
fi

say "service"
cat > "$UNIT" <<EOF
[Unit]
Description=MH3U Revival server
After=network-online.target
Wants=network-online.target

[Service]
User=mh3u
Group=mh3u
WorkingDirectory=$ROOT/mh3u-revival
EnvironmentFile=$ENV_FILE
ExecStart=$ROOT/venv/bin/python server.py
StandardInput=null
Restart=on-failure
RestartSec=5
# SIGTERM makes the server shut down cleanly (and post "stopped" to Discord, if set up).
TimeoutStopSec=20
StateDirectory=mh3u
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable -q mh3u
systemctl restart mh3u
sleep 5
if ! systemctl is-active -q mh3u; then
  journalctl -u mh3u -n 40 --no-pager || true
  die "the server didn't start (log above)"
fi
journalctl -u mh3u -n 10 --no-pager || true

cat <<EOF

Done: the server is running, advertising $PUBLIC_IP, relay mode "$RELAY_MODE".

On your PC:
  1. Put $PUBLIC_IP in each Cemu's mh3u_server.txt (portable\\mh3u_server.txt).
  2. From your mh3u-revival folder:
       python tests/extkit/check_natcheck.py $PUBLIC_IP
       python tests/extkit/check_server_leg.py $PUBLIC_IP
     If both fail, the Oracle security list is missing the UDP ports.
  3. Create a room in one Cemu and join it from the other.
EOF
if [ "$STATUS_PORT" -gt 0 ]; then
  cat <<EOF
  4. Status page: http://$PUBLIC_IP:$STATUS_PORT/status
     If it doesn't load, the Oracle security list is missing TCP $STATUS_PORT.
EOF
fi
cat <<EOF

Live log: journalctl -u mh3u -f
EOF
