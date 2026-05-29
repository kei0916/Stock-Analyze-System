// Dashboard screen
const Dashboard = ({ navigate }) => {
  const watchlist = MOCK_COMPANIES.slice(0, 4);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: "-0.01em", margin: 0, color: "var(--fg-1)" }}>ダッシュボード</h1>
          <div style={{ fontSize: 12, color: "var(--fg-3)", fontFamily: "var(--font-mono)", marginTop: 4 }}>
            最終同期 · 2026-04-25 09:14 JST · 358銘柄
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button variant="secondary" icon="refresh">日次更新</Button>
          <Button variant="primary" icon="plus">銘柄を追加</Button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        <KpiTile label="ウォッチ中" value="24" delta="+3 this week" deltaDirection="up"/>
        <KpiTile label="分析ターゲット" value="8" delta="+1" deltaDirection="up"/>
        <KpiTile label="LLM分析" value="42" delta="6 today" deltaDirection="neutral"/>
        <KpiTile label="平均PER" value="22.6" delta="−1.2 MoM" deltaDirection="down"/>
      </div>

      <Panel title="ウォッチリスト · Tech Watch" padding={0}
        action={<Button variant="ghost" size="sm" onClick={() => navigate("watchlists")}>すべて表示 →</Button>}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["銘柄", "株価", "PER", "PBR", "ROE", "1Y", ""].map((h, i) => (
                <th key={i} style={{
                  textAlign: i === 0 ? "left" : i === 6 ? "center" : "right",
                  font: "500 11px var(--font-sans)", letterSpacing: "0.06em", textTransform: "uppercase",
                  color: "var(--fg-2)", padding: "10px 16px", borderBottom: "1px solid var(--border-strong)",
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {watchlist.map(c => (
              <tr key={c.id} onClick={() => navigate(`stocks/${c.id}`)} style={{ cursor: "pointer" }}
                onMouseEnter={e => e.currentTarget.style.background = "var(--surface-2)"}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                <td style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)" }}>
                  <div style={{ fontWeight: 500, color: "var(--fg-1)" }}>{c.name_ja}</div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)" }}>{c.id} · {c.market}</div>
                </td>
                <td style={{ ...numCellStyle }}>{fmt.num(c.price, 2)}</td>
                <td style={{ ...numCellStyle }}>{fmt.ratio(c.per)}</td>
                <td style={{ ...numCellStyle }}>{fmt.ratio(c.pbr)}</td>
                <td style={{ ...numCellStyle }}>{fmt.pct(c.roe)}</td>
                <td style={{ ...numCellStyle, color: c.change1y >= 0 ? "var(--up)" : "var(--down)" }}>
                  {c.change1y >= 0 ? "↗ " : "↘ "}{fmt.delta(c.change1y)}
                </td>
                <td style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", textAlign: "center" }}>
                  <Icon name="chevRight" size={14} style={{ color: "var(--fg-3)" }}/>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Panel title="最近の同期">
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[
              { id: "US_AAPL", t: "09:14", n: 4 },
              { id: "JP_7203", t: "09:12", n: 12 },
              { id: "US_NVDA", t: "09:08", n: 4 },
              { id: "US_MSFT", t: "08:54", n: 8 },
            ].map(s => (
              <div key={s.id + s.t} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12 }}>
                <Badge variant="up" mono><span style={{ width: 5, height: 5, borderRadius: 999, background: "currentColor" }}/>OK</Badge>
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--fg-1)", flex: 1 }}>{s.id}</span>
                <span style={{ color: "var(--fg-2)" }}>{s.n}件のレコード</span>
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--fg-3)", fontSize: 11 }}>{s.t}</span>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="LLM分析キュー">
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[
              { id: "US_AAPL", type: "business_summary", st: "running" },
              { id: "US_NVDA", type: "risk_factors", st: "queued" },
              { id: "JP_6758", type: "mda", st: "queued" },
            ].map(j => (
              <div key={j.id + j.type} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12 }}>
                <Badge variant={j.st === "running" ? "accent" : "neutral"} mono>{j.st}</Badge>
                <span style={{ fontFamily: "var(--font-mono)", color: "var(--fg-1)" }}>{j.id}</span>
                <span style={{ color: "var(--fg-2)", fontFamily: "var(--font-mono)", fontSize: 11 }}>· {j.type}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
};

const numCellStyle = {
  padding: "10px 16px", borderBottom: "1px solid var(--border)",
  fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums",
  fontSize: 13, color: "var(--fg-1)", textAlign: "right",
};

Object.assign(window, { Dashboard });
