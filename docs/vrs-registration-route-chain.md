# VRS registration, outbound flow, and routing evidence chain

Status: runnable-candidate / clean-room

This slice composes Baudot's public VRS/RUE interoperability contract with its synthetic Part 64 registration/TND contract and a bounded RFC 5626 outbound-flow proof.

## Chain

```text
synthetic registration
  -> TND NANP-to-SIP URI
  -> provider domain
  -> deterministic RFC 3263-style NAPTR/SRV selection
  -> SIPS+D2T selected
  -> ephemeral loopback TLS
  -> challenged SIP REGISTER
  -> verified authenticated REGISTER
  -> registration accepted
  -> outbound registration receives Require: outbound
  -> CRLF keepalive round trip
  -> controlled flow loss detected
  -> same AOR/+sip.instance/reg-id re-registers on replacement TLS flow
  -> inbound SIP request traverses replacement flow
  -> RFC 9248 provider selection
  -> Provider-B one-stage dial-around
  -> selected peer observes preserved routing identity
  -> dialog established
```

Every transition is preserved as an independent fact.

## Core invariant

```text
number assigned
!= TND route exists
!= provider service selected
!= TLS established
!= REGISTER sent
!= authentication verified
!= registration accepted
!= outbound flow established
!= flow replacement observed
!= dial-around provider selected
!= INVITE reached selected provider
!= dialog established
!= per-call validation
!= TRS business authority
!= media/RTT/video readiness
!= compensability
!= Fund claim authority
```

The first registration arm deliberately remains marker-level evidence. `Supported: outbound`, `reg-id`, `+sip.instance`, or `;ob` syntax alone cannot produce outbound-flow authority.

The separate outbound-flow lane requires `Require: outbound`, a CRLF keepalive/pong, detected TLS flow loss, replacement registration with the same binding key, and an inbound request/response across the replacement connection before its bounded reducer emits `rfc5626.outbound.flow.proven=true`.

That field is not an RFC 5626 conformance verdict. Recovery backoff timing, multiple outbound proxies, NAT/SBC behavior, public Path behavior, 430/439 handling, long-running keepalive timing, and production TLS remain unproven.

## Evidence boundaries

The composed reducer intentionally keeps these facts false or unclaimed:

```text
RFC 5626 conformance = NOT_CLAIMED
per-call validation = NOT_COMPOSED
TRS business authority = NOT_DERIVED
compensability = NOT_DERIVED
Fund claim authority = NOT_DERIVED
media readiness = false
RTT readiness = false
video readiness = false
```

No live TND, live DNS, production provider, real subscriber data, or emergency service endpoint is queried.

## Portable execution

```bash
bash scripts/run-vrs-registration-route-chain.sh
```

The runner is intended for local execution, WindAnvil, Jenkins, or another external CI plane. This stack adds no GitHub Actions workflow and removes the VRS Actions wrapper inherited from the earlier branch.

## Promotion rule

Keep the branch at `runnable-candidate` until the portable runner produces the declared evidence bundle in an independent execution environment. A green synthetic run establishes only this controlled composition, not production interoperability or standards conformance.
