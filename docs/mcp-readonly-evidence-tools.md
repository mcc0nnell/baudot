# Read-only MCP evidence tools

Issue #92 is the first executable MCP-facing Baudot slice.

```text
MCP client
  -> released Camel 4.22 MCP qualification adapter
  -> neutral read-only tool contract
  -> preserved synthetic evidence fixture
  -> identical bounded result
```

The first tool surface is deliberately tiny:

```text
inspect_dialog
observe_sip_trace
compare_sdp
export_evidence
```

No call origination, RTT injection, raw SIP mutation, arbitrary dialing, media injection, or live-call termination is exposed.

## Released implementation lane

The qualification lane pins:

```text
Apache Camel 4.22.0 LTS
release commit 1a54683f4becad3b32df42507e709526d8563f35
camel-ai-tool
camel-mcp-server
streamable HTTP
```

Camel 4.22 marks the MCP/AI-tool surface as preview. Qualification success is therefore interoperability evidence, not a production-readiness claim.

The server publishes only the explicit tag:

```text
baudot-evidence-readonly
```

The live test requires `tools/list` to contain exactly the four expected tools.

## Tool hints

All four tools publish:

```text
readOnlyHint=true
destructiveHint=false
idempotentHint=true
openWorldHint=false
```

These are MCP client hints only.

```text
readOnlyHint=true
!= authorization
```

A production deployment still requires its Shiro/Ranger/API boundary as appropriate.

## Direct/MCP equivalence

The controlled fixture `run-001` contains no production subscriber, provider, call, or credential data.

The live test:

1. reads the direct fixture result;
2. starts a real Camel 4.22 MCP server;
3. initializes a real streamable-HTTP MCP client;
4. verifies the exact advertised tool set and annotations;
5. calls every tool with `runId=run-001`; and
6. requires the returned text to equal the direct fixture bytes exactly.

That gives a narrow but useful invariant:

```text
direct evidence inspection
== MCP evidence inspection
```

for the facts in these fixed fixtures.

It does **not** imply:

```text
MCP tool success
== SIP truth
== media usability
== RTT readiness
== accessibility readiness
```

## Juneau status

Apache Juneau remains the preferred/reference protocol candidate because its development line has revision-neutral MCP cores plus dated protocol adapters. However, that MCP implementation is currently on unreleased Juneau 10 development artifacts.

Normative Baudot CI therefore does not depend on Juneau snapshots. When a released Juneau version containing MCP lands, it can be qualified against these same contracts and fixtures.

## Authority boundary

```text
MCP tool listed
!= actor authorized

MCP call succeeds
!= protocol valid

inspect_dialog
!= independent dialog authority

compare_sdp
!= media usable

observe_sip_trace
!= accessibility ready

export_evidence
!= new semantic claim
```

## Next threshold

Compose a protected-operation contract with #127 Shiro actor/session context and #114 Ranger policy decisions, while keeping these four evidence-inspection tools read-only. Mutation should arrive only as a separate, explicitly authorized profile with controlled destinations and deterministic negative tests.

## Sources

- Apache Camel 4.22.0 release: <https://camel.apache.org/releases/release-4.22.0/>
- Camel MCP server: <https://camel.apache.org/components/4.22.x/others/mcp-server.html>
- Camel AI Tool: <https://camel.apache.org/components/4.22.x/ai-tool-component.html>
- Apache Juneau repository/status: <https://github.com/apache/juneau>

## Claim boundary

This profile does not establish production MCP security, production authentication/authorization, Apache Camel MCP conformance beyond the bounded fixture, future Apache Juneau MCP conformance, SIP/media/RTT conformance, or accessibility readiness.
