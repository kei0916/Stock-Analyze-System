# Stock Analyze System 使い方ガイド

## プロジェクト概要

**Stock Analyze System** は、米国・日本の株式を対象とした財務分析・LLM分析を行うローカルWebアプリケーションです。

- **対象市場**: US（米国）、JP（日本）
- **主要技術**: Python (FastAPI + uvicorn)、SQLAlchemy (aiosqlite)、RAG (PageIndex + litellm)、Jinja2テンプレート
- **実行形式**: CLIコマンド (`stock-analyze`) とWebサーバー（ブラウザUI）

---

## 主要機能

| 機能分野 | 内容 |
|---|---|
| **企業管理** | 企業の登録・検索・詳細表示（ticker、CIK、EDINETコード対応） |
| **財務データ** | 財務データの表示（Revenue、EPS、EBITDA等）と指標計算（ROE、営業利益率、成長率等） |
| **バリュエーション** | PER/PBR/EV-EBITDA/PSRの履歴表示、複数企業比較、PERレンジ分析、グループ偏差分析（z-score） |
| **ファイリング** | SEC EDGAR / EDINET からの有価証券報告書メタデータ取得・コンテンツダウンロード |
| **RAG分析** | 有価証券報告書をベースとしたLLM定型分析（4タイプ）、自由質問、インデックス構築・管理 |
| **スクリーニング** | SECからのuniverse取得、Yahoo Finance/Google Sheets連携による指標 enrichment、条件フィルタ実行 |
| **ウォッチリスト** | ウォッチリストの作成・銘柄追加削除 |
| **分析ターゲット** | 分析対象銘柄の管理 |
| **ジョブ管理** | 単一企業のデータ同期、日次更新バッチ、ターゲット株価・バリュエーション更新 |
| **株価管理** | Google Sheets連携、stooq.comからのヒストリカル株価ダウンロード |
| **Web UI** | ダッシュボード、銘柄詳細、分析ジョブキュー、スクリーニング結果のブラウザ表示 |

---

## 実行コマンド一覧

### エントリポイント

```bash
uv run stock-analyze [COMMAND] [OPTIONS]
# または（Infisicalでsecrets注入）
scripts/infisical-run uv run stock-analyze [COMMAND] [OPTIONS]
```

### グローバルオプション

| オプション | 説明 |
|---|---|
| `--json` | JSON形式で出力 |
| `--config PATH` | 設定ファイルパス（デフォルト: `config/settings.yaml`） |
| `--db-path PATH` | データベースパスを上書き |

`--json` はグローバルオプションです。`stock-analyze --json rag health` と `stock-analyze rag --json health` はどちらも JSON 出力になります。

---

### Webサーバー・ワーカー

| コマンド | 説明 | 実行例 |
|---|---|---|
| `serve` | Webサーバー起動 | `uv run stock-analyze serve [--host HOST] [--port PORT]` |
| `worker` | バックグラウンド分析ワーカー起動 | `uv run stock-analyze worker [--poll-interval SEC]` |

> **注意**: 定型分析（RAG analyze）や自由質問（RAG ask）を使う場合、**Webサーバー・ワーカー・LLMバックエンド（llama-server）の3つを起動**する必要があります。ワーカーが停止中にジョブを作成すると、ジョブは `pending` のまま実行されません。

**起動例**:
```bash
# ターミナル1: Webサーバー
scripts/infisical-run uv run stock-analyze serve

# ターミナル2: 分析ワーカー
scripts/infisical-run uv run stock-analyze worker

# ターミナル3: LLMバックエンド (llama-server)
# モデル名は config/settings.yaml の llm.model (openai/Qwen3.6-27B-Q4_K_M.gguf) と一致させること
~/llama.cpp/build/bin/llama-server \
  --model ~/models/Qwen3.6-27B-Q4_K_M.gguf \
  --host 127.0.0.1 --port 8080 \
  --jinja \
  --ctx-size 131072 \
  --n-gpu-layers 99 \
  --parallel 1 \
  --reasoning off \
  > data/logs/llama-server.log 2>&1
```

> **llama-server 起動フラグの注意** (ADR-004 検証済み構成):
> - `--jinja` は**必須**。これがないと `enable_thinking=false` が chat template に効かず、Qwen3 系が思考トークンを暴走出力する。
> - `--ctx-size 131072 --parallel 1` を下げないこと。`--parallel N` は ctx-size を slot 数で分割するため、これより小さい ctx や多い parallel slot にすると実 10-K セクション（`risk_factors` で ~58K tokens）が context overflow する。
> - 詳細は `docs/analysis-jobs-runbook.md` §1 を参照。

---

### 企業管理 (`company`)

| サブコマンド | 説明 | 実行例 |
|---|---|---|
| `register` | 企業を登録 | `stock-analyze company register "Apple" --market US --ticker AAPL --cik 0000320193` |
| `search` | 企業を検索 | `stock-analyze company search "Apple" [--limit 20]` |
| `show` | 企業詳細を表示 | `stock-analyze company show US_AAPL` |

---

### 財務データ (`financial`)

| サブコマンド | 説明 | 実行例 |
|---|---|---|
| `show` | 財務データ一覧 | `stock-analyze financial show US_AAPL [--period annual|quarterly] [--years 5]` |
| `metrics` | 財務指標表示 | `stock-analyze financial metrics US_AAPL [--period annual] [--years 5]` |

---

### バリュエーション (`valuation`)

| サブコマンド | 説明 | 実行例 |
|---|---|---|
| `show` | バリュエーション履歴 | `stock-analyze valuation show US_AAPL [--years 5]` |
| `compare` | 複数企業比較 | `stock-analyze valuation compare US_AAPL US_MSFT US_GOOG` |
| `range` | PERレンジ（高値/中央値/安値） | `stock-analyze valuation range US_AAPL` |
| `deviation` | グループ偏差分析（z-score） | `stock-analyze valuation deviation US_AAPL US_MSFT` |

---

### ファイリング (`filings`)

| サブコマンド | 説明 | 実行例 |
|---|---|---|
| `list` | ファイリング一覧 | `stock-analyze filings list US_AAPL` |
| `download` | ファイリングをダウンロード | `stock-analyze filings download US_AAPL` |

---

### RAG分析 (`rag`)

| サブコマンド | 説明 | 実行例 |
|---|---|---|
| `health` | LLMヘルスチェック | `stock-analyze rag health` |
| `index` | インデックス構築 | `stock-analyze rag index US_AAPL` |
| `index --all` | 全企業のインデックス一括構築 | `stock-analyze rag index --all` |
| `status` | インデックス状態確認 | `stock-analyze rag status US_AAPL` |
| `analyze` | 定型分析実行 | `stock-analyze rag analyze US_AAPL [--type TYPE] [--quality]` |
| `ask` | 自由質問 | `stock-analyze rag ask US_AAPL "質問文" [--quality]` |
| `show` | 分析結果表示 | `stock-analyze rag show US_AAPL` |

---

### スクリーニング (`screening`)

| サブコマンド | 説明 | 実行例 |
|---|---|---|
| `universe refresh` | SECからuniverseを取り込み | `stock-analyze screening universe refresh` |
| `refresh` | screening cache更新（Yahoo Finance連携） | `stock-analyze screening refresh [--source yahoo|sec-google]` |
| `run` | スクリーニング実行 | `stock-analyze screening run --gte market_cap=1000000000 --sort roe --limit 50` |
| `add-targets` | ターゲットに追加 | `stock-analyze screening add-targets US_AAPL US_MSFT` |
| `fields` | フィルタ可能フィールド一覧 | `stock-analyze screening fields` |

**フィルタオプション** (`run` 用):
- `--gte FIELD=V`, `--lte FIELD=V`, `--between FIELD=LO,HI`
- `--eq FIELD=V`, `--in FIELD=V1,V2,...`
- `--sort FIELD`, `--asc` / `--desc`

---

### ウォッチリスト (`watchlist`)

| サブコマンド | 説明 | 実行例 |
|---|---|---|
| `create` | ウォッチリスト作成 | `stock-analyze watchlist create "My List" [--description "desc"]` |
| `list` | ウォッチリスト一覧 | `stock-analyze watchlist list` |
| `show` | ウォッチリスト詳細 | `stock-analyze watchlist show 1` |
| `add` | 銘柄を追加 | `stock-analyze watchlist add 1 US_AAPL` |
| `remove` | 銘柄を削除 | `stock-analyze watchlist remove 1 US_AAPL` |

---

### 分析ターゲット (`target`)

| サブコマンド | 説明 | 実行例 |
|---|---|---|
| `list` | ターゲット一覧 | `stock-analyze target list` |
| `add` | ターゲット追加 | `stock-analyze target add US_AAPL` |
| `remove` | ターゲット削除 | `stock-analyze target remove US_AAPL` |

---

### ジョブ管理 (`jobs`)

| サブコマンド | 説明 | 実行例 |
|---|---|---|
| `sync` | 単一企業のデータ同期 | `stock-analyze jobs sync US_AAPL` |
| `daily` | 日次更新バッチ | `stock-analyze jobs daily [--market us|jp] [--filing-date YYYY-MM-DD]` |
| `valuations` | ターゲットの株価・バリュエーション更新 | `stock-analyze jobs valuations [--market all|us|jp] [--quote-provider yahoo|google_sheets]` |

---

### 株価管理 (`quotes`)

| サブコマンド | 説明 | 実行例 |
|---|---|---|
| `sheets refresh` | Google Sheetsから株価を更新 | `stock-analyze quotes sheets refresh [--market us]` |
| `sheets status` | 株価キャッシュのステータス集計 | `stock-analyze quotes sheets status` |

---

### Stooq (`stooq`)

| サブコマンド | 説明 | 実行例 |
|---|---|---|
| `download` | stooq.comからヒストリカル株価をダウンロード | `stock-analyze stooq download [--years 10] [--apikey KEY] [--skip-existing] [--dry-run]` |

---

## 便利なスクリプト

| スクリプト | 用途 |
|---|---|
| `scripts/infisical-run` | Infisical secrets を注入してコマンド実行 |
| `scripts/cron-daily-update.sh` | cron用 日次更新バッチ |
| `scripts/cron-valuation-update.sh` | cron用 バリュエーション更新 |
| `scripts/cron-screening-enrich.sh` | cron用 スクリーニング enrichment |
| `scripts/rebuild_index.py` | RAGインデックス再構築 |
| `scripts/rag_inference_test.py` | RAG推論テスト |

---

## テスト・開発コマンド

```bash
# テスト実行
uv run pytest -q

# カバレッジ計測
uv run pytest --cov=src/stock_analyze_system --cov-report=term-missing

# リント
uv run ruff check .
uv run ruff format .
```
