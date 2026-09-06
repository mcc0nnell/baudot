#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from urllib.request import urlopen


def load_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


def load_json(path):
    return json.loads(Path(path).read_text())


def get_json(url):
    with urlopen(url, timeout=2) as response:
        return json.loads(response.read().decode())


def check(name, condition):
    print(f"{name:<58} {'PASS' if condition else 'FAIL'}")
    return 1 if condition else 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--work-dir", required=True)
    p.add_argument("--adapter-a", default="http://127.0.0.1:8801")
    p.add_argument("--adapter-b", default="http://127.0.0.1:8802")
    p.add_argument("--ace-a", default="http://127.0.0.1:8831")
    p.add_argument("--ace-b", default="http://127.0.0.1:8832")
    args = p.parse_args()

    work = Path(args.work_dir)
    a_routes = load_jsonl(work / "traces/agi-a.jsonl")
    b_routes = load_jsonl(work / "traces/agi-b.jsonl")
    sip_a = load_json(work / "traces/sip-a-to-b.json")
    sip_b = load_json(work / "traces/sip-b-to-a.json")
    stats_a = get_json(args.adapter_a + "/stats")
    stats_b = get_json(args.adapter_b + "/stats")
    ace_a = get_json(args.ace_a + "/api/config")
    ace_b = get_json(args.ace_b + "/api/config")

    passed = 0
    total = 8

    passed += check(
        "ACE instances are bound to two real AMI endpoints",
        ace_a.get("asterisk", {}).get("ami", {}).get("port") == 5038
        and ace_b.get("asterisk", {}).get("ami", {}).get("port") == 5039,
    )
    passed += check(
        "historical /vrsverify/ classification hits both adapters",
        stats_a.get("requests") == 2
        and stats_a.get("successes") == 1
        and stats_a.get("failures") == 1
        and stats_b.get("requests") == 1
        and stats_b.get("successes") == 1,
    )
    passed += check(
        "Asterisk A AGI consumes provider-A AllCallQuery route",
        len(a_routes) == 1
        and a_routes[0].get("toTn") == "2025550103"
        and a_routes[0].get("connectAllowed") is True
        and a_routes[0].get("routeUri") == "sip:2025550103@provider-b.invalid"
        and bool(a_routes[0].get("transactionId")),
    )
    passed += check(
        "Asterisk B AGI consumes provider-B AllCallQuery route",
        len(b_routes) == 1
        and b_routes[0].get("toTn") == "2025550101"
        and b_routes[0].get("connectAllowed") is True
        and b_routes[0].get("routeUri") == "sip:2025550101@vrs-a.example.invalid"
        and bool(b_routes[0].get("transactionId")),
    )
    passed += check(
        "Asterisk A emits exact CTE logical URI into JAIN-SIP peer",
        sip_a.get("passed") is True
        and sip_a.get("requestUri") == "sip:2025550103@provider-b.invalid"
        and sip_a.get("inviteReceived") is True
        and sip_a.get("ackReceived") is True
        and sip_a.get("byeOkReceived") is True,
    )
    passed += check(
        "Asterisk B emits exact CTE logical URI into JAIN-SIP peer",
        sip_b.get("passed") is True
        and sip_b.get("requestUri") == "sip:2025550101@vrs-a.example.invalid"
        and sip_b.get("inviteReceived") is True
        and sip_b.get("ackReceived") is True
        and sip_b.get("byeOkReceived") is True,
    )
    passed += check(
        "negative ACE classification never reaches route AGI or SIP",
        stats_a.get("lastNumber") == "2025550105"
        and len(a_routes) == 1
        and sip_a.get("requestUri") != "sip:2025550105@provider-a.invalid",
    )
    passed += check(
        "directory identity and transport proxy remain distinct",
        sip_a.get("routeHeader") is not None
        and "127.0.0.1:5092" in sip_a.get("routeHeader", "")
        and "provider-b.invalid" in sip_a.get("requestUri", "")
        and sip_b.get("routeHeader") is not None
        and "127.0.0.1:5093" in sip_b.get("routeHeader", "")
        and "vrs-a.example.invalid" in sip_b.get("requestUri", ""),
    )

    print(f"Dual ACE -> Asterisk -> JAIN-SIP lab: {passed}/{total} {'PASS' if passed == total else 'FAIL'}")
    if passed != total:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
