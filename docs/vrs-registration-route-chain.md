# VRS registration and routing composition

Status: runnable candidate / clean-room composition

This slice composes Baudot's public RFC 9248-facing VRS/RUE contract with the synthetic Part 64 registration and TRS Numbering Directory model without promoting success at one layer into authority at another.

## Evidence chain

```text
synthetic registration record
  -> synthetic TND NANP-to-SIP URI mapping
  -> provider domain preserved
  -> deterministic RFC 3263-style NAPTR/SRV selection
  -> SIPS+D2T selected
  -> ephemeral loopback TLS handshake
  -> initial SIP REGISTER
  -> Digest challenge
  -> verified authenticated REGISTER
  -> registration accepted
  -> independent RFC 9248 provider selection
  -> existing one-stage dial-around INVITE
  -> selected Provider-B peer observes preserved target/source identity
  -> dialog established
```

Each arrow remains an independently observed or reduced fact.

## Core non-equivalence

```text
number assigned
!= TND route exists
!= provider domain resolved
!= service endpoint selected
!= TLS handshake succeeded
!= REGISTER sent
!= authentication challenged
!= authentication verified
!= registration accepted
!= dial-around provider selected
!= INVITE reached selected provider
!= dialog established
!= per-call validation
!= TRS business authority
!= media ready
!= RTT ready
!= video ready
!= compensable
!= Fund claim approved
```

The final reducer therefore records Part 64 per-call validation as `NOT_COMPOSED` and TRS business/Fund authority as `NOT_DERIVED` even when the synthetic registration and dial-around signaling legs succeed.

## Controlled discovery

`testkit/vrs/fixtures/rue-provider-dns-v1.json` is not a DNS capture. It is a deterministic, reserved-domain fixture used to exercise the ordering and evidence boundary of provider-domain service discovery. In the positive arm:

```text
provider-a.example
  NAPTR 10/10 SIPS+D2T -> _sips._tcp.provider-a.example.
  SRV   10/0  port 5161 -> sip-tls.provider-a.example.
  address                 -> 127.0.0.1
```

The reducer records:

```text
liveDnsQueried = false
liveTndQueried = false
```

A future live-authorized lane may replace the fixture with an external DNS observation, but no public test may silently promote historical `.1.itrs.us` behavior, production TND data, or a provider endpoint into normative authority.

## Challenged TLS registration

`RueRegistrationTlsProbe` creates an ephemeral self-signed certificate for `provider-a.example`, trusted only inside the loopback harness. It then exercises:

1. TLS handshake;
2. provider-domain presence in the certificate SAN;
3. initial `REGISTER`;
4. `401` Digest challenge;
5. independently verified Digest response;
6. accepted second `REGISTER`;
7. `Supported: outbound`; and
8. Contact `;ob` / `reg-id` / `+sip.instance` markers.

The authorization value is redacted before evidence persistence. The ephemeral PKCS#12 file is deleted before the runner exits.

Critically:

```text
Supported: outbound + Contact ;ob observed
!= RFC 5626 outbound flow proven
```

The result keeps `rfc5626.outbound.flow.proven=false` until an actual outbound-flow behavior test exists.

## Dial-around composition

After registration, the portable runner reuses the existing RFC 9248 provider-selection and JAIN SIP one-stage dial-around lane. Provider A remains the source/default-provider identity while Provider B is the explicit dial-around route.

Successful signaling still records:

```text
media.readiness.proven = false
rtt.readiness.proven   = false
video.readiness.proven = false
```

## Portable execution

No GitHub Actions workflow is introduced for this slice. Run the complete candidate locally or from WindAnvil/Jenkins/another external CI executor:

```bash
bash scripts/run-vrs-registration-route-chain.sh
```

The runner executes the public VRS and Part 64 validators, reduces synthetic discovery, creates and destroys the ephemeral TLS material, runs challenged registration, executes the existing Provider-B selection/dial-around lane, and independently reduces the complete evidence chain.

Final summary:

```text
target/evidence/VRS-REGISTRATION-ROUTE-CHAIN/summary.json
```

## Claim boundary

A green run establishes only that this controlled synthetic composition preserved the declared identities and evidence boundaries. It does not establish live TND or DNS behavior, provider interoperability, provider certification, SIP/RFC 3263/RFC 5626/RFC 9248 conformance, production TLS security, per-call eligibility validation, TRS business authority, emergency behavior, media readiness, compensability, reimbursement, or regulatory compliance.
