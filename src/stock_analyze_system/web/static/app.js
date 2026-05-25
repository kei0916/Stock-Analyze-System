(function () {
    const ASSET_VERSION = document.currentScript
        ? document.currentScript.dataset.assetVersion
        : "1";

    function debounce(fn, wait) {
        let timer = null;
        return (...args) => {
            window.clearTimeout(timer);
            timer = window.setTimeout(() => fn(...args), wait);
        };
    }

    function fmtNumber(value) {
        if (value === null || value === undefined || value === "") {
            return "—";
        }
        if (typeof value === "number") {
            return value.toLocaleString("en-US");
        }
        return String(value);
    }

    function fmtPercent(value) {
        if (value === null || value === undefined || value === "") {
            return "—";
        }
        return `${(value * 100).toFixed(1)}%`;
    }

    function fmtDateTime(value) {
        if (!value) {
            return "—";
        }
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return String(value);
        }
        return date.toLocaleString("ja-JP");
    }

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

    async function fetchJson(url, options) {
        const response = await fetch(url, options);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
    }

    function dispatchAnalysisJobsChanged() {
        window.dispatchEvent(new CustomEvent("analysis-jobs:changed"));
    }

    function safeSessionGet(key) {
        try {
            return window.sessionStorage.getItem(key);
        } catch (_) {
            return null;
        }
    }

    function safeSessionSet(key, value) {
        try {
            window.sessionStorage.setItem(key, value);
        } catch (_) {
            // ignore storage restrictions
        }
    }

    function initSearch() {
        const input = document.querySelector("[data-stock-search]");
        const results = document.getElementById("search-results");
        if (!input || !results) {
            return;
        }
        const url = input.dataset.searchUrl;
        let latestSearchToken = 0;
        let activeSearchController = null;
        const runSearch = debounce((token, query) => {
            if (!query) {
                return;
            }
            const controller = new AbortController();
            activeSearchController = controller;
            fetch(`${url}?q=${encodeURIComponent(query)}`, { signal: controller.signal })
                .then((response) => {
                    if (!response.ok) {
                        throw new Error(`HTTP ${response.status}`);
                    }
                    return response.text();
                })
                .then((html) => {
                    if (controller.signal.aborted) {
                        return;
                    }
                    if (token !== latestSearchToken || input.value.trim() !== query) {
                        return;
                    }
                    results.innerHTML = html;
                })
                .catch((error) => {
                    if (controller.signal.aborted || token !== latestSearchToken) {
                        return;
                    }
                    results.textContent = `検索エラー: ${error.message}`;
                })
                .finally(() => {
                    if (activeSearchController === controller) {
                        activeSearchController = null;
                    }
                });
        }, 300);
        input.addEventListener("input", () => {
            const query = input.value.trim();
            latestSearchToken += 1;
            const token = latestSearchToken;
            if (activeSearchController) {
                activeSearchController.abort();
                activeSearchController = null;
            }
            if (!query) {
                results.innerHTML = "";
            }
            runSearch(token, query);
        });
    }

    function initTabs() {
        document.querySelectorAll("[data-tabs]").forEach((root) => {
            const defaultTab = root.dataset.defaultTab;
            const buttons = root.querySelectorAll("[data-tab-target]");
            const panels = root.querySelectorAll("[data-tab-panel]");
            const validTabs = new Set(
                [...panels].map((panel) => panel.dataset.tabPanel),
            );

            function activate(tab) {
                buttons.forEach((button) => {
                    const active = button.dataset.tabTarget === tab;
                    button.dataset.active = active ? "true" : "false";
                });
                panels.forEach((panel) => {
                    panel.hidden = panel.dataset.tabPanel !== tab;
                });
            }

            function hashTab() {
                const params = new URLSearchParams(window.location.hash.slice(1));
                const tab = params.get("tab");
                return validTabs.has(tab) ? tab : null;
            }

            function activateInitialOrHashTab() {
                activate(hashTab() || defaultTab);
            }

            buttons.forEach((button) => {
                button.addEventListener("click", () => activate(button.dataset.tabTarget));
            });
            window.addEventListener("hashchange", activateInitialOrHashTab);
            activateInitialOrHashTab();
        });
    }

    const FINANCIAL_CHART_FIELDS = [
        { key: "revenue",          label: "売上高",     unit: "currency-large" },
        { key: "gross_profit",     label: "粗利益",     unit: "currency-large" },
        { key: "operating_income", label: "営業利益",   unit: "currency-large" },
        { key: "net_income",       label: "純利益",     unit: "currency-large" },
        { key: "ebitda",           label: "EBITDA",    unit: "currency-large" },
        { key: "operating_cf",     label: "営業CF",    unit: "currency-large" },
        { key: "capex",            label: "設備投資",   unit: "currency-large" },
        { key: "fcf",              label: "FCF",       unit: "currency-large" },
        { key: "eps",              label: "EPS",       unit: "currency" },
    ];
    const FINANCIAL_DEFAULT_FIELDS = ["revenue", "operating_income", "net_income"];

    const VALUATION_CHART_FIELDS = [
        { key: "per",         label: "PER",        unit: "ratio" },
        { key: "pbr",         label: "PBR",        unit: "ratio" },
        { key: "psr",         label: "PSR",        unit: "ratio" },
        { key: "ev_ebitda",   label: "EV/EBITDA",  unit: "ratio" },
        { key: "fcf_yield",   label: "FCF Yield",  unit: "percent" },
        { key: "stock_price", label: "株価",        unit: "currency" },
    ];
    const VALUATION_DEFAULT_FIELDS = ["per", "pbr", "psr"];

    function chartTheme() {
        const styles = getComputedStyle(document.documentElement);
        const get = (name, fallback) => (styles.getPropertyValue(name) || "").trim() || fallback;
        return {
            bar:  get("--accent",  "#22D3EE"),
            line: get("--fg-1",    "#F2F4F7"),
            grid: get("--border",  "#22272F"),
            edge: get("--border-strong", "#2D333C"),
            axis: get("--fg-3",    "#5C636E"),
            mute: get("--fg-2",    "#A1A6AE"),
            bg:   get("--bg",      "#0B0D10"),
        };
    }

    function toYearMonth(value) {
        if (!value) return "";
        const s = String(value);
        const m = s.match(/^(\d{4})-(\d{2})/);
        return m ? `${m[1]}-${m[2]}` : s;
    }

    function formatYTick(unit, v) {
        if (v == null || !Number.isFinite(v)) return "";
        if (unit === "currency-large") {
            const abs = Math.abs(v);
            if (abs >= 1e6) return (v / 1e6).toFixed(0) + "T";
            if (abs >= 1e3) return (v / 1e3).toFixed(0) + "B";
            return v.toFixed(0) + "M";
        }
        if (unit === "percent") return (v * 100).toFixed(1) + "%";
        if (unit === "currency") return v.toFixed(2);
        // ratio
        return Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2);
    }

    function bindChartPicker({ chipsHost, addSelect, allFields, selectedFields, onChange }) {
        const labelOf = (key) => {
            const m = allFields.find((f) => f.key === key);
            return m ? m.label : key;
        };
        function refreshAddOptions() {
            if (!addSelect) return;
            const remaining = allFields.filter((f) => !selectedFields.includes(f.key));
            addSelect.replaceChildren();
            const placeholder = document.createElement("option");
            placeholder.value = "";
            placeholder.textContent = "+ フィールド追加";
            addSelect.appendChild(placeholder);
            remaining.forEach((f) => {
                const opt = document.createElement("option");
                opt.value = f.key;
                opt.textContent = f.label;
                addSelect.appendChild(opt);
            });
            addSelect.disabled = remaining.length === 0;
        }
        function renderChips() {
            if (!chipsHost) return;
            chipsHost.replaceChildren();
            selectedFields.forEach((key) => {
                const chip = document.createElement("button");
                chip.type = "button";
                chip.className = "chip-pill";
                chip.dataset.fieldKey = key;
                chip.title = "クリックで削除";
                const dot = document.createElement("span");
                dot.className = "chip-pill__dot";
                dot.style.background = "var(--accent)";
                chip.appendChild(dot);
                const lbl = document.createElement("span");
                lbl.textContent = labelOf(key);
                chip.appendChild(lbl);
                const x = document.createElement("span");
                x.className = "chip-pill__x";
                x.textContent = "×";
                chip.appendChild(x);
                chip.addEventListener("click", () => {
                    if (selectedFields.length <= 1) return;
                    const i = selectedFields.indexOf(key);
                    if (i >= 0) selectedFields.splice(i, 1);
                    renderChips();
                    refreshAddOptions();
                    onChange();
                });
                chipsHost.appendChild(chip);
            });
        }
        if (addSelect) {
            addSelect.addEventListener("change", () => {
                const key = addSelect.value;
                if (!key) return;
                addSelect.value = "";
                if (!selectedFields.includes(key)) {
                    selectedFields.push(key);
                    renderChips();
                    refreshAddOptions();
                    onChange();
                }
            });
        }
        return { render: () => { renderChips(); refreshAddOptions(); } };
    }

    const UNIT_LABEL = {
        "currency-large": "百万単位",
        "percent":        "%",
        "currency":       "通貨",
        "ratio":          "倍率",
    };

    function renderChartStack(host, rows, fields, dateKey, allFields, chartType = "bar-yoy") {
        host.replaceChildren();
        if (!rows || !rows.length) {
            const empty = document.createElement("p");
            empty.className = "chart-stack__empty";
            empty.textContent = "データがありません。";
            host.appendChild(empty);
            return;
        }
        const metaByKey = Object.fromEntries(allFields.map((f) => [f.key, f]));
        const renderer = chartType === "timeseries" ? renderTimeSeriesChart : renderFieldChart;
        fields.forEach((key) => {
            const meta = metaByKey[key];
            if (!meta) return;
            const card = document.createElement("div");
            card.className = "chart-stack__item";
            card.dataset.chartField = key;
            const head = document.createElement("div");
            head.className = "chart-stack__head";
            const title = document.createElement("h4");
            title.className = "chart-stack__title";
            title.textContent = meta.label;
            const unit = document.createElement("span");
            unit.className = "chart-stack__unit";
            unit.textContent = UNIT_LABEL[meta.unit] || "";
            head.appendChild(title);
            head.appendChild(unit);
            card.appendChild(head);
            const svgHost = document.createElement("div");
            svgHost.className = "chart-stack__svg";
            card.appendChild(svgHost);
            host.appendChild(card);
            renderer(svgHost, rows, {
                dateKey, fieldKey: key, label: meta.label, unit: meta.unit,
            });
        });
    }

    function initFinancialPanels() {
        document.querySelectorAll("[data-financial-panel]").forEach((panel) => {
            const companyId = panel.dataset.companyId;
            const select = panel.querySelector("[data-period-select]");
            const segmented = panel.querySelector("[data-period-segmented]");
            const tbody = panel.querySelector("[data-financial-body]");
            const summary = panel.querySelector("[data-financial-summary]");
            const chartsHost = panel.querySelector("[data-financial-charts]");
            const chipsHost = panel.querySelector("[data-fieldpicker-chips]");
            const addSelect = panel.querySelector("[data-fieldpicker-add]");

            const selectedFields = [...FINANCIAL_DEFAULT_FIELDS];
            let lastRows = [];

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

            function renderCharts() {
                if (chartsHost) {
                    renderChartStack(chartsHost, lastRows, selectedFields, "fiscal_year_end", FINANCIAL_CHART_FIELDS);
                }
            }

            const picker = bindChartPicker({
                chipsHost, addSelect,
                allFields: FINANCIAL_CHART_FIELDS,
                selectedFields,
                onChange: renderCharts,
            });

            async function load() {
                tbody.innerHTML = "";
                summary.textContent = "読み込み中…";
                const rows = await fetchJson(`/api/stocks/${companyId}/financials/${select.value}`);
                lastRows = rows;
                if (!rows.length) {
                    summary.textContent = "財務データがありません。";
                    renderEmptyRow(tbody, 5, "財務データがありません。");
                    if (chartsHost) chartsHost.replaceChildren();
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
                renderCharts();
            }

            picker.render();

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

    function initValuationPanels() {
        document.querySelectorAll("[data-valuation-panel]").forEach((panel) => {
            const companyId = panel.dataset.companyId;
            const tbody = panel.querySelector("[data-valuation-body]");
            const summary = panel.querySelector("[data-valuation-summary]");
            const chartsHost = panel.querySelector("[data-valuation-charts]");
            const chipsHost = panel.querySelector("[data-valuation-chips]");
            const addSelect = panel.querySelector("[data-valuation-add]");

            const selectedFields = [...VALUATION_DEFAULT_FIELDS];
            let lastRows = [];

            function renderCharts() {
                if (chartsHost) {
                    renderChartStack(chartsHost, lastRows, selectedFields, "date", VALUATION_CHART_FIELDS, "timeseries");
                }
            }

            const picker = bindChartPicker({
                chipsHost, addSelect,
                allFields: VALUATION_CHART_FIELDS,
                selectedFields,
                onChange: renderCharts,
            });
            picker.render();

            fetchJson(`/api/stocks/${companyId}/valuations?years=5`)
                .then((rows) => {
                    lastRows = rows;
                    if (!rows.length) {
                        summary.textContent = "バリュエーションデータがありません。";
                        renderEmptyRow(tbody, 6, "バリュエーションデータがありません。");
                        if (chartsHost) chartsHost.replaceChildren();
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
                    renderCharts();
                })
                .catch((error) => {
                    summary.textContent = `取得失敗: ${error.message}`;
                    renderEmptyRow(tbody, 6, "取得に失敗しました。");
                });
        });
    }

    const ANALYSIS_LABELS = {
        business_summary: "事業概要",
        risk_factors: "リスク要因",
        mda: "経営者による分析 (MD&A)",
        competitors: "競合分析",
    };
    const DEFAULT_ANALYSIS_TOTAL = Object.keys(ANALYSIS_LABELS).length;

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

    const SVG_NS = "http://www.w3.org/2000/svg";

    function svgEl(parent, tag, attrs, text) {
        const node = document.createElementNS(SVG_NS, tag);
        if (attrs) {
            for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
        }
        if (text != null) node.textContent = text;
        if (parent) parent.appendChild(node);
        return node;
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

    function renderLabeledNotice(label, body) {
        const root = el("div", "stack stack--sm");
        root.appendChild(el("p", "subtle small", label));
        if (body) root.appendChild(paragraph(body));
        return root;
    }

    function renderRawFallback(data) {
        if (typeof data === "object" && data !== null && "raw_answer" in data) {
            return renderLabeledNotice("※ JSONとしてパースできなかった生回答です:", data.raw_answer);
        }
        const root = el("div", "stack stack--sm");
        const pre = el("pre", "rag-pre");
        pre.textContent = JSON.stringify(data, null, 2);
        root.appendChild(pre);
        return root;
    }

    function renderAnalysisBody(type, data) {
        if (data && typeof data === "object" && "raw_answer" in data) return renderRawFallback(data);
        if (data && typeof data === "object" && data._status === "not_applicable") {
            return renderLabeledNotice("適用外: 該当章なし", data._message);
        }
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
        const prefix = isDefault ? "★既定: " : "";
        const suffixes = [];
        if (filing.content_available === false) {
            suffixes.push("[本体未取得]");
            if (filing.is_fallback_default) suffixes.push("（取得待ち）");
        }
        const suffix = suffixes.length ? ` ${suffixes.join(" ")}` : "";
        return `${prefix}${date} — ${typeLabel} (FY${filing.fiscal_year})${suffix}`;
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
            const warningBox = panel.querySelector("[data-rag-content-warning]");
            const question = panel.querySelector("[data-rag-question]");
            const button = panel.querySelector("[data-rag-ask]");
            const answerBlock = panel.querySelector("[data-rag-answer]");
            const answerText = panel.querySelector("[data-rag-answer-text]");
            const sourcePages = panel.querySelector("[data-rag-source-pages]");
            const sourceSections = panel.querySelector("[data-rag-source-sections]");

            const filingById = new Map();

            let analysesRequestToken = 0;

            function loadAnalyses(filingId) {
                const requestToken = ++analysesRequestToken;
                const isCurrentRequest = () => requestToken === analysesRequestToken;
                analysesBox.innerHTML = "";
                analysesBox.appendChild(el("p", "muted", "読み込み中…"));
                const url = filingId
                    ? `/api/stocks/${companyId}/rag/analyses?filing_id=${encodeURIComponent(filingId)}`
                    : `/api/stocks/${companyId}/rag/analyses`;
                return fetchJson(url)
                    .then((analyses) => {
                        if (!isCurrentRequest()) return;
                        renderAnalysesList(analysesBox, analyses, companyId);
                    })
                    .catch((error) => {
                        if (!isCurrentRequest()) return;
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
                    if (warningBox) warningBox.hidden = true;
                    return;
                }
                const parts = [`filing_id=${f.id}`, `${f.filing_type}`, `FY${f.fiscal_year}`];
                if (f.period_end) parts.push(`期末: ${f.period_end}`);
                if (f.filed_at)   parts.push(`提出: ${f.filed_at}`);
                filingMeta.textContent = parts.join(" · ");
                filingMeta.hidden = false;
                if (warningBox) warningBox.hidden = f.content_available !== false;
            }

            let activeAnalysisPoll = null;
            let filingSelectionToken = 0;
            let activeAnalysisRequestToken = 0;
            let detectInProgress = async () => {};
            let resetAnalysisUiForSelectionChange = () => {};

            function isCurrentFilingSelection(filingId, selectionToken) {
                return selectionToken === filingSelectionToken
                    && (!filingSelect || String(filingSelect.value) === String(filingId));
            }

            function cancelActivePoll() {
                if (!activeAnalysisPoll) return;
                window.clearInterval(activeAnalysisPoll.interval);
                const resolve = activeAnalysisPoll.resolve;
                activeAnalysisPoll = null;
                resolve();
            }

            function advanceFilingSelection() {
                filingSelectionToken += 1;
                activeAnalysisRequestToken += 1;
                cancelActivePoll();
                resetAnalysisUiForSelectionChange();
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
                        loadAnalyses(filingSelect.value)
                            .finally(() => detectInProgress(filingSelect.value));
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
                    advanceFilingSelection();
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
                    const filingId = filingSelect ? filingSelect.value : "";
                    if (filingId) askPayload.filing_id = Number(filingId);
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

            const analyzeButton = panel.querySelector("[data-rag-analyze]");
            const progressBox = panel.querySelector("[data-rag-analyze-progress]");
            if (analyzeButton && progressBox) {
                const progressBar = progressBox.querySelector("[data-progress-bar]");
                const progressLabel = progressBox.querySelector("[data-progress-label]");
                const progressCount = progressBox.querySelector("[data-progress-count]");
                const progressError = progressBox.querySelector("[data-progress-error]");

                function resetProgress() {
                    progressBox.classList.remove("progress--error", "progress--indeterminate");
                    progressBar.style.width = "0%";
                    progressLabel.textContent = "準備中…";
                    progressCount.textContent = "";
                    progressError.hidden = true;
                    progressError.textContent = "";
                }

                function showIndeterminate(label) {
                    progressBox.classList.add("progress--indeterminate");
                    progressLabel.textContent = label;
                    progressCount.textContent = "";
                }

                function setDeterminate() {
                    progressBox.classList.remove("progress--indeterminate");
                }

                function terminalCompleteEvent(job) {
                    return {
                        event: "complete",
                        status: job.status,
                        progress_current: job.progress_current,
                        progress_total: job.progress_total,
                    };
                }

                function positiveProgressTotal(value) {
                    return Number.isFinite(value) && value > 0 ? value : null;
                }

                function resolveProgressTotal(value, state) {
                    return (
                        positiveProgressTotal(value)
                        ?? positiveProgressTotal(state.total)
                        ?? DEFAULT_ANALYSIS_TOTAL
                    );
                }

                function syncTerminalProgress(evt, state) {
                    let changed = false;
                    const nextTotal = Number.isFinite(evt.progress_total)
                        ? evt.progress_total
                        : positiveProgressTotal(evt.progress_total);
                    if (nextTotal !== null) {
                        state.total = nextTotal;
                        changed = true;
                    }
                    if (Number.isFinite(evt.progress_current)) {
                        state.completed = evt.progress_current;
                        changed = true;
                    }
                    if (changed) {
                        progressCount.textContent = `${state.completed} / ${state.total}`;
                    }
                }

                function terminalProgressLabel(state) {
                    if (state.errored && state.completed === 0) return "失敗";
                    if (state.errored || state.completed < state.total) return "完了 (一部失敗)";
                    return "完了";
                }

                function applyEvent(evt, state) {
                    if (evt.event === "fetching") {
                        showIndeterminate("決算本体をダウンロード中…");
                    } else if (evt.event === "extracting") {
                        showIndeterminate("章テキスト抽出中…");
                    } else if (evt.event === "indexing") {
                        // Legacy event from old in-flight progress streams.
                        showIndeterminate("インデックス構築中…");
                    } else if (evt.event === "started") {
                        setDeterminate();
                        state.total = resolveProgressTotal(evt.total, state);
                        state.completed = 0;
                        progressLabel.textContent = `分析開始 (${state.total}タイプ)`;
                        progressCount.textContent = `0 / ${state.total}`;
                    } else if (evt.event === "phase") {
                        setDeterminate();
                        state.total = resolveProgressTotal(evt.progress_total ?? evt.total, state);
                        if (Number.isFinite(evt.progress_current)) {
                            state.completed = evt.progress_current;
                        }
                        const pct = state.total
                            ? Math.round((state.completed / state.total) * 100)
                            : 0;
                        progressBar.style.width = `${pct}%`;
                        const lbl = evt.label || evt.analysis_type || "進行中";
                        progressLabel.textContent = evt.analysis_type
                            ? `${lbl} を実行中…`
                            : lbl;
                        progressCount.textContent = `${state.completed} / ${state.total}`;
                    } else if (evt.event === "done" || evt.event === "cached" || evt.event === "skipped") {
                        state.completed = (evt.index ?? state.completed) + 1;
                        const pct = state.total
                            ? Math.round((state.completed / state.total) * 100)
                            : 0;
                        progressBar.style.width = `${pct}%`;
                        progressCount.textContent = `${state.completed} / ${state.total}`;
                        if (evt.event === "cached") {
                            progressLabel.textContent = `${evt.analysis_type} (キャッシュ使用)`;
                        } else if (evt.event === "skipped") {
                            progressLabel.textContent = `${evt.analysis_type} (適用外: 該当章なし)`;
                        }
                    } else if (evt.event === "error") {
                        state.errored = true;
                        progressBox.classList.add("progress--error");
                        progressError.hidden = false;
                        const prev = progressError.textContent;
                        const msg = evt.analysis_type
                            ? `${evt.analysis_type}: ${evt.message || "失敗"}`
                            : (evt.message || "失敗");
                        progressError.textContent = prev ? `${prev}\n${msg}` : msg;
                    } else if (evt.event === "complete") {
                        state.completed_event = true;
                        setDeterminate();
                        syncTerminalProgress(evt, state);
                        progressBar.style.width = state.errored && state.completed === 0
                            ? "0%"
                            : "100%";
                        progressLabel.textContent = terminalProgressLabel(state);
                    }
                }

                const rerunBox = panel.querySelector("[data-rag-rerun]");
                const rerunBtn = panel.querySelector("[data-rag-rerun-btn]");

                resetAnalysisUiForSelectionChange = () => {
                    progressBox.hidden = true;
                    if (rerunBox) rerunBox.hidden = true;
                    resetProgress();
                    analyzeButton.disabled = false;
                };

                function jobToEvents(job, prevStatus) {
                    const events = [];
                    if (job.status === "pending") {
                        events.push({ event: "fetching", filing_id: job.filing_id });
                    } else if (job.status === "running") {
                        if (prevStatus !== "running") {
                            events.push({ event: "started", total: job.progress_total });
                        }
                        events.push({
                            event: "phase",
                            index: job.progress_current,
                            total: job.progress_total,
                            progress_current: job.progress_current,
                            progress_total: job.progress_total,
                            analysis_type: job.current_analysis_type || null,
                            label: job.current_analysis_type || "進行中",
                        });
                    } else if (job.status === "completed") {
                        events.push(terminalCompleteEvent(job));
                    } else if (job.status === "failed") {
                        const details = job.error_details || {};
                        let emittedFailure = false;
                        // Prefer the extractor-pipeline failure key; fall through to
                        // the legacy PageIndex key for older job records.
                        if (details.extraction_error) {
                            events.push({
                                event: "error",
                                analysis_type: null,
                                message: details.extraction_error.message || "章抽出失敗",
                            });
                            emittedFailure = true;
                        } else if (details.index_build_error) {
                            events.push({
                                event: "error",
                                analysis_type: null,
                                message: details.index_build_error.message || "インデックス構築失敗",
                            });
                            emittedFailure = true;
                        } else {
                            const failed = details.failed_types || [];
                            if (failed.length === 0 && details.reason) {
                                events.push({ event: "error", message: details.reason });
                                emittedFailure = true;
                            }
                            for (const f of failed) {
                                events.push({
                                    event: "error",
                                    analysis_type: f.type,
                                    message: f.message,
                                });
                                emittedFailure = true;
                            }
                        }
                        if (!emittedFailure) {
                            events.push({ event: "error", message: "分析に失敗しました" });
                        }
                        events.push(terminalCompleteEvent(job));
                    } else if (job.status === "cancelled") {
                        events.push({ event: "error", message: "分析がキャンセルされました" });
                        events.push(terminalCompleteEvent(job));
                    }
                    return events;
                }

                async function pollJob(jobId, filingIdForReload, selectionToken = filingSelectionToken) {
                    if (!isCurrentFilingSelection(filingIdForReload, selectionToken)) return;
                    cancelActivePoll();
                    let prevStatus = null;
                    let requestInFlight = false;
                    let resolved = false;
                    const token = {};
                    const state = { total: 0, completed: 0, errored: false, completed_event: false };
                    return new Promise((resolve) => {
                        const finish = () => {
                            if (resolved) return;
                            resolved = true;
                            if (activeAnalysisPoll && activeAnalysisPoll.token === token) {
                                window.clearInterval(activeAnalysisPoll.interval);
                                activeAnalysisPoll = null;
                            }
                            resolve();
                        };
                        const interval = setInterval(async () => {
                            if (!activeAnalysisPoll || activeAnalysisPoll.token !== token
                                || !isCurrentFilingSelection(filingIdForReload, selectionToken)) {
                                finish();
                                return;
                            }
                            if (requestInFlight) return;
                            requestInFlight = true;
                            try {
                                const resp = await fetch(`/api/analysis-jobs/${jobId}`);
                                if (!resp.ok) {
                                    finish();
                                    return;
                                }
                                const job = await resp.json();
                                if (!activeAnalysisPoll || activeAnalysisPoll.token !== token
                                    || !isCurrentFilingSelection(filingIdForReload, selectionToken)) {
                                    finish();
                                    return;
                                }
                                const events = jobToEvents(job, prevStatus);
                                for (const ev of events) applyEvent(ev, state);
                                prevStatus = job.status;
                                if (["completed", "failed", "cancelled"].includes(job.status)) {
                                    if (job.status === "completed") {
                                        await loadAnalyses(filingIdForReload);
                                    }
                                    if (job.status === "failed" || job.status === "cancelled") {
                                        if (rerunBox) rerunBox.hidden = false;
                                    }
                                    dispatchAnalysisJobsChanged();
                                    finish();
                                }
                            } catch (e) {
                                // ignore transient
                            } finally {
                                requestInFlight = false;
                            }
                        }, 5000);
                        activeAnalysisPoll = { token, interval, resolve: finish };
                    });
                }

                async function startAnalysis(filingId) {
                    if (!filingId) return;
                    if (analyzeButton.disabled) return;
                    const selectionToken = filingSelectionToken;
                    const requestToken = ++activeAnalysisRequestToken;
                    if (!isCurrentFilingSelection(filingId, selectionToken)) return;
                    analyzeButton.disabled = true;
                    progressBox.hidden = false;
                    if (rerunBox) rerunBox.hidden = true;
                    resetProgress();
                    showIndeterminate("分析を要求中…");

                    const apiUrl = "/api/analysis-jobs";
                    try {
                        const resp = await fetch(apiUrl, {
                            method: "POST",
                            credentials: "same-origin",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                company_id: companyId,
                                filing_id: Number(filingId),
                            }),
                        });
                        if (!isCurrentFilingSelection(filingId, selectionToken)) return;
                        if (!resp.ok) {
                            let detail = `HTTP ${resp.status}`;
                            try {
                                const body = await resp.json();
                                if (body && body.detail) {
                                    detail = typeof body.detail === "string"
                                        ? body.detail
                                        : JSON.stringify(body.detail);
                                }
                            } catch (_) { /* ignore */ }
                            // 開発時の典型的な原因: サーバ再起動忘れで新ルート未登録 → 404
                            const hint = resp.status === 404
                                ? " (サーバ再起動を確認してください)"
                                : "";
                            console.error("[analysis-jobs] POST failed", {
                                url: apiUrl, status: resp.status, detail,
                            });
                            throw new Error(`HTTP ${resp.status} ${detail}${hint}`);
                        }
                        const job = await resp.json();
                        dispatchAnalysisJobsChanged();
                        if (!isCurrentFilingSelection(filingId, selectionToken)) return;
                        await pollJob(job.job_id, filingId, selectionToken);
                    } catch (error) {
                        if (!isCurrentFilingSelection(filingId, selectionToken)) return;
                        progressBox.classList.add("progress--error");
                        progressError.hidden = false;
                        progressError.textContent = `失敗: ${error.message}`;
                        progressLabel.textContent = "中断しました";
                        if (rerunBox) rerunBox.hidden = false;
                    } finally {
                        if (requestToken === activeAnalysisRequestToken) {
                            analyzeButton.disabled = false;
                        }
                    }
                }

                analyzeButton.addEventListener("click", () => {
                    const filingId = filingSelect ? filingSelect.value : "";
                    startAnalysis(filingId);
                });

                if (rerunBtn) {
                    rerunBtn.addEventListener("click", () => {
                        const filingId = filingSelect ? filingSelect.value : "";
                        startAnalysis(filingId);
                    });
                }

                detectInProgress = async function (filingId) {
                    if (!filingId) return;
                    const selectionToken = filingSelectionToken;
                    if (!isCurrentFilingSelection(filingId, selectionToken)) return;
                    try {
                        const resp = await fetch(
                            `/api/analysis-jobs?company_id=${encodeURIComponent(companyId)}`
                            + `&filing_id=${encodeURIComponent(filingId)}`
                            + `&status=pending,running&limit=1`,
                        );
                        if (!resp.ok || !isCurrentFilingSelection(filingId, selectionToken)) return;
                        const jobs = await resp.json();
                        if (!isCurrentFilingSelection(filingId, selectionToken)) return;
                        if (jobs.length === 0) return;
                        const job = jobs[0];
                        progressBox.hidden = false;
                        resetProgress();
                        showIndeterminate("既存ジョブに接続中…");
                        await pollJob(job.job_id, filingId, selectionToken);
                    } catch (e) {
                        // ignore
                    }
                }

                // タブ復帰時の自動検出: filing_select が変化した時に進行中ジョブを探す
                if (filingSelect) {
                    filingSelect.addEventListener("change", () => {
                        detectInProgress(filingSelect.value);
                    });
                }
            }
        });
    }

    const TOOLTIP_MARGIN = 12;
    const TOOLTIP_VALUE_MOD = {
        up: "chart-stack__tooltip-value--up",
        down: "chart-stack__tooltip-value--down",
    };

    function attachChartHover(host, svg, opts) {
        const {
            points, viewBoxW, viewBoxH,
            padL, padR, padT, padB,
            theme, formatTooltip, makeMarkers, updateMarkers,
        } = opts;
        const innerW = viewBoxW - padL - padR;
        const innerH = viewBoxH - padT - padB;

        const guide = svgEl(svg, "line", {
            y1: padT, y2: padT + innerH,
            stroke: theme.mute, "stroke-width": 1,
            "stroke-dasharray": "2 3", opacity: "0.7",
        });
        guide.style.display = "none";
        guide.style.pointerEvents = "none";

        const markers = makeMarkers ? makeMarkers() : [];
        markers.forEach((m) => {
            m.style.display = "none";
            m.style.pointerEvents = "none";
            svg.appendChild(m);
        });

        const tipEl = el("div", "chart-stack__tooltip");
        tipEl.style.display = "none";
        host.appendChild(tipEl);

        const overlay = svgEl(svg, "rect", {
            x: padL, y: padT, width: innerW, height: innerH,
            fill: "transparent", "pointer-events": "all",
        });
        overlay.style.cursor = "crosshair";

        function findIndex(viewBoxX) {
            if (!points.length) return -1;
            let lo = 0, hi = points.length - 1;
            if (viewBoxX <= points[lo].x) return lo;
            if (viewBoxX >= points[hi].x) return hi;
            while (hi - lo > 1) {
                const mid = (lo + hi) >> 1;
                if (points[mid].x <= viewBoxX) lo = mid; else hi = mid;
            }
            return (viewBoxX - points[lo].x) <= (points[hi].x - viewBoxX) ? lo : hi;
        }

        let lastIdx = -1;
        function show(idx) {
            if (idx === lastIdx) return;
            const p = points[idx];
            if (!p) return;
            lastIdx = idx;

            guide.setAttribute("x1", p.x);
            guide.setAttribute("x2", p.x);
            guide.style.display = "";

            const visibility = updateMarkers ? updateMarkers(markers, p) : [];
            markers.forEach((m, i) => {
                m.style.display = visibility[i] === false ? "none" : "";
            });

            tipEl.replaceChildren(...formatTooltip(p));
            tipEl.style.display = "";
            const rect = svg.getBoundingClientRect();
            const hostRect = host.getBoundingClientRect();
            const screenX = rect.left + p.x * (rect.width / viewBoxW) - hostRect.left;
            const tipW = tipEl.offsetWidth;
            let left = screenX + TOOLTIP_MARGIN;
            if (left + tipW > hostRect.width - TOOLTIP_MARGIN) {
                left = screenX - tipW - TOOLTIP_MARGIN;
            }
            tipEl.style.left = `${Math.max(TOOLTIP_MARGIN, left)}px`;
            tipEl.style.top = `${TOOLTIP_MARGIN}px`;
        }

        function hide() {
            if (lastIdx === -1) return;
            lastIdx = -1;
            guide.style.display = "none";
            markers.forEach((m) => { m.style.display = "none"; });
            tipEl.style.display = "none";
        }

        overlay.addEventListener("pointermove", (e) => {
            const rect = svg.getBoundingClientRect();
            if (rect.width === 0) return;
            const viewBoxX = (e.clientX - rect.left) * (viewBoxW / rect.width);
            const idx = findIndex(viewBoxX);
            if (idx >= 0) show(idx);
        });
        overlay.addEventListener("pointerleave", hide);
    }

    function tooltipRowNode(label, value, valueClass) {
        const row = el("div", "chart-stack__tooltip-row");
        row.append(
            el("span", "chart-stack__tooltip-label", label),
            el("span",
                `chart-stack__tooltip-value${TOOLTIP_VALUE_MOD[valueClass] ? " " + TOOLTIP_VALUE_MOD[valueClass] : ""}`,
                value),
        );
        return row;
    }

    function renderFieldChart(host, rows, opts) {
        host.innerHTML = "";
        const { dateKey, fieldKey, unit } = opts;
        const ordered = [...rows].reverse();
        const series = ordered.map((r, i) => {
            const raw = Number(r[fieldKey]);
            const v = Number.isFinite(raw) ? raw : null;
            const prevRaw = i > 0 ? Number(ordered[i - 1][fieldKey]) : null;
            const prev = Number.isFinite(prevRaw) ? prevRaw : null;
            const yoy = (v != null && prev != null && prev !== 0)
                ? (v - prev) / Math.abs(prev) : null;
            return { fy: toYearMonth(r[dateKey]), value: v, yoy };
        });
        const usable = series.filter((s) => s.value != null);
        if (usable.length === 0) {
            const empty = document.createElement("p");
            empty.className = "chart-stack__empty";
            empty.textContent = "データがありません。";
            host.appendChild(empty);
            return;
        }

        const w = 600, h = 220, padL = 60, padR = 60, padT = 16, padB = 32;
        const innerW = w - padL - padR;
        const innerH = h - padT - padB;
        const theme = chartTheme();

        let maxV = 0, minV = 0;
        for (const v of usable.map((s) => s.value)) {
            if (v > maxV) maxV = v;
            if (v < minV) minV = v;
        }
        const valSpan = Math.max(Math.abs(maxV - minV), Math.abs(maxV) || 1);
        let yoyRange = 0.05;
        for (const s of series) {
            if (s.yoy == null) continue;
            const a = Math.abs(s.yoy);
            if (a > yoyRange) yoyRange = a;
        }
        const yoyMax = yoyRange * 1.2;
        const yoyMin = -yoyMax;

        const n = ordered.length;
        const slot = innerW / Math.max(n, 1);
        const barW = Math.min(slot * 0.6, 48);
        const barX = (i) => padL + slot * i + slot / 2 - barW / 2;
        const barY = (v) => padT + (1 - (v - minV) / valSpan) * innerH;
        const baselineY = barY(0);
        const pointX = (i) => padL + slot * i + slot / 2;
        const pointY = (v) => padT + (1 - (v - yoyMin) / (yoyMax - yoyMin)) * innerH;

        const leftTicks = Array.from({ length: 5 }, (_, i) => minV + ((4 - i) / 4) * valSpan);
        const rightTicks = Array.from({ length: 5 }, (_, i) => yoyMax - (i / 4) * (yoyMax - yoyMin));
        const labelEvery = Math.max(1, Math.ceil(n / 12));

        const svg = document.createElementNS(SVG_NS, "svg");
        svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
        svg.setAttribute("width", "100%");
        svg.setAttribute("height", h);
        svg.setAttribute("preserveAspectRatio", "none");
        svg.classList.add("chart-stack__svg-el");
        svg.style.display = "block";

        const el = (tag, attrs, text) => svgEl(svg, tag, attrs, text);

        leftTicks.forEach((v, i) => {
            const yPos = padT + (i / 4) * innerH;
            el("line", { x1: padL, y1: yPos, x2: w - padR, y2: yPos, stroke: theme.grid, "stroke-width": 1 });
            el("text", {
                x: padL - 8, y: yPos + 3, "text-anchor": "end", fill: theme.axis,
                "font-family": "JetBrains Mono", "font-size": 10,
                style: "font-variant-numeric: tabular-nums",
            }, formatYTick(unit, v));
            el("text", {
                x: w - padR + 8, y: yPos + 3, "text-anchor": "start", fill: theme.axis,
                "font-family": "JetBrains Mono", "font-size": 10,
                style: "font-variant-numeric: tabular-nums",
            }, (rightTicks[i] * 100).toFixed(0) + "%");
        });
        el("line", { x1: padL, y1: padT, x2: padL, y2: padT + innerH, stroke: theme.edge, "stroke-width": 1 });
        el("line", { x1: w - padR, y1: padT, x2: w - padR, y2: padT + innerH, stroke: theme.edge, "stroke-width": 1 });
        el("line", { x1: padL, y1: padT + innerH, x2: w - padR, y2: padT + innerH, stroke: theme.edge, "stroke-width": 1 });
        if (minV < 0 && maxV > 0) {
            el("line", { x1: padL, y1: baselineY, x2: w - padR, y2: baselineY,
                stroke: theme.axis, "stroke-width": 1, "stroke-dasharray": "3 3" });
        }

        series.forEach((s, i) => {
            if (s.value == null) return;
            const y = s.value >= 0 ? barY(s.value) : baselineY;
            const h2 = Math.abs(barY(s.value) - baselineY);
            el("rect", {
                x: barX(i), y, width: barW, height: h2,
                fill: theme.bar, opacity: 0.55, rx: 2,
            });
        });

        const linePts = series
            .map((s, i) => s.yoy == null ? null : `${pointX(i)},${pointY(s.yoy)}`)
            .filter(Boolean);
        if (linePts.length >= 2) {
            el("path", {
                d: "M" + linePts.join(" L"),
                stroke: theme.line, "stroke-width": 1.6, fill: "none",
                "stroke-linejoin": "round", "stroke-linecap": "round",
            });
        }
        series.forEach((s, i) => {
            if (s.yoy == null) return;
            el("circle", {
                cx: pointX(i), cy: pointY(s.yoy), r: 3, fill: theme.bg,
                stroke: theme.line, "stroke-width": 1.4,
            });
        });

        series.forEach((s, i) => {
            if (i % labelEvery !== 0 && i !== n - 1) return;
            el("text", {
                x: pointX(i), y: padT + innerH + 16, fill: theme.mute,
                "font-family": "JetBrains Mono", "font-size": 10, "text-anchor": "middle",
                style: "font-variant-numeric: tabular-nums",
            }, s.fy);
        });

        host.appendChild(svg);

        const hoverPoints = series.map((s, i) => ({
            x: pointX(i),
            value: s.value,
            yoy: s.yoy,
            barX: barX(i),
            barW,
            baselineY,
            barTopY: s.value != null ? barY(s.value) : null,
            yoyY: s.yoy != null ? pointY(s.yoy) : null,
            date: String(ordered[i][dateKey] || ""),
            fy: s.fy,
        }));
        attachChartHover(host, svg, {
            points: hoverPoints,
            viewBoxW: w, viewBoxH: h,
            padL, padR, padT, padB, theme,
            makeMarkers: () => [
                svgEl(null, "rect", {
                    fill: theme.bar, opacity: "1", rx: "2",
                }),
                svgEl(null, "circle", {
                    r: "4.5", fill: theme.line,
                    stroke: theme.bg, "stroke-width": "1.4",
                }),
            ],
            updateMarkers: ([barHi, yoyHi], p) => {
                const barVisible = p.value != null && p.barTopY != null;
                if (barVisible) {
                    const top = Math.min(p.barTopY, p.baselineY);
                    const height = Math.abs(p.barTopY - p.baselineY);
                    barHi.setAttribute("x", p.barX);
                    barHi.setAttribute("y", top);
                    barHi.setAttribute("width", p.barW);
                    barHi.setAttribute("height", height);
                }
                const yoyVisible = p.yoy != null && p.yoyY != null;
                if (yoyVisible) {
                    yoyHi.setAttribute("cx", p.x);
                    yoyHi.setAttribute("cy", p.yoyY);
                }
                return [barVisible, yoyVisible];
            },
            formatTooltip: (p) => {
                const dateText = p.date || p.fy || "";
                const valueText = p.value != null ? formatYTick(unit, p.value) : "—";
                let yoyText = "—";
                let yoyClass = "";
                if (p.yoy != null) {
                    yoyText = (p.yoy >= 0 ? "+" : "") + (p.yoy * 100).toFixed(1) + "%";
                    yoyClass = p.yoy >= 0 ? "up" : "down";
                }
                return [
                    el("div", "chart-stack__tooltip-date", dateText),
                    tooltipRowNode(opts.label || "値", valueText),
                    tooltipRowNode("YoY", yoyText, yoyClass),
                ];
            },
        });
    }

    function renderTimeSeriesChart(host, rows, opts) {
        host.innerHTML = "";
        const { dateKey, fieldKey, unit } = opts;
        const points = [];
        for (let i = rows.length - 1; i >= 0; i--) {
            const row = rows[i];
            const v = Number(row[fieldKey]);
            if (!Number.isFinite(v)) continue;
            points.push({ date: String(row[dateKey] || ""), v });
        }
        if (points.length === 0) {
            const empty = document.createElement("p");
            empty.className = "chart-stack__empty";
            empty.textContent = "データがありません。";
            host.appendChild(empty);
            return;
        }

        const w = 600, h = 220, padL = 60, padR = 16, padT = 16, padB = 32;
        const innerW = w - padL - padR;
        const innerH = h - padT - padB;
        const theme = chartTheme();

        let minV = points[0].v, maxV = points[0].v;
        for (const p of points) {
            if (p.v < minV) minV = p.v;
            if (p.v > maxV) maxV = p.v;
        }
        const span = Math.max(maxV - minV, Math.abs(maxV) * 0.01 || 1);
        const padTop = span * 0.05;
        const padBottom = span * 0.05;
        const yMin = minV - padBottom;
        const yMax = maxV + padTop;
        const yRange = yMax - yMin;

        const sorted = [...points.map((p) => p.v)].sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);
        const median = sorted.length % 2
            ? sorted[mid]
            : (sorted[mid - 1] + sorted[mid]) / 2;

        const n = points.length;
        const x = (i) => padL + (i / Math.max(n - 1, 1)) * innerW;
        const y = (v) => padT + (1 - (v - yMin) / yRange) * innerH;
        const yTicks = Array.from({ length: 5 }, (_, i) => yMin + ((4 - i) / 4) * yRange);
        const labelEvery = Math.max(1, Math.ceil(n / 8));

        const svg = document.createElementNS(SVG_NS, "svg");
        svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
        svg.setAttribute("width", "100%");
        svg.setAttribute("height", h);
        svg.setAttribute("preserveAspectRatio", "none");
        svg.classList.add("chart-stack__svg-el");
        svg.style.display = "block";

        const el = (tag, attrs, text) => svgEl(svg, tag, attrs, text);

        yTicks.forEach((v, i) => {
            const yPos = padT + (i / 4) * innerH;
            el("line", { x1: padL, y1: yPos, x2: w - padR, y2: yPos, stroke: theme.grid, "stroke-width": 1 });
            el("text", {
                x: padL - 8, y: yPos + 3, "text-anchor": "end", fill: theme.axis,
                "font-family": "JetBrains Mono", "font-size": 10,
                style: "font-variant-numeric: tabular-nums",
            }, formatYTick(unit, v));
        });
        el("line", { x1: padL, y1: padT, x2: padL, y2: padT + innerH, stroke: theme.edge, "stroke-width": 1 });
        el("line", { x1: padL, y1: padT + innerH, x2: w - padR, y2: padT + innerH, stroke: theme.edge, "stroke-width": 1 });

        const path = points
            .map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(2)},${y(p.v).toFixed(2)}`)
            .join(" ");
        el("path", {
            d: path, stroke: theme.bar, "stroke-width": 1.6, fill: "none",
            "stroke-linejoin": "round", "stroke-linecap": "round",
        });

        if (yMin <= median && median <= yMax) {
            el("line", {
                x1: padL, y1: y(median), x2: w - padR, y2: y(median),
                stroke: theme.axis, "stroke-width": 1, "stroke-dasharray": "3 3",
            });
            el("text", {
                x: w - padR - 4, y: y(median) - 4, "text-anchor": "end", fill: theme.mute,
                "font-family": "JetBrains Mono", "font-size": 10,
            }, `中央値 ${formatYTick(unit, median)}`);
        }

        const last = points[n - 1];
        el("circle", { cx: x(n - 1), cy: y(last.v), r: 3, fill: theme.bar });

        points.forEach((p, i) => {
            if (i % labelEvery !== 0 && i !== n - 1) return;
            el("text", {
                x: x(i), y: padT + innerH + 16, fill: theme.mute,
                "font-family": "JetBrains Mono", "font-size": 10, "text-anchor": "middle",
                style: "font-variant-numeric: tabular-nums",
            }, toYearMonth(p.date));
        });

        host.appendChild(svg);

        const hoverPoints = points.map((p, i) => ({
            x: x(i),
            y: y(p.v),
            v: p.v,
            date: p.date,
        }));
        attachChartHover(host, svg, {
            points: hoverPoints,
            viewBoxW: w, viewBoxH: h,
            padL, padR, padT, padB, theme,
            makeMarkers: () => [
                svgEl(null, "circle", {
                    r: "5", fill: theme.bg,
                    stroke: theme.bar, "stroke-width": "2",
                }),
            ],
            updateMarkers: ([dot], p) => {
                dot.setAttribute("cx", p.x);
                dot.setAttribute("cy", p.y);
                return [true];
            },
            formatTooltip: (p) => [
                el("div", "chart-stack__tooltip-date", p.date),
                tooltipRowNode(opts.label || "値", formatYTick(unit, p.v)),
            ],
        });
    }

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

    // ── LLM分析キューパネル (ダッシュボード) ─────────────────────────
    async function fetchAnalysisJobs(statuses, limit = 20) {
        const params = new URLSearchParams({
            status: statuses.join(","),
            include_dismissed: "false",
            limit: String(limit),
        });
        const resp = await fetch(`/api/analysis-jobs?${params.toString()}`);
        if (!resp.ok) return null;
        return resp.json();
    }

    let _queuePanelModule = null;
    async function loadQueuePanelModule() {
        if (_queuePanelModule) return _queuePanelModule;
        // 既存 analysis_status.js loader と同じく ASSET_VERSION を encodeURIComponent
        const version = encodeURIComponent(ASSET_VERSION || "1");
        _queuePanelModule = await import(`/static/queue_panel.js?v=${version}`);
        return _queuePanelModule;
    }

    async function fetchQueue() {
        try {
            const jobs = await fetchAnalysisJobs(["pending", "running", "failed"]);
            if (!jobs) return;
            const listEl = document.getElementById("llm-queue-list");
            const emptyEl = document.getElementById("llm-queue-empty");
            const countEl = document.getElementById("llm-queue-count");
            if (!listEl) return;

            // 先頭で必ず clear。module import 失敗 / 後続の例外があっても
            // 古い queue 行が UI に残らないようにする。
            listEl.replaceChildren();

            if (jobs.length === 0) {
                if (emptyEl) emptyEl.style.display = "";
                if (countEl) countEl.textContent = "";
                return;
            }

            // sink を replaceQueueRows 1 箇所に集約して HTML 文字列流し込み経路を残さない。
            const queueMod = await loadQueuePanelModule();
            queueMod.replaceQueueRows(listEl, jobs);
            if (emptyEl) emptyEl.style.display = "none";
            if (countEl) countEl.textContent = `${jobs.length} 件`;
        } catch (e) {
            // ignore transient errors
        }
    }

    function initQueuePanel() {
        const root = document.getElementById("llm-queue-panel");
        if (!root) return;
        root.addEventListener("click", async (e) => {
            const btn = e.target.closest("button[data-action]");
            if (!btn) return;
            const jobId = btn.dataset.jobId;
            const action = btn.dataset.action;
            try {
                if (action === "cancel") {
                    await fetch(`/api/analysis-jobs/${jobId}`, { method: "DELETE" });
                } else if (action === "dismiss") {
                    await fetch(
                        `/api/analysis-jobs/${jobId}/dismiss`,
                        { method: "POST" },
                    );
                }
            } catch (err) {
                // ignore - next poll will reconcile
            }
            dispatchAnalysisJobsChanged();
            await fetchQueue();
        });
        fetchQueue();
        setInterval(fetchQueue, 5000);
    }

    async function initAnalysisStatusBadge() {
        const badge = document.getElementById("analysis-status-badge");
        if (!badge) return;
        const textEl = badge.querySelector(".topbar__badge-text");
        if (!textEl) return;

        let mod;
        try {
            const version = encodeURIComponent(ASSET_VERSION || "1");
            mod = await import(`/static/analysis_status.js?v=${version}`);
        } catch (_) {
            return;
        }

        const baseTitle = document.title;
        let prevActiveIds = new Set();
        const notifiedKey = "analysis_notified_job_ids";

        function applyBadgeViewModel(viewModel) {
            badge.hidden = viewModel.hidden;
            if (viewModel.state) {
                badge.dataset.state = viewModel.state;
            } else {
                delete badge.dataset.state;
            }
            textEl.textContent = viewModel.text;
            badge.setAttribute("aria-label", viewModel.ariaLabel);
        }

        function readNotifiedIds() {
            try {
                const value = JSON.parse(safeSessionGet(notifiedKey) || "[]");
                return Array.isArray(value) ? value : [];
            } catch (_) {
                return [];
            }
        }

        function alreadyNotified(jobId) {
            return readNotifiedIds().includes(jobId);
        }

        function markNotified(jobId) {
            const ids = readNotifiedIds();
            if (!ids.includes(jobId)) {
                ids.push(jobId);
            }
            safeSessionSet(notifiedKey, JSON.stringify(ids));
        }

        function fireNotification(job) {
            if (typeof Notification === "undefined") return;
            if (Notification.permission !== "granted") return;
            if (alreadyNotified(job.job_id)) return;

            markNotified(job.job_id);
            const notification = new Notification(mod.buildNotificationTitle(job));
            notification.onclick = () => {
                window.focus();
                window.location.href = `/stocks/${job.company_id}#tab=analysis`;
            };
        }

        async function poll() {
            try {
                const jobs = await fetchAnalysisJobs(
                    ["pending", "running", "completed", "failed"],
                );
                if (!jobs) return;

                const active = jobs.filter((job) => (
                    job.status === "pending" || job.status === "running"
                ));
                const nowMs = Date.now();
                const warning = mod.shouldWarnWorkerDown(jobs, nowMs);
                const content = mod.buildBadgeText(active, nowMs);
                applyBadgeViewModel(mod.buildBadgeViewModel(content, warning));
                document.title = mod.buildTitlePrefix(active) + baseTitle;

                const { completions, currentActiveIds } =
                    mod.detectCompletions(prevActiveIds, jobs);
                for (const job of completions) {
                    fireNotification(job);
                }
                prevActiveIds = currentActiveIds;
            } catch (_) {
                // ignore transient errors
            }
        }

        window.addEventListener("analysis-jobs:changed", () => {
            poll();
        });
        poll();
        setInterval(poll, 5000);
    }

    function initAnalysisNotificationPermission() {
        document.addEventListener("click", (event) => {
            const button = event.target.closest("[data-rag-analyze]");
            if (!button) return;
            if (typeof Notification === "undefined") return;
            if (safeSessionGet("notification_denied") === "true") return;
            if (Notification.permission !== "default") return;

            Notification.requestPermission().then((permission) => {
                if (permission === "denied") {
                    safeSessionSet("notification_denied", "true");
                }
            });
        }, { capture: true });
    }

    document.addEventListener("DOMContentLoaded", () => {
        initSearch();
        initTabs();
        initDetailKpis();
        initFinancialPanels();
        initMetricsPanels();
        initValuationPanels();
        initRagPanels();
        initQueuePanel();
        initAnalysisStatusBadge();
        initAnalysisNotificationPermission();
    });
})();
