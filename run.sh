#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
exec .venv/bin/python scripts/take_icp_gradio_app.py --host 0.0.0.0 --port 7866
