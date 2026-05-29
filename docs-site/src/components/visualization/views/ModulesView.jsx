/* =====================================================================
   Modules View — 各 app 内モジュールの解説ページ
   左サイドナビ (7 モジュール) + 右に詳細
   ===================================================================== */
import React, { useState } from 'react';
import { MODULES } from '../data/content-modules';
import { PROGRESS } from '../data/content-progress';
import { TermLink, Linkify, Modal, ModalCloseButton, useScrollToTop, adrTermKey } from '../shared';

const MODULE_IDS = new Set(MODULES.map((m) => m.id));

export default function ModulesView() {
  const [activeId, setActiveId] = useState(MODULES[0].id);
  const [openFeature, setOpenFeature] = useState(null); // { feature, module }

  useScrollToTop(activeId);

  const activeIndex = MODULES.findIndex((m) => m.id === activeId);
  const mod = MODULES[activeIndex];

  return (
    <div className="mod-shell">
      {/* Left rail */}
      <aside className="mod-rail">
        <div className="mod-rail__label">MODULES · 7</div>
        <ul className="mod-rail__list">
          {MODULES.map((m) => (
            <li key={m.id}>
              <button
                className={'mod-rail__item' + (activeId === m.id ? ' mod-rail__item--active' : '')}
                onClick={() => setActiveId(m.id)}
              >
                <span className="mod-rail__name">{m.name}</span>
                <span className="mod-rail__path">{m.path.replace('src/stock_analyze_system/', '')}</span>
                <span className="mod-rail__count">{m.files}</span>
              </button>
            </li>
          ))}
        </ul>

        <div className="mod-rail__legend">
          <div className="mod-rail__legend-title">凡例</div>
          <div className="mod-rail__legend-item"><span className="mod-rail__legend-dot mod-rail__legend-dot--called" /> 呼ぶ側</div>
          <div className="mod-rail__legend-item"><span className="mod-rail__legend-dot mod-rail__legend-dot--calls" /> 呼ばれる側</div>
        </div>
      </aside>

      {/* Main */}
      <div className="mod-main" key={mod.id}>
        <header className="mod-hero">
          <div className="mod-hero__tag">MODULE · {activeIndex + 1} / {MODULES.length}</div>
          <h1 className="mod-hero__title">{mod.name}</h1>
          <div className="mod-hero__path">{mod.path}</div>
          <p className="mod-hero__summary"><Linkify text={mod.summary} /></p>
          <div className="mod-hero__meta">
            <span><strong>{mod.files}</strong> ファイル</span>
            {mod.adrs.length > 0 && (
              <span>関連 ADR · {mod.adrs.map((a, i) => (
                <React.Fragment key={a}>
                  {i > 0 && ', '}<TermLink k={adrTermKey(a)} plain>{a}</TermLink>
                </React.Fragment>
              ))}</span>
            )}
          </div>
        </header>

        {/* 1. 概要 */}
        <ModSection n="01" title="概要">
          <div className="mod-prose">
            {mod.description.map((p, i) => (
              <p key={i}><Linkify text={p} /></p>
            ))}
          </div>
        </ModSection>

        {/* 2. 機能詳細 */}
        <ModSection n="02" title="機能詳細" sub={`${mod.path} 配下の主要ファイル · クリックで詳細`}>
          <ul className="mod-features">
            {mod.features.map((f, i) => {
              const clickable = !!(f.functions || f.intent);
              return (
                <li key={i} className={'mod-feature' + (clickable ? ' mod-feature--clickable' : '')}>
                  {clickable ? (
                    <button
                      type="button"
                      className="mod-feature__btn"
                      onClick={() => setOpenFeature({ feature: f, module: mod })}
                      aria-label={`${f.name} の詳細を開く`}
                    >
                      <span className="mod-feature__name mod-feature__name--link">{f.name}</span>
                      <span className="mod-feature__hint" aria-hidden="true">詳細 →</span>
                    </button>
                  ) : (
                    <div className="mod-feature__name">{f.name}</div>
                  )}
                  <div className="mod-feature__role"><Linkify text={f.role} /></div>
                </li>
              );
            })}
          </ul>
        </ModSection>

        {/* 3. 他モジュールとの関係 */}
        <ModSection n="03" title="他モジュールとの関係">
          <ModuleRelations module={mod} onPick={setActiveId} />
          {mod.deps.note && (
            <p className="mod-note"><Linkify text={mod.deps.note} /></p>
          )}
        </ModSection>

        {/* 4. 関連 ADR */}
        <ModSection n="04" title="関連 ADR">
          {mod.adrs.length === 0 ? (
            <p className="mod-prose"><span className="muted">この層に固有の ADR はまだない。</span></p>
          ) : (
            <ul className="mod-adrs">
              {mod.adrs.map((id) => {
                const adr = PROGRESS.adrs.find((a) => a.id === id);
                if (!adr) return null;
                return (
                  <li key={id} className="mod-adr">
                    <TermLink k={adrTermKey(id)} plain>{adr.id}</TermLink>
                    <span className="mod-adr__title"><Linkify text={adr.title} /></span>
                    <p className="mod-adr__summary"><Linkify text={adr.summary} /></p>
                  </li>
                );
              })}
            </ul>
          )}
        </ModSection>

        {/* 関連用語 */}
        {mod.terms?.length > 0 && (
          <ModSection n="05" title="関連用語">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)' }}>
              {mod.terms.map((t) => (
                <span key={t} className="chip"><TermLink k={t} plain /></span>
              ))}
            </div>
          </ModSection>
        )}

        <footer className="footer">
          {mod.path} · kei0916 / Stock-Analyze-System
        </footer>
      </div>

      {openFeature && (
        <FeatureModal {...openFeature} onClose={() => setOpenFeature(null)} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------
   ModSection: 番号付きセクション
   ------------------------------------------------------------------ */
function ModSection({ n, title, sub, children }) {
  return (
    <section className="mod-section">
      <header className="mod-section__head">
        <div className="mod-section__n">{n}</div>
        <div>
          <h2 className="mod-section__title">{title}</h2>
          {sub && <div className="mod-section__sub">{sub}</div>}
        </div>
      </header>
      <div className="mod-section__body">{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------------
   ModuleRelations: 矢印付きで calls / calledBy を表示
   ------------------------------------------------------------------ */
function ModuleRelations({ module: mod, onPick }) {
  const renderModule = (item) => {
    if (MODULE_IDS.has(item)) {
      const target = MODULES.find((m) => m.id === item);
      return (
        <button className="mod-rel-chip mod-rel-chip--mod" onClick={() => onPick(item)}>
          {target.name}
          <span className="mod-rel-chip__arrow">→</span>
        </button>
      );
    }
    return <span className="mod-rel-chip">{item}</span>;
  };

  return (
    <div className="mod-rel">
      <div className="mod-rel__row">
        <div className="mod-rel__label">↑ 呼ばれる側 (inbound)</div>
        <div className="mod-rel__chips">
          {mod.deps.calledBy.map((c) => <React.Fragment key={c}>{renderModule(c)}</React.Fragment>)}
        </div>
      </div>
      <div className="mod-rel__center">
        <div className="mod-rel__self">{mod.name}</div>
      </div>
      <div className="mod-rel__row">
        <div className="mod-rel__label">↓ 呼ぶ側 (outbound)</div>
        <div className="mod-rel__chips">
          {mod.deps.calls.map((c) => <React.Fragment key={c}>{renderModule(c)}</React.Fragment>)}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------
   FeatureModal — ソースファイルの 具体的な機能 / 設計時の意図 を表示
   ------------------------------------------------------------------ */
function FeatureModal({ feature, module: mod, onClose }) {
  return (
    <Modal panelClassName="term-modal feat-modal" onClose={onClose}>
      <header className="term-modal__head">
        <div className="feat-modal__breadcrumb">
          <span className="feat-modal__module">{mod.name}</span>
          <span className="feat-modal__sep">›</span>
          <span className="feat-modal__path">{mod.path.replace('src/stock_analyze_system/', '')}</span>
        </div>
        <ModalCloseButton onClose={onClose} />
      </header>

      <h2 className="term-modal__title feat-modal__title">
        <span className="feat-modal__title-text">{feature.name}</span>
      </h2>

      <p className="term-modal__short"><Linkify text={feature.role} /></p>

      {feature.functions && feature.functions.length > 0 && (
        <section className="feat-modal__section">
          <h3 className="feat-modal__section-title">具体的な機能</h3>
          <ul className="feat-modal__fns">
            {feature.functions.map((fn, i) => (
              <li key={i}><Linkify text={fn} /></li>
            ))}
          </ul>
        </section>
      )}

      {feature.intent && (
        <section className="feat-modal__section">
          <h3 className="feat-modal__section-title">設計時の意図</h3>
          <p className="feat-modal__intent"><Linkify text={feature.intent} /></p>
        </section>
      )}
    </Modal>
  );
}
