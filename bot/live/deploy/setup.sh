#!/usr/bin/env bash
# Turnkey deploy of the nix2 paper bot on a fresh Ubuntu/Debian VPS.
# Run once as your normal user (with sudo available). Edit YOURUSER first.
set -euo pipefail

REPO="https://github.com/xin10ylop/polybtctelonex.git"
BRANCH="claude/polymarket-btc-strategy-ys9coc"
DIR="$HOME/polybtctelonex"

# 1) system deps
sudo apt-get update -y && sudo apt-get install -y python3-venv git

# 2) clone + venv + deps
[ -d "$DIR" ] || git clone -b "$BRANCH" "$REPO" "$DIR"
cd "$DIR"
python3 -m venv .venv
.venv/bin/pip install -r bot/live/requirements.txt

# 3) retire the legacy one-off units.
#    Earlier revisions installed a separate ad-hoc unit per variant as each
#    was added (nix2-bot = paper1, nix2-bot-v2 = paper2, nix2-bot-v4 =
#    paper4). On 2026-08-02 those were found running ALONGSIDE the per-account
#    units below, so paper1 and paper4 had two live processes each writing to
#    the same log — every window logged twice. (No trade was double-counted:
#    duplicated TRADE records were 0.) Any `pkill` was instantly undone by
#    their Restart=always, so they must be DISABLED, not killed.
for legacy in nix2-bot nix2-bot-v2 nix2-bot-v4; do
  sudo systemctl disable --now "$legacy" 2>/dev/null || true
  sudo rm -f "/etc/systemd/system/$legacy.service"
done

# 4) one unit per paper account (auto-restart, survives reboot).
#    Use the REAL repo path ($DIR) — root's home is /root, not /home/root.
#    Keep these names in sync with bot/cheapsig.json: v1=paper1, v2=paper2
#    (q_imb gate), v3=paper3 (walk the ladder, $25), v4=paper4 (walk +
#    realistic fills, $50).
install_unit() {   # $1=account  $2..=extra bot args
  local acct="$1"; shift
  sudo tee "/etc/systemd/system/nix2-$acct.service" >/dev/null <<EOF
[Unit]
Description=nix2 cheap+signal paper bot ($acct)
After=network-online.target
Wants=network-online.target
# a genuine config error should stop the unit, not crash-loop forever
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
Environment=PYTHONUNBUFFERED=1
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python bot/live/nix2_live.py --venue coinbase --account $acct $*
Restart=always
RestartSec=10
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
}
# NOTE: deliberately no MemoryMax. A cap is prudent on a 512MB box, but it
# must come from a MEASURED ceiling (`systemctl show nix2-paper1 -p MemoryPeak`
# after a week), not a guess — an under-set cap silently OOM-kills the fleet.
install_unit paper1 --stake 10
install_unit paper2 --stake 10 --qimb-max -0.05
install_unit paper3 --stake 25 --walk
install_unit paper4 --stake 50 --walk --realistic --slip-ticks 1

sudo systemctl daemon-reload
sudo systemctl enable --now nix2-paper1 nix2-paper2 nix2-paper3 nix2-paper4

# 5) hourly status push so you can check STATUS.md from your phone
( crontab -l 2>/dev/null | grep -v 'bot/live/status.py'; \
  echo "0 * * * * cd $DIR && .venv/bin/python bot/live/status.py --accounts paper1 paper2 paper3 paper4 >/dev/null 2>&1" ) | crontab -

echo "== nix2 paper fleet deployed =="
echo "running: systemctl status 'nix2-paper*' --no-pager | grep -E '●|Active'"
echo "sanity:  ps -eo args --no-headers | grep -c '[n]ix2_live.py'   # must be 4"
echo "logs:    journalctl -u nix2-paper1 -f"
echo "verdict: for A in 'paper1 10 1000' 'paper2 10 1000' 'paper3 25 2500' 'paper4 50 5000'; do"
echo "           set -- \$A; .venv/bin/python bot/live/settle.py --account \$1 --stake \$2 --bankroll \$3; done"
