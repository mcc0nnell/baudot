# TRS Fund testkit

Baudot separates the **public Fund model** from the **synthetic financial lifecycle**.

```text
public FCC / Rolka Loube calibration
        |
        v
claim / assessment policy model
        |
        v
explicit synthetic business decision
        |
        v
runtime lifecycle contract
        |
        v
Apache Fineract ledger adapter
        |
        v
synthetic settlement / reconciliation
```

The public calibration fixtures and `interop/fineract/journal-contract-v1.json` own the canonical Fund arithmetic and accounting vocabulary.

`trs-fund-runtime-contract-v1.json` begins only after an upstream synthetic decision already exists. It does **not** define rates or its own chart of accounts. It exercises the lifecycle behavior that remains useful regardless of the particular approved amount:

- approved claim -> provider payable;
- settlement -> payable cleared against Fund cash;
- duplicate replay -> zero additional posting;
- downward adjustment -> explicit compensating entry; and
- erroneous posting -> explicit reversal while preserving the original transaction identity.

The runtime validator loads the canonical journal contract and fails if the runtime fixture attempts to redefine accounts or rate profiles.

## Five-year benchmark

`synthetic-trs-fund-five-year-v1.json` is a separate deterministic **benchmark workload**, not another policy or accounting authority.

It spans July 2022 through June 2027 with:

- 60 monthly cycles;
- three synthetic providers;
- five synthetic contributors;
- public reimbursement-rate and contribution-factor snapshots;
- synthetic monthly volume and revenue bases; and
- one deliberate state-transition disturbance per program year.

Its original reducer remains independent so it can detect arithmetic/state drift without simply reproducing the canonical validator. A second authority guard binds overlapping 2025-27 source facts back to the canonical public calibration, contributor-assessment fixture, and runtime contract.

```text
public source facts
      -> canonical Fund fixtures
      -> authority guard
                  |
independent five-year benchmark reducer
                  |
                  v
       expected 60-month state
```

The benchmark may carry public parameter snapshots as test inputs, but it may not define a chart of accounts, assign Fineract policy authority, or turn synthetic provider/contributor data into historical claims.

Run:

```bash
python scripts/validate_trs_fund_public_model.py
python scripts/validate_trs_fund_runtime_contract.py
python scripts/validate_synthetic_trs_fund_five_year.py
python scripts/validate_synthetic_trs_fund_five_year_authority.py
```

The static runtime contract pins Apache Fineract 1.15.0 as the next reference implementation profile, but neither the lifecycle contract nor the five-year benchmark claims that a live Fineract instance has executed the scenarios. Live execution is a separate evidence threshold.
