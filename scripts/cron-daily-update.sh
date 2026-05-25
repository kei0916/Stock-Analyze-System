#!/usr/bin/env bash
# 米国市場 close 後の日次更新 cron entrypoint。
# 推奨スケジュール: 07:00 JST (EDT 18:00 / EST 17:00 後)。
# 同時実行を flock で抑止し、 stdout/stderr をログファイルへ集約する。
#
# 上書き可能 env:
#   SAS_LOG_DIR    既定: $HOME/.local/share/stock-analyze/logs
#   SAS_LOCK_FILE  既定: /tmp/stock-analyze-daily-update.lock
#   SAS_MARKET     既定: us  (us/jp)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${SAS_LOG_DIR:-${HOME}/.local/share/stock-analyze/logs}"
LOCK_FILE="${SAS_LOCK_FILE:-/tmp/stock-analyze-daily-update.lock}"
MARKET="${SAS_MARKET:-us}"

mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/daily-update-$(date +%Y-%m-%d).log"

# cron は PATH を最小限に剥がすため明示する (uv は user-local installation)
export PATH="${HOME}/.local/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

# fd 経由の flock — 既に別プロセスが走っていれば exit 0 で静かに撤退
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "$(date -Iseconds) another daily-update is already running; skipping" \
    >> "${LOG_FILE}"
  exit 0
fi

# ロックを保持したまま 標準出力/エラーをログへ
exec >> "${LOG_FILE}" 2>&1

echo "=== $(date -Iseconds) starting daily-update market=${MARKET} ==="
status=0
"${REPO_ROOT}/scripts/infisical-run" \
  uv run stock-analyze jobs daily --market "${MARKET}" || status=$?
echo "=== $(date -Iseconds) finished status=${status} ==="

exit "${status}"
