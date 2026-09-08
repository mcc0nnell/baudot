#!/usr/bin/env python3
"""Reduce synthetic TND and RFC 3263-style provider discovery into bounded registration-route evidence."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = ROOT / "testkit" / "part64" / "fixtures" / "registration-valid.json"
NUMBERING = ROOT / "testkit" / "part64" / "fixtures" / "numbering-directory.json"
DNS = ROOT / "testkit" / "vrs" / "fixtures" / "rue-provider-dns-v1.json"
OUT = ROOT / "target" / "evidence" / "RUE-REG-001" / "discovery.json"


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    registration = load(REGISTRATION)
    numbering = load(NUMBERING)
    dns = load(DNS)

    require(registration.get("schema") == "baudot.synthetic-vrs-registration@1", "registration schema drift")
    require(numbering.get("schema") == "baudot.synthetic-trs-numbering-directory@1", "numbering schema drift")
    require(dns.get("schema") == "baudot.synthetic-rue-provider-dns@1", "DNS fixture schema drift")
    require(dns.get("synthetic") is True, "DNS fixture must remain synthetic")

    number = registration.get("nanpNumber")
    default_provider = registration.get("defaultProvider")
    require(isinstance(number, str) and number.startswith("+1"), "synthetic NANP number missing")
    require(isinstance(default_provider, str) and default_provider.endswith(".example"), "default provider must be reserved")

    routes = [item for item in numbering.get("entries", []) if item.get("nanpNumber") == number]
    require(len(routes) == 1, "registration number must resolve to exactly one synthetic TND route")
    route = routes[0]
    require(route.get("status") == "active", "synthetic TND route is not active")
    require(route.get("routeOwner") == default_provider, "TND route owner diverges from default provider")
    expected_uri = f"sip:{number}@{default_provider}"
    require(route.get("uri") == expected_uri, "TND URI does not preserve number/provider identity")

    require(dns.get("providerDomain") == default_provider, "DNS fixture provider domain does not match TND route owner")
    naptr = dns.get("naptr")
    require(isinstance(naptr, list) and naptr, "NAPTR fixture is empty")
    ordered = sorted(naptr, key=lambda row: (row.get("order", 65535), row.get("preference", 65535)))
    selected_naptr = ordered[0]
    require(selected_naptr.get("service") == "SIPS+D2T", "controlled fixture must prefer SIPS+D2T")
    replacement = selected_naptr.get("replacement")

    srv_rows = dns.get("srv", {}).get(replacement)
    require(isinstance(srv_rows, list) and srv_rows, "selected NAPTR replacement has no SRV record")
    selected_srv = sorted(srv_rows, key=lambda row: (row.get("priority", 65535), -row.get("weight", 0), row.get("target", "")))[0]
    host = selected_srv.get("target")
    port = selected_srv.get("port")
    require(isinstance(host, str) and host.endswith(".example."), "selected SRV target must remain reserved")
    require(isinstance(port, int) and 1 <= port <= 65535, "selected SRV port invalid")

    address = dns.get("address", {}).get(host)
    require(address == "127.0.0.1", "controlled registration execution must remain loopback-only")

    evidence = {
        "schema": "baudot.rue-registration-discovery-evidence@1",
        "scenario": "RUE-REG-001",
        "sourceRegistrationScenario": registration.get("scenario"),
        "nanpNumber": number,
        "tndUri": route.get("uri"),
        "tndRouteOwner": route.get("routeOwner"),
        "providerDomain": default_provider,
        "naptrService": selected_naptr.get("service"),
        "naptrReplacement": replacement,
        "srvTarget": host,
        "srvPort": port,
        "resolvedAddress": address,
        "selectedTransport": "tls",
        "tlsPreferredDiscoveryObserved": True,
        "liveDnsQueried": False,
        "liveTndQueried": False,
        "claim": "synthetic-tnd-plus-rfc3263-style-selection-only",
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"RUE registration discovery evidence: {OUT}")
    print(f"  {number} -> {route['uri']} -> {host}:{port}/tls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
