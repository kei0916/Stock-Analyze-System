# Stock Analyzer Web UI Kit

High-fidelity recreation of the FastAPI + Jinja2 + HTMX + Alpine.js + Chart.js web surface described in the source repo's `requirements_specification.md` (§7).

## Files
- `index.html` — entry point. Click-thru prototype covering Dashboard, Stock Detail (5 tabs), Screening, Watchlists, Login.
- `App.jsx` — top-level shell + routing.
- `Layout.jsx` — sidebar + topbar.
- `Components.jsx` — atomic UI: Button, Input, Badge, Tabs, KpiTile, etc.
- `screens/Dashboard.jsx`
- `screens/StockDetail.jsx`
- `screens/Screening.jsx`
- `screens/Watchlists.jsx`
- `screens/Login.jsx`

## What's recreated vs. invented
The source repo defines routes and templates only at the spec level — there is **no `web/templates/` directory** with concrete HTML. This UI kit follows the spec's route map, tab structure, and field names exactly (`/stocks/{id}`, tabs 財務 / バリュエーション / 指標 / 分析 / ファイリング, screening filter keys per §7.5, etc.) but the visual treatment is a fresh implementation aligned with the design system.

## Verify
Open `index.html`. Use the sidebar to navigate. Stock Detail starts on US_AAPL and supports tab switching + period toggle. Screening has working client-side filters.
