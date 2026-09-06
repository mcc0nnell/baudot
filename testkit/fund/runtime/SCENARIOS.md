# Scenario mapping

The reference runtime maps the existing Fund invariants into executable scenario behavior:

| Invariant | Runtime exercise |
| --- | --- |
| `FUND-ACC-001` | compare reducer effects with balanced Fineract journal entries |
| `FUND-REC-001` | fold assessments and receipts to outstanding receivables |
| `FUND-CLM-001` | admit payable effects only from explicit claim-approval events |
| `FUND-DIS-001` | replay a business transaction ID and verify `applied=false` with no duplicate effect |
| `FUND-ADJ-001` | preserve original transaction plus explicit reversal/adjustment event |
| `FUND-CLS-001` | reject events back-dated into a closed accounting period and require an authorized open date |
| `FUND-AUD-001` | rebuild all projected balances from the append-only event stream; fail closed on sequence gaps or duplicate persisted IDs |
| `FUND-AUT-001` | keep policy authorization in Baudot and ledger acceptance in Fineract |

## Five-year baseline

`five-year-synthetic.json` is the first replayable long-horizon fixture. It carries 35 ordered events across five synthetic program years and exercises:

1. ordinary contributor assessment/receipt and provider claim/payment flows;
2. a contributor-base/demand change in year two;
3. a year-three delinquency plus an anomalous provider claim corrected by explicit downward adjustment;
4. a year-four revised contributor assessment;
5. a year-five recovery plus a retroactive prior-year provider adjustment posted in an open period; and
6. annual accounting closure and program-policy transition events.

The fixture declares a terminal expected projection and the test suite independently folds the full log to verify it. Its entity-level amounts are synthetic and make no production Rolka Loube, provider, contributor, or payment-network compatibility claim.

The next threshold is to post the same event-derived accounting effects to a pinned external Fineract instance and reconcile returned transaction IDs, journal entries, balances, reversals, and closure behavior against the independently folded Baudot state.
