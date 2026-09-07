# Celix provider-payable accounting boundary

This slice extends Baudot's Celix authority graph from an approved synthetic Fund claim into a canonical provider-payable accounting intent and a synthetic Fineract execution adapter.

It preserves the authority split already present in:

- `interop/fineract/journal-contract-v1.json`;
- PR #137, the Part 64 Fund claim handoff; and
- PR #161, the Celix Fund claim authority boundary.

## Runtime chain

```text
PJSIP parse
  -> call admission
  -> authentication
  -> authorization
  -> TRS ordinary-call authority
  -> VRS compensability
  -> typed rate result
  -> Fund claim authority
  -> provider-payable accounting intent
  -> synthetic Fineract journal adapter
  -> payment authorization remains separate
```

## New service contracts

```text
IProviderPayableIntentService 1.0.0
IFineractJournalAdapter       1.0.0
```

### Provider-payable intent

The provider-payable service consumes an upstream `FundClaimDecision` plus accounting-intent facts:

```text
eventType
postingDate
amountUsd
expectedDebitAccount
expectedCreditAccount
priorPostingObservedForBusinessTransactionId
accountingPeriodOpen
authorizedOpenPostingDate
```

The first modeled event is exactly the canonical contract event:

```text
providerClaimApproved
  Dr 5100 TRS Provider Compensation Expense
  Cr 2100 Provider Payable
```

The service cannot approve a Fund claim, calculate compensation, authorize payment, or move Fund cash.

### Fineract journal adapter

The Fineract adapter accepts only a ready provider-payable intent. The positive fixture returns:

```text
FINERACT_JOURNAL_ACCEPTED_FIXTURE
```

This is synthetic execution evidence only. It does not establish a live Apache Fineract deployment, production ledger state, claim approval, payment authorization, cash movement, settlement, or regulatory compliance.

## Five executable profiles

### 1. Provider payable ready

The upstream Fund claim is approved for `$8,830.00`, the canonical accounting mapping is supplied, the business transaction id has not posted before, and the period is open.

Required result:

```text
ProviderPayableIntent  PROVIDER_PAYABLE_INTENT_READY
FineractJournalAdapter FINERACT_JOURNAL_ACCEPTED_FIXTURE
PaymentAuthorizationBoundary NOT_MODELED
FundCashBoundary             NOT_MODELED
```

The accepted journal creates only synthetic accounting-execution evidence.

### 2. Claim pending + hostile ledger-success observation

All upstream evidence through terminal compensability and the rate result is the same, but the synthetic Fund claim is still pending.

A hostile downstream observation is injected:

```text
RawFineractLedgerObservation FINERACT_LEDGER_ACCEPTED_FIXTURE
```

Required result:

```text
FundClaimAuthority    FUND_CLAIM_PENDING_DECISION
ProviderPayableIntent PROVIDER_PAYABLE_INTENT_NOT_EVALUATED_CLAIM_APPROVAL_REQUIRED
FineractJournalAdapter FINERACT_POST_NOT_ATTEMPTED_INTENT_REQUIRED
```

This mechanically proves:

```text
ledger success != claim approval
```

A downstream accounting token cannot repair missing upstream authority.

### 3. Reversed journal mapping

An approved claim is present, but the accounts are deliberately reversed:

```text
Dr 2100
Cr 5100
```

Required result:

```text
PROVIDER_PAYABLE_INTENT_REJECTED_JOURNAL_MAPPING
```

The adapter cannot silently rewrite the canonical journal contract.

### 4. Duplicate business transaction replay

The claim and mapping are valid, but the synthetic business transaction id is marked as already posted.

Required result:

```text
PROVIDER_PAYABLE_INTENT_REJECTED_IDEMPOTENT_REPLAY
```

The existing journal contract names the Baudot synthetic business transaction id as the adapter idempotency key.

### 5. Closed accounting period

The claim and mapping are valid, but the posting period is closed and no separately authorized open posting date is supplied.

Required result:

```text
PROVIDER_PAYABLE_INTENT_REJECTED_ACCOUNTING_CLOSURE
```

This preserves the journal-contract invariant that posting after closure must fail or use an authorized open date.

## Evidence non-interference

The validator requires these observations to remain identical across all five profiles:

```text
SignalingParser
CallAdmission
ActorAuthentication
Authorization
TrsBusinessAuthority
VrsCompensability
VrsRateResult
```

Only the explicit claim/accounting conditions may change downstream results.

The full authority ladder remains:

```text
parser accepted
!= call admitted
!= actor authenticated
!= policy authorized
!= ordinary call placement allowed
!= call completed
!= externally established compensable
!= rate calculated
!= Fund claim approved
!= provider-payable intent ready
!= Fineract journal accepted
!= payment authorized
!= Fund cash moved
!= settlement reconciled
```

## Payment boundary

The canonical disbursement journal is intentionally not modeled here:

```text
providerDisbursement
  Dr 2100 Provider Payable
  Cr 1100 TRS Fund Cash
```

That event belongs to a separate payment-authorization boundary. A provider payable may exist without a disbursement being authorized.

## Claim boundary

A green run establishes only a synthetic contract composition. It does not establish production provider eligibility, a real Fund administrator decision, actual compensable minutes, a live § 64.643 rate calculation, production Fineract journal entries, a real provider payable, payment authorization, bank instruction, Fund cash movement, settlement, or FCC compliance.

## Next threshold

Add payment authorization as its own Celix service. It must consume a posted provider-payable accounting result and an explicit payment-authority decision, then produce a separate `providerDisbursement` intent while proving that provider payable or Fineract ledger success alone can never move Fund cash.
