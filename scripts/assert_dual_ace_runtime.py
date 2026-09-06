#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from urllib.request import urlopen


def load_actions(path):
    actions = []
    for line in Path(path).read_text().splitlines():
        if line.strip():
            actions.append(json.loads(line))
    return actions


def has_originate(actions, exten, context, channel):
    for event in actions:
        if event.get("action") != "Originate":
            continue
        fields = event.get("fields", {})
        if (
            fields.get("Exten") == exten
            and fields.get("Context") == context
            and fields.get("Channel") == channel
        ):
            return True
    return False


def get_json(url):
    with urlopen(url, timeout=2) as response:
        return json.loads(response.read().decode())


def check(name, condition):
    print(f"{name:<48} {'PASS' if condition else 'FAIL'}")
    return 1 if condition else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-dir", required=True)
    parser.add_argument("--adapter-a", default="http://127.0.0.1:8801")
    parser.add_argument("--adapter-b", default="http://127.0.0.1:8802")
    parser.add_argument("--ace-a", default="http://127.0.0.1:8831")
    parser.add_argument("--ace-b", default="http://127.0.0.1:8832")
    parser.add_argument("--adapter-a-port", type=int, default=8801)
    parser.add_argument("--adapter-b-port", type=int, default=8802)
    args = parser.parse_args()

    trace_dir = Path(args.trace_dir)
    a_actions = load_actions(trace_dir / "ami-a.jsonl")
    b_actions = load_actions(trace_dir / "ami-b.jsonl")
    a_stats = get_json(args.adapter_a + "/stats")
    b_stats = get_json(args.adapter_b + "/stats")
    ace_a_config = get_json(args.ace_a + "/api/config")
    ace_b_config = get_json(args.ace_b + "/api/config")

    passed = 0
    total = 5

    passed += check(
        "two live ACE configs bind separate adapters",
        ace_a_config.get("vrscheck", {}).get("port") == args.adapter_a_port
        and ace_b_config.get("vrscheck", {}).get("port") == args.adapter_b_port
        and ace_a_config.get("vrscheck", {}).get("url") == "http://127.0.0.1"
        and ace_b_config.get("vrscheck", {}).get("url") == "http://127.0.0.1",
    )

    passed += check(
        "ACE A real handler selects outbound-CA",
        has_originate(a_actions, "2025550103", "outbound-CA", "SIP/7001"),
    )
    passed += check(
        "ACE B real handler selects outbound-CA",
        has_originate(b_actions, "2025550101", "outbound-CA", "SIP/7002"),
    )
    passed += check(
        "ACE A fail-closed lookup selects from-phones",
        has_originate(a_actions, "2025550105", "from-phones", "SIP/7001"),
    )
    passed += check(
        "dedicated adapters observe both provider runtimes",
        a_stats.get("requests") == 2
        and a_stats.get("successes") == 1
        and a_stats.get("failures") == 1
        and a_stats.get("lastNumber") == "2025550105"
        and b_stats.get("requests") == 1
        and b_stats.get("successes") == 1
        and b_stats.get("failures") == 0
        and b_stats.get("lastNumber") == "2025550101",
    )

    print(f"Dual ACE Connect Lite runtime lab: {passed}/{total} {'PASS' if passed == total else 'FAIL'}")
    if passed != total:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
