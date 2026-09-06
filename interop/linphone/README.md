# Linphone native RTT candidate lane

Baudot uses the Linphone SDK here as a **candidate second independent native RTT implementation**.

It is not yet an admitted oracle. See [ADR-0003](../../docs/adr/0003-linphone-native-rtt-candidate.md).

## Why this repository

Current Liblinphone development lives inside `BelledonneCommunications/linphone-sdk`; the older standalone `BelledonneCommunications/liblinphone` GitHub repository is no longer the live development tree.

The candidate profile is pinned to:

```text
repository: BelledonneCommunications/linphone-sdk
commit:     10f0cb98eb5ae7dae973d6666894561ce5eea561
role:       candidate second native RTT implementation
status:     source-admitted only
```

The pinned tree exposes a native RFC 4103/T.140 path through Liblinphone, Mediastreamer2, and oRTP. Baudot's admission gate verifies those surfaces before any implementation claim is allowed.

## Source-admission gate

With a clean checkout at the exact commit:

```bash
LINPHONE_SDK_ROOT=/path/to/linphone-sdk \
  python3 scripts/linphone_candidate_admission.py
```

The command writes a machine-readable record by default to:

```text
target/evidence-external/LINPHONE-CANDIDATE/source-admission/linphone-source-admission.json
```

The record includes:

- exact commit identity and clean-checkout status;
- observed origin URL;
- SHA-256 hashes for the Liblinphone public RTT APIs;
- SHA-256 hashes for the Mediastreamer2 RFC 4103 source/sink/stream implementation surfaces;
- the oRTP T.140 payload definition surface; and
- an explicit claim boundary with `oracleAdmitted=false`.

Passing this gate means **the source tree is worth executing**. It does not mean the implementation has passed Baudot.

## Candidate native-media experiment

The first live experiment intentionally mirrors the narrow PJSIP direct-T.140 profile:

```text
Baudot-owned driver
  -> public Liblinphone call API
  -> real-time text enabled
  -> controlled JAIN SIP UAS
  -> direct PT 98 t140/1000 negotiated
  -> public RTT character API emits "H"
  -> Linphone/Mediastreamer2 generates native wire traffic
  -> raw datagram evidence
  -> independent Python RFC 4103/T.140 reduction
  -> only the reducer may publish rttReady=true
```

The driver source in this directory is deliberately small and deterministic. It does not create RTP packets, does not call Mediastreamer2 RFC 4103 filters directly, and does not know Baudot's terminal verdict semantics.

## Build boundary

Linphone SDK's open-source distribution includes AGPLv3 licensing. Baudot therefore keeps this lane external and ephemeral:

- do not vendor the Linphone SDK into Baudot;
- do not commit a built Linphone SDK or linked qualification executable;
- do not upload the linked qualification executable as evidence;
- preserve source identity, build metadata, hashes, logs, SIP evidence, raw media evidence, and reducer output instead.

The candidate driver uses CMake's exported `LibLinphone` package once an external SDK build/install prefix is available:

```bash
cmake -S interop/linphone -B target/linphone-native-t140-app \
  -DCMAKE_PREFIX_PATH=/path/to/linphone/sdk/prefix
cmake --build target/linphone-native-t140-app --parallel
```

That build command is only the Baudot driver build. Building the external SDK itself remains outside the Baudot source tree and must be evidence-bound to the pinned commit.

## Admission threshold

ADR-0003 stays **Proposed** until one run demonstrates all of these facts separately:

```text
exact clean checkout
RTT-enabled offer
controlled direct-T.140 answer
confirmed dialog
native Linphone RTT path active
public API emits "H"
implementation-generated packet preserved
independent reducer sees first non-empty T.140 "H"
rttReady=true only in the terminal reducer
```

No successful SIP response, Linphone call state, or packet receipt can substitute for the independent semantic reduction.

## After the first pass

Once admitted, Linphone should be exercised as:

1. an incoming native RTT endpoint;
2. the replacement endpoint in `BAUDOT-INTEROP-004`;
3. one side of a PJSIP <-> Linphone native-media matrix; and
4. a separate RFC 2198/RED qualification target.

Only after those narrower implementation boundaries are stable should the lane be composed with proxy, media-relay, NAT, SBC, WebRTC, or production-representative gateway paths.
