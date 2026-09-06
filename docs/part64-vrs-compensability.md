# Part 64 VRS compensability evidence map

Status: implementation slice

This document extends Baudot's synthetic Part 64 chain from call evidence into compensation decision evidence under 47 CFR § 64.604. It deliberately does **not** make Baudot, Apache Fineract, or any provider fixture the authority that establishes a real TRS Fund claim as compensable.

## Core invariant

```text
completed call
!= complete CDR
!= eligible provider
!= eligible call class
!= certified compensation request
!= compensable determination
!= payable claim
!= settlement
```

The key regulatory boundary is the burden-of-proof step: a provider may assemble and submit evidence, but a request is not established as compensable until the Fund administrator in consultation with the Commission, or the Commission, determines that the applicable burden has been met.

## Regulatory map

| Rule | Synthetic requirement | Baudot boundary |
| --- | --- | --- |
| § 64.604(c)(5)(iii)(E)(2) | Fund minutes derive from completed interstate or internet-based TRS calls after setup; integrated VRS uses paragraph (e). | Completion/timing evidence feeds the reducer but does not establish compensability. |
| § 64.604(c)(5)(iii)(E)(6) | A request is not payable until compensability is established by the administrator/Commission process. | `administratorDetermination` is an external-decision input. Baudot cannot synthesize it from CDR success. |
| § 64.604(c)(5)(iii)(F)(2) | Internet-based TRS providers receiving Fund payments are Commission-certified under § 64.606. | Provider certification status is a policy input, not a claim Baudot proves. |
| § 64.604(c)(5)(iii)(D)(5) | Each compensation request has a qualifying senior-executive certification. | Synthetic certification proves structural completeness only; no real executive identity/signature is stored. |
| § 64.604(c)(5)(iii)(D)(6) | Failure to submit to a requested audit or provide verification documentation automatically suspends payment until cured. | Audit state is independent of CDR and claim correctness. |
| § 64.604(c)(5)(iii)(L) | Withheld minutes remain unresolved until adequate justification and a compensability determination; inadequate/absent response may be permanently denied. | Hold, response, determination, and payment-release states remain separate. |
| § 64.604(c)(8)(v)-(vi) | VRS registration/use incentives are prohibited and noncompliance makes the service ineligible for Fund compensation. | Incentive evidence is a hard negative control; no monetary transaction is simulated. |
| § 64.604(c)(13) | Known false/unverified, unauthorized, induced, or unnecessary-use minutes may not be billed and known practices must be reported as soon as practicable. | Knowledge state drives `seekPaymentAllowed=false`; it does not fabricate an enforcement finding. |
| § 64.604(d)(4) | Provider-involved remote training/comparable calls are non-compensable. | Provider involvement is modeled explicitly rather than guessed from call destination. |
| § 64.604(d)(6) | International-IP-origin calls are non-compensable absent the preregistered U.S.-resident travel exception with specified period/region and accurate identity/location verification. | Every exception element is required independently; passing the international gate still does not establish the claim as compensable. |
| § 64.604(e)(2)-(4) | Integrated VRS is one compensation call; start requires identification of the registered requester within five minutes; end is the earliest specified termination event. | IVCS timing is reduced from timestamps independently and remains only one input to final compensability. |

## Executable scenarios

- `VRS-COMP-DOMESTIC-001` — complete domestic candidate plus explicit external `compensable` determination.
- `VRS-COMP-PENDING-001` — same evidence shape without a final determination; remains not payable.
- `VRS-COMP-INTERNATIONAL-DENY-001` — international origin with one missing preregistration element; denied at the call-class gate.
- `VRS-COMP-INTERNATIONAL-EXCEPTION-001` — all travel-exception elements present; remains pending until a compensability determination.
- `VRS-COMP-TRAINING-DENY-001` — provider-involved remote-training call; cannot be submitted as compensable minutes.
- `VRS-COMP-INCENTIVE-DENY-001` — prohibited incentive state makes the modeled VRS service ineligible for Fund compensation.
- `VRS-COMP-UNAUTHORIZED-USE-001` — known induced/unauthorized-use pattern prevents billing and creates a reporting obligation.
- `VRS-COMP-AUDIT-SUSPEND-001` — audit/documentation refusal automatically suspends payment until cure.
- `VRS-COMP-WITHHOLD-001` — claim withholding, timely provider justification, and later external compensability determination remain separate transitions.
- `VRS-IVCS-COMP-001` — timely requester identification and deterministic earliest-end-event accounting for one conference call.
- `VRS-IVCS-NO-USER-001` — requester not identified within five minutes; call is marked non-compensable.

## Executive certification

`testkit/part64/fixtures/vrs-compensation-certification.json` records only the structural facts needed for a clean-room test: an eligible executive role, first-hand-knowledge state, perjury certification state, report completeness/accuracy assertions, section 225/rules compliance assertion, and no-impermissible-incentive assertion.

It contains no real executive identity, signature, claim, or provider submission.

## Fund adapter boundary

A downstream synthetic accounting adapter may consume only a terminal decision object with an explicit external determination state. It must not infer eligibility from:

```text
CDR valid
OR user validated
OR provider route selected
OR executive certification present
```

The only safe handoff is conceptually:

```text
regulatory evidence
      |
      v
Baudot compensability reducer
      |
      +-- denied / suspended / pending --> no payable journal
      |
      `-- externally established compensable
                    |
                    v
          synthetic claim lifecycle
                    |
                    v
            Fineract journal adapter
```

Fineract remains an accounting execution surface. It is never the authority for § 64.604 eligibility, compensability, certification, audit, or enforcement decisions.

## Deferred monthly capacity controls

This slice deliberately leaves two percentage caps for a separate monthly-capacity reducer so call-level logic does not silently absorb aggregate policy:

- § 64.604(d)(1)(iii)(B) — third-party interpretation-service percentage cap;
- § 64.604(d)(7)(i) — at-home VRS percentage cap.

Those require month-level denominators and should be tested as aggregate evidence, not per-call flags.
