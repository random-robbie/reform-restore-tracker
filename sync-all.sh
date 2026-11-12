#!/bin/sh
# In-container daily sync: fetch votes -> LLM analysis -> bill links.
# Called by cron inside the 'reform' container; logs to /data/sync.log.
set -u

cd /app || exit 1
echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') ====="

echo "[1/3] Fetching votes from Parliament API..."
python3 fetch.py --no-llm

echo "[2/3] Running LLM analysis on unanalysed divisions..."
python3 fetch.py --analyse

echo "[3/3] Syncing bill links..."
timeout 1800 python3 bills.py || echo "bills.py failed or timed out (non-fatal)"

echo "Done."
