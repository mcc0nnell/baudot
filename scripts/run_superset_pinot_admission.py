#!/usr/bin/env python3
"""Admit a synthetic Superset -> Pinot connection through Superset's REST API."""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONNECTION = json.loads((ROOT / "interop/superset/pinot/database-connection-v1.json").read_text())
PROFILE = json.loads((ROOT / "testkit/business/superset-pinot-cdr-v1.json").read_text())


def digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class SupersetClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        self.token: str | None = None
        self.csrf: str | None = None

    def request(self, method: str, path: str, payload: dict | None = None, auth: bool = True):
        headers = {"Accept": "application/json"}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if method != "GET" and self.csrf:
            headers["X-CSRFToken"] = self.csrf
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        with self.opener.open(request, timeout=60) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body) if body.strip() else {}
            return response.status, parsed

    def wait_health(self, timeout_seconds: int = 300) -> dict:
        deadline = time.monotonic() + timeout_seconds
        attempts = 0
        while time.monotonic() < deadline:
            attempts += 1
            try:
                with self.opener.open(self.base_url + "/health", timeout=10) as response:
                    body = response.read().decode("utf-8").strip()
                    if response.status == 200 and body == "OK":
                        return {"attempts": attempts, "body": body}
            except urllib.error.URLError:
                pass
            time.sleep(2)
        raise SystemExit("Superset health check timed out")

    def login(self, username: str, password: str) -> None:
        status, payload = self.request(
            "POST",
            "/api/v1/security/login",
            {"username": username, "password": password, "provider": "db", "refresh": True},
            auth=False,
        )
        if status != 200 or not payload.get("access_token"):
            raise RuntimeError(f"Superset login failed: {payload}")
        self.token = payload["access_token"]

        status, csrf = self.request("GET", "/api/v1/security/csrf_token/")
        if status != 200 or not csrf.get("result"):
            raise RuntimeError(f"Superset CSRF token failed: {csrf}")
        self.csrf = csrf["result"]


def extract_database_id(payload: dict) -> int:
    candidates = [payload.get("id")]
    result = payload.get("result")
    if isinstance(result, dict):
        candidates.extend([result.get("id"), result.get("pk")])
    for candidate in candidates:
        if isinstance(candidate, int):
            return candidate
    raise RuntimeError(f"database create response missing integer id: {payload}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8088")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--out", default="target/superset-pinot/admission.json")
    args = parser.parse_args()

    client = SupersetClient(args.base_url)
    health = client.wait_health()
    client.login(args.username, args.password)

    test_payload = {
        "database_name": CONNECTION["database_name"],
        "sqlalchemy_uri": CONNECTION["sqlalchemy_uri"],
    }
    test_status, test_response = client.request("POST", "/api/v1/database/test_connection/", test_payload)
    if test_status not in (200, 201):
        raise RuntimeError(f"connection test failed: {test_response}")

    create_status, create_response = client.request("POST", "/api/v1/database/", CONNECTION)
    if create_status not in (200, 201):
        raise RuntimeError(f"database create failed: {create_response}")
    database_id = extract_database_id(create_response)

    table_name = PROFILE["dataset"]["tableName"]
    encoded = urllib.parse.quote(table_name, safe="")
    select_status, select_response = client.request(
        "GET",
        f"/api/v1/database/{database_id}/select_star/{encoded}/",
    )
    if select_status != 200:
        raise RuntimeError(f"select_star failed: {select_response}")

    forbidden = {field.lower() for field in PROFILE["dataset"]["forbiddenColumns"]}
    serialized = json.dumps(select_response, sort_keys=True).lower()
    leaked = sorted(field for field in forbidden if field in serialized)
    if leaked:
        raise AssertionError(f"forbidden fields surfaced through Superset select_star: {leaked}")

    evidence = {
        "schema": "baudot.superset-pinot-admission-evidence@1",
        "supersetVersion": PROFILE["stack"]["supersetVersion"],
        "pinotVersion": PROFILE["stack"]["pinotVersion"],
        "pinotdbVersion": "9.1.2",
        "health": health,
        "connectionTestStatus": test_status,
        "connectionTestSha256": digest(test_response),
        "databaseCreateStatus": create_status,
        "databaseId": database_id,
        "selectStarStatus": select_status,
        "selectStarSha256": digest(select_response),
        "dataset": table_name,
        "forbiddenFieldLeak": False,
        "authority": {
            "callTruth": False,
            "compensability": False,
            "claimApproval": False,
            "paymentAuthorization": False,
            "accessibilityVerdict": False,
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()
