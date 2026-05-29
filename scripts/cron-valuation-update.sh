#!/usr/bin/env bash
# 分析ターゲットの株価・バリュエーション更新 cron entrypoint。
# US/JP の市場 close 後に別々の cron entry として実行する。
#
# 上書き可能 env:
#   SAS_LOG_DIR    既定: $HOME/.local/share/stock-analyze/logs
#   SAS_LOCK_FILE  既定: /tmp/stock-analyze-valuation-update-${SAS_MARKET}.lock
#   SAS_MARKET     既定: us  (us/jp/all)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${SAS_LOG_DIR:-${HOME}/.local/share/stock-analyze/logs}"
MARKET="${SAS_MARKET:-us}"
LOCK_FILE="${SAS_LOCK_FILE:-/tmp/stock-analyze-valuation-update-${MARKET}.lock}"

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/valuation-update-${MARKET}-$(date +%Y-%m-%d).log"

# cron は PATH を最小限に剥がすため明示する (uv は user-local installation)
export PATH="${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "$(date -Iseconds) another valuation-update is already running; skipping" \
    >> "${LOG_FILE}"
  exit 0
fi

exec >> "${LOG_FILE}" 2>&1

echo "=== $(date -Iseconds) starting valuation-update market=${MARKET} ==="
status=0
"${REPO_ROOT}/scripts/infisical-run" \
  uv run stock-analyze jobs valuations --market "${MARKET}" || status=$?
echo "=== $(date -Iseconds) finished status=${status} ==="

exit "${status}"
