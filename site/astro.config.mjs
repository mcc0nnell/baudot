import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://mcc0nnell.github.io',
  base: '/baudot',
  integrations: [
    starlight({
      title: 'Baudot',
      description: 'Accessible real-time communications, specified as behavior before implementation.',
      favicon: '/baudot/favicon.svg',
      customCss: ['./src/styles/custom.css'],
      social: [
        {
          icon: 'github',
          label: 'Baudot on GitHub',
          href: 'https://github.com/mcc0nnell/baudot',
        },
      ],
      editLink: {
        baseUrl: 'https://github.com/mcc0nnell/baudot/edit/main/site/',
      },
      sidebar: [
        {
          label: 'Overview',
          items: [
            { label: 'Home', slug: '' },
            { label: 'Why Baudot', slug: 'why-baudot' },
          ],
        },
        {
          label: 'Proving ground',
          items: [{ label: 'Scenario catalog', slug: 'scenarios' }],
        },
        {
          label: 'Architecture',
          items: [
            { label: 'System shape', slug: 'architecture' },
            { label: 'Evidence model', slug: 'evidence' },
          ],
        },
        {
          label: 'Trust',
          items: [{ label: 'Provenance', slug: 'provenance' }],
        },
      ],
    }),
  ],
});
