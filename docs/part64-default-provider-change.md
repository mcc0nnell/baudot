# Part 64 default-provider change evidence map

Status: implementation slice

This document maps the next executable regulatory chain for synthetic iTRS default-provider changes under 47 CFR §§ 64.630–64.636. It is stacked on the registration/numbering/validation slice so provider-change evidence can consume a synthetic registered user and number without inventing a second registration authority.

## Core invariant

```text
change requested
!= user authorized
!= authorization verified
!= order valid
!= change implemented
!= number routed to new provider
!= minutes compensable
!= reimbursement payable
```

A dispute adds another independent chain:

```text
complaint received
!= change unauthorized
!= reimbursement withheld
!= Commission determination
!= Fund denial or clawback
```

## Regulatory map

| Rule | Synthetic requirement | Baudot evidence boundary |
| --- | --- | --- |
| § 64.630 | Change-of-default-provider rules apply to Fund-eligible VRS/IP Relay providers and covered NANP-numbered iTRS users. | Applicability is an input classification, not proof of provider certification or Fund eligibility. |
| § 64.631(a) | Obtain user authorization and verify it before initiating or implementing a default-provider change; retain verification records without alteration for at least five years. | Preserve authorization state, verification method, evidence digest, retention horizon, and mutation policy separately. |
| § 64.631(b) | When multiple TRS types are offered, authorization and verification are separate for each service. | One service's verified authorization cannot promote another service. |
| § 64.631(c) | Verification may use a conforming LOA or qualifying independent third-party verification. | Method-specific reducers prove only the verification transaction represented. |
| § 64.631(d) | Implement within 60 days after valid LOA or third-party verification; otherwise the order is void. | `implementedDay <= 60` is independent from route completion and service readiness. |
| § 64.631(e) | Original provider must not degrade service or VRS access-technology functionality while the change is pending. | Synthetic continuity observation is a separate non-degradation assertion. |
| § 64.631(f) | Qualifying provider-user-base transfers use advance notice rather than individual authorization, with at least 30 days' notice and required disclosures. | Offline notice fixture only; no real subscriber contact. |
| § 64.632 | LOA has prescribed form/content and is invalid if nonconforming. | Structural LOA validation; all subscriber identity values remain synthetic/redacted. |
| § 64.633 | Unauthorized-change complaints trigger notifications, identification of affected minutes, Fund withholding, and a 30-day proof-of-verification response window. | Complaint, hold, evidence response, and final determination remain separate states. |
| § 64.634 | If the Fund has not reimbursed and the change is found unauthorized, affected minutes are not reimbursable by either provider. | Synthetic Fund decision only; no production claim data. |
| § 64.635 | If reimbursement already occurred and the change is found unauthorized, the unauthorized provider remits 100% of affected payments. | Synthetic clawback calculation only. |
| § 64.636 | Default-provider freezes are prohibited. | A freeze request is a failing policy arm, never a supported feature flag. |

## Executable scenarios

- `ITRS-CHANGE-LOA-001` — valid synthetic LOA; change implemented inside 60 days.
- `ITRS-CHANGE-VOID-060` — otherwise valid order implemented after day 60; order is void.
- `ITRS-CHANGE-MULTI-001` — VRS authorization verified while IP Relay authorization is not; only VRS may proceed.
- `ITRS-CHANGE-TPV-001` — independent third-party verification using the same ASL format as the synthetic underlying transaction.
- `ITRS-CHANGE-CONTINUITY-001` — original provider service/functionality remains unchanged while the change is pending.
- `ITRS-TRANSFER-001` — synthetic provider-user-base transfer notice sent at least 30 days in advance with required disclosures.
- `ITRS-DISPUTE-PREPAY-001` — alleged unauthorized change before Fund reimbursement; affected minutes are held and a final unauthorized determination makes them non-reimbursable.
- `ITRS-DISPUTE-PAID-001` — alleged unauthorized change after Fund reimbursement; final unauthorized determination produces a 100% synthetic clawback.
- `ITRS-FREEZE-001` — attempted default-provider freeze is rejected.

## Clean-room boundary

No fixture may contain live TRS User Registration Database data, TRS Numbering Directory records, real subscriber identity information, real authorization recordings, provider credentials, production CDRs, complaint records, or Fund claim records.

Verification media are represented only by synthetic metadata and a deterministic evidence digest. The digest proves that the fixture is immutable inside the test model; it is not a substitute for production records and does not establish regulatory compliance.

## Promotion rule

A future implementation lane may consume this contract only if:

1. authorization, verification, implementation, routing, service continuity, and Fund decisions remain independently observed;
2. service-specific authorizations cannot leak across TRS types;
3. verification evidence is preserved without mutation for the modeled retention period;
4. a pending complaint cannot be silently converted into a final unauthorized-change determination;
5. Fund withholding, denial, and clawback are modeled as consequences of the relevant determination, not as provider-side guesses; and
6. no live user, complaint, URD, Numbering Directory, or Fund data enters the public corpus.
