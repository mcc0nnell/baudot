# Part 64 Internet-based TRS certification dossier

Status: implementation slice / synthetic certification evidence

This slice turns Baudot's executable Part 64 work into a synthetic 47 CFR § 64.606 Internet-based TRS certification dossier. It is intentionally **not** an FCC filing and cannot establish provider certification.

## Core invariant

```text
requirements mapped
!= documentary evidence present
!= application structurally complete
!= Commission review complete
!= FCC certification granted
!= Fund eligibility
```

The Commission decision remains an external authority boundary.

## Application evidence

`testkit/part64/fixtures/internet-trs-certification-dossier.json` models a VRS-only Internet-based TRS Certification Application with:

- form-of-service identification;
- an index to the executable non-waived Part 64 evidence maps already built in Baudot;
- synthetic call-center facility and technology/equipment evidence state;
- 10%-ownership/control and organizational-structure evidence state;
- TRS employee counts by required role without real employee names;
- employment-agreement retention state without storing agreements;
- sponsorship list/retention state;
- complaint procedures;
- annual-compliance-report commitment;
- qualifying senior-executive certification structure;
- consent to Commission on-site visits; and
- an at-home VRS compliance-plan state because the fixture requests at-home handling at initial certification.

The dossier explicitly sets:

```text
commissionDecision = not-determined
claimsActualFccCertification = false
```

A green validator therefore means only that the **synthetic evidence package is internally coherent**.

## Upstream evidence index

The certification dossier composes, rather than duplicates, these policy planes:

```text
§§ 64.611 / 613 / 615
registration → numbering → validation
        |
        v
§§ 64.630–636
provider-change authorization → verification → dispute
        |
        v
§ 64.604 call evidence
CDR → speed of answer
        |
        v
§ 64.604 compensability
call class → certification → audit/withhold → external decision
        |
        v
§ 64.604(d) aggregate controls
third-party / at-home / workforce / monthly reporting
        |
        v
§ 64.606 synthetic certification dossier
```

No downstream plane can retroactively promote an upstream observation.

## Annual compliance evidence

`testkit/part64/fixtures/vrs-annual-compliance.json` models the annual § 64.606(g) surface:

- updated certification information/documentation and summary;
- senior-executive annual certification;
- VRS § 64.604(c)(13) compliance plan identifying responsible management, training, employee reporting channels, internal audits, and waste/fraud/abuse controls; and
- synthetic at-home annual information when at-home VRS is authorized.

A submitted compliance plan is not presumed adequate. The fixture therefore keeps:

```text
commissionAdequacyDetermination = not-determined
```

## Deadline controls

Executable boundary arms cover:

```text
certification renewal
  90 days before expiration -> timely
  89 days before expiration -> late

substantive change notice
  day 60 -> timely
  day 61 -> late

Commission-directed compliance-plan correction
  day 60 -> within modeled maximum period
  day 61 -> late
```

A missing VRS annual compliance plan, and a failure to comply with a Commission plan-correction directive, are modeled as eliminating compensation entitlement during the period of noncompliance because § 64.606(g)(3)-(4) states that consequence directly.

## Clean-room boundary

No real provider application, ownership list, executive or employee identity, call-center deed/lease, technology contract, sponsorship agreement, employment agreement, annual report, Commission determination, or certification is present.

All organizational and facility facts are synthetic evidence-of-presence values only.

## What green means

A green certification-dossier workflow establishes only:

1. the required public-rule evidence classes are represented;
2. the existing Part 64 test planes are referenced rather than duplicated;
3. the key filing/deadline state machines behave deterministically; and
4. the synthetic package cannot self-promote into actual FCC certification.

It does not establish provider compliance, application sufficiency in a real proceeding, Commission approval, certification, or TRS Fund eligibility.

## Next boundary

§ 64.606(h) unauthorized service interruptions remains deliberately separate. It is an operational-continuity state machine with advance authorization, short/unforeseen outage notice, restoration notice, consumer-status updates, and possible enforcement consequences. It should not be hidden inside the certification dossier validator.
