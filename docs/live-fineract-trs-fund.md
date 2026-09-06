# Live pinned Fineract TRS Fund proving lane

Status: external implementation qualification slice

This lane promotes Baudot's synthetic TRS Fund accounting contract from fixture-only ledger observations to an actual Apache Fineract instance running in CI.

It does **not** promote Fineract into TRS policy authority.

## Core invariant

```text
synthetic business event authorized
!= Fineract request accepted
!= transaction persisted
!= journal readback matches
!= accounting control satisfied
!= Baudot reconciliation passes
```

A live HTTP success response is an observation, not a verdict.

## Exact platform pin

The qualification target is Apache Fineract 1.15.0:

```text
release tag:       1.15.0
release commit:    d5636847ac556c30b437254c353f05526d172b97
container source:  built locally from the verified release checkout
database family:   PostgreSQL
```

The CI lane checks out the Apache source at `1.15.0`, verifies that the checkout resolves to the pinned release commit, and builds the Fineract image from that exact source using the same `:fineract-provider:jibDockerBuild` task used by Apache's Docker CI.

The first two qualification attempts also established a useful negative fact: neither the release commit SHA nor `apache/fineract:1.15.0` was resolvable from Docker Hub at test time. Baudot therefore does **not** fall back to `latest`; it removes registry tag publication from the trust chain and builds the observed runtime from verified release source.

This prevents `latest`, a moving branch, or an unrelated image build from silently changing the evidence target.

## API correction discovered by qualification

Baudot's first static Fineract contract described reversal as:

```text
/api/v1/journalentries/{transactionId}/reversal
```

Fineract 1.15.0 actually exposes manual-journal reversal as:

```text
POST /api/v1/journalentries/{transactionId}?command=reverse
```

The canonical journal contract is corrected in this slice. The correction is source-bound to the pinned Fineract release; it does not change Baudot's business authority model.

## Synthetic chart of accounts

The live lane creates isolated detail accounts with unique test codes and maps them back to Baudot's canonical semantic accounts:

```text
canonical 1100  TRS Fund Cash
canonical 2100  Provider Payable
canonical 5100  TRS Provider Compensation Expense

live-only support account
Synthetic Opening Balance Equity
```

The live codes are intentionally distinct from any production chart and exist only inside the ephemeral CI database.

## Live transaction sequence

The first promoted path uses the same `$8,830.00` example already established by the Part 64 rate/claim/payment chain.

### 1. Seed synthetic cash

```text
Dr TRS Fund Cash                    50,000.00
Cr Synthetic Opening Balance Equity 50,000.00
```

This is test-state bootstrap, not a TRS Fund business event.

### 2. Approved provider claim accrual

```text
Dr TRS Provider Compensation Expense  8,830.00
Cr Provider Payable                    8,830.00
```

Baudot requires the returned Fineract transaction ID and independently reads the journal back by that ID.

### 3. Authorized provider disbursement

```text
Dr Provider Payable  8,830.00
Cr TRS Fund Cash     8,830.00
```

Again, the request response is insufficient. The external journal entries must be read back and reduced to the exact account IDs, debit/credit directions, and amount.

### 4. Duplicate suppression boundary

`syntheticBusinessTransactionId` remains a Baudot adapter idempotency key. Fineract is **not** asked to decide whether a repeated TRS business event is economically duplicate.

The live harness records the business ID before posting and refuses a replay before a second HTTP mutation can occur. It then verifies that Fineract contains only the one externally observed transaction for that business event.

### 5. Explicit reversal

The live harness invokes the pinned Fineract reversal command against the disbursement transaction and then reads the original transaction back to verify the externally exposed reversal state.

A reversal response alone is not sufficient evidence.

### 6. Accounting closure

The harness creates an actual Fineract GL closure for the synthetic office and then attempts a manual journal dated prior to that closure.

The closed-period mutation must fail. A successful backdated post is a qualification failure.

## Evidence bundle

A live run preserves only synthetic, non-secret evidence:

```text
target/evidence-external/LIVE-FINERACT-TRS/v1/
  source-pin.json
  image-build.json
  image-git-properties.txt
  actuator-info.json
  platform-pin.json
  gl-accounts.json
  seed-request.json
  seed-response.json
  seed-readback.json
  claim-request.json
  claim-response.json
  claim-readback.json
  disbursement-request.json
  disbursement-response.json
  disbursement-readback.json
  duplicate-control.json
  reversal-request.json
  reversal-response.json
  reversal-readback.json
  closure-request.json
  closure-response.json
  closed-period-request.json
  closed-period-response.json
  summary.json
  bundle.manifest.sha256
```

No Basic Auth header, password, database credential, container environment, or production information is written into the bundle.

## Promotion criteria

A run qualifies only when all of these independent facts hold:

1. source checkout is the pinned Fineract 1.15.0 release commit;
2. the runtime image is built from that exact verified checkout and contains generated `git.properties`;
3. the running actuator exposes Git build information;
4. synthetic GL accounts are created and read from Fineract;
5. claim accrual returns a transaction ID and readback exactly matches `Dr 5100 / Cr 2100` semantics;
6. disbursement returns a different transaction ID and readback exactly matches `Dr 2100 / Cr 1100` semantics;
7. the adapter rejects duplicate business-event replay before a second mutation;
8. the Fineract reversal command succeeds and external readback exposes the reversed transaction state;
9. a real Fineract accounting closure rejects a journal dated before the closure; and
10. Baudot's independent reducer produces the final `qualified=true` result.

## Claim boundary

A green live lane establishes only that the source-built, pinned Fineract 1.15.0 release behaved consistently with this narrow synthetic accounting contract in the observed CI run.

It does **not** establish:

- FCC provider eligibility or certification;
- compensability of a real TRS call;
- administrator claim approval or payment authorization;
- production Fineract suitability;
- financial-statement compliance;
- bank/payment-network behavior;
- Rolka Loube compatibility; or
- regulatory compliance of any real provider.
