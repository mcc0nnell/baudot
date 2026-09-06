#!/usr/bin/env python3
"""Synthetic OIDC introspection and Ranger-deny upstream for the APISIX live lane."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

EVIDENCE_DIR = Path(os.environ.get("BAUDOT_EDGE_EVIDENCE", "/evidence"))
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


class IntrospectionHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/introspect":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        token = parse_qs(body).get("token", [""])[0]
        if token == "good-token":
            response = {
                "active": True,
                "sub": "synthetic-provider-operator",
                "scope": "openid itrs",
                "aud": "baudot-edge",
            }
        elif token == "missing-scope-token":
            response = {
                "active": True,
                "sub": "synthetic-provider-operator",
                "scope": "openid profile",
                "aud": "baudot-edge",
            }
        else:
            response = {"active": False}
        payload = json.dumps(response, sort_keys=True).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        return


class UpstreamHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        headers = {name.lower(): value for name, value in self.headers.items()}
        forbidden = [
            name
            for name in (
                "authorization",
                "x-access-token",
                "x-userinfo",
                "x-id-token",
                "x-refresh-token",
                "x-raw-id-token",
            )
            if name in headers
        ]
        evidence = {
            "path": self.path,
            "method": "GET",
            "forbiddenHeadersObserved": forbidden,
            "rangerDecision": "DENY",
            "status": 403,
        }
        (EVIDENCE_DIR / "upstream-observation.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        payload = b'{"decision":"DENY","authority":"synthetic-ranger"}\n'
        self.send_response(403)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def serve(port: int, handler: type[BaseHTTPRequestHandler]) -> None:
    ThreadingHTTPServer(("0.0.0.0", port), handler).serve_forever()


def main() -> None:
    introspection = threading.Thread(
        target=serve, args=(8080, IntrospectionHandler), daemon=True
    )
    introspection.start()
    serve(8081, UpstreamHandler)


if __name__ == "__main__":
    main()
