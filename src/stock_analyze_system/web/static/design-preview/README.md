# Stock Analyzer Design System

> 株式の投資判断に必要な情報を、詳細に・視覚的に提供する分析プラットフォームのためのデザインシステム。

**Product:** Stock Analyzer (株式分析システム)
**Source repo:** [`kei0916/Stock-Analyze-System`](https://github.com/kei0916/Stock-Analyze-System)
**Spec:** `docs/superpowers/specs/2026-03-21-stock-analyze-system-design.md` (in source repo)
**Primary spec read:** `requirements_specification.md` (root of source repo, v0.1.0, 2026-03-21)

---

## What is Stock Analyzer?

A comprehensive financial analysis platform for **US (SEC EDGAR)** and **Japanese (EDINET)** equities. It pulls XBRL financial filings, computes valuation multiples (PER/PBR/EV-EBITDA/PSR/FCF yield), runs screeners, builds 10-year monthly valuation history, and adds **LLM analysis** (local Ollama / LM Studio) of filings — including a planned **PageIndex RAG** system that lets you ask questions of a 10-K and get cited answers.

### Three surfaces, one services layer

```
┌──────────┐  ┌──────────┐  ┌──────────┐
│   CLI    │  │ Discord  │  │   Web    │  ← surfaces
│(argparse)│  │   Bot    │  │(FastAPI) │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     └─────────────┴─────────────┘
                  │
          Services Layer (pure)
                  │
   Ingestion │ Models (ORM) │ Metrics
   SEC EDGAR / EDINET / Yahoo Finance / Ollama
```

The **Web** surface is what this design system is primarily for: a FastAPI + Jinja2 SSR app, augmented by HTMX (partial updates), Alpine.js (client state), and Chart.js (charts). Tailwind CSS is loaded via CDN.

### Core screens

1. **Dashboard** — landing, recent activity, quick actions
2. **Stock Detail** (`/stocks/{id}`) — Financials / Valuation / Metrics / LLM Analysis / Filings tabs
3. **Screening** (`/screening`) — multi-filter screener with HTMX result swaps
4. **Watchlists** — manage groups of monitored companies
5. **Targets** — companies promoted from screening into the analysis funnel
6. **Jobs** — sync / daily update controls
7. **RAG Q&A** — (planned) ask questions of a specific 10-K, with cited page ranges
8. **Login** — password-only session auth

---

## Design philosophy

> 先進的なデザイン。使用する色は2-3色で、分析に集中できるよう見やすさとシンプルさを重視。

**Three operating principles:**

1. **Data is the hero.** Numbers, charts, and tables come first. Chrome (nav, headers, controls) recedes — low contrast, monochrome, no decoration.
2. **Two colors plus signal.** Near-black canvas, off-white type, one accent (electric cyan) for interactive state and one neutral pair of semantic colors (up / down). No purple gradients, no pastel cards, no glassmorphism.
3. **Density without noise.** Tight vertical rhythm, monospaced numerics for column alignment, hairline rules instead of cards-with-shadows. The interface should feel like a Bloomberg terminal that went to design school.

**Inspiration:** Linear, Vercel, Bloomberg Terminal, TradingView's "dark" mode, Things 3's restraint.

**Anti-patterns** (do not do):
- Bluish-purple gradients
- Emoji as iconography
- Cards with `border-left: 4px solid <color>`
- Drop shadows on everything
- Hand-drawn or organic illustration
- Inline icons that are decorative rather than functional

---

## File index

| File / folder | What's in it |
|---|---|
| `README.md` | This file. Overview + content + visual + iconography guides. |
| `colors_and_type.css` | All design tokens: color, type, spacing, radius, shadow, motion. Import this from any artifact. |
| `fonts/` | Self-hosted webfonts (Inter, JetBrains Mono). |
| `assets/` | Logos, icons, brand marks. |
| `preview/` | Cards rendered in the Design System tab — one concept per card. |
| `ui_kits/web/` | High-fidelity Web UI kit. JSX components + interactive `index.html`. |
| `SKILL.md` | Agent Skills entrypoint (cross-compatible with Claude Code). |

---

## Content fundamentals

The product is **bilingual** (Japanese-primary, English-secondary). UI labels in Japanese; ticker/company codes and financial concept names often in English.

**Tone**

- **Direct, technical, neutral.** No marketing voice. No emoji. No exclamation points.
- **Second-person sparingly** — most copy is third-person descriptive ("売上高", "営業利益", "前年同期比"). Direct address only in calls-to-action ("同期する", "分析を実行").
- **Imperative for actions.** Buttons read as commands: `同期`, `追加`, `分析`, `削除`. Not `ここをクリック` style.
- **Numbers are nouns.** A column heading says `PER` or `売上高 (B)`. The unit is part of the label. The cell is just the number.

**Casing & punctuation**

- Japanese sentences end with 。 — but UI labels and table headers do not get terminal punctuation.
- English acronyms uppercase: `PER`, `PBR`, `EV/EBITDA`, `FCF`, `ROE`, `ROIC`, `EPS`, `DPS`.
- Ticker symbols uppercase: `AAPL`, `7203`, `BRK-B`. Company IDs prefix-and-uppercase: `US_AAPL`, `JP_7203`.
- Currency codes ISO-3 uppercase: `USD`, `JPY`, `TWD`.
- Negative numbers: leading minus sign, never parentheses. `-1,234` not `(1,234)`.

**Number formatting** (matches `shared/formatters.py`)

| Helper | Output |
|---|---|
| `fmt_number(1234567)` | `1,234,567` |
| `fmt_pct(0.158)` | `15.8%` |
| `fmt_large(2_500_000_000)` | `2.50B` |
| `fmt_ratio(15.823)` | `15.82` |

Suffix scale: `k`, `M`, `B`, `T`. Always two decimal places for ratios. Always one decimal for percentages.

**Examples (from the source)**

- Tab label: `財務` / `バリュエーション` / `指標` / `分析` / `ファイリング`
- Period toggle: `通期 / 四半期`
- Metric picker labels: `売上高`, `営業利益`, `純利益`, `EBITDA`, `営業CF`, `設備投資`, `FCF`
- Empty state: `データがありません。同期を実行してください。`
- Error toast: `同期に失敗しました: {reason}`
- Success toast: `同期が完了しました ({n}件のレコードを更新)`
- Confirm: `このウォッチリストを削除しますか？この操作は取り消せません。`

**Don't** write filler ("Welcome to your dashboard! Let's get started analyzing stocks today 🚀"). **Do** write status: `最終同期: 2026-04-25 09:14 JST · 358銘柄`.

---

## Visual foundations

### Colors — two and a half

The whole interface lives in two grayscale ramps plus one accent. Semantic up/down green/red is treated as "data ink" — used inside numerics, never as a UI element.

| Role | Token | Light | Dark | Notes |
|---|---|---|---|---|
| Canvas | `--bg` | `#FAFAFA` | `#0B0D10` | Page background. Dark default. |
| Surface | `--surface` | `#FFFFFF` | `#111418` | Panels, table cards. Barely lifted. |
| Surface raised | `--surface-2` | `#F4F4F5` | `#171B21` | Modals, popovers, hovered rows. |
| Foreground 1 | `--fg-1` | `#0B0D10` | `#F2F4F7` | Primary text, numbers. |
| Foreground 2 | `--fg-2` | `#52525B` | `#A1A6AE` | Secondary text, labels. |
| Foreground 3 | `--fg-3` | `#A1A1AA` | `#5C636E` | Tertiary, axis labels, captions. |
| Border | `--border` | `#E4E4E7` | `#22272F` | Hairlines (1px). |
| Border strong | `--border-strong` | `#D4D4D8` | `#2D333C` | Emphasized dividers. |
| Accent | `--accent` | `#0EA5E9` | `#22D3EE` | Sky-500 / Cyan-400. Interactive only. |
| Accent fg | `--accent-fg` | `#FFFFFF` | `#031018` | Text on accent. |
| Up | `--up` | `#16A34A` | `#22C55E` | Positive change. Number-only. |
| Down | `--down` | `#DC2626` | `#EF4444` | Negative change. Number-only. |

**Rules:**
- Default mode is dark. Light mode is supported but secondary.
- Accent is only for: focus rings, primary buttons, active tabs, links, selected rows.
- Up/down only color the digit and its sign, never a whole row or background.
- No third hue. No purple, no orange, no yellow. If a chart needs more series, use accent at 100/70/40% opacity, then `--fg-2`, then `--fg-3`.

### Typography

Two families. No display face.

- **Inter** — UI, body, headings. Variable font; weights 400/500/600/700. Letter-spacing slightly tightened on headings (`-0.01em`).
- **JetBrains Mono** — all numerics in tables, all tabular data, code snippets, ticker symbols, company IDs. Tabular-figures variant always on.

**Scale** (rem; root = 14px):

| Token | Size | Line-height | Use |
|---|---|---|---|
| `--text-h1` | 28px / 700 | 1.15 | Page title. One per page. |
| `--text-h2` | 20px / 600 | 1.25 | Section header. |
| `--text-h3` | 16px / 600 | 1.35 | Subsection / card title. |
| `--text-body` | 14px / 400 | 1.5 | Default body. |
| `--text-sm` | 13px / 400 | 1.45 | Secondary copy, table cells. |
| `--text-xs` | 12px / 500 | 1.4 | Labels, badges, captions, axis. |
| `--text-num-lg` | 32px / 600 mono | 1.1 | KPI display value. |
| `--text-num` | 14px / 500 mono | 1.4 | Inline number. |

Headings use `--fg-1`. Body uses `--fg-1`. Labels and captions use `--fg-2`. Disabled / placeholder uses `--fg-3`.

### Spacing & layout

8-pt grid, with 4-pt half-step for table cell padding.

`--space-1: 4px`, `--space-2: 8px`, `--space-3: 12px`, `--space-4: 16px`, `--space-5: 24px`, `--space-6: 32px`, `--space-7: 48px`, `--space-8: 64px`.

- Page gutter: 24px on desktop.
- Sidebar width: 240px fixed.
- Content max-width: 1440px.
- Table row height: 36px (compact) / 44px (default).
- Card padding: 16px or 20px. Never more on data panels.

### Backgrounds, borders, shadows

- **No imagery.** No hero photos, no illustrations, no patterns. The product is a tool.
- **Hairlines, not boxes.** Sections divide with 1px `--border`. Cards exist only when a panel needs to scroll independently or a popover detaches from flow.
- **Shadows are barely there.**
  - `--shadow-1` (popover): `0 1px 2px rgba(0,0,0,.06), 0 4px 12px rgba(0,0,0,.08)`
  - `--shadow-2` (modal): `0 8px 32px rgba(0,0,0,.18)`
  - In dark mode, shadows are emulated with a 1px top inner highlight and the `--border` ring.
- **Corner radius is restrained.**
  - `--radius-sm: 4px` (badges, tags)
  - `--radius-md: 6px` (buttons, inputs)
  - `--radius-lg: 8px` (cards, modals)
  - Tables and rows are not rounded internally.
- **Transparency / blur:** Used only on the modal scrim (`rgba(0,0,0,.5)` in dark; `rgba(15,23,42,.4)` in light). No frosted-glass surfaces.

### Imagery

There is no imagery system. Empty states use type and a single mono-line glyph from Lucide. Charts are the visual content.

### Motion

Functional, fast, never decorative.

- **Easing:** `cubic-bezier(0.2, 0.8, 0.2, 1)` (a snappy ease-out). Stored as `--ease-snap`.
- **Durations:** 120ms (hover, focus), 180ms (modal/menu), 240ms (tab/route swap). Stored as `--dur-1/--dur-2/--dur-3`.
- **No bounces, no spring overshoot, no entrance animations on page load.**
- HTMX swaps fade their content over 120ms; nothing slides.
- Charts animate axis-in once on first render only (200ms), never on data updates.

### State

| State | Treatment |
|---|---|
| Hover (button, link) | Background lifts to `--surface-2`, or accent fades to its `-hover` token. No translate, no scale. |
| Focus (keyboard) | 2px `--accent` ring, 2px offset. Always visible. |
| Active / pressed | Background drops to `--surface` (one step down), no scale. |
| Selected (row, tab) | 2px left or bottom `--accent` indicator + `--surface-2` fill. |
| Disabled | `--fg-3` text, `opacity: .5`, `cursor: not-allowed`. No hover. |
| Loading | Pulse opacity 1 → 0.5 over 1s. No spinners on inline elements; one global top-bar progress on route changes (HTMX). |

### Layout rules

- Sidebar is **fixed** on desktop (`position: sticky; top: 0; height: 100vh`).
- Top bar is **fixed** within content area, contains breadcrumb + search + user.
- Tabs in stock detail are **sticky** below the top bar.
- Tables scroll horizontally on overflow; the first column (company / metric name) is sticky.
- Modals are centered, max-width 560px (default) / 720px (form-heavy).

---

## Iconography

**Library:** [Lucide](https://lucide.dev/) — loaded via CDN (`<script src="https://unpkg.com/lucide@latest"></script>`). The source repo does not vendor an icon set, so we adopt Lucide as the standard. **Flag:** this is a substitution; please confirm or supply a preferred set.

**Style rules:**
- 1.5px stroke, no fill, square caps, round joins.
- Sizes: 14px (inline), 16px (default in nav/buttons), 20px (section headers), 24px (empty states).
- Color: inherit `--fg-2`. Active state inherits `--accent`. Never multi-color icons.
- Always paired with a text label or aria-label. **No** standalone decorative icons.

**Common icons used in this product:**

| Use | Icon |
|---|---|
| Search | `lucide:search` |
| Sync / refresh | `lucide:refresh-cw` |
| Watchlist | `lucide:bookmark` |
| Screening | `lucide:filter` |
| Targets | `lucide:target` |
| Jobs | `lucide:zap` |
| Stock detail | `lucide:line-chart` |
| LLM Analysis | `lucide:sparkles` *(only icon allowed to imply AI)* |
| Filings | `lucide:file-text` |
| Up arrow (in numbers) | `lucide:arrow-up-right` |
| Down arrow (in numbers) | `lucide:arrow-down-right` |
| External link | `lucide:external-link` |
| User | `lucide:user-circle` |
| Logout | `lucide:log-out` |
| Sort asc/desc | `lucide:chevron-up` / `lucide:chevron-down` |

**Emoji:** never used.
**Unicode glyphs:** allowed for math/finance: `±`, `≥`, `≤`, `→`, `↗`, `↘`, `·`. Use `→` in breadcrumbs.

---

## Brand mark

The source repo has no logo. We've designed a wordmark + symbol pair (`assets/logo.svg`, `assets/mark.svg`) consistent with the visual system: a monospaced wordmark `STOCK ANALYZER` with a small bracketed cursor `[•]` mark to evoke a terminal prompt and a data point.

**Flag:** This is a designer-supplied mark. If the user has an existing brand, supply it and we'll swap.

---

## File index

| Path | Purpose |
|---|---|
| `colors_and_type.css` | Token source of truth (colors, type, spacing, radius, motion). Import in every artifact. |
| `SKILL.md` | Hard rules + recipes for designing new artifacts in this system. |
| `assets/` | `logo.svg`, `mark.svg`, `mark-inverse.svg` |
| `fonts/` | Inter Variable, JetBrains Mono Variable (woff2) |
| `preview/` | One HTML card per primitive — open any in a browser to see it in isolation. Registered as design-system review cards (Type, Colors, Spacing, Components, Brand). |
| `ui_kits/web/` | Full clickable React prototype: Dashboard, Stock Detail (5 tabs), Screening, Watchlists, Login. Open `ui_kits/web/index.html`. |

---

## Caveats

- **No Figma source** was provided — the design system is derived from `requirements_specification.md` (very detailed) and the source code structure. Visual specifics (exact colors, type scale) are designer interpretations of the brief: 先進的, 2-3色, 見やすさとシンプルさ.
- **Lucide is a substitution** for icons (none vendored in source repo). Icons in the UI kit are inline SVG paths matching Lucide's geometry.
- **No `web/templates/` directory exists yet in the source repo** — the FastAPI Web routes described in §7 of the spec are designed but not implemented. The UI kit in `ui_kits/web/` is a fresh implementation that follows the spec's tab structure and route map (`/stocks/{id}`, tabs 財務 / バリュエーション / 指標 / 分析 / ファイリング, screening filter keys per §7.5).
- **Brand mark is designer-supplied.** A monospaced `STOCK ANALYZER` wordmark with a `[•]` terminal-prompt symbol. Swap if you have an existing brand.
- **Mock data is illustrative.** Numbers in the prototype are plausible but not real-time.

If any of the above is wrong, reply and I'll adjust.
