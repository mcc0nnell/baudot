# Public VRS interoperability evidence map

Status: research / test-design input

This document records a clean-room map of publicly available Video Relay Service (VRS) interoperability requirements and operational evidence. It is intended to drive Baudot scenarios and fixtures without copying provider-private configuration, subscriber data, production traces, credentials, or non-public TRS Numbering Directory data.

The central rule is the same as the rest of Baudot: **a published requirement identifies a behavior to test; it does not prove that any implementation satisfies it.**

## Evidence hierarchy

The public VRS interoperability surface has three distinct standards layers and one operational-evidence layer. They should not be collapsed into one claim.

| Layer | Public source | What it can support |
| --- | --- | --- |
| U.S. regulatory provider baseline | 47 CFR § 64.621 | VRS providers have interoperability and portability obligations; the codified technical baseline incorporates the SIP Forum VRS US Providers Profile TWG-6-1.0. |
| Industry provider profile | SIP Forum VRS Task Group | TWG-6-1.0 is the archived 2015 profile. TWG-6-2.0 was ratified April 23, 2020, and the archive publishes a version with changes highlighted from 1.0. |
| RUE ↔ provider / RUE ↔ RUE interface | IETF RFC 9248, June 2022 | A Standards Track profile for Relay User Equipment registration, calling, media, dial-around, provisioning, emergency signaling, call transfer, and related behavior. |
| Operational interoperability evidence | 2019 industry-wide event; MITRE National Test Lab | Evidence that multi-provider SIP interoperability has been exercised at scale and that interoperability testing remains an operational discipline. It is not a public provider conformance matrix. |

### Source links

- 47 CFR § 64.621: <https://www.law.cornell.edu/cfr/text/47/64.621>
- SIP Forum VRS Task Group archive: <https://www.sipforum.org/download-category/vrs-task-group/>
- RFC 9248: <https://www.rfc-editor.org/rfc/rfc9248.html>
- IETF 105 RUM history / 2019 interoperability-event material: <https://datatracker.ietf.org/meeting/105/materials/slides-105-rum-rum-history-background-00>
- MITRE National Test Lab story: <https://www.mitre.org/news-insights/impact-story/mitre-connects-improving-telecommunications-deaf-community>

Accessed for this research pass: 2026-09-05.

## Important version boundary

As of this research pass, the codified § 64.621 text still identifies **TWG-6-1.0 (September 23, 2015)** as the incorporated VRS Provider Interoperability Profile. The SIP Forum separately publishes **TWG-6-2.0 (April 23, 2020)** as the newer ratified industry profile.

Baudot must therefore preserve these as separate authorities:

```text
regulatory baseline       = TWG-6-1.0 as incorporated by § 64.621
newer industry profile    = TWG-6-2.0
RUE interoperability      = RFC 9248
```

A test derived from 2.0 must not be described as a current § 64.621 requirement merely because 2.0 is newer. A clause-by-clause 1.0 → 2.0 delta should be transcribed only from the official SIP Forum redline and reviewed independently before it becomes a Baudot assertion.

## Operational evidence

The public record is strong enough to show that provider interoperability is not merely theoretical.

The 10th industry-wide VRS interoperability event, held April 8–11, 2019, included Convo, Global VRS, Purple, Sorenson VRS, ZVRS, nWise, and MITRE. Public event material reports more than 1,800 SIP interoperability tests across 33 VRS endpoints, including point-to-point and VRS dial-around calls. The same material records discussion of a revised provider profile covering encryption, 911 geolocation, other service improvements, and STIR/SHAKEN.

MITRE reported in 2024 that its FCC-sponsored National Test Lab performs as many as 24,000 manual and automated test calls per quarter for interoperability and service-quality analysis. MITRE also reports that more than one quarter of test calls exposed interoperability or communications issues when the lab began testing in summer 2017.

These facts justify a broad, repeatable interoperability matrix. They do **not** identify which current provider supports which optional behavior, disclose the National Test Lab test suite, or establish contemporary provider defects.

## RFC 9248 behavior map

RFC 9248 gives Baudot a clean public contract for neutral RUE/provider testing.

| Test family | Public behavior to exercise | Baudot evidence boundary |
| --- | --- | --- |
| `RUE-REG` | SIP registration; configured provider domain; SIP outbound; DNS-based resolution; TLS-preferred service discovery; supported digest authentication | Preserve configuration input, DNS selection, transport, REGISTER transaction, authentication facts, and registration result separately. |
| `RUE-CALL` | Outbound and inbound SIP calls; E.164 URI representation; direct/P2P and relay use cases | Route identity, Request-URI, dialog establishment, and modality readiness remain separate facts. |
| `RUE-DIAL` | One-stage and two-stage dial-around | Provider selection must survive into the actual call route; success through the default provider does not prove that the selected dial-around provider was used. |
| `RUE-MIDCALL` | re-INVITE; in-dialog REFER; Replaces; full-frame refresh fallback | Existing Baudot re-INVITE and REFER scenarios can be reused as bounded evidence lanes. |
| `RUE-SEC` | SRTP/SRTCP profile requirements and WebRTC-derived transport requirements | Transport encryption is observed independently from participant authorization and any E2EE claim. |
| `RUE-RTT` | T.140 via RFC 4103; one original plus two redundant generations; 300 ms transmission interval; RFC 9071 multiparty RTT; RFC 8865 gateway path for browser WebRTC | Negotiate RTT, observe implementation-generated T.140, validate redundancy and timing independently, then derive readiness. |
| `RUE-VIDEO` | H.264 mandatory-to-implement; VP8 optional; feedback mechanisms | Negotiated codec, RTP receipt, decoder input, decoded frame, and rendered video remain separate observations. |
| `RUE-AUDIO` | WebRTC audio profile behavior, including mandatory-to-implement capabilities | Audio negotiation and audio receipt do not imply video or RTT readiness. |
| `RUE-ICE` | Full ICE, with ICE-lite interworking permitted | Preserve candidate gathering, selected pair, connectivity, and media receipt separately. |
| `RUE-PROV` | HTTPS provider list and provider-specific configuration | Provider discovery/configuration is input evidence. It does not confer trust or prove runtime reachability. |
| `RUE-OWNER` | RUE owner contact material using xCard-related signaling | Use only synthetic contact records in fixtures. Never ingest a subscriber contact export into the public test corpus. |
| `RUE-EMERG` | Emergency-call signaling, geolocation behavior, LoST/provider fallback behavior, and additional emergency data | Synthetic/offline only unless an expressly authorized test environment exists. No public Baudot test should originate a real emergency call. |

## First clean-room matrix

The machine-readable companion is [`../testkit/vrs/public-interoperability-matrix-v1.json`](../testkit/vrs/public-interoperability-matrix-v1.json).

The first implementation order should be:

1. `RUE-REG-001` — local TLS registration and provider-domain preservation.
2. `RUE-DIAL-001` — one-stage dial-around through synthetic provider A to synthetic provider B.
3. `RUE-DIAL-002` — two-stage front-door selection as a separate route shape.
4. `RUE-RTT-001` — negotiated RFC 4103/T.140 with two redundant generations and independently measured timing.
5. `RUE-VIDEO-001` — H.264 negotiation followed by implementation-generated RTP and eventually decode/render evidence.
6. `RUE-SEC-001` — SRTP/SRTCP evidence without converting transport security into an E2EE claim.
7. `RUE-PROV-001` — deterministic provider-list retrieval and selection.
8. `RUE-EMERG-001` — offline validation of emergency location/additional-data construction only.

## Mapping to existing Baudot work

Baudot already has important pieces of this architecture:

- `BAUDOT-INTEROP-003` separates re-INVITE / SDP freshness / RTT readiness.
- `BAUDOT-INTEROP-004` separates REFER acceptance, NOTIFY progression, replacement-dialog establishment, target correlation, RTT readiness, and old-leg release.
- the active iTRS mock work provides a clean-room route-authority seam without using live subscriber data;
- the staged Linphone lane is a candidate second independent native RTT implementation, not a conformance oracle;
- PJSIP, Elixip, JAIN SIP, Wiretap, and the Baudot reference reducers already provide the implementation/evidence separation needed to execute the matrix.

The new VRS layer should therefore **compose existing evidence**, not create VRS-specific shortcuts inside reducers.

```text
public requirement
      |
      v
portable VRS/RUE test row
      |
      +--> provider/routing fixture
      +--> SIP implementation(s)
      +--> native media implementation(s)
      +--> controlled network
      |
      v
source-separated observations
      |
      v
Baudot terminal reducer
```

## Representative one-stage dial-around fixture

`testkit/vrs/fixtures/rue-one-stage-dial-around-invite.txt` is a Baudot-authored synthetic SIP request. It is not copied from a provider trace. Its purpose is to bind the following public RFC 9248 facts into one deterministic input:

- called E.164 number remains in the Request-URI and To URI;
- the Request-URI uses the selected dial-around provider domain;
- the From identity remains associated with the synthetic user's default provider domain;
- transport and dialog identifiers are fixture values, not production observations.

The fixture intentionally omits SDP. Media negotiation belongs to separate evidence lanes so that a correct dial-around route cannot accidentally be promoted into an H.264, SRTP, or RTT result.

## Provider discovery fixture

`testkit/vrs/fixtures/provider-list-v1.json` is a synthetic RFC 9248-shaped provider list. It contains only reserved example domains and invented provider labels.

It can support deterministic provider-selection tests. It cannot support claims about which real VRS providers expose RFC 9248 provisioning endpoints.

## What this OSINT pass does not establish

This research does not establish:

- current behavior of Sorenson, Convo, ZP/Purple, Global VRS, nWise, or any other provider;
- access to, contents of, or behavior of the live TRS Numbering Directory;
- the contents of MITRE's non-public National Test Lab test suite;
- current provider support for every RFC 9248 feature;
- that TWG-6-2.0 has been incorporated into § 64.621;
- VRS certification or regulatory compliance of Baudot or any implementation;
- SIP, RFC 4103, T.140, SRTP, ICE, H.264, RFC 9248, or provider-profile conformance; or
- authorization to probe production VRS infrastructure.

## Promotion rule

A row in the public matrix may become an executable Baudot scenario when:

1. its normative/public source is pinned;
2. the fixture is synthetic or independently generated;
3. implementation behavior is observed rather than inferred;
4. the terminal reducer has no provider-specific branch;
5. positive and negative/control arms exist where the distinction matters; and
6. the scenario states exactly what additional evidence would be required before any stronger claim.

That keeps the OSINT useful: public standards tell Baudot **what to challenge**, while controlled experiments tell Baudot **what actually happened**.
