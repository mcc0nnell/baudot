# Celix payment authorization boundary

This slice extends Baudot's Celix authority graph from an accepted provider-payable journal into an explicit synthetic payment-authority decision and a separate provider-disbursement accounting intent.

It deliberately stops before any disbursement journal post, bank instruction, cash movement, settlement, or regulatory-compliance claim.

## Semantic source

The canonical accounting source is:

```text
interop/fineract/journal-contract-v1.json
```

The existing contract assigns distinct authority to two events:

```text
providerClaimApproved
  Dr 5100 TRS Provider Compensation Expense
  Cr 2100 Provider Payable

providerDisbursement
  Dr 2100 Provider Payable
  Cr 1100 TRS Fund Cash
  businessAuthority = baudot-synthetic-payment-authorization
```

The checked-in live Fund smoke fixture also gives claim accrual and disbursement separate event ids (`EVT-CLAIM-0001` and `EVT-DISBURSE-0001`). The Celix model preserves that distinction instead of reusing the provider-payable transaction id as the disbursement idempotency key.

## New service contracts

```text
IPaymentAuthorizationService 1.0.0
IProviderDisbursementIntentService 1.0.0
```

### Payment authorization

`IPaymentAuthorizationService` consumes:

- a canonical `ProviderPayableIntentDecision`;
- the corresponding posted `FineractJournalDecision`; and
- explicit synthetic payment-authority facts.

It rejects payment authority unless:

1. the provider-payable intent is ready;
2. the provider-payable journal is actually posted;
3. business-transaction lineage matches exactly;
4. posted ledger evidence carries a ledger transaction id;
5. an explicit payment decision is `approved`;
6. a stable payment authorization id is present; and
7. the authorized amount exactly matches the posted payable amount.

The service depends on the typed `posted` result, not adapter-specific verdict text. A future live adapter therefore does not gain or lose payment authority merely by changing a diagnostic verdict string.

A positive result is:

```text
PAYMENT_AUTHORIZED
```

That verdict authorizes only the next Baudot decision boundary. It does not post a disbursement journal or move cash.

### Provider-disbursement intent

`IProviderDisbursementIntentService` consumes a `PaymentAuthorizationDecision` and explicit accounting-intent facts.

It requires a new disbursement business transaction id and preserves three distinct lineage values:

```text
disbursementBusinessTransactionId
sourceProviderPayableBusinessTransactionId
paymentAuthorizationId
```

The disbursement id must be non-empty and distinct from the provider-payable transaction id.

It otherwise admits only:

```text
eventType = providerDisbursement
Dr 2100 Provider Payable
Cr 1100 TRS Fund Cash
amount = exact authorized payment amount
```

It also rejects replay and accounting-closure violations.

A positive result is:

```text
PROVIDER_DISBURSEMENT_INTENT_READY
```

That result is still only an intent. No execution adapter exists in this slice.

## Full authority graph

```text
PJSIP parse
  -> call admission
  -> actor authentication
  -> Ranger authorization
  -> TRS ordinary-call authority
  -> VRS compensability
  -> typed VRS rate result
  -> Fund claim authority
  -> provider-payable accounting intent
  -> synthetic Fineract provider-payable journal
  -> payment authorization
  -> providerDisbursement accounting intent
  -> Fund cash execution NOT MODELED
  -> settlement NOT MODELED
```

The core invariant is:

```text
parser accepted
!= call admitted
!= actor authenticated
!= policy authorized
!= ordinary call placement allowed
!= call completed
!= compensable
!= rate calculated
!= Fund claim approved
!= provider payable ready
!= provider-payable journal accepted
!= payment authorized
!= providerDisbursement intent ready
!= Fund cash moved
!= settlement reconciled
```

## Five deterministic controls

Every profile uses the same successful upstream evidence through:

```text
FineractJournalAdapter = FINERACT_JOURNAL_ACCEPTED_FIXTURE
```

Only payment/disbursement facts vary.

### 1. Payment authorized and disbursement intent ready

```text
PaymentAuthorization
  PAYMENT_AUTHORIZED
  authorizationId=payment-auth-celix-001
  authorizedAmountUsd=8830.00

ProviderDisbursementIntent
  PROVIDER_DISBURSEMENT_INTENT_READY
  businessTransactionId=disburse-vrs-celix-payment-001
  sourceProviderPayableBusinessTransactionId=claim-vrs-celix-payment-001
  paymentAuthorizationId=payment-auth-celix-001
  Dr 2100
  Cr 1100
  amountUsd=8830.00

FundCashBoundary
  NOT_MODELED
```

This is the first legitimate path to constructing the canonical `providerDisbursement` event shape.

### 2. Posted payable but payment remains pending

```text
FineractJournalAdapter
  FINERACT_JOURNAL_ACCEPTED_FIXTURE

PaymentAuthorization
  PAYMENT_AUTHORIZATION_PENDING

ProviderDisbursementIntent
  PROVIDER_DISBURSEMENT_INTENT_NOT_EVALUATED_PAYMENT_AUTHORIZATION_REQUIRED
```

This proves:

```text
Fineract ledger success != payment authorization
```

### 3. Payment amount mismatch

The posted payable is `$8,830.00`, but the injected payment approval is `$8,829.99`.

Required result:

```text
PAYMENT_AUTHORIZATION_REJECTED_AMOUNT_MISMATCH
```

Payment authority cannot rewrite accounting value.

### 4. Reversed disbursement mapping

Payment authorization succeeds, but the proposed accounting intent is reversed:

```text
Dr 1100
Cr 2100
```

Required result:

```text
PROVIDER_DISBURSEMENT_INTENT_REJECTED_JOURNAL_MAPPING
```

### 5. Duplicate disbursement replay

Payment authorization succeeds, but prior disbursement evidence for the same disbursement transaction id is present.

Required result:

```text
PROVIDER_DISBURSEMENT_INTENT_REJECTED_IDEMPOTENT_REPLAY
```

A previously authorized payment cannot be replayed into a second financial effect.

## Local qualification only

This branch intentionally does not add or modify GitHub Actions.

Use an existing local Apache Celix 2.4.0 installation and the pinned PJPROJECT checkout, then run:

```bash
export CELIX_PREFIX=/path/to/celix-install
export PJSIP_SOURCE_DIR=/path/to/pjproject
bash scripts/run_celix_payment_authorization_local.sh
```

The runner builds the Celix containers, executes the five payment profiles, captures evidence under `build/celix-payment-evidence`, and runs:

```text
scripts/validate_celix_payment_authorization.py
```

The validator requires upstream evidence through the posted provider-payable journal to remain identical across every profile and verifies the separate disbursement id, payable lineage, and payment-authorization lineage on the ready path.

## Claim boundary

A green local qualification establishes only the synthetic service composition described here. It does not establish:

- a live FCC/Fund administrator decision;
- a production payment authorization;
- a real Fineract disbursement journal;
- a bank or ACH instruction;
- Fund cash movement;
- settlement/reconciliation; or
- regulatory compliance.

## Next threshold

The next slice should add a separate disbursement execution adapter. It should consume only a ready `ProviderDisbursementIntentDecision`, preserve the canonical Dr 2100 / Cr 1100 contract and the distinct disbursement/payable/payment lineage, and still keep external bank/cash settlement as a separate authority boundary.
