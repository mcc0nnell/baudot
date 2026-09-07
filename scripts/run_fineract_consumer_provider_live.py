#!/usr/bin/env python3
"""Exercise a pinned Fineract Consumer-Facing provider read against live Fineract.

The probe proves a narrow boundary only:

* an authenticated synthetic provider can read its own savings list through the BFF;
* the same provider is denied when requesting another provider's savings account; and
* after priming the ownership cache, that denied request creates no downstream
  request through the recording Fineract proxy.

It does not derive TRS program authority from Consumer authentication, ABAC, or
Fineract state.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.cookiejar
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_DIR = Path("/tmp/baudot-fineract-consumer-provider-live")
UPSTREAM_COMMIT = "58eacf7338126aa0de2b2a2ef70319f45d403fbf"
BFF_BASE = "http://localhost:8080/api/v1"
MAILPIT_BASE = "http://localhost:8025/api/v1"
FINERACT_BASE = "http://localhost:8888/fineract-provider/api/v1"
PROVIDER_EMAIL = "demo3@example.com"
PROVIDER_PASSWORD = "DemoPassw0rd!23"
DEVICE_FINGERPRINT = "baudot-provider-live-probe"
CROSS_PROVIDER_EXTERNAL_ID = "demo-client-4"
TENANT = "default"
FINERACT_AUTH = base64.b64encode(b"mifos:password").decode("ascii")


def require(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def run(cmd: list[str], *, cwd: Path | None = None, capture: bool = False) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd))
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=True,
        text=True,
        capture_output=capture,
    )


def http(
    method: str,
    url: str,
    *,
    data: Any | None = None,
    headers: dict[str, str] | None = None,
    opener: urllib.request.OpenerDirector | None = None,
) -> tuple[int, Any, bytes]:
    payload = None if data is None else json.dumps(data).encode("utf-8")
    request_headers = dict(headers or {})
    if payload is not None:
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=payload, method=method, headers=request_headers)
    client = opener or urllib.request.build_opener()
    try:
        with client.open(request, timeout=30) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def json_body(body: bytes) -> Any:
    return json.loads(body.decode("utf-8")) if body else None


def mailpit_clear(email: str) -> None:
    query = urllib.parse.quote(f"to:{email}", safe="")
    status, _, body = http("GET", f"{MAILPIT_BASE}/search?query={query}&limit=200")
    require("Mailpit search is available", status == 200)
    ids = [row["ID"] for row in json_body(body).get("messages", [])]
    if ids:
        status, _, _ = http("DELETE", f"{MAILPIT_BASE}/messages", data={"IDs": ids})
        require("stale provider OTP messages cleared", 200 <= status < 300)


def mailpit_latest_code(email: str) -> str:
    query = urllib.parse.quote(f"to:{email}", safe="")
    for _ in range(30):
        status, _, body = http("GET", f"{MAILPIT_BASE}/search?query={query}&limit=1")
        if status == 200:
            messages = json_body(body).get("messages", [])
            if messages:
                message_id = messages[0]["ID"]
                detail_status, _, detail_body = http("GET", f"{MAILPIT_BASE}/message/{message_id}")
                if detail_status == 200:
                    text = json_body(detail_body).get("Text", "")
                    match = re.search(r"verification code is:\s*([A-Za-z0-9]{4,})", text)
                    if match:
                        return match.group(1)
        time.sleep(1)
    raise AssertionError(f"no OTP email arrived for {email}")


def login_provider(opener: urllib.request.OpenerDirector) -> dict[str, Any]:
    mailpit_clear(PROVIDER_EMAIL)
    headers = {"X-Device-Fingerprint": DEVICE_FINGERPRINT}
    login_status, _, login_body = http(
        "POST",
        f"{BFF_BASE}/authentication/login",
        data={"email": PROVIDER_EMAIL, "password": PROVIDER_PASSWORD},
        headers=headers,
        opener=opener,
    )
    require("provider password step succeeds", login_status == 200)
    challenge = json_body(login_body).get("challengeToken")
    require("provider login returns a challenge token", bool(challenge))

    otp = mailpit_latest_code(PROVIDER_EMAIL)
    two_factor_status, _, two_factor_body = http(
        "POST",
        f"{BFF_BASE}/authentication/2fa",
        data={"challengeToken": challenge, "token": otp},
        headers=headers,
        opener=opener,
    )
    require("provider 2FA establishes a session", two_factor_status == 200)
    return {
        "loginStatus": login_status,
        "twoFactorStatus": two_factor_status,
        "twoFactorResponsePresent": bool(two_factor_body),
    }


def fineract_get(path: str) -> Any:
    status, _, body = http(
        "GET",
        f"{FINERACT_BASE}{path}",
        headers={
            "Authorization": f"Basic {FINERACT_AUTH}",
            "Fineract-Platform-TenantId": TENANT,
        },
    )
    require(f"direct Fineract lookup {path} succeeds", status == 200)
    return json_body(body)


def cross_provider_savings_id() -> int:
    clients = fineract_get(f"/clients?externalId={urllib.parse.quote(CROSS_PROVIDER_EXTERNAL_ID)}")
    rows = clients.get("pageItems", [])
    require("cross-provider synthetic client exists", len(rows) == 1)
    client_id = rows[0]["id"]
    accounts = fineract_get(f"/clients/{client_id}/accounts")
    savings = accounts.get("savingsAccounts", [])
    require("cross-provider synthetic client has savings accounts", len(savings) > 0)
    return int(savings[0]["id"])


def proxy_logs() -> str:
    completed = subprocess.run(
        ["docker", "logs", "fineract-proxy"],
        text=True,
        capture_output=True,
        check=False,
    )
    return (completed.stdout or "") + (completed.stderr or "")


def request_lines(log_text: str) -> list[str]:
    return [line for line in log_text.splitlines() if '"GET ' in line or '"POST ' in line or '"PUT ' in line or '"DELETE ' in line]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare_upstream(upstream_root: Path) -> tuple[Path, Path]:
    consumer = upstream_root / "consumer"
    require("pinned Consumer checkout is present", (consumer / "compose.yaml").is_file())

    proxy_src = ROOT / "interop" / "fineract-consumer" / "live" / "fineract-proxy.conf"
    override_src = ROOT / "interop" / "fineract-consumer" / "live" / "compose.override.yaml"
    proxy_dst = consumer / "baudot-fineract-proxy.conf"
    override_dst = consumer / "baudot-provider-proxy.override.yaml"
    shutil.copy2(proxy_src, proxy_dst)
    shutil.copy2(override_src, override_dst)

    run(["./scripts/generate-dev-jwt-key.sh"], cwd=consumer)
    return consumer, override_dst


def compose_cmd(override: Path, *args: str) -> list[str]:
    return ["docker", "compose", "-f", "compose.yaml", "-f", override.name, *args]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    args = parser.parse_args()

    upstream_root = args.upstream_root.resolve()
    evidence_dir = args.evidence_dir.resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    consumer, override = prepare_upstream(upstream_root)

    seed_log = ""
    final_proxy_log = ""
    evidence: dict[str, Any] = {
        "schema": "baudot.fineract-consumer-provider-live-evidence@1",
        "upstream": {
            "repository": "apache/fineract-consumer-facing",
            "commit": UPSTREAM_COMMIT,
        },
        "claimBoundary": {
            "trsProgramAuthority": "NOT_DERIVED",
            "providerProductionEntitlementClaimed": False,
            "productionFineractSuitabilityClaimed": False,
            "regulatoryComplianceClaimed": False,
        },
    }

    try:
        run(compose_cmd(override, "up", "-d", "--build", "--wait"), cwd=consumer)
        seed = run(["./scripts/seed-demo.sh"], cwd=consumer, capture=True)
        seed_log = (seed.stdout or "") + (seed.stderr or "")
        (evidence_dir / "seed-demo.log").write_text(seed_log, encoding="utf-8")

        cookie_jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        auth_evidence = login_provider(opener)

        own_status, _, own_body = http("GET", f"{BFF_BASE}/savings", opener=opener)
        require("authenticated provider can list own savings through Consumer BFF", own_status == 200)
        own_accounts = json_body(own_body)
        require("provider savings response is a non-empty list", isinstance(own_accounts, list) and len(own_accounts) > 0)
        (evidence_dir / "provider-own-savings.json").write_bytes(own_body)

        cross_id = cross_provider_savings_id()
        protected_path = f"/fineract-provider/api/v1/savingsaccounts/{cross_id}"

        before_log = proxy_logs()
        before_lines = request_lines(before_log)
        before_protected_hits = sum(protected_path in line for line in before_lines)

        cross_status, _, cross_body = http("GET", f"{BFF_BASE}/savings/{cross_id}", opener=opener)
        require("cross-provider savings request is denied by Consumer BFF", cross_status == 403)
        (evidence_dir / "cross-provider-denial.json").write_bytes(cross_body)

        after_log = proxy_logs()
        after_lines = request_lines(after_log)
        after_protected_hits = sum(protected_path in line for line in after_lines)

        require(
            "cross-provider denial does not fetch the protected Fineract savings resource",
            after_protected_hits == before_protected_hits,
        )
        require(
            "primed ownership cache lets cross-provider denial occur with no downstream Fineract request",
            len(after_lines) == len(before_lines),
        )

        audit_status, _, audit_body = http("GET", f"{BFF_BASE}/audit/events", opener=opener)
        if audit_status == 200:
            (evidence_dir / "provider-audit-events.json").write_bytes(audit_body)

        final_proxy_log = after_log
        (evidence_dir / "fineract-proxy.log").write_text(final_proxy_log, encoding="utf-8")

        evidence.update(
            {
                "actor": {
                    "kind": "synthetic-provider-user",
                    "email": PROVIDER_EMAIL,
                    "deviceFingerprint": DEVICE_FINGERPRINT,
                },
                "authentication": auth_evidence,
                "ownRead": {
                    "endpoint": "GET /api/v1/savings",
                    "status": own_status,
                    "accountCount": len(own_accounts),
                    "responseSha256": sha256_bytes(own_body),
                },
                "crossProviderControl": {
                    "targetExternalId": CROSS_PROVIDER_EXTERNAL_ID,
                    "targetSavingsId": cross_id,
                    "endpoint": f"GET /api/v1/savings/{cross_id}",
                    "status": cross_status,
                    "protectedFineractPath": protected_path,
                    "protectedPathHitsBefore": before_protected_hits,
                    "protectedPathHitsAfter": after_protected_hits,
                    "proxyRequestLinesBefore": len(before_lines),
                    "proxyRequestLinesAfter": len(after_lines),
                    "downstreamRequestDelta": len(after_lines) - len(before_lines),
                    "denialResponseSha256": sha256_bytes(cross_body),
                },
                "auditQueryStatus": audit_status,
                "seedLogSha256": sha256_text(seed_log),
                "proxyLogSha256": sha256_text(final_proxy_log),
            }
        )
        write_json(evidence_dir / "evidence.json", evidence)
        print("Fineract Consumer provider live boundary: PASS")
    except Exception as exc:
        evidence["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        try:
            final_proxy_log = proxy_logs()
            (evidence_dir / "fineract-proxy.log").write_text(final_proxy_log, encoding="utf-8")
            evidence["proxyLogSha256"] = sha256_text(final_proxy_log)
        except Exception:
            pass
        write_json(evidence_dir / "evidence.json", evidence)
        raise
    finally:
        subprocess.run(compose_cmd(override, "down", "-v", "--remove-orphans"), cwd=consumer, check=False)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
