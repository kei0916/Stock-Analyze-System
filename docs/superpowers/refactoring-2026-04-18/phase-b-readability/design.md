# Phase B: 可読性・命名 — Design

**Status**: Draft (2026-04-24)

**前提**: Phase E (デッドコード削除) 完了直後。master.md の Phase 進捗表では Phase B は次順位。Phase D / C / E で判明した readability 負債を本 Phase で消費する。

---

## Goal

可読性・命名の負債を 3 クラスタで解消する。

1. **クラスタ A** — 履歴コメント (`Bug #N 修正` / `新発見N 修正`) を除去し、対象 6 ファイル内の全関数 docstring を Google スタイル (`Args:` / `Returns:` / `Raises:`) に統一
2. **クラスタ B** — クラスタ A 対象ファイル内の `Any` アノテーションを具体型 (`FinancialData` 等) に置換
3. **クラスタ C** — CLI `_handle_*` 関数の型注釈を統一 (現在 4 ファイルが未アノテーション)

**成功条件:**

1. `src/` 配下に `Bug #N 修正` / `新発見N 修正` / `Bug#N` 文字列が 0 件 (grep)
2. 対象 6 ファイル内の全 public method / module-level 関数に Google スタイル docstring
3. `compute_valuation_from_financials` の `fd` が `FinancialData` 型
4. 4 CLI ファイルの全 `_handle_*` 関数が `args: argparse.Namespace, services: ServiceContainer, -> None` に統一
5. 既存テスト (783+) 全 PASS、ruff clean、coverage 変動なし

---

## Non-Goals

- repo/service の巨大ファイル分割 (`pageindex_service.py` 514 行) — Phase A 範囲
- 更なる dead code 削除 — Phase E で完了済
- public API の signature 変更 (引数名 rename 含む) — master rule §4 により禁止
- 対象 6 ファイル外の docstring Google 化 (次回 follow-up で必要なら)
- `mypy` / `pyright` 導入 — Phase A 後の検討事項

---

## Master rule 遵守

master.md §ルール §4 により「public API は Phase D〜B で不変」。本 Phase で触れるのは:

- docstring (振る舞い不変)
- 内部変数名・コメント (非 public)
- 型アノテーション追加 (signature 型情報の精緻化のみ、引数名・並び・default は不変)

**禁止事項**:
- public API (`service/repository` の外部 method、`compute_valuation_from_financials` 等 module-level 関数) の引数名 rename
- default 値の変更
- 関数の返り値型の変更 (アノテーションを `Any` → 具体型に精緻化する場合も、既存の値構造と完全一致することを確認)

---

## Architecture

4 Task を Layer 別に分割 (Phase C/E と同じ構成)。Task 間は独立、推奨順は記載順。

```
┌────────────────┐  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│  Task 1        │  │  Task 2        │  │  Task 3        │  │  Task 4        │
│  services/ 層  │  │  ingestion/ +  │  │  CLI _handle_* │  │  docs update   │
│                │  │  cli/ 層       │  │  型注釈統一    │  │                │
│ company.py     │  │ sec_edgar.py   │  │ cli/company    │  │ master.md      │
│ job.py         │  │ cli/valuation  │  │ cli/financial  │  │ phase-b/       │
│ valuation.py   │  │ cli/jobs       │  │ cli/rag        │  │ report.md      │
│                │  │                │  │ cli/valuation* │  │                │
│ A + B          │  │ A のみ         │  │ C のみ         │  │ Codex 追跡用   │
│                │  │                │  │                │  │ change-log 含む│
└────────────────┘  └────────────────┘  └────────────────┘  └────────────────┘
```

**Task 間依存**:
- Task 2 と 3 はどちらも `cli/valuation.py` を触るが、**異なる行**に触れる
  (Task 2: module-top 近辺の `Bug #16修正` コメント + docstring、Task 3: `_handle_*` 関数の型注釈)
- Task 2 → Task 3 の順で実施すれば merge conflict なし
- Task 4 は他 3 Task 完了後 (commit hash を report.md に埋め込むため)

---

## Task 1: services/ 層

### 対象ファイル (3 件)
- `services/company.py` (80 行)
- `services/job.py` (164 行)
- `services/valuation.py` (172 行)

### 1-1. 履歴コメント除去 + docstring Google 化

**`services/company.py:60`** — Before:
```python
def build_company_id(...) -> str:
    """市場と識別子から企業IDを生成。Bug #7 修正: 未知市場で ValueError。"""
```
After:
```python
def build_company_id(
    ticker: str | None, security_code: str | None, market: str,
) -> str:
    """市場と識別子から企業IDを生成する。

    Args:
        ticker: US 市場の ticker symbol。
        security_code: JP 市場の証券コード。
        market: 市場コード (JP_PRIME / US_NASDAQ 等)。

    Returns:
        `JP_<code>` または `US_<ticker>` 形式の企業ID。

    Raises:
        ValueError: 市場が未知、または必須識別子が不足している場合。
    """
```

**`services/job.py:68`** (`sync_company`) / **`:141`** (`run_daily_update`) — 履歴 tail 削除 + Args/Returns 追加。

**`services/valuation.py:80`** (`compute_group_deviation`) / **`:106`** (`compute_valuation_from_financials`) — 同上。

### 1-2. Any → 具体型 (Task 1-B)

**`services/valuation.py:108`** の `fd: Any` を `FinancialData` に置換。既存の `FinancialData` は
`models/financial_data` 配下にあるため import 追加は TYPE_CHECKING ガードで行う
(ランタイム import にすると循環依存の可能性があるため、現状の pattern に準拠):

```python
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stock_analyze_system.models.financial_data import FinancialData


def compute_valuation_from_financials(
    stock_price: float | None,
    fd: "FinancialData",
    currency: str,
    val_date: date_type,
    market_cap: float | None = None,
) -> dict[str, Any]:
```

戻り値 `dict[str, Any]` は heterogenous のため残す (`TypedDict` 化は Phase A スコープ)。

### 1-3. その他同ファイル内の全関数

- `services/company.py`: `CompanyService` 全 method (`get_company`/`list_companies`/`search_companies`/`is_us_market`/`resolve_yf_ticker`) を Google 化
- `services/job.py`: `JobService.__init__` は self 代入のみのため docstring 不要。`sync_company` / `run_daily_update` を整備
- `services/valuation.py`: `ValuationService` 全 method + module-level `compute_valuation_from_financials` を整備

**除外規則**:
- `__init__` で引数を self._X に代入するだけの場合 → クラス docstring に集約、method docstring は不要
- 1 行 delegate (例: `return await self._repo.upsert(...)`) → 既存の 1 行 docstring 維持で可

### 1-4. テスト計画

- 既存 `tests/unit/services/test_company_service.py` / `test_job_service.py` / `test_valuation_service.py` は無変更で全 PASS (docstring / 型アノテーション変更は実行に影響しない)
- 新規テストなし (振る舞い不変)
- `scripts/infisical-run uv run pytest tests/unit/services/ -q` で green 確認
- `scripts/infisical-run uv run ruff check src/stock_analyze_system/services/` で clean 確認

### 1-5. Commit (Task 1)

```
refactor(services): apply Google-style docstrings + strict types (Phase B cluster 1)

- services/company.py: Bug #7 履歴除去、build_company_id に Args/Returns/Raises
- services/job.py: Bug #4 / 新発見3 履歴除去、sync_company / run_daily_update の docstring 整備
- services/valuation.py: 新発見1/2/5 履歴除去、compute_valuation_from_financials の fd: Any → FinancialData
- 同ファイル内の全 public method を Google スタイルへ統一
- 既存 unit tests 無変更で全 PASS、ruff clean
```

---

## Task 2: ingestion/ + cli/ 層

### 対象ファイル (3 件)
- `ingestion/sec_edgar.py` (`新発見4修正` at line 84)
- `cli/valuation.py` (`Bug #16修正` at line 28)
- `cli/jobs.py` (`Bug #3修正` at line 20)

### 2-1. 履歴コメント除去

- **`ingestion/sec_edgar.py:84`** — `# zip で安全にイテレート（新発見4修正）` を削除。コード自体が自明
- **`cli/valuation.py:28`** — `# Bug #16修正: no manual usage string. argparse auto-generates help including deviation.` を削除。argparse のデフォルト挙動は言語仕様
- **`cli/jobs.py:20`** — `# Bug #3修正: sync と daily を明確に分離。--type は削除。` を削除。現在の CLI 構造から自明

### 2-2. docstring Google 化 (同ファイル内全関数)

- **`ingestion/sec_edgar.py`**: `SecEdgarClient` の全 public method (`get_company_facts`, `list_filings`, `download_submission` 等) に Args/Returns/Raises
- **`cli/valuation.py`**: module-level setup + `_handle_*` 関数 (Task 3 で型注釈を追加するため、docstring はここで整備)
- **`cli/jobs.py`**: 既に型注釈あり (`async def _handle_sync(args: argparse.Namespace, ...)`)。docstring のみ Google 化

### 2-3. 適用除外

- `ingestion/sec_edgar.py` の `_install_pypdf_compat` 等の private helper は既存 1 行 docstring 維持 (呼び手 1 箇所・内容自明)
- 内部 lambda / 無名関数は対象外

### 2-4. テスト計画

- 既存 `tests/unit/ingestion/test_sec_edgar.py` / `tests/unit/cli/test_valuation_cli.py` / `test_jobs_cli.py` は無変更で全 PASS
- `scripts/infisical-run uv run pytest tests/unit/ingestion/ tests/unit/cli/ -q` で green 確認
- ruff clean 維持

### 2-5. Commit (Task 2)

```
refactor(ingestion,cli): apply Google-style docstrings (Phase B cluster 2)

- ingestion/sec_edgar.py: 新発見4 履歴コメント除去、SecEdgarClient 全 public method docstring 統一
- cli/valuation.py: Bug #16 履歴コメント除去、docstring Google 化 (型注釈は Task 3 で追加)
- cli/jobs.py: Bug #3 履歴コメント除去、docstring Google 化
- 既存 tests 無変更で全 PASS、ruff clean
```

---

## Task 3: CLI `_handle_*` 型注釈統一

### 対象ファイル (4 件、現時点で型注釈なし)

- `cli/company.py` — `_handle_register` / `_handle_search` / `_handle_show`
- `cli/financial.py` — `_handle_show` / `_handle_metrics`
- `cli/rag.py` — `_handle_health` / `_handle_index` / `_handle_analyze` / `_handle_ask` / `_handle_status` / `_handle_show`
- `cli/valuation.py` — `_handle_*` (Task 2 で docstring は既に整備済み)

### 3-1. 統一シグネチャ

既に型注釈済みの `cli/watchlist.py` / `cli/target.py` / `cli/jobs.py` と揃える:

```python
async def _handle_show(
    args: argparse.Namespace, services: ServiceContainer,
) -> None:
```

**`cli/rag.py` の特殊形**:

`_handle_*(rag, services, args)` の順 (`rag` を先頭で受け取る)。`rag` の型は `RagService` を確認して確定:

```python
async def _handle_health(
    rag: RagService, args: argparse.Namespace,
) -> None:
```

### 3-2. import 追加

各ファイル冒頭に `import argparse` / `from stock_analyze_system.cli.container import ServiceContainer` が未追加であれば追加。`TYPE_CHECKING` ガードは不要 (CLI 層は hot path ではないため実行時 import で問題なし)。

### 3-3. テスト計画

- 既存 `tests/unit/cli/test_company_cli.py` / `test_financial_cli.py` / `test_rag_cli.py` / `test_valuation_cli.py` は無変更で全 PASS (型注釈追加は実行時 noop)
- `scripts/infisical-run uv run pytest tests/unit/cli/ -q` で green 確認
- ruff clean 維持 (`ANN` rule は現在未設定のため警告増加なし)

### 3-4. 適用外

- `cli/app.py` / `cli/helpers.py` / `cli/container.py` / `cli/formatters.py` は `_handle_*` を持たない
- `cli/serve.py` / `cli/filings.py` / `cli/screen.py` / `cli/target.py` / `cli/watchlist.py` / `cli/jobs.py` は既に型注釈済み

### 3-5. Commit (Task 3)

```
refactor(cli): align _handle_* type annotations (Phase B cluster 3)

- cli/company.py / cli/financial.py / cli/rag.py / cli/valuation.py の
  _handle_* 関数に args: argparse.Namespace, services: ServiceContainer, -> None
  の型注釈を追加 (rag は rag: RagService 先頭)
- 既存テスト無変更で全 PASS、ruff clean
```

---

## Task 4: docs update + Codex 追跡用 change-log

### 4-1. master.md 更新

- **Phase 進捗表**: Phase B 行を `⚪ Pending` → `✅ Done` に更新し、design/plan/report リンクを追加
- **Backlog**: `**Phase B (可読性) 候補:**` を「2026-04-?? 完了」+「消費した項目」節に書き換え

### 4-2. phase-b-readability/report.md 新規作成

Phase E report.md と同形式 + **Codex 追跡用 change-log** を必須で含める。

**Codex 追跡要件** (本 Phase の追加要件):

実装後に Codex がプロジェクト全体精査を行うため、Codex が変更箇所を機械的に辿れるよう
report.md に以下を記録:

1. **Task 単位の commit hash 一覧** (Task 1〜3)
2. **変更ファイル + 行範囲の一覧** (例: `services/company.py:60-80` — `build_company_id` docstring 書き換え)
3. **触った関数・method の一覧** (ファイルパス・関数名・変更種別 [履歴除去 / docstring 化 / 型注釈追加] の 3 列)
4. **除去した履歴コメント 7 件の明細** (除去前文字列 + 除去後の状態)
5. **追加した型注釈の一覧** (関数パス・パラメータ名・追加された型)
6. **スコープ外の明示** (他 Phase で扱う項目:`pageindex_service.py` 分割 → Phase A など)

**report.md 構造**:

```markdown
# Phase B: 可読性・命名 — 実施記録

**Status**: ✅ Done (2026-04-??)

## Task 記録
### Task 1: services/ 層 — ✅ Done
- 変更: services/company.py, services/job.py, services/valuation.py
- commit: <TASK_1_SHA>
- 備考: ...

### Task 2: ingestion/ + cli/ 層 — ✅ Done
...

### Task 3: CLI _handle_* 型注釈統一 — ✅ Done
...

### Task 4: Docs update — ✅ Done
...

## 変更箇所 change-log (Codex 追跡用)

### 除去した履歴コメント (7 件)
| # | ファイル:行 | 除去前文字列 | 状態 |
|---|---|---|---|
| 1 | services/company.py:60 | `Bug #7 修正: 未知市場で ValueError。` | docstring tail 削除 + Google 化 |
| ... | ... | ... | ... |

### Google スタイル docstring に書き換えた関数
| ファイル | 関数 | 種別 |
|---|---|---|
| services/company.py | build_company_id | 履歴除去 + Args/Returns/Raises |
| ... | ... | ... |

### 追加した型注釈
| ファイル | 関数 | パラメータ | 追加型 |
|---|---|---|---|
| services/valuation.py | compute_valuation_from_financials | fd | FinancialData |
| cli/company.py | _handle_register | args | argparse.Namespace |
| ... | ... | ... | ... |

## サマリー
| 指標 | Before | After | 差分 |
|---|---|---|---|
| 全 unit tests 件数 | 783 | 783 | 0 |
| 履歴コメント残数 (src/ grep) | 7 | 0 | -7 |
| ...

## スコープ外 (次 Phase)
- `pageindex_service.py` 514 行分割 → Phase A
- 対象外ファイルの docstring Google 化 → 次回 follow-up
```

### 4-3. Commit (Task 4)

```
docs(phase-b): mark Phase B done in master + add report with change-log

- master.md: Phase B を ✅ Done に更新、design/plan/report リンク追加。
  Backlog の "Phase B 候補" を "消費した項目" 一覧へ書き換え。
- phase-b-readability/report.md 新規作成:
  - 3 commit (<TASK_1_SHA> / <TASK_2_SHA> / <TASK_3_SHA>) を Task 単位で記録
  - 除去した履歴コメント 7 件、書き換えた docstring N 件、追加した型注釈 M 件を
    Codex 追跡可能な table 形式で列挙
  - 全 unit tests 783 PASS / ruff clean を確認
```

---

## テスト & 受け入れ基準

- **全 unit tests PASS**: 現 783 件 → 変更なし。docstring / 型注釈追加のみのため新規テストは不要
- **integration tests**: 変更なし
- **coverage**: 低下なし (実行パス不変)
- **ruff clean**: 新規 error 0
- **`mypy` / `pyright`**: 未導入のため対象外 (Phase A 後の検討事項)
- **grep 確認**: `scripts/infisical-run uv run bash -c 'grep -rn "新発見\|Bug #[0-9]" src/'` で 0 件
- **作業順序**: Task 1 → Task 2 → Task 3 → Task 4
  (Task 2 と 3 で `cli/valuation.py` の異なる行を触るため順序固定)

---

## ファイル / 関数別チェックリスト (plan.md での Step 化用)

**Task 1 (services/)**:
- [ ] `services/company.py:60` — `build_company_id` 履歴除去 + Google docstring
- [ ] `services/company.py` — `CompanyService` 他全 method Google 化
- [ ] `services/job.py:68` — `sync_company` 履歴除去 + Google docstring
- [ ] `services/job.py:141` — `run_daily_update` 履歴除去 + Google docstring
- [ ] `services/valuation.py:80` — `compute_group_deviation` 履歴除去 + Google docstring
- [ ] `services/valuation.py:106` — `compute_valuation_from_financials` 履歴除去 + `fd: Any → FinancialData` + Google docstring
- [ ] `services/valuation.py` — `ValuationService` 他全 method Google 化

**Task 2 (ingestion/ + cli/)**:
- [ ] `ingestion/sec_edgar.py:84` — `新発見4修正` コメント除去
- [ ] `ingestion/sec_edgar.py` — `SecEdgarClient` 全 public method Google 化
- [ ] `cli/valuation.py:28` — `Bug #16修正` コメント除去 + docstring Google 化
- [ ] `cli/jobs.py:20` — `Bug #3修正` コメント除去 + docstring Google 化

**Task 3 (CLI 型注釈)**:
- [ ] `cli/company.py` — `_handle_register` / `_handle_search` / `_handle_show` に型注釈
- [ ] `cli/financial.py` — `_handle_show` / `_handle_metrics` に型注釈
- [ ] `cli/rag.py` — `_handle_*` 6 関数に型注釈 (rag 先頭形)
- [ ] `cli/valuation.py` — `_handle_*` に型注釈

**Task 4 (docs)**:
- [ ] master.md 進捗表 Phase B ✅ Done + Backlog 書き換え
- [ ] phase-b-readability/report.md 新規作成 (Codex 追跡 change-log 含む)

---

## 参照

- Phase E report: `../phase-e-deadcode/report.md`
- Phase C design: `../phase-c-dry/design.md`
- master tracker: `../master.md`
