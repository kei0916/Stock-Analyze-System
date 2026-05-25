/* =====================================================================
   Project Visualization — root component。
   ページ内ナビで 3 つの View を切り替える単一の可視化アプリ。
   Docusaurus の /visualization ルートから描画される。
   ===================================================================== */
import React, { useState, useEffect } from 'react';
import { TermProvider, GlobalSearch, useScrollToTop } from './shared';
import StoryView from './views/StoryView';
import ModulesView from './views/ModulesView';
import ProgressView from './views/ProgressView';
import './styles/visualization.css';

const PAGES = [
  { id: 'arch',     label: 'アーキテクチャ' },
  { id: 'modules',  label: 'モジュール詳細' },
  { id: 'progress', label: '進捗・設計意図' },
];
const VIEWS = { arch: StoryView, modules: ModulesView, progress: ProgressView };
const DEFAULT_PAGE = 'arch';
const STORAGE_KEY = 'sas-page';

export default function App() {
  const [page, setPage] = useState(() => localStorage.getItem(STORAGE_KEY) || DEFAULT_PAGE);

  useEffect(() => { localStorage.setItem(STORAGE_KEY, page); }, [page]);
  useScrollToTop(page);

  const View = VIEWS[page] ?? VIEWS[DEFAULT_PAGE];

  return (
    <div className="sas-viz">
      <TermProvider>
        <div className="site-shell">
          <header className="topbar">
            <div className="topbar__brand">
              <span className="topbar__brand-mark">[•]</span>
              <span className="topbar__brand-name">Stock&nbsp;Analyzer</span>
              <span className="topbar__brand-sub">/ backend docs</span>
            </div>

            <nav className="page-nav" aria-label="ページ">
              {PAGES.map((p) => (
                <button
                  key={p.id}
                  className={'page-nav__btn' + (page === p.id ? ' page-nav__btn--active' : '')}
                  onClick={() => setPage(p.id)}
                  aria-current={page === p.id ? 'page' : undefined}
                >
                  <span className="page-nav__dot" />{p.label}
                </button>
              ))}
            </nav>

            <div className="topbar__spacer" />

            <div className="topbar__actions">
              <GlobalSearch />
            </div>
          </header>

          <div className="sas-main">
            <View />
          </div>
        </div>
      </TermProvider>
    </div>
  );
}
