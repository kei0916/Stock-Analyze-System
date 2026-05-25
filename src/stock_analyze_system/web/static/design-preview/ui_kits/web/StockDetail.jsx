// Stock Detail screen with 5 tabs.

const StockDetail = ({ companyId = "US_AAPL", navigate }) => {
  const [tab, setTab] = React.useState("financials");
  const [period, setPeriod] = React.useState("annual");
  const [metric, setMetric] = React.useState("revenue");
  const c = MOCK_COMPANIES.find(c => c.id === companyId) || MOCK_COMPANIES[0];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <Badge mono>{c.market}</Badge>
            <Badge mono>{c.standard}</Badge>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-3)" }}>{c.id}</span>
          </div>
          <h1 style={{ fontSize: 26, fontWeight: 700, letterSpacing: "-0.01em", margin: 0, color: "var(--fg-1)" }}>
            {c.name_ja} <span style={{ color: "var(--fg-3)", fontWeight: 500 }}>· {c.name}</span>
          </h1>
          <div style={{ display: "flex", gap: 16, marginTop: 8, alignItems: "baseline" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 28, fontWeight: 600, color: "var(--fg-1)", fontVariantNumeric: "tabular-nums", letterSpacing: "-0.01em" }}>
              {fmt.num(c.price, 2)}
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: c.change1y >= 0 ? "var(--up)" : "var(--down)", fontVariantNumeric: "tabular-nums" }}>
              {c.change1y >= 0 ? "↗ " : "↘ "}{fmt.delta(c.change1y)} (1Y)
            </span>
            <span style={{ fontSize: 12, color: "var(--fg-3)", fontFamily: "var(--font-mono)" }}>· 時価総額 {fmt.large(c.marketCap)}</span>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <Button variant="secondary" icon="bookmark">ウォッチに追加</Button>
          <Button variant="secondary" icon="refresh">同期</Button>
          <Button variant="primary" icon="sparkles">LLM分析</Button>
        </div>
      </div>

      {/* KPI tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
        <KpiTile label="PER" value={fmt.ratio(c.per)} delta="+2.1" deltaDirection="up"/>
        <KpiTile label="PBR" value={fmt.ratio(c.pbr)} delta="+5.4" deltaDirection="up"/>
        <KpiTile label="EV/EBITDA" value={fmt.ratio(c.evEbitda)} delta="−0.8" deltaDirection="down"/>
        <KpiTile label="PSR" value={fmt.ratio(c.psr)} delta="+0.4" deltaDirection="up"/>
        <KpiTile label="FCF Yield" value={fmt.pct(c.fcfYield)} delta="−0.4pp" deltaDirection="down"/>
      </div>

      {/* Tabs */}
      <div style={{ position: "sticky", top: "var(--topbar-h)", background: "var(--bg)", zIndex: 4 }}>
        <Tabs value={tab} onChange={setTab} tabs={[
          { value: "financials", label: "財務" },
          { value: "valuation",  label: "バリュエーション" },
          { value: "analysis",   label: "分析" },
          { value: "filings",    label: "ファイリング" },
        ]}/>
      </div>

      {tab === "financials" && <FinancialsTab period={period} setPeriod={setPeriod} metric={metric} setMetric={setMetric}/>}
      {tab === "valuation"  && <ValuationTab/>}
      {tab === "analysis"   && <AnalysisTab company={c}/>}
      {tab === "filings"    && <FilingsTab/>}
    </div>
  );
};

const ComboChart = ({ data, metric }) => {
  // Compute YoY growth %; first year is null.
  const series = data.map((d, i) => {
    const prev = i > 0 ? data[i - 1][metric] : null;
    const curr = d[metric];
    const yoy = prev != null && prev !== 0 ? (curr - prev) / Math.abs(prev) : null;
    return { fy: d.fy, value: curr, yoy };
  });

  const w = 800, h = 260;
  const padL = 60, padR = 60, padT = 24, padB = 36;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;

  const values = series.map(s => s.value);
  const maxV = Math.max(...values);
  const yoys = series.map(s => s.yoy).filter(v => v != null);
  const maxY = Math.max(...yoys, 0.05);
  const minY = Math.min(...yoys, -0.05);
  const yoyRange = Math.max(Math.abs(maxY), Math.abs(minY));
  const yoyMax = yoyRange * 1.2;
  const yoyMin = -yoyMax;

  const n = series.length;
  const slot = innerW / n;
  const barW = Math.min(56, slot * 0.5);
  const barX = (i) => padL + slot * i + slot / 2 - barW / 2;
  const barY = (v) => padT + (1 - v / maxV) * innerH;
  const barH = (v) => (v / maxV) * innerH;

  const pointX = (i) => padL + slot * i + slot / 2;
  const pointY = (v) => padT + (1 - (v - yoyMin) / (yoyMax - yoyMin)) * innerH;
  const zeroY = pointY(0);

  const linePts = series.map((s, i) => s.yoy == null ? null : `${pointX(i)},${pointY(s.yoy)}`).filter(Boolean);
  const linePath = linePts.length ? "M" + linePts.join(" L") : "";

  const leftTicks = Array.from({ length: 5 }, (_, i) => maxV * (1 - i / 4));
  const rightTicks = Array.from({ length: 5 }, (_, i) => yoyMax - (i / 4) * (yoyMax - yoyMin));

  const fmtAbs = (v) => {
    const a = Math.abs(v);
    if (a >= 1000) return (v / 1000).toFixed(0) + "B";
    return v.toFixed(0) + "M";
  };
  const fmtFull = (v) => v.toLocaleString("en-US", { maximumFractionDigits: 0 }) + " M";
  const tick = { fontFamily: "JetBrains Mono", fontSize: 10, fill: "#5C636E" };

  // ---------- Hover state ----------
  const svgRef = React.useRef(null);
  const [hover, setHover] = React.useState(null); // index | null

  const onMove = (e) => {
    const svg = svgRef.current;
    if (!svg) return;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const ctm = svg.getScreenCTM();
    if (!ctm) return;
    const local = pt.matrixTransform(ctm.inverse());
    if (local.x < padL || local.x > w - padR || local.y < padT || local.y > padT + innerH) {
      setHover(null); return;
    }
    const idx = Math.max(0, Math.min(n - 1, Math.floor((local.x - padL) / slot)));
    setHover(idx);
  };

  const cur = hover != null ? series[hover] : null;
  const tipX = cur ? pointX(hover) : 0;
  // tooltip width ~150; flip when near right edge
  const tipW = 168, tipH = 76;
  const tipLeft = cur ? Math.max(padL + 4, Math.min(w - padR - tipW - 4, tipX - tipW / 2)) : 0;
  const tipTop = padT + 6;

  return (
    <div>
      <svg ref={svgRef} viewBox={`0 0 ${w} ${h}`} width="100%" height={h}
           style={{ display: "block" }}
           onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {/* Grid + axis labels */}
        {leftTicks.map((v, i) => {
          const yPos = padT + (i / 4) * innerH;
          return (
            <g key={i}>
              <line x1={padL} y1={yPos} x2={w - padR} y2={yPos} stroke="#22272F" strokeWidth="1"/>
              <text x={padL - 8} y={yPos + 3} textAnchor="end" {...tick} style={{ fontVariantNumeric: "tabular-nums" }}>
                {fmtAbs(v)}
              </text>
              <text x={w - padR + 8} y={yPos + 3} textAnchor="start" {...tick} style={{ fontVariantNumeric: "tabular-nums" }}>
                {(rightTicks[i] * 100).toFixed(0)}%
              </text>
            </g>
          );
        })}

        <line x1={padL} y1={padT} x2={padL} y2={padT + innerH} stroke="#2D333C" strokeWidth="1"/>
        <line x1={w - padR} y1={padT} x2={w - padR} y2={padT + innerH} stroke="#2D333C" strokeWidth="1"/>
        <line x1={padL} y1={padT + innerH} x2={w - padR} y2={padT + innerH} stroke="#2D333C" strokeWidth="1"/>

        {yoyMin < 0 && yoyMax > 0 && (
          <line x1={padL} y1={zeroY} x2={w - padR} y2={zeroY} stroke="#5C636E" strokeWidth="1" strokeDasharray="3 3"/>
        )}

        {/* Hover crosshair (behind data) */}
        {cur && (
          <line x1={tipX} y1={padT} x2={tipX} y2={padT + innerH}
                stroke="#22D3EE" strokeWidth="1" strokeDasharray="2 3" opacity="0.7"/>
        )}

        {/* Bars */}
        {series.map((s, i) => (
          <g key={s.fy}>
            <rect x={barX(i)} y={barY(s.value)} width={barW} height={barH(s.value)}
                  fill="#22D3EE" opacity={hover == null || hover === i ? 0.55 : 0.22} rx="2"
                  style={{ transition: "opacity 80ms linear" }}/>
            <text x={pointX(i)} y={padT + innerH + 18}
                  fill={hover === i ? "#F2F4F7" : "#A1A6AE"}
                  fontFamily="JetBrains Mono" fontSize="11" textAnchor="middle">{s.fy}</text>
          </g>
        ))}

        {/* YoY line */}
        {linePath && <path d={linePath} stroke="#F2F4F7" strokeWidth="1.8" fill="none" strokeLinejoin="round" strokeLinecap="round"/>}
        {series.map((s, i) => s.yoy == null ? null : (
          <g key={"pt" + i}>
            <circle cx={pointX(i)} cy={pointY(s.yoy)} r={hover === i ? 5 : 3.5}
                    fill="#0B0D10" stroke="#F2F4F7" strokeWidth="1.6"/>
            {hover !== i && (
              <text x={pointX(i)} y={pointY(s.yoy) - 9} textAnchor="middle"
                    fontFamily="JetBrains Mono" fontSize="10" fill={s.yoy >= 0 ? "#22C55E" : "#EF4444"}
                    style={{ fontVariantNumeric: "tabular-nums" }}>
                {(s.yoy >= 0 ? "+" : "") + (s.yoy * 100).toFixed(1) + "%"}
              </text>
            )}
          </g>
        ))}

        {/* Axis titles */}
        <text x={16} y={padT + innerH / 2} textAnchor="middle"
              transform={`rotate(-90 16 ${padT + innerH / 2})`}
              fontFamily="Inter" fontSize="10" fill="#A1A6AE" letterSpacing="0.08em">金額 (USD)</text>
        <text x={w - 14} y={padT + innerH / 2} textAnchor="middle"
              transform={`rotate(90 ${w - 14} ${padT + innerH / 2})`}
              fontFamily="Inter" fontSize="10" fill="#A1A6AE" letterSpacing="0.08em">前年比 (%)</text>

        {/* Tooltip */}
        {cur && (
          <g style={{ pointerEvents: "none" }}>
            <rect x={tipLeft} y={tipTop} width={tipW} height={tipH} rx="6"
                  fill="#171B21" stroke="#2D333C"/>
            <text x={tipLeft + 12} y={tipTop + 18}
                  fontFamily="JetBrains Mono" fontSize="11" fill="#F2F4F7" fontWeight="600"
                  letterSpacing="0.04em">{cur.fy}</text>
            <line x1={tipLeft + 12} y1={tipTop + 26} x2={tipLeft + tipW - 12} y2={tipTop + 26} stroke="#2D333C"/>
            <text x={tipLeft + 12} y={tipTop + 42} fontFamily="Inter" fontSize="10" fill="#A1A6AE">金額</text>
            <text x={tipLeft + tipW - 12} y={tipTop + 42} textAnchor="end"
                  fontFamily="JetBrains Mono" fontSize="11" fill="#F2F4F7"
                  style={{ fontVariantNumeric: "tabular-nums" }}>{fmtFull(cur.value)}</text>
            <text x={tipLeft + 12} y={tipTop + 60} fontFamily="Inter" fontSize="10" fill="#A1A6AE">前年比</text>
            <text x={tipLeft + tipW - 12} y={tipTop + 60} textAnchor="end"
                  fontFamily="JetBrains Mono" fontSize="11"
                  fill={cur.yoy == null ? "#5C636E" : cur.yoy >= 0 ? "#22C55E" : "#EF4444"}
                  style={{ fontVariantNumeric: "tabular-nums" }}>
              {cur.yoy == null ? "—" : (cur.yoy >= 0 ? "+" : "") + (cur.yoy * 100).toFixed(1) + "%"}
            </text>
          </g>
        )}
      </svg>

      {/* Legend */}
      <div style={{ display: "flex", gap: 18, justifyContent: "center", marginTop: 6, fontFamily: "var(--font-sans)", fontSize: 11, color: "var(--fg-2)" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 12, height: 10, background: "#22D3EE", opacity: 0.55, borderRadius: 2 }}/>金額
        </span>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 14, height: 2, background: "#F2F4F7" }}/>
          <span style={{ width: 7, height: 7, background: "#0B0D10", border: "1.5px solid #F2F4F7", borderRadius: 999, marginLeft: -10 }}/>
          前年比成長率
        </span>
      </div>
    </div>
  );
};

const FinancialsTab = ({ period, setPeriod, metric, setMetric }) => {
  const data = period === "quarterly" ? APPLE_FINANCIALS_QUARTERLY : APPLE_FINANCIALS_ANNUAL;
  const max = Math.max(...data.map(d => d.revenue));
  const metricOpts = [
    { value: "revenue", label: "売上高" },
    { value: "opIncome", label: "営業利益" },
    { value: "netIncome", label: "純利益" },
    { value: "ebitda", label: "EBITDA" },
    { value: "fcf", label: "FCF" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Segmented value={period} onChange={setPeriod} options={[
          { value: "annual", label: "通期" },
          { value: "quarterly", label: "四半期" },
        ]}/>
        <div style={{ display: "flex", gap: 4 }}>
          {metricOpts.map(o => (
            <button key={o.value} onClick={() => setMetric(o.value)} style={{
              background: metric === o.value ? "var(--surface-2)" : "transparent",
              border: `1px solid ${metric === o.value ? "var(--border-strong)" : "var(--border)"}`,
              color: metric === o.value ? "var(--fg-1)" : "var(--fg-2)",
              borderRadius: 4, font: "500 12px var(--font-sans)", padding: "5px 10px", cursor: "pointer",
            }}>{o.label}</button>
          ))}
        </div>
      </div>

      <Panel title={`${metricOpts.find(m => m.value === metric)?.label} 推移`} padding={16}>
        <ComboChart data={data} metric={metric}/>
      </Panel>

      <Panel title="財務サマリ" padding={0}
        action={<span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)" }}>単位: 百万USD (EPS除く)</span>}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>{["項目", ...data.map(d => d.fy)].map((h, i) => (
            <th key={i} style={{
              textAlign: i === 0 ? "left" : "right",
              font: "500 11px var(--font-sans)", letterSpacing: "0.06em", textTransform: "uppercase",
              color: "var(--fg-2)", padding: "10px 16px", borderBottom: "1px solid var(--border-strong)",
            }}>{h}</th>
          ))}</tr></thead>
          <tbody>
            {[
              { k: "売上高", f: "revenue" },
              { k: "営業利益", f: "opIncome" },
              { k: "純利益", f: "netIncome" },
              { k: "EBITDA", f: "ebitda" },
              { k: "EPS", f: "eps" },
            ].map(row => (
              <tr key={row.f}>
                <td style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", color: "var(--fg-2)", fontSize: 13 }}>{row.k}</td>
                {data.map(d => (
                  <td key={d.fy} style={{ ...numCellStyle, color: "var(--fg-1)" }}>
                    {row.f === "eps" ? fmt.ratio(d[row.f]) : fmt.num(d[row.f])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel title="財務指標" padding={0}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr>{["カテゴリ", "指標", "値", "前年比"].map((h, i) => (
            <th key={i} style={{
              textAlign: i >= 2 ? "right" : "left",
              font: "500 11px var(--font-sans)", letterSpacing: "0.06em", textTransform: "uppercase",
              color: "var(--fg-2)", padding: "10px 16px", borderBottom: "1px solid var(--border-strong)",
            }}>{h}</th>
          ))}</tr></thead>
          <tbody>
            {[
              ["収益性", "営業利益率", "31.5%", "+0.8pp", "up"],
              ["収益性", "純利益率", "23.97%", "−1.4pp", "down"],
              ["収益性", "ROE", "156.2%", "+12.1pp", "up"],
              ["収益性", "ROA", "27.5%", "+1.2pp", "up"],
              ["効率性", "総資産回転率", "1.10", "+0.04", "up"],
              ["財務安全性", "自己資本比率", "17.5%", "−2.1pp", "down"],
              ["財務安全性", "流動比率", "0.99", "−0.05", "down"],
              ["財務安全性", "D/E", "1.51", "+0.18", "down"],
              ["成長性", "売上成長率", "+2.0%", "+13.5pp", "up"],
              ["成長性", "EPS成長率", "−0.8%", "+0.4pp", "up"],
            ].map((r, i) => (
              <tr key={i}>
                <td style={{ padding: "9px 16px", borderBottom: "1px solid var(--border)", color: "var(--fg-3)", fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>{r[0]}</td>
                <td style={{ padding: "9px 16px", borderBottom: "1px solid var(--border)", color: "var(--fg-1)", fontSize: 13 }}>{r[1]}</td>
                <td style={{ ...numCellStyle }}>{r[2]}</td>
                <td style={{ ...numCellStyle, color: r[4] === "up" ? "var(--up)" : "var(--down)" }}>{r[4] === "up" ? "↗ " : "↘ "}{r[3]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
};

const ValuationTab = () => {
  const series = APPLE_PER_SERIES;
  const max = Math.max(...series), min = Math.min(...series);
  const median = 26.4;
  const w = 800, h = 200, pad = 30;
  const path = series.map((v, i) => {
    const x = pad + (i / (series.length - 1)) * (w - pad * 2);
    const y = pad + (1 - (v - min) / (max - min)) * (h - pad * 2);
    return `${i === 0 ? "M" : "L"}${x},${y}`;
  }).join(" ");
  const area = path + ` L${w-pad},${h-pad} L${pad},${h-pad} Z`;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {[
        { title: "PER 推移 · 10年", series, suffix: "x", high: max, lo: min, med: median },
        { title: "PBR 推移 · 10年", series: series.map(v => v / 5.5), suffix: "x", high: max/5.5, lo: min/5.5, med: median/5.5 },
        { title: "PSR 推移 · 10年", series: series.map(v => v / 4), suffix: "x", high: max/4, lo: min/4, med: median/4 },
      ].map((cfg, idx) => (
        <Panel key={idx} title={cfg.title} action={
          <div style={{ display: "flex", gap: 12, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-2)" }}>
            <span>High <span style={{ color: "var(--fg-1)" }}>{cfg.high.toFixed(2)}</span></span>
            <span>Median <span style={{ color: "var(--fg-1)" }}>{cfg.med.toFixed(2)}</span></span>
            <span>Low <span style={{ color: "var(--fg-1)" }}>{cfg.lo.toFixed(2)}</span></span>
          </div>
        }>
          <ValSvg series={cfg.series} median={cfg.med}/>
        </Panel>
      ))}
    </div>
  );
};

const ValSvg = ({ series, median }) => {
  const max = Math.max(...series), min = Math.min(...series);
  const w = 800, h = 220;
  const padL = 52, padR = 16, padT = 16, padB = 32;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;
  const x = (i) => padL + (i / (series.length - 1)) * innerW;
  const y = (v) => padT + (1 - (v - min) / (max - min)) * innerH;
  const path = series.map((v, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(v)}`).join(" ");
  const area = path + ` L${x(series.length-1)},${padT+innerH} L${padL},${padT+innerH} Z`;

  // 36 monthly points → label by month/year
  // Series ends at "now" (2026-04). Step backwards.
  const endYear = 2026, endMonth = 4;
  const dateAt = (i) => {
    const monthsBack = (series.length - 1 - i);
    const totalMonths = endYear * 12 + endMonth - monthsBack;
    const yr = Math.floor(totalMonths / 12);
    const mo = totalMonths - yr * 12;
    return { year: yr, month: mo };
  };

  const yTicks = Array.from({ length: 5 }, (_, i) => min + (i / 4) * (max - min));
  const xTicks = [0, Math.floor((series.length - 1) / 3), Math.floor((series.length - 1) * 2 / 3), series.length - 1]
    .map(idx => ({ idx, label: `'${dateAt(idx).year.toString().slice(2)}` }));

  const gradId = "fade" + Math.round(median * 100);
  const tick = { fontFamily: "JetBrains Mono", fontSize: 10, fill: "#5C636E" };

  // ---------- Hover ----------
  const svgRef = React.useRef(null);
  const [hover, setHover] = React.useState(null);

  const onMove = (e) => {
    const svg = svgRef.current; if (!svg) return;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const ctm = svg.getScreenCTM(); if (!ctm) return;
    const local = pt.matrixTransform(ctm.inverse());
    if (local.x < padL || local.x > w - padR || local.y < padT || local.y > padT + innerH) {
      setHover(null); return;
    }
    const ratio = (local.x - padL) / innerW;
    const idx = Math.max(0, Math.min(series.length - 1, Math.round(ratio * (series.length - 1))));
    setHover(idx);
  };

  const cur = hover != null ? { idx: hover, value: series[hover], date: dateAt(hover) } : null;
  const tipW = 152, tipH = 60;
  const tipLeft = cur ? Math.max(padL + 4, Math.min(w - padR - tipW - 4, x(cur.idx) - tipW / 2)) : 0;
  const tipTop = padT + 6;
  const monthName = (mo) => `${mo}月`;

  return (
    <svg ref={svgRef} viewBox={`0 0 ${w} ${h}`} width="100%" height={h}
         style={{ display: "block" }}
         onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      <defs><linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
        <stop offset="0%" stopColor="#22D3EE" stopOpacity="0.25"/>
        <stop offset="100%" stopColor="#22D3EE" stopOpacity="0"/>
      </linearGradient></defs>

      {yTicks.map((v, i) => (
        <g key={i}>
          <line x1={padL} y1={y(v)} x2={w - padR} y2={y(v)} stroke="#22272F" strokeWidth="1"/>
          <text x={padL - 8} y={y(v) + 3} textAnchor="end" {...tick} style={{ fontVariantNumeric: "tabular-nums" }}>
            {v.toFixed(1)}x
          </text>
        </g>
      ))}

      <line x1={padL} y1={padT} x2={padL} y2={padT + innerH} stroke="#2D333C" strokeWidth="1"/>
      <line x1={padL} y1={padT + innerH} x2={w - padR} y2={padT + innerH} stroke="#2D333C" strokeWidth="1"/>

      {xTicks.map(t => (
        <g key={t.idx}>
          <line x1={x(t.idx)} y1={padT + innerH} x2={x(t.idx)} y2={padT + innerH + 4} stroke="#2D333C" strokeWidth="1"/>
          <text x={x(t.idx)} y={padT + innerH + 16} textAnchor="middle" {...tick}>{t.label}</text>
        </g>
      ))}

      <text x={padL - 44} y={padT + innerH / 2} textAnchor="middle" transform={`rotate(-90 ${padL - 44} ${padT + innerH / 2})`}
        fontFamily="Inter" fontSize="10" fill="#A1A6AE" letterSpacing="0.08em">倍率 (x)</text>
      <text x={padL + innerW / 2} y={h - 4} textAnchor="middle"
        fontFamily="Inter" fontSize="10" fill="#A1A6AE" letterSpacing="0.08em">年</text>

      {/* Hover crosshair */}
      {cur && (
        <line x1={x(cur.idx)} y1={padT} x2={x(cur.idx)} y2={padT + innerH}
              stroke="#22D3EE" strokeWidth="1" strokeDasharray="2 3" opacity="0.7"/>
      )}

      <path d={area} fill={`url(#${gradId})`}/>
      <path d={path} stroke="#22D3EE" strokeWidth="1.6" fill="none" strokeLinejoin="round" strokeLinecap="round"/>

      {/* median ref */}
      <line x1={padL} y1={y(median)} x2={w - padR} y2={y(median)} stroke="#5C636E" strokeWidth="1" strokeDasharray="3 3"/>
      <text x={w - padR - 4} y={y(median) - 4} textAnchor="end" {...tick} style={{ fill: "#A1A6AE" }}>median</text>

      <circle cx={x(series.length-1)} cy={y(series[series.length-1])} r="3" fill="#22D3EE"/>

      {/* Hover marker + tooltip */}
      {cur && (
        <g style={{ pointerEvents: "none" }}>
          <circle cx={x(cur.idx)} cy={y(cur.value)} r="4.5" fill="#0B0D10" stroke="#22D3EE" strokeWidth="1.8"/>
          <rect x={tipLeft} y={tipTop} width={tipW} height={tipH} rx="6" fill="#171B21" stroke="#2D333C"/>
          <text x={tipLeft + 12} y={tipTop + 18}
                fontFamily="JetBrains Mono" fontSize="11" fill="#F2F4F7" fontWeight="600"
                style={{ fontVariantNumeric: "tabular-nums" }}>
            {cur.date.year}年{monthName(cur.date.month)}
          </text>
          <line x1={tipLeft + 12} y1={tipTop + 26} x2={tipLeft + tipW - 12} y2={tipTop + 26} stroke="#2D333C"/>
          <text x={tipLeft + 12} y={tipTop + 46} fontFamily="Inter" fontSize="10" fill="#A1A6AE">倍率</text>
          <text x={tipLeft + tipW - 12} y={tipTop + 46} textAnchor="end"
                fontFamily="JetBrains Mono" fontSize="13" fill="#22D3EE" fontWeight="600"
                style={{ fontVariantNumeric: "tabular-nums" }}>{cur.value.toFixed(2)}x</text>
        </g>
      )}
    </svg>
  );
};

const AnalysisTab = ({ company }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
    {[
      { type: "business_summary", title: "事業概要", body: "Appleは、iPhone・Mac・iPad・Wearables・Servicesの5セグメントで事業を展開する。Servicesセグメント (App Store, iCloud, Apple Music) は売上の約25%を占め、最も高い粗利率 (~74%) を持つ。Productsの粗利率は約36%。" },
      { type: "risk_factors", title: "リスク要因", body: "(1) サプライチェーンの中国集中。組立の大部分を中国本土と台湾に依存。(2) iPhone単一プロダクト依存。売上の約52%。(3) 為替変動リスク。海外売上が60%超のため米ドル高で逆風。(4) 規制環境。EU DMA、米司法省訴訟。" },
      { type: "mda", title: "経営陣による議論と分析", body: "FY2024は売上 $391.0B (+2.0% YoY)、純利益 $93.7B。Servicesは過去最高の四半期売上を記録。新興市場での iPhone販売が伸長。次年度はApple Intelligenceの段階的展開が成長ドライバー。" },
    ].map(a => (
      <Panel key={a.type} title={a.title} action={
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Badge variant="accent" mono>gpt-oss-20b</Badge>
          <span style={{ fontSize: 11, color: "var(--fg-3)", fontFamily: "var(--font-mono)" }}>generated 2026-04-25</span>
        </div>
      }>
        <p style={{ margin: 0, lineHeight: 1.65, color: "var(--fg-1)", fontSize: 13 }}>{a.body}</p>
      </Panel>
    ))}
    <Panel title="RAG Q&A" action={<Badge variant="up" mono><span style={{ width: 5, height: 5, borderRadius: 999, background: "currentColor" }}/>indexed</Badge>}>
      <div style={{ fontSize: 12, color: "var(--fg-2)", marginBottom: 10 }}>10-K (FY2024) · 142 ページ · 47 ノード · ollama/gptoss20b:q8</div>
      <div style={{ display: "flex", gap: 8 }}>
        <input placeholder="ファイリングに質問する…" style={{
          flex: 1, background: "var(--surface-2)", border: "1px solid var(--border-strong)",
          borderRadius: 6, padding: "8px 12px", color: "var(--fg-1)", fontSize: 13, outline: "none",
        }}/>
        <Button variant="primary">質問</Button>
      </div>
    </Panel>
  </div>
);

const FilingsTab = () => (
  <Panel title="ファイリング" padding={0}>
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead><tr>{["タイプ", "期間", "提出日", "Source", "Accession", ""].map((h, i) => (
        <th key={i} style={{
          textAlign: "left", font: "500 11px var(--font-sans)", letterSpacing: "0.06em", textTransform: "uppercase",
          color: "var(--fg-2)", padding: "10px 16px", borderBottom: "1px solid var(--border-strong)",
        }}>{h}</th>
      ))}</tr></thead>
      <tbody>
        {[
          { t: "10-K", fy: "FY2024", filed: "2024-11-01", acc: "0000320193-24-000123" },
          { t: "10-Q", fy: "Q3 2024", filed: "2024-08-02", acc: "0000320193-24-000091" },
          { t: "10-Q", fy: "Q2 2024", filed: "2024-05-03", acc: "0000320193-24-000071" },
          { t: "10-Q", fy: "Q1 2024", filed: "2024-02-02", acc: "0000320193-24-000051" },
          { t: "10-K", fy: "FY2023", filed: "2023-11-03", acc: "0000320193-23-000106" },
        ].map(f => (
          <tr key={f.acc} style={{ cursor: "pointer" }}
            onMouseEnter={e => e.currentTarget.style.background = "var(--surface-2)"}
            onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
            <td style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)" }}><Badge mono>{f.t}</Badge></td>
            <td style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", color: "var(--fg-1)", fontSize: 13 }}>{f.fy}</td>
            <td style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", color: "var(--fg-1)", fontFamily: "var(--font-mono)", fontSize: 12 }}>{f.filed}</td>
            <td style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)" }}><Badge mono>SEC</Badge></td>
            <td style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", color: "var(--fg-2)", fontFamily: "var(--font-mono)", fontSize: 11 }}>{f.acc}</td>
            <td style={{ padding: "10px 16px", borderBottom: "1px solid var(--border)", color: "var(--accent)" }}><Icon name="external" size={14}/></td>
          </tr>
        ))}
      </tbody>
    </table>
  </Panel>
);

Object.assign(window, { StockDetail });
