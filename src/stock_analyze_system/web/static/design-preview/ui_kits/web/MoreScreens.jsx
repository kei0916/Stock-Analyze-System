// Screening, Watchlists, Login screens

const Screening = ({ navigate }) => {
  // Distribution-aware filter ranges. Values are absolute (per, pbr, etc).
  // ROE stored as fraction; we display as %.
  const PER_MIN = 0, PER_MAX = 80;
  const PBR_MIN = 0, PBR_MAX = 50;
  const ROE_MIN = -10, ROE_MAX = 200;       // %
  const FCF_MIN = 0,  FCF_MAX = 10;         // %

  const [ranges, setRanges] = React.useState({
    per: [PER_MIN, PER_MAX],
    pbr: [PBR_MIN, PBR_MAX],
    roe: [ROE_MIN, ROE_MAX],
    fcf: [FCF_MIN, FCF_MAX],
  });
  const [market, setMarket] = React.useState("all");
  const setRange = (k, v) => setRanges(r => ({ ...r, [k]: v }));

  const filtered = MOCK_COMPANIES.filter(c => {
    if (c.per < ranges.per[0] || c.per > ranges.per[1]) return false;
    if (c.pbr < ranges.pbr[0] || c.pbr > ranges.pbr[1]) return false;
    const roePct = c.roe * 100;
    if (roePct < ranges.roe[0] || roePct > ranges.roe[1]) return false;
    const fcfPct = c.fcfYield * 100;
    if (fcfPct < ranges.fcf[0] || fcfPct > ranges.fcf[1]) return false;
    if (market !== "all" && !c.id.startsWith(market)) return false;
    return true;
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: "-0.01em", margin: 0, color: "var(--fg-1)" }}>スクリーニング</h1>
        <div style={{ fontSize: 12, color: "var(--fg-3)", fontFamily: "var(--font-mono)", marginTop: 4 }}>
          {filtered.length} / {MOCK_COMPANIES.length} 銘柄
        </div>
      </div>

      <Panel title="フィルター">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 24, rowGap: 20 }}>
          <HistogramRange label="PER" unit="x" min={PER_MIN} max={PER_MAX} step={0.5}
            value={ranges.per} onChange={v => setRange("per", v)}
            data={MOCK_COMPANIES.map(c => c.per)}/>
          <HistogramRange label="PBR" unit="x" min={PBR_MIN} max={PBR_MAX} step={0.5}
            value={ranges.pbr} onChange={v => setRange("pbr", v)}
            data={MOCK_COMPANIES.map(c => c.pbr)}/>
          <HistogramRange label="ROE" unit="%" min={ROE_MIN} max={ROE_MAX} step={1}
            value={ranges.roe} onChange={v => setRange("roe", v)}
            data={MOCK_COMPANIES.map(c => c.roe * 100)}/>
          <HistogramRange label="FCF Yield" unit="%" min={FCF_MIN} max={FCF_MAX} step={0.1}
            value={ranges.fcf} onChange={v => setRange("fcf", v)}
            data={MOCK_COMPANIES.map(c => c.fcfYield * 100)}/>
        </div>
        <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px solid var(--border)",
          display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
          <div>
            <Label>市場</Label>
            <div style={{ marginTop: 6 }}>
              <Segmented value={market} onChange={setMarket} options={[
                { value: "all", label: "全て" }, { value: "US_", label: "US" }, { value: "JP_", label: "JP" },
              ]}/>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <Button variant="ghost" size="sm">プリセット保存</Button>
            <Button variant="secondary" size="sm" onClick={() => setRanges({
              per: [PER_MIN, PER_MAX], pbr: [PBR_MIN, PBR_MAX],
              roe: [ROE_MIN, ROE_MAX], fcf: [FCF_MIN, FCF_MAX],
            })}>リセット</Button>
            <Button variant="primary" size="sm">適用</Button>
          </div>
        </div>
      </Panel>

      <Panel title={`結果 (${filtered.length})`} padding={0}
        action={<Button variant="ghost" size="sm" icon="bookmark">ウォッチに追加</Button>}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>{["銘柄", "市場", "セクター", "PER ↓", "PBR", "PSR", "ROE", "FCF Yld", "1Y"].map((h, i) => (
            <th key={i} style={{
              textAlign: i <= 2 ? "left" : "right",
              font: "500 11px var(--font-sans)", letterSpacing: "0.06em", textTransform: "uppercase",
              color: "var(--fg-2)", padding: "10px 16px", borderBottom: "1px solid var(--border-strong)",
            }}>{h}</th>
          ))}</tr></thead>
          <tbody>
            {filtered.sort((a, b) => a.per - b.per).map(c => (
              <tr key={c.id} onClick={() => navigate(`stocks/${c.id}`)} style={{ cursor: "pointer" }}
                onMouseEnter={e => e.currentTarget.style.background = "var(--surface-2)"}
                onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                <td style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)" }}>
                  <div style={{ fontWeight: 500, color: "var(--fg-1)", fontSize: 13 }}>{c.name_ja}</div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)" }}>{c.id}</div>
                </td>
                <td style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)" }}><Badge mono>{c.market}</Badge></td>
                <td style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", color: "var(--fg-2)", fontSize: 12 }}>{c.sector}</td>
                <td style={{ ...numCellStyle }}>{fmt.ratio(c.per)}</td>
                <td style={{ ...numCellStyle }}>{fmt.ratio(c.pbr)}</td>
                <td style={{ ...numCellStyle }}>{fmt.ratio(c.psr)}</td>
                <td style={{ ...numCellStyle }}>{fmt.pct(c.roe)}</td>
                <td style={{ ...numCellStyle }}>{fmt.pct(c.fcfYield, 2)}</td>
                <td style={{ ...numCellStyle, color: c.change1y >= 0 ? "var(--up)" : "var(--down)" }}>{fmt.delta(c.change1y)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
};

// Histogram-backed dual-handle range slider.
const HistogramRange = ({ label, unit = "", min, max, step, value, onChange, data, bins = 24 }) => {
  const [lo, hi] = value;
  const trackRef = React.useRef(null);
  const [drag, setDrag] = React.useState(null); // 'lo' | 'hi' | null

  // Build histogram
  const counts = React.useMemo(() => {
    const arr = new Array(bins).fill(0);
    const range = max - min;
    data.forEach(v => {
      if (v == null || isNaN(v)) return;
      const clamped = Math.max(min, Math.min(max - 0.0001, v));
      const idx = Math.min(bins - 1, Math.floor(((clamped - min) / range) * bins));
      arr[idx]++;
    });
    return arr;
  }, [data, min, max, bins]);
  const peak = Math.max(1, ...counts);

  const pct = (v) => ((v - min) / (max - min)) * 100;
  const fromClient = (clientX) => {
    const rect = trackRef.current.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const raw = min + ratio * (max - min);
    return Math.round(raw / step) * step;
  };

  const onPointerDown = (which) => (e) => {
    e.preventDefault();
    setDrag(which);
    const move = (ev) => {
      const v = fromClient(ev.clientX);
      onChange(which === "lo"
        ? [Math.min(v, hi - step), hi]
        : [lo, Math.max(v, lo + step)]);
    };
    const up = () => {
      setDrag(null);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const onTrackClick = (e) => {
    if (drag) return;
    const v = fromClient(e.clientX);
    // pick nearer handle
    if (Math.abs(v - lo) < Math.abs(v - hi)) onChange([Math.min(v, hi - step), hi]);
    else onChange([lo, Math.max(v, lo + step)]);
  };

  // count of items currently in range (highlighted bins)
  const inRangeCount = data.filter(v => v >= lo && v <= hi).length;

  const fmtV = (v) => (Math.round(v * 100) / 100).toString();

  return (
    <div>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 }}>
        <Label>{label}</Label>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-2)", fontVariantNumeric: "tabular-nums" }}>
          {fmtV(lo)}{unit} – {fmtV(hi)}{unit}
          <span style={{ color: "var(--fg-3)", marginLeft: 8 }}>· {inRangeCount}社</span>
        </span>
      </div>

      {/* Histogram */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 1, height: 44, padding: "0 1px" }}>
        {counts.map((c, i) => {
          const binStart = min + (i / bins) * (max - min);
          const binEnd = min + ((i + 1) / bins) * (max - min);
          const inRange = binEnd > lo && binStart < hi;
          return (
            <div key={i} style={{
              flex: 1,
              height: `${(c / peak) * 100}%`,
              minHeight: c > 0 ? 2 : 0,
              background: inRange ? "var(--accent)" : "var(--surface-3)",
              opacity: inRange ? 0.85 : 0.6,
              borderRadius: "2px 2px 0 0",
              transition: "background 80ms linear, opacity 80ms linear",
            }}/>
          );
        })}
      </div>

      {/* Track + handles */}
      <div ref={trackRef} onPointerDown={onTrackClick}
        style={{ position: "relative", height: 28, marginTop: 2, cursor: "pointer" }}>
        {/* Base track */}
        <div style={{
          position: "absolute", left: 0, right: 0, top: 12, height: 4,
          background: "var(--surface-3)", borderRadius: 2,
        }}/>
        {/* Selected fill */}
        <div style={{
          position: "absolute", top: 12, height: 4,
          left: `${pct(lo)}%`, width: `${pct(hi) - pct(lo)}%`,
          background: "var(--accent)", borderRadius: 2,
        }}/>
        {/* Handles */}
        {[
          { which: "lo", v: lo },
          { which: "hi", v: hi },
        ].map(({ which, v }) => (
          <div key={which}
            onPointerDown={onPointerDown(which)}
            style={{
              position: "absolute", top: 7, left: `${pct(v)}%`, transform: "translateX(-50%)",
              width: 14, height: 14, borderRadius: 999,
              background: "var(--bg)", border: "2px solid var(--accent)",
              boxShadow: drag === which ? "0 0 0 4px var(--accent-soft)" : "0 1px 2px rgba(0,0,0,0.4)",
              cursor: drag === which ? "grabbing" : "grab",
              touchAction: "none",
            }}/>
        ))}
      </div>

      {/* Min/Max axis labels */}
      <div style={{ display: "flex", justifyContent: "space-between",
        fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)",
        fontVariantNumeric: "tabular-nums", marginTop: 2 }}>
        <span>{fmtV(min)}{unit}</span>
        <span>{fmtV(max)}{unit}</span>
      </div>
    </div>
  );
};

const Watchlists = ({ navigate }) => {
  const lists = [
    { id: 1, name: "Tech Watch",   count: 8, lastView: "今日 09:14" },
    { id: 2, name: "Value Picks",  count: 12, lastView: "昨日" },
    { id: 3, name: "JP Auto",      count: 4, lastView: "3日前" },
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, letterSpacing: "-0.01em", margin: 0, color: "var(--fg-1)" }}>ウォッチリスト</h1>
        <Button variant="primary" icon="plus">リスト作成</Button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
        {lists.map(l => (
          <div key={l.id} style={{
            background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8, padding: 18,
            cursor: "pointer", display: "flex", flexDirection: "column", gap: 4,
          }}
          onMouseEnter={e => e.currentTarget.style.borderColor = "var(--border-strong)"}
          onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border)"}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ font: "600 14px var(--font-sans)", color: "var(--fg-1)" }}>{l.name}</span>
              <Icon name="moreH" size={14} style={{ color: "var(--fg-3)" }}/>
            </div>
            <div style={{ font: "500 28px var(--font-mono)", color: "var(--fg-1)", fontVariantNumeric: "tabular-nums", letterSpacing: "-0.01em" }}>{l.count}</div>
            <div style={{ fontSize: 11, color: "var(--fg-3)", fontFamily: "var(--font-mono)" }}>銘柄 · {l.lastView}</div>
          </div>
        ))}
      </div>
    </div>
  );
};

const Login = () => (
  <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg)" }}>
    <div style={{ width: 360, padding: 32, background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 24 }}>
        <img src="../../assets/mark.svg" width="28" height="28" alt=""/>
        <span style={{ font: "700 14px var(--font-mono)", letterSpacing: "0.04em", color: "var(--fg-1)" }}>STOCK ANALYZER</span>
      </div>
      <h2 style={{ font: "600 18px var(--font-sans)", margin: "0 0 20px 0", color: "var(--fg-1)" }}>ログイン</h2>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div><Label>ユーザー名</Label><div style={{ marginTop: 6 }}><Input placeholder="admin" mono/></div></div>
        <div><Label>パスワード</Label><div style={{ marginTop: 6 }}><Input type="password" placeholder="••••••••" mono/></div></div>
        <Button variant="primary" style={{ width: "100%", justifyContent: "center", marginTop: 8 }}>ログイン</Button>
      </div>
      <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--border)", fontSize: 11, color: "var(--fg-3)", fontFamily: "var(--font-mono)", textAlign: "center" }}>
        ローカル認証 · single-user mode
      </div>
    </div>
  </div>
);

Object.assign(window, { Screening, Watchlists, Login });
