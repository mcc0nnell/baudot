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
        self.ctx = ssl._create_unverified_context()
        self.token = self._login(username, password)

    def _login(self, username: str, password: str) -> str:
        data = urllib.parse.urlencode({"username": username, "password": password}).encode()
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
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=45) as response:
                raw = response.read()
                return response.status, json.loads(raw.decode() or "{}")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")[:4000]
            raise RuntimeError(f"NiFi API {method} {path} failed: HTTP {exc.code}: {text}") from exc


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_data(root: Path) -> dict[str, dict[str, object]]:
    if root.exists():
        shutil.rmtree(root)
    for relative in (
        "input/provider", "input/cdr", "accepted/provider", "accepted/cdr",
        "quarantine/provider", "quarantine/cdr",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)

    mapping = {
        "provider-valid.csv": ("provider", "accepted/provider"),
        "provider-invalid.csv": ("provider", "quarantine/provider"),
        "cdr-valid.json": ("cdr", "accepted/cdr"),
        "cdr-invalid.json": ("cdr", "quarantine/cdr"),
    }
    expected: dict[str, dict[str, object]] = {}
    for filename, (kind, destination) in mapping.items():
        source = FIXTURES / filename
        shutil.copy2(source, root / "input" / kind / filename)
        expected[filename] = {
            "destination": destination,
            "sha256": sha256(source),
            "bytes": source.read_bytes(),
        }
    return expected


def processor_bundles(client: NiFiClient) -> dict[str, dict]:
    _, payload = client.request("/flow/processor-types")
    return {entry["type"]: entry["bundle"] for entry in payload.get("processorTypes", [])}


def create_group(client: NiFiClient) -> dict:
    _, entity = client.request(
        "/process-groups/root/process-groups",
        method="POST",
        payload={
            "revision": {"version": 0, "clientId": CLIENT_ID},
            "disconnectedNodeAcknowledged": False,
            "component": {"position": {"x": 0, "y": 0}, "name": "Baudot Synthetic Bulk Ingest"},
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
    bundle = bundles.get(processor_type)
    if bundle is None:
        raise RuntimeError(f"NiFi runtime did not advertise processor {processor_type}")

    _, created = client.request(
        f"/process-groups/{group_id}/processors",
        method="POST",
        payload={
            "revision": {"version": 0, "clientId": CLIENT_ID},
            "disconnectedNodeAcknowledged": False,
            "component": {
                "position": {"x": x, "y": y},
                "type": processor_type,
                "bundle": bundle,
            },
        },
    )
    processor_id = created["id"]
    _, configured = client.request(
        f"/processors/{processor_id}",
        method="PUT",
        payload={
            "revision": created["revision"],
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


def connect(client: NiFiClient, group_id: str, source: dict, destination: dict, relationship: str, name: str) -> None:
    client.request(
        f"/process-groups/{group_id}/connections",
        method="POST",
        payload={
            "revision": {"version": 0, "clientId": CLIENT_ID},
            "disconnectedNodeAcknowledged": False,
            "component": {
                "name": name,
                "source": {"id": source["id"], "groupId": group_id, "type": "PROCESSOR"},
                "destination": {"id": destination["id"], "groupId": group_id, "type": "PROCESSOR"},
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


def evidence_properties(kind: str) -> dict[str, str]:
    return {
        "sourceSystem": "synthetic-provider-batch" if kind == "provider" else "synthetic-legacy-cdr",
        "sourceObjectId": "${filename}",
        "receivedAt": "${now():toNumber()}",
        "contentSha256": "${'content_SHA-256'}",
        "flowId": "provider-roster-import" if kind == "provider" else "cdr-backfill-import",
        "correlationId": "${uuid}",
    }


def build_lane(client: NiFiClient, group_id: str, bundles: dict[str, dict], *, kind: str, y: int) -> dict:
    standard = "org.apache.nifi.processors.standard."
    update_type = "org.apache.nifi.processors.attributes.UpdateAttribute"

    get_file = create_processor(
        client, group_id, bundles, standard + "GetFile", f"{kind}-GetFile", 0, y,
        properties={
            "Input Directory": f"/data/input/{kind}",
            "Recurse Subdirectories": "false",
            "Keep Source File": "false",
            "Polling Interval": "250 ms",
            "Batch Size": "10",
        },
        auto_terminate=[],
    )
    hash_content = create_processor(
        client, group_id, bundles, standard + "CryptographicHashContent", f"{kind}-SHA256", 250, y,
        properties={"Hash Algorithm": "SHA-256", "Fail When Content Empty": "false"},
        auto_terminate=[],
    )
    update = create_processor(
        client, group_id, bundles, update_type, f"{kind}-EvidenceAttributes", 500, y,
        properties=evidence_properties(kind), auto_terminate=[],
    )
    logger = create_processor(
        client, group_id, bundles, standard + "LogAttribute", f"{kind}-EvidenceLog", 750, y,
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
            client, group_id, bundles, standard + "ValidateCsv", "provider-ValidateCsv", 1000, y,
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
            client, group_id, bundles, standard + "ValidateJson", "cdr-ValidateJson", 1000, y,
            properties={
                "Schema Access Strategy": "SCHEMA_CONTENT_PROPERTY",
                "JSON Schema": json.dumps(schema, separators=(",", ":")),
                "Input Format": "FLOW_FILE",
            },
            auto_terminate=[],
        )

    accepted = create_processor(
        client, group_id, bundles, standard + "PutFile", f"{kind}-AcceptedStaging", 1250, y - 100,
        properties={
            "Directory": f"/data/accepted/{kind}",
            "Conflict Resolution Strategy": "replace",
            "Create Missing Directories": "true",
        },
        auto_terminate=["success", "failure"],
    )
    quarantine = create_processor(
        client, group_id, bundles, standard + "PutFile", f"{kind}-Quarantine", 1250, y + 100,
        properties={
            "Directory": f"/data/quarantine/{kind}",
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
        "getFile": get_file["id"], "hash": hash_content["id"], "evidence": update["id"],
        "log": logger["id"], "validator": validator["id"], "accepted": accepted["id"],
        "quarantine": quarantine["id"],
    }


def set_group_state(client: NiFiClient, group_id: str, state: str) -> None:
    client.request(
        f"/flow/process-groups/{group_id}",
        method="PUT",
        payload={"id": group_id, "disconnectedNodeAcknowledged": False, "state": state},
    )


def wait_for_outputs(data_root: Path, expected: dict[str, dict[str, object]], timeout: int = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if all((data_root / str(item["destination"]) / filename).exists() for filename, item in expected.items()):
            return
        time.sleep(1)
    present = sorted(str(p.relative_to(data_root)) for p in data_root.rglob("*") if p.is_file())
    raise RuntimeError(f"NiFi did not stage all expected outputs; present={present}")


def validate_outputs(data_root: Path, expected: dict[str, dict[str, object]]) -> list[dict]:
    results = []
    for filename, item in expected.items():
        out = data_root / str(item["destination"]) / filename
        actual = out.read_bytes()
        if actual != item["bytes"]:
            raise RuntimeError(f"NiFi changed staged bytes for {filename}")
        digest = hashlib.sha256(actual).hexdigest()
        if digest != item["sha256"]:
            raise RuntimeError(f"NiFi staging hash mismatch for {filename}")
        results.append({"file": filename, "destination": str(item["destination"]), "sha256": digest, "bytesPreserved": True})

    forbidden = [
        data_root / "accepted/provider/provider-invalid.csv",
        data_root / "accepted/cdr/cdr-invalid.json",
        data_root / "quarantine/provider/provider-valid.csv",
        data_root / "quarantine/cdr/cdr-valid.json",
    ]
    if any(path.exists() for path in forbidden):
        raise RuntimeError("NiFi staging boundary was crossed by a misclassified fixture")
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
    bundles = processor_bundles(client)
    group = create_group(client)
    group_id = group["id"]

    flows = {
        "provider": build_lane(client, group_id, bundles, kind="provider", y=200),
        "cdr": build_lane(client, group_id, bundles, kind="cdr", y=600),
    }

    set_group_state(client, group_id, "RUNNING")
    try:
        wait_for_outputs(data_root, expected)
        files = validate_outputs(data_root, expected)
    finally:
        set_group_state(client, group_id, "STOPPED")

    evidence = {
        "schema": "baudot.nifi-live-evidence@1",
        "nifiVersion": "2.11.0",
        "processGroupId": group_id,
        "flows": flows,
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
