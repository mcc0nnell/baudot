#!/usr/bin/env python3
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TOKENS = {
    "provider-a": "baudot-cte-provider-a",
    "provider-b": "baudot-cte-provider-b",
}


def read_agi_environment():
    env = {}
    for raw in sys.stdin:
        line = raw.rstrip("\r\n")
        if not line:
            break
        if ":" in line:
            key, value = line.split(":", 1)
            env[key.strip()] = value.strip()
    return env


def agi_command(command):
    sys.stdout.write(command + "\n")
    sys.stdout.flush()
    return sys.stdin.readline().strip()


def set_var(name, value):
    safe = str(value).replace("\\", "\\\\").replace('"', '\\"')
    agi_command(f'SET VARIABLE {name} "{safe}"')


def main():
    if len(sys.argv) != 7:
        raise SystemExit("usage: itrs_route_agi.py <provider-id> <from-tn> <to-tn> <cte-base> <trace-path> <service>")
    provider_id, from_tn, to_tn, cte_base, trace_path, service = sys.argv[1:]
    token = TOKENS.get(provider_id)
    if token is None:
        raise SystemExit(f"unknown provider id: {provider_id}")

    agi_env = read_agi_environment()
    query = urlencode({
        "from": from_tn,
        "to": to_tn,
        "service": service,
        "direction": "OUTBOUND",
    })
    url = cte_base.rstrip("/") + "/itrs/v2/all-call-query?" + query
    failure = None
    try:
        request = Request(url, headers={"Authorization": "Bearer " + token})
        with urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode())
    except Exception as exc:
        failure = "CTE_QUERY_ERROR"
        payload = {
            "valid": False,
            "connectAllowed": False,
            "failure": failure,
            "detail": str(exc),
        }

    connect_allowed = bool(payload.get("connectAllowed"))
    route_uri = payload.get("routeUri") or ""
    transaction_id = payload.get("transactionId") or ""
    failure = payload.get("failure") or failure or ""

    set_var("BAUDOT_CONNECT_ALLOWED", "1" if connect_allowed else "0")
    set_var("BAUDOT_ROUTE_URI", route_uri)
    set_var("BAUDOT_TRANSACTION_ID", transaction_id)
    set_var("BAUDOT_ROUTE_FAILURE", failure)

    event = {
        "ts": time.time(),
        "providerId": provider_id,
        "fromTn": from_tn,
        "toTn": to_tn,
        "service": service,
        "agiChannel": agi_env.get("agi_channel"),
        "connectAllowed": connect_allowed,
        "routeUri": route_uri or None,
        "transactionId": transaction_id or None,
        "failure": failure or None,
    }
    path = Path(trace_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
