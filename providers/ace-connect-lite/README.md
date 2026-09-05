# ACE Connect Lite provider fixture

This module describes the Baudot integration boundary for the historical MITRE/FCC ACE Connect Lite VRS interoperability implementation.

ACE Connect Lite is an **external implementation fixture**, not Baudot's semantic authority and not a model of every production VRS provider.

## Why it belongs here

The upstream implementation already exposes useful VRS interoperability surfaces:

- Asterisk-backed SIP call handling;
- SIP-over-WebSocket and video configuration;
- agent and queue state through Asterisk AMI; and
- an emulated VRS-number lookup seam at `/vrsverify/`.

That last seam is especially useful for Baudot. A deterministic iTRS adapter can front the legacy lookup behavior without teaching ACE Connect Lite about Baudot's internal model.

```text
Baudot scenario
     |
     v
provider-neutral fixture SPI
     |
     v
ACE Connect Lite profile
     |
     +--> deterministic iTRS adapter
     |         |
     |         `--> legacy /vrsverify/ contract
     |
     `--> Asterisk / SIP / media
```

## Two-provider proving ground

The intended first topology uses two isolated fixture identities backed by the same implementation:

```text
                  Baudot
                     |
              iTRS mock/adapter
                     |
          +----------+----------+
          |                     |
     provider-a              provider-b
   ACE Connect Lite        ACE Connect Lite
          |                     |
          +------ SIP/media ----+
```

`provider-a` and `provider-b` are synthetic Baudot fixture identities. They are not real VRS providers and must not be represented as production routing records.

## Evidence boundary

A passing ACE Connect Lite scenario may establish only the observations explicitly preserved by the scenario: lookup behavior, selected route, SIP state, negotiated media facts, packet/media observations, agent state, and terminal accessibility readiness.

It does not by itself establish VRS, SIP, SDP, RTP, RFC 4103, T.140, iTRS, security, accessibility, or production-provider conformance.

## Upstream

Source fixture: <https://github.com/mitrefccace/aceconnectlite-public>

Baudot should pin an exact upstream commit before executable fixture automation is promoted beyond exploratory use.
