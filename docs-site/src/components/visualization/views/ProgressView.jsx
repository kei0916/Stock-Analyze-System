/* =====================================================================
   Progress View — ロードマップ可視化 + Linkify で全テキストに用語モーダル
   ===================================================================== */
import React, { useState, useMemo } from 'react';
import { PROGRESS } from '../data/content-progress';
import { SectionHeading, TermLink, Linkify, AdrModal, adrTermKey } from '../shared';

export default function ProgressView() {
  const P = PROGRESS;
  const [activeAdr, setActiveAdr] = useState(null);
  const [intentN, setIntentN] = useState(P.intents[0].n);

  const planGroups = useMemo(() => {
    const g = {};
    P.plansTimeline.forEach((p) => {
      const k = p.date.slice(0, 7);
      (g[k] ||= []).push(p);
    });
    return Object.entries(g).sort((a, b) => b[0].localeCompare(a[0]));
  }, [P]);

  const intent = P.intents.find((i) => i.n === intentN);

  return (
    <div className="page page--wide progress-page">

      <Roadmap roadmap={P.roadmap} />

      <section className="progress__triple">
        <ProgressColumn tag="NOW"  title="進行中"  accent items={P.inFlight} />
        <ProgressColumn tag="NEXT" title="次に着手"      items={P.nextUp} />
        <ProgressColumn tag="DONE" title="最近マージ (7 日)"
          items={P.recentlyLanded.map((r) => ({
            title: r.title,
            bullets: [r.detail + (r.hash ? `  ·  ${r.hash}` : '')],
          }))} />
      </section>

      <section style={{ marginTop: 'var(--space-7)' }}>
        <SectionHeading n="INTENT" title="設計意図"
          sub="なぜこの設計を選んだのか。コードを読む前にここを 5 分で読むと、あとが速い。" />
        <div className="intent-shell">
          <nav className="intent-nav" aria-label="設計意図">
            {P.intents.map((i) => (
              <button
                key={i.n}
                className={'intent-nav__item' + (intentN === i.n ? ' intent-nav__item--active' : '')}
                onClick={() => setIntentN(i.n)}
              >
                <span className="intent-nav__n">{i.n}</span>
                <span className="intent-nav__title">{i.title}</span>
              </button>
            ))}
          </nav>
          <article className="intent-body" key={intentN}>
            <div className="intent-body__n">{intent.n}</div>
            <h3 className="intent-body__title"><Linkify text={intent.title} /></h3>
            <div className="intent-body__copy">
              {intent.body.map((p, i) => <p key={i}><Linkify text={p} /></p>)}
            </div>
            {intent.terms?.length > 0 && (
              <div className="intent-body__terms">
                {intent.terms.map((t) => (
                  <span key={t} className="chip"><TermLink k={t} plain /></span>
                ))}
              </div>
            )}
          </article>
        </div>
      </section>

      <section style={{ marginTop: 'var(--space-7)' }}>
        <SectionHeading n="ADR" title="Architecture Decision Records"
          sub="決定 (Decision) と、それを採った理由・代案・トレードオフが書かれている短文。" />
        <ul className="adr-list">
          {P.adrs.map((adr) => (
            <li key={adr.id}>
              <button className="adr-row" onClick={() => setActiveAdr(adr)}>
                <span className="adr-row__id">{adr.id}</span>
                <span className="adr-row__title">{adr.title}</span>
                <span className="adr-row__meta">
                  <span className="adr-row__domain">{adr.domain}</span>
                  <span className="adr-row__status">{adr.status}</span>
                  <span className="adr-row__date">{adr.date}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section style={{ marginTop: 'var(--space-7)' }}>
        <SectionHeading n="DOCS" title="3 層 Living Docs (ADR-005)"
          sub="このサイト自身もこの考え方の延長線にあります。" />
        <div className="ldocs">
          {P.livingDocs.map((l) => (
            <div key={l.layer} className="ldocs__row">
              <div className="ldocs__layer">
                <div className="ldocs__layer-tag">{l.layer}</div>
                <div className="ldocs__layer-name">{l.name}</div>
              </div>
              <div className="ldocs__body">
                <div className="ldocs__path">{l.path}</div>
                <div className="ldocs__what"><Linkify text={l.what} /></div>
                <div className="ldocs__freshness">
                  <span className="ldocs__freshness-tag">鮮度保証</span>
                  <Linkify text={l.freshness} />
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section style={{ marginTop: 'var(--space-7)' }}>
        <SectionHeading n="TIMELINE" title="Plans タイムライン"
          sub={`docs/superpowers/plans/ 配下の plan を月別に集計 (${P.plansTimeline.length} 件)。`} />
        <div className="timeline">
          {planGroups.map(([month, items]) => (
            <div key={month} className="timeline__group">
              <div className="timeline__month">{month}</div>
              <ul className="timeline__items">
                {items.map((p, idx) => (
                  <li key={idx} className={'timeline__item timeline__item--' + p.kind}>
                    <span className="timeline__day">{p.date.slice(-2)}</span>
                    <span className="timeline__kind">{p.kind}</span>
                    <span className="timeline__title"><Linkify text={p.title} /></span>
                    {p.adr && (
                      <span className="timeline__adr">
                        → <TermLink k={adrTermKey(p.adr)}>{p.adr}</TermLink>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <footer className="footer">
        kei0916 / Stock-Analyze-System · 進捗データソース: docs/current-work.md, docs/adr/*, docs/superpowers/plans/*
      </footer>

      {activeAdr && <AdrModal adr={activeAdr} onClose={() => setActiveAdr(null)} />}
    </div>
  );
}

/* ------------------------------------------------------------------
   Roadmap — 大きく目立つ 4 フェーズ stepper
   ------------------------------------------------------------------ */
function Roadmap({ roadmap }) {
  const { phases, currentIndex } = roadmap;
  const overallPct = ((currentIndex + 0.5) / phases.length) * 100;
  return (
    <section className="rm">
      <header className="rm__head">
        <div>
          <div className="rm__tag">ROADMAP · 現在地</div>
          <h1 className="rm__title">{roadmap.title}</h1>
          <p className="rm__sub"><Linkify text={roadmap.sub} /></p>
        </div>
        <div className="rm__pct">
          <div className="rm__pct-bar">
            <div className="rm__pct-fill" style={{ width: overallPct + '%' }} />
          </div>
          <div className="rm__pct-num">
            <span className="rm__pct-now">{phases[currentIndex].id}</span>
            <span className="rm__pct-of">/ {phases[phases.length - 1].id}</span>
          </div>
        </div>
      </header>

      <div className="rm__track">
        <div className="rm__line">
          <div className="rm__line-done" style={{ width: (currentIndex / (phases.length - 1)) * 100 + '%' }} />
        </div>
        <ol className="rm__stops">
          {phases.map((ph, i) => (
            <li key={ph.id} className={'rm__stop rm__stop--' + ph.status}>
              <div className="rm__stop-dot">
                {ph.status === 'done' && <span>✓</span>}
                {ph.status === 'active' && <span className="rm__stop-pulse" />}
                {ph.status !== 'done' && ph.status !== 'active' && <span>{i + 1}</span>}
              </div>
              <div className="rm__stop-id">{ph.id}</div>
              <div className="rm__stop-title"><Linkify text={ph.title} /></div>
              <div className="rm__stop-sub"><Linkify text={ph.sub} /></div>
              <div className="rm__stop-date">{ph.date}</div>
            </li>
          ))}
        </ol>
      </div>

      <div className="rm__now">
        <div className="rm__now-head">
          <span className="rm__now-label">NOW</span>
          <span className="rm__now-phase">{phases[currentIndex].id} · {phases[currentIndex].title}</span>
          <span className="rm__now-date">{phases[currentIndex].date}</span>
        </div>
        <ul className="rm__now-bullets">
          {phases[currentIndex].bullets.map((b, i) => (
            <li key={i}><Linkify text={b} /></li>
          ))}
        </ul>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------
   ProgressColumn — NOW / NEXT / DONE の 3 列
   ------------------------------------------------------------------ */
function ProgressColumn({ tag, title, items, accent }) {
  return (
    <article className={'pcol' + (accent ? ' pcol--accent' : '')}>
      <header className="pcol__head">
        <span className="pcol__tag">{tag}</span>
        <h3 className="pcol__title">{title}</h3>
      </header>
      <ul className="pcol__list">
        {items.map((it, i) => (
          <li key={i} className="pcol__item">
            <div className="pcol__item-title"><Linkify text={it.title} /></div>
            <ul className="pcol__bullets">
              {it.bullets?.map((b, j) => <li key={j}><Linkify text={b} /></li>)}
            </ul>
            {it.ref && (
              <div className="pcol__ref">↪ <Linkify text={it.ref} /></div>
            )}
          </li>
        ))}
      </ul>
    </article>
  );
}
