#!/usr/bin/env sh
set -eu

if [ -x "../.venv/bin/python" ]; then
  PYTHON_BIN="../.venv/bin/python"
elif [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

exec "$PYTHON_BIN" backend/avatar_ws_server.py "$@"
