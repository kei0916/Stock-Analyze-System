/* =====================================================================
   /visualization — プロジェクト可視化ページ。
   アプリ本体は localStorage / IntersectionObserver を使うクライアント専用なので
   <BrowserOnly> で囲んで描画する。
   ===================================================================== */
import React from 'react';
import Layout from '@theme/Layout';
import BrowserOnly from '@docusaurus/BrowserOnly';
import App from '@site/src/components/visualization/App';

export default function VisualizationPage() {
  return (
    <Layout
      title="プロジェクト可視化"
      description="Stock Analyze System のバックエンド構成・モジュール・進捗・設計意図をビギナー開発者向けに可視化したドキュメント"
    >
      <BrowserOnly
        fallback={
          <div style={{ padding: '6rem 1rem', textAlign: 'center', opacity: 0.6 }}>
            読み込み中…
          </div>
        }
      >
        {() => <App />}
      </BrowserOnly>
    </Layout>
  );
}
