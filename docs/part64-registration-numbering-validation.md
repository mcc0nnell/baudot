# Part 64 registration, numbering, and validation evidence map

Status: implementation slice

This document maps the first executable regulatory chain for synthetic VRS registration, numbering-directory routing, and pre-call validation. It is intentionally clean-room: no live TRS Numbering Directory records, no real subscriber identity data, no provider credentials, and no production call detail records are permitted in the public test corpus.

## Core invariant

```text
number assigned
!= directory route exists
!= user registered
!= identity verified
!= call validated
!= call connected
!= compensable event
!= reimbursable claim
```

Each transition requires independent evidence. A downstream fact must never be inferred solely from an upstream success.

## Regulatory chain

| Rule | Synthetic requirement | Baudot evidence |
| --- | --- | --- |
| 47 CFR § 64.611 | Register a VRS user/default provider, assign or port a NANP number, preserve eligibility/identity-verification state, and maintain Registered Location state where applicable. | Synthetic registration record, provider selection, reserved NANP number, identity-verification state, and location token. |
| 47 CFR § 64.613 | Resolve a registered NANP number through a numbering-directory mapping to a URI/routing target. | Synthetic directory lookup preserving query, match, URI, route owner, and lookup result independently. |
| 47 CFR § 64.615 | Validate user eligibility during call setup before ordinary call placement; preserve validation failure separately from routing and connection. | Pre-call validation transaction and reducer result. Emergency behavior remains offline/synthetic-only. |

## Authority boundary

The machine-readable companion is `testkit/part64/requirements-v1.json`.

It records regulatory requirements as test-design authority. It does not claim FCC certification, provider compliance, access to production FCC systems, or correctness of any non-public implementation.

## Synthetic states

### Registration

`ITRS-REG-001` proves only that a synthetic user record is accepted by the local fixture with:

- a synthetic default-provider identifier;
- a reserved NANP number;
- an explicit identity-verification state;
- an explicit eligibility state;
- a synthetic Registered Location token.

It does not prove live registration, NANP assignment authority, provider enrollment, or TRS Fund eligibility.

### Numbering

`ITRS-NUM-001` proves only that the synthetic numbering directory maps a reserved NANP number to the expected synthetic URI and route owner.

A successful lookup does not prove user validation, provider authorization, SIP dialog establishment, media readiness, or compensability.

### Validation

`ITRS-VAL-001` is a positive pre-call validation arm. `ITRS-VAL-002` is a negative arm in which routing data exists but validation fails. This intentionally establishes:

```text
routable != validated
```

`ITRS-VAL-911` is an offline-only emergency-policy fixture. It must never originate a real emergency call and must never be used to probe public safety infrastructure.

## Promotion rule

A future live/provider lane may consume these contracts only if:

1. public regulatory authority remains pinned separately from implementation behavior;
2. subscriber and numbering data remain synthetic or expressly authorized;
3. routing, validation, connection, modality readiness, compensability, and reimbursement remain separate reducer facts;
4. emergency behavior is exercised only in an isolated authorized environment; and
5. no provider-specific implementation result is promoted into a normative Part 64 rule.
