# Part 64 VRS call evidence and speed-of-answer map

Status: implementation slice

This document maps a focused § 64.604 evidence plane for synthetic VRS calls and TRS Fund claim support. It deliberately starts after registration, numbering, validation, and default-provider policy have already produced their own evidence. None of those upstream facts is allowed to substitute for call-record or compensation evidence.

## Core invariant

```text
call attempt
!= answered by CA
!= conversation started
!= completed TRS call
!= valid call record
!= speed-of-answer compliant month
!= compensable minutes
!= payable Fund claim
```

## Regulatory map

| Rule | Synthetic requirement | Baudot evidence boundary |
| --- | --- | --- |
| § 64.604(b)(2)(iii) | VRS providers answer at least 80% of VRS calls within 120 seconds, measured monthly; the interval runs from arrival at provider facilities to CA answer and abandoned calls are included. | Preserve arrival time, CA-answer time or abandonment, and monthly numerator/denominator independently. Queue/IVR entry is not a CA answer. |
| § 64.604(b)(4) | VRS remains available 24x7 and uses redundancy features. | Out of scope for this first call-record slice; represented as a later operational-availability requirement, not inferred from successful calls. |
| § 64.604(c)(5)(iii)(D)(2) | Each compensated TRS call carries required call-record fields including record ID, CA ID, session/conversation timestamps, endpoints, durations, handling location, and initiating URL. | Synthetic CDR field presence and timestamp/duration consistency only. |
| § 64.604(c)(5)(iii)(D)(3) | Internet-based relay providers submit speed-of-answer compliance data. | Monthly synthetic speed-of-answer report derived from call-attempt evidence. |
| § 64.604(c)(5)(iii)(D)(4) | Call-record and speed-of-answer data are captured by an automated recordkeeping system and submitted electronically in standardized form; conversation/session time is not manually altered during the call. | Fixture provenance and `humanInterventionDuringCallTiming=false` are explicit machine-verifiable facts. |
| § 64.604(c)(5)(iii)(D)(7) | Internet-based TRS providers retain submitted call data and supporting claim records electronically and retrievably for at least five years. | Retention horizon and retrieval format are evidence metadata, not proof of a production retention system. |
| § 64.604(c)(5)(iii)(D)(9) | Integrated-VRS call data identify the video conference; administrator instructions may substitute conference/requesting-user identifiers for ordinary endpoint fields. | Optional IVCS fixture uses synthetic conference identifiers and remains separate from ordinary VRS CDR semantics. |

## Executable scenarios

- `VRS-CDR-001` — ordinary synthetic VRS CDR with all required fields and internally consistent session/conversation durations.
- `VRS-SOA-PASS-001` — ten-call synthetic month where eight calls are answered by a CA within 120 seconds; abandoned calls remain in the denominator, producing exactly 80% compliance.
- `VRS-SOA-FAIL-001` — ten-call synthetic month with seven timely CA answers, producing 70% and a failing monthly result.
- `VRS-IVCS-CDR-001` — synthetic integrated-VRS conference record with conference/requesting-user identifiers and no claim that Teams, Zoom, or any named platform is compliant.

## Evidence rules

1. `providerArrival` starts the VRS speed-of-answer interval.
2. `caAnswer` ends it only when a CA actually answers; queue, hold, and IVR events do not count.
3. abandoned calls remain in the denominator.
4. prohibited/unvalidated calls that the rules say must not be completed belong to the validation lane and must not be silently injected into the speed-of-answer corpus.
5. conversation time must be contained within session time.
6. calculated durations must equal the preserved timestamps to the nearest second.
7. successful CDR validation never sets `compensable=true`; compensability remains a later policy reduction over call, validation, provider, and Fund evidence.

## Clean-room boundary

All call identities, numbers, IP addresses, URLs, CA IDs, call-center IDs, conference IDs, and timestamps are Baudot-authored synthetic values. No provider CDR, Fund claim, employee identifier, production URL, production IP address, subscriber identity, or interpreted conversation content may enter this corpus.

## Promotion rule

A live execution adapter may emit evidence into this contract only when capture occurs independently of the reducer and cannot rewrite conversation/session timing during the call. A future Fund adapter may consume the resulting evidence, but must keep these transitions distinct:

```text
call record complete
!= call eligible
!= minutes compensable
!= claim approved
!= payment settled
```
