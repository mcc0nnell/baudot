# Apache APISIX TRS API-edge profile

Apache APISIX is the bounded external gateway/enforcement edge for the Apache-native TRS stack. It owns transport- and gateway-level controls; it does not become TRS policy or protocol authority.

## Pin

```text
Apache APISIX: 3.18.0
release commit: 0796d9c2cbedb1f8bf8194292ff526599f4fde20
```

## Runtime boundary

```text
client
  -> TLS / gateway authentication / rate limit / route
  -> APISIX
  -> Baudot application service
  -> Ranger policy decision where required
  -> application enforcement
```

The canonical non-equivalence remains:

```text
gateway authenticated
!= Ranger authorized

gateway route matched
!= protocol valid

HTTP success at edge
!= business operation valid
!= subscriber eligible
!= compensable
!= claim approved
!= payment authorized
!= accessibility ready
```

## Live APISIX 3.18 qualification lane

The repository now boots the exact released `apache/apisix:3.18.0-debian` runtime in standalone YAML mode with a synthetic TLS certificate, a bounded OIDC introspection/discovery peer, and a synthetic downstream service representing a Ranger-gated application service.

The live route is deliberately narrow:

```text
GET /itrs/*
  -> TLS SNI baudot.invalid
  -> bearer-only openid-connect
  -> required scope: itrs
  -> local limit-count
  -> credential-header removal
  -> synthetic downstream Ranger decision
```

The lane proves:

```text
missing bearer token             -> 401
inactive / invalid token         -> 401
active token without itrs scope  -> 403
authenticated + scoped request   -> downstream Ranger DENY -> 403
third admitted request/window     -> 429
```

The authenticated request remaining `403` is intentional: gateway authentication succeeds, but the downstream protected-domain policy decision is still DENY.

## Credential propagation boundary

The OIDC profile explicitly disables access-token and userinfo forwarding, and `proxy-rewrite` removes credential/token headers before upstream dispatch.

The synthetic upstream records whether it observed any of:

- `Authorization`
- `X-Access-Token`
- `X-Userinfo`
- `X-ID-Token`
- `X-Refresh-Token`
- `X-Raw-ID-Token`

The live lane requires that observed forbidden-header set to be empty. APISIX container logs are also checked for the synthetic bearer token, client secret, and literal bearer header.

## TLS boundary

The live test exposes only the APISIX HTTPS listener to the host and resolves a reserved synthetic SNI (`baudot.invalid`) to localhost. The synthetic OIDC/upstream peers remain on the isolated Docker network.

The synthetic discovery/introspection endpoint uses HTTP only inside that isolated test network. This does **not** claim a production IdP transport profile; production discovery/introspection must use an appropriately secured transport and trust configuration.

## First route families

The neutral contract retains these deployment families:

```text
/itrs/*       -> iTRS service       -> Ranger required downstream
/equipment/*  -> equipment service  -> Ranger required downstream
/fund/*       -> Fund service       -> Ranger required downstream
/analytics/*  -> analytics service  -> read-only edge
```

Only the `/itrs/*` family is exercised in the current live qualification lane.

## Privacy boundary

Gateway evidence and logs must not become a shadow identity/URD/CDR store. The profile forbids request/response body logging, Authorization/token logging, telephone numbers, and subscriber IDs. Only bounded technical/correlation data is admissible.

## Claim boundary

The live lane proves a bounded APISIX 3.18 deployment profile with synthetic TLS, bearer introspection, scope enforcement, local rate limiting, header stripping, and downstream-deny preservation. It does not establish production API security, production OIDC/IdP integration, production TLS posture, iTRS authorization correctness, subscriber eligibility, compensability, Fund authorization, provider certification, or accessibility readiness.
