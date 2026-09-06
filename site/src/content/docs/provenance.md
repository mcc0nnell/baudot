---
title: Provenance
description: Source identity, build identity, and licensing are part of the evidence story.
---

Baudot treats provenance as engineering data, not cleanup work.

## External implementations

When an external implementation is admitted as an oracle, specimen, or execution substrate, the preferred record includes:

- upstream repository identity;
- exact commit or release pin;
- the role it plays in the experiment;
- whether source is vendored;
- how it is built or invoked;
- upstream-declared license information; and
- the boundary between implementation evidence and Baudot authority.

## Build provenance matters too

A release label is useful, but it is not always enough to identify what actually ran.

The Synthetic TRS Fund lane therefore verifies the Apache Fineract `1.15.0` source commit, builds the container from that exact source tree in CI, and records the source tree, Java version, Gradle version, build task, local image ID, and repo tags in the evidence bundle.

```text
release tag
    + source commit
    + source tree
    + build toolchain
    + executed image ID
    = reproducible implementation identity
```

This avoids depending on a moving external image tag and avoids assuming that a nominal release tag exists in every container registry.

## Historical donor material

Historical systems such as ACE Direct can motivate scenarios. Baudot records the relevant donor commit and files where practical, but a historical workaround is not copied forward merely because it once existed in production.

## Evidence integrity

Scenario runs preserve source hashes, build identities, artifact digests, manifest hashes, and external transaction identifiers where those identities are material to the claim. The goal is simple: a later reviewer should be able to answer **what code ran, what was observed, and what evidence supports the verdict**.

## Distribution is a separate decision

Running or building an external implementation during a controlled qualification experiment is not the same thing as redistributing that implementation. Any future packaging or distribution step should evaluate the applicable upstream license obligations explicitly.
