# Part 64 synthetic regulatory fixtures

This directory contains only Baudot-authored synthetic material for executable Part 64 test design.

No live TRS User Registration Database data, TRS Numbering Directory records, subscriber identity information, provider credentials, production call records, or real emergency-call traffic may be committed here.

The current slice covers:

- `ITRS-REG-001` — synthetic default-provider registration evidence;
- `ITRS-NUM-001` — reserved NANP-to-URI directory mapping;
- `ITRS-VAL-001` — successful pre-call validation;
- `ITRS-VAL-002` — routable but unvalidated negative control;
- `ITRS-VAL-911` — offline emergency validation exception;
- `ITRS-VAL-PORT-PENDING` — provisional porting-in state while identity verification is pending.

Run:

```bash
python scripts/validate_part64_registration_numbering.py
```

A passing validator means only that the synthetic fixtures preserve the declared evidence boundaries. It is not a claim of FCC certification, provider compliance, live database behavior, call completion, media readiness, compensability, or reimbursement eligibility.
