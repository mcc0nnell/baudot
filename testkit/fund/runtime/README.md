# Synthetic Fund event runtime

This package adapts the event-sourced control-plane pattern proven in SF26's College Bowl runtime to Baudot's synthetic TRS Fund test bench.

The runtime is deliberately infrastructure-neutral: append-only business events are the source of truth, current Fund state is derived by a deterministic fold, and external accounting systems such as Apache Fineract remain implementation targets rather than policy authorities.

Core rules:

- every command carries a unique business transaction / idempotency key;
- duplicate delivery is a no-op;
- original events are immutable;
- corrections are explicit reversal or adjustment events;
- policy and fixture identity are hash-bound to a run;
- the reducer is pure and replayable;
- accounting acceptance never implies program authorization;
- projections may be rebuilt entirely from the event log.

`fund_runtime.py` contains the reference event vocabulary, validation, append semantics, and reducer. `test_fund_runtime.py` exercises replay, duplicate suppression, reversals, adjustments, policy binding, and period closure.
