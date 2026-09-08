# Controlled VRS/RUE outbound-flow recovery evidence

Status: runnable-candidate / clean-room

This slice advances the existing `RUE-REG-001` registration lane from marker observation into one bounded RFC 5626 behavior chain. It remains entirely synthetic and loopback-only.

## Source boundary

RFC 9248 requires SIP registration with SIP outbound behavior. RFC 5626 is the direct behavioral source for the mechanics exercised here.

The critical distinction is:

```text
Supported: outbound
+ +sip.instance
+ reg-id
!= outbound flow established
```

For a successful outbound registration, the controlled registrar returns `Require: outbound`. Only then does this lane attempt flow behavior.

## Evidence chain

```text
TLS flow 1 established
  -> REGISTER carries Supported: outbound + +sip.instance + reg-id
  -> Digest challenge verified
  -> 200 carries Require: outbound + Flow-Timer
  -> CRLF keepalive ping observed
  -> CRLF pong observed
  -> flow 1 deliberately closed by harness
  -> client detects TLS EOF
  -> TLS flow 2 established
  -> same AOR/+sip.instance/reg-id re-registers
  -> registrar recognizes the same binding key on a new network flow
  -> provider-originated OPTIONS traverses flow 2
  -> RUE returns correlated 200 over flow 2
```

Only after all of those observations may the bounded reducer emit:

```text
rfc5626.outbound.flow.proven=true
```

That field means only that this controlled flow establishment/replacement behavior was observed. It is **not** a claim of RFC 5626 conformance.

## Deliberately unproven

This accelerated harness does not exercise RFC 5626 recovery backoff timing, multiple outbound-proxy-set members, NAT/SBC traversal, production Path behavior, 430/439 handling, long-running keepalive timing, public-PKI TLS, or provider failover policy.

In particular, the harness closes the first loopback flow and forms the replacement immediately so the evidence lane remains deterministic and fast. RFC 5626 defines recovery backoff after failed-flow attempts; that timing is deliberately outside this slice. Therefore:

```text
outbound flow behavior observed
!= RFC 5626 recovery-timer conformance
!= full RFC 5626 conformance
```

## Accessibility and business boundaries

Flow recovery is still below the accessibility and TRS authority planes:

```text
outbound flow recovered
!= INVITE routed correctly
!= dialog established
!= media received
!= RTT ready
!= video ready
!= per-call eligibility validated
!= compensable event
!= Fund claim authority
```

The composed runner joins this proof to the existing registration/TND/dial-around chain only through independent reducers.

## Portable execution

Standalone:

```bash
bash scripts/run-rue-outbound-flow.sh
```

Composed:

```bash
bash scripts/run-vrs-registration-route-chain.sh
```

No GitHub Actions workflow is added by this slice. The runner is intended for local execution, WindAnvil, Jenkins, or another external CI plane.
