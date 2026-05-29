# Maintainability Refactoring Design

**Date**: 2026-03-29
**Scope**: プロジェクト全体の保守性向上（インターフェース変更許容）
**Approach**: ボトムアップ（モデル層 → サービス層 → CLI層）

---

## 背景

プロジェクトは堅実なレイヤードアーキテクチャを持つが、急速な機能追加（特にRAG/LLM系）により以下の技術的負債が蓄積している:

- マジック文字列の散在（`"10-K"`, `"annual"` 等が9ファイル以上）
- レイヤー境界の侵犯（CLIがサービスのprivate関数を直接import）
- 責務過多のファイル（4ファイルが200行超）
- コード重複（filing-type処理パターンが4箇所で反復）
- マジックナンバーの未文書化

---

## セクション1: 定数・Enum定義の導入

### 問題
`"10-K"`, `"10-Q"`, `"20-F"`, `"6-K"` 等のファイリングタイプや `"annual"`, `"quarterly"` 等の期間タイプが生の文字列として散在。タイポによるサイレント不具合のリスクがある。

### 変更

**新規ファイル**: `models/enums.py`

```python
# Python 3.10互換
try:
    from enum import StrEnum
except ImportError:  # Python 3.10
    from enum import Enum
    class StrEnum(str, Enum):
        pass

class FilingType(StrEnum):
    TEN_K = "10-K"
    TEN_Q = "10-Q"
    TWENTY_F = "20-F"
    SIX_K = "6-K"

class PeriodType(StrEnum):
    ANNUAL = "annual"
    QUARTERLY = "quarterly"

class AccountingStandard(StrEnum):
    """Companyモデルに格納される会計基準値。

    注意: XBRLタクソノミキー（"us-gaap", "ifrs-full"）とは異なる。
    タクソノミキーは ingestion/xbrl/taxonomy.py 内でローカル定数として管理し、
    このenumへの変換は financial_sync 層で行う。
    """
    US_GAAP = "US-GAAP"
    IFRS = "IFRS"
    JP_GAAP = "JP-GAAP"
```

**影響ファイル** (文字列リテラルをenumメンバーに置換):
- `ingestion/sec_edgar.py`
- `ingestion/sec_xbrl_parser.py` (→ 分割後の各ファイル)
- `ingestion/fmp.py`
- `services/filing_sync.py`
- `services/financial_sync.py`
- `services/financial.py`
- `services/job.py`
- `cli/rag.py`
- `cli/financial.py`

**argparse連携**: `choices=list(FilingType)` で入力バリデーション自動化。

---

## セクション2: レイヤー違反の修正

### 問題
1. `PageIndexService._count_nodes` をCLI層が直接import
2. `_save_verification_report()` がCLI層にあるがサービス層の責務
3. CLI handler内のdeferred importが散在・重複

### 変更

#### 2-1. PageIndexService に公開API追加

```python
class PageIndexService:
    @staticmethod
    def count_nodes(tree: dict) -> int:
        """ツリーのノード数を返す"""
        return _count_nodes(tree)
```

CLI層は `_count_nodes` の直接importを廃止し、サービス経由で呼び出す。

#### 2-2. 検証レポート生成をサービス層に移動

**新規ファイル**: `services/verification_report.py`

単一関数として実装（クラス不要、拡張予定なし）:

```python
def save_verification_report(
    company_id: str, filing_id: int, tree: dict,
    verification_log: list, node_count: int,
    output_dir: Path = Path("data/logs/verification"),
) -> Path:
    """検証レポートを保存しパスを返す"""
    ...
```

`cli/rag.py` の `_save_verification_report()` を削除し、このサービス関数の呼び出しに置換。

#### 2-3. deferred import整理

各ハンドラ関数の先頭に1回だけimportを配置。ループ内・ブランチ内の重複importを排除。

---

## セクション3: 責務過多ファイルの分割

### 3-1. `job.py` (223行)

バリュエーション計算ロジックを分離:
- **移動先**: 既存の `services/valuation.py` の `ValuationService` に統合（新ファイル不要）
- **`JobService`**: オーケストレーションに専念、`ValuationService` を呼ぶだけに

### 3-2. `sec_xbrl_parser.py` (288行)

3つの責務に分割:

```
ingestion/sec_xbrl_parser.py
  ↓
ingestion/xbrl/
  ├── __init__.py          (公開API re-export、既存importパス互換維持)
  ├── parser.py            (エントリポイント: parse_xbrl())
  ├── taxonomy.py          (タクソノミマッピング解決)
  └── period_filter.py     (期間フィルタリング + 日付マージ)
```

`__init__.py` の re-export により、既存の `from stock_analyze_system.ingestion.sec_xbrl_parser import ...` は互換維持。

### 3-3. `cli/helpers.py` (128行)

DIコンテナとバリデーションを分離:

```
cli/helpers.py
  ↓
cli/
  ├── container.py         (ServiceContainer定義 + setup_services())
  └── helpers.py           (require_company, require_latest_filing等)
```

### 3-4. `cli/rag.py` (263行)

セクション2で `_save_verification_report` 移動後、セクション4の共通化により自然縮小。

---

## セクション4: コード重複の排除

### 4-1. `--filing-type` 引数の共通化

**`cli/helpers.py` に追加**:

```python
def add_filing_type_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--filing-type", default=FilingType.TEN_K,
        type=FilingType, choices=list(FilingType),
        help="ファイリングタイプ (デフォルト: 10-K)",
    )
```

`rag.py` の4サブパーサー（index, analyze, ask, show）すべてに `add_filing_type_argument()` で argparse 登録を追加し、各ハンドラで `args.filing_type` を統一的に参照する。現状 `index` のみ登録済み、他3つは新規追加。

### 4-2. company + filing 取得パターンの統一

4ハンドラで繰り返されるパターンを1ヘルパーに:

```python
async def require_company_and_filing(
    services: ServiceContainer, company_id: str, filing_type: FilingType
) -> tuple[Company, Filing]:
    company = await require_company(services.company_service, company_id)
    filing = await require_latest_filing(services.filing_service, company.id, filing_type)
    return company, filing
```

### 4-3. `job.py` sync処理パターン統一

`daily_update` 内のfinancial sync / filing syncの類似エラーハンドリングを `_sync_with_error_handling()` に抽出。

---

## セクション5: 設定・定数管理の改善

### 5-1. マジックナンバーの定数化

```python
# ingestion/xbrl/period_filter.py
QUARTERLY_MAX_DAYS: Final[int] = 120
"""四半期レポートの最大期間日数"""

ANNUAL_MIN_DAYS: Final[int] = 300
"""年次レポートの最小期間日数"""

# services/financial_sync.py
DATE_MATCH_TOLERANCE_DAYS: Final[int] = 15
"""期末日マッチングの許容誤差（日数）"""
```

- `_` プレフィックスを外しモジュール定数として公開（いずれもモジュール内ローカル参照のみのためリネーム安全）
- `Final` アノテーションで不変性を明示

### 5-2. `PageIndexConfig.enabled` の起動時チェック

`cli/container.py` の `setup_services()` 内で:
- `pageindex.enabled is False` → `rag_service = None`
- 既存の `if services.rag_service is None` チェックにより無効時は適切にエラー表示

### 5-3. デフォルト値の一元管理

設定デフォルト値が `config.py` と各サービスで二重定義されていないか確認し、`config.py` を唯一の真実の源に統一。

---

## 実行順序

```
セクション1 (enum) → セクション2 (レイヤー修正) → セクション3 (分割) → セクション4 (重複排除) → セクション5 (設定)
```

各セクション完了後にテストを実行し、グリーンを確認してからコミット。

## 影響まとめ

| 区分 | 新規ファイル | 変更ソースファイル | 変更テストファイル |
|------|-------------|-------------------|-------------------|
| セクション1 | `models/enums.py` | 9ファイル | `test_rag_cli.py` (args.filing_type の型変更) |
| セクション2 | `services/verification_report.py` | `pageindex_service.py`, `cli/rag.py` | `test_rag_cli.py` |
| セクション3 | `ingestion/xbrl/` (4ファイル), `cli/container.py` | `job.py`, `cli/helpers.py` | `test_helpers.py` (import先変更), `test_sec_xbrl_parser.py` (import先確認), `test_job_service.py` (valuation関数の移動先変更) |
| セクション4 | — | `cli/helpers.py`, `cli/rag.py`, `job.py` | `test_rag_cli.py`, `test_helpers.py` |
| セクション5 | — | 3-4ファイル | — |
