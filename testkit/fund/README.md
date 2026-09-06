# Synthetic TRS fund plane

This directory defines deterministic accounting fixtures for the Baudot TRS proving ground.

The fund plane begins **after** a synthetic fund-administrator fixture has produced an explicit claim decision. It does not decide compensability, rates, provider eligibility, or payment authorization.

```text
Baudot call evidence
      -> synthetic CDR
      -> fund-admin fixture
      -> approved / adjusted / reversed claim
      -> Fineract ledger adapter
      -> synthetic payment fixture
      -> reconciliation
```

`trs-fund-contract-v1.json` freezes the first accounting profile and scenarios. `scripts/validate_trs_fund_contract.py` independently checks that:

- every financial posting balances;
- Fineract is never assigned eligibility/rate authority;
- all committed rates are explicitly synthetic;
- duplicate claim replay has zero additional financial effect;
- settlement clears the provider payable against fund cash;
- adjustments preserve balanced equal-and-opposite effects; and
- reversals retain the original transaction identity instead of deleting history.

The initial Fineract role is a **reference ledger implementation**, not a production dependency and not a TRS Fund policy engine.

Run:

```bash
python scripts/validate_trs_fund_contract.py
```

See [`docs/trs-fund-fineract-proving-ground.md`](../../docs/trs-fund-fineract-proving-ground.md) for the architecture, evidence contract, and first live Fineract threshold.