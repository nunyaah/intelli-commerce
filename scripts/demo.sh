#!/usr/bin/env bash
# "Break it" demo: freeze a healthy baseline, regress the agent, watch the gate
# catch it and go red. Fully deterministic + free (mock mode), ~30s.
set -euo pipefail
cd "$(dirname "$0")/.."

export RELIABILITY_MOCK=1
export RELIABILITY_DB=".reliability/demo.db"

echo "=== IntelliCommerce Agent Reliability — break-it demo ==="
python -m reliability.cli demo
