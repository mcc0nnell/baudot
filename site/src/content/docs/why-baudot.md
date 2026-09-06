---
title: Why Baudot
description: Why an evidence-first proving ground spans both accessible communications and synthetic regulated-system workflows.
---

Baudot started from a practical problem in accessible telecommunications: the important behavior often lives between standards, signaling stacks, media implementations, gateways, packet captures, and institutional memory.

The project turns those boundaries into executable scenarios with preserved evidence and explicit claim limits.

That method turned out to be useful beyond communications.

## The common problem

In both accessible calling and synthetic Fund workflows, one successful subsystem can easily be mistaken for proof of the whole system.

```text
SIP dialog established
    != RTT usable

journal balanced
    != program authorized
```

Baudot keeps those claims separate.

The communications lane asks whether the observed signaling, negotiation, transport, media, and presentation evidence is sufficient for the declared accessibility behavior.

The Fund lane asks whether public-rule-calibrated synthetic events produced the expected accounting behavior against an external ledger implementation without letting that ledger become the authority for eligibility, contribution policy, claim approval, or payment authorization.

## Why preserve the evidence

A useful test result should survive longer than the terminal window that produced it. Baudot therefore treats implementation identity, source/build provenance, messages or API exchanges, runtime identifiers, timestamps, scenario manifests, independent reducer output, and the claim boundary itself as part of the result.

This lets a later reviewer answer:

1. what behavior or policy was declared;
2. what implementation actually ran;
3. what was observed;
4. how the verdict was reduced; and
5. what the run did not prove.

## Why external implementations matter

A proving ground becomes more interesting when it crosses into real independent implementations.

JAIN SIP, Elixip, PJSIP, Sandia Wiretap, and Apache Fineract each contribute different kinds of evidence. They are not correct by definition. Their output is preserved and evaluated against the declared scenario boundary.

That makes the same scenario portable enough to be replayed against another SIP stack, gateway, network substrate, media endpoint, or accounting engine later.

## Why the synthetic Fund belongs here

The Synthetic TRS Fund Lab is not a departure from Baudot's method. It applies the same discipline to a different system boundary:

```text
public rules -> synthetic event -> external implementation -> evidence -> independent reduction
```

The useful artifact is not merely a ledger or a dashboard. It is a replayable explanation of how a declared event became an observed state and which authority was responsible for each decision along the way.

That is the through-line: **systems should prove what they claim, and no component should be allowed to claim more than its evidence supports.**
