# Public VRS interoperability implementation archaeology

Status: research / behavioral-donor catalog

This document records public historical implementations that can motivate Baudot interoperability scenarios. None of these implementations is normative authority, a statement about a contemporary provider, or a substitute for standards-grounded independent reduction.

The rule is:

> Historical code may show that a behavior existed, how an implementation decomposed it, or which edge cases were operationally important. It cannot make that behavior correct by itself.

## Source classes

| Class | Meaning in Baudot |
| --- | --- |
| `normative-authority` | A standards or regulatory source from which a requirement may be derived. Historical code is never placed in this class. |
| `historical-test-tool` | A public tool expressly built to exercise interoperability or RUE behavior. Useful for scenario discovery and evidence vocabulary. |
| `historical-behavioral-donor` | Public implementation code whose behavior can motivate a clean-room test. |
| `external-implementation-candidate` | An implementation that may later participate in a controlled live qualification lane under an exact pin. |
| `compatibility-clue-only` | Evidence of an old integration seam or workaround that should be characterized, not copied as a requirement. |

## 1. MITRE/FCC VATRP desktop reference tool

Repository: `mitrefccace/fcc-vatrp`

Pinned revision used for this pass:

```text
9f82469ba8c591869c1e9ce9fc66b866ab5983a4
```

The repository README describes VATRP as an FCC functional test tool for RUE specification compliance and VRS provider interoperability. That statement makes the repository especially valuable as historical test-tool archaeology, but it does not make its implementation choices normative.

### Provider discovery

Observed seam:

```text
VATRP.App/Services/ServiceManager.cs
```

At the pinned revision, `UpdateProvidersList()` / `LoadJsonProvidersAsync()` retrieve a JSON provider-domain list from a configured server, materialize provider label/domain/icon information, and fall back to a local `Custom` provider when remote loading fails.

Baudot use:

- behavioral donor for `RUE-PROV-001` and provider-list failure states;
- evidence that provider discovery and provider runtime behavior were treated as separable application concerns;
- motivation for deterministic unavailable/malformed/duplicate provider-list controls.

Do not infer:

- RFC 9248 ProviderList schema compliance;
- contemporary provider discovery endpoints;
- trustworthiness of a downloaded provider list;
- current provider inventory.

### One-stage dial-around route construction

Observed seam:

```text
VATRP.App/Services/MediaActionHandler.cs
```

At the pinned revision, outbound call construction:

1. parses the dialed target;
2. prefers `App.CurrentAccount.DialAroundProviderAddress` when configured;
3. constructs `sip:{user}@{DialAroundProviderAddress}`;
4. appends `;user=phone` for an E.164-looking user and `;user=dialstring` otherwise; and
5. passes the resulting destination to the Linphone service separately from RTT enablement, video/audio policy, geolocation URI, and privacy.

This independently echoes the route shape now captured in Baudot `RUE-DIAL-001`, whose normative authority remains RFC 9248 rather than VATRP.

Baudot use:

- behavioral donor for one-stage dial-around target correlation;
- historical evidence that provider selection and the logical SIP target were explicit state;
- negative-control donor for selected-provider drift and E.164 user-parameter handling.

Do not infer:

- that this exact construction is sufficient for RFC 9248 conformance;
- current provider routing behavior;
- DNS/TLS/SBC behavior;
- media readiness from call initiation.

### RTT negotiation boundary

Observed seams:

```text
VATRP.Core/Model/Configuration.cs
VATRP.App/Services/MediaActionHandler.cs
VATRP.Core/Interfaces/ILinphoneService.cs
VATRP.Core/Services/LinphoneService.cs
VATRP.LinphoneWrapper/LinphoneAPI.cs
```

The application keeps RTT as an explicit configuration input. Outgoing call creation carries `rttEnabled` separately from destination/video/audio/geolocation. The Linphone wrapper exposes `linphone_call_params_enable_realtime_text(...)`. Incoming acceptance intersects local RTT enablement with the remote call parameters before enabling real-time text on the answer.

Baudot use:

- behavioral donor for `RUE-RTT-001` negotiation arms;
- strong motivation to preserve local policy, remote offer, negotiated RTT, first T.140 observation, and terminal RTT readiness as distinct facts.

Do not infer:

- RFC 4103 packet correctness;
- RFC 2198 redundancy correctness;
- T.140 semantic correctness;
- readiness merely because the Linphone call parameter says RTT is enabled.

### Emergency and RUE-owner metadata

Observed seam:

```text
VATRP.Core/Services/LinphoneService.cs
```

For configured emergency numbers, the historical implementation adds geolocation-related signaling and conditionally attaches a `Geolocation` URI. It also derives a `Call-Info` URI with `purpose=rue-owner` when a geolocation URI is available.

Baudot use:

- behavioral donor for offline-only `RUE-EMERG-001` construction tests;
- donor for keeping emergency route selection, location presence, owner/contact material, and call establishment as separate evidence planes;
- useful source of malformed/missing-location negative controls.

Do not infer:

- current emergency-call requirements from this code;
- correctness of its historical header construction;
- permission to originate emergency traffic in a public test;
- successful PSAP/provider processing.

All Baudot emergency fixtures remain synthetic and offline unless an expressly authorized isolated environment exists.

## 2. MITRE/FCC WebRTC VATRP experiment

Repository: `mitrefccace/fcc-vatrp-webrtc`

Pinned revision used for this pass:

```text
2aa96bb7306d0482da9ca4412a6cf520ded6a6cc
```

The pinned commit is dated 2021-08-26 and identifies the project as a WebRTC VATRP RUE operability test tool. It should be treated separately from the earlier desktop/Linphone VATRP rather than as a later version of one monolithic implementation.

### Runtime split

Observed public architecture includes:

```text
Electron / React UI
JsSIP 3.4.x dependency
custom JsSIP files
Janus SIP bridge experiment
location server
sample JSON profile
```

The README explicitly instructs builds to copy a custom JsSIP layer for geolocation functionality. The custom `RTCSession.js` adds a `locationBody` input to `connect()` and appends it to the outgoing request body during initial request construction.

Baudot use:

- compatibility clue for SIP/WebRTC gateway and location-body edge cases;
- behavioral donor for `RUE-EMERG` malformed/multipart/location handling tests;
- donor for the rule that a browser/WebRTC session, SIP registration, and accessibility modality readiness are independently observable.

Do not infer:

- that the custom JsSIP behavior matches current RFC 9248 emergency signaling;
- that body concatenation is a normative SIP construction pattern;
- browser RTT support from ordinary WebRTC media state;
- production Janus/SIP gateway behavior.

### Historical profile experiment

Observed seam:

```text
docs/vatrp_example_profile.json
```

The sample profile contains a version/lifetime, phone number, provider domain, SIP credentials, contacts placeholder, a `sendLocationWithRegistration` flag, and an `rttserver` URL.

Baudot use:

- provenance for historical provider/profile provisioning experiments;
- donor for configuration-lifetime, registration-location, credential-separation, and RTT-service-address negative controls.

Do not infer:

- RFC 9248 ProviderConfig or RUEConfig schema conformance;
- a contemporary provisioning endpoint;
- that a separate RTT server is required by RFC 9248.

Baudot's normative provisioning fixtures continue to follow the RFC 9248 OpenAPI schema, including `providerEntryPoint` where the normative schema differs from an illustrative prose example.

## 3. FCC / VTC Secure Linphone lineage

Repository: `FCC/vtc_secure_linphone`

Pinned repository revision:

```text
60f23ce7845cdaa13f442bb9fa8087336dbfd495
```

At this revision, the `mediastreamer2` gitlink resolves to the separate VTC Secure fork:

```text
VTCSecureLLC/mediastreamer2
17d514f0e5c6adc46c791e75a626f91369baa37a
```

This matters for provenance: behavior found in that media layer must be attributed to the exact VTC Secure fork/revision, not to modern upstream Linphone or Mediastreamer2 generally.

Baudot use:

- historical implementation lineage for the staged modern Linphone qualification work;
- candidate source archaeology for H.264, SRTP, ICE, and media behavior when an exact path can be identified;
- provenance reminder that top-level client and media submodule are distinct evidence sources.

Do not infer:

- modern Linphone behavior from the 2016 FCC fork;
- RTT/RFC 4103 support until an exact implementation path is located;
- conformance from dependency presence.

## 4. Relationship to current Baudot implementations

Historical donors never receive terminal verdict authority.

```text
public standard / regulation
          |
          v
Baudot portable scenario
          |
          +------ historical donor --> scenario motivation only
          |
          +------ JAIN SIP ----------> controlled signaling observation
          +------ PJSIP/Linphone ----> native implementation behavior
          +------ Wiretap -----------> controlled network evidence
          |
          v
independent Baudot reduction
          |
          v
bounded verdict
```

This preserves a useful distinction:

```text
VATRP did X
    !=
RFC 9248 requires X
    !=
a current provider does X
    !=
Baudot has proven X interoperable
```

## Immediate scenario harvest

The public archaeology supports these additions without provider probing:

1. `RUE-PROV-002` — provider-list unavailable/malformed/cache-fallback classification without silently selecting a provider.
2. `RUE-DIAL-003` — selected dial-around domain must survive E.164 and explicit-SIP-URI input variants.
3. `RUE-RTT-003` — local RTT enabled + remote RTT absent must not produce `rttReady`.
4. `RUE-RTT-004` — remote RTT offered + local RTT disabled must remain explicitly unavailable rather than partially ready.
5. `RUE-EMERG-002` — offline geolocation present/missing/malformed construction matrix.
6. `RUE-OWNER-002` — synthetic owner-contact signaling separated from geolocation and from call success.
7. `RUE-GW-001` — WebRTC/SIP gateway can be connected while RTT path remains independently unproven.

Each should be grounded first in the current normative source, then use the historical code only to choose useful manipulated arms.
