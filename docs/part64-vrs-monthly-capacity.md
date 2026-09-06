# Part 64 VRS monthly capacity and workforce controls

Status: implementation slice

This document keeps aggregate VRS capacity controls separate from per-call compensability. The rules in 47 CFR § 64.604(d) use month-level denominators, provider authorization state, and annual workstation oversight; those facts cannot be reduced correctly from a single CDR.

## Core invariant

```text
individual call eligible
!= monthly capacity available
!= at-home program authorized
!= aggregate cap satisfied
!= workforce compensation permitted
!= monthly report complete
!= payable claim
```

## Regulatory map

| Rule | Synthetic requirement | Baudot evidence boundary |
| --- | --- | --- |
| § 64.604(d)(1)(iii)(B) | Third-party interpretation-service minutes may be compensated only up to the greater of 30% of total compensated monthly minutes or 30% of average projected monthly conversation minutes. | Reducer calculates both branches from preserved aggregate inputs and selects the greater value. |
| § 64.604(d)(1)(iv) | VRS minutes used by an authorized third party for marketing or outreach are not compensable on a per-minute basis. | Marketing purpose is a hard zero-minute payable-journal gate; it is not blended into the 30% interpretation cap. |
| § 64.604(d)(3) | CA/interpretation-contractor compensation, scheduling preferences, or benefits may not be based on VRS minutes or calls relayed. | Volume-based benefit basis is rejected as a workforce-policy arm; Baudot does not invent an enforcement penalty beyond the rule. |
| § 64.604(d)(7)(i) | For Commission-authorized at-home VRS, home-workstation minutes may be compensated up to the greater of 80% of total compensated monthly minutes or 80% of average projected monthly conversation minutes. | Commission authorization is a prerequisite input; passing the percentage alone cannot authorize home handling. |
| § 64.604(d)(7)(iv)(D)-(E) | Home-workstation records are retained at least five years and at least 5% of workstations receive random unannounced inspections in each 12-month period. | Retention and inspection coverage are separate aggregate evidence facts. Conversation content is excluded. |
| § 64.604(d)(7)(vi) | Monthly compensation requests include workstation ID/address, CA IDs, and supervising call-center ID/address/supervisor information for each home workstation. | Public fixture proves field shape only with synthetic addresses and identities. |

## Boundary tests

The current fixtures intentionally use exact one-minute-over controls:

```text
third-party interpretation
  total compensated      = 10,000
  projected monthly      = 12,000
  30% branches           = 3,000 / 3,600
  cap                    = 3,600
  3,500                  = PASS
  3,601                  = FAIL

at-home VRS
  total compensated      = 10,000
  projected monthly      = 12,000
  80% branches           = 8,000 / 9,600
  cap                    = 9,600
  9,500                  = PASS
  9,601                  = FAIL
```

These tests protect two important implementation details:

1. use the **greater** of the two rule-defined values; and
2. do not round or silently substitute a different denominator.

## Additional negative controls

- `VRS-MONTHLY-ATHOME-UNAUTHORIZED-001` — one home-workstation minute with no Commission authorization cannot pass merely because it is below 80%.
- `VRS-MARKETING-NONCOMP-001` — third-party marketing/outreach VRS minutes produce zero minutes eligible for a payable journal.
- `VRS-CA-MINUTE-INCENTIVE-001` — CA compensation tied to conversation minutes is rejected.
- `VRS-HOME-OVERSIGHT-001` — forty synthetic home workstations require at least two random unannounced inspections in the 12-month control and five-year non-content record retention.

## Monthly home-workstation report

`testkit/part64/fixtures/vrs-home-workstation-monthly-report.json` is a structural public fixture only. It includes synthetic:

- workstation IDs and full street-address-shaped values;
- CA IDs;
- supervising call-center ID and address; and
- supervisor name.

No production CA, home address, call-center record, supervisor identity, or monthly compensation filing is stored.

## Accounting boundary

Aggregate cap success is still not a Fund payment verdict:

```text
call-level compensability
      +
monthly capacity controls
      +
required monthly reporting
      |
      v
eligible evidence bundle
      |
      v
external Fund determination / payment process
      |
      v
synthetic accounting adapter
```

A Fineract journal must never be created from raw third-party or at-home minutes before the aggregate reducer has produced an allowed-minute result and the upstream compensability layer has produced the required external decision state.
