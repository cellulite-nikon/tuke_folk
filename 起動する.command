#!/bin/bash
# ----------------------------------------------------
# 🍻 飲み会ツケ管理アプリ 起動スクリプト
# Finderでダブルクリックするだけで起動＆ブラウザが開きます
# ----------------------------------------------------

cd "$(dirname "$0")"

clear
echo "======================================================"
echo " 🍻 飲み会ツケ管理アプリ (Tuke Folk) を起動しています..."
echo "======================================================"
echo ""

# Python3の検出
if [ -x "/opt/homebrew/bin/python3.14" ]; then
    PYTHON_CMD="/opt/homebrew/bin/python3.14"
elif [ -x "/opt/homebrew/bin/python3" ]; then
    PYTHON_CMD="/opt/homebrew/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
else
    echo "❌ エラー: Python3が見つかりませんでした。"
    echo "MacにPythonがインストールされているか確認してください。"
    read -p "Enterキーを押して終了してください..."
    exit 1
fi

PORT=8765

# 既存のプロセスがあれば自動終了して再起動
OLD_PID=$(lsof -ti :$PORT 2>/dev/null)
if [ -n "$OLD_PID" ]; then
    echo "⚠️ 既に起動していたサーバーを再起動します..."
    kill -9 $OLD_PID 2>/dev/null
    sleep 1
fi

# 1.5秒後にブラウザを自動で開く
(sleep 1.5 && open "http://localhost:$PORT" 2>/dev/null) &

# サーバー本体を起動
$PYTHON_CMD server.py $PORT
