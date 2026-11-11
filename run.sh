#!/bin/bash
cd "$(dirname "$0")"

# HomebrewのPythonまたはシステムPythonを使用
if [ -x "/opt/homebrew/bin/python3.14" ]; then
    PYTHON_CMD="/opt/homebrew/bin/python3.14"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
else
    echo "Python3が見つかりません。"
    exit 1
fi

PORT=8765

# 既存プロセスがあれば再起動
OLD_PID=$(lsof -ti :$PORT 2>/dev/null)
if [ -n "$OLD_PID" ]; then
    kill -9 $OLD_PID 2>/dev/null
    sleep 0.5
fi

$PYTHON_CMD server.py $PORT
