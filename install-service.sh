#!/usr/bin/env bash
#
# Installs/updates rd-import-web as a systemd service.
#
# Run this as the normal user that should own the app and its venv
# (e.g. alastair) — NOT as root. It uses sudo itself for the parts that
# actually need elevated privileges (writing the unit file, systemctl).
#
# Override any of these by setting them in the environment before running,
# e.g.:
#   PORT=8080 RD_IMPORT_ROOT=/home/rd/import ./install-service.sh
#
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
SERVICE_NAME="${SERVICE_NAME:-rd-import-web}"
SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$(whoami)}}"
SERVICE_GROUP="${SERVICE_GROUP:-$SERVICE_USER}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
RD_IMPORT_ROOT="${RD_IMPORT_ROOT:-/home/$SERVICE_USER}"
RD_CONF_PATH="${RD_CONF_PATH:-/etc/rd.conf}"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
AUTO_SCHEDULE_SERVICE_NAME="rd-auto-schedule"
AUTO_SCHEDULE_UNIT_PATH="/etc/systemd/system/${AUTO_SCHEDULE_SERVICE_NAME}.service"
AUTO_SCHEDULE_TIMER_PATH="/etc/systemd/system/${AUTO_SCHEDULE_SERVICE_NAME}.timer"

if [ "$EUID" -eq 0 ]; then
  echo "Don't run this script directly as root." >&2
  echo "Run it as the normal user that should own the app (e.g. alastair)." >&2
  echo "It will use sudo itself for the steps that need elevated privileges." >&2
  exit 1
fi

echo "== Rivendell Import Web — systemd install =="
echo "App directory : $APP_DIR"
echo "Service name  : $SERVICE_NAME"
echo "Service user  : $SERVICE_USER:$SERVICE_GROUP"
echo "Listen on     : $HOST:$PORT"
echo "Import root   : $RD_IMPORT_ROOT"
echo "rd.conf path  : $RD_CONF_PATH"
echo

cd "$APP_DIR"

# --- Python virtual environment ---
if [ ! -d venv ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

echo "Installing/updating dependencies..."
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt -q

# --- Sanity checks (warnings only, won't stop the install) ---
if ! command -v rdimport >/dev/null 2>&1; then
  echo
  echo "WARNING: 'rdimport' not found on PATH for $SERVICE_USER." >&2
  echo "  If it lives somewhere non-standard, add this line under [Service]" >&2
  echo "  in $UNIT_PATH after install:" >&2
  echo "    Environment=RDIMPORT_BIN=/full/path/to/rdimport" >&2
fi

if [ ! -r "$RD_CONF_PATH" ]; then
  echo
  echo "WARNING: $RD_CONF_PATH is not readable by $SERVICE_USER." >&2
  echo "  The app needs read access to it to reach the Rivendell database." >&2
fi

mkdir -p "$RD_IMPORT_ROOT"

# --- systemd unit ---
echo
echo "Writing $UNIT_PATH (requires sudo)..."

sudo tee "$UNIT_PATH" > /dev/null << EOF
[Unit]
Description=Rivendell Import Web
After=network.target mysql.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$APP_DIR
Environment=RD_IMPORT_ROOT=$RD_IMPORT_ROOT
Environment=RD_CONF_PATH=$RD_CONF_PATH
ExecStart=$APP_DIR/venv/bin/uvicorn app.main:app --host $HOST --port $PORT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# --- Auto Scheduling timer ---
# Fires every 15 minutes; app/auto_schedule_runner.py checks the rule
# saved from the Scheduler tab's Auto Scheduling card and only acts when
# it's actually due (see app/auto_schedule.py CHECK_WINDOW_MINUTES). The
# oneshot service below is never enabled/started directly — only the
# timer is, and it triggers the service by matching unit name.
sudo tee "$AUTO_SCHEDULE_UNIT_PATH" > /dev/null << EOF
[Unit]
Description=Rivendell Import Web - Auto Scheduling run
After=network.target mysql.service

[Service]
Type=oneshot
User=$SERVICE_USER
Group=$SERVICE_GROUP
WorkingDirectory=$APP_DIR
Environment=RD_IMPORT_ROOT=$RD_IMPORT_ROOT
Environment=RD_CONF_PATH=$RD_CONF_PATH
ExecStart=$APP_DIR/venv/bin/python -m app.auto_schedule_runner
EOF

sudo tee "$AUTO_SCHEDULE_TIMER_PATH" > /dev/null << EOF
[Unit]
Description=Rivendell Import Web - Auto Scheduling timer

[Timer]
OnCalendar=*:00/15
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl enable --now "${AUTO_SCHEDULE_SERVICE_NAME}.timer"

echo
echo "Done. Current status:"
sudo systemctl --no-pager -l status "$SERVICE_NAME" | head -n 12

echo
echo "Useful commands:"
echo "  sudo systemctl status $SERVICE_NAME"
echo "  sudo systemctl restart $SERVICE_NAME"
echo "  sudo systemctl stop $SERVICE_NAME"
echo "  journalctl -u $SERVICE_NAME -f"
echo "  systemctl list-timers ${AUTO_SCHEDULE_SERVICE_NAME}.timer"
echo "  journalctl -u $AUTO_SCHEDULE_SERVICE_NAME -f"
