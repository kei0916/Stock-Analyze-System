// Atomic components shared across screens.

const Icon = ({ name, size = 16, ...props }) => {
  const paths = {
    search: <><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></>,
    refresh: <path d="M21 12a9 9 0 1 1-3.8-7.3M21 5v5h-5"/>,
    bookmark: <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>,
    filter: <path d="M3 6h18M7 12h10M11 18h2"/>,
    target: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/></>,
    zap: <path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"/>,
    chart: <path d="M3 12h4l3-9 4 18 3-9h4"/>,
    sparkles: <path d="M12 3l1.6 5h5.4l-4.4 3.2 1.7 5.3L12 13.6 7.7 16.5l1.7-5.3L5 8h5.4z"/>,
    file: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></>,
    upRight: <path d="M7 17l10-10M9 7h8v8"/>,
    downRight: <path d="M7 7l10 10M9 17h8V9"/>,
    external: <path d="M14 4h6v6M10 14L20 4M14 12v6H4V8h6"/>,
    user: <><circle cx="12" cy="12" r="9"/><circle cx="12" cy="10" r="3"/><path d="M6.5 19a6 6 0 0 1 11 0"/></>,
    logout: <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>,
    chevDown: <path d="M6 9l6 6 6-6"/>,
    chevRight: <path d="M9 6l6 6-6 6"/>,
    plus: <path d="M12 5v14M5 12h14"/>,
    x: <path d="M18 6L6 18M6 6l12 12"/>,
    check: <path d="M5 12l5 5L20 7"/>,
    arrowRight: <path d="M5 12h14M13 6l6 6-6 6"/>,
    moreH: <><circle cx="6" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="18" cy="12" r="1.5"/></>,
  };
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor"
      strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...props}>
      {paths[name]}
    </svg>
  );
};

const Button = ({ variant = "secondary", size = "md", icon, children, onClick, disabled, type, style }) => {
  const base = {
    fontFamily: "var(--font-sans)", fontWeight: 500, borderRadius: 6,
    border: "1px solid transparent", cursor: disabled ? "not-allowed" : "pointer",
    display: "inline-flex", alignItems: "center", gap: 6,
    transition: "background 120ms var(--ease-snap), border-color 120ms var(--ease-snap)",
    opacity: disabled ? 0.5 : 1,
  };
  const sizes = {
    sm: { padding: "5px 10px", fontSize: 12 },
    md: { padding: "8px 14px", fontSize: 13 },
  };
  const variants = {
    primary:   { background: "var(--accent)", color: "var(--accent-fg)" },
    secondary: { background: "var(--surface-2)", color: "var(--fg-1)", borderColor: "var(--border-strong)" },
    ghost:     { background: "transparent", color: "var(--fg-1)" },
    danger:    { background: "transparent", color: "var(--down)", borderColor: "var(--border-strong)" },
  };
  return (
    <button type={type || "button"} className={`btn btn-${variant}`} onClick={onClick} disabled={disabled}
      style={{ ...base, ...sizes[size], ...variants[variant], ...style }}>
      {icon && <Icon name={icon} size={size === "sm" ? 12 : 14}/>}
      {children}
    </button>
  );
};

const Input = ({ value, onChange, placeholder, mono, style, error, type = "text" }) => (
  <input type={type} value={value} onChange={e => onChange?.(e.target.value)} placeholder={placeholder}
    style={{
      background: "var(--surface)", border: `1px solid ${error ? "var(--down)" : "var(--border-strong)"}`,
      borderRadius: 6, color: "var(--fg-1)", padding: "8px 12px", width: "100%", boxSizing: "border-box",
      fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)", fontSize: 13, fontWeight: 500,
      fontVariantNumeric: mono ? "tabular-nums" : "normal", outline: "none",
      ...style,
    }}/>
);

const Label = ({ children, style }) => (
  <span style={{
    fontSize: 11, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase",
    color: "var(--fg-2)", ...style,
  }}>{children}</span>
);

const Badge = ({ children, variant = "neutral", mono, style }) => {
  const variants = {
    neutral: { background: "var(--surface-2)", color: "var(--fg-2)", border: "1px solid var(--border)" },
    accent:  { background: "var(--accent-soft)", color: "var(--accent)", border: "1px solid transparent" },
    up:      { background: "var(--up-soft)", color: "var(--up)", border: "1px solid transparent" },
    down:    { background: "var(--down-soft)", color: "var(--down)", border: "1px solid transparent" },
    solid:   { background: "var(--accent)", color: "var(--accent-fg)", border: "1px solid transparent" },
  };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 8px", borderRadius: 4,
      fontSize: 11, fontWeight: 500, lineHeight: 1,
      fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)",
      fontVariantNumeric: mono ? "tabular-nums" : "normal",
      ...variants[variant], ...style,
    }}>{children}</span>
  );
};

const Segmented = ({ options, value, onChange }) => (
  <div style={{
    display: "inline-flex", background: "var(--surface-2)", border: "1px solid var(--border)",
    borderRadius: 6, padding: 2,
  }}>
    {options.map(opt => {
      const active = opt.value === value;
      return (
        <button key={opt.value} onClick={() => onChange(opt.value)} style={{
          background: active ? "var(--surface)" : "transparent",
          color: active ? "var(--fg-1)" : "var(--fg-2)",
          border: 0, borderRadius: 4, padding: "5px 12px", cursor: "pointer",
          font: "500 12px var(--font-sans)",
          boxShadow: active ? "0 1px 2px rgba(0,0,0,.4)" : "none",
        }}>{opt.label}</button>
      );
    })}
  </div>
);

const Tabs = ({ tabs, value, onChange }) => (
  <div style={{ display: "flex", borderBottom: "1px solid var(--border)" }}>
    {tabs.map(t => {
      const active = t.value === value;
      return (
        <button key={t.value} onClick={() => onChange(t.value)} style={{
          background: "transparent", border: 0,
          color: active ? "var(--fg-1)" : "var(--fg-2)",
          font: "500 13px var(--font-sans)",
          padding: "10px 16px", cursor: "pointer",
          borderBottom: `2px solid ${active ? "var(--accent)" : "transparent"}`,
          marginBottom: -1,
        }}>{t.label}</button>
      );
    })}
  </div>
);

const KpiTile = ({ label, value, delta, deltaDirection }) => (
  <div style={{
    border: "1px solid var(--border)", borderRadius: 8, padding: 16, background: "var(--surface)",
    display: "flex", flexDirection: "column", gap: 4,
  }}>
    <Label>{label}</Label>
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: 24, fontWeight: 600, color: "var(--fg-1)",
      fontVariantNumeric: "tabular-nums", letterSpacing: "-0.01em", lineHeight: 1.1,
    }}>{value}</div>
    {delta && (
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: 11, fontVariantNumeric: "tabular-nums",
        color: deltaDirection === "up" ? "var(--up)" : deltaDirection === "down" ? "var(--down)" : "var(--fg-2)",
      }}>
        {deltaDirection === "up" ? "↗ " : deltaDirection === "down" ? "↘ " : ""}{delta}
      </div>
    )}
  </div>
);

const Panel = ({ title, action, children, style, padding = 16 }) => (
  <section style={{
    background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8,
    overflow: "hidden", ...style,
  }}>
    {title && (
      <header style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "12px 16px", borderBottom: "1px solid var(--border)",
      }}>
        <h3 style={{ font: "600 13px var(--font-sans)", color: "var(--fg-1)", margin: 0 }}>{title}</h3>
        {action}
      </header>
    )}
    <div style={{ padding }}>{children}</div>
  </section>
);

const fmt = {
  num: (v, d = 0) => v == null ? "—" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }),
  pct: (v, d = 1) => v == null ? "—" : `${(v * 100).toFixed(d)}%`,
  ratio: (v, d = 2) => v == null ? "—" : Number(v).toFixed(d),
  large: (v) => {
    if (v == null) return "—";
    const abs = Math.abs(v);
    if (abs >= 1e12) return (v / 1e12).toFixed(2) + "T";
    if (abs >= 1e9)  return (v / 1e9 ).toFixed(2) + "B";
    if (abs >= 1e6)  return (v / 1e6 ).toFixed(2) + "M";
    if (abs >= 1e3)  return (v / 1e3 ).toFixed(2) + "k";
    return v.toFixed(2);
  },
  delta: (v, d = 1) => v == null ? "—" : (v >= 0 ? "+" : "") + (v * 100).toFixed(d) + "%",
};

Object.assign(window, { Icon, Button, Input, Label, Badge, Segmented, Tabs, KpiTile, Panel, fmt });
