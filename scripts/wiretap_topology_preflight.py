#!/usr/bin/env python3
"""Fail-fast topology guard for Baudot's routed Sandia Wiretap labs.

The current harness pins Wiretap v0.9.0. Baudot observed that Wiretap owns
192.0.2.2 for an IPv4 API path in that profile, so the entire 192.0.2.0/24
prefix is conservatively excluded from lab allocations until a later Wiretap
profile is independently revalidated.

The validator also makes reverse SIP delivery an explicit topology contract.
The current labs use RFC 3581 rport over the transparent routed flow. A future
UDP expose/loopback path must explicitly declare the loopback-to-E2EE forwarding
shim instead of silently changing transport semantics.
"""

from __future__ import annotations

import argparse
import ipaddress
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Iterable

OBSERVED_WIRETAP_VERSION = "0.9.0"
OBSERVED_API_IPV4 = "192.0.2.2"
RESERVED_IPV4_PREFIX = "192.0.2.0/24"
TRANSPARENT_RPORT = "rfc3581-rport-over-transparent-flow"
UDP_EXPOSE_LOOPBACK = "udp-expose-loopback"


class TopologyError(ValueError):
    """Raised when a declared lab topology violates a Baudot guardrail."""


def _network(value: str, label: str) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise TopologyError(f"{label}: invalid network/address {value!r}") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise TopologyError(f"{label}: routed Wiretap preflight currently requires IPv4")
    return network


def validate_topology(
    *,
    underlay_addresses: Iterable[str],
    signaling_network: str,
    media_network: str,
    routes: str,
    response_routing: str,
    loopback_forwarding_shim: bool = False,
    reserved_ipv4_prefix: str = RESERVED_IPV4_PREFIX,
) -> dict[str, str]:
    """Validate topology semantics without touching host networking."""

    underlays = [_network(value, "underlay") for value in underlay_addresses]
    if len(underlays) < 2:
        raise TopologyError("underlay: at least two endpoint addresses are required")
    if len(set(underlays)) != 1:
        raise TopologyError("underlay: endpoint addresses must resolve to one shared network")

    underlay = underlays[0]
    signaling = _network(signaling_network, "signaling")
    media = _network(media_network, "media")
    reserved = _network(reserved_ipv4_prefix, "wiretap-reserved")

    declared = {
        "underlay": underlay,
        "signaling": signaling,
        "media": media,
    }

    for label, network in declared.items():
        if network.overlaps(reserved):
            raise TopologyError(
                f"{label}: {network} overlaps Wiretap-reserved IPv4 prefix {reserved} "
                f"(observed API address {OBSERVED_API_IPV4})"
            )

    labels = list(declared)
    for index, left_label in enumerate(labels):
        for right_label in labels[index + 1 :]:
            left = declared[left_label]
            right = declared[right_label]
            if left.overlaps(right):
                raise TopologyError(
                    f"topology: {left_label} {left} overlaps {right_label} {right}"
                )

    route_values = [value.strip() for value in routes.split(",") if value.strip()]
    if not route_values:
        raise TopologyError("routes: at least the signaling network must be routed")
    route_networks = [_network(value, "route") for value in route_values]
    allowed_routes = {signaling, media}
    for route in route_networks:
        if route.overlaps(reserved):
            raise TopologyError(f"route: {route} overlaps Wiretap-reserved IPv4 prefix {reserved}")
        if route not in allowed_routes:
            raise TopologyError(
                f"route: {route} is not one of the declared signaling/media networks"
            )
    if signaling not in route_networks:
        raise TopologyError(f"routes: signaling network {signaling} is not routed")

    if response_routing == TRANSPARENT_RPORT:
        if loopback_forwarding_shim:
            raise TopologyError(
                "response-routing: loopback forwarding shim is incompatible with transparent rport mode"
            )
        shim_state = "not-required"
    elif response_routing == UDP_EXPOSE_LOOPBACK:
        if not loopback_forwarding_shim:
            raise TopologyError(
                "response-routing: udp-expose-loopback requires an explicit loopback-to-E2EE forwarding shim"
            )
        shim_state = "declared"
    else:
        raise TopologyError(f"response-routing: unsupported mode {response_routing!r}")

    return {
        "underlay.network": str(underlay),
        "signaling.network": str(signaling),
        "media.network": str(media),
        "wiretap.routes": ",".join(str(route) for route in route_networks),
        "wiretap.reservedIpv4Prefix": str(reserved),
        "wiretap.observedApiIpv4": OBSERVED_API_IPV4,
        "wiretap.reservedProfile": f"observed-v{OBSERVED_WIRETAP_VERSION}-conservative",
        "signaling.responseRouting": response_routing,
        "signaling.loopbackForwardingShim": shim_state,
    }


def _runtime_checks(
    *,
    namespaces: list[str],
    host_links: list[str],
    required_bins: list[str],
    response_routing: str,
    wiretap_bin: str,
    evidence_root: Path,
) -> tuple[list[str], dict[str, str]]:
    errors: list[str] = []
    facts: dict[str, str] = {}

    binaries = list(dict.fromkeys([wiretap_bin, *required_bins]))
    if response_routing == UDP_EXPOSE_LOOPBACK and "socat" not in binaries:
        binaries.append("socat")
    for binary in binaries:
        present = shutil.which(binary) is not None
        facts[f"binary.{Path(binary).name}.present"] = str(present).lower()
        if not present:
            errors.append(f"binary: required executable {binary!r} is not available")

    wiretap_path = shutil.which(wiretap_bin)
    if wiretap_path:
        try:
            completed = subprocess.run(
                [wiretap_path, "--version"],
                check=True,
                capture_output=True,
                text=True,
            )
            facts["wiretap.version"] = completed.stdout.splitlines()[0].strip() or "unknown"
        except (subprocess.CalledProcessError, IndexError):
            errors.append("wiretap: unable to read version from configured executable")
            facts["wiretap.version"] = "unknown"
    else:
        facts["wiretap.version"] = "unavailable"

    try:
        evidence_root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".baudot-preflight-", dir=evidence_root) as probe:
            probe.write(b"ok")
            probe.flush()
        facts["evidence.root.writable"] = "true"
    except OSError as exc:
        facts["evidence.root.writable"] = "false"
        errors.append(f"evidence: root {evidence_root} is not writable ({exc})")

    if namespaces or host_links:
        if shutil.which("ip") is None:
            errors.append("topology: ip executable is required to verify host-state cleanliness")
        else:
            try:
                completed = subprocess.run(
                    ["ip", "netns", "list"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                existing_namespaces = {
                    line.split()[0]
                    for line in completed.stdout.splitlines()
                    if line.strip()
                }
                for namespace in namespaces:
                    clean = namespace not in existing_namespaces
                    facts[f"namespace.{namespace}.clean"] = str(clean).lower()
                    if not clean:
                        errors.append(
                            f"namespace: {namespace!r} already exists; refusing to reuse stale topology"
                        )

                completed = subprocess.run(
                    ["ip", "-o", "link", "show"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                existing_links: set[str] = set()
                for line in completed.stdout.splitlines():
                    parts = line.split(": ", 2)
                    if len(parts) < 2:
                        continue
                    existing_links.add(parts[1].split("@", 1)[0])
                for link in host_links:
                    clean = link not in existing_links
                    facts[f"hostLink.{link}.clean"] = str(clean).lower()
                    if not clean:
                        errors.append(
                            f"host-link: {link!r} already exists; refusing to reuse stale topology"
                        )
            except subprocess.CalledProcessError as exc:
                errors.append(f"topology: unable to inspect host network state (exit {exc.returncode})")

    return errors, facts


def _write_properties(path: Path, facts: dict[str, str], errors: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = dict(facts)
    values["preflight.status"] = "PASS" if not errors else "FAIL"
    values["preflight.errorCount"] = str(len(errors))
    for index, error in enumerate(errors, start=1):
        values[f"preflight.error.{index}"] = error.replace("\n", " ")
    path.write_text(
        "".join(f"{key}={values[key]}\n" for key in sorted(values)),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--underlay-address", action="append", required=True)
    parser.add_argument("--signaling-network", required=True)
    parser.add_argument("--media-network", required=True)
    parser.add_argument("--routes", required=True)
    parser.add_argument("--response-routing", required=True)
    parser.add_argument("--loopback-forwarding-shim", action="store_true")
    parser.add_argument("--namespace", action="append", default=[])
    parser.add_argument("--host-link", action="append", default=[])
    parser.add_argument("--require-bin", action="append", default=[])
    parser.add_argument("--wiretap-bin", default="wiretap")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    facts: dict[str, str] = {
        "preflight.claimBoundary": (
            "reserved-ipv4 profile derives from Baudot observation of Wiretap v0.9.0; "
            "no SIP/RTP/RFC4103 conformance claim"
        ),
    }
    errors: list[str] = []

    try:
        facts.update(
            validate_topology(
                underlay_addresses=args.underlay_address,
                signaling_network=args.signaling_network,
                media_network=args.media_network,
                routes=args.routes,
                response_routing=args.response_routing,
                loopback_forwarding_shim=args.loopback_forwarding_shim,
            )
        )
    except TopologyError as exc:
        errors.append(str(exc))

    runtime_errors, runtime_facts = _runtime_checks(
        namespaces=args.namespace,
        host_links=args.host_link,
        required_bins=args.require_bin,
        response_routing=args.response_routing,
        wiretap_bin=args.wiretap_bin,
        evidence_root=args.evidence_root,
    )
    errors.extend(runtime_errors)
    facts.update(runtime_facts)
    _write_properties(args.output, facts, errors)

    if errors:
        for error in errors:
            print(f"preflight: {error}", file=sys.stderr)
        print(f"preflight evidence: {args.output}", file=sys.stderr)
        return 2

    print("✓ Wiretap topology preflight: reserved-prefix, route, reverse-path, host-state, and evidence guards passed")
    print(f"preflight evidence: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
