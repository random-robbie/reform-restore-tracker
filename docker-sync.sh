#!/bin/bash
set -euo pipefail

LOG=~/docker/reform/sync.log

log() { echo "$1" | tee -a "$LOG"; }

log "===== $(date '+%Y-%m-%d %H:%M:%S') ====="

log "[1/3] Fetching votes from Parliament API..."
docker exec reform python3 /app/fetch.py --no-llm >> "$LOG" 2>&1

log "[2/3] Running LLM analysis..."
docker exec reform python3 /app/fetch.py --analyse >> "$LOG" 2>&1

log "[3/3] Syncing bill links..."
docker exec reform python3 /app/bills.py >> "$LOG" 2>&1

log "Done."
