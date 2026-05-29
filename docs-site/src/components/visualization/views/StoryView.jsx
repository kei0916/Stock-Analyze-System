/* =====================================================================
   案A — Story: 縦スクロール / 章構成の物語型ドキュメント
   ===================================================================== */
import React, { useState, useEffect } from 'react';
import { CONTENT } from '../data/content';
import { SectionHeading, TermLink, Linkify } from '../shared';

export default function StoryView() {
  const C = CONTENT;
  const [active, setActive] = useState(C.chapters[0].id);

  // ScrollSpy
  useEffect(() => {
    const els = C.chapters.map(c => document.getElementById("ch-" + c.id)).filter(Boolean);
    const obs = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter(e => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) {
          const id = visible[0].target.id.replace("ch-", "");
          setActive((prev) => (prev === id ? prev : id));
        }
      },
      { rootMargin: "-30% 0px -55% 0px" }
    );
    els.forEach(el => obs.observe(el));
    return () => obs.disconnect();
  }, []);

  return (
    <div className="story">
      {/* Progress rail */}
      <nav className="story__rail" aria-label="進行状況">
        {C.chapters.map(c => (
          <button
            key={c.id}
            className={"story__rail-item" + (active === c.id ? " story__rail-item--active" : "")}
            onClick={() => document.getElementById("ch-" + c.id)?.scrollIntoView({ behavior: "smooth", block: "start" })}
          >
            <span className="story__rail-bar" />
            <span className="story__rail-n">{c.n}</span>
            <span>{c.title}</span>
          </button>
        ))}
      </nav>

      <div className="page">
        {/* HERO */}
        <section className="story__hero">
          <div className="story__hero-tag">Backend Internals · v0.1</div>
          <h1 className="story__hero-title">
            株式分析の<br/>
            バックエンドを、<span style={{color:"var(--accent)"}}>10分</span>で歩く。
          </h1>
          <p className="story__hero-sub">
            <strong style={{color:"var(--fg-1)"}}>{C.meta.name}</strong> は、米国 (<TermLink k="secEdgar"/>) と日本 (<TermLink k="edinet"/>) の有価証券報告書を取り込み、
            指標計算と <TermLink k="rag" /> 分析を行うローカル Web アプリです。
            このページは <strong style={{color:"var(--fg-1)"}}>開発者向け</strong>に、プロセス構成・データフロー・services / models の中身までを順番に辿ります。
          </p>
          <div className="story__hero-meta">
            <span>repo · <strong>{C.meta.repo}</strong></span>
            <span>branch · <strong>{C.meta.branch}</strong></span>
            <span>python · <strong>{C.meta.python}</strong></span>
            <span>db · <strong>{C.meta.db}</strong></span>
            <span>llm · <strong>{C.meta.llm}</strong></span>
          </div>
        </section>

        {/* 01 — What */}
        <section className="story__chapter" id="ch-what">
          <SectionHeading n="01" title="このシステムは何？" sub="目的・対象・できること を 1 段落で。" />
          <p className="story__lead">
            投資判断のために、<TermLink k="filing">有価証券報告書 (Filing)</TermLink> をベースに
            <TermLink k="per" />・<TermLink k="pbr" />・<TermLink k="evEbitda" />・<TermLink k="roe" /> など
            の指標を計算し、長期の推移を可視化する。
            さらに <TermLink k="rag" /> パイプラインで Filing 本文を <TermLink k="llm" /> に渡し、
            「ビジネスモデル」「リスク要因」などの定型分析と自由質問ができる。
          </p>
          <p className="story__lead story__lead--muted">
            実装は 3 プロセス。<TermLink k="webLayer">Web</TermLink> (操作受付)、
            <TermLink k="worker">Worker</TermLink> (重い LLM 推論)、
            <TermLink k="cli">CLI</TermLink> (バッチ・cron)。
            重い処理を Web プロセスから外に出しているのが構成上の急所。
          </p>
        </section>

        {/* 02 — Surfaces */}
        <section className="story__chapter" id="ch-surfaces">
          <SectionHeading n="02" title="プロセス構成" sub="Web / Worker / CLI の 3 プロセス。同じ services 層を共有する shared-nothing 構成。" />
          <p className="story__lead story__lead--muted">
            Web プロセスは <strong style={{color:"var(--fg-1)"}}>LLM を呼ばない</strong>。
            分析リクエストは DB に <span className="inline-code">AnalysisJob</span> を作るだけで応答を返し、
            別プロセスの <TermLink k="worker">Worker</TermLink> がそれを polling して LLM 推論を回す。
            両者は DB だけで連携する。
          </p>
          <div className="surface-grid">
            {C.surfaces.map(s => (
              <article key={s.id} className="surface-card">
                <div className="surface-card__name">{s.name}</div>
                <h3 className="surface-card__title">{s.name}</h3>
                <div className="surface-card__sub">{s.sub}</div>
                <div className="surface-card__who">FOR · {s.who}</div>
                <p className="surface-card__what"><Linkify text={s.what} /></p>
                <div className="surface-card__examples">
                  {s.examples.map(ex => <div key={ex} className="surface-card__ex">{ex}</div>)}
                </div>
              </article>
            ))}
          </div>
        </section>

        {/* 03 — Flow */}
        <section className="story__chapter" id="ch-flow">
          <SectionHeading n="03" title="データはこう流れる" sub="外部 API → DB → 指標 → UI の 4 ステップ。" />
          <div className="flow">
            <div className="flow__row">
              <div className="flow__node">
                <div className="flow__node-label">External</div>
                <div className="flow__node-name">EDGAR / EDINET / Yahoo</div>
              </div>
              <div className="flow__arrow">→<span className="flow__arrow-label">fetch</span></div>
              <div className="flow__node">
                <div className="flow__node-label">ingestion</div>
                <div className="flow__node-name">外部取得</div>
              </div>
              <div className="flow__arrow">→<span className="flow__arrow-label">save</span></div>
              <div className="flow__node">
                <div className="flow__node-label">DB (SQLite)</div>
                <div className="flow__node-name">SQLAlchemy</div>
              </div>
              <div className="flow__arrow">→<span className="flow__arrow-label">render</span></div>
              <div className="flow__node">
                <div className="flow__node-label">UI</div>
                <div className="flow__node-name">Web / CLI</div>
              </div>
            </div>
            {C.flow.map(f => (
              <div key={f.step} className="flow__step">
                <div className="flow__step-n">{String(f.step).padStart(2, "0")}</div>
                <div>
                  <h4 className="flow__step-title">
                    {f.from} <span style={{color:"var(--fg-3)"}}>→</span> {f.to}
                    <small>{f.label}</small>
                  </h4>
                  <p className="flow__step-desc"><Linkify text={f.desc} /></p>
                  {f.sources && (
                    <div className="flow__step-sources">
                      {f.sources.map(s => (
                        <span key={s} className="chip">
                          <TermLink k={s} plain />
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 04 — RAG Pipeline */}
        <section className="story__chapter" id="ch-rag">
          <SectionHeading n="04" title="RAG パイプライン" sub="ADR-004 後の構成。LLM 呼び出しを step 3 だけに閉じ込めた。" />
          <p className="story__lead story__lead--muted">
            この 4 ステップのうち、<strong style={{color:"var(--fg-1)"}}>LLM が要るのは step 3 だけ</strong>。
            section 抽出 (step 2) は <TermLink k="sectionExtractor" /> が edgartools.HTMLParser を使って
            決定論的に行う。これで定型分析の LLM 呼び出しが <span className="inline-code">数十回 → 4 回</span> になった。
          </p>
          <div className="rag-pipeline">
            {C.ragPipeline.map(p => (
              <div key={p.step} className={"rag-step" + (p.llm ? " rag-step--llm" : "")}>
                <div className="rag-step__n">{String(p.step).padStart(2, "0")}</div>
                <div className="rag-step__body">
                  <div className="rag-step__head">
                    <span className="rag-step__name">{p.name}</span>
                    <span className={"rag-step__badge" + (p.llm ? " rag-step__badge--llm" : "")}>
                      {p.llm ? "LLM 呼び出しあり" : "LLM 呼び出しなし"}
                    </span>
                  </div>
                  <div className="rag-step__file">{p.file}</div>
                  <p className="rag-step__desc"><Linkify text={p.desc} /></p>
                  {p.detail && <p className="rag-step__detail"><Linkify text={p.detail} /></p>}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 05 — Layers */}
        <section className="story__chapter" id="ch-layers">
          <SectionHeading n="05" title="コードの 7 層" sub="src/stock_analyze_system/ 配下の構造。役割が層で分かれている。" />
          <p className="story__lead story__lead--muted">
            原則：<strong>上の層は下の層しか呼ばない</strong>。
            たとえば <TermLink k="webLayer">web</TermLink> は <TermLink k="servicesLayer">services</TermLink> だけを呼び、
            <TermLink k="modelsLayer">models</TermLink> を直接いじったりはしません。
            <TermLink k="repositoryPattern" /> でテストもしやすくなります。
          </p>
          <table className="layer-table">
            <thead>
              <tr><th>Path</th><th>Role</th><th>In</th><th>Out</th></tr>
            </thead>
            <tbody>
              {C.layers.map(l => (
                <tr key={l.id}>
                  <td className="path">{l.path}</td>
                  <td className="role">
                    {l.term ? <TermLink k={l.term}>{l.role}</TermLink> : l.role}
                  </td>
                  <td className="dir">← {l.inbound}</td>
                  <td className="dir">→ {l.outbound}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        {/* 06 — Services */}
        <section className="story__chapter" id="ch-services">
          <SectionHeading n="06" title="Services の中身" sub="services/ 配下 29 ファイルを役割でグルーピング。" />
          <p className="story__lead story__lead--muted">
            <TermLink k="servicesLayer">services 層</TermLink> はビジネスロジックの集約点。
            CLI / Web / Worker のすべてがここを通じて DB を読み書きする。
          </p>
          <div className="svc-grid">
            {C.services.map(cat => (
              <div key={cat.category} className="svc-card">
                <div className="svc-card__cat">{cat.category}</div>
                <ul className="svc-card__items">
                  {cat.items.map(it => (
                    <li key={it.file} className="svc-card__item">
                      <div className="svc-card__file">
                        {it.term ? <TermLink k={it.term}>{it.file}</TermLink> : it.file}
                        {it.lines && <span className="svc-card__lines">{it.lines.toLocaleString()}b</span>}
                      </div>
                      <div className="svc-card__role"><Linkify text={it.role} /></div>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        {/* 07 — Models */}
        <section className="story__chapter" id="ch-models">
          <SectionHeading n="07" title="DB スキーマ" sub="models/ 配下、SQLAlchemy 2.x の declarative 定義 17 ファイル。" />
          <p className="story__lead story__lead--muted">
            DB は <strong style={{color:"var(--fg-1)"}}>SQLite</strong>。aiosqlite で非同期化。
            起動時に idempotent な <span className="inline-code">ALTER TABLE</span> でカラム追加に対応する仕組み (base.py)。
          </p>
          <div className="models-grid">
            {C.models.map(m => (
              <div key={m.file} className="model-card">
                <div className="model-card__name">{m.name}</div>
                <div className="model-card__file">{m.file}</div>
                <div className="model-card__desc"><Linkify text={m.desc} /></div>
              </div>
            ))}
          </div>
        </section>

        {/* 08 — Stack */}
        <section className="story__chapter" id="ch-stack">
          <SectionHeading n="08" title="技術スタック" sub="pyproject.toml に書いてある依存を、カテゴリ別に整理。" />
          <div className="stack-grid">
            {C.stack.map(cat => (
              <div key={cat.category} className="stack-card">
                <div className="stack-card__cat">{cat.category}</div>
                <div className="stack-card__items">
                  {cat.items.map(k => <span key={k} className="chip"><TermLink k={k} plain /></span>)}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* 09 — Startup */}
        <section className="story__chapter" id="ch-start">
          <SectionHeading n="09" title="起動・開発フロー" sub="4 コマンドで動く。" />
          <div className="startup">
            {C.startup.map(s => (
              <div key={s.step} className="startup__step">
                <div className="startup__n">{String(s.step).padStart(2, "0")}</div>
                <div>
                  <h4 className="startup__title">{s.title}</h4>
                  <pre className="startup__cmd">{s.cmd}</pre>
                  <p className="startup__note"><Linkify text={s.note} /></p>
                </div>
              </div>
            ))}
          </div>
          <p className="story__lead story__lead--muted" style={{marginTop:"var(--space-5)"}}>
            <TermLink k="worker">分析ワーカー</TermLink> が止まっていると、
            ジョブは <span className="inline-code">pending</span> のまま動きません。
            Web トップバーに赤いバッジが出るので、起動忘れに気付けます。
          </p>
          <footer className="footer">
            kei0916 / Stock-Analyze-System · ドキュメントは feat/sec-section-extractor を参照
          </footer>
        </section>
      </div>
    </div>
  );
}
