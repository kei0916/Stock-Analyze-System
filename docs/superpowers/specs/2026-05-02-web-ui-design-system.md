# Web UI Design System 反映設計

- 日付: 2026-05-02
- ブランチ: `codex-refactoring-followups-20260419`
- 関連: Anthropic Design 由来の `stock-analyzer-design-system` ハンドオフバンドル

## 背景

`claude.ai/design` で作成された **Stock Analyzer Design System** ハンドオフバンドル (`ui_kits/web/index.html` 等) を、既存の FastAPI + Jinja2 Web UI に全面適用する。既存 UI はライトテーマ + 横ナビ + Tailwind 風ユーティリティクラス (`app.css` 内シム) を採用しており、デザインシステム (ダーク標準 + サイドバー + トークン駆動) と全面的に競合する。重複・競合する部分は削除し、デザインのトークン/レイアウト/構造へ置き換える。

機能 (HTMX SSR, FastAPI ルート, RAG / 財務 / 指標 / バリュエーション API, Screening, Watchlists, Targets, Jobs, Login) は維持する。Login のフォーム仕様 (パスワードのみ) は既存維持し、外観のみデザインのログインカードに合わせる。

## 設計原則 (デザインシステムから引き継ぐ)

1. **ダーク標準** (`color-scheme: dark`, `--bg: #0B0D10`)。ライトモードは secondary だが今回は提供しない。
2. **2.5 色** — 2 系統のグレーランプ + シアンアクセント (`--accent: #22D3EE`)。`--up`/`--down` は数値内のみで使用。
3. **数値は JetBrains Mono + tabular-nums**。テーブルセル、KPI、株価、比率、日付、ID。
4. **ヘアラインボーダー優先**。1px `--border` で区切り。`--shadow-*` はモーダル/ポップオーバーのみ。
5. **8pt グリッド** (`--space-1〜8`)。パネル padding 16px, テーブル 10–12px / 16px, ボタン高 32–36px。
6. **アイコンはインライン SVG のみ**。Lucide CDN を読み込まない。
7. **絵文字禁止**。
8. **トークンを必ず参照**。raw hex を直書きしない。

## スコープ

- 視覚: 全画面 (Login除く構造 + Login外観) を新デザインへ移行。
- 構造: Stock Detail のタブを 5 → 4 へ縮約 (財務 / バリュエーション / 分析 / ファイリング)。指標は財務へ統合、RAG は分析へ統合。
- 機能追加: 財務タブにコンボチャート (バー + YoY 折れ線)、バリュエーションタブに 10 年推移エリアチャート (どちらもインライン SVG)。
- 機能維持: HTMX SSR, FastAPI ルート, 既存 API, タブ JS, スクリーニング, RAG Q&A 機能ロジック。
- 機能除外: ダッシュボードの「最近の同期」「LLM分析キュー」は実データ無しのため未実装 (filler 禁止原則)。チャート系のクライアント側ライブラリ (Chart.js) は導入しない (インライン SVG で対応)。

非対象:
- ログイン認証仕様の変更 (パスワードのみ維持)。
- 新規バックエンド機能 (sync 履歴 API, LLM ジョブキュー API 等)。
- モバイル/タブレット最適化 (デスクトップ first)。

## 成果物

### 静的アセット (新規)
- `src/stock_analyze_system/web/static/colors_and_type.css` — デザイン同梱を移植。トークン定義の唯一の出所。
- `src/stock_analyze_system/web/static/fonts/Inter-Variable.woff2`
- `src/stock_analyze_system/web/static/fonts/JetBrainsMono-Variable.woff2`
- `src/stock_analyze_system/web/static/assets/logo.svg`
- `src/stock_analyze_system/web/static/assets/mark.svg`
- `src/stock_analyze_system/web/static/assets/mark-inverse.svg`

### CSS
- `src/stock_analyze_system/web/static/app.css` — 全面書き換え。
  - 旧 Tailwind シム (`.bg-white`, `.rounded-lg`, `.shadow`, `.bg-blue-600`, `.text-gray-500`, `.bg-red-100` 等) を削除。
  - 新規セマンティッククラス: `.layout`, `.sidebar`, `.topbar`, `.panel`, `.panel__header`, `.panel__body`, `.btn`, `.btn--primary|secondary|ghost|danger`, `.badge`, `.badge--accent|up|down`, `.kpi-tile`, `.kpi-tile__label|value|delta`, `.tabs`, `.tab`, `.segmented`, `.input`, `.label`, `.num`, `.num-cell`, `.up`, `.down`, `.icon`, `.empty-state`。
  - `colors_and_type.css` を `@import` で先頭に取り込む (もしくは `<link>` 二重指定でも可。`@import` 推奨)。

### Jinja2 テンプレート

新規:
- `templates/_macros.html` — `{% macro icon(name, size=16, cls="") %}` インライン SVG マクロ。デザインの `Components.jsx` の `Icon` を移植 (search, refresh, bookmark, filter, target, zap, chart, sparkles, file, upRight, downRight, external, user, logout, chevDown, chevRight, plus, x, check, arrowRight, moreH)。
- `templates/_sidebar.html` — `STOCK ANALYZER` mark + NAV (ダッシュボード / 銘柄 / ウォッチリスト / スクリーニング / 分析ターゲット / ジョブ) + フッタ (`v0.1.0` + `last sync`)。
- `templates/_topbar.html` — パンくず, 検索 (`data-stock-search` を継承), ユーザーバッジ + ログアウト。
- `templates/stocks/_tab_analysis.html` — `_tab_rag.html` を改名 + 再構成。
- (任意) `templates/_panel.html` — 共通 `<section class="panel">…</section>` ラッパ。テンプレ重複が多ければ導入。

更新:
- `templates/base.html` — body クラス削除, レイアウト構造を `<div class="layout"> <aside> <main> ... </main> </div>` に。`{% block sidebar %}{% include "_sidebar.html" %}{% endblock %}` で差し替え可能に (login 用に空ブロック)。
- `templates/login.html` — `{% block sidebar %}{% endblock %}` で sidebar 抑制、中央カード型のログインフォーム (デザインの `Login` 移植) に置換。フォーム仕様はパスワードのみ維持。
- `templates/dashboard.html` — タイトル + 最終同期日時 + KPI 4 タイル (登録銘柄 / 分析ターゲット / ウォッチリスト / 直近の更新からの経過日数 or 最終同期日時) + ウォッチリスト一覧パネル。
- `templates/stocks/search.html`, `_search_results.html` — 入力カードとリストをパネル化。
- `templates/stocks/detail.html` — ヘッダ (Badge: market/standard, ID, 企業名 + 英名) + KPI タイル 5 枚 (PER/PBR/EV-EBITDA/PSR/FCF Yld) + 4 タブ (財務/バリュエーション/分析/ファイリング)。
- `templates/stocks/_tab_financial.html` — 期間切替 (`Segmented`) + メトリック切替 + コンボチャート (svg) + 財務サマリ表 + 財務指標表 (旧 `_tab_metrics.html` の内容)。
- `templates/stocks/_tab_valuation.html` — 既存表 + 10 年推移エリアチャート (svg)。
- `templates/stocks/_tab_filings.html` — テーブルをデザインのスタイルへ。
- `templates/screening/check.html` — Tailwind 全廃, 新クラスへ。
- `templates/watchlists/list.html`, `detail.html` — 同上。
- `templates/targets/list.html`, `templates/jobs/list.html`, `templates/rag/ask.html` — 同上。

削除:
- `templates/_nav.html` (横ナビ廃止)。
- `templates/stocks/_tab_metrics.html` (財務タブへ統合)。
- `templates/stocks/_tab_rag.html` (`_tab_analysis.html` へ改名 + 内容改修)。

### JavaScript
- `static/app.js` — DOM 生成時のクラス文字列を Tailwind 風から新クラスへ置換。財務タブ用に `initFinancialChart()` (コンボチャート) と `initValuationChart()` (10 年推移エリア) を新設。`fmtNumber` を `ja-JP` から `en-US` ロケール (`1,234,567`) へ変更。タブ初期値を `_tab_metrics` 削除に合わせて修正。
- `static/screening_check.js` — クラス文字列を新クラスへ置換。
- 既存タブ JS (`initTabs`, `data-tabs` / `data-tab-target` / `data-tab-panel`) は活かし、CSS でアクティブ表示を `border-bottom: 2px solid var(--accent)` に置換。

### Python (Web レイヤ)
- `web/routes/` — テンプレ削除 (`_tab_metrics.html`) と改名 (`_tab_rag.html` → `_tab_analysis.html`) に追従し、ハンドラ・URL があれば更新。`/api/stocks/{id}/metrics` API は残し、財務タブ JS から呼び出す。
- `dependencies.py` の `register_static` 等は変更なし (静的配信は `static/` 配下を維持)。

### テスト
- `tests/unit/web/test_app.py`, `test_targets.py`, `test_api.py` のレンダリング期待文字列を新クラス・新構造に追従。
- 機能テスト (HTMX 経路, スクリーニング, RAG) は構造変更なしのまま green を維持。
- フォント・SVG ファイルの 200 配信確認 (任意)。

## レイアウト構造 (擬似 HTML)

```html
<body>
  <div class="layout">
    <aside class="sidebar"> … {% include "_sidebar.html" %} … </aside>
    <main class="main">
      <header class="topbar"> … {% include "_topbar.html" %} … </header>
      <div class="content">{% block content %}{% endblock %}</div>
    </main>
  </div>
</body>
```

ログインのみ `{% block sidebar %}{% endblock %}` + `{% block topbar %}{% endblock %}` を空にして中央カードを表示。

## アイコン (インライン SVG)

- `_macros.html` の `icon` マクロが `viewBox="0 0 24 24"`, `stroke="currentColor"`, `stroke-width="1.6"`, `fill="none"`, `linecap="round"`, `linejoin="round"` で出力する。
- 命名はデザインの `Components.jsx` と同一 (search / bookmark / chart 等)。

## 数値フォーマット

- `app.js` の `fmtNumber` を `en-US` ロケール (`1,234,567`) に統一。
- パーセントは小数 1 桁 (`15.8%`)、比率は 2 桁 (`15.82`)、大きな数は `k`/`M`/`B`/`T` 接尾辞 (デザインの `fmt.large` を移植)。
- 既存テンプレで `{{ value }}` のまま出している数値は、必要に応じて Python 側の `fmt_*` ヘルパー (既に `shared/formatters.py` に存在) を使うか、変更しない。

## 削除対象 (重複・競合)

| 種別 | パス | 削除理由 |
|---|---|---|
| ファイル | `templates/_nav.html` | 横ナビ廃止、サイドバーへ移行 |
| ファイル | `templates/stocks/_tab_metrics.html` | 財務タブへ統合 |
| ファイル | `templates/stocks/_tab_rag.html` | `_tab_analysis.html` へ改名 |
| CSS | `app.css` のライトテーマ変数, グラデーション body, Tailwind シム全クラス | デザイントークン・新セマンティッククラスに置換 |
| インラインクラス | 全テンプレ・`app.js`/`screening_check.js` の `bg-white` / `rounded-lg` / `shadow` / `bg-blue-600` / `text-gray-500` / `bg-red-100` / `border` 等 Tailwind 風文字列 | 新クラス (`panel`, `btn--primary` 等) に置換 |
| ロジック | `web/routes/api.py` 等で `_tab_metrics` を前提とした分岐 (もしあれば) | 統合に合わせ更新 |

## 受け入れ条件

- ダッシュボード, 銘柄詳細 (4 タブ), スクリーニング, ウォッチリスト, ターゲット, ジョブ, ログイン がすべて新デザインで描画される。
- ライトテーマの色 (青/白/グレー) が一切残っていない (raw hex で直書きしていない、`bg-white` 等のクラスが一切残っていない)。
- HTMX 経路 (検索のインクリメンタル更新, 財務/指標/バリュエーション API, RAG Q&A) が動作する。
- `tests/unit/web/` が green。
- ブラウザ自動起動・スクリーンショットは行わない (ハンドオフ README 指示)。

## リスク

- 大規模リテーマで PR 差分が膨大になる。レビュー容易性のため、ロジック非変更 (純粋なクラス置換) と構造変更 (タブ統合・チャート追加) はコミット分割する。
- インライン SVG チャート (デザインの `ComboChart` / `ValSvg`) は数百行規模。app.js のサイズが増えるため、機能ごとに関数を分離する。
- フォント woff2 の同梱でリポジトリサイズが増える (Inter Variable ~330KB, JetBrains Mono Variable ~200KB)。許容前提。

## 未確定事項

特になし (Login=パスワードのみ、Charts=インライン SVG、Dashboard=実データのみで決定済み)。
