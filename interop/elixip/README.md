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

## BAUDOT-INTEROP-004: JAIN SIP -> Elixip

The first cross-implementation direction has two controlled arms.

### Signaling-only negative arm

[`interop004-signaling-only-target.exs`](interop004-signaling-only-target.exs) answers the JAIN SIP replacement INVITE with `m=text` / `t140/1000`, independently records replacement ACK receipt inside Elixip, and deliberately emits no T.140 traffic.

Baudot passes the negative arm only when:

```text
REFER accepted
+ terminal NOTIFY observed and acknowledged
+ Elixip replacement dialog established
+ text/t140 negotiated
+ bounded no-packet observation completed
+ original leg preserved
```

That demonstrates across two SIP implementations that signaling success does not imply accessibility readiness.

### Positive handoff arm

[`interop004-positive-handoff-target.exs`](interop004-positive-handoff-target.exs) uses the same independent Elixip SIP/dialog boundary. After Elixip records replacement ACK receipt, the **Baudot-owned scenario** emits Baudot's deterministic canonical primary T.140 RTP datagram to the `m=text` port from JAIN's offer.

The packet is test stimulus executed from the external scenario process. It is intentionally **not** described as native Elixip RFC 4103 media.

The positive arm passes only when:

```text
REFER accepted
+ terminal NOTIFY observed and acknowledged
+ Elixip replacement dialog established
+ Elixip independently observed replacement ACK
+ text/t140 negotiated
+ canonical RTP bytes observed on JAIN's offered media port
+ Python RFC 4103 reference parses first T.140 text as "H"
+ original leg released after the RTT observation
```

Java preserves and byte-matches the live packet so the transfer policy can make a deterministic old-leg decision. It deliberately leaves `firstT140CharacterObserved` and `rttReady` unclassified. `scripts.validate_elixip_refer_positive_handoff` independently parses the preserved packet with `baudot_reference.rfc4103.PrimaryT140RtpPacket` and owns the terminal semantic verdict.

## BAUDOT-INTEROP-004: Elixip -> JAIN SIP

The reverse direction makes implementation ownership explicit rather than merely swapping labels. Elixip owns the original UAC/referrer dialog and emits the in-dialog REFER through its public FSL `send_REFER` surface. JAIN SIP receives the REFER and acts as the transfer processor, while a controlled provider-b peer supplies replacement-dialog evidence.

### Signaling-only negative arm

[`interop004-elixip-to-jain-signaling-only.exs`](interop004-elixip-to-jain-signaling-only.exs) establishes the original dialog from Elixip into JAIN SIP and sends:

```text
Refer-To: sip:provider-b@127.0.0.1:5283
```

JAIN SIP must preserve the original dialog unless replacement accessibility readiness is actually observed. The controlled provider-b answers the replacement INVITE with `m=text` / `t140/1000` and ACK is observed, but it deliberately emits no T.140 packet.

The reverse negative arm passes only when:

```text
Elixip original dialog established
+ Elixip REFER emitted and observed by JAIN
+ Refer-To target correlated
+ REFER accepted
+ terminal NOTIFY observed and acknowledged by Elixip
+ replacement dialog established
+ replacement ACK observed
+ text/t140 negotiated
+ bounded no-packet observation completed
+ JAIN records old-leg preservation
+ Elixip independently observes its original dialog remain up
```

Elixip's scenario result is still observation-only. `scripts.validate_elixip_to_jain_refer_signaling_only` independently reconciles Elixip markers with preserved raw SIP and JAIN evidence before emitting the terminal `rttReady=false` verdict.

## Claim boundary

A successful Elixip scenario process is never sufficient to pass `BAUDOT-INTEROP-004`. Wire evidence and Baudot's independent reducers retain verdict authority.

The current ensemble establishes controlled cross-implementation SIP/dialog behavior and accessibility-handoff policy. It does **not** establish SIP, REFER, RFC 3515, RFC 6665, RFC 4103, T.140, JAIN SIP, Elixip, VRS, SBC/NAT, or production conformance. The JAIN SIP -> Elixip positive arm specifically does not claim native Elixip RFC 4103 media support.

## Next slice

After the reverse signaling-only arm is stable, add the matching positive `Elixip -> JAIN SIP` handoff without changing the evidence vocabulary or terminal reducer semantics. The next independent-media threshold after that is a participant that actually emits RFC 4103/T.140 through its own media implementation rather than Baudot-owned canonical stimulus.
