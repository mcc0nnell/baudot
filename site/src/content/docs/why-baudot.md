---
title: Why Baudot
description: The problem Baudot is designed to make observable.
---

Accessible communications failures often hide behind a successful protocol state.

A SIP transaction can succeed while the replacement leg has no usable real-time text. A media description can negotiate successfully while the wrong SDP is active. A transfer can complete while the original accessible leg was torn down too early. A historical workaround can tell us where to look without proving that a modern implementation has the same defect.

Baudot exists to keep those facts separate.

## Working principles

1. **Behavior before stack choice.** Portable behavior should be expressible before it is tied to a specific SIP, WebRTC, VRS, or application implementation.
2. **Connected is not usable.** Signaling, transport, presentation, and modality readiness are independent observations.
3. **Evidence before conformance claims.** A fixture or adapter is not conformant because its documentation says so.
4. **Transport does not redefine text semantics.** T.140 behavior belongs to the semantic core; transports carry it.
5. **Interop failures become tests.** Historical production behavior can motivate a scenario without becoming normative.

## What Baudot is not

Baudot is not a replacement SIP stack, a VRS provider, a standards body, or a shortcut to certification. It is a proving ground: scenarios, evidence requirements, implementation oracles, and reducers that make interoperability claims reviewable.
