# TRS Fund public / oversight publication boundary

Baudot's fourth consumer is deliberately not another authenticated application.

Public, oversight, and research consumers receive a one-way static projection built only from the repository's explicitly public aggregate Fund calibration data.

```text
public calibration source
        |
        | deterministic allowlist projection
        v
static JSON publication
        |
        +--> public
        +--> oversight
        +--> research
```

There is no route from this surface back into Fineract Consumer-Facing, a provider session, an Open Banking consent, or the Baudot operator control plane.

## Source

The first publication is derived from:

```text
testkit/fund/rolka-loube-2025-26.json
```

That fixture already declares:

```text
publicAggregatesOnly = true
```

and cites its public source material.

The publication builder refuses to operate unless that source boundary remains explicit.

## Published artifact

The checked-in projection is:

```text
site/public/data/trs-fund-public-2025-26.json
```

When the Baudot site is built, it is exposed as a static JSON resource under the site's `/data/` path.

The first projection contains only:

- program-year dates;
- public source citations;
- aggregate Fund revenue requirement, NDBEDP, administrative cost, projected Fund balance, and net requirement;
- aggregate analog and IP-based net requirements;
- aggregate contribution revenue bases and reported factors; and
- published service compensation rates for the program year.

It does not publish the synthetic live-ledger scenario, provider-specific state, Consumer identities, account identifiers, transaction identifiers, claim identifiers, consent identifiers, audit principals, sessions, tokens, or operator decisions.

## Allowlist, not redaction

The builder constructs a new projection from named source fields. It does not copy a large internal object and then try to redact it.

The contract also defines a second defensive layer:

```text
forbiddenFieldsAnywhere
forbiddenValueMarkers
```

The validator recursively rejects fields such as provider/client/user/account/transaction/journal/payment/claim/consent/session/token identifiers and rejects known synthetic identity/token markers if they appear anywhere in the serialized projection.

This is intentionally redundant. The allowlist defines what may be published; the denylist catches accidental expansion.

## Arithmetic integrity

Before publication, the builder requires:

```text
analog net Fund requirement
+ IP-based net Fund requirement
= published total net Fund requirement
```

For the current public calibration:

```text
$8,212,726
+ $1,525,148,289
= $1,533,361,015
```

If those source aggregates stop reconciling, the public projection does not silently regenerate.

## Authority boundary

The public JSON carries its own claim boundary:

```text
publicAggregatesOnly             = true
officialFccPublication           = false
productionFundStateClaimed       = false
providerLevelData                = false
providerEntitlementDerived       = false
consumerAuthenticationDerived    = false
machineConsentDerived            = false
operatorAuthorityDerived         = false
trsProgramAuthorityDerived       = false
claimAuthorityDerived            = false
paymentAuthorityDerived          = false
regulatoryComplianceClaimed      = false
```

The core invariants are:

```text
public visibility != provider entitlement
public visibility != machine consent
public visibility != Baudot operator authority
public visibility != TRS program authority
public visibility != claim approval
public visibility != payment authorization
published aggregate != Fineract ledger authority
```

## Relationship to all four consumers

```text
provider user
  -> Fineract Consumer-Facing provider surface
  -> provider-scoped financial visibility

third-party system
  -> Fineract Consumer-Facing Open Banking surface
  -> consent-scoped financial visibility

operator
  -> Baudot control plane
  -> cross-provider evidence, exceptions, reconciliation, program decisions

public / oversight / research
  -> static allowlisted aggregate projection
  -> no authenticated control-plane path
```

The surfaces may describe overlapping facts, but they do not share authority.

## Reproducibility

Run:

```bash
python scripts/build_trs_fund_public_projection.py --write
python scripts/build_trs_fund_public_projection.py
```

The first command regenerates the checked-in projection. The second validates that the checked-in file is byte-for-byte deterministic from the current source and contract.

CI runs the validation-only form so a stale or manually edited public payload fails the pull request.

## Next threshold

Use the public JSON as the data source for a dedicated ECharts oversight view. The visualization should remain a pure consumer of the public projection: no hidden provider endpoint, no Consumer BFF credential, and no operator-only data fallback.
