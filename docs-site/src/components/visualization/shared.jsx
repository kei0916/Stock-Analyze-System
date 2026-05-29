/* =====================================================================
   Shared components — Modal primitive, TermLink/TermModal, GlobalSearch,
   Linkify, SectionHeading。各 View から使う共通部品。

   ダーク/ライト切替は持たない。Docusaurus ナビバーのトグルに任せ、
   `<html data-theme>` を両者で共有する。
   ===================================================================== */
import React, {
  useState,
  useEffect,
  useRef,
  useMemo,
  useCallback,
  createContext,
  useContext,
} from 'react';
import { TERMS, TERM_CATEGORIES } from './data/terms';
import { PROGRESS } from './data/content-progress';

/* ------------------------------------------------------------------
   Modal — scrim/panel・Escape・スクロールロックを 1 箇所に集約。
   開いている間だけマウントされる前提 (呼び出し側で条件付きレンダリング)。
   ------------------------------------------------------------------ */
export function Modal({ panelClassName, onClose, children }) {
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = '';
      window.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  return (
    <div className="term-modal__scrim" onClick={onClose} role="dialog" aria-modal="true">
      <div className={panelClassName} onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  );
}

export function ModalCloseButton({ onClose }) {
  return (
    <button className="term-modal__close" onClick={onClose} aria-label="閉じる">×</button>
  );
}

export function useScrollToTop(dep) {
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [dep]);
}

/* `"ADR-004"` → TERMS のキー `"adr004"`。ID 末尾 3 桁が adrNNN 用語に対応する。 */
export const adrTermKey = (id) => 'adr' + id.slice(-3);

/* ------------------------------------------------------------------
   Term Context — TermLink がクリックされたときに開くモーダルを管理
   ------------------------------------------------------------------ */
const TermContext = createContext({ open: () => {}, close: () => {} });

export function TermProvider({ children }) {
  const [activeKey, setActiveKey] = useState(null);
  const open = useCallback((k) => setActiveKey(k), []);
  const close = useCallback(() => setActiveKey(null), []);
  const value = useMemo(() => ({ open, close }), [open, close]);

  return (
    <TermContext.Provider value={value}>
      {children}
      <TermModal termKey={activeKey} onClose={close} />
    </TermContext.Provider>
  );
}

export function useTerm() { return useContext(TermContext); }

/* ------------------------------------------------------------------
   TermLink — 用語クリックでモーダルを開く下線リンク
   ------------------------------------------------------------------ */
export function TermLink({ k, children, plain }) {
  const { open } = useTerm();
  const term = TERMS[k];
  if (!term) return <span style={{ color: 'var(--down)' }}>{children || k}</span>;
  return (
    <button
      type="button"
      className={'term-link' + (plain ? ' term-link--plain' : '')}
      onClick={() => open(k)}
      aria-label={`${term.label} の解説を開く`}
    >
      {children || term.label}
      {!plain && <span className="term-link__indicator" aria-hidden="true">?</span>}
    </button>
  );
}

/* ------------------------------------------------------------------
   ADR モーダル — term 経由 (TermModal) と一覧経由 (ProgressView) で共用
   ------------------------------------------------------------------ */
function AdrModalBody({ adr, onClose }) {
  return (
    <>
      <header className="term-modal__head">
        <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="term-modal__cat">{adr.id}</span>
          <span className="adr-modal__status">{adr.status}</span>
          <span style={{ color: 'var(--fg-3)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
            {adr.date} · {adr.domain}
          </span>
        </div>
        <ModalCloseButton onClose={onClose} />
      </header>
      <h2 className="term-modal__title" style={{ fontSize: '22px' }}>
        <Linkify text={adr.title} />
      </h2>

      <div className="adr-modal__section">
        <h4 className="adr-modal__section-title">Situation</h4>
        <p className="adr-modal__body"><Linkify text={adr.summary} /></p>
      </div>
      <div className="adr-modal__section">
        <h4 className="adr-modal__section-title">Decision</h4>
        <p className="adr-modal__body"><Linkify text={adr.decision} /></p>
      </div>
      <div className="adr-modal__section">
        <h4 className="adr-modal__section-title">Trade-offs</h4>
        <ul className="adr-modal__tradeoffs">
          {adr.tradeoffs.map((t, i) => (
            <li key={i} className={t.startsWith('+') ? 'is-pos' : t.startsWith('−') ? 'is-neg' : 'is-mid'}>
              <Linkify text={t} />
            </li>
          ))}
        </ul>
      </div>
      {adr.amendments && (
        <div className="adr-modal__section">
          <h4 className="adr-modal__section-title">Amendments</h4>
          <ul className="adr-modal__amends">
            {adr.amendments.map((a, i) => (
              <li key={i}>
                <span className="adr-modal__amend-date">{a.date}</span>
                <span><Linkify text={a.note} /></span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {adr.relatedTerms?.length > 0 && (
        <div className="adr-modal__section">
          <h4 className="adr-modal__section-title">Related terms</h4>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
            {adr.relatedTerms.map((t) => (
              <span key={t} className="chip"><TermLink k={t} plain /></span>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

export function AdrModal({ adr, onClose }) {
  return (
    <Modal panelClassName="term-modal adr-modal" onClose={onClose}>
      <AdrModalBody adr={adr} onClose={onClose} />
    </Modal>
  );
}

/* ------------------------------------------------------------------
   TermModal — 用語の解説モーダル。adrRef 付き用語は ADR レイアウトに振る
   ------------------------------------------------------------------ */
function TermDetailModal({ term, onClose }) {
  const cat = TERM_CATEGORIES[term.category];
  return (
    <Modal panelClassName="term-modal" onClose={onClose}>
      <header className="term-modal__head">
        <div className="term-modal__cat">{cat?.label ?? term.category}</div>
        <ModalCloseButton onClose={onClose} />
      </header>
      <h2 className="term-modal__title">
        <span className="term-modal__title-en">{term.label}</span>
      </h2>
      <p className="term-modal__short"><Linkify text={term.short} /></p>
      <div className="term-modal__body">
        {term.detail.map((p, i) => <p key={i}><Linkify text={p} /></p>)}
      </div>
      {term.links && (
        <div className="term-modal__links">
          {term.links.map((l) => (
            <a key={l.href} href={l.href} target="_blank" rel="noopener noreferrer">
              {l.label} <span aria-hidden="true">↗</span>
            </a>
          ))}
        </div>
      )}
    </Modal>
  );
}

function TermModal({ termKey, onClose }) {
  const term = termKey ? TERMS[termKey] : null;
  if (!term) return null;
  const adr = term.adrRef ? PROGRESS.adrs.find((a) => a.id === term.adrRef) : null;
  if (adr) return <AdrModal adr={adr} onClose={onClose} />;
  return <TermDetailModal term={term} onClose={onClose} />;
}

/* ------------------------------------------------------------------
   GlobalSearch — 用語検索 (Cmd/Ctrl+K で開く)
   ------------------------------------------------------------------ */
export function GlobalSearch() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const inputRef = useRef(null);
  const { open: openTerm } = useTerm();

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => { if (open && inputRef.current) inputRef.current.focus(); }, [open]);

  const results = useMemo(() => {
    const qq = q.trim().toLowerCase();
    const entries = Object.entries(TERMS);
    if (!qq) return entries.slice(0, 8);
    return entries
      .filter(([k, t]) =>
        t.label.toLowerCase().includes(qq) ||
        t.short.toLowerCase().includes(qq) ||
        k.toLowerCase().includes(qq)
      )
      .slice(0, 12);
  }, [q]);

  return (
    <>
      <button className="search-trigger" onClick={() => setOpen(true)} aria-label="用語を検索">
        <span className="search-trigger__icon" aria-hidden="true">⌕</span>
        <span className="search-trigger__placeholder">用語を検索…</span>
        <kbd className="search-trigger__kbd">⌘K</kbd>
      </button>
      {open && (
        <div className="search-scrim" onClick={() => setOpen(false)}>
          <div className="search-panel" onClick={(e) => e.stopPropagation()}>
            <div className="search-input-row">
              <span className="search-input-icon">⌕</span>
              <input
                ref={inputRef}
                className="search-input"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="FastAPI, PER, Target …"
              />
              <kbd className="search-input-kbd">ESC</kbd>
            </div>
            <ul className="search-results">
              {results.length === 0 && (
                <li className="search-results__empty">該当する用語がありません</li>
              )}
              {results.map(([k, t]) => (
                <li key={k}>
                  <button
                    className="search-result"
                    onClick={() => { setOpen(false); openTerm(k); }}
                  >
                    <span className="search-result__label">{t.label}</span>
                    <span className="search-result__cat">
                      {TERM_CATEGORIES[t.category]?.label}
                    </span>
                    <span className="search-result__short">{t.short}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}

/* ------------------------------------------------------------------
   Linkify — テキスト中の既知の用語を自動で TermLink にラップする
   ------------------------------------------------------------------ */
const LINKIFY_ALIASES = {
  // term key → matching label aliases (longer first inside this list too)
  per: ['PER'],
  pbr: ['PBR'],
  evEbitda: ['EV/EBITDA', 'EV-EBITDA'],
  psr: ['PSR'],
  fcfYield: ['FCF Yield', 'FCF yield'],
  roe: ['ROE'],
  filing: ['有価証券報告書', 'Filing', 'filing'],
  cik: ['CIK'],
  fastapi: ['FastAPI'],
  uvicorn: ['uvicorn'],
  sqlalchemy: ['SQLAlchemy'],
  aiosqlite: ['aiosqlite'],
  jinja2: ['Jinja2'],
  litellm: ['litellm'],
  pageindex: ['PageIndex'],
  edgartools: ['edgartools'],
  pymupdf: ['pymupdf'],
  weasyprint: ['WeasyPrint'],
  pypdf: ['pypdf'],
  yfinance: ['yfinance'],
  httpx: ['httpx'],
  uv: [],
  infisical: ['Infisical'],
  ruff: ['Ruff'],
  pytest: ['pytest'],
  rag: ['RAG'],
  llm: ['LLM'],
  ormPattern: ['ORM'],
  repositoryPattern: ['Repository パターン'],
  ingestion: [],
  asgi: ['ASGI'],
  secEdgar: ['SEC EDGAR', 'EDGAR'],
  edinet: ['EDINET'],
  yahooFinance: ['Yahoo Finance', 'Yahoo'],
  stooq: ['stooq.com', 'Stooq', 'stooq'],
  xbrl: ['XBRL'],
  watchlist: ['Watchlist'],
  target: ['Target', '分析ターゲット'],
  screening: ['Screening', 'スクリーニング'],
  universe: ['universe', 'Universe'],
  worker: ['Worker', '分析ワーカー'],
  analysisJob: ['Analysis Job', 'AnalysisJob'],
  cli: ['CLI'],
  servicesLayer: ['services 層', 'Services 層'],
  repositoriesLayer: ['repositories 層', 'Repositories 層'],
  modelsLayer: ['models 層', 'Models 層'],
  ingestionLayer: ['ingestion 層', 'Ingestion 層'],
  webLayer: ['web 層', 'Web 層'],
  sectionExtractor: ['FilingSectionExtractor', 'SectionExtractor'],
  /* new */
  adr: ['ADR'],
  adr001: ['ADR-001'],
  adr002: ['ADR-002'],
  adr003: ['ADR-003'],
  adr004: ['ADR-004'],
  adr005: ['ADR-005'],
  livingDocs: ['Living Docs'],
  skill: ['maintaining-living-docs', 'Skill'],
  qwen: ['Qwen3.6-27B-Q4_K_M', 'Qwen3.6', 'Qwen3'],
  llamacpp: ['llama-server', 'llama.cpp'],
  regSK: ['Regulation S-K', 'Reg S-K'],
  toc: ['TOC'],
  spof: ['SPOF'],
  docusaurus: ['Docusaurus'],
  preCommitHook: ['pre-commit hook'],
  claudeMd: ['CLAUDE.md'],
  agentsMd: ['AGENTS.md'],
  ixbrl: ['iXBRL'],
  bulkUpsert: ['bulk_upsert_cache', 'bulk upsert'],
  ssr: ['SSR'],
  llmClient: ['LlmClient'],
  filingTypeEnum: ['FilingType'],
  semaphore: ['Semaphore'],
  jobStatus: ['JobStatus'],
  daily: ['jobs daily'],
  pageindexEnabled: ['pageindex.enabled'],
};

// Flat list { key, label } sorted by label length (longest first) so the
// regex prefers the most specific match.
const LINKIFY_ENTRIES = (() => {
  const out = [];
  for (const [key, aliases] of Object.entries(LINKIFY_ALIASES)) {
    const term = TERMS[key];
    if (!term) continue;
    const labels = new Set([term.label, ...aliases]);
    labels.forEach((l) => { if (l) out.push({ key, label: l }); });
  }
  out.sort((a, b) => b.label.length - a.label.length);
  return out;
})();

function escRegex(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

const LINKIFY_REGEX = new RegExp(
  '(' + LINKIFY_ENTRIES.map((e) => escRegex(e.label)).join('|') + ')',
  'g'
);

// label → term key, first (longest-sorted) entry wins. O(1) lookup per segment.
const LINKIFY_LABEL_TO_KEY = (() => {
  const m = new Map();
  for (const { key, label } of LINKIFY_ENTRIES) {
    if (!m.has(label)) m.set(label, key);
  }
  return m;
})();

// linkify input is almost entirely static module data, so memoize by string.
const LINKIFY_CACHE = new Map();

export function linkifyToReact(text) {
  if (!text) return null;
  const s = String(text);
  const cached = LINKIFY_CACHE.get(s);
  if (cached !== undefined) return cached;
  const out = s.split(LINKIFY_REGEX).map((part, i) => {
    if (!part) return null;
    const key = LINKIFY_LABEL_TO_KEY.get(part);
    if (key) return <TermLink key={i} k={key} plain>{part}</TermLink>;
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
  LINKIFY_CACHE.set(s, out);
  return out;
}

export function Linkify({ text, children, as: As = 'span' }) {
  const content = text != null ? text : children;
  if (typeof content !== 'string') return <As>{content}</As>;
  return <As>{linkifyToReact(content)}</As>;
}

export function SectionHeading({ n, title, sub, id }) {
  return (
    <header className="section-heading" id={id}>
      {n && <div className="section-heading__n">{n}</div>}
      <div>
        <h2 className="section-heading__title">{title}</h2>
        {sub && <p className="section-heading__sub">{sub}</p>}
      </div>
    </header>
  );
}
