# Part 64 VRS service interruption / continuity state machine

Status: implementation slice

This slice models 47 CFR § 64.606(h) as operational continuity evidence, not as a certification shortcut or an enforcement simulator.

## Core invariant

```text
interruption planned
!= prior authorization requested
!= Commission authorization granted
!= interruption authorized
!= notice complete
!= restoration complete
!= enforcement consequence determined
```

## Rule paths

### Voluntary interruption of 30 minutes or more

The modeled path requires:

1. a written Commission/CGB request at least 60 days before the interruption;
2. justification for the interruption;
3. a customer-notification plan;
4. a service-resumption/transition plan; and
5. an external CGB grant/deny decision at least 35 days before the proposed interruption.

The boundary fixture deliberately treats **30 minutes** as requiring prior authorization.

### Voluntary interruption under 30 minutes

No prior-authorization requirement is asserted by this paragraph. Instead, the provider must use the post-commencement notice path:

- written CGB notification within two business days;
- accessible consumer service-status notice; and
- timely status updates.

The boundary fixture uses **29 minutes** to keep this path distinct from the 30-minute rule.

### Unforeseen interruption beyond provider control

The same two-business-day initial notification path applies. If service has not been restored when that first report is filed, the fixture requires a second report within two business days after restoration with a restoration explanation.

## Executable scenarios

- `VRS-OUTAGE-PLANNED-030-PASS` — 30-minute planned outage; day-60 request; complete request package; explicit synthetic external authorization; decision 35 days before interruption.
- `VRS-OUTAGE-PLANNED-060DAY-FAIL` — 45-minute planned outage requested only 59 days before; not timely and no fabricated authorization.
- `VRS-OUTAGE-PLANNED-029-001` — 29-minute voluntary interruption follows the two-business-day post-notice path.
- `VRS-OUTAGE-UNFORESEEN-002DAY-PASS` — unforeseen outage; initial notice at two business days; service still down; second restoration report at two business days.
- `VRS-OUTAGE-UNFORESEEN-003DAY-FAIL` — initial notice at three business days.
- `VRS-OUTAGE-RESTORE-003DAY-FAIL` — timely initial notice but restoration report at three business days.
- `VRS-OUTAGE-WEBSITE-NOTICE-FAIL` — timely written notice but missing accessible/timely consumer status notice.

## Enforcement authority boundary

§ 64.606(h)(4) states that failures may lead to certification revocation, TRS Fund payment suspension, or other Commission enforcement action as appropriate. The rule does not authorize Baudot to select that outcome.

Every failure arm therefore preserves:

```text
possibleEnforcementExposure = true
actualEnforcementOutcome = not-determined
```

This is the same evidence discipline used throughout Baudot:

```text
rule violation evidence
!= agency finding
!= sanction
```

## Clean-room boundary

All outage durations, requests, decisions, notices, and restoration events are synthetic. No production outage log, customer notification, FCC/CGB filing, provider incident, actual authorization, or enforcement action is represented.

## Composition

This lane can feed the § 64.606 annual/certification evidence plane as an operational-continuity observation, but it must remain independently reduced:

```text
service interruption evidence
        |
        v
§ 64.606(h) continuity reducer
        |
        +-- conforming
        `-- deficient / possible enforcement exposure
                 |
                 v
        certification/compliance evidence
```

A deficient interruption record does not let Baudot revoke certification or suspend a real Fund payment. Those remain Commission authorities.
