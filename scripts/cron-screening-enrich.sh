#!/usr/bin/env bash
# screening_cache の Yahoo 一括更新 cron entrypoint。
# 米国市場 close (16:00 ET) の直後に走らせ、当日終値を screening 用 cache に
# 反映させる。Yahoo v7 batch API を使うため 10k ticker でも ~8 秒で完了する。
#
# 推奨スケジュール:
#   30 16 * * 1-5 America/New_York   (close + 30 分, 平日のみ)
#
# 上書き可能 env:
#   SAS_LOG_DIR    既定: $HOME/.local/share/stock-analyze/logs
#   SAS_LOCK_FILE  既定: /tmp/stock-analyze-screening-enrich.lock

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${SAS_LOG_DIR:-${HOME}/.local/share/stock-analyze/logs}"
LOCK_FILE="${SAS_LOCK_FILE:-/tmp/stock-analyze-screening-enrich.lock}"

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/screening-enrich-$(date +%Y-%m-%d).log"

# cron は PATH を最小限に剥がすため明示する (uv は user-local installation)
export PATH="${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "$(date -Iseconds) another screening-enrich is already running; skipping" \
    >> "${LOG_FILE}"
  exit 0
fi

exec >> "${LOG_FILE}" 2>&1

echo "=== $(date -Iseconds) starting screening-enrich (yahoo batch) ==="
status=0
"${REPO_ROOT}/scripts/infisical-run" \
  uv run stock-analyze screening refresh --source yahoo || status=$?
echo "=== $(date -Iseconds) finished status=${status} ==="

exit "${status}"
