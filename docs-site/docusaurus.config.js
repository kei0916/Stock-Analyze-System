// @ts-check
const config = {
  title: 'Stock Analyze — Living Docs',
  tagline: '3-layer living documentation',
  favicon: 'img/favicon.ico',
  url: 'http://localhost',
  baseUrl: '/',
  onBrokenLinks: 'warn',
  onBrokenMarkdownLinks: 'warn',
  markdown: {
    mermaid: true,
  },
  // @easyops-cn/docusaurus-search-local は「テーマ」として登録する
  // （公式 README の Usage 形式）。plugins ではない。
  themes: [
    '@docusaurus/theme-mermaid',
    [
      require.resolve('@easyops-cn/docusaurus-search-local'),
      {
        hashed: true,
        language: ['en', 'ja'],
        // docs の routeBasePath を '/' にしているので、検索側にも明示する。
        // 既定値 'docs' のままだと検索インデックスのパスがずれる。
        docsRouteBasePath: '/',
      },
    ],
  ],
  i18n: {
    defaultLocale: 'ja',
    locales: ['ja'],
  },
  presets: [
    [
      'classic',
      /** @type {import('@docusaurus/preset-classic').Options} */
      ({
        docs: {
          path: 'docs',
          routeBasePath: '/',
          sidebarPath: require.resolve('./sidebars.js'),
          // L2 `overview.md` をトップに据える
        },
        blog: false,
        theme: {
          customCss: require.resolve('./src/css/custom.css'),
        },
      }),
    ],
  ],
  themeConfig: {
    navbar: {
      title: 'Stock Analyze — Living Docs',
      items: [
        { to: '/visualization', label: 'プロジェクト可視化', position: 'left' },
      ],
    },
    colorMode: {
      defaultMode: 'dark',
      respectPrefersColorScheme: true,
    },
  },
};

module.exports = config;
