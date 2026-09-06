---
title: Provenance
description: Source identity and licensing are part of the evidence story.
---

Baudot treats provenance as engineering data, not cleanup work.

## External implementations

When an external implementation is admitted as an oracle or specimen, the preferred record includes:

- upstream repository identity;
- exact commit or release pin;
- the role it plays in the experiment;
- whether source is vendored;
- how it is built or invoked;
- upstream-declared license information; and
- the boundary between implementation evidence and Baudot semantic authority.

## Historical donor material

Historical systems such as ACE Direct can motivate scenarios. Baudot records the relevant donor commit and files where practical, but a historical workaround is not copied forward merely because it once existed in production.

## Evidence integrity

Scenario runs preserve source hashes and artifact digests where those identities are material to the claim. The goal is simple: a later reviewer should be able to answer **what code ran, what was observed, and what evidence supports the verdict**.

## Distribution is a separate decision

Running or building an external oracle during a controlled qualification experiment is not the same thing as redistributing that implementation. Any future packaging or distribution step should evaluate the applicable upstream license obligations explicitly.
