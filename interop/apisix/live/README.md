# APISIX live-edge fixture

This directory is the bounded runtime fixture for PR #122.

```text
synthetic client
  -> TLS SNI baudot.invalid
  -> Apache APISIX 3.18.0 standalone YAML
  -> bearer introspection + required `itrs` scope
  -> local rate limit
  -> credential-header removal
  -> synthetic downstream Ranger DENY
```

The fixture exists to prove boundary behavior, not production configuration.

Expected observations:

| Case | Expected HTTP status | Meaning |
| --- | ---: | --- |
| no bearer token | 401 | edge authentication fails closed |
| inactive token | 401 | edge authentication fails closed |
| active token without `itrs` scope | 403 | authenticated token lacks required gateway scope |
| active scoped token | 403 | edge authentication succeeded; downstream Ranger-style policy still denies |
| third admitted request in window | 429 | technical edge rate limit |

No status above is a TRS program verdict. In particular, gateway authentication and rate limiting are not Ranger policy decisions.

The synthetic upstream records whether credential/token headers survive proxying. The required set is empty.

The OIDC discovery/introspection peer uses HTTP only on the isolated Docker network. Production IdP transport is explicitly outside this fixture's claim boundary.
