# Stock Analyze System

米国・日本の株式を対象とした、財務分析と SEC EDGAR / EDINET filing の LLM 定型分析を行うローカル Web アプリケーション。

> **個人プロジェクト** — ローカル単独ユーザでの個人利用を想定しています。Production 利用や金融助言・投資助言を意図したものではありません。詳細は [注意事項](#注意事項) を参照。

## 主要機能

| 分野 | 内容 |
|---|---|
| **企業管理** | ticker / CIK / EDINET コードでの企業登録・検索、企業詳細表示 |
| **財務データ** | Revenue / EPS / EBITDA 等の表示、ROE・営業利益率・成長率の指標計算 |
| **バリュエーション** | PER / PBR / EV-EBITDA / PSR 履歴、複数企業比較、PER レンジ、グループ z-score 偏差 |
| **ファイリング** | SEC EDGAR (10-K/10-Q/20-F/6-K) / EDINET (有価証券報告書) のメタデータ取得・コンテンツダウンロード |
| **RAG 分析** | 有価証券報告書をベースとした LLM 定型分析 4 種 (事業 / リスク / MD&A / 競合) + 自由質問 |
| **スクリーニング** | SEC からの universe 取り込み、Yahoo Finance / Google Sheets 連携、条件フィルタ実行 |
| **ウォッチリスト / ターゲット** | 銘柄リストとフォロー対象の管理 |
| **ジョブ管理** | 単一企業のデータ同期、日次バッチ更新、株価・バリュエーション更新 |
| **株価管理** | Google Sheets 連携、stooq.com からのヒストリカル株価ダウンロード |
| **Web UI** | ダッシュボード、銘柄詳細、分析ジョブキュー、スクリーニング結果のブラウザ表示 |

CLI コマンドの詳細リファレンスは [HOW_TO_USE.md](./HOW_TO_USE.md) を参照。

## 技術スタック

- Python ≥ 3.10
- **Web**: FastAPI + uvicorn / Jinja2
- **DB**: SQLAlchemy + aiosqlite (SQLite)
- **LLM**: LiteLLM + llama.cpp / vLLM (OpenAI 互換 API も可)
- **PDF**: pymupdf / WeasyPrint
- **データ取得**: edgartools (SEC EDGAR) / yfinance / FMP / EDINET API / Google Sheets API
- **シークレット管理**: Infisical
- **Living Docs**: Docusaurus (`docs-site/`)

## 必要環境

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) — パッケージ管理
- [Infisical CLI](https://infisical.com/docs/cli/overview) — シークレット管理
- LLM バックエンド (いずれか):
  - llama.cpp + GGUF モデル (Qwen3.5-27B 相当を推奨)
  - vLLM
  - OpenAI 互換エンドポイント

## セットアップ

```bash
# 依存関係インストール
uv sync

# 設定ファイル雛形をコピーして編集
cp config/settings.yaml.example config/settings.yaml

# Infisical 連携 (workspaceId を記入してログイン)
cp .infisical.json.example .infisical.json
infisical login
```

必要な secrets (例: `WEB_PASSWORD`, `WEB_SESSION_SECRET`, `EDINET_API_KEY`, `FMP_API_KEY`, `OPENAI_API_KEY`) を Infisical に登録してください。secret 名と用途の一覧は [HOW_TO_USE.md](./HOW_TO_USE.md) を参照。

## 起動

定型分析を使う場合、Web サーバーと分析ワーカーを **両方** 起動する必要があります:

```bash
# 端末1: Web サーバー
scripts/infisical-run uv run stock-analyze serve

# 端末2: 分析ワーカー
scripts/infisical-run uv run stock-analyze worker
```

ブラウザで http://localhost:8501 を開く。worker が停止していると分析ジョブは `pending` のまま処理されず、Web 上に警告バッジが表示されます。

### systemd 常駐例

```ini
[Unit]
Description=Stock Analyze analysis worker
After=network.target

[Service]
WorkingDirectory=<repo-root>
ExecStart=<repo-root>/scripts/infisical-run uv run stock-analyze worker
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## 設定

- `config/settings.yaml` (gitignore) — DB パス、LLM backend、Web port、rate limit 等
- Infisical secrets — API キー、認証情報 ([HOW_TO_USE.md](./HOW_TO_USE.md) 参照)

### PageIndex 連携 (任意)

`pageindex.enabled` はデフォルト `false`。RAG の自由質問・index 構築で PageIndex を使う場合のみ、互換 PageIndex を別途導入し `pageindex.enabled=true` を設定してください。定型分析 (4 種) は PageIndex 不要で動作します (ADR-004 参照)。

## 開発

```bash
# テスト
uv run pytest -q

# カバレッジ計測
uv run pytest --cov=src/stock_analyze_system --cov-report=term-missing

# Lint / Format
uv run ruff check .
uv run ruff format .
```

設計判断は `docs/adr/` に Architecture Decision Record として記録されています。

## プロジェクト構成

```
src/stock_analyze_system/
  cli/              CLI コマンド (stock-analyze ...)
  web/              FastAPI Web アプリ + テンプレート
  services/         ビジネスロジック (RAG / Analysis / Sync など)
  repositories/     永続化層 (SQLAlchemy)
  models/           ORM モデル
  ingestion/        外部データ取り込み (SEC / EDINET / FMP / Yahoo)
  shared/           共有ユーティリティ

config/             設定ファイル雛形 (settings.yaml は gitignored)
data/               ローカル DB・ファイル (gitignored)
docs/               ADR / 設計仕様 / runbook
docs-site/          Docusaurus Living Docs
scripts/            補助スクリプト (infisical-run など)
tests/              pytest テスト
```

## 注意事項

- **本アプリは投資助言・売買推奨を行うものではありません。** 出力は LLM の生成結果であり、誤り・古い情報・幻覚を含みうるため、投資判断は必ず一次情報 (SEC EDGAR / EDINET 等) で確認してください。
- ローカル単独ユーザを想定した実装で、multi-tenant・公開 hosting には対応していません。
- 個人プロジェクトのため、Issue / PR への対応は best-effort です。
- 外部 API (SEC EDGAR / EDINET / Yahoo Finance / FMP / stooq.com) の利用規約・rate limit を遵守してください。

## ライセンス

[MIT License](./LICENSE)

## 謝辞

本プロジェクトは以下の OSS / 公開データ源を利用しています:

- [edgartools](https://github.com/dgunning/edgartools) — SEC EDGAR client
- [yfinance](https://github.com/ranaroussi/yfinance) — Yahoo Finance data
- [LiteLLM](https://github.com/BerriAI/litellm) — LLM API 統合
- [llama.cpp](https://github.com/ggerganov/llama.cpp) — ローカル LLM 推論
- [PageIndex](https://github.com/VectifyAI/PageIndex) — PDF RAG (任意連携)
- [Infisical](https://infisical.com/) — シークレット管理
- SEC EDGAR / EDINET — 公開金融情報
