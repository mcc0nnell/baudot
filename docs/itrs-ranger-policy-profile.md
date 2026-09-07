# iTRS Ranger policy profile

This slice implements the first concrete Apache Ranger integration boundary for Baudot's synthetic iTRS proving ground.

It is deliberately narrower than a production authorization deployment:

```text
Shiro-authenticated subject
        -> trusted Baudot iTRS service
        -> Ranger PDP /v1/authorize
        -> explicit ALLOW / DENY
        -> independent iTRS protocol gate
        -> operation may execute
```

The governing invariant is:

```text
identity
!= policy authorization
!= protocol validity
!= route correctness
!= compensability
```

## Ranger integration shape

Current Apache Ranger application-integration guidance describes three steps:

1. register the application's authorization model as a Ranger service definition;
2. request authorization decisions through an embedded plugin or Ranger PDP API; and
3. enforce the returned decision in the application.

For the remote PDP path, the current documented REST shape is:

```text
POST /v1/authorize
{
  "user": { "name": "..." },
  "access": {
    "resource": { "name": "..." },
    "action": "QUERY",
    "permissions": [ "query" ]
  },
  "context": {
    "serviceType": "baudot-itrs",
    "serviceName": "synthetic_itrs"
  }
}
```

with an authorization result containing an explicit decision such as `ALLOW` or `DENY`.

Sources:

- <https://ranger.apache.org/blogs/integrating_applications.html>
- <https://github.com/apache/ranger/tree/master/agents-common/src/main/resources/service-defs>

## Service definition

`interop/ranger/itrs-service-def-v1.json` defines the first clean-room iTRS resource and access vocabulary:

```text
resources
  provider
  subscriber
  telephone-number
  registration
  routing-record

access types
  query
  create
  update
  assign
  route
  audit
```

The definition uses Ranger's standard default string resource matcher and independent root resources. It is an integration profile, not an assertion that the model matches any private administrator implementation.

## Neutral operation mapping

`interop/ranger/itrs-pdp-contract-v1.json` maps Baudot-owned neutral operation classes into the Ranger vocabulary:

```text
itrs.directory.query         -> telephone-number / QUERY  / query
itrs.directory.reverse-query -> routing-record   / QUERY  / query
itrs.registration.create     -> registration     / CREATE / create
itrs.registration.update     -> registration     / UPDATE / update
itrs.number.assign           -> telephone-number / UPDATE / assign
itrs.route.read              -> routing-record   / QUERY  / route
```

These are Baudot integration classes. They are not claimed to be production iTRS API method names.

## Trusted-caller boundary

Ranger's current PDP guidance warns that only trusted PDP callers should be permitted to assert another user's identity, groups, or attributes.

This profile therefore does not let browser/end-user clients call Ranger PDP directly. The trusted Baudot iTRS service forwards only the already-authenticated subject established at the application boundary.

```text
end user
  -> Shiro/application authentication
  -> trusted iTRS service
  -> Ranger PDP
```

An untrusted caller attempting to assert another subject is rejected before any PDP request is sent.

## Fail-closed behavior

Ranger's guidance also states that failure to obtain a PDP decision is not an authorization result and should not become an implicit allow for protected operations.

The adapter therefore treats all of the following as rejection:

- network failure;
- HTTP failure;
- timeout;
- malformed/non-JSON response;
- missing/unknown decision;
- explicit `DENY`;
- unauthenticated subject; and
- untrusted application caller.

Even a valid `ALLOW` still passes through the independent iTRS protocol gate.

## Executable fixtures

The dedicated validator runs a local deterministic HTTP PDP fixture and drives the actual adapter over `POST /v1/authorize`:

```text
ITRS-RANGER-001  authenticated + trusted + ALLOW + protocol valid   -> execute
ITRS-RANGER-002  authenticated + trusted + DENY  + protocol valid   -> reject
ITRS-RANGER-003  authenticated + trusted + ALLOW + protocol invalid -> reject
ITRS-RANGER-004  unauthenticated                                   -> no PDP call
ITRS-RANGER-005  PDP unavailable                                   -> reject
ITRS-RANGER-006  untrusted caller asserting subject                -> no PDP call
ITRS-RANGER-007  malformed PDP result                              -> reject
```

The local server is a deterministic wire-shape fixture. It is not a Ranger implementation and does not establish live Ranger compatibility.

## Next threshold

The next Ranger-specific threshold is a separate pinned live Apache Ranger lane that:

1. registers this service definition in an ephemeral Ranger deployment;
2. creates a synthetic `baudot-itrs` service and deterministic policies;
3. executes the same seven authorization cases against the real PDP server;
4. preserves the registered service definition, policy identities, request/response evidence, Ranger version/commit, and audit output; and
5. requires the same fail-closed protocol-gate outcomes.

That live lane must remain separate from iTRS protocol correctness and from any production-provider claim.

## Claim boundary

This slice proves only the documented Ranger PDP request shape, Baudot's resource/action mapping, trusted-caller boundary, and fail-closed enforcement against a deterministic local fixture.

It does not establish production Ranger deployment security, production Ranger wire compatibility, live iTRS compatibility, provider certification, routing correctness, subscriber eligibility, call compensability, Fund authorization, or accessibility readiness.
