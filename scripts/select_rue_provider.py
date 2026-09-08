#!/usr/bin/env python3
"""Select one synthetic RFC 9248 provider deterministically and fail closed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIST = ROOT / "testkit" / "vrs" / "fixtures" / "provider-list-v1.json"


def load_provider_list(path: Path) -> list[dict[str, str]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("providers"), list):
        raise ValueError("provider list must contain a providers array")

    providers: list[dict[str, str]] = []
    names: set[str] = set()
    entry_points: set[str] = set()
    for index, raw in enumerate(value["providers"]):
        if not isinstance(raw, dict):
            raise ValueError(f"provider {index} must be an object")
        if "entryPoint" in raw:
            raise ValueError("illustrative entryPoint is not accepted; use normative providerEntryPoint")
        name = raw.get("name")
        entry_point = raw.get("providerEntryPoint")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"provider {index} has invalid name")
        if not isinstance(entry_point, str) or not entry_point.strip():
            raise ValueError(f"provider {index} has invalid providerEntryPoint")
        if name in names:
            raise ValueError(f"duplicate provider name: {name}")
        if entry_point in entry_points:
            raise ValueError(f"duplicate providerEntryPoint: {entry_point}")
        names.add(name)
        entry_points.add(entry_point)
        providers.append({"name": name, "providerEntryPoint": entry_point})
    return providers


def select_provider(providers: list[dict[str, str]], name: str) -> dict[str, str]:
    matches = [provider for provider in providers if provider["name"] == name]
    if len(matches) != 1:
        raise ValueError(f"provider selection must resolve exactly once: {name!r} matched {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True, help="exact human-readable provider name")
    parser.add_argument("--provider-list", type=Path, default=DEFAULT_LIST)
    parser.add_argument("--json", action="store_true", help="emit the bounded selection record")
    args = parser.parse_args()

    selected = select_provider(load_provider_list(args.provider_list), args.provider)
    if args.json:
        print(json.dumps(
            {
                "schema": "baudot.rue-provider-selection@1",
                "source": str(args.provider_list.relative_to(ROOT)),
                "selectedProvider": selected["name"],
                "providerEntryPoint": selected["providerEntryPoint"],
                "claim": "synthetic-provider-selection-only",
            },
            sort_keys=True,
        ))
    else:
        print(selected["providerEntryPoint"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
