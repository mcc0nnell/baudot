#!/usr/bin/env python3
"""Admit one exact clean SIPp checkout for hostile scenario authoring.

This gate proves only that the pinned upstream source exposes the XML scenario
primitives Baudot intends to use. It does not admit SIPp as an oracle and does
not establish runtime interoperability or conformance.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

EXPECTED_COMMIT = "c496186356b9089fc70b311607be4d2853809625"
EXPECTED_REPOSITORY = "SIPp/sipp"

SURFACES = {
    "docs/scenarios/ownscenarios.rst": [
        '<send retrans="500">',
        '<send lost="10">',
        '<recv response="100" optional="true">',
        '<recv timeout="100000">',
        '<pause milliseconds="5000"/>',
        'start_txn="invite"',
        'response_txn="invite"',
        'ack_txn="invite"',
        'ignoresdp="true"',
    ],
    "src/scenario.cpp": [
        '<recv response=\\"183\\" optional=\\"true\\">',
    ],
    "regress/github-#0850/uac_no_rrs.xml": [
        'retrans="500"',
        'start_txn="invite"',
    ],
}


def run(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_remote(value: str) -> str:
    remote = value.removesuffix(".git")
    if remote.startswith("git@github.com:"):
        remote = "https://github.com/" + remote.split(":", 1)[1]
    return remote.rstrip("/")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: sipp_candidate_admission.py <sipp-checkout>")

    repo = Path(sys.argv[1]).resolve()
    if not (repo / ".git").exists():
        raise AssertionError(f"not a Git checkout: {repo}")

    commit = run(repo, "rev-parse", "HEAD")
    if commit != EXPECTED_COMMIT:
        raise AssertionError(f"unexpected SIPp commit: {commit}")

    dirty = run(repo, "status", "--porcelain")
    if dirty:
        raise AssertionError("SIPp checkout is not clean")

    remote = normalize_remote(run(repo, "remote", "get-url", "origin"))
    expected_remote = f"https://github.com/{EXPECTED_REPOSITORY}"
    if remote != expected_remote:
        raise AssertionError(f"unexpected SIPp origin: {remote}")

    evidence: dict[str, object] = {
        "repository": EXPECTED_REPOSITORY,
        "commit": commit,
        "cleanCheckout": True,
        "role": "hostile_signaling_stimulus_generator",
        "oracleAdmitted": False,
        "terminalVerdictAuthority": False,
        "surfaces": {},
        "primitives": {
            "rawSendReceive": False,
            "udpRetransmission": False,
            "lossInjection": False,
            "explicitPause": False,
            "receiveTimeout": False,
            "optionalReceive": False,
            "transactionCorrelation": False,
            "sdpIgnore": False,
        },
        "claimBoundary": {
            "sipConformance": False,
            "referConformance": False,
            "reinviteConformance": False,
            "rfc4103Conformance": False,
            "t140Conformance": False,
            "accessibilityConformance": False,
        },
    }

    observed_text = ""
    for relative, required_tokens in SURFACES.items():
        path = repo / relative
        if not path.is_file():
            raise AssertionError(f"missing upstream source surface: {relative}")
        text = path.read_text(encoding="utf-8")
        for token in required_tokens:
            if token not in text:
                raise AssertionError(f"{relative}: missing required primitive token {token!r}")
        evidence["surfaces"][relative] = {
            "sha256": sha256(path),
            "requiredTokenCount": len(required_tokens),
        }
        observed_text += "\n" + text

    primitives = evidence["primitives"]
    primitives["rawSendReceive"] = "<send" in observed_text and "<recv" in observed_text
    primitives["udpRetransmission"] = 'retrans="500"' in observed_text
    primitives["lossInjection"] = 'lost="10"' in observed_text
    primitives["explicitPause"] = '<pause milliseconds="5000"/>' in observed_text
    primitives["receiveTimeout"] = 'timeout="100000"' in observed_text
    primitives["optionalReceive"] = 'optional="true"' in observed_text
    primitives["transactionCorrelation"] = all(
        token in observed_text
        for token in ('start_txn="invite"', 'response_txn="invite"', 'ack_txn="invite"')
    )
    primitives["sdpIgnore"] = 'ignoresdp="true"' in observed_text

    if not all(primitives.values()):
        missing = [name for name, value in primitives.items() if not value]
        raise AssertionError(f"missing required SIPp scenario primitives: {missing}")

    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
