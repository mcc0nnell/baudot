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

Run:

```bash
python scripts/validate_trs_fund_public_model.py
python scripts/validate_trs_fund_runtime_contract.py
```

The static runtime contract pins Apache Fineract 1.15.0 as the next reference implementation profile, but it does not claim that a live Fineract instance has executed the scenarios. Live execution is a separate evidence threshold.
