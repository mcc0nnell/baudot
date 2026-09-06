# Tilden-authorized reselection recovery

`TILDEN-HANDOFF-004` proves a routing-authority boundary after a selected route fails.

Baudot may observe that a selected route failed. It may not promote another candidate on its own. A second route attempt requires a second Tilden selection with a distinct `selectionId`.

## Controlled sequence

```text
TildenSelection #1
  selectionId = sel-reselection-initial-0001
  selected = sip:unavailable@127.0.0.1:5390;transport=udp
  eligible = sip:provider-a@127.0.0.1:5310
        |
        v
Baudot attempts exactly the selected URI
        |
        v
no dialog established
        |
        +-- UDP sentinel on provider-a observes 0 datagrams
        |
        v
NO BAUDOT AUTONOMOUS FALLBACK
        |
        v
TildenSelection #2
  selectionId = sel-reselection-recovery-0002
  failed = prior selected URI
  selected = sip:provider-a@127.0.0.1:5310
        |
        v
Baudot runs TILDEN-HANDOFF-003
        |
        v
selected provider -> REFER -> PJSIP 2.17 -> native T.140
        |
        v
independent Baudot rttReady
        |
        v
old provider leg released after readiness
```

## Why the sentinel matters

The first Tilden selection already reveals `provider-a` as an eligible candidate. That alone is not authorization to signal it.

During the failed first attempt, a UDP sentinel binds the eligible provider endpoint. The terminal reducer requires `datagramCount=0`. The first-attempt Baudot evidence must also contain exactly one `sip.invite.sent` event, and its Request-URI must be the selected unavailable endpoint.

This makes the negative claim executable: before the second Tilden selection is consumed, Baudot emitted no observed signaling toward the eligible recovery provider.

## Reselection authority

The recovery fixture is not a mutation of the first selection. It has a new `selectionId` and records the prior selected endpoint as `failed` while promoting the previously eligible provider to `selected`.

The runner deliberately does not adapt the recovery selection until after:

1. the first selected route has failed;
2. the first attempt has emitted its evidence; and
3. the eligible-provider sentinel has proven zero pre-reselection traffic.

Only then may Baudot run the existing `TILDEN-HANDOFF-003` provider -> REFER -> native RTT proof.

## Required terminal facts

```text
initialSelectedRouteAttempted=true
initialSelectedRouteFailed=true
eligibleProviderUntouchedBeforeReselection=true
distinctRecoverySelectionRequired=true
recoverySelectedProviderUsed=true
recoveryReferAccepted=true
recoveryReplacementRttReady=true
recoveryOldLegReleasedAfterIndependentReadiness=true
```

The terminal verdict is:

```text
recovered-after-authorized-reselection
```

## Authority boundary

- **Tilden selection #1** owns the initial route choice.
- **Baudot signaling evidence** owns the observation that the selected route failed.
- **Baudot does not own recovery route choice.**
- **Tilden selection #2** owns authorization of the recovery provider.
- **TILDEN-HANDOFF-003 / BAUDOT-INTEROP-004** own the provider, REFER, replacement, readiness, and release observations after reselection.
- **Baudot's independent RFC 4103/T.140 reference** remains the only positive RTT semantic authority.

## Claim boundary

This is a controlled failed-route and authorized-reselection observation. It does not establish production provider failover, Tilden deployment, numbering authority, SIP/RTP/RFC 4103/T.140/PJSIP/VRS conformance, relay-service behavior, or production accessibility readiness.
