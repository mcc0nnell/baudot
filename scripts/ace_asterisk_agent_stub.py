#!/usr/bin/env python3
import argparse
import json
import signal
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

AGENTS = {
    "provider-a-agent": {
        "agent_id": 1,
        "username": "provider-a-agent",
        "first_name": "Provider",
        "last_name": "A",
        "role": "agent",
        "phone": "202-555-0101",
        "email": "provider-a@example.invalid",
        "organization": "Baudot Provider A",
        "extension": 6001,
        "channel": "Local/7001@agent-origin/n",
    },
    "provider-b-agent": {
        "agent_id": 2,
        "username": "provider-b-agent",
        "first_name": "Provider",
        "last_name": "B",
        "role": "agent",
        "phone": "202-555-0103",
        "email": "provider-b@example.invalid",
        "organization": "Baudot Provider B",
        "extension": 6002,
        "channel": "Local/7002@agent-origin/n",
    },
}


class Handler(BaseHTTPRequestHandler):
    server_version = "BaudotAceAsteriskAgentStub/1"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {"status": "ok", "service": "baudot-ace-asterisk-agent-stub"})
            return
        if parsed.path.rstrip("/") != "/agentverify":
            self._json(404, {"message": "failed", "data": []})
            return
        query = parse_qs(parsed.query)
        username = query.get("username", [""])[0]
        password = query.get("password", [""])[0]
        profile = AGENTS.get(username)
        if profile is None or password != "test":
            self._json(200, {"message": "failed", "data": []})
            return
        self._json(200, {"message": "success", "data": [profile]})

    def log_message(self, fmt, *args):
        return

    def _json(self, status, payload):
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8840)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)

    def shutdown(_signum, _frame):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    print(f"ACE Asterisk agent stub listening on 127.0.0.1:{args.port}", flush=True)
    server.serve_forever(poll_interval=0.1)
    server.server_close()


if __name__ == "__main__":
    main()
