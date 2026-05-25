# Stock Analyzer — Design System Skill

You are working in the **Stock Analyzer** design system. Use this skill whenever the user asks for any UI artifact (screen, component, deck, prototype, mock) tied to this product.

## Always start by loading
- `README.md` — content fundamentals, voice, taxonomy, visual foundations
- `colors_and_type.css` — token source of truth (colors, type, spacing, radius, motion). **Import this first** in any HTML output.
- `preview/` — visual cards for every primitive. Look here before inventing components.
- `ui_kits/web/` — full clickable web prototype. The Components.jsx, Layout.jsx, and screen files are the canonical React reference.

## Hard rules
1. **Dark mode is the default and only mode.** Do not produce a light theme unless the user explicitly asks.
2. **Use tokens, never raw hex.** `var(--accent)`, `var(--up)`, `var(--down)`, `var(--fg-1/2/3)`, `var(--surface)`, `var(--surface-2)`, `var(--border)`, `var(--border-strong)`. Never inline `#22D3EE`.
3. **Numbers use `JetBrains Mono` with `font-variant-numeric: tabular-nums`.** Every price, ratio, percentage, date, and ID. Mix mono+sans inside the same row freely.
4. **Up = green (#22C55E), Down = red (#EF4444).** Always paired with a directional glyph (`↗ ↘`). Never use color alone.
5. **Japanese-first copy.** Default UI labels to Japanese (`ダッシュボード`, `銘柄`, `スクリーニング`). Render company names as `日本語名 · English Name`. Use English for ticker IDs (`US_AAPL`, `JP_7203`) and metric abbreviations (PER, PBR, ROE, EV/EBITDA).
6. **Cyan accent is rationed.** One primary action per view. Use it for the active nav row, primary buttons, focus rings, and a single chart series — not as decoration.
7. **No gradients on chrome.** Solid surfaces only. The single permitted gradient is the area-fill under chart lines (token: `--accent-soft` fading to transparent).
8. **Borders over shadows.** `1px solid var(--border)` separates panels. `--border-strong` for interactive containers. Shadows only for floating overlays (menus, toasts, modals).
9. **8pt grid.** Padding/margin/gap from `--space-*`. Tight density: panel padding 16px, table cells 10–12px vertical / 16px horizontal, button height 32–36px.
10. **No emoji.** Use the SVG icon set in `preview/iconography.html`. 1.5px stroke, 24px viewbox, currentColor stroke, no fill.

## Voice
Concise, data-forward, neutral. No marketing prose. Section headings are short noun phrases. Numbers are the protagonist — UI gets out of their way. Empty states are one short sentence + one action.

## Component recipes (lift, don't reinvent)
- **Buttons** — `ui_kits/web/Components.jsx` exports `<Button variant="primary|secondary|ghost|danger" size="sm|md" icon="…">`.
- **Tables** — header row uses uppercase 11px label color (`--fg-2`), `border-bottom: 1px solid var(--border-strong)`. Body rows `border-bottom: 1px solid var(--border)`. Numeric cells: mono, tabular, right-aligned.
- **KPI tiles** — `<KpiTile label value delta deltaDirection>`. Label small caps, value 24–32px mono, delta 11px mono colored by direction.
- **Tabs / Segmented** — see Components.jsx. Tabs underline the active item with the accent.
- **Charts** — single accent line + faint gradient fill + dashed median line (`--fg-3`, `stroke-dasharray: 3 3`). Grid lines `--border`, axis labels mono 10–11px `--fg-3`.

## Building new screens
1. Copy `ui_kits/web/index.html` head + script tags as your scaffold. Pinned React/Babel CDNs already in place.
2. Use existing components from Components.jsx (export to window — see existing `Object.assign(window, …)` pattern).
3. Mock data goes in a separate `data.jsx` file. Use the schema in the existing one (id, ticker, name, name_ja, market, standard, per/pbr/psr/evEbitda/fcfYield/roe).
4. Always include the sidebar + topbar via `<Layout>`.

## When asked to design something not yet covered
Ask: does the user have an existing screen in the spec (`requirements_specification.md` §7) or codebase you should reference? If yes, find it. Don't invent flows from nothing.

## Output sizing
- Web mocks: 1280–1440px wide, scrollable.
- Tablet/mobile: ask first — the source app is desktop-first.
- Decks: use `deck_stage.js`, 1920×1080, dark `--bg`, accent for emphasis only.
