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

# 3) install the bot as a service (auto-restart, survives reboot)
#    use the REAL repo path ($DIR) — root's home is /root, not /home/root
sudo tee /etc/systemd/system/nix2-bot.service >/dev/null <<EOF
[Unit]
Description=nix2 cheap+signal paper bot (BTC 5m)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$DIR
ExecStart=$DIR/.venv/bin/python bot/live/nix2_live.py --venue coinbase --stake 10 --account paper1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now nix2-bot

# 4) hourly status push so you can check STATUS.md from your phone
( crontab -l 2>/dev/null; \
  echo "0 * * * * cd $DIR && .venv/bin/python bot/live/status.py --accounts paper1 >/dev/null 2>&1" ) | crontab -

echo "== nix2 bot deployed =="
echo "logs:    journalctl -u nix2-bot -f"
echo "status:  cat $DIR/bot/live/STATUS.md   (also pushed to the repo hourly)"
echo "verdict: .venv/bin/python bot/live/settle.py --account paper1"
