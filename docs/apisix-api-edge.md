# Apache APISIX API edge

Baudot uses Apache APISIX as the bounded external API gateway and enforcement edge for the Apache-native TRS stack.

## Pin

```text
Apache APISIX: 3.18.0
release commit: 0796d9c2cbedb1f8bf8194292ff526599f4fde20
```

## Role

APISIX may terminate TLS, authenticate callers at the gateway, route requests, apply rate limits, and emit bounded technical telemetry.

```text
client
  -> TLS / gateway authentication / rate limit / route
  -> APISIX
  -> Baudot application service
  -> Ranger policy decision where required
  -> application enforcement
```

The gateway is not the TRS policy authority.

## First route families

- `/itrs/*` -> iTRS service, downstream Ranger policy required;
- `/equipment/*` -> equipment service, downstream Ranger policy required;
- `/fund/*` -> Fund service, downstream Ranger policy required;
- `/analytics/*` -> read-only analytics service.

## Authority boundary

```text
gateway authenticated
!= Ranger authorized

gateway route matched
!= protocol valid

HTTP 2xx at edge
!= business operation valid
!= subscriber eligible
!= compensable
!= claim approved
!= payment authorized
!= accessibility ready
```

APISIX enforces the external boundary. Ranger remains the centralized resource/action/context policy decision point, and the application remains responsible for enforcing Ranger's decision and its own protocol/business invariants.

## Logging and privacy

The initial profile forbids logging:

- request bodies;
- response bodies;
- Authorization headers;
- access or refresh tokens;
- telephone numbers; and
- subscriber identifiers.

Only opaque request/correlation/route/upstream identifiers are admitted by the contract.

## Security posture

APISIX 3.18.0 includes stricter authentication and validation behavior, including fail-closed OpenID Connect validation. Baudot still treats those controls as gateway security behavior rather than TRS program-policy authority.

## Next threshold

Boot pinned APISIX 3.18.0 with synthetic routes, prove unauthenticated and rate-limited requests fail at the edge, prove an authenticated iTRS request still cannot execute when downstream Ranger denies it, and inspect gateway logs to confirm forbidden subscriber/token fields are absent.
