#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    p.add_argument("--http-port", type=int, required=True)
    p.add_argument("--ami-port", type=int, required=True)
    p.add_argument("--adapter-port", type=int, required=True)
    p.add_argument("--agent-port", type=int, required=True)
    args = p.parse_args()

    config = {
        "debuglevel": "ERROR",
        "dialaroundnums": "|1234567890|",
        "http": {
            "port": args.http_port,
            "port-dashboard": args.http_port,
            "port-user": args.http_port,
        },
        "zendesk": {
            "ticket": "no",
            "apiurl": "http://127.0.0.1:9/api/v2",
            "userid": "nobody@example.invalid",
            "token": "synthetic",
            "proxy": {
                "host": "127.0.0.1",
                "port": 9,
                "tunnel": "false",
            },
        },
        "asterisk": {
            "sip": {
                "host": "127.0.0.1",
                "realm": "baudot.invalid",
                "stun": "[]",
                "wsport": 443,
                "outboundurl_host": "",
                "outboundurl_port": "",
                "disable_3gpp_early_ims": False,
                "disable_debug_message": False,
                "cache_media_stream": True,
                "disable_call_button_options": False,
                "disable_video": False,
                "enable_rtcweb_breaker": False,
                "channel": "SIP",
                "websocket": "wss://127.0.0.1:9/ws",
            },
            "ami": {
                "id": "baudot",
                "passwd": "synthetic",
                "port": args.ami_port,
            },
            "ari": {
                "id": "baudot",
                "passwd": "synthetic",
            },
        },
        "extensions": {
            "startnumber": "4001",
            "endnumber": "4010",
            "secret": "synthetic",
        },
        "queues": {
            "inbound": {"name": "InboundQueue"},
            "complaint": {"number": "123456"},
            "information": {"number": "123456"},
        },
        "vrscheck": {
            "verify": "yes",
            "url": "http://127.0.0.1",
            "port": args.adapter_port,
        },
        "agentservice": {
            "verify": "yes",
            "url": "http://127.0.0.1",
            "port": args.agent_port,
        },
        "scriptservice": {
            "verify": "no",
            "url": "http://127.0.0.1",
            "port": 9,
        },
        "jsonwebtoken": {
            "encoding": "base64",
            "secretkey": "YmF1ZG90LWFjZS1sYWItc2VjcmV0",
            "timeout": 15000,
            "handshake": True,
        },
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(config, indent=2) + "\n")


if __name__ == "__main__":
    main()
