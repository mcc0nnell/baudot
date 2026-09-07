# TRS Fund public oversight view

This slice adds a visualization consumer for Baudot's public/oversight boundary.

The component is intentionally downstream of the checked-in public aggregate projection only:

```text
site/public/data/trs-fund-public-2025-26.json
  -> PublicFundOversight.astro
  -> /public-fund/
```

It does not call Apache Fineract Consumer-Facing, Baudot operator services, Open Banking endpoints, provider endpoints, or any authenticated runtime API.

## Visualization

The primary chart is a public aggregate Fund requirement bridge:

```text
service revenue requirement
+ NDBEDP
+ administrative costs
= gross Fund requirement
- projected Fund balance
= net Fund requirement
```

The page also exposes the same values in semantic HTML tables, plus the aggregate analog/IP-based net requirements, published contribution factors, published service rates, and source/provenance metadata.

## Accessibility

The ECharts view uses the SVG renderer and ARIA component. The chart is supplementary: the complete numerical relationship is also present as normal text and table content.

## Boundary

The page must never imply:

```text
public visibility = provider entitlement
public visibility = machine consent
public visibility = operator authority
public visibility = TRS program authority
public visibility = claim approval
public visibility = payment authorization
```

The validator fails if the visualization component grows runtime/private markers such as `fetch(`, `/api/v1`, cookies, authorization headers, device fingerprints, Open Banking routes, savings routes, or a second JSON data source.

## Dependency alignment

This branch uses Apache ECharts 6.1.0, matching the existing ECharts renderer introduced on #152. It intentionally does not fork a second visualization stack.
