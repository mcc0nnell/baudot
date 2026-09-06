# Baudot site

The GitHub Pages site is an Astro + Starlight projection of Baudot's repository documentation and proving-ground model.

It currently presents two evidence-first proving lanes:

- accessible real-time communications interoperability; and
- the public-data-calibrated Synthetic TRS Fund Lab.

The homepage, architecture, evidence, provenance, and Why Baudot pages share one rule across both lanes: implementation facts are evidence, not authority to make a broader claim.

## Local development

```bash
cd site
npm install
npm run dev
```

Build the static site with:

```bash
npm run build
```

The production configuration targets `https://mcc0nnell.github.io/baudot/` and the Fund Lab route is `/baudot/fund-lab/`.

GitHub Pages deploys from `main`; pull-request site changes are build-checked first and become public after the corresponding change lands on `main` and the Pages workflow succeeds.

## Authority

The site explains repository state; it does not promote scenario status or create conformance claims. Machine-readable scenario definitions, preserved evidence, ADRs, reducers, Fund fixtures, and journal contracts remain authoritative for their declared scopes.
