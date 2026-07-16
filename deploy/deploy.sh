#!/bin/bash
set -e

APP_DIR="/opt/daxiao"
VENV_DIR="$APP_DIR/venv"

echo "=== 李大霄视频追踪系统 部署脚本 ==="

if [ ! -f "$APP_DIR/.env" ]; then
    echo "[ERROR] 请先创建 $APP_DIR/.env 配置文件"
    echo "  参考 .env.example"
    exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

$VENV_DIR/bin/pip install --upgrade pip
$VENV_DIR/bin/pip install -r "$APP_DIR/backend/requirements.txt"
$VENV_DIR/bin/python -m playwright install --with-deps chromium

$VENV_DIR/bin/python -m backend.main init-db

cp "$APP_DIR/deploy/daxiao.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable daxiao
systemctl restart daxiao

echo ""
echo "=== 部署完成 ==="
echo "Web 面板: http://$(hostname -I | awk '{print $1}'):8088"
echo "查看状态: systemctl status daxiao"
echo "查看日志: journalctl -u daxiao -f"
