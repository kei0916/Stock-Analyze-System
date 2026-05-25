// @ts-check
const sidebars = {
  main: [
    {
      type: 'doc',
      id: 'overview',
      label: 'Start Here',
    },
    {
      type: 'category',
      label: 'Current State',
      collapsed: false,
      items: [
        // P1: current-work + 自動生成 3 種のみ。Module READMEs は P2-P3 で追加
        { type: 'doc', id: 'current-work', label: 'Current Work' },
        {
          type: 'category',
          label: 'Generated References',
          collapsed: true,
          items: [
            'generated/module-index',
            'generated/dependency-graph',
            'generated/cli-reference',
          ],
        },
      ],
    },
    {
      type: 'category',
      label: 'Archive',
      collapsed: true,
      items: [
        {
          type: 'html',
          value: '<span class="menu__link menu__link--disabled">P3 で追加</span>',
          defaultStyle: true,
        },
        // P3 で archive/adr/, archive/specs/, archive/plans/ を追加
      ],
    },
  ],
};

module.exports = sidebars;
