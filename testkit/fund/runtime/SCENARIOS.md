# Scenario mapping

The reference runtime is intended to support the existing Fund invariants as executable scenarios:

| Invariant | Runtime exercise |
| --- | --- |
| `FUND-ACC-001` | compare reducer effects with balanced Fineract journal entries |
| `FUND-REC-001` | fold assessments and receipts to outstanding receivables |
| `FUND-CLM-001` | admit payable effects only from explicit claim-approval events |
| `FUND-DIS-001` | replay a payment transaction ID and verify `applied=false` with no duplicate effect |
| `FUND-ADJ-001` | preserve original transaction plus explicit reversal/adjustment event |
| `FUND-CLS-001` | reject ordinary events back-dated into a closed accounting period |
| `FUND-AUD-001` | rebuild all projected balances from the append-only event stream |
| `FUND-AUT-001` | keep policy authorization in Baudot and ledger acceptance in Fineract |

The next executable threshold is a five-program-year fixture that emits these events, posts their accounting projections to a pinned Fineract instance, and reconciles Fineract balances and transaction identifiers back to the independently folded Baudot state.
