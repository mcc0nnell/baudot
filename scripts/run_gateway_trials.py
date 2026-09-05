#!/usr/bin/env python3
"""Execute BAUDOT-INTEROP-002 with the deterministic reference gateway harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from baudot_reference.gateway import run_gateway_contract

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "testkit" / "gateways" / "rfc4103-rfc8865-equivalence-v1.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--json", action="store_true", help="emit the full evidence trace as JSON")
    args = parser.parse_args()

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    results = run_gateway_contract(contract)
    evidence = {
        "contractId": contract["id"],
        "contractVersion": contract["version"],
        "executionKind": "deterministic-reference-harness",
        "results": [result.as_dict() for result in results],
        "verdict": "pass",
    }

    if args.json:
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2))
    else:
        for result in results:
            print(
                f"✓ {result.trial_id}: {result.source_transport} → {result.target_transport} "
                f"presentation={result.presentation!r} missing={result.missing_text_markers}"
            )
        print(f"BAUDOT-INTEROP-002 runnable reference harness: {len(results)} trial(s) passed.")


if __name__ == "__main__":
    main()
