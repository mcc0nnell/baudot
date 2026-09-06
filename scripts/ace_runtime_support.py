#!/usr/bin/env python3
import argparse
import json
import signal
import socketserver
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
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
        "channel": "SIP/7001",
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
        "channel": "SIP/7002",
    },
}


class AgentHandler(BaseHTTPRequestHandler):
    server_version = "BaudotAceRuntimeSupport/1"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {"status": "ok", "service": "baudot-ace-agent-stub"})
            return
        if parsed.path.rstrip("/") != "/agentverify":
            self._json(404, {"message": "failed"})
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


class AmiHandler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.sendall(b"Asterisk Call Manager/1.1\r\n")
        buffer = b""
        while True:
            data = self.request.recv(4096)
            if not data:
                return
            buffer += data
            while b"\r\n\r\n" in buffer:
                frame, buffer = buffer.split(b"\r\n\r\n", 1)
                fields = {}
                for line in frame.decode("utf-8", "replace").split("\r\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        fields[key.strip()] = value.strip()
                if fields:
                    self.server.record(fields)
                action_id = fields.get("ActionID") or fields.get("ActionId")
                response = ["Response: Success"]
                if action_id:
                    response.append(f"ActionID: {action_id}")
                action = fields.get("Action", "")
                if action == "Login":
                    response.append("Message: Authentication accepted")
                else:
                    response.append("Message: Action accepted by Baudot AMI stub")
                payload = "\r\n".join(response) + "\r\n\r\n"
                self.request.sendall(payload.encode())


class AmiServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, trace_path):
        self.trace_path = Path(trace_path)
        self.trace_path.parent.mkdir(parents=True, exist_ok=True)
        self.trace_path.write_text("")
        self._lock = threading.Lock()
        super().__init__(address, AmiHandler)

    def record(self, fields):
        event = {
            "ts": time.time(),
            "action": fields.get("Action"),
            "fields": fields,
        }
        with self._lock:
            with self.trace_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, separators=(",", ":")) + "\n")


def serve(server):
    server.serve_forever(poll_interval=0.1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-port", type=int, default=8840)
    parser.add_argument("--ami-a-port", type=int, default=5038)
    parser.add_argument("--ami-b-port", type=int, default=5039)
    parser.add_argument("--trace-dir", default="/tmp/baudot-dual-ace")
    args = parser.parse_args()

    trace_dir = Path(args.trace_dir)
    trace_dir.mkdir(parents=True, exist_ok=True)

    http = ThreadingHTTPServer(("127.0.0.1", args.agent_port), AgentHandler)
    ami_a = AmiServer(("127.0.0.1", args.ami_a_port), trace_dir / "ami-a.jsonl")
    ami_b = AmiServer(("127.0.0.1", args.ami_b_port), trace_dir / "ami-b.jsonl")

    servers = [http, ami_a, ami_b]
    threads = [threading.Thread(target=serve, args=(s,), daemon=True) for s in servers]
    for thread in threads:
        thread.start()

    print(
        f"ACE runtime support listening: agent={args.agent_port} "
        f"ami-a={args.ami_a_port} ami-b={args.ami_b_port}",
        flush=True,
    )

    stop = threading.Event()

    def shutdown(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    while not stop.wait(0.5):
        pass

    for server in servers:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
