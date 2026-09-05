# VRS E2EE trust-boundary contract

Baudot models VRS privacy as a question with a testable answer:

> Who is capable of decrypting the current media epoch?

The answer is deliberately independent of whether SIP connected, RTP arrived, a frame decoded, or a UI rendered video.

## Roles

For the initial contract, the following roles are modeled.

| Role | May decrypt current media epoch? |
| --- | --- |
| caller | yes |
| callee | yes |
| active CA | yes |
| former CA | no |
| SFU | no |
| TURN/relay | no |
| Wiretap/network witness | no |
| SIP proxy | no |
| observability/evidence collector | no |

An implementation may have more than one active CA when the service model requires it. The policy is about the active authorized set, not a hard-coded number of interpreters.

## Canonical invariants

A baseline VRS E2EE trust-boundary fixture matches only when all of the following are true:

1. the caller can decrypt the current epoch;
2. the callee can decrypt the current epoch;
3. at least one active CA can decrypt the current epoch;
4. no former CA can decrypt the current epoch;
5. no infrastructure actor can decrypt the current epoch.

The executable Java fixture writes a timestamp-free artifact to:

```text
target/baudot-evidence/vrs-e2ee-trust-boundary.json
```

The artifact describes authorization state only. It does not claim that any cryptographic mechanism has been implemented.

## Proving-ground scenarios

The initial Omni proving-ground campaign should grow from this contract rather than from a product-specific encryption API.

| Scenario | Expected result |
| --- | --- |
| baseline authorized set | caller + callee + active CA decrypt; infrastructure cannot |
| infrastructure plaintext exposure | diagnostic failure: trust boundary violated |
| CA handoff | new active CA decrypts; former CA cannot decrypt future epoch |
| stale CA key | diagnostic failure: former CA retains current-epoch access |
| missing active-CA access | diagnostic failure: VRS relay cannot function |
| downgrade attempt | diagnostic failure unless policy explicitly authorizes the downgrade |
| reconnect/rekey | authorized set is re-established and evidenced before media is considered protected |

## Candidate media protection

[RFC 9605](https://www.rfc-editor.org/rfc/rfc9605.html) defines SFrame, an end-to-end media-encryption framing designed so an SFU can make forwarding decisions without access to the media content. That property is a strong architectural fit for the infrastructure side of this contract.

Baudot does not yet select a key-management system. The eventual implementation must separately prove participant authentication, active-CA authorization, epoch changes during CA handoff, key rotation, downgrade resistance, and recovery behavior.

## Evidence rule

`authorizedDecryptorSetMatched=true` means the observed authorization state matched the scenario's expected trust boundary.

It does **not** by itself mean `e2eeProven=true`.

Cryptographic E2EE becomes a supportable claim only when the implementation also proves that protected media was produced, unauthorized actors lacked usable content keys, authorized actors could authenticate/decrypt the protected media, and the relevant key lifecycle was exercised.
