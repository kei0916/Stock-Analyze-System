# Yahoo Finance v7 バッチAPI設計（enrich_with_yahoo高速化）

> **Implementation status (2026-05-09):**
> Step 1 (Yahoo v7 batch fetch + bulk upsert with key-set grouping) は
> 実装済 (ADR-003 参照)。Step 2 (financial_data 一括取得) と Step 3
> (一括メトリクス計算) は本設計書で引き続き計画中で、別計画として後続着手予定。
>
> v7 batch API が返さないフィールド (sector / industry / beta /
> returnOnEquity / operatingMargins / profitMargins / revenueGrowth /
> earningsGrowth / pegRatio / freeCashflow / debtToEquity) は
> `bulk_upsert_cache` の key-set grouping により既存値が温存される。
> これらを補完する経路は `ScreeningMetricsService.refresh_from_sec_google()`
> および個別 `Ticker.info` (`get_screening_info()`) の双方とも維持。
>
> バッチ DB 失敗時は個別 `upsert_cache` フォールバックに切り替えて R7
> パターン (1件失敗で全体停止しない) を維持する。

## 1. 目的

`ScreeningUniverseService.enrich_with_yahoo()` の処理時間を、個別Ticker.info方式（10,376社で約8分）から、Yahoo Finance v7バッチAPI方式（約8秒）に短縮する。

## 2. アーキテクチャ概要

```
┌─────────────────────────────────────────────────────────────────┐
│  ScreeningUniverseService.enrich_with_yahoo()                   │
│                                                                 │
│  Step 1: Yahoo Finance v7 Batch API (新規実装)                  │
│    ├─ 11バッチ × 1000銘柄/回 = 10,376社一括取得                  │
│    ├─ 取得項目: 株価・PER・時価総額・PBR・配当利回り等              │
│    └─ screening_cache 一括upsert                                 │
│                                                                 │
│  Step 2: financial_data 一括取得 (既存拡張)                      │
│    ├─ get_latest_many() で全社最新財務データを一括取得            │
│    └─ 営業利益率・ROE等を計算                                     │
│                                                                 │
│  Step 3: screening_cache 一括更新 (計算値反映)                   │
│    └─ 営業利益率・ROE等の計算結果を一括UPDATE                     │
└─────────────────────────────────────────────────────────────────┘
```

## 3. データ取得戦略

| 情報源 | 取得方法 | 取得項目 | 推定時間 |
|--------|---------|---------|---------|
| **Yahoo v7 API** | バッチリクエスト(1000銘柄/回) | 株価・PER・時価総額・PBR・配当利回り・forwardPER・exchange | ~8秒 |
| **financial_data** | DB一括取得 `get_latest_many()` | 売上高・営業利益・純利益・自己資本・EPS等 | ~0.5秒 |
| **計算** | Python演算 | 営業利益率・ROE・PSR・EV/EBITDA・DEレシオ等 | ~0.1秒 |

## 4. 既存コードへの変更範囲

### 新規
- `YahooFinanceClient.get_screening_info_batch(tickers, batch_size=1000)` — v7バッチAPIラッパー
- `FinancialRepository.get_latest_many(company_ids, period_type)` — 一括最新財務取得
- `ScreeningUniverseService._enrich_batch()` — バッチ方式のメイン処理
- `ScreeningMetricsService.compute_metrics_bulk()` — 一括メトリクス計算

### 修正
- `ScreeningUniverseService.enrich_with_yahoo()` — 個別取得→バッチ取得に置き換え

### 維持（後方互換）
- `YahooFinanceClient.get_screening_info()` — 個別取得API
- `ScreeningMetricsService.refresh_from_sec_google()` — 既存フロー

## 5. パフォーマンス目標

| 処理 | 現状 | 新設計 | 改善率 |
|------|------|--------|--------|
| Yahoo基本情報取得 | ~7.8分 | ~8秒 | **60x** |
| financial_data取得 | N/A(別フロー) | ~0.5秒 | - |
| メトリクス計算 | N/A | ~0.1秒 | - |
| **合計** | **~8-9分** | **~13-15秒** | **~36-40x** |

## 6. 実装計画概要

1. **YahooFinanceClient** に `get_screening_info_batch()` を追加
2. **FinancialRepository** に `get_latest_many()` を追加
3. **ScreeningUniverseService** の `enrich_with_yahoo()` をバッチ方式にリファクタリング
4. 一括メトリクス計算・一括upsertを実装
5. 統合テスト（10社バッチ→全社バッチ）

## 7. 技術的考慮事項

### Yahoo Finance v7 API仕様
- エンドポイント: `https://query1.finance.yahoo.com/v7/finance/quote`
- パラメータ: `symbols={comma_separated_tickers}&formatted=false`
- 最大バッチサイズ: 1000銘柄（実測確認済み）
- 取得可能フィールド: `regularMarketPrice`, `marketCap`, `trailingPE`, `forwardPE`, `priceToBook`, `dividendYield`, `exchange`

### 取得不可能なフィールド（v7 API制限）
- `sector`, `industry`, `beta`, `returnOnEquity`, `operatingMargins`, `profitMargins`
- これらはfinancial_dataから計算するか、個別APIで取得する

### エラーハンドリング
- バッチ内の一部銘柄が失敗しても、成功銘柄はそのまま処理を続行
- 失敗した銘柄は個別にリトライするオプションを残す
- Rate limitはyfinanceの内部管理に委ねる（curl_cffi使用）
