// Sidebar + topbar layout shell.

const NAV = [
  { key: "dashboard",  label: "ダッシュボード",   icon: "chart" },
  { key: "stocks",     label: "銘柄",            icon: "search" },
  { key: "watchlists", label: "ウォッチリスト",   icon: "bookmark" },
  { key: "screening",  label: "スクリーニング",   icon: "filter" },
  { key: "targets",    label: "分析ターゲット",   icon: "target" },
  { key: "jobs",       label: "ジョブ",          icon: "zap" },
];

const Sidebar = ({ route, navigate }) => (
  <aside style={{
    width: "var(--sidebar-w)", background: "var(--surface)", borderRight: "1px solid var(--border)",
    height: "100vh", position: "sticky", top: 0, display: "flex", flexDirection: "column",
    flexShrink: 0,
  }}>
    <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 10 }}>
      <img src="../../assets/mark.svg" width="22" height="22" alt=""/>
      <span style={{ font: "700 13px var(--font-mono)", letterSpacing: "0.04em", color: "var(--fg-1)" }}>
        STOCK ANALYZER
      </span>
    </div>
    <nav style={{ padding: 8, display: "flex", flexDirection: "column", gap: 2, flex: 1 }}>
      {NAV.map(n => {
        const active = route.startsWith(n.key);
        return (
          <a key={n.key} onClick={() => navigate(n.key)} style={{
            display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", borderRadius: 5,
            background: active ? "var(--surface-2)" : "transparent",
            color: active ? "var(--fg-1)" : "var(--fg-2)",
            font: "500 13px var(--font-sans)", cursor: "pointer",
            transition: "background 120ms var(--ease-snap)",
          }}>
            <Icon name={n.icon} size={15}/>{n.label}
          </a>
        );
      })}
    </nav>
    <div style={{ padding: 12, borderTop: "1px solid var(--border)", fontSize: 11, color: "var(--fg-3)", fontFamily: "var(--font-mono)" }}>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <span>v0.1.0</span>
        <span>SQLite WAL</span>
      </div>
      <div style={{ marginTop: 4 }}>last sync · 2026-04-25 09:14</div>
    </div>
  </aside>
);

const Topbar = ({ title, breadcrumbs, onSearch }) => (
  <header style={{
    height: "var(--topbar-h)", borderBottom: "1px solid var(--border)",
    display: "flex", alignItems: "center", padding: "0 24px", gap: 16,
    background: "var(--bg)", position: "sticky", top: 0, zIndex: 5,
  }}>
    <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--fg-2)" }}>
      {breadcrumbs?.map((b, i) => (
        <React.Fragment key={i}>
          {i > 0 && <span style={{ color: "var(--fg-3)" }}>→</span>}
          <span style={{ color: i === breadcrumbs.length - 1 ? "var(--fg-1)" : "var(--fg-2)", fontWeight: i === breadcrumbs.length - 1 ? 500 : 400 }}>{b}</span>
        </React.Fragment>
      )) || <span style={{ font: "600 14px var(--font-sans)", color: "var(--fg-1)" }}>{title}</span>}
    </div>
    <div style={{ position: "relative", width: 280 }}>
      <Icon name="search" size={14} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--fg-3)" }}/>
      <input placeholder="銘柄を検索  (例: AAPL, 7203)" onChange={e => onSearch?.(e.target.value)} style={{
        width: "100%", boxSizing: "border-box", background: "var(--surface)",
        border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px 6px 30px",
        color: "var(--fg-1)", font: "400 12px var(--font-sans)", outline: "none",
      }}/>
    </div>
    <Button variant="ghost" size="sm" icon="user">admin</Button>
  </header>
);

const Layout = ({ route, navigate, breadcrumbs, children }) => (
  <div style={{ display: "flex", minHeight: "100vh", background: "var(--bg)" }}>
    <Sidebar route={route} navigate={navigate}/>
    <main style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
      <Topbar breadcrumbs={breadcrumbs}/>
      <div style={{ padding: 24, maxWidth: "var(--content-max)", width: "100%", boxSizing: "border-box" }}>
        {children}
      </div>
    </main>
  </div>
);

Object.assign(window, { Layout, Sidebar, Topbar });
