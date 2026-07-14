#!/bin/bash
set -e

APP_DIR="/opt/daxiao"
VENV_DIR="$APP_DIR/venv"

echo "=== 李大霄视频追踪系统 部署脚本 ==="

if [ ! -f "$APP_DIR/.env" ]; then
    echo "[ERROR] 请先创建 $APP_DIR/.env 配置文件"
    echo "  参考 backend/.env.example"
    exit 1
fi

apt-get update
apt-get install -y python3.11 python3.11-venv python3-pip \
    libgl1-mesa-glx libglib2.0-0 libnss3 libnspr4 libatk-bridge2.0-0 \
    libatk1.0-0 libcups2 libdrm2 libdbus-1-3 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2

if [ ! -d "$VENV_DIR" ]; then
    python3.11 -m venv "$VENV_DIR"
fi

$VENV_DIR/bin/pip install --upgrade pip
$VENV_DIR/bin/pip install -r "$APP_DIR/backend/requirements.txt"
$VENV_DIR/bin/python -m playwright install chromium --with-deps

$VENV_DIR/bin/python -m backend.main init-db

cp "$APP_DIR/deploy/daxiao.service" /etc/systemd/system/

systemctl daemon-reload
systemctl enable daxiao
systemctl restart daxiao

echo ""
echo "=== 部署完成 ==="
echo "Web 面板: http://$(hostname -I | awk '{print $1}'):8080"
echo "查看状态: systemctl status daxiao"
echo "查看日志: journalctl -u daxiao -f"
