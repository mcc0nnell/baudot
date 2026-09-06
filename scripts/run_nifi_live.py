#!/usr/bin/env python3
"""Build and exercise the bounded Apache NiFi 2.11 bulk-ingest lane."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "testkit/nifi/live"
CLIENT_ID = "baudot-nifi-live"
REQUIRED_EVIDENCE = [
    "sourceSystem",
    "sourceObjectId",
    "receivedAt",
    "contentSha256",
    "flowId",
    "correlationId",
]


class NiFiClient:
    def __init__(self, base: str, username: str, password: str):
        self.base = base.rstrip("/") + "/nifi-api"
        self.username = username
        self.password = password
        self.ctx = ssl._create_unverified_context()
        self.token = self._login()

    def _login(self) -> str:
        data = urllib.parse.urlencode(
            {"username": self.username, "password": self.password}
        ).encode()
        req = urllib.request.Request(
            self.base + "/access/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, context=self.ctx, timeout=30) as response:
            token = response.read().decode().strip()
        if not token:
            raise RuntimeError("NiFi returned an empty access token")
        return token

    def request(self, path: str, *, method: str = "GET", payload=None):
        body = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self.base + path, data=body, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=45) as response:
                raw = response.read()
                return response.status, json.loads(raw.decode() or "{}")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")[:4000]
            raise RuntimeError(
                f"NiFi API {method} {path} failed: HTTP {exc.code}: {text}"
            ) from exc


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_data(root: Path) -> dict[str, dict[str, object]]:
    if root.exists():
        shutil.rmtree(root)
    for path in (
        root / "input/provider",
        root / "input/cdr",
        root / "accepted/provider",
        root / "accepted/cdr",
        root / "quarantine/provider",
        root / "quarantine/cdr",
    ):
        path.mkdir(parents=True, exist_ok=True)

    mapping = {
        "provider-valid.csv": ("provider", "accepted/provider"),
        "provider-invalid.csv": ("provider", "quarantine/provider"),
        "cdr-valid.json": ("cdr", "accepted/cdr"),
        "cdr-invalid.json": ("cdr", "quarantine/cdr"),
    }
    expected: dict[str, dict[str, object]] = {}
    for filename, (kind, destination) in mapping.items():
        source = FIXTURES / filename
        target = root / "input" / kind / filename
        shutil.copy2(source, target)
        expected[filename] = {
            "kind": kind,
            "destination": destination,
            "sha256": sha256(source),
            "bytes": source.read_bytes(),
        }
    return expected


def processor_bundle_map(client: NiFiClient) -> dict[str, dict]:
    _, payload = client.request("/flow/processor-types")
    result = {}
    for entry in payload.get("processorTypes", []):
        result[entry["type"]] = entry["bundle"]
    return result


def create_group(client: NiFiClient, name: str) -> dict:
    _, entity = client.request(
        "/process-groups/root/process-groups",
        method="POST",
        payload={
            "revision": {"version": 0, "clientId": CLIENT_ID},
            "disconnectedNodeAcknowledged": False,
            "component": {"position": {"x": 0, "y": 0}, "name": name},
        },
    )
    return entity


def create_processor(
    client: NiFiClient,
    group_id: str,
    bundles: dict[str, dict],
    processor_type: str,
    name: str,
    x: int,
    y: int,
    *,
    properties: dict[str, str],
    auto_terminate: list[str],
) -> dict:
    if processor_type not in bundles:
        raise RuntimeError(f"NiFi runtime did not advertise processor {processor_type}")
    _, entity = client.request(
        f"/process-groups/{group_id}/processors",
        method="POST",
        payload={
            "revision": {"version": 0, "clientId": CLIENT_ID},
            "disconnectedNodeAcknowledged": False,
            "component": {
                "position": {"x": x, "y": y},
                "type": processor_type,
                "bundle": bundles[processor_type],
            },
        },
    )

    revision = entity["revision"]
    processor_id = entity["id"]
    _, configured = client.request(
        f"/processors/{processor_id}",
        method="PUT",
        payload={
            "revision": revision,
            "disconnectedNodeAcknowledged": False,
            "component": {
                "id": processor_id,
                "name": name,
                "config": {
                    "penaltyDuration": "30 sec",
                    "yieldDuration": "1 sec",
                    "bulletinLevel": "WARN",
                    "schedulingStrategy": "TIMER_DRIVEN",
                    "schedulingPeriod": "500 ms",
                    "executionNode": "ALL",
                    "concurrentlySchedulableTaskCount": 1,
                    "autoTerminatedRelationships": auto_terminate,
                    "retriedRelationships": [],
                    "comments": "Baudot bounded synthetic NiFi qualification lane",
                    "properties": properties,
                    "sensitiveDynamicPropertyNames": [],
                },
            },
        },
    )
    return configured


def connect(
    client: NiFiClient,
    group_id: str,
    source: dict,
    destination: dict,
    relationship: str,
    name: str,
) -> dict:
    _, entity = client.request(
        f"/process-groups/{group_id}/connections",
        method="POST",
        payload={
            "revision": {"version": 0, "clientId": CLIENT_ID},
            "disconnectedNodeAcknowledged": False,
            "component": {
                "name": name,
                "source": {"id": source["id"], "groupId": group_id, "type": "PROCESSOR"},
                "destination": {
                    "id": destination["id"],
                    "groupId": group_id,
                    "type": "PROCESSOR",
                },
                "selectedRelationships": [relationship],
                "backPressureObjectThreshold": 10000,
                "backPressureDataSizeThreshold": "1 GB",
                "flowFileExpiration": "0 sec",
                "loadBalanceStrategy": "DO_NOT_LOAD_BALANCE",
                "loadBalancePartitionAttribute": "",
                "loadBalanceCompression": "DO_NOT_COMPRESS",
                "prioritizers": [],
            },
        },
    )
    return entity


def evidence_properties(flow_id: str, source_system: str) -> dict[str, str]:
    return {
        "sourceSystem": source_system,
        "sourceObjectId": "${filename}",
        "receivedAt": "${now():toNumber()}",
        "contentSha256": "${'content_SHA-256'}",
        "flowId": flow_id,
        "correlationId": "${uuid}",
    }


def build_lane(client: NiFiClient, group_id: str, bundles: dict[str, dict], *, kind: str, y: int) -> dict:
    standard = "org.apache.nifi.processors.standard."
    update_type = "org.apache.nifi.processors.attributes.UpdateAttribute"
    input_dir = f"/data/input/{kind}"
    accepted_dir = f"/data/accepted/{kind}"
    quarantine_dir = f"/data/quarantine/{kind}"

    get_file = create_processor(
        client,
        group_id,
        bundles,
        standard + "GetFile",
        f"{kind}-GetFile",
        0,
        y,
        properties={
            "Input Directory": input_dir,
            "Recurse Subdirectories": "false",
            "Keep Source File": "false",
            "Polling Interval": "250 ms",
            "Batch Size": "10",
        },
        auto_terminate=[],
    )
    hash_content = create_processor(
        client,
        group_id,
        bundles,
        standard + "CryptographicHashContent",
        f"{kind}-SHA256",
        250,
        y,
        properties={"Hash Algorithm": "SHA-256", "Fail on empty": "false"},
        auto_terminate=[],
    )
    update = create_processor(
        client,
        group_id,
        bundles,
        update_type,
        f"{kind}-EvidenceAttributes",
        500,
        y,
        properties=evidence_properties(
            "provider-roster-import" if kind == "provider" else "cdr-backfill-import",
            "synthetic-provider-batch" if kind == "provider" else "synthetic-legacy-cdr",
        ),
        auto_terminate=[],
    )
    logger = create_processor(
        client,
        group_id,
        bundles,
        standard + "LogAttribute",
        f"{kind}-EvidenceLog",
        750,
        y,
        properties={
            "Log Level": "info",
            "Log Payload": "false",
            "Log FlowFile Properties": "false",
            "Output Format": "Line per Attribute",
            "Attributes to Log": ",".join(REQUIRED_EVIDENCE),
            "Log Prefix": f"BAUDOT_NIFI_{kind.upper()}_EVIDENCE",
        },
        auto_terminate=[],
    )

    if kind == "provider":
        validator = create_processor(
            client,
            group_id,
            bundles,
            standard + "ValidateCsv",
            "provider-ValidateCsv",
            1000,
            y,
            properties={
                "Schema": "StrNotNullOrEmpty,StrNotNullOrEmpty,StrNotNullOrEmpty",
                "Header": "true",
                "Validation Strategy": "FlowFile validation",
            },
            auto_terminate=[],
        )
    else:
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["cdrId", "providerId", "durationSeconds"],
            "properties": {
                "cdrId": {"type": "string", "minLength": 1},
                "providerId": {"type": "string", "minLength": 1},
                "durationSeconds": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": False,
        }
        validator = create_processor(
            client,
            group_id,
            bundles,
            standard + "ValidateJson",
            "cdr-ValidateJson",
            1000,
            y,
            properties={
                "Schema Access Strategy": "SCHEMA_CONTENT_PROPERTY",
                "JSON Schema": json.dumps(schema, separators=(",", ":")),
                "Input Format": "FLOW_FILE",
            },
            auto_terminate=[],
        )

    accepted = create_processor(
        client,
        group_id,
        bundles,
        standard + "PutFile",
        f"{kind}-AcceptedStaging",
        1250,
        y - 100,
        properties={
            "Directory": accepted_dir,
            "Conflict Resolution Strategy": "replace",
            "Create Missing Directories": "true",
        },
        auto_terminate=["success", "failure"],
    )
    quarantine = create_processor(
        client,
        group_id,
        bundles,
        standard + "PutFile",
        f"{kind}-Quarantine",
        1250,
        y + 100,
        properties={
            "Directory": quarantine_dir,
            "Conflict Resolution Strategy": "replace",
            "Create Missing Directories": "true",
        },
        auto_terminate=["success", "failure"],
    )

    connect(client, group_id, get_file, hash_content, "success", f"{kind}-read-to-hash")
    connect(client, group_id, hash_content, update, "success", f"{kind}-hash-to-evidence")
    connect(client, group_id, hash_content, quarantine, "failure", f"{kind}-hash-failure-quarantine")
    connect(client, group_id, update, logger, "success", f"{kind}-evidence-to-log")
    connect(client, group_id, logger, validator, "success", f"{kind}-log-to-validation")
    connect(client, group_id, validator, accepted, "valid", f"{kind}-valid-to-staging")
    connect(client, group_id, validator, quarantine, "invalid", f"{kind}-invalid-to-quarantine")

    return {
        "getFile": get_file["id"],
        "hash": hash_content["id"],
        "evidence": update["id"],
        "log": logger["id"],
        "validator": validator["id"],
        "accepted": accepted["id"],
        "quarantine": quarantine["id"],
    }


def wait_for_outputs(data_root: Path, expected: dict[str, dict[str, object]], timeout: int = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        ready = True
        for filename, item in expected.items():
            if not (data_root / str(item["destination"]) / filename).exists():
                ready = False
                break
        if ready:
            return
        time.sleep(1)
    present = [str(p.relative_to(data_root)) for p in data_root.rglob("*") if p.is_file()]
    raise RuntimeError(f"NiFi did not stage all expected outputs; present={present}")


def validate_outputs(data_root: Path, expected: dict[str, dict[str, object]]) -> list[dict]:
    results = []
    for filename, item in expected.items():
        out = data_root / str(item["destination"]) / filename
        actual_bytes = out.read_bytes()
        if actual_bytes != item["bytes"]:
            raise RuntimeError(f"NiFi changed staged bytes for {filename}")
        actual_sha = hashlib.sha256(actual_bytes).hexdigest()
        if actual_sha != item["sha256"]:
            raise RuntimeError(f"NiFi staging hash mismatch for {filename}")
        results.append(
            {
                "file": filename,
                "destination": str(item["destination"]),
                "sha256": actual_sha,
                "bytesPreserved": True,
            }
        )
    if (data_root / "accepted/provider/provider-invalid.csv").exists():
        raise RuntimeError("malformed provider roster reached accepted staging")
    if (data_root / "accepted/cdr/cdr-invalid.json").exists():
        raise RuntimeError("malformed CDR reached accepted staging")
    if (data_root / "quarantine/provider/provider-valid.csv").exists():
        raise RuntimeError("valid provider roster reached quarantine")
    if (data_root / "quarantine/cdr/cdr-valid.json").exists():
        raise RuntimeError("valid CDR reached quarantine")
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="https://127.0.0.1:8443")
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--data-root", default="target/nifi-live")
    parser.add_argument("--out", default="target/nifi-live/evidence.json")
    args = parser.parse_args()

    data_root = Path(args.data_root).resolve()
    expected = prepare_data(data_root)
    client = NiFiClient(args.base, args.user, args.password)
    bundles = processor_bundle_map(client)
    group = create_group(client, "Baudot Synthetic Bulk Ingest")
    group_id = group["id"]

    provider = build_lane(client, group_id, bundles, kind="provider", y=200)
    cdr = build_lane(client, group_id, bundles, kind="cdr", y=600)

    client.request(
        f"/flow/process-groups/{group_id}",
        method="PUT",
        payload={
            "id": group_id,
            "disconnectedNodeAcknowledged": False,
            "state": "RUNNING",
        },
    )

    wait_for_outputs(data_root, expected)
    files = validate_outputs(data_root, expected)

    client.request(
        f"/flow/process-groups/{group_id}",
        method="PUT",
        payload={
            "id": group_id,
            "disconnectedNodeAcknowledged": False,
            "state": "STOPPED",
        },
    )

    evidence = {
        "schema": "baudot.nifi-live-evidence@1",
        "nifiVersion": "2.11.0",
        "processGroupId": group_id,
        "flows": {"provider": provider, "cdr": cdr},
        "requiredEvidenceAttributes": REQUIRED_EVIDENCE,
        "stagedFiles": files,
        "accepted": ["provider-valid.csv", "cdr-valid.json"],
        "quarantined": ["provider-invalid.csv", "cdr-invalid.json"],
        "authority": {
            "ingestionCompleteIsBusinessApproval": False,
            "schemaValidIsSourceAuthoritative": False,
            "deliveryToKafkaIsCallTruth": False,
            "deliveryToFineractStagingIsLedgerPosting": False,
            "deliveryToOFBizStagingIsEligibility": False,
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print("validated live NiFi bulk ingest: accepted=2 quarantined=2")


if __name__ == "__main__":
    main()
