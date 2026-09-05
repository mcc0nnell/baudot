# Baudot MCP control plane

## Status

Accepted architectural direction; implementation intentionally staged.

## Decision

Baudot will expose a thin Model Context Protocol (MCP) control plane on the Java edge using Apache Juneau's MCP server support.

The MCP layer is an adapter over Baudot's existing semantic and evidence model. It does **not** own SIP state, T.140 semantics, RFC 4103 behavior, transport behavior, or conformance decisions.

```text
agent / assurance runtime
          |
          v
   Apache Juneau MCP
          |
          v
   Baudot tool boundary
          |
     +----+-------------------+
     |                        |
     v                        v
T.140 / testkit          JAIN SIP harness
semantics/evidence       signaling/transport
     |                        |
     +-----------+------------+
                 |
                 v
          preserved evidence
                 |
        +--------+---------+
        |                  |
        v                  v
   SIPp proving peer   Beckett / Godot
                      visualization only
```

## Boundary rules

1. **Baudot semantics remain authoritative.** MCP does not redefine T.140 behavior or transport-independent test vectors.
2. **JAIN SIP owns SIP mechanics.** Dialog, transaction, header, SDP, and transport state stay behind the Baudot adapter rather than being recreated in MCP handlers.
3. **Evidence is the default output.** Tools return observations and preserved evidence suitable for later verification; they do not turn observations into conformance claims.
4. **SIPp is an independent proving peer.** SIPp may drive or challenge the implementation in controlled scenarios, but it is not the Baudot runtime.
5. **Beckett is downstream visualization.** Godot/Beckett may render Baudot evidence as an explorable system, but visualization must not become an execution or policy authority.
6. **Mutation is staged.** The first MCP surface is read/observe/export oriented. Live call and RTT mutation tools require explicit policy gates and arrive later.

## Initial tool surface

The first vertical slice is intentionally small:

- `inspect_dialog` — return normalized dialog and transaction state for a controlled run.
- `observe_sip_trace` — return a bounded, structured signaling trace with correlation identifiers.
- `compare_sdp` — compare offer/answer state and report differences without claiming media usability.
- `export_evidence` — emit the preserved evidence bundle for a run.

These tools should be deterministic over a fixed evidence bundle wherever possible.

## Deferred mutation surface

The following tools are deliberately not part of the first slice:

- `originate_test_call`
- `inject_rtt`
- raw SIP message mutation
- arbitrary destination dialing
- arbitrary network or media injection

When introduced, mutation tools must be restricted to controlled endpoints/scenarios and must produce the same evidence trail as non-MCP execution.

## Evidence model

The MCP adapter should preserve the existing separation between facts such as:

- signaling success
- dialog establishment
- transport readiness
- media-path reachability
- RTT readiness
- presentation/usability

A successful SIP dialog must not be reported as successful media or successful RTT unless the relevant evidence exists.

## Apache Juneau integration

Apache Juneau is the selected MCP implementation because it keeps the control plane in the same Java/Maven runtime as the JAIN SIP harness and provides a first-party MCP server surface.

At the time this decision was recorded, Juneau's first-party MCP example targets the `2026-07-28` MCP revision from the `10.0.0-SNAPSHOT` development line. Baudot therefore records the architecture now but does **not** add a snapshot dependency to the build. Runtime integration should pin a released Juneau version that contains the required MCP server module.

Upstream reference:

- `apache/juneau` — `juneau-examples/juneau-examples-mcp`
- server module used by the current example: `juneau-rest-server-mcp-v20260728`

## Non-goals

This decision does not:

- make Baudot an Apache Software Foundation project;
- claim MCP, SIP, RFC 4103, T.140, VRS, or accessibility conformance;
- replace the normative vector/testkit layer;
- make Beckett or Godot part of the protocol implementation;
- expose unrestricted telecom operations to an agent.

## Next implementation slice

When a suitable released Juneau artifact is available:

1. add the pinned Juneau MCP server dependency;
2. implement the four read/observe/export tools above as adapters over existing Baudot services;
3. add in-process tool-contract tests using fixed evidence fixtures;
4. prove that direct harness execution and MCP execution produce equivalent preserved evidence;
5. only then evaluate gated mutation tools and SIPp-driven adversarial scenarios.
