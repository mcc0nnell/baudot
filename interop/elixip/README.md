# Elixip external oracle lane

Baudot uses Elixip as an **externally installed independent implementation oracle** under [ADR-0001](../../docs/adr/0001-interoperability-ensemble-and-external-oracles.md).

Elixip is not vendored, linked, added as a Maven dependency, or treated as a source of Baudot verdict semantics. The boundary is process/network/scenario level.

## Pinned upstream identity

The initial oracle profile admits only:

```text
repository: neutrino38/elixip
commit:     d5f942768213200576031346099a896fb61bef4f
release:    1.5.1 observation recorded by ADR-0001
```

The checkout must be clean. A fork, a different commit, or an uncommitted modification fails admission before the scenario runs.

## Admission smoke

With a clean external checkout:

```bash
ELIXIP_ROOT=/path/to/elixip \
  bash scripts/run-elixip-oracle-scenario.sh
```

The default scenario, [`admission-smoke.exs`](admission-smoke.exs), contains no SIP traffic. It proves only that:

1. Baudot admitted the expected independent implementation identity;
2. the exact Baudot-owned FSL scenario bytes were SHA-256 bound before execution;
3. an optional external configuration is hash-bound without copying its contents into the admission record;
4. Elixip loaded and executed the Baudot-owned scenario through its public `mix scenario` boundary; and
5. the process outcome is preserved as an **observation**, not a terminal accessibility verdict.

The evidence directory contains:

```text
admission.json
scenario.exs
elixip.stdout.log
elixip.stderr.log
result.json
manifest.sha256
```

## Next execution slice

The next scenario pack will execute `BAUDOT-INTEROP-004` in both directions:

```text
JAIN SIP -> Elixip
Elixip -> JAIN SIP
```

The existing Baudot reducer semantics do not change. REFER acceptance, NOTIFY progression, replacement-dialog correlation, RTT negotiation, first independently validated T.140 character, old-leg teardown ordering, and terminal readiness remain separate facts.

A successful Elixip scenario process is not sufficient to pass `BAUDOT-INTEROP-004`. Wire/network evidence and Baudot's independent reducers retain verdict authority.
