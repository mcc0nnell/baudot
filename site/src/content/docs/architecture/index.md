---
title: System shape
description: The authority boundaries that keep Baudot implementation-independent.
---

Baudot deliberately separates semantic authority, execution, observations, and terminal reduction.

```text
portable accessibility behavior
             │
             ▼
     scenario + vectors
             │
             ▼
      execution adapter
             │
             ▼
       system under test
             │
             ▼
   source-identified facts
             │
             ▼
     preserved evidence
             │
             ▼
    independent reducer
             │
             ▼
       scoped verdict
```

## Implementation ensemble

The proving ground uses implementations for different roles rather than asking one stack to be both the subject and the judge.

- **JAIN SIP** — glass-box signaling instrument.
- **Elixip** — independent SIP/call-state oracle.
- **PJSIP/PJPROJECT** — external native RTT media oracle for qualified profiles.
- **Sandia Wiretap** — controlled network/evidence substrate, never verdict authority.
- **Apache OpenMeetings** — integration specimen and scenario donor.
- **ACE Direct** — historical donor corpus used to motivate scenarios without copying workarounds forward.

The same pattern can admit additional gateways, WebRTC runtimes, VRS mocks, hardware endpoints, and legacy media implementations without moving their behavior into Baudot's semantic core.
