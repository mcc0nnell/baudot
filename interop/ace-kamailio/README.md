# ACE Kamailio + rtpengine donor lane

This directory turns the public ACE Direct Kamailio/rtpengine deployment into a **scenario donor** for Baudot. It does not vendor Kamailio or rtpengine and it does not claim that the historical deployment is a normative architecture.

## Pinned donor

```text
repository: mitre-ace-direct/kamailio
commit:     3c56fc4112680a15cedd4ece835a9f371f079e0b
kamailio.cfg blob: 47f0af82f3c5a713e2bf7ae1e15023507e588e8d
README.md blob:    bcc9b691e941ad1760b350dfd6a1aca04ad1fc80
observed:   2026-09-05
```

The pinned configuration provides useful production-derived pressure at two separate boundaries:

```text
external signaling
      |
      v
Kamailio route selection
      |
      v
Asterisk/media-server destination

SDP-bearing dialog traffic
      |
      v
rtpengine media anchoring
      |
      v
relayed media path
```

The configuration distinguishes traffic already coming from its Asterisk/media-server cluster, dispatches external INVITEs toward media-server destinations, loads Kamailio's `rtpengine` module when NAT support is enabled, points it at `udp:127.0.0.1:12221`, and invokes `rtpengine_manage()` on selected SDP-bearing dialog paths. BYE handling also touches the relay lifecycle.

## Baudot extraction

The useful interoperability question is not whether Baudot can reproduce this exact proxy configuration. It is:

> Can accessible media traverse an independently operated signaling proxy and media relay while routing success, SDP rewriting, media observation, semantic T.140 reduction, and terminal accessibility readiness remain separately attributable?

That produces a future proving-ground shape:

```text
Tilden resolution
      |
      v
proxy route selected
      |
      v
SIP dialog established
      |
      v
media relay requested
      |
      v
SDP/media path rewritten or anchored
      |
      v
implementation-generated RFC 4103 traffic
      |
      v
Baudot independent T.140 reducer
      |
      v
rttReady=true only after semantic evidence
```

## Invariants

1. **Route selection is not media readiness.** Selecting an Asterisk/backend destination cannot promote `rttReady`.
2. **Relay control success is not media readiness.** A successful rtpengine control operation cannot promote `rttReady`.
3. **SDP rewriting is evidence, not a verdict.** Pre-relay and post-relay SDP belong in the evidence bundle, but neither proves T.140 delivery.
4. **Packet receipt is not semantic readiness.** Raw relayed media must still be independently reduced before a T.140 claim is made.
5. **Relay failure is explicit.** A missing or failed media relay cannot be silently converted into successful accessibility readiness.
6. **Teardown remains lifecycle evidence.** BYE/relay cleanup must not erase the ordering evidence needed to prove whether accessible media became usable before release.

## Offline donor model

`media-relay-vectors.json` and `validate_media_relay_donor.py` are intentionally small. They model only the invariant boundary above:

- INVITE/ACK + SDP can request relay management;
- no SDP does not create media readiness;
- BYE can request relay teardown;
- relay unavailability is a distinct failure;
- signaling and relay success remain insufficient for RTT readiness; and
- only an independent semantic reduction can publish readiness in the mock model.

Run:

```bash
python interop/ace-kamailio/validate_media_relay_donor.py
```

No sockets are opened and no external infrastructure is contacted.

## Next live threshold

A later live qualification should run an external Kamailio + rtpengine pair as an ephemeral substrate between already-qualified native endpoints. The minimum evidence bundle should preserve:

- exact external implementation versions/commits or package identities;
- clean/configured startup state;
- original SIP request/response and SDP;
- relay-rewritten SIP/SDP;
- rtpengine control observations without treating them as verdict authority;
- raw implementation-generated RFC 4103 datagrams on the relayed path;
- independent T.140 reduction;
- teardown ordering; and
- an outer manifest binding all evidence.

The first useful live matrix after Linphone qualification is:

```text
PJSIP -> Kamailio/rtpengine -> Linphone
Linphone -> Kamailio/rtpengine -> PJSIP
```

Passing that matrix would still be controlled interoperability evidence, not Kamailio, rtpengine, PJSIP, Linphone, RFC 4103, T.140, or VRS conformance.
