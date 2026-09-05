#!/usr/bin/env python3
"""Admit an external Elixip checkout as an observation-only Baudot oracle.

This module intentionally does not install, vendor, import, or link Elixip.  It
verifies the process boundary chosen in ADR-0001 and emits evidence that binds an
external run to one upstream repository identity, exact commit, clean checkout,
and Baudot-owned scenario/config bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Sequence

SCHEMA = "baudot.elixip-oracle-admission/v1"
EXPECTED_REPOSITORY = "neutrino38/elixip"
EXPECTED_COMMIT = "d5f942768213200576031346099a896fb61bef4f"
AUTHORITY = "observation-only"


class AdmissionError(ValueError):
    pass


def normalize_github_repository(remote: str) -> str:
    value = remote.strip()
    patterns = (
        r"^(?:https?://github\.com/|ssh://git@github\.com/|git@github\.com:)([^/]+/[^/]+?)(?:\.git)?$",
        r"^git://github\.com/([^/]+/[^/]+?)(?:\.git)?$",
    )
    for pattern in patterns:
        match = re.match(pattern, value)
        if match:
            return match.group(1).removesuffix(".git")
    raise AdmissionError(f"unsupported or non-GitHub origin URL: {remote!r}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_identity(*, repository: str, commit: str, dirty: bool) -> None:
    if repository != EXPECTED_REPOSITORY:
        raise AdmissionError(
            f"repository mismatch: expected {EXPECTED_REPOSITORY}, observed {repository}"
        )
    if commit != EXPECTED_COMMIT:
        raise AdmissionError(
            f"commit mismatch: expected {EXPECTED_COMMIT}, observed {commit}"
        )
    if dirty:
        raise AdmissionError("external Elixip checkout is dirty")


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def inspect_checkout(root: Path) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise AdmissionError(f"Elixip root does not exist: {root}")
    try:
        top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
        remote = _git(root, "remote", "get-url", "origin")
        commit = _git(root, "rev-parse", "HEAD")
        status = _git(root, "status", "--porcelain=v1", "--untracked-files=normal")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise AdmissionError(f"unable to inspect Elixip git checkout: {exc}") from exc

    if top != root:
        raise AdmissionError(f"Elixip root must be repository root: observed {top}")

    repository = normalize_github_repository(remote)
    dirty = bool(status)
    validate_identity(repository=repository, commit=commit, dirty=dirty)

    runner = root / "apps/elixip2/lib/mix/tasks/scenario.ex"
    if not runner.is_file():
        raise AdmissionError(f"pinned checkout is missing scenario runner: {runner}")

    return {
        "repository": repository,
        "origin": remote,
        "commit": commit,
        "clean": True,
        "scenarioRunnerSha256": sha256_file(runner),
    }


def build_manifest(*, checkout: dict[str, object], scenario: Path, config: Path | None) -> dict[str, object]:
    scenario = scenario.resolve()
    if not scenario.is_file():
        raise AdmissionError(f"scenario file does not exist: {scenario}")
    if scenario.suffix != ".exs":
        raise AdmissionError("Elixip oracle scenario must be a Baudot-owned .exs file")

    config_record: dict[str, object] | None = None
    if config is not None:
        config = config.resolve()
        if not config.is_file():
            raise AdmissionError(f"config file does not exist: {config}")
        config_record = {
            "name": config.name,
            "sha256": sha256_file(config),
            "contentPreserved": False,
        }

    return {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "implementation": {
            "name": "Elixip",
            "repository": checkout["repository"],
            "commit": checkout["commit"],
            "cleanCheckout": checkout["clean"],
            "scenarioRunnerSha256": checkout["scenarioRunnerSha256"],
        },
        "scenario": {
            "name": scenario.name,
            "sha256": sha256_file(scenario),
            "contentPreserved": True,
        },
        "config": config_record,
        "execution": {
            "runner": "mix scenario",
            "terminalVerdictAuthority": False,
        },
        "claimBoundary": (
            "Admission proves external implementation identity and input binding only; "
            "it is not SIP, REFER, RFC 4103, T.140, VRS, or accessibility conformance evidence."
        ),
    }


def build_command(scenario: Path, config: Path | None = None) -> list[str]:
    command = ["mix", "scenario"]
    if config is not None:
        command.extend(["--config", str(config.resolve())])
    command.append(str(scenario.resolve()))
    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elixip-root", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checkout = inspect_checkout(args.elixip_root)
        manifest = build_manifest(checkout=checkout, scenario=args.scenario, config=args.config)
    except AdmissionError as exc:
        print(f"elixip admission: {exc}", file=sys.stderr)
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"✓ admitted external Elixip oracle {EXPECTED_REPOSITORY}@{EXPECTED_COMMIT}")
    print(f"admission evidence: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
