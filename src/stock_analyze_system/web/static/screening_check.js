(() => {
  const root = document.getElementById("screening-check");
  if (!root) return;

  const filtersGrid = document.getElementById("screening-histogram-grid");
  const addFieldSelect = document.getElementById("screening-add-field");
  const applyButton = document.getElementById("screening-apply");
  const resetButton = document.getElementById("screening-reset");
  const includeNullInput = document.getElementById("screening-include-null");
  const limitInput = document.getElementById("screening-limit");
  const statusRegion = document.getElementById("screening-status");
  const resultsRegion = document.getElementById("screening-results");
  const resultsCount = document.getElementById("screening-results-count");
  const selectedCount = document.getElementById("screening-selected-count");
  const addTargetsButton = document.getElementById("screening-add-targets");
  const targetsStatus = document.getElementById("screening-targets-status");

  const DEFAULT_FIELDS = ["trailing_per", "pbr", "roe", "fcf_yield"];
  const fieldsMeta = new Map();
  const ranges = new Map();
  const selectedCompanyIds = new Set();

  const setStatus = (message, isError = false) => {
    statusRegion.textContent = message;
    statusRegion.className = isError ? "down small" : "muted small";
  };

  const requestJson = async (url, options = {}) => {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    const text = await response.text();
    const body = text ? JSON.parse(text) : null;
    if (!response.ok) {
      const message = body && body.detail ? body.detail : `HTTP ${response.status}`;
      throw new Error(message);
    }
    return body;
  };

  class HistogramRange {
    constructor({ container, field, label, format }) {
      this.container = container;
      this.field = field;
      this.label = label;
      this.format = format;
      this.percentScale = format === "percent";
      this.min = 0;
      this.max = 1;
      this.lo = 0;
      this.hi = 1;
      this.step = 0.01;
      this.bins = [];
      this.peak = 1;
      this.atFullExtent = true;
      this.dragging = null;
      this._abort = new AbortController();
      this._build();
    }

    destroy() {
      this._abort.abort();
    }

    _build() {
      this.container.classList.add("hr");
      this.container.dataset.histogramRange = this.field;
      this.container.innerHTML = `
        <div class="hr__head">
          <span class="hr__label">${this.label}</span>
          <button type="button" class="hr__remove btn--ghost" aria-label="削除">×</button>
        </div>
        <div class="hr__readout">
          <span class="hr__range">— – —</span>
          <span class="hr__count subtle"></span>
        </div>
        <div class="hr__hist" aria-hidden="true"></div>
        <div class="hr__track" tabindex="0">
          <div class="hr__track-base"></div>
          <div class="hr__track-fill"></div>
          <button type="button" class="hr__handle hr__handle--lo" aria-label="下限"></button>
          <button type="button" class="hr__handle hr__handle--hi" aria-label="上限"></button>
        </div>
        <div class="hr__axis">
          <span class="hr__axis-min">—</span>
          <span class="hr__axis-max">—</span>
        </div>`;
      this.refs = {
        head: this.container.querySelector(".hr__head"),
        remove: this.container.querySelector(".hr__remove"),
        range: this.container.querySelector(".hr__range"),
        count: this.container.querySelector(".hr__count"),
        hist: this.container.querySelector(".hr__hist"),
        track: this.container.querySelector(".hr__track"),
        fill: this.container.querySelector(".hr__track-fill"),
        loHandle: this.container.querySelector(".hr__handle--lo"),
        hiHandle: this.container.querySelector(".hr__handle--hi"),
        axisMin: this.container.querySelector(".hr__axis-min"),
        axisMax: this.container.querySelector(".hr__axis-max"),
      };
      this._wirePointer(this.refs.loHandle, "lo");
      this._wirePointer(this.refs.hiHandle, "hi");
      this.refs.track.addEventListener("pointerdown", (e) => this._onTrackPointer(e));
      this.refs.remove.addEventListener("click", () => this.onRemove?.());
      this.refs.track.addEventListener("keydown", (e) => this._onKey(e));
    }

    async load() {
      const url = root.dataset.distributionUrlTemplate.replace("{field}", this.field);
      const body = await requestJson(`${url}?buckets=24`);
      if (body.min == null || body.max == null) {
        this.refs.hist.innerHTML = '<span class="hr__hist-empty subtle">データなし</span>';
        this._setRange(0, 0, true);
        this.refs.axisMin.textContent = "—";
        this.refs.axisMax.textContent = "—";
        this.refs.range.textContent = "—";
        this.refs.count.textContent = `· 0社`;
        return;
      }
      const scale = this.percentScale ? 100 : 1;
      this.min = body.min * scale;
      this.max = body.max * scale;
      this.totalFinite = body.finite_count;
      this.bins = body.buckets.map((b) => ({
        lower: b.lower * scale,
        upper: b.upper * scale,
        count: b.count,
      }));
      this.peak = Math.max(1, ...this.bins.map((b) => b.count));
      this.step = this._computeStep(this.max - this.min);
      this._setRange(this.min, this.max, true);
      this._renderHistogram();
      this._renderAxis();
      this._render();
    }

    _computeStep(span) {
      if (span <= 5) return 0.1;
      if (span <= 50) return 0.5;
      if (span <= 500) return 1;
      return 10;
    }

    _setRange(lo, hi, full = false) {
      if (lo === this.lo && hi === this.hi && full === this.atFullExtent) return false;
      this.lo = lo;
      this.hi = hi;
      this.atFullExtent = full;
      return true;
    }

    _onTrackPointer(e) {
      if (e.target.classList.contains("hr__handle")) return;
      const v = this._fromClient(e.clientX);
      const changed = (Math.abs(v - this.lo) < Math.abs(v - this.hi))
        ? this._setRange(Math.min(v, this.hi - this.step), this.hi)
        : this._setRange(this.lo, Math.max(v, this.lo + this.step));
      if (changed) this._markDirty();
    }

    _wirePointer(el, which) {
      const signal = this._abort.signal;
      el.addEventListener("pointerdown", (e) => {
        e.preventDefault();
        this.dragging = which;
        el.classList.add("hr__handle--drag");
        const dragAbort = new AbortController();
        const dragSignal = dragAbort.signal;
        const onMove = (ev) => {
          const v = this._fromClient(ev.clientX);
          const changed = which === "lo"
            ? this._setRange(Math.min(v, this.hi - this.step), this.hi)
            : this._setRange(this.lo, Math.max(v, this.lo + this.step));
          if (changed) this._markDirty(false);
        };
        const onUp = () => {
          this.dragging = null;
          el.classList.remove("hr__handle--drag");
          dragAbort.abort();
          this._markDirty(true);
        };
        window.addEventListener("pointermove", onMove, { signal: dragSignal });
        window.addEventListener("pointerup", onUp, { signal: dragSignal });
        signal.addEventListener("abort", () => dragAbort.abort(), { once: true });
      }, { signal });
    }

    _onKey(e) {
      const d = e.shiftKey ? this.step * 10 : this.step;
      const span = this.max - this.min;
      if (!span) return;
      let changed;
      if (e.key === "ArrowLeft") {
        changed = this._setRange(Math.max(this.min, this.lo - d), this.hi);
      } else if (e.key === "ArrowRight") {
        changed = this._setRange(this.lo, Math.min(this.max, this.hi + d));
      } else {
        return;
      }
      e.preventDefault();
      if (changed) this._markDirty();
    }

    _fromClient(clientX) {
      const rect = this.refs.track.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      const raw = this.min + ratio * (this.max - this.min);
      return Math.round(raw / this.step) * this.step;
    }

    _markDirty(emitChange = true) {
      this.atFullExtent = this.lo <= this.min && this.hi >= this.max;
      this._render();
      if (emitChange && this.onChange) this.onChange();
    }

    _renderHistogram() {
      if (!this.bins.length) {
        this.refs.hist.innerHTML = '<span class="hr__hist-empty subtle">データなし</span>';
        return;
      }
      this.refs.hist.replaceChildren(...this.bins.map((b) => {
        const bar = document.createElement("div");
        bar.className = "hr__bar";
        bar.style.height = `${(b.count / this.peak) * 100}%`;
        bar.style.minHeight = b.count > 0 ? "2px" : "0";
        bar.title = `${this._fmt(b.lower)} – ${this._fmt(b.upper)} · ${b.count}社`;
        return bar;
      }));
    }

    _renderAxis() {
      this.refs.axisMin.textContent = this._fmt(this.min);
      this.refs.axisMax.textContent = this._fmt(this.max);
    }

    _render() {
      const span = this.max - this.min;
      const pct = (v) => span ? ((v - this.min) / span) * 100 : 0;
      const loPct = pct(this.lo);
      const hiPct = pct(this.hi);
      this.refs.fill.style.left = `${loPct}%`;
      this.refs.fill.style.width = `${Math.max(0, hiPct - loPct)}%`;
      this.refs.loHandle.style.left = `${loPct}%`;
      this.refs.hiHandle.style.left = `${hiPct}%`;
      this.refs.range.textContent = `${this._fmt(this.lo)} – ${this._fmt(this.hi)}`;
      const inRange = this.bins
        .filter((b) => b.upper > this.lo && b.lower < this.hi)
        .reduce((sum, b) => sum + b.count, 0);
      this.refs.count.textContent = `· ${inRange}社`;
      // recolor bars
      this.refs.hist.querySelectorAll(".hr__bar").forEach((bar, i) => {
        const b = this.bins[i];
        if (!b) return;
        const inSelection = b.upper > this.lo && b.lower < this.hi;
        bar.classList.toggle("hr__bar--in", inSelection);
      });
    }

    _fmt(v) {
      if (v == null || Number.isNaN(v)) return "—";
      const unit = this.percentScale ? "%" : "";
      const decimals = Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2;
      return `${v.toFixed(decimals)}${unit}`;
    }

    isDirty() {
      return !this.atFullExtent;
    }

    asFilter() {
      if (!this.isDirty()) return null;
      const lo = this.percentScale ? this.lo / 100 : this.lo;
      const hi = this.percentScale ? this.hi / 100 : this.hi;
      return { field: this.field, op: "between", value: [lo, hi] };
    }

    reset() {
      if (this._setRange(this.min, this.max, true)) {
        this._render();
      }
    }
  }

  const addRange = async (fieldKey) => {
    const meta = fieldsMeta.get(fieldKey);
    if (!meta || ranges.has(fieldKey)) return;
    const card = document.createElement("div");
    card.className = "hr-card";
    filtersGrid.appendChild(card);
    const widget = new HistogramRange({
      container: card,
      field: fieldKey,
      label: meta.label || fieldKey,
      format: meta.format,
    });
    widget.onChange = () => { /* applied on demand */ };
    widget.onRemove = () => {
      widget.destroy();
      ranges.delete(fieldKey);
      card.remove();
      _refreshAddOptions();
    };
    ranges.set(fieldKey, widget);
    try {
      await widget.load();
    } catch (error) {
      card.remove();
      ranges.delete(fieldKey);
      setStatus(`${meta.label}: ${error.message}`, true);
    }
    _refreshAddOptions();
  };

  const _refreshAddOptions = () => {
    const remaining = [];
    fieldsMeta.forEach((meta, key) => {
      if (!ranges.has(key) && meta.format !== "string") {
        remaining.push([key, meta.label || key]);
      }
    });
    addFieldSelect.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "+ フィールド追加";
    addFieldSelect.appendChild(placeholder);
    remaining.sort((a, b) => a[1].localeCompare(b[1])).forEach(([key, label]) => {
      const opt = document.createElement("option");
      opt.value = key;
      opt.textContent = label;
      addFieldSelect.appendChild(opt);
    });
    addFieldSelect.disabled = remaining.length === 0;
  };

  const renderResults = (items) => {
    selectedCompanyIds.clear();
    updateSelection();
    if (!items.length) {
      resultsRegion.innerHTML = '<p class="empty-state">該当する銘柄はありません。</p>';
      return;
    }
    const metricFields = [...new Set(items.flatMap((it) => Object.keys(it.metrics || {})))]
      .filter((f) => fieldsMeta.has(f))
      .slice(0, 6);
    const table = document.createElement("table");
    table.className = "table";
    const headHtml = `
      <thead><tr>
        <th class="w-10"></th>
        <th>Ticker</th>
        <th>会社名</th>
        <th>市場</th>
        <th>セクター</th>
        ${metricFields.map((f) => `<th class="num">${fieldsMeta.get(f).label}</th>`).join("")}
      </tr></thead><tbody></tbody>`;
    table.innerHTML = headHtml;
    const tbody = table.querySelector("tbody");
    items.forEach((it) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><input type="checkbox" class="screening-row"></td>
        <td class="mono">${escapeHtml(it.ticker || "")}</td>
        <td>${escapeHtml(it.name || "")}</td>
        <td><span class="badge badge--mono">${escapeHtml(it.market || "")}</span></td>
        <td class="muted">${escapeHtml(it.sector || "")}</td>
        ${metricFields.map((f) => `<td class="num-cell">${fmtMetric(f, it.metrics?.[f])}</td>`).join("")}`;
      tr.querySelector("input").addEventListener("change", (event) => {
        if (event.target.checked) selectedCompanyIds.add(it.company_id);
        else selectedCompanyIds.delete(it.company_id);
        updateSelection();
      });
      tbody.appendChild(tr);
    });
    resultsRegion.replaceChildren(table);
  };

  const fmtMetric = (field, v) => {
    if (v == null) return "—";
    const meta = fieldsMeta.get(field);
    if (!meta) return String(v);
    if (meta.format === "percent") return `${(v * 100).toFixed(1)}%`;
    if (meta.format === "currency") return formatLarge(v);
    if (meta.format === "count") return Math.round(v).toLocaleString("en-US");
    return Number(v).toFixed(2);
  };

  const formatLarge = (v) => {
    const abs = Math.abs(v);
    if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
    if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
    if (abs >= 1e3) return `${(v / 1e3).toFixed(2)}k`;
    return v.toFixed(2);
  };

  const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));

  const updateSelection = () => {
    selectedCount.textContent = `${selectedCompanyIds.size}件選択`;
    addTargetsButton.disabled = selectedCompanyIds.size === 0;
  };

  const apply = async () => {
    const filters = [];
    ranges.forEach((widget) => {
      const f = widget.asFilter();
      if (f) filters.push(f);
    });
    try {
      setStatus("実行中...");
      const limit = Math.max(1, Math.min(200, Number(limitInput.value) || 50));
      const body = await requestJson(root.dataset.runUrl, {
        method: "POST",
        body: JSON.stringify({
          filters, sort: null, limit, offset: 0,
          include_null: includeNullInput.checked,
        }),
      });
      const items = body.items || [];
      renderResults(items);
      resultsCount.textContent = `${items.length} / ${body.total_matched ?? items.length}`;
      setStatus(filters.length
        ? `${filters.length}件のレンジ条件を適用しました。`
        : "条件なしで全件を取得しました。");
    } catch (error) {
      setStatus(error.message, true);
      resultsRegion.innerHTML = '<p class="down">スクリーニングに失敗しました。</p>';
    }
  };

  const resetAll = () => {
    ranges.forEach((widget) => widget.reset());
  };

  const loadFields = async () => {
    const body = await requestJson(root.dataset.fieldsUrl);
    fieldsMeta.clear();
    [...body.numeric, ...body.categorical].forEach((m) => fieldsMeta.set(m.field, m));
    for (const key of DEFAULT_FIELDS) {
      if (fieldsMeta.has(key)) await addRange(key);
    }
    _refreshAddOptions();
  };

  addFieldSelect.addEventListener("change", async () => {
    const key = addFieldSelect.value;
    if (!key) return;
    addFieldSelect.value = "";
    await addRange(key);
  });

  applyButton.addEventListener("click", apply);
  resetButton.addEventListener("click", resetAll);

  addTargetsButton.addEventListener("click", async () => {
    try {
      targetsStatus.textContent = "追加中...";
      const body = await requestJson(root.dataset.targetsUrl, {
        method: "POST",
        body: JSON.stringify({ company_ids: [...selectedCompanyIds] }),
      });
      targetsStatus.className = "muted small";
      targetsStatus.textContent = `${body.added}件追加、${body.already_present}件は登録済みです。`;
    } catch (error) {
      targetsStatus.textContent = error.message;
      targetsStatus.className = "down small";
    }
  });

  loadFields()
    .then(() => { setStatus(`${fieldsMeta.size}フィールドを読み込みました。条件を調整して「適用」を押してください。`); })
    .catch((error) => setStatus(error.message, true));
})();
