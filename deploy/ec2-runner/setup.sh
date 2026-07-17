#!/usr/bin/env bash
# Provision the running instance: install claude CLI, drop the runner + env, and
# start it as a systemd service. Requires ./up.sh to have run and runner.env filled.
set -euo pipefail
cd "$(dirname "$0")"

[[ -f .state.json ]] || { echo "no .state.json — run ./up.sh first" >&2; exit 1; }
[[ -f runner.env ]] || { echo "create runner.env from runner.env.example (set CANOPY_TOKEN + CLAUDE_CODE_OAUTH_TOKEN)" >&2; exit 1; }

IP=$(python3 -c 'import json;print(json.load(open(".state.json"))["public_ip"])')
KEYFILE=$(python3 -c 'import json;print(json.load(open(".state.json"))["key_file"])')
SSH=(ssh -i "$KEYFILE" -o StrictHostKeyChecking=accept-new "ubuntu@$IP")
SCP=(scp -i "$KEYFILE" -o StrictHostKeyChecking=accept-new)

echo ">> copying runner + env to $IP"
"${SCP[@]}" cloud_runner.py "ubuntu@$IP:/tmp/cloud_runner.py"
"${SCP[@]}" runner.env "ubuntu@$IP:/tmp/runner.env"

echo ">> provisioning (this installs Node + the claude CLI on first run)"
"${SSH[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
sudo mkdir -p /opt/canopy-runner
sudo mv /tmp/cloud_runner.py /opt/canopy-runner/cloud_runner.py
sudo mv /tmp/runner.env /etc/canopy-runner.env
sudo chmod 600 /etc/canopy-runner.env
if ! command -v claude >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
  sudo npm i -g @anthropic-ai/claude-code
fi
echo "claude: $(claude --version 2>/dev/null || echo MISSING)"

echo ">> claude smoke test (auth check)"
if sudo bash -c 'set -a; source /etc/canopy-runner.env; set +a; claude -p "reply with exactly: OK" --output-format text --dangerously-skip-permissions' 2>/tmp/claude.err; then
  echo "   claude auth OK"
else
  echo "   !! claude smoke FAILED — token likely invalid:"; cat /tmp/claude.err | head -5
fi

sudo tee /etc/systemd/system/canopy-runner.service >/dev/null <<'UNIT'
[Unit]
Description=Canopy cloud runner
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
EnvironmentFile=/etc/canopy-runner.env
ExecStart=/usr/bin/python3 /opt/canopy-runner/cloud_runner.py
Restart=on-failure
RestartSec=5
User=ubuntu
[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now canopy-runner.service
sleep 3
sudo systemctl --no-pager status canopy-runner.service | head -14
REMOTE

echo ""
echo "==> provisioned. follow logs:"
echo "    ssh -i $KEYFILE ubuntu@$IP 'journalctl -u canopy-runner -f'"
