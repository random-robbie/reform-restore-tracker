#!/bin/bash
# Daily sync: fetch new votes → run LLM analysis → commit DB → push → Render redeploys

set -euo pipefail

REPO="$HOME/tools/reform"
LOG="$REPO/sync.log"
PYTHON="$(which python3)"

echo "===== $(date '+%Y-%m-%d %H:%M:%S') =====" | tee -a "$LOG"

cd "$REPO"

# 1. Fetch new votes from Parliament API (safe to re-run; uses ON CONFLICT upserts)
echo "[1/3] Fetching votes from Parliament API..." | tee -a "$LOG"
$PYTHON fetch.py --no-llm 2>&1 | tee -a "$LOG"

# 2. Run LLM analysis on any unanalysed divisions
echo "[2/3] Running LLM analysis..." | tee -a "$LOG"
$PYTHON fetch.py --analyse 2>&1 | tee -a "$LOG"

# 3. Sync bill data from Parliament Bills API
echo "[2b] Syncing bill links..." | tee -a "$LOG"
$PYTHON bills.py 2>&1 | tee -a "$LOG"

# 4. Commit and push if anything changed
echo "[3/3] Committing to git..." | tee -a "$LOG"
git add reform.db
if git diff --cached --quiet; then
    echo "No changes to commit — DB unchanged" | tee -a "$LOG"
else
    DATE=$(date '+%Y-%m-%d')
    ANALYSED=$($PYTHON -c "from db import get_db; conn=list(get_db().__enter__() for _ in [1])[0]; print(conn.execute('SELECT COUNT(*) FROM divisions WHERE analyzed=1').fetchone()[0])" 2>/dev/null || echo "?")
    git commit -m "sync: ${DATE} — ${ANALYSED} divisions analysed"
    git push origin main
    echo "Pushed — Render will auto-deploy" | tee -a "$LOG"
fi

echo "Done." | tee -a "$LOG"
