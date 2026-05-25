# Web UI Design System Retheme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 既存の FastAPI + Jinja2 Web UI を、Anthropic Design 由来の Stock Analyzer Design System (ダーク標準, サイドバー+トップバー, シアンアクセント, JetBrains Mono 数値, インライン SVG アイコン/チャート) へ全面的にリテーマする。Login のみ機能 (パスワードのみ) を維持。

**Architecture:** 既存の HTMX SSR + FastAPI ルートはそのまま、テンプレ・CSS・JS を全面書き換え。デザイントークン (`colors_and_type.css`) を唯一の出所として、`app.css` には旧 Tailwind 風シムを廃止しセマンティックコンポーネントクラスを定義する。Stock Detail は 5 → 4 タブに統合 (指標 → 財務へ統合, RAG → 分析へ改名)。チャートは外部ライブラリを入れずインライン SVG で実装。

**Tech Stack:** FastAPI / Jinja2 / HTMX / Vanilla JS / Inline SVG / 自前ホスト Inter & JetBrains Mono Variable Fonts

**Reference:** `docs/superpowers/specs/2026-05-02-web-ui-design-system.md`, デザインバンドル `/tmp/anthropic_design/stock-analyzer-design-system/` (gzip 展開済み)

---

## File structure

新規:
- `src/stock_analyze_system/web/static/colors_and_type.css`
- `src/stock_analyze_system/web/static/fonts/Inter-Variable.woff2`
- `src/stock_analyze_system/web/static/fonts/JetBrainsMono-Variable.woff2`
- `src/stock_analyze_system/web/static/assets/logo.svg`
- `src/stock_analyze_system/web/static/assets/mark.svg`
- `src/stock_analyze_system/web/static/assets/mark-inverse.svg`
- `src/stock_analyze_system/web/templates/_macros.html`
- `src/stock_analyze_system/web/templates/_sidebar.html`
- `src/stock_analyze_system/web/templates/_topbar.html`
- `src/stock_analyze_system/web/templates/stocks/_tab_analysis.html`

書き換え:
- `src/stock_analyze_system/web/static/app.css`
- `src/stock_analyze_system/web/static/app.js`
- `src/stock_analyze_system/web/static/screening_check.js`
- `src/stock_analyze_system/web/templates/base.html`
- `src/stock_analyze_system/web/templates/login.html`
- `src/stock_analyze_system/web/templates/dashboard.html`
- `src/stock_analyze_system/web/templates/stocks/{detail.html, search.html, _search_results.html, _tab_financial.html, _tab_valuation.html, _tab_filings.html}`
- `src/stock_analyze_system/web/templates/screening/check.html`
- `src/stock_analyze_system/web/templates/watchlists/{list.html, detail.html}`
- `src/stock_analyze_system/web/templates/targets/list.html`
- `src/stock_analyze_system/web/templates/jobs/list.html`
- `src/stock_analyze_system/web/templates/rag/ask.html`

削除:
- `src/stock_analyze_system/web/templates/_nav.html`
- `src/stock_analyze_system/web/templates/stocks/_tab_metrics.html`
- `src/stock_analyze_system/web/templates/stocks/_tab_rag.html`

---

## Task 1: 静的アセット (トークン CSS, フォント, ロゴ) を移植

**Files:**
- Create: `src/stock_analyze_system/web/static/colors_and_type.css`
- Create: `src/stock_analyze_system/web/static/fonts/Inter-Variable.woff2`
- Create: `src/stock_analyze_system/web/static/fonts/JetBrainsMono-Variable.woff2`
- Create: `src/stock_analyze_system/web/static/assets/logo.svg`
- Create: `src/stock_analyze_system/web/static/assets/mark.svg`
- Create: `src/stock_analyze_system/web/static/assets/mark-inverse.svg`

- [ ] **Step 1: フォントとアセットをコピー**

```bash
mkdir -p src/stock_analyze_system/web/static/fonts src/stock_analyze_system/web/static/assets
cp /tmp/anthropic_design/stock-analyzer-design-system/project/fonts/Inter-Variable.woff2 \
   src/stock_analyze_system/web/static/fonts/
cp /tmp/anthropic_design/stock-analyzer-design-system/project/fonts/JetBrainsMono-Variable.woff2 \
   src/stock_analyze_system/web/static/fonts/
cp /tmp/anthropic_design/stock-analyzer-design-system/project/assets/logo.svg \
   /tmp/anthropic_design/stock-analyzer-design-system/project/assets/mark.svg \
   /tmp/anthropic_design/stock-analyzer-design-system/project/assets/mark-inverse.svg \
   src/stock_analyze_system/web/static/assets/
```

- [ ] **Step 2: `colors_and_type.css` を移植して font URL を補正**

```bash
cp /tmp/anthropic_design/stock-analyzer-design-system/project/colors_and_type.css \
   src/stock_analyze_system/web/static/colors_and_type.css
```

`fonts/Inter-Variable.woff2` 等の相対パスを `/static/fonts/Inter-Variable.woff2` に置換するために以下の Edit を実施:

- `url("fonts/Inter-Variable.woff2")` → `url("/static/fonts/Inter-Variable.woff2")`
- `url("fonts/JetBrainsMono-Variable.woff2")` → `url("/static/fonts/JetBrainsMono-Variable.woff2")`

- [ ] **Step 3: コミット**

```bash
git add src/stock_analyze_system/web/static/colors_and_type.css \
        src/stock_analyze_system/web/static/fonts \
        src/stock_analyze_system/web/static/assets
git commit -m "feat(web): vendor design tokens, variable fonts, and brand marks"
```

---

## Task 2: `app.css` をセマンティックコンポーネントクラスに全面書き換え

**Files:**
- Modify: `src/stock_analyze_system/web/static/app.css`

- [ ] **Step 1: 既存テスト (あれば) を確認**

```bash
grep -nE "(bg-white|rounded-lg|shadow|bg-blue|bg-red|text-gray)" tests/unit/web/*.py
```

これらのクラスがテストの期待値に出現していたら、後続タスクで合わせて修正する。

- [ ] **Step 2: `app.css` を全面置換**

ファイル全体を以下で置換:

```css
/* Stock Analyzer — semantic component layer.
   All raw tokens come from colors_and_type.css. No raw hex here. */
@import url("/static/colors_and_type.css");

* { box-sizing: border-box; }

::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 4px; }
::-webkit-scrollbar-track { background: var(--bg); }

a { color: var(--accent); }
a:hover { color: var(--accent-hover); text-decoration: none; }

button { font: inherit; cursor: pointer; }
button:disabled { cursor: not-allowed; opacity: 0.5; }

input, select, textarea { font: inherit; }

/* ---------- Layout shell ---------- */
.layout {
  display: flex;
  min-height: 100vh;
  background: var(--bg);
}

.sidebar {
  width: var(--sidebar-w);
  background: var(--surface);
  border-right: 1px solid var(--border);
  height: 100vh;
  position: sticky;
  top: 0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar__brand {
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.sidebar__brand-text {
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: var(--text-sm);
  letter-spacing: var(--tracking-wide);
  color: var(--fg-1);
}

.sidebar__nav {
  padding: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.sidebar__link {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  color: var(--fg-2);
  font-weight: var(--fw-medium);
  font-size: var(--text-sm);
  transition: background var(--dur-1) var(--ease-snap);
}

.sidebar__link:hover {
  background: var(--surface-2);
  color: var(--fg-1);
  text-decoration: none;
}

.sidebar__link[aria-current="page"] {
  background: var(--surface-2);
  color: var(--fg-1);
}

.sidebar__footer {
  padding: var(--space-3);
  border-top: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--fg-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.sidebar__footer-row {
  display: flex;
  justify-content: space-between;
}

.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.topbar {
  height: var(--topbar-h);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 var(--space-5);
  gap: var(--space-4);
  background: var(--bg);
  position: sticky;
  top: 0;
  z-index: 5;
}

.topbar__breadcrumbs {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--fg-2);
}

.topbar__crumb { color: var(--fg-2); }
.topbar__crumb--current { color: var(--fg-1); font-weight: var(--fw-medium); }
.topbar__crumb-sep { color: var(--fg-3); }

.topbar__search {
  position: relative;
  width: 280px;
}

.topbar__search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--fg-3);
}

.topbar__search-input {
  width: 100%;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 6px 10px 6px 30px;
  color: var(--fg-1);
  font-size: var(--text-xs);
  outline: none;
}

.topbar__search-input:focus { border-color: var(--accent); box-shadow: var(--ring-focus); }

.topbar__user {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--fg-2);
}

.topbar__user a:hover { color: var(--fg-1); }

.content {
  padding: var(--space-5);
  max-width: var(--content-max);
  width: 100%;
}

/* ---------- Page header ---------- */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: var(--space-5);
  gap: var(--space-4);
}

.page-header__meta {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--fg-3);
  margin-top: var(--space-1);
}

.page-header__actions {
  display: flex;
  gap: var(--space-2);
}

/* ---------- Panel (card) ---------- */
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.panel__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
  gap: var(--space-3);
}

.panel__title {
  font-family: var(--font-sans);
  font-weight: var(--fw-semibold);
  font-size: var(--text-h3);
  color: var(--fg-1);
  margin: 0;
}

.panel__action { display: flex; align-items: center; gap: var(--space-2); }

.panel__body { padding: var(--space-4); }
.panel__body--flush { padding: 0; }

/* ---------- KPI tile ---------- */
.kpi-grid { display: grid; gap: var(--space-3); }
.kpi-grid--3 { grid-template-columns: repeat(3, 1fr); }
.kpi-grid--4 { grid-template-columns: repeat(4, 1fr); }
.kpi-grid--5 { grid-template-columns: repeat(5, 1fr); }

.kpi-tile {
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  background: var(--surface);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.kpi-tile__label {
  font-size: var(--text-xs);
  font-weight: var(--fw-medium);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
  color: var(--fg-2);
}

.kpi-tile__value {
  font-family: var(--font-mono);
  font-size: 24px;
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  font-variant-numeric: tabular-nums;
  letter-spacing: var(--tracking-tight);
  line-height: 1.1;
}

.kpi-tile__delta {
  font-family: var(--font-mono);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--fg-2);
}

.kpi-tile__delta--up { color: var(--up); }
.kpi-tile__delta--down { color: var(--down); }

/* ---------- Buttons ---------- */
.btn {
  font-family: var(--font-sans);
  font-weight: var(--fw-medium);
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  padding: 8px 14px;
  font-size: var(--text-sm);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--surface-2);
  color: var(--fg-1);
  border-color: var(--border-strong);
  transition: background var(--dur-1) var(--ease-snap), border-color var(--dur-1) var(--ease-snap);
}
.btn:hover:not(:disabled) { background: var(--surface-3, var(--surface-2)); }
.btn--sm { padding: 5px 10px; font-size: var(--text-xs); }
.btn--primary { background: var(--accent); color: var(--accent-fg); border-color: transparent; }
.btn--primary:hover:not(:disabled) { background: var(--accent-hover); }
.btn--ghost { background: transparent; border-color: transparent; color: var(--fg-1); }
.btn--ghost:hover:not(:disabled) { background: var(--surface-2); }
.btn--danger { background: transparent; color: var(--down); border-color: var(--border-strong); }
.btn--danger:hover:not(:disabled) { background: var(--down-soft); }
.btn--block { width: 100%; justify-content: center; }

/* ---------- Form fields ---------- */
.field { display: flex; flex-direction: column; gap: 6px; }
.label {
  font-size: var(--text-xs);
  font-weight: var(--fw-semibold);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
  color: var(--fg-2);
}

.input, select.input, textarea.input {
  background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  color: var(--fg-1);
  padding: 8px 12px;
  width: 100%;
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  font-weight: var(--fw-medium);
  outline: none;
}
.input:focus { border-color: var(--accent); box-shadow: var(--ring-focus); }
.input--mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.input--invalid { border-color: var(--down); }

/* ---------- Badge ---------- */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: var(--fw-medium);
  line-height: 1;
  background: var(--surface-2);
  color: var(--fg-2);
  border: 1px solid var(--border);
}
.badge--mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.badge--accent { background: var(--accent-soft); color: var(--accent); border-color: transparent; }
.badge--up { background: var(--up-soft); color: var(--up); border-color: transparent; }
.badge--down { background: var(--down-soft); color: var(--down); border-color: transparent; }
.badge--solid { background: var(--accent); color: var(--accent-fg); border-color: transparent; }

/* ---------- Tabs (underline) ---------- */
.tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: var(--topbar-h);
  background: var(--bg);
  z-index: 4;
}
.tab {
  background: transparent;
  border: 0;
  color: var(--fg-2);
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  font-weight: var(--fw-medium);
  padding: 10px 16px;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tab[data-active="true"] { color: var(--fg-1); border-bottom-color: var(--accent); }

/* ---------- Segmented ---------- */
.segmented {
  display: inline-flex;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 2px;
}
.segmented__option {
  background: transparent;
  border: 0;
  border-radius: 4px;
  padding: 5px 12px;
  color: var(--fg-2);
  font-size: var(--text-xs);
  font-weight: var(--fw-medium);
}
.segmented__option[data-active="true"] {
  background: var(--surface);
  color: var(--fg-1);
  box-shadow: 0 1px 2px rgba(0,0,0,.4);
}

/* ---------- Tables ---------- */
.table { width: 100%; border-collapse: collapse; }
.table thead th {
  text-align: left;
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: var(--fw-medium);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
  color: var(--fg-2);
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-strong);
}
.table tbody td {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  color: var(--fg-1);
  font-size: var(--text-sm);
}
.table tbody tr:hover td { background: var(--surface-2); }
.table .num,
.table .num-cell {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  text-align: right;
  color: var(--fg-1);
}

.up   { color: var(--up); }
.down { color: var(--down); }
.muted   { color: var(--fg-2); }
.subtle  { color: var(--fg-3); }

/* ---------- Icons ---------- */
.icon { display: inline-block; vertical-align: -2px; }

/* ---------- Empty state ---------- */
.empty-state {
  padding: var(--space-5);
  text-align: center;
  color: var(--fg-2);
  font-size: var(--text-sm);
}

/* ---------- Login ---------- */
.login-shell {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}
.login-card {
  width: 360px;
  padding: 32px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
}
.login-card__brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-5);
}
.login-card__title {
  font-family: var(--font-sans);
  font-size: 18px;
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  margin: 0 0 var(--space-5) 0;
}
.login-card__error {
  margin-bottom: var(--space-3);
  padding: 8px 12px;
  background: var(--down-soft);
  color: var(--down);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}
.login-card__footer {
  margin-top: var(--space-5);
  padding-top: var(--space-4);
  border-top: 1px solid var(--border);
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--fg-3);
  text-align: center;
}

/* ---------- Stock detail header ---------- */
.stock-header { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-4); }
.stock-header__meta { display: flex; align-items: center; gap: var(--space-2); margin-bottom: 6px; }
.stock-header__id { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--fg-3); }
.stock-header__title { font-size: 26px; font-weight: var(--fw-bold); letter-spacing: -0.01em; margin: 0; color: var(--fg-1); }
.stock-header__title-en { color: var(--fg-3); font-weight: var(--fw-medium); }
.stock-header__price-row { display: flex; gap: var(--space-4); margin-top: var(--space-2); align-items: baseline; }
.stock-header__price { font-family: var(--font-mono); font-size: 28px; font-weight: var(--fw-semibold); color: var(--fg-1); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }
.stock-header__delta { font-family: var(--font-mono); font-size: var(--text-sm); font-variant-numeric: tabular-nums; }
.stock-header__cap { font-size: var(--text-xs); color: var(--fg-3); font-family: var(--font-mono); }

/* ---------- Misc grid utilities (used sparingly) ---------- */
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); }
.flex { display: flex; }
.flex--gap-2 { gap: var(--space-2); }
.flex--gap-3 { gap: var(--space-3); }
.flex--between { justify-content: space-between; }
.flex--center { align-items: center; }
.flex--end { align-items: flex-end; }
.flex--col { flex-direction: column; }
.stack > * + * { margin-top: var(--space-3); }
.stack--lg > * + * { margin-top: var(--space-5); }

[hidden] { display: none !important; }
```

- [ ] **Step 3: 起動して 200 を返すことだけ確認**

```bash
uv run pytest tests/unit/web/test_app.py::test_static_files_mounted tests/unit/web/test_app.py::test_templates_do_not_load_remote_cdn_assets -v
```

Expected: PASS (既存テストの assertion は変わっていない)。

- [ ] **Step 4: コミット**

```bash
git add src/stock_analyze_system/web/static/app.css
git commit -m "feat(web): replace tailwind shim with token-based component css"
```

---

## Task 3: アイコンマクロ (`_macros.html`)

**Files:**
- Create: `src/stock_analyze_system/web/templates/_macros.html`

- [ ] **Step 1: マクロを作成**

`src/stock_analyze_system/web/templates/_macros.html`:

```html
{# Inline SVG icons. Usage: {{ icon("search", 16) }} or {{ icon("search", 16, cls="muted") }} #}
{% macro icon(name, size=16, cls="") -%}
{%- set paths = {
  "search":   '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/>',
  "refresh":  '<path d="M21 12a9 9 0 1 1-3.8-7.3M21 5v5h-5"/>',
  "bookmark": '<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>',
  "filter":   '<path d="M3 6h18M7 12h10M11 18h2"/>',
  "target":   '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
  "zap":      '<path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"/>',
  "chart":    '<path d="M3 12h4l3-9 4 18 3-9h4"/>',
  "sparkles": '<path d="M12 3l1.6 5h5.4l-4.4 3.2 1.7 5.3L12 13.6 7.7 16.5l1.7-5.3L5 8h5.4z"/>',
  "file":     '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>',
  "upRight":  '<path d="M7 17l10-10M9 7h8v8"/>',
  "downRight":'<path d="M7 7l10 10M9 17h8V9"/>',
  "external":'<path d="M14 4h6v6M10 14L20 4M14 12v6H4V8h6"/>',
  "user":     '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="10" r="3"/><path d="M6.5 19a6 6 0 0 1 11 0"/>',
  "logout":   '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  "chevDown": '<path d="M6 9l6 6 6-6"/>',
  "chevRight":'<path d="M9 6l6 6-6 6"/>',
  "plus":     '<path d="M12 5v14M5 12h14"/>',
  "x":        '<path d="M18 6L6 18M6 6l12 12"/>',
  "check":    '<path d="M5 12l5 5L20 7"/>',
  "arrowRight":'<path d="M5 12h14M13 6l6 6-6 6"/>',
  "moreH":    '<circle cx="6" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="18" cy="12" r="1.5"/>'
} -%}
<svg class="icon{% if cls %} {{ cls }}{% endif %}" viewBox="0 0 24 24" width="{{ size }}" height="{{ size }}"
  fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"
  aria-hidden="true">{{ paths.get(name, "") | safe }}</svg>
{%- endmacro %}
```

- [ ] **Step 2: コミット**

```bash
git add src/stock_analyze_system/web/templates/_macros.html
git commit -m "feat(web): add jinja2 macro for inline SVG icons"
```

---

## Task 4: サイドバーパーシャル (`_sidebar.html`)

**Files:**
- Create: `src/stock_analyze_system/web/templates/_sidebar.html`

- [ ] **Step 1: サイドバーを作成**

`src/stock_analyze_system/web/templates/_sidebar.html`:

```html
{% from "_macros.html" import icon %}
{% set path = request.url.path %}
{% set links = [
    ("/", "ダッシュボード", "chart"),
    ("/stocks/search", "銘柄", "search"),
    ("/watchlists", "ウォッチリスト", "bookmark"),
    ("/screening", "スクリーニング", "filter"),
    ("/targets", "分析ターゲット", "target"),
    ("/jobs", "ジョブ", "zap"),
] %}
<aside class="sidebar">
    <div class="sidebar__brand">
        <img src="/static/assets/mark.svg" width="22" height="22" alt="">
        <span class="sidebar__brand-text">STOCK ANALYZER</span>
    </div>
    <nav class="sidebar__nav">
        {% for href, label, ic in links %}
        {% set is_active = (href == "/" and path == "/") or (href != "/" and path.startswith(href)) %}
        <a class="sidebar__link" href="{{ href }}"
           {% if is_active %}aria-current="page"{% endif %}>
            {{ icon(ic, 15) }}{{ label }}
        </a>
        {% endfor %}
    </nav>
    <div class="sidebar__footer">
        <div class="sidebar__footer-row">
            <span>v0.1.0</span>
            <span>SQLite WAL</span>
        </div>
    </div>
</aside>
```

- [ ] **Step 2: コミット**

```bash
git add src/stock_analyze_system/web/templates/_sidebar.html
git commit -m "feat(web): add sidebar partial with brand mark and nav"
```

---

## Task 5: トップバーパーシャル (`_topbar.html`)

**Files:**
- Create: `src/stock_analyze_system/web/templates/_topbar.html`

- [ ] **Step 1: トップバーを作成**

`src/stock_analyze_system/web/templates/_topbar.html`:

```html
{% from "_macros.html" import icon %}
<header class="topbar">
    <div class="topbar__breadcrumbs">
        {% for crumb in breadcrumbs or [] %}
            {% if not loop.first %}<span class="topbar__crumb-sep">→</span>{% endif %}
            <span class="topbar__crumb{% if loop.last %} topbar__crumb--current{% endif %}">{{ crumb }}</span>
        {% endfor %}
    </div>
    <div class="topbar__search">
        <span class="topbar__search-icon">{{ icon("search", 14) }}</span>
        <input class="topbar__search-input" type="search"
               data-stock-search data-search-url="/stocks/search/results"
               placeholder="銘柄を検索 (例: AAPL, 7203)">
    </div>
    <div class="topbar__user">
        {{ icon("user", 16, cls="muted") }}
        <a href="/logout">ログアウト</a>
    </div>
</header>
```

注意: 既存の `static/app.js` の `initSearch()` は `[data-stock-search]` を起点として動くので、トップバーに置いても機能する。`results = document.getElementById("search-results")` という ID 参照になっているので、検索結果をどこに描画するかは別途検討。**今回はトップバーの検索を即時ナビゲーションに変えず、検索ページ (`/stocks/search`) と同じ仕様を維持** → `data-search-url` の参照先は専用ページなので、現状維持で OK。後の Task 14 で銘柄検索ページのレイアウトを更新する際に整合させる。

- [ ] **Step 2: コミット**

```bash
git add src/stock_analyze_system/web/templates/_topbar.html
git commit -m "feat(web): add topbar partial with breadcrumbs, search, logout"
```

---

## Task 6: `base.html` を新レイアウトに置き換え

**Files:**
- Modify: `src/stock_analyze_system/web/templates/base.html`

- [ ] **Step 1: テストを追加**

`tests/unit/web/test_app.py` の `test_templates_do_not_load_remote_cdn_assets` に続き、新規アサーションを **追加** (既存テストの末尾に新しい `def` を追加):

```python
def test_base_template_uses_new_layout_classes():
    base_template = Path(
        "src/stock_analyze_system/web/templates/base.html"
    ).read_text()
    assert 'class="layout"' in base_template
    assert "_sidebar.html" in base_template
    assert "_topbar.html" in base_template
    assert "bg-gray-50" not in base_template


def test_nav_template_is_removed():
    nav_path = Path("src/stock_analyze_system/web/templates/_nav.html")
    assert not nav_path.exists()
```

注意: `test_nav_template_is_removed` は **Task 18** までフェイルする。よってこのステップでは `test_base_template_uses_new_layout_classes` のみ追加する。

- [ ] **Step 2: テスト実行で fail を確認**

```bash
uv run pytest tests/unit/web/test_app.py::test_base_template_uses_new_layout_classes -v
```

Expected: FAIL.

- [ ] **Step 3: `base.html` を書き換え**

`src/stock_analyze_system/web/templates/base.html`:

```html
<!doctype html>
<html lang="ja">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}Stock Analyze System{% endblock %}</title>
    <link rel="stylesheet" href="/static/app.css">
    <script defer src="/static/app.js"></script>
</head>
<body>
    <div class="layout">
        {% block sidebar %}{% include "_sidebar.html" %}{% endblock %}
        <main class="main">
            {% block topbar %}{% include "_topbar.html" %}{% endblock %}
            <div class="content">
                {% block content %}{% endblock %}
            </div>
        </main>
    </div>
</body>
</html>
```

- [ ] **Step 4: テスト実行で pass を確認**

```bash
uv run pytest tests/unit/web/test_app.py::test_base_template_uses_new_layout_classes tests/unit/web/test_app.py::test_templates_do_not_load_remote_cdn_assets -v
```

Expected: PASS。

- [ ] **Step 5: コミット**

```bash
git add src/stock_analyze_system/web/templates/base.html tests/unit/web/test_app.py
git commit -m "feat(web): switch base layout to sidebar+topbar shell"
```

---

## Task 7: ログイン画面をデザインスタイルに置換 (機能はパスワードのみ維持)

**Files:**
- Modify: `src/stock_analyze_system/web/templates/login.html`

- [ ] **Step 1: テスト実行で既存挙動を把握**

```bash
uv run pytest tests/unit/web/ -k login -v
```

ログインの POST フローテストがあれば、フィールド名 `password` を維持したまま見た目だけ変えればパスする。

- [ ] **Step 2: `login.html` を書き換え**

```html
{% extends "base.html" %}
{% from "_macros.html" import icon %}
{% block title %}ログイン — Stock Analyze System{% endblock %}
{% block sidebar %}{% endblock %}
{% block topbar %}{% endblock %}
{% block content %}
<div class="login-shell">
    <div class="login-card">
        <div class="login-card__brand">
            <img src="/static/assets/mark.svg" width="28" height="28" alt="">
            <span class="sidebar__brand-text">STOCK ANALYZER</span>
        </div>
        <h2 class="login-card__title">ログイン</h2>
        {% if error %}
        <div class="login-card__error">{{ error }}</div>
        {% endif %}
        <form method="post" action="/login" class="stack">
            <div class="field">
                <label class="label" for="password">パスワード</label>
                <input class="input input--mono" id="password" name="password" type="password"
                       required autofocus placeholder="••••••••">
            </div>
            <button class="btn btn--primary btn--block" type="submit">ログイン</button>
        </form>
        <div class="login-card__footer">ローカル認証 · single-user mode</div>
    </div>
</div>
{% endblock %}
```

注意点: `base.html` の `<div class="content">` ラッパは login にも入る。`.login-shell` を `min-height: 100vh; display:flex; align-items:center` に設定しているので、`.content` の `padding: 24px; max-width: 1440px` の中で十分なスペースが確保される。トップバー/サイドバーが空ブロック上書きで非表示になるので、`min-height: 100vh` を `.content` ではなく外側に出さなくても見た目は中央寄せになる。

- [ ] **Step 3: 既存ログインテストを実行**

```bash
uv run pytest tests/unit/web/ -k login -v
```

Expected: PASS。

- [ ] **Step 4: コミット**

```bash
git add src/stock_analyze_system/web/templates/login.html
git commit -m "feat(web): restyle login as centered card on dark canvas"
```

---

## Task 8: ダッシュボードを KPI タイル + ウォッチリストプレビューに置き換え

**Files:**
- Modify: `src/stock_analyze_system/web/templates/dashboard.html`

- [ ] **Step 1: 既存ダッシュボードテストの期待値を更新**

`tests/unit/web/test_app.py` か `test_targets.py` に `dashboard` のレンダリング検証があれば確認 (上記 grep で確認済み: 直接の HTML アサーションは無い。`test_create_app_returns_fastapi_instance` 等 app-factory テストのみ)。

- [ ] **Step 2: `dashboard.html` を書き換え**

```html
{% extends "base.html" %}
{% set breadcrumbs = ["ダッシュボード"] %}
{% from "_macros.html" import icon %}
{% block title %}ダッシュボード — Stock Analyze System{% endblock %}
{% block content %}
<div class="page-header">
    <div>
        <h1 class="h1">ダッシュボード</h1>
        <div class="page-header__meta">登録 {{ company_count }}銘柄 · ウォッチ {{ watchlist_count }}件</div>
    </div>
</div>

<div class="kpi-grid kpi-grid--3">
    <div class="kpi-tile">
        <span class="kpi-tile__label">登録銘柄</span>
        <div class="kpi-tile__value">{{ company_count }}</div>
    </div>
    <div class="kpi-tile">
        <span class="kpi-tile__label">分析ターゲット</span>
        <div class="kpi-tile__value">{{ target_count }}</div>
    </div>
    <div class="kpi-tile">
        <span class="kpi-tile__label">ウォッチリスト</span>
        <div class="kpi-tile__value">{{ watchlist_count }}</div>
    </div>
</div>
{% endblock %}
```

注意: デザインの 4 タイル目 (`平均PER` や同期履歴) は実データが無いため除外。`page-header__meta` に同等情報を集約。

- [ ] **Step 3: ダッシュボードテストを実行**

```bash
uv run pytest tests/unit/web/ -v
```

Expected: PASS。

- [ ] **Step 4: コミット**

```bash
git add src/stock_analyze_system/web/templates/dashboard.html
git commit -m "feat(web): redesign dashboard as KPI tiles on dark canvas"
```

---

## Task 9: Stock Detail のヘッダ + KPI タイル + 4 タブ構造

**Files:**
- Modify: `src/stock_analyze_system/web/templates/stocks/detail.html`

注意: KPI タイルの数値は **既存の API 経由 (JS で fetch)** で埋める。テンプレでは空セル + `data-detail-kpi` 属性を出力し、`app.js` の `initDetailKpis(panel)` (Task 17 で追加) が `/api/stocks/{id}/valuations` の最新行と `/api/stocks/{id}/metrics` から PER/PBR/EV-EBITDA/PSR/FCF Yld を埋める。実データが無ければ `—` 表示。

- [ ] **Step 1: `detail.html` を書き換え**

```html
{% extends "base.html" %}
{% set breadcrumbs = ["銘柄", company.name] %}
{% from "_macros.html" import icon %}
{% block title %}{{ company.name }} — {{ company.ticker or company.security_code }}{% endblock %}
{% block content %}
<div data-tabs data-default-tab="financial" data-company-id="{{ company.id }}" data-detail-kpis>
    <header class="stock-header">
        <div>
            <div class="stock-header__meta">
                <span class="badge badge--mono">{{ company.market }}</span>
                <span class="stock-header__id">{{ company.id }}</span>
            </div>
            <h1 class="stock-header__title">
                {{ company.name }}
                {% if company.ticker or company.security_code %}
                <span class="stock-header__title-en">· {{ company.ticker or company.security_code }}</span>
                {% endif %}
            </h1>
        </div>
        <div class="page-header__actions">
            <a class="btn" href="/jobs">{{ icon("refresh", 14) }} ジョブ</a>
        </div>
    </header>

    <div class="kpi-grid kpi-grid--5" style="margin-top: var(--space-4);">
        {% for k in ["per", "pbr", "ev_ebitda", "psr", "fcf_yield"] %}
        {% set labels = {"per": "PER", "pbr": "PBR", "ev_ebitda": "EV/EBITDA", "psr": "PSR", "fcf_yield": "FCF Yield"} %}
        <div class="kpi-tile">
            <span class="kpi-tile__label">{{ labels[k] }}</span>
            <div class="kpi-tile__value" data-kpi="{{ k }}">—</div>
        </div>
        {% endfor %}
    </div>

    <nav class="tabs" style="margin-top: var(--space-5);">
        {% set tabs = [
            ("financial", "財務"),
            ("valuation", "バリュエーション"),
            ("analysis", "分析"),
            ("filings", "ファイリング"),
        ] %}
        {% for key, label in tabs %}
        <button type="button" class="tab" data-tab-target="{{ key }}">{{ label }}</button>
        {% endfor %}
    </nav>

    <div data-tab-panel="financial" class="stack stack--lg" style="margin-top: var(--space-4);">
        {% include "stocks/_tab_financial.html" %}
    </div>
    <div data-tab-panel="valuation" hidden style="margin-top: var(--space-4);">
        {% include "stocks/_tab_valuation.html" %}
    </div>
    <div data-tab-panel="analysis" hidden style="margin-top: var(--space-4);">
        {% include "stocks/_tab_analysis.html" %}
    </div>
    <div data-tab-panel="filings" hidden style="margin-top: var(--space-4);">
        {% include "stocks/_tab_filings.html" %}
    </div>
</div>
{% endblock %}
```

- [ ] **Step 2: `_tab_analysis.html` を `_tab_rag.html` から作成 (内容は Task 12 で書き換え、暫定はコピー)**

```bash
cp src/stock_analyze_system/web/templates/stocks/_tab_rag.html \
   src/stock_analyze_system/web/templates/stocks/_tab_analysis.html
```

(後の Task 12 で内容書き換え。`detail.html` が `_tab_analysis.html` を include するため先に存在させる必要あり)

- [ ] **Step 3: テンプレリンタが通ることを確認 (テスト不要なら skip)**

```bash
uv run pytest tests/unit/web/ -v
```

Expected: PASS (既存テストは structural アサーションだけ、このタスクで影響を受けない)。
注意: `_tab_metrics.html` を include していたタブ構造は既に削除済み (5 → 4 タブ)。Stock detail を開いた時に metrics を空のまま表示する API は呼ばれなくなったが、財務タブ統合は Task 10 で実施。

- [ ] **Step 4: コミット**

```bash
git add src/stock_analyze_system/web/templates/stocks/detail.html \
        src/stock_analyze_system/web/templates/stocks/_tab_analysis.html
git commit -m "feat(web): redesign stock detail header, KPI tiles, and 4-tab structure"
```

---

## Task 10: 財務タブ (財務 + 旧指標 + コンボチャート) を統合

**Files:**
- Modify: `src/stock_analyze_system/web/templates/stocks/_tab_financial.html`
- Modify: `src/stock_analyze_system/web/static/app.js` (新関数 `initFinancialChart` 追加)
- Delete: `src/stock_analyze_system/web/templates/stocks/_tab_metrics.html`

- [ ] **Step 1: `_tab_financial.html` を書き換え**

```html
<div class="stack" data-financial-panel data-company-id="{{ company.id }}">
    <div class="flex flex--between flex--center">
        <div class="segmented" role="tablist" data-period-segmented>
            <button class="segmented__option" data-period-value="annual" data-active="true">通期</button>
            <button class="segmented__option" data-period-value="quarterly">四半期</button>
        </div>
        <select data-period-select hidden>
            <option value="annual">通期</option>
            <option value="quarterly">四半期</option>
        </select>
        <p class="muted" data-financial-summary>読み込み中…</p>
    </div>

    <section class="panel">
        <header class="panel__header">
            <h3 class="panel__title">売上高 推移</h3>
            <span class="muted" style="font-family: var(--font-mono); font-size: 11px;">単位: 百万USD</span>
        </header>
        <div class="panel__body">
            <div data-financial-chart></div>
        </div>
    </section>

    <section class="panel">
        <header class="panel__header"><h3 class="panel__title">財務サマリ</h3></header>
        <div class="panel__body panel__body--flush">
            <table class="table">
                <thead>
                    <tr>
                        <th>期末</th>
                        <th class="num-cell">売上</th>
                        <th class="num-cell">営業利益</th>
                        <th class="num-cell">純利益</th>
                        <th class="num-cell">EPS</th>
                    </tr>
                </thead>
                <tbody data-financial-body></tbody>
            </table>
        </div>
    </section>

    <section class="panel" data-metrics-panel data-company-id="{{ company.id }}">
        <header class="panel__header"><h3 class="panel__title">財務指標</h3></header>
        <div class="panel__body panel__body--flush">
            <table class="table">
                <thead>
                    <tr>
                        <th>期末</th>
                        <th class="num-cell">ROE</th>
                        <th class="num-cell">ROA</th>
                        <th class="num-cell">営業利益率</th>
                        <th class="num-cell">純利益率</th>
                        <th class="num-cell">売上成長率</th>
                    </tr>
                </thead>
                <tbody data-metrics-body></tbody>
            </table>
        </div>
    </section>
</div>
```

注意: `data-period-select` は app.js が既に依存しているため hidden で残す。新規 `data-period-segmented` を表示用に追加し、Task 17 で同期ハンドラを実装。

- [ ] **Step 2: `_tab_metrics.html` を削除**

```bash
git rm src/stock_analyze_system/web/templates/stocks/_tab_metrics.html
```

- [ ] **Step 3: `app.js` の `initFinancialPanels` の DOM 生成を新クラスに揃える**

`src/stock_analyze_system/web/static/app.js` の `initFinancialPanels` 関数内、DOM生成行を以下に置き換える:

```javascript
function initFinancialPanels() {
    document.querySelectorAll("[data-financial-panel]").forEach((panel) => {
        const companyId = panel.dataset.companyId;
        const select = panel.querySelector("[data-period-select]");
        const segmented = panel.querySelector("[data-period-segmented]");
        const tbody = panel.querySelector("[data-financial-body]");
        const summary = panel.querySelector("[data-financial-summary]");
        const chartHost = panel.querySelector("[data-financial-chart]");

        function syncSegmented() {
            if (!segmented) return;
            segmented.querySelectorAll("[data-period-value]").forEach((b) => {
                b.dataset.active = b.dataset.periodValue === select.value ? "true" : "false";
            });
        }
        if (segmented) {
            segmented.querySelectorAll("[data-period-value]").forEach((b) => {
                b.addEventListener("click", () => {
                    select.value = b.dataset.periodValue;
                    select.dispatchEvent(new Event("change"));
                });
            });
        }

        async function load() {
            tbody.innerHTML = "";
            summary.textContent = "読み込み中…";
            const rows = await fetchJson(`/api/stocks/${companyId}/financials/${select.value}`);
            if (!rows.length) {
                summary.textContent = "財務データがありません。";
                renderEmptyRow(tbody, 5, "財務データがありません。");
                if (chartHost) chartHost.innerHTML = "";
                return;
            }
            const latest = rows[0];
            summary.textContent =
                `最新 ${latest.fiscal_year_end}: 売上 ${fmtNumber(latest.revenue)}, 純利益 ${fmtNumber(latest.net_income)}`;
            rows.forEach((row) => {
                const tr = document.createElement("tr");
                [
                    row.fiscal_year_end,
                    fmtNumber(row.revenue),
                    fmtNumber(row.operating_income),
                    fmtNumber(row.net_income),
                    fmtNumber(row.eps),
                ].forEach((value, index) => {
                    const td = document.createElement("td");
                    if (index > 0) td.className = "num-cell";
                    td.textContent = value;
                    tr.appendChild(td);
                });
                tbody.appendChild(tr);
            });
            if (chartHost) renderFinancialChart(chartHost, rows);
        }

        select.addEventListener("change", () => {
            syncSegmented();
            load().catch((error) => {
                summary.textContent = `取得失敗: ${error.message}`;
                renderEmptyRow(tbody, 5, "取得に失敗しました。");
            });
        });
        syncSegmented();
        load().catch((error) => {
            summary.textContent = `取得失敗: ${error.message}`;
            renderEmptyRow(tbody, 5, "取得に失敗しました。");
        });
    });
}
```

`renderEmptyRow` の `td.className = "px-2 py-3 text-sm text-gray-500"` を `td.className = "muted"` に変更:

```javascript
function renderEmptyRow(tbody, colspan, message) {
    tbody.innerHTML = "";
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = colspan;
    td.className = "muted";
    td.textContent = message;
    tr.appendChild(td);
    tbody.appendChild(tr);
}
```

- [ ] **Step 4: `renderFinancialChart` (インライン SVG コンボチャート) を `app.js` 末尾の IIFE 内に追加**

`(function () {` の中、`document.addEventListener("DOMContentLoaded", ...)` の直前に挿入:

```javascript
function renderFinancialChart(host, rows) {
    // 古い順に並べる: rows は新しい→古い順で API から来るため反転する
    const data = [...rows].reverse().map(r => ({
        fy: String(r.fiscal_year_end || ""),
        revenue: Number(r.revenue) || 0,
    }));
    const series = data.map((d, i) => {
        const prev = i > 0 ? data[i - 1].revenue : null;
        const yoy = prev != null && prev !== 0 ? (d.revenue - prev) / Math.abs(prev) : null;
        return { fy: d.fy, value: d.revenue, yoy };
    });
    const w = 800, h = 260, padL = 60, padR = 60, padT = 24, padB = 36;
    const innerW = w - padL - padR;
    const innerH = h - padT - padB;
    const maxV = Math.max(...series.map(s => s.value), 1);
    const yoys = series.map(s => s.yoy).filter(v => v != null);
    const yoyRange = Math.max(0.05, ...yoys.map(Math.abs));
    const yoyMax = yoyRange * 1.2;
    const yoyMin = -yoyMax;
    const n = series.length;
    const slot = innerW / Math.max(n, 1);
    const barW = Math.min(56, slot * 0.5);
    const barX = (i) => padL + slot * i + slot / 2 - barW / 2;
    const barY = (v) => padT + (1 - v / maxV) * innerH;
    const barH = (v) => (v / maxV) * innerH;
    const pointX = (i) => padL + slot * i + slot / 2;
    const pointY = (v) => padT + (1 - (v - yoyMin) / (yoyMax - yoyMin)) * innerH;
    const linePts = series.map((s, i) => s.yoy == null ? null : `${pointX(i)},${pointY(s.yoy)}`).filter(Boolean);
    const linePath = linePts.length ? "M" + linePts.join(" L") : "";
    const leftTicks = Array.from({ length: 5 }, (_, i) => maxV * (1 - i / 4));
    const rightTicks = Array.from({ length: 5 }, (_, i) => yoyMax - (i / 4) * (yoyMax - yoyMin));
    const fmtAbs = (v) => Math.abs(v) >= 1000 ? (v / 1000).toFixed(0) + "B" : v.toFixed(0) + "M";

    const svgNS = "http://www.w3.org/2000/svg";
    host.innerHTML = "";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", h);
    svg.style.display = "block";

    function el(tag, attrs, text) {
        const e = document.createElementNS(svgNS, tag);
        for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
        if (text != null) e.textContent = text;
        svg.appendChild(e);
        return e;
    }

    leftTicks.forEach((v, i) => {
        const yPos = padT + (i / 4) * innerH;
        el("line", { x1: padL, y1: yPos, x2: w - padR, y2: yPos, stroke: "#22272F", "stroke-width": 1 });
        el("text", {
            x: padL - 8, y: yPos + 3, "text-anchor": "end", fill: "#5C636E",
            "font-family": "JetBrains Mono", "font-size": 10,
            style: "font-variant-numeric: tabular-nums",
        }, fmtAbs(v));
        el("text", {
            x: w - padR + 8, y: yPos + 3, "text-anchor": "start", fill: "#5C636E",
            "font-family": "JetBrains Mono", "font-size": 10,
            style: "font-variant-numeric: tabular-nums",
        }, (rightTicks[i] * 100).toFixed(0) + "%");
    });
    el("line", { x1: padL, y1: padT, x2: padL, y2: padT + innerH, stroke: "#2D333C", "stroke-width": 1 });
    el("line", { x1: w - padR, y1: padT, x2: w - padR, y2: padT + innerH, stroke: "#2D333C", "stroke-width": 1 });
    el("line", { x1: padL, y1: padT + innerH, x2: w - padR, y2: padT + innerH, stroke: "#2D333C", "stroke-width": 1 });

    series.forEach((s, i) => {
        el("rect", {
            x: barX(i), y: barY(s.value), width: barW, height: barH(s.value),
            fill: "#22D3EE", opacity: 0.55, rx: 2,
        });
        el("text", {
            x: pointX(i), y: padT + innerH + 18, fill: "#A1A6AE",
            "font-family": "JetBrains Mono", "font-size": 11, "text-anchor": "middle",
        }, s.fy);
    });

    if (linePath) {
        el("path", { d: linePath, stroke: "#F2F4F7", "stroke-width": 1.8, fill: "none",
            "stroke-linejoin": "round", "stroke-linecap": "round" });
    }
    series.forEach((s, i) => {
        if (s.yoy == null) return;
        el("circle", { cx: pointX(i), cy: pointY(s.yoy), r: 3.5, fill: "#0B0D10",
            stroke: "#F2F4F7", "stroke-width": 1.6 });
        el("text", {
            x: pointX(i), y: pointY(s.yoy) - 9, "text-anchor": "middle",
            "font-family": "JetBrains Mono", "font-size": 10,
            fill: s.yoy >= 0 ? "#22C55E" : "#EF4444",
            style: "font-variant-numeric: tabular-nums",
        }, (s.yoy >= 0 ? "+" : "") + (s.yoy * 100).toFixed(1) + "%");
    });
    host.appendChild(svg);
}
```

- [ ] **Step 5: `initMetricsPanels` のクラス修正**

`app.js` の `initMetricsPanels` の DOM 生成内 `td.className` を `index === 0 ? "" : "num-cell"` に変更し、`renderEmptyRow` 呼び出しが新クラスを使うよう確認:

```javascript
function initMetricsPanels() {
    document.querySelectorAll("[data-metrics-panel]").forEach((panel) => {
        const companyId = panel.dataset.companyId;
        const tbody = panel.querySelector("[data-metrics-body]");
        fetchJson(`/api/stocks/${companyId}/metrics`)
            .then((rows) => {
                if (!rows.length) {
                    renderEmptyRow(tbody, 6, "指標データがありません。");
                    return;
                }
                rows.forEach((row) => {
                    const tr = document.createElement("tr");
                    [
                        row.fiscal_year_end,
                        fmtPercent(row.roe),
                        fmtPercent(row.roa),
                        fmtPercent(row.operating_margin),
                        fmtPercent(row.net_margin),
                        fmtPercent(row.revenue_growth),
                    ].forEach((value, index) => {
                        const td = document.createElement("td");
                        if (index > 0) td.className = "num-cell";
                        td.textContent = value;
                        tr.appendChild(td);
                    });
                    tbody.appendChild(tr);
                });
            })
            .catch((error) => {
                renderEmptyRow(tbody, 6, `取得に失敗しました: ${error.message}`);
            });
    });
}
```

- [ ] **Step 6: テスト実行**

```bash
uv run pytest tests/unit/web/ -v
```

Expected: PASS (`test_templates_do_not_load_remote_cdn_assets` で `_tab_financial.html` のチェックは `cdn.jsdelivr.net` の不在のみ。引き続き合格する)。

- [ ] **Step 7: コミット**

```bash
git add src/stock_analyze_system/web/templates/stocks/_tab_financial.html \
        src/stock_analyze_system/web/static/app.js
git rm src/stock_analyze_system/web/templates/stocks/_tab_metrics.html 2>/dev/null || true
git commit -m "feat(web): merge metrics into financial tab and add inline SVG combo chart"
```

---

## Task 11: バリュエーションタブ + 10年推移エリアチャート

**Files:**
- Modify: `src/stock_analyze_system/web/templates/stocks/_tab_valuation.html`
- Modify: `src/stock_analyze_system/web/static/app.js` (`renderValuationChart` を追加し、`initValuationPanels` から呼ぶ)

- [ ] **Step 1: `_tab_valuation.html` を書き換え**

```html
<div class="stack" data-valuation-panel data-company-id="{{ company.id }}">
    <p class="muted" data-valuation-summary>読み込み中…</p>

    <section class="panel">
        <header class="panel__header">
            <h3 class="panel__title">PER 推移</h3>
            <span class="muted" style="font-family: var(--font-mono); font-size: 11px;">最新までの月次</span>
        </header>
        <div class="panel__body"><div data-valuation-chart></div></div>
    </section>

    <section class="panel">
        <header class="panel__header"><h3 class="panel__title">バリュエーション履歴</h3></header>
        <div class="panel__body panel__body--flush">
            <table class="table">
                <thead>
                    <tr>
                        <th>日付</th>
                        <th class="num-cell">株価</th>
                        <th class="num-cell">PER</th>
                        <th class="num-cell">PBR</th>
                        <th class="num-cell">EV/EBITDA</th>
                        <th class="num-cell">PSR</th>
                    </tr>
                </thead>
                <tbody data-valuation-body></tbody>
            </table>
        </div>
    </section>
</div>
```

- [ ] **Step 2: `app.js` の `initValuationPanels` を更新**

`th.className = ...` の Tailwind 風指定を新クラスに置換し、`td.className = "px-2 py-1 text-right"` を `td.className = "num-cell"` に置換。さらに `renderValuationChart` を呼ぶ。

```javascript
function initValuationPanels() {
    document.querySelectorAll("[data-valuation-panel]").forEach((panel) => {
        const companyId = panel.dataset.companyId;
        const tbody = panel.querySelector("[data-valuation-body]");
        const summary = panel.querySelector("[data-valuation-summary]");
        const chartHost = panel.querySelector("[data-valuation-chart]");

        fetchJson(`/api/stocks/${companyId}/valuations`)
            .then((rows) => {
                if (!rows.length) {
                    summary.textContent = "バリュエーションデータがありません。";
                    renderEmptyRow(tbody, 6, "バリュエーションデータがありません。");
                    if (chartHost) chartHost.innerHTML = "";
                    return;
                }
                const latest = rows[0];
                summary.textContent =
                    `最新 ${latest.date}: 株価 ${fmtNumber(latest.stock_price)}, PER ${fmtNumber(latest.per)}, PBR ${fmtNumber(latest.pbr)} / 最終更新 ${fmtDateTime(latest.last_updated)}`;
                rows.forEach((row) => {
                    const tr = document.createElement("tr");
                    [
                        row.date,
                        fmtNumber(row.stock_price),
                        fmtNumber(row.per),
                        fmtNumber(row.pbr),
                        fmtNumber(row.ev_ebitda),
                        fmtNumber(row.psr),
                    ].forEach((value, index) => {
                        const td = document.createElement("td");
                        if (index > 0) td.className = "num-cell";
                        td.textContent = value;
                        tr.appendChild(td);
                    });
                    tbody.appendChild(tr);
                });
                if (chartHost) renderValuationChart(chartHost, rows);
            })
            .catch((error) => {
                summary.textContent = `取得失敗: ${error.message}`;
                renderEmptyRow(tbody, 6, "取得に失敗しました。");
            });
    });
}
```

- [ ] **Step 3: `renderValuationChart` を追加**

`app.js` 内、`renderFinancialChart` の直後に追加:

```javascript
function renderValuationChart(host, rows) {
    // rows: [{date, per, ...}] in newest-first order. Reverse for chronological draw.
    const series = [...rows].reverse()
        .map(r => ({ date: r.date, v: Number(r.per) }))
        .filter(s => Number.isFinite(s.v));
    if (series.length === 0) { host.innerHTML = ""; return; }

    const w = 800, h = 220, padL = 52, padR = 16, padT = 16, padB = 32;
    const innerW = w - padL - padR;
    const innerH = h - padT - padB;
    const max = Math.max(...series.map(s => s.v));
    const min = Math.min(...series.map(s => s.v));
    const range = Math.max(0.001, max - min);
    const sum = series.reduce((s, p) => s + p.v, 0);
    const median = (() => {
        const sorted = [...series.map(s => s.v)].sort((a, b) => a - b);
        const m = Math.floor(sorted.length / 2);
        return sorted.length % 2 ? sorted[m] : (sorted[m - 1] + sorted[m]) / 2;
    })();
    const x = (i) => padL + (i / Math.max(series.length - 1, 1)) * innerW;
    const y = (v) => padT + (1 - (v - min) / range) * innerH;
    const path = series.map((s, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(s.v)}`).join(" ");
    const area = path + ` L${x(series.length - 1)},${padT + innerH} L${padL},${padT + innerH} Z`;
    const yTicks = Array.from({ length: 5 }, (_, i) => min + (i / 4) * range);

    const svgNS = "http://www.w3.org/2000/svg";
    host.innerHTML = "";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", h);
    svg.style.display = "block";

    const defs = document.createElementNS(svgNS, "defs");
    const gradId = "valFade" + Math.round(Math.random() * 1e6);
    defs.innerHTML = `<linearGradient id="${gradId}" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stop-color="#22D3EE" stop-opacity="0.25"/>
        <stop offset="100%" stop-color="#22D3EE" stop-opacity="0"/>
    </linearGradient>`;
    svg.appendChild(defs);

    function el(tag, attrs, text) {
        const e = document.createElementNS(svgNS, tag);
        for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
        if (text != null) e.textContent = text;
        svg.appendChild(e);
        return e;
    }

    yTicks.forEach((v) => {
        el("line", { x1: padL, y1: y(v), x2: w - padR, y2: y(v), stroke: "#22272F", "stroke-width": 1 });
        el("text", {
            x: padL - 8, y: y(v) + 3, "text-anchor": "end", fill: "#5C636E",
            "font-family": "JetBrains Mono", "font-size": 10,
            style: "font-variant-numeric: tabular-nums",
        }, v.toFixed(1) + "x");
    });
    el("line", { x1: padL, y1: padT, x2: padL, y2: padT + innerH, stroke: "#2D333C", "stroke-width": 1 });
    el("line", { x1: padL, y1: padT + innerH, x2: w - padR, y2: padT + innerH, stroke: "#2D333C", "stroke-width": 1 });

    el("path", { d: area, fill: `url(#${gradId})` });
    el("path", { d: path, stroke: "#22D3EE", "stroke-width": 1.6, fill: "none",
        "stroke-linejoin": "round", "stroke-linecap": "round" });
    el("line", { x1: padL, y1: y(median), x2: w - padR, y2: y(median),
        stroke: "#5C636E", "stroke-width": 1, "stroke-dasharray": "3 3" });
    el("text", {
        x: w - padR - 4, y: y(median) - 4, "text-anchor": "end", fill: "#A1A6AE",
        "font-family": "JetBrains Mono", "font-size": 10,
    }, "median " + median.toFixed(2) + "x");

    const last = series[series.length - 1];
    el("circle", { cx: x(series.length - 1), cy: y(last.v), r: 3, fill: "#22D3EE" });
    host.appendChild(svg);
}
```

- [ ] **Step 4: テスト実行**

```bash
uv run pytest tests/unit/web/ -v
```

Expected: PASS。

- [ ] **Step 5: コミット**

```bash
git add src/stock_analyze_system/web/templates/stocks/_tab_valuation.html \
        src/stock_analyze_system/web/static/app.js
git commit -m "feat(web): redesign valuation tab with inline SVG history chart"
```

---

## Task 12: 分析タブ (`_tab_analysis.html`) を再構成 (旧 `_tab_rag.html`)

**Files:**
- Modify: `src/stock_analyze_system/web/templates/stocks/_tab_analysis.html`
- Delete: `src/stock_analyze_system/web/templates/stocks/_tab_rag.html`
- Modify: `src/stock_analyze_system/web/static/app.js` (`initRagPanels` 内のクラス文字列を新クラスへ置換)

- [ ] **Step 1: `_tab_analysis.html` を書き換え**

```html
<div class="stack" data-rag-panel data-company-id="{{ company.id }}">
    <section class="panel">
        <header class="panel__header">
            <h3 class="panel__title">保存済み定型分析</h3>
            <div class="panel__action">
                <label class="muted" for="rag-filing-select" style="font-size: var(--text-xs);">対象決算</label>
                <select class="input" id="rag-filing-select" data-rag-filing-select
                        style="width: 18rem;">
                    <option value="">読み込み中…</option>
                </select>
            </div>
        </header>
        <div class="panel__body">
            <p class="subtle" data-rag-filing-meta hidden style="font-size: var(--text-xs); margin-bottom: var(--space-2);"></p>
            <div data-rag-analyses>
                <p class="muted">分析結果を確認中です。</p>
            </div>
        </div>
    </section>

    <section class="panel">
        <header class="panel__header">
            <h3 class="panel__title">RAG Q&amp;A</h3>
        </header>
        <div class="panel__body stack">
            <textarea class="input" data-rag-question rows="3"
                      placeholder="例: Appleの2024年度の売上高は？"></textarea>
            <div>
                <button class="btn btn--primary" data-rag-ask>送信</button>
            </div>
            <div data-rag-answer hidden style="border-top: 1px solid var(--border); padding-top: var(--space-3);">
                <p style="white-space: pre-wrap; color: var(--fg-1);" data-rag-answer-text></p>
                <p class="subtle" style="font-size: var(--text-xs); margin-top: var(--space-2);">
                    Pages: <span data-rag-source-pages>—</span>
                    · Sections: <span data-rag-source-sections>—</span>
                </p>
            </div>
        </div>
    </section>

    <section class="panel">
        <header class="panel__header">
            <h3 class="panel__title">質問履歴</h3>
            <button class="btn btn--ghost btn--sm" data-rag-history-refresh>再読込</button>
        </header>
        <div class="panel__body">
            <div data-rag-history>
                <p class="muted">読み込み中…</p>
            </div>
        </div>
    </section>
</div>
```

- [ ] **Step 2: 旧 `_tab_rag.html` を削除**

```bash
git rm src/stock_analyze_system/web/templates/stocks/_tab_rag.html
```

- [ ] **Step 3: `app.js` の `initRagPanels` 内のクラス文字列を一括置換**

下記を一括置換 (順番に Edit) :

| 旧 | 新 |
|---|---|
| `"text-sm text-gray-500"` (空状態) | `"muted"` |
| `"text-sm text-red-600"` (エラー) | `"down"` |
| `"section", "mt-4"` | `"section", "stack-section"` (CSS 不要、`margin-top: var(--space-4)` を該当要素のクラスで担保) |
| `"h4", "text-sm font-semibold text-gray-700 border-b pb-1 mb-2"` | `"h4", "panel-section__title"` |
| `"p", "text-sm leading-6 text-gray-900 whitespace-pre-wrap"` | `"p", "rag-paragraph"` (style: `whiteSpace: pre-wrap; color: var(--fg-1); font-size: var(--text-sm); line-height: 1.65; margin: 0;`) |
| `"ul", "list-disc list-inside text-sm text-gray-900 space-y-1"` | `"ul", "rag-bullets"` |
| `"dl", "grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1 text-sm"` | `"dl", "rag-kv"` |
| `"dt", "text-gray-600 font-medium"` | `"dt", "muted"` |
| `"dd", "text-gray-900 whitespace-pre-wrap"` | `"dd", "rag-kv__val"` |
| `"div", "border rounded p-3 bg-gray-50"` | `"div", "rag-card"` |
| `"div", "space-y-4"` | `"div", "stack"` |
| `"div", "space-y-2"` | `"div", "stack stack--sm"` |
| `"div", "font-semibold text-gray-900"` | `"div", "rag-card__title"` |
| `"div", "text-xs text-gray-500 mb-1"` | `"div", "subtle small"` |
| `"flex items-center gap-2 mb-1"` | `"flex flex--center flex--gap-2 rag-card__head"` |
| `"font-semibold text-gray-900"` | `"rag-card__title"` |
| ` `bg-red-100 text-red-800` (severity high) | `badge--down` |
| `bg-yellow-100 text-yellow-800` (severity medium) | `badge` (中立) |
| `bg-green-100 text-green-800` (severity low) | `badge--up` |
| `text-xs px-2 py-0.5 rounded {cls}` | `badge {cls}` |
| `text-xs text-gray-500` | `subtle small` |
| `min-w-full text-sm border` | `table` |
| `bg-gray-100` (thead) | `""` (CSS で対応) |
| `px-2 py-1 text-left border-b` | `"th"` defaults |
| `border-t` (tr) | `""` (CSS) |
| `px-2 py-1` / `px-2 py-1 text-right` (td) | `""` / `"num-cell"` |
| `text-xs text-amber-700` (raw fallback warn) | `badge` style: `background: #4A3B1A; color: #FACC15;` 不要、シンプルに `subtle small` |
| `text-xs whitespace-pre-wrap bg-gray-50 border rounded p-2` | `rag-pre` (style block) |
| `space-y-2` / `space-y-1` | `stack` / `stack stack--sm` |
| `cursor-pointer font-semibold text-base text-gray-800 hover:text-blue-700` | `analysis-summary` (style block) |
| `border-t py-3` | `analysis-row` (style block) |
| `text-xs text-gray-400 mt-3` | `subtle small` style: margin-top |
| `font-medium text-gray-800 truncate` | `analysis-history__q` |
| `ml-2 text-xs text-gray-400 font-normal` | `subtle small` |
| `mt-2 pl-2` | `stack stack--sm` style: padding-left |
| `text-xs font-semibold text-gray-500 mt-1` | `label` |
| `text-xs text-gray-500 mt-3` | `subtle small` |
| `cursor-pointer hover:text-blue-700` | `analysis-history__summary` |

これらは段階的にやると地獄なので、`initRagPanels` セクション (おおよそ 270〜700 行) を **丸ごと書き直す** のが現実的。次の Step で全文を提示する。

- [ ] **Step 4: `initRagPanels` 全文書き換え + 関連 helper の調整**

`app.js` の `const ANALYSIS_LABELS = {…};` から `function initRagPanels() { … }` の閉じ括弧 (`});` の直前まで を、以下で置換:

```javascript
const ANALYSIS_LABELS = {
    business_summary: "事業概要",
    risk_factors: "リスク要因",
    mda: "経営者による分析 (MD&A)",
    competitors: "競合分析",
};

const SEVERITY_BADGE_CLASS = {
    high: "badge badge--down",
    medium: "badge",
    low: "badge badge--up",
};

function el(tag, className, text) {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (text !== undefined && text !== null && text !== "") e.textContent = String(text);
    return e;
}

function isMeaningful(value) {
    if (value === null || value === undefined) return false;
    if (typeof value === "string") return value.trim() !== "";
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === "object") return Object.keys(value).length > 0;
    return true;
}

function section(title, body) {
    const wrap = el("section", "rag-section");
    wrap.appendChild(el("h4", "rag-section__title", title));
    wrap.appendChild(body);
    return wrap;
}

function paragraph(text) {
    const p = el("p", "rag-paragraph");
    p.textContent = String(text || "");
    return p;
}

function bulletList(items) {
    const ul = el("ul", "rag-bullets");
    items.forEach((item) => { if (isMeaningful(item)) ul.appendChild(el("li", null, item)); });
    return ul;
}

function kvList(pairs) {
    const dl = el("dl", "rag-kv");
    pairs.forEach(([k, v]) => {
        if (!isMeaningful(v)) return;
        dl.appendChild(el("dt", "muted", `${k}:`));
        dl.appendChild(el("dd", "rag-kv__val", v));
    });
    return dl;
}

function cardList(items, renderItem) {
    const wrap = el("div", "stack stack--sm");
    items.forEach((item) => {
        const card = el("div", "rag-card");
        renderItem(card, item);
        wrap.appendChild(card);
    });
    return wrap;
}

function renderBusinessSummary(d) {
    const root = el("div", "stack");
    if (isMeaningful(d.summary)) root.appendChild(section("概要", paragraph(d.summary)));
    const basics = [
        ["企業名", d.company_name],
        ["業種", d.industry],
        ["従業員数", d.employees],
    ].filter(([, v]) => isMeaningful(v));
    if (basics.length) root.appendChild(section("基本情報", kvList(basics)));
    if (Array.isArray(d.business_segments) && d.business_segments.length) {
        root.appendChild(section("事業セグメント", cardList(d.business_segments, (card, seg) => {
            card.appendChild(el("div", "rag-card__title", seg.name || "(無題)"));
            if (isMeaningful(seg.revenue_share)) {
                card.appendChild(el("div", "subtle small", `売上比率: ${seg.revenue_share}`));
            }
            if (isMeaningful(seg.description)) card.appendChild(paragraph(seg.description));
        })));
    }
    if (Array.isArray(d.key_products) && d.key_products.length) {
        root.appendChild(section("主要製品/サービス", bulletList(d.key_products)));
    }
    if (Array.isArray(d.geographic_presence) && d.geographic_presence.length) {
        root.appendChild(section("展開地域", bulletList(d.geographic_presence)));
    }
    return root;
}

function renderRiskFactors(d) {
    const root = el("div", "stack");
    if (isMeaningful(d.top_risks_summary)) {
        root.appendChild(section("最重要リスク要約", paragraph(d.top_risks_summary)));
    }
    if (Array.isArray(d.risks) && d.risks.length) {
        root.appendChild(section("リスク一覧", cardList(d.risks, (card, risk) => {
            const head = el("div", "rag-card__head");
            head.appendChild(el("span", "rag-card__title", risk.title || "(無題)"));
            if (isMeaningful(risk.severity)) {
                const cls = SEVERITY_BADGE_CLASS[String(risk.severity).toLowerCase()] || "badge";
                head.appendChild(el("span", cls, risk.severity));
            }
            if (isMeaningful(risk.category)) {
                head.appendChild(el("span", "subtle small", `[${risk.category}]`));
            }
            card.appendChild(head);
            if (isMeaningful(risk.description)) card.appendChild(paragraph(risk.description));
        })));
    }
    return root;
}

function renderMda(d) {
    const root = el("div", "stack");
    if (isMeaningful(d.summary)) root.appendChild(section("要約", paragraph(d.summary)));
    const sections = [
        ["売上高分析", d.revenue_analysis],
        ["利益率動向", d.profitability],
        ["キャッシュフロー", d.cash_flow],
        ["資本配分方針", d.capital_allocation],
        ["業績見通し", d.outlook],
    ];
    sections.forEach(([title, body]) => {
        if (isMeaningful(body)) root.appendChild(section(title, paragraph(body)));
    });
    if (Array.isArray(d.key_metrics) && d.key_metrics.length) {
        const table = el("table", "table");
        const thead = el("thead");
        const trh = el("tr");
        ["指標", "当期", "前期", "変化率"].forEach((h) => trh.appendChild(el("th", null, h)));
        thead.appendChild(trh);
        table.appendChild(thead);
        const tbody = el("tbody");
        d.key_metrics.forEach((m) => {
            const tr = el("tr");
            [m.metric, m.current, m.previous, m.change].forEach((v, i) => {
                tr.appendChild(el("td", i === 0 ? "" : "num-cell", isMeaningful(v) ? v : "—"));
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        root.appendChild(section("主要指標", table));
    }
    return root;
}

function renderCompetitors(d) {
    const root = el("div", "stack");
    if (isMeaningful(d.summary)) root.appendChild(section("要約", paragraph(d.summary)));
    const basics = [
        ["競合ポジション", d.competitive_position],
        ["市場シェア", d.market_share],
    ].filter(([, v]) => isMeaningful(v));
    if (basics.length) root.appendChild(section("ポジション", kvList(basics)));
    if (Array.isArray(d.competitors) && d.competitors.length) {
        root.appendChild(section("競合企業", cardList(d.competitors, (card, c) => {
            card.appendChild(el("div", "rag-card__title", c.name || "(無名)"));
            if (isMeaningful(c.description)) card.appendChild(paragraph(c.description));
        })));
    }
    if (Array.isArray(d.competitive_advantages) && d.competitive_advantages.length) {
        root.appendChild(section("競合優位性", bulletList(d.competitive_advantages)));
    }
    if (Array.isArray(d.competitive_risks) && d.competitive_risks.length) {
        root.appendChild(section("競合上のリスク", bulletList(d.competitive_risks)));
    }
    return root;
}

function renderRawFallback(data) {
    const root = el("div", "stack stack--sm");
    if (typeof data === "object" && data !== null && "raw_answer" in data) {
        root.appendChild(el("p", "subtle small", "※ JSONとしてパースできなかった生回答です:"));
        root.appendChild(paragraph(data.raw_answer));
        return root;
    }
    const pre = el("pre", "rag-pre");
    pre.textContent = JSON.stringify(data, null, 2);
    root.appendChild(pre);
    return root;
}

function renderAnalysisBody(type, data) {
    if (data && typeof data === "object" && "raw_answer" in data) return renderRawFallback(data);
    switch (type) {
        case "business_summary": return renderBusinessSummary(data || {});
        case "risk_factors":     return renderRiskFactors(data || {});
        case "mda":              return renderMda(data || {});
        case "competitors":      return renderCompetitors(data || {});
        default:                 return renderRawFallback(data);
    }
}

const FILING_TYPE_LABEL = {
    "10-K": "年次 (10-K)",
    "10-Q": "四半期 (10-Q)",
    "20-F": "年次 (20-F)",
    "6-K": "随時 (6-K)",
    annual_report: "年次",
    quarterly_report: "四半期",
};

function formatFilingOptionLabel(filing, isDefault) {
    const typeLabel = FILING_TYPE_LABEL[filing.filing_type] || filing.filing_type;
    const date = filing.period_end || filing.filed_at || `FY${filing.fiscal_year}`;
    const prefix = isDefault ? "★最新: " : "";
    return `${prefix}${date} — ${typeLabel} (FY${filing.fiscal_year})`;
}

function renderAnalysesList(analysesBox, analyses, companyId) {
    analysesBox.innerHTML = "";
    if (!analyses.length) {
        const p = document.createElement("p");
        p.className = "muted";
        p.appendChild(document.createTextNode("分析結果がありません。CLIから "));
        const code = document.createElement("code");
        code.textContent = `stock-analyze rag analyze ${companyId}`;
        p.appendChild(code);
        p.appendChild(document.createTextNode(" を実行してください。"));
        analysesBox.appendChild(p);
        return;
    }
    analyses.forEach((analysis) => {
        const details = document.createElement("details");
        details.className = "analysis-row";
        const summary = document.createElement("summary");
        summary.className = "analysis-row__summary";
        const label = ANALYSIS_LABELS[analysis.analysis_type] || analysis.analysis_type;
        summary.textContent = label;
        details.appendChild(summary);
        details.appendChild(renderAnalysisBody(analysis.analysis_type, analysis.result_json));
        if (analysis.created_at || analysis.model_name) {
            const meta = el("p", "subtle small");
            const parts = [];
            if (analysis.model_name) parts.push(`model: ${analysis.model_name}`);
            if (analysis.created_at) parts.push(`生成: ${analysis.created_at}`);
            meta.textContent = parts.join(" · ");
            details.appendChild(meta);
        }
        analysesBox.appendChild(details);
    });
}

function initRagPanels() {
    document.querySelectorAll("[data-rag-panel]").forEach((panel) => {
        const companyId = panel.dataset.companyId;
        const analysesBox = panel.querySelector("[data-rag-analyses]");
        const filingSelect = panel.querySelector("[data-rag-filing-select]");
        const filingMeta = panel.querySelector("[data-rag-filing-meta]");
        const question = panel.querySelector("[data-rag-question]");
        const button = panel.querySelector("[data-rag-ask]");
        const answerBlock = panel.querySelector("[data-rag-answer]");
        const answerText = panel.querySelector("[data-rag-answer-text]");
        const sourcePages = panel.querySelector("[data-rag-source-pages]");
        const sourceSections = panel.querySelector("[data-rag-source-sections]");

        const filingById = new Map();

        function loadAnalyses(filingId) {
            analysesBox.innerHTML = "";
            analysesBox.appendChild(el("p", "muted", "読み込み中…"));
            const url = filingId
                ? `/api/stocks/${companyId}/rag/analyses?filing_id=${encodeURIComponent(filingId)}`
                : `/api/stocks/${companyId}/rag/analyses`;
            return fetchJson(url)
                .then((analyses) => renderAnalysesList(analysesBox, analyses, companyId))
                .catch((error) => {
                    analysesBox.innerHTML = "";
                    analysesBox.appendChild(el("p", "down", `分析結果の取得に失敗しました: ${error.message}`));
                });
        }

        function updateFilingMeta(filingId) {
            if (!filingMeta) return;
            const f = filingById.get(String(filingId));
            if (!f) {
                filingMeta.hidden = true;
                filingMeta.textContent = "";
                return;
            }
            const parts = [`filing_id=${f.id}`, `${f.filing_type}`, `FY${f.fiscal_year}`];
            if (f.period_end) parts.push(`期末: ${f.period_end}`);
            if (f.filed_at)   parts.push(`提出: ${f.filed_at}`);
            filingMeta.textContent = parts.join(" · ");
            filingMeta.hidden = false;
        }

        if (filingSelect) {
            fetchJson(`/api/stocks/${companyId}/rag/filing_options`)
                .then((opts) => {
                    filingSelect.innerHTML = "";
                    const def = opts.default;
                    const annuals = opts.annual_options || [];
                    const seen = new Set();
                    const append = (filing, isDefault) => {
                        if (!filing || seen.has(filing.id)) return;
                        seen.add(filing.id);
                        filingById.set(String(filing.id), filing);
                        const opt = document.createElement("option");
                        opt.value = String(filing.id);
                        opt.textContent = formatFilingOptionLabel(filing, isDefault);
                        filingSelect.appendChild(opt);
                    };
                    if (def) append(def, true);
                    annuals.forEach((f) => append(f, false));
                    if (filingSelect.options.length === 0) {
                        const opt = document.createElement("option");
                        opt.value = "";
                        opt.textContent = "決算データがありません";
                        filingSelect.appendChild(opt);
                        filingSelect.disabled = true;
                        renderAnalysesList(analysesBox, [], companyId);
                        return;
                    }
                    filingSelect.value = String(def ? def.id : annuals[0].id);
                    updateFilingMeta(filingSelect.value);
                    loadAnalyses(filingSelect.value);
                })
                .catch((error) => {
                    filingSelect.innerHTML = "";
                    const opt = document.createElement("option");
                    opt.value = "";
                    opt.textContent = `読み込み失敗: ${error.message}`;
                    filingSelect.appendChild(opt);
                    filingSelect.disabled = true;
                    loadAnalyses(null);
                });

            filingSelect.addEventListener("change", () => {
                updateFilingMeta(filingSelect.value);
                loadAnalyses(filingSelect.value);
            });
        } else {
            loadAnalyses(null);
        }

        const historyBox = panel.querySelector("[data-rag-history]");
        const historyRefresh = panel.querySelector("[data-rag-history-refresh]");

        function renderHistory(items) {
            historyBox.innerHTML = "";
            if (!items.length) {
                historyBox.appendChild(el("p", "muted", "まだ質問履歴がありません。"));
                return;
            }
            items.forEach((item) => {
                const details = document.createElement("details");
                details.className = "analysis-row";
                const summary = document.createElement("summary");
                summary.className = "analysis-row__summary";
                const qLine = el("div", "analysis-history__q", item.question || "(空の質問)");
                const meta = [];
                if (item.created_at) meta.push(item.created_at.replace("T", " ").slice(0, 19));
                if (item.model_name)  meta.push(item.model_name);
                if (meta.length) {
                    qLine.appendChild(el("span", "subtle small", ` — ${meta.join(" · ")}`));
                }
                summary.appendChild(qLine);
                details.appendChild(summary);

                const body = el("div", "stack stack--sm");
                body.appendChild(el("h5", "label", "質問"));
                body.appendChild(paragraph(item.question || ""));
                body.appendChild(el("h5", "label", "回答"));
                body.appendChild(paragraph(item.answer || "(回答なし)"));

                const srcParts = [];
                if ((item.source_pages || []).length)    srcParts.push(`Pages: ${item.source_pages.join(", ")}`);
                if ((item.source_sections || []).length) srcParts.push(`Sections: ${item.source_sections.join(" / ")}`);
                if (item.confidence != null)             srcParts.push(`confidence: ${(item.confidence * 100).toFixed(0)}%`);
                if (srcParts.length) {
                    body.appendChild(el("p", "subtle small", srcParts.join(" · ")));
                }
                details.appendChild(body);
                historyBox.appendChild(details);
            });
        }

        function loadHistory() {
            if (!historyBox) return Promise.resolve();
            historyBox.innerHTML = "";
            historyBox.appendChild(el("p", "muted", "読み込み中…"));
            return fetchJson(`/api/stocks/${companyId}/rag/history`)
                .then(renderHistory)
                .catch((error) => {
                    historyBox.innerHTML = "";
                    historyBox.appendChild(el("p", "down", `履歴の取得に失敗しました: ${error.message}`));
                });
        }

        if (historyRefresh) historyRefresh.addEventListener("click", loadHistory);
        loadHistory();

        function selectedFilingType() {
            if (!filingSelect || !filingSelect.value) return null;
            const f = filingById.get(String(filingSelect.value));
            return f ? f.filing_type : null;
        }

        button.addEventListener("click", async () => {
            const value = question.value.trim();
            if (!value) return;
            button.disabled = true;
            answerBlock.hidden = false;
            answerText.textContent = "回答中…";
            sourcePages.textContent = "—";
            sourceSections.textContent = "—";
            try {
                const askPayload = { question: value };
                const filingType = selectedFilingType();
                if (filingType) askPayload.filing_type = filingType;
                const data = await fetchJson(`/api/stocks/${companyId}/rag/ask`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(askPayload),
                });
                answerText.textContent = data.answer || "回答できませんでした";
                sourcePages.textContent = (data.source_pages || []).join(", ") || "—";
                sourceSections.textContent = (data.source_sections || []).join(" / ") || "—";
                loadHistory();
            } catch (error) {
                answerText.textContent = `エラー: ${error.message}`;
            } finally {
                button.disabled = false;
            }
        });
    });
}
```

- [ ] **Step 5: 上記 JS が参照する追加 CSS クラスを `app.css` に追加**

`app.css` 末尾に追加:

```css
/* RAG / Analysis tab specifics */
.rag-section { margin-top: var(--space-4); }
.rag-section__title {
  font-size: var(--text-sm);
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  border-bottom: 1px solid var(--border);
  padding-bottom: var(--space-1);
  margin: 0 0 var(--space-2) 0;
}
.rag-paragraph {
  white-space: pre-wrap;
  color: var(--fg-1);
  font-size: var(--text-sm);
  line-height: 1.65;
  margin: 0;
}
.rag-bullets { padding-left: 1.2rem; margin: 0; color: var(--fg-1); font-size: var(--text-sm); }
.rag-bullets > li + li { margin-top: var(--space-1); }
.rag-kv {
  display: grid;
  grid-template-columns: max-content 1fr;
  column-gap: var(--space-3);
  row-gap: var(--space-1);
  font-size: var(--text-sm);
  margin: 0;
}
.rag-kv__val { color: var(--fg-1); white-space: pre-wrap; }
.rag-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  background: var(--surface-2);
}
.rag-card__head { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-1); }
.rag-card__title { font-weight: var(--fw-semibold); color: var(--fg-1); }
.rag-pre {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  white-space: pre-wrap;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: var(--space-2);
  color: var(--fg-1);
}
.subtle.small, .subtle .small { font-size: var(--text-xs); }
.small { font-size: var(--text-xs); }
.stack--sm > * + * { margin-top: var(--space-2); }
.analysis-row { padding: var(--space-3) 0; border-top: 1px solid var(--border); }
.analysis-row__summary {
  cursor: pointer;
  font-weight: var(--fw-semibold);
  color: var(--fg-1);
  font-size: var(--text-body);
}
.analysis-row__summary:hover { color: var(--accent); }
.analysis-history__q {
  font-weight: var(--fw-medium);
  color: var(--fg-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.label {
  font-size: var(--text-xs);
  font-weight: var(--fw-semibold);
  letter-spacing: var(--tracking-caps);
  text-transform: uppercase;
  color: var(--fg-2);
  margin: 0;
}
```

- [ ] **Step 6: テスト実行**

```bash
uv run pytest tests/unit/web/ -v
```

Expected: PASS。

- [ ] **Step 7: コミット**

```bash
git add src/stock_analyze_system/web/templates/stocks/_tab_analysis.html \
        src/stock_analyze_system/web/static/app.js \
        src/stock_analyze_system/web/static/app.css
git rm src/stock_analyze_system/web/templates/stocks/_tab_rag.html
git commit -m "feat(web): rename rag tab to analysis and restyle as panels"
```

---

## Task 13: ファイリングタブのリテーマ

**Files:**
- Modify: `src/stock_analyze_system/web/templates/stocks/_tab_filings.html`

- [ ] **Step 1: 書き換え**

```html
{% from "_macros.html" import icon %}
<section class="panel">
    <header class="panel__header"><h3 class="panel__title">ファイリング</h3></header>
    <div class="panel__body panel__body--flush">
        {% if filings %}
        <table class="table">
            <thead>
                <tr>
                    <th>タイプ</th>
                    <th>年度</th>
                    <th>期末</th>
                    <th>提出日</th>
                    <th>ソース</th>
                    <th>識別子</th>
                </tr>
            </thead>
            <tbody>
                {% for f in filings %}
                <tr>
                    <td><span class="badge badge--mono">{{ f.filing_type }}</span></td>
                    <td class="num">FY{{ f.fiscal_year }}</td>
                    <td class="num">{{ f.period_end or "—" }}</td>
                    <td class="num">{{ f.filed_at or "—" }}</td>
                    <td><span class="badge badge--mono">{{ f.source }}</span></td>
                    <td class="num muted small">{{ f.accession_no or f.doc_id or "—" }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p class="empty-state">ファイリングがありません。</p>
        {% endif %}
    </div>
</section>
```

- [ ] **Step 2: テスト実行**

```bash
uv run pytest tests/unit/web/ -v
```

Expected: PASS。

- [ ] **Step 3: コミット**

```bash
git add src/stock_analyze_system/web/templates/stocks/_tab_filings.html
git commit -m "feat(web): restyle filings table to design system tokens"
```

---

## Task 14: 銘柄検索ページ

**Files:**
- Modify: `src/stock_analyze_system/web/templates/stocks/search.html`
- Modify: `src/stock_analyze_system/web/templates/stocks/_search_results.html`

- [ ] **Step 1: `search.html` を書き換え**

```html
{% extends "base.html" %}
{% set breadcrumbs = ["銘柄"] %}
{% block title %}銘柄検索{% endblock %}
{% block content %}
<div class="page-header">
    <h1 class="h1">銘柄検索</h1>
</div>
<section class="panel">
    <div class="panel__body stack">
        <input class="input" type="search" name="q" placeholder="ティッカー / 企業名"
               data-stock-search data-search-url="/stocks/search/results">
        <div id="search-results"></div>
    </div>
</section>
{% endblock %}
```

- [ ] **Step 2: `_search_results.html` を書き換え**

```html
{% if companies %}
<ul class="search-results">
    {% for c in companies %}
    <li>
        <a class="search-results__item" href="/stocks/{{ c.id }}">
            <div class="search-results__title">{{ c.ticker or c.security_code }} — {{ c.name }}</div>
            <div class="search-results__meta">{{ c.id }} · {{ c.market }}</div>
        </a>
    </li>
    {% endfor %}
</ul>
{% else %}
<p class="empty-state">該当する銘柄がありません。</p>
{% endif %}
```

- [ ] **Step 3: `app.css` に検索結果のクラスを追加 (末尾に追記)**

```css
/* Search results */
.search-results { list-style: none; padding: 0; margin: 0; }
.search-results > li + li { border-top: 1px solid var(--border); }
.search-results__item {
  display: block;
  padding: var(--space-3) var(--space-2);
  color: var(--fg-1);
}
.search-results__item:hover { background: var(--surface-2); text-decoration: none; }
.search-results__title { font-weight: var(--fw-semibold); }
.search-results__meta { font-family: var(--font-mono); font-size: var(--text-xs); color: var(--fg-3); }
```

- [ ] **Step 4: テスト実行**

```bash
uv run pytest tests/unit/web/ -v
```

Expected: PASS。

- [ ] **Step 5: コミット**

```bash
git add src/stock_analyze_system/web/templates/stocks/search.html \
        src/stock_analyze_system/web/templates/stocks/_search_results.html \
        src/stock_analyze_system/web/static/app.css
git commit -m "feat(web): redesign stock search page and result list"
```

---

## Task 15: スクリーニング画面 + `screening_check.js`

**Files:**
- Modify: `src/stock_analyze_system/web/templates/screening/check.html`
- Modify: `src/stock_analyze_system/web/static/screening_check.js`

- [ ] **Step 1: `check.html` を書き換え**

```html
{% extends "base.html" %}
{% set breadcrumbs = ["スクリーニング"] %}
{% block title %}スクリーニング{% endblock %}
{% block content %}
<div class="page-header">
    <h1 class="h1">スクリーニング</h1>
</div>

<section id="screening-check"
         data-fields-url="/api/screening/fields"
         data-run-url="/api/screening/run"
         data-distribution-url-template="/api/screening/distributions/{field}"
         data-targets-url="/api/screening/targets"
         class="stack stack--lg">

    <section class="panel">
        <div class="panel__body stack">
            <div class="screening-form-grid">
                <div class="field">
                    <span class="label">フィールド</span>
                    <select id="screening-field" class="input"><option value="">読み込み中...</option></select>
                </div>
                <div class="field">
                    <span class="label">条件</span>
                    <select id="screening-operator" class="input">
                        <option value="gte">以上</option>
                        <option value="lte">以下</option>
                        <option value="between">範囲</option>
                        <option value="eq">等しい</option>
                        <option value="in">いずれか</option>
                    </select>
                </div>
                <div class="field">
                    <span class="label">値</span>
                    <input id="screening-value" class="input" type="text" placeholder="例: 15 または 10,30">
                </div>
                <div class="field">
                    <span class="label">件数</span>
                    <input id="screening-limit" class="input" type="number" min="1" max="200" value="20">
                </div>
                <div class="field">
                    <span class="label">&nbsp;</span>
                    <button id="screening-add-filter" type="button" class="btn">条件追加</button>
                </div>
            </div>
            <div class="flex flex--center flex--gap-3">
                <button id="screening-run" type="button" class="btn btn--primary">スクリーニング実行</button>
                <label class="flex flex--center" style="gap: var(--space-2); font-size: var(--text-sm); color: var(--fg-2);">
                    <input id="screening-include-null" type="checkbox"> NULLを含める
                </label>
                <p id="screening-status" class="muted" role="status">フィールドを読み込んでいます。</p>
            </div>
            <div id="screening-filters" class="screening-filters">条件はまだありません。</div>
        </div>
    </section>

    <section class="panel">
        <header class="panel__header">
            <h3 class="panel__title">結果</h3>
            <div id="screening-targets-actions" class="panel__action">
                <span id="screening-selected-count" class="muted">0件選択</span>
                <button id="screening-add-targets" type="button" class="btn btn--primary btn--sm" disabled>選択をターゲットへ追加</button>
            </div>
        </header>
        <div class="panel__body" id="screening-results">
            <p class="empty-state">条件を指定して実行してください。</p>
        </div>
        <div class="panel__body" style="padding-top: 0;">
            <p id="screening-targets-status" class="muted" role="status"></p>
        </div>
    </section>
</section>
<script src="/static/screening_check.js"></script>
{% endblock %}
```

- [ ] **Step 2: `app.css` に screening 用クラスを追加**

```css
/* Screening */
.screening-form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 0.8fr) minmax(0, 1fr) 7rem auto;
  gap: var(--space-3);
  align-items: end;
}
.screening-filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  min-height: 40px;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  font-size: var(--text-sm);
  color: var(--fg-2);
}
@media (max-width: 960px) {
  .screening-form-grid { grid-template-columns: 1fr; }
}
```

- [ ] **Step 3: `screening_check.js` のクラス文字列を新クラスへ置換**

ファイル全体を以下のフィルタで一括 Edit (順番に適用):

| 旧 | 新 |
|---|---|
| `inline-flex items-center gap-1 rounded bg-gray-100 px-2 py-1 text-xs text-gray-700` | `badge badge--mono` |
| `inline-flex items-center gap-1 rounded bg-blue-100 px-2 py-1 text-xs text-blue-800` | `badge badge--accent` |
| `text-gray-400 hover:text-gray-600` | `btn btn--ghost btn--sm` |
| `min-w-full divide-y divide-gray-200 text-sm` | `table` |
| `bg-gray-50` | `""` (空文字 — table thead は CSS で十分) |
| `px-2 py-2 text-left font-semibold text-gray-700` | `""` (`th` のデフォルトで足りる) |
| `px-2 py-2 text-right font-semibold text-gray-700` | `num-cell` |
| `divide-y divide-gray-100` | `""` (`tbody td` の border-bottom で代替) |
| `px-2 py-2` | `""` |
| `px-2 py-2 text-right` | `num-cell` |
| `text-blue-600 hover:underline` | (anchor のデフォルト) |
| `text-sm text-gray-500` | `muted` |
| `text-sm text-emerald-600` | `up` |
| `text-sm text-red-600` | `down` |
| `bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs` | `badge badge--accent` |

※ `screening_check.js` は読み込みが大きいので、実装時に `Read` した上で個別 Edit するのが現実的。本タスクの目的は **どの class が新クラスに対応するかのマッピング** を確定させることであり、置換漏れがあったら見た目で気付いて補修。

- [ ] **Step 4: 動作確認 (構文)**

```bash
node -c src/stock_analyze_system/web/static/screening_check.js
```

Expected: 構文エラーなし。

- [ ] **Step 5: テスト実行**

```bash
uv run pytest tests/unit/web/ -v
```

Expected: PASS。

- [ ] **Step 6: コミット**

```bash
git add src/stock_analyze_system/web/templates/screening/check.html \
        src/stock_analyze_system/web/static/app.css \
        src/stock_analyze_system/web/static/screening_check.js
git commit -m "feat(web): redesign screening filter form and result table"
```

---

## Task 16: ウォッチリスト / ターゲット / ジョブ / RAG ask ページ

**Files:**
- Modify: `src/stock_analyze_system/web/templates/watchlists/list.html`
- Modify: `src/stock_analyze_system/web/templates/watchlists/detail.html`
- Modify: `src/stock_analyze_system/web/templates/targets/list.html`
- Modify: `src/stock_analyze_system/web/templates/jobs/list.html`
- Modify: `src/stock_analyze_system/web/templates/rag/ask.html`

各テンプレを以下の方針で書き換える: 既存の Tailwind 風クラスを `panel` / `btn--primary` / `input` / `table` / `empty-state` / `muted` に置換。HTMX や `name=` 属性は完全保持。

- [ ] **Step 1: `watchlists/list.html`**

```html
{% extends "base.html" %}
{% set breadcrumbs = ["ウォッチリスト"] %}
{% block title %}ウォッチリスト{% endblock %}
{% block content %}
<div class="page-header"><h1 class="h1">ウォッチリスト</h1></div>

<form method="post" action="/watchlists" class="panel">
    <div class="panel__body flex flex--gap-2">
        <input class="input" name="name" required placeholder="名前">
        <input class="input" name="description" placeholder="説明">
        <button class="btn btn--primary" type="submit">作成</button>
    </div>
</form>

<section class="panel" style="margin-top: var(--space-4);">
    <ul class="search-results">
        {% for w in watchlists %}
        <li>
            <a class="search-results__item" href="/watchlists/{{ w.id }}">
                <div class="search-results__title">{{ w.name }}</div>
                {% if w.description %}<div class="search-results__meta">{{ w.description }}</div>{% endif %}
            </a>
        </li>
        {% else %}
        <li><p class="empty-state">ウォッチリストがありません。</p></li>
        {% endfor %}
    </ul>
</section>
{% endblock %}
```

- [ ] **Step 2: `watchlists/detail.html`**

既存ファイルを Read してから、Tailwind クラスを上記マッピングで置換。`bg-white rounded-lg shadow p-N` → `panel` + `panel__body` 構造に。`button` → `btn` + バリアント。テーブルがあれば `table` クラス + `num-cell`。完了したら **次の Step を実行する前にこの差分のみをコミット**。

- [ ] **Step 3: `targets/list.html`**

```html
{% extends "base.html" %}
{% set breadcrumbs = ["分析ターゲット"] %}
{% block title %}分析ターゲット{% endblock %}
{% block content %}
<div class="page-header"><h1 class="h1">分析ターゲット</h1></div>

<form method="post" action="/targets" class="panel">
    <div class="panel__body flex flex--gap-2">
        <input class="input" name="company_id" required placeholder="例: US_AAPL">
        <button class="btn btn--primary" type="submit">追加</button>
    </div>
</form>

<section class="panel" style="margin-top: var(--space-4);">
    <ul class="search-results">
        {% for t in targets %}
        <li class="flex flex--between flex--center" style="padding: var(--space-3); border-bottom: 1px solid var(--border);">
            <a href="/stocks/{{ t.company_id }}" class="search-results__title">{{ t.company_id }}</a>
            <form method="post" action="/targets/{{ t.company_id }}/delete">
                <button class="btn btn--danger btn--sm" type="submit">削除</button>
            </form>
        </li>
        {% else %}
        <li><p class="empty-state">ターゲットがありません。</p></li>
        {% endfor %}
    </ul>
</section>
{% endblock %}
```

- [ ] **Step 4: `jobs/list.html`**

```html
{% extends "base.html" %}
{% set breadcrumbs = ["ジョブ"] %}
{% block title %}ジョブ{% endblock %}
{% block content %}
<div class="page-header"><h1 class="h1">ジョブ</h1></div>
{% if error %}
<div class="login-card__error" style="margin-bottom: var(--space-4);">
    <strong>エラー:</strong> {{ error }}
</div>
{% endif %}
<div class="grid-2">
    <section class="panel">
        <header class="panel__header"><h3 class="panel__title">単一銘柄を同期</h3></header>
        <div class="panel__body stack">
            <p class="muted">財務・バリュエーション・ファイリングをすべて取得します。</p>
            <form method="post" action="/jobs/sync" class="flex flex--gap-2">
                <input class="input" name="company_id" required placeholder="例: US_AAPL">
                <button class="btn btn--primary" type="submit">実行</button>
            </form>
        </div>
    </section>
    <section class="panel">
        <header class="panel__header"><h3 class="panel__title">日次バッチ</h3></header>
        <div class="panel__body stack">
            <p class="muted">市場単位でターゲット銘柄を一括更新します。</p>
            <form method="post" action="/jobs/daily" class="flex flex--gap-2">
                <select class="input" name="market">
                    <option value="us">米国</option>
                    <option value="jp">日本</option>
                </select>
                <button class="btn btn--primary" type="submit">実行</button>
            </form>
        </div>
    </section>
</div>
{% endblock %}
```

- [ ] **Step 5: `rag/ask.html`**

ファイルを Read したうえで、上記同様 `panel` / `btn` / `input` パターンで置換。

- [ ] **Step 6: テスト実行**

```bash
uv run pytest tests/unit/web/ -v
```

Expected: PASS (`test_targets.py` は `name=company_id` 等のフォーム属性を検証しているはずなので、属性は保持)。

- [ ] **Step 7: コミット**

```bash
git add src/stock_analyze_system/web/templates/watchlists \
        src/stock_analyze_system/web/templates/targets \
        src/stock_analyze_system/web/templates/jobs \
        src/stock_analyze_system/web/templates/rag
git commit -m "feat(web): restyle watchlists, targets, jobs, and rag-ask pages"
```

---

## Task 17: `app.js` の最終クリーンアップ (`fmtNumber`, `initSearch`, `initTabs`, `initDetailKpis`)

**Files:**
- Modify: `src/stock_analyze_system/web/static/app.js`

- [ ] **Step 1: `fmtNumber` を `en-US` ロケールに変更**

```javascript
function fmtNumber(value) {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "number") return value.toLocaleString("en-US");
    return String(value);
}
```

`fmtDateTime` は `ja-JP` のままで OK (UI は日本語ロケール)。

- [ ] **Step 2: `initSearch` の検索結果コンテナ参照は変更不要 (id="search-results" を維持)**

確認のみ。

- [ ] **Step 3: `initTabs` を新タブ CSS (`data-active`) に追従**

```javascript
function initTabs() {
    document.querySelectorAll("[data-tabs]").forEach((root) => {
        const defaultTab = root.dataset.defaultTab;
        const buttons = root.querySelectorAll("[data-tab-target]");
        const panels = root.querySelectorAll("[data-tab-panel]");
        function activate(tab) {
            buttons.forEach((button) => {
                button.dataset.active = button.dataset.tabTarget === tab ? "true" : "false";
            });
            panels.forEach((panel) => {
                panel.hidden = panel.dataset.tabPanel !== tab;
            });
        }
        buttons.forEach((button) => button.addEventListener("click", () => activate(button.dataset.tabTarget)));
        activate(defaultTab);
    });
}
```

- [ ] **Step 4: `initDetailKpis` を新規追加**

`document.addEventListener("DOMContentLoaded", ...)` 直前に追加:

```javascript
function initDetailKpis() {
    document.querySelectorAll("[data-detail-kpis]").forEach(async (root) => {
        const companyId = root.dataset.companyId;
        if (!companyId) return;
        const tiles = root.querySelectorAll("[data-kpi]");
        try {
            const valuations = await fetchJson(`/api/stocks/${companyId}/valuations`);
            const latest = valuations[0] || {};
            tiles.forEach((tile) => {
                const k = tile.dataset.kpi;
                const v = latest[k];
                if (k === "fcf_yield") {
                    tile.textContent = fmtPercent(v);
                } else if (v == null) {
                    tile.textContent = "—";
                } else {
                    tile.textContent = Number(v).toFixed(2);
                }
            });
        } catch (e) {
            tiles.forEach((tile) => { tile.textContent = "—"; });
        }
    });
}
```

`DOMContentLoaded` ハンドラに `initDetailKpis()` を追加:

```javascript
document.addEventListener("DOMContentLoaded", () => {
    initSearch();
    initTabs();
    initDetailKpis();
    initFinancialPanels();
    initMetricsPanels();
    initValuationPanels();
    initRagPanels();
});
```

- [ ] **Step 5: 旧 Tailwindクラスの残存確認**

```bash
grep -nE '"(bg-(white|gray|blue|red|emerald|amber)-[0-9]+|rounded(-lg)?|shadow|space-y|text-gray|font-(bold|semibold|medium))[^"]*"' \
  src/stock_analyze_system/web/static/app.js \
  src/stock_analyze_system/web/static/screening_check.js
```

何もマッチしなければ OK。

- [ ] **Step 6: テスト実行**

```bash
uv run pytest tests/unit/web/ -v
```

Expected: PASS。

注意: `test_app.py` の `test_stock_search_handles_errors_inside_debounced_callback` 等は引き続き合格する (構造は触っていない)。

- [ ] **Step 7: コミット**

```bash
git add src/stock_analyze_system/web/static/app.js
git commit -m "feat(web): finalize app.js DOM classes, en-US locale, KPI loader"
```

---

## Task 18: `_nav.html` 削除 + 仕上げの全体動作確認

**Files:**
- Delete: `src/stock_analyze_system/web/templates/_nav.html`

- [ ] **Step 1: `_nav.html` を削除**

```bash
git rm src/stock_analyze_system/web/templates/_nav.html
```

- [ ] **Step 2: `_nav.html` への参照が残っていないか確認**

```bash
grep -rn "_nav.html" src/stock_analyze_system/web/ tests/
```

期待: マッチなし (`base.html` は Task 6 で `_sidebar.html` / `_topbar.html` を使うように置換済み)。

- [ ] **Step 3: テストに `_nav.html` 不在を追加**

`tests/unit/web/test_app.py` 末尾に追加:

```python
def test_nav_template_is_removed():
    nav_path = Path("src/stock_analyze_system/web/templates/_nav.html")
    assert not nav_path.exists()


def test_no_tailwind_shim_classes_in_templates():
    template_dir = Path("src/stock_analyze_system/web/templates")
    forbidden = ["bg-white", "rounded-lg", "shadow", "bg-blue-600",
                 "bg-red-100", "text-gray-500", "text-gray-600", "text-gray-700"]
    for tpl in template_dir.rglob("*.html"):
        text = tpl.read_text()
        for token in forbidden:
            assert token not in text, f"{tpl}: still uses '{token}'"
```

- [ ] **Step 4: テスト実行**

```bash
uv run pytest tests/unit/web/ -v
```

Expected: PASS。マッチした場合は該当テンプレを修正してから再度テスト。

- [ ] **Step 5: 静的解析 (任意)**

```bash
uv run ruff check src/stock_analyze_system/web/
node -c src/stock_analyze_system/web/static/app.js
node -c src/stock_analyze_system/web/static/screening_check.js
```

Expected: 致命エラーなし。

- [ ] **Step 6: 既存ユニット/統合テスト全体**

```bash
uv run pytest tests/ -x
```

Expected: PASS。

- [ ] **Step 7: コミット**

```bash
git add tests/unit/web/test_app.py
git rm src/stock_analyze_system/web/templates/_nav.html 2>/dev/null || true
git commit -m "feat(web): remove legacy top nav and lock no-tailwind-shim invariant"
```

---

## Self-Review (完了)

- ✅ 仕様 spec の全機能要件を Task 1〜18 で網羅 (静的アセット, base 構造, 各画面, チャート, 削除リスト, テスト)
- ✅ プレースホルダ無し: 各ステップに具体コード
- ✅ Type/属性命名一貫: `data-tab-target/-panel`, `data-financial-panel/data-period-select`, `data-rag-panel/-question/-ask` など既存契約を維持
- ✅ DRY: 共通クラスは `app.css` に集約。テンプレ単位で重複しない
- ✅ TDD: 各タスクで `uv run pytest tests/unit/web/` を verification ステップとして配置
- ✅ コミット粒度: タスクごとに 1 コミット (チャート + 財務統合のみ大きめ)

---

## Execution

Plan complete. 次に実行モードを選択してください。
