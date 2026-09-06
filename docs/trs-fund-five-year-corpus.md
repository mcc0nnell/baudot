# Five-year synthetic TRS Fund corpus

This corpus extends Baudot's synthetic fund plane across five complete Interstate TRS Fund program years, from July 2022 through June 2027.

The purpose is not to reconstruct a production administrator system. It is to provide a deterministic, public-parameter-based economy that can be replayed against a Fineract-backed ledger and later joined to Baudot call/CDR evidence.

## Scope

```text
2022-23
2023-24
2024-25
2025-26
2026-27
   |
   v
60 monthly cycles
   |
   +--> 3 synthetic providers
   +--> 5 synthetic contributors
   +--> public reimbursement-rate snapshots
   +--> public contribution-factor snapshots
   +--> deterministic synthetic volume/revenue
   +--> adjustments / failures / recovery
   |
   v
expected five-year closing state
```

The committed source is `testkit/fund/synthetic-trs-fund-five-year-v1.json`. The validator materializes monthly provider volume from a fixed seasonal curve and annual contributor revenue from a fixed 3% synthetic growth rule. Every generated financial result is deterministic.

## Public parameter spine

The reimbursement-rate snapshots come from Rolka Loube's public TRS-provider rate history:

<https://rolkaloube.com/programs/federal-itrs/trs-providers>

The contribution-factor snapshots come from Rolka Loube's public TRS-contributor history:

<https://rolkaloube.com/programs/federal-itrs/trs-contributors>

The five-year corpus deliberately preserves real public rule changes instead of inventing random year-to-year variation.

| Program year | VRS emergent | IP CTS CA | IP CTS ASR | IP Relay | Contribution formula |
| --- | ---: | ---: | ---: | ---: | --- |
| 2022-23 | 5.29 | 1.30 | 1.30 | 1.9576 | legacy dual factor: 0.01125 / 0.00653 |
| 2023-24 | 7.77 | 1.30 | 1.30 | 2.048 | 514b 0.00025 / 514a 0.01615 |
| 2024-25 | 8.06 | 1.30 -> 1.35 | 1.30 -> 1.17 | 2.1252 | 514b 0.00024 / 514a 0.01952 |
| 2025-26 | 8.33 | 1.40 | 1.05 | 2.197 | 514b 0.00025 / 514a 0.02086 |
| 2026-27 | 8.61 | 1.45 | 0.95 | 2.271 | 514b 0.00021 / 514a 0.02276 |

For 2024-25, the IP CTS CA/ASR change takes effect November 1, 2024. For 2022-23, the corpus records the published legacy dual factors but intentionally does not invent a Form 499 line mapping that is not asserted by the public source used here.

## Synthetic actors

Three provider identities exercise distinct reimbursement paths:

```text
provider-vrs     -> low-volume / emergent VRS
provider-ipcts   -> mixed CA + ASR IP CTS
provider-iprelay -> IP Relay
```

Five contributor identities supply deterministic annual synthetic revenue bases. Their values are not historical carrier revenue and are not intended to approximate any named company.

```text
carrier-alpha
carrier-bravo
carrier-charlie
carrier-delta
carrier-echo
```

## Five deliberate disturbances

Each program year adds a different state-transition problem.

1. **2022-23:** one contributor invoice is collected one month late. The receivable must exist in October and clear in November.
2. **2023-24:** a VRS claim is replayed with the same identity. Financial effect must remain zero.
3. **2024-25:** the public November IP CTS rate transition is preserved and a December synthetic adjustment demonstrates amendment handling.
4. **2025-26:** an IP Relay provider payment fails in April and retries in May. The payable must remain open between those events and then clear.
5. **2026-27:** a synthetic VRS overpayment creates a recovery receivable in November and is recovered in January.

These are test pressures, not claims about actual historical TRS Fund incidents.

## Deterministic five-year result

The current corpus produces:

```text
synthetic contribution assessments  $63,047,666.10
synthetic approved reimbursements    $61,304,332.59
opening synthetic cash                $8,000,000.00
closing synthetic cash                $9,743,333.51
closing provider payable                     $0.00
closing contributor receivable               $0.00
closing recovery receivable                  $0.00
```

The cash result must independently satisfy:

```text
opening cash
+ contributor cash received
+ recoveries received
- provider cash paid
= closing cash
```

The five-year close is intentionally fully reconciled. Intermediate receivables and payables are required by the disturbance cases, but none may silently survive the end of the corpus.

## Fineract threshold

The JSON/validator pair is the canonical input-and-expected-output contract. It does not yet prove Fineract execution.

The next stronger lane should materialize the same 60 monthly cycles against an exact pinned Apache Fineract instance and preserve, for every generated financial transition:

- request identity and idempotency key;
- journal-entry request;
- Fineract transaction/journal identifier;
- read-back journal state;
- adjustment/reversal linkage;
- provider payable state;
- contributor/recovery receivable state;
- cash state; and
- a manifest binding the full five-year result to source and runtime identity.

A Fineract-backed run passes only if its externally read financial state reduces to the same expected year-end and five-year balances as this independent corpus validator.

## Authority boundary

```text
public rate/factor snapshot
!= real provider traffic
!= real contributor revenue
!= administrator internal validation
!= production chart of accounts
!= production payment authorization
!= Fineract conformance
```

Provider volumes, contributor revenue, opening cash, disturbances, and actor identities are all Baudot-owned synthetic fixtures. Public parameters are used as source facts only. The corpus does not reconstruct Rolka Loube's private schemas, APIs, fraud controls, accounting implementation, staff workflow, credentials, or payment infrastructure.
