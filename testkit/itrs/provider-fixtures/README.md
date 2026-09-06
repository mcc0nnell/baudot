# iTRS provider compatibility fixtures

These files bridge external historical implementations into the Baudot proving ground without making those implementations authoritative for iTRS semantics.

## ACE Connect Lite `/vrsverify/`

The public `mitrefccace/aceconnectlite-public` umbrella pins `mitrefccace/aceconnectlite` at commit `da74e6450193be1456ce2cdf65dd5ffdf0e92f1e`.

At that commit, `server.js` constructs:

```text
GET /vrsverify/?vrsnum=<number>
```

and consumes JSON in two observable ways:

- it compares `message` with `success` when deciding the outbound call context; and
- for incoming-call enrichment after a successful lookup, it compares the source number with `data[0].vrs`.

`AceConnectLiteVrsVerifyAdapter` therefore exposes a loopback-only compatibility facade with only that observed response shape:

```json
{"message":"success","data":[{"vrs":"2025550103"}]}
```

or:

```json
{"message":"failure","data":[]}
```

The adapter asks the Baudot CTE's existing compatibility query whether the synthetic TN has a routable VRS result. It deliberately does **not** copy `logicalSipUri` into the ACE response because the inspected ACE consumer does not demonstrate that it reads such a field.

This is a consumer compatibility adapter, not a reconstruction of the original VRS verifier service, iTRS provisioning/query APIs, iconectiv, Neustar, or any production provider implementation.

Run:

```bash
bash scripts/run-ace-vrsverify-adapter.sh
```

Expected result:

```text
ACE /vrsverify/ adapter probe: 3/3 PASS
```

The actual SIP route remains a separate Baudot/Tilden/iTRS evidence object. Future composition with PR #41 can point an ACE Connect Lite fixture's configured `vrscheck` host/port at this adapter while its provider session independently exercises the CTE directory model.
