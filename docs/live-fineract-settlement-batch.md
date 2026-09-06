# Live Fineract settlement batch close

Status: stacked external-ledger qualification slice

This slice extends the single-event live Fineract proving lane into a deterministic synthetic settlement batch.

It does **not** move regulatory or administrator authority into Apache Fineract.

## Core invariant

```text
source evidence
!= regulatory reducer verdict
!= approved claim
!= payment authorization
!= Fineract mutation
!= persisted journal
!= settlement batch close
!= reconciliation
```

The batch fixture is explicitly **pre-reduced synthetic input**. The live adapter may enforce state transitions it has already been handed; it may not infer TRS eligibility, select a rate, approve a claim, or authorize payment.

## Synthetic batch

The first live batch contains four reserved `.example` providers:

| event | claim state | payment state | amount | live accounting consequence |
|---|---|---|---:|---|
| `claim-vrs-batch-001` | approved | authorized | $8,830.00 | accrue + disburse |
| `claim-vrs-batch-002` | approved | authorized | $4,415.50 | accrue + disburse |
| `claim-vrs-batch-003` | approved | held | $1,250.00 | accrue only |
| `claim-vrs-batch-004` | rejected | not-applicable | $777.77 | no Fineract business mutation |

Expected business movements:

```text
approved accruals             14,495.50
payment-authorized outflow    13,245.50
ending provider payable        1,250.00
rejected amount excluded         777.77
```

The `$1,250.00` residual is intentional evidence that:

```text
claim approved != payment authorized
```

## Live journal contract

The batch uses isolated CI-only GL codes mapped to Baudot's canonical semantic accounts:

```text
981100 -> canonical 1100 TRS Fund Cash
982100 -> canonical 2100 Provider Payable
985100 -> canonical 5100 Provider Compensation Expense
983900 -> synthetic opening equity only
```

Every approved claim accrual must read back as:

```text
Dr Provider Compensation Expense
Cr Provider Payable
```

Every payment-authorized disbursement must read back as:

```text
Dr Provider Payable
Cr TRS Fund Cash
```

A POST response alone is not evidence of a correct posting. Baudot reads each returned Fineract transaction ID back and verifies account code, debit/credit direction, and amount.

## Batch replay boundary

The first pass requires exactly five business mutations:

- three accrual journals;
- two disbursement journals.

The same batch is then replayed in the same adapter run. All five business mutation IDs must already be present and the replay must attempt **zero** additional Fineract HTTP mutations.

This proves only in-run adapter replay suppression. It explicitly does **not** claim durable cross-process or distributed idempotency.

## Independent reconciliation

Baudot reduces only the observed transaction readbacks from the five first-pass business mutations and requires:

```text
expense debits      == 14,495.50
payable credits     == 14,495.50
payable debits      == 13,245.50
cash credits        == 13,245.50
payable credit net  ==  1,250.00
```

The final reconciliation verdict is produced outside Fineract.

## Close control

After the batch reconciles, the harness creates a real Fineract GL closure for the synthetic office and attempts a deliberately late journal dated before the close.

The late mutation must be rejected with a Fineract client/domain-rule error. A successful late posting fails qualification.

## Evidence bundle

The lane preserves:

```text
target/evidence-external/LIVE-FINERACT-TRS-BATCH/v1/
  gl-accounts.json
  seed.json
  first-pass.json
  replay-pass.json
  reconciliation.json
  close.json
  post-close-rejection.json
  summary.json
  source-pin.json
  image-build.json
  image-git-properties.txt
  actuator-info.json
  bundle.manifest.sha256
```

The manifest is regenerated after platform provenance is copied into the bundle and is verified before artifact upload.

## Promotion criteria

A run qualifies only when all of these hold:

1. the Fineract source/runtime lineage inherited from the pinned 1.15.0 live lane remains intact;
2. three approved claims produce exactly three accrual journals;
3. only the two separately payment-authorized claims produce disbursement journals;
4. the rejected claim produces no business journal;
5. every journal is read back and independently checked;
6. replay attempts zero additional Fineract business mutations;
7. aggregate movement reconciles to `$14,495.50 / $13,245.50 / $1,250.00`;
8. every first-pass business mutation has a distinct Fineract transaction ID;
9. the real GL close is created;
10. a post-close late mutation is rejected; and
11. the sealed external evidence bundle verifies.

## Claim boundary

A green result does not establish FCC compliance, entitlement of a real provider, correctness of any actual TRS Fund administrator payment, durable distributed idempotency, bank settlement, production Fineract suitability, or financial-statement compliance.
