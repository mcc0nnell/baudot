#!/usr/bin/env python3
"""Evidence-bound source admission for the pinned Linphone native RTT candidate.

This gate answers one narrow question: does an exact clean Linphone SDK checkout
at the candidate commit contain the public and native RFC 4103/T.140 source
surfaces that justify running a live Baudot qualification?

It does not execute Linphone and it never admits the implementation as an oracle.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Iterable

EXPECTED_COMMIT = "10f0cb98eb5ae7dae973d6666894561ce5eea561"
EXPECTED_REPOSITORY = "BelledonneCommunications/linphone-sdk"
DEFAULT_OUTPUT = Path(
    "target/evidence-external/LINPHONE-CANDIDATE/source-admission/"
    "linphone-source-admission.json"
)

SOURCE_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "liblinphone/include/linphone/call_params.h": (
        "linphone_call_params_enable_realtime_text",
        "rfc4103",
    ),
    "liblinphone/include/linphone/api/c-chat-message.h": (
        "linphone_chat_message_put_char",
        "real-time text",
    ),
    "liblinphone/coreapi/help/examples/C/realtimetext_sender.c": (
        "linphone_call_params_enable_realtime_text",
        "linphone_chat_message_put_char",
    ),
    "mediastreamer2/src/voip/rfc4103_textstream.c": (
        "TextStream",
        "T140",
    ),
    "mediastreamer2/src/otherfilters/rfc4103_source.c": (
        "pt_t140",
        "pt_red",
    ),
    "mediastreamer2/src/otherfilters/rfc4103_sink.c": (
        "process_t140_packet",
    ),
    "ortp/src/avprofile.c": (
        "payload_type_t140",
        'MIME_TYPE("t140")',
    ),
}


def run_git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed with exit {proc.returncode}: "
            f"{proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_markers(path: Path, markers: Iterable[str]) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as failure:
        raise RuntimeError(f"required Linphone source surface is missing: {path}") from failure

    folded = content.casefold()
    missing = [marker for marker in markers if marker.casefold() not in folded]
    if missing:
        raise RuntimeError(
            f"required marker(s) missing from {path}: {', '.join(missing)}"
        )


def main() -> int:
    root_arg = os.environ.get("LINPHONE_SDK_ROOT")
    if len(sys.argv) > 1:
        root_arg = sys.argv[1]
    if not root_arg:
        raise RuntimeError(
            "set LINPHONE_SDK_ROOT or pass the pinned linphone-sdk checkout path"
        )

    output = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    root = Path(root_arg).expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError(f"Linphone SDK root does not exist: {root}")

    actual_commit = run_git(root, "rev-parse", "HEAD")
    if actual_commit != EXPECTED_COMMIT:
        raise RuntimeError(
            f"unexpected Linphone SDK commit: {actual_commit}; expected {EXPECTED_COMMIT}"
        )

    status = run_git(root, "status", "--porcelain=v1", "--untracked-files=normal")
    if status:
        raise RuntimeError("Linphone SDK checkout must be clean")

    origin = run_git(root, "remote", "get-url", "origin", check=False)

    surfaces: list[dict[str, object]] = []
    for relative, markers in SOURCE_REQUIREMENTS.items():
        path = root / relative
        require_markers(path, markers)
        surfaces.append(
            {
                "path": relative,
                "sha256": sha256(path),
                "requiredMarkers": list(markers),
            }
        )

    record = {
        "repository": EXPECTED_REPOSITORY,
        "originObserved": origin,
        "commit": actual_commit,
        "cleanCheckout": True,
        "profile": "linphone-native-rtt-candidate-v1",
        "role": "candidate-second-native-rtt-implementation",
        "sourceAdmissionPassed": True,
        "oracleAdmitted": False,
        "verdictAuthority": False,
        "nativePath": {
            "applicationApi": [
                "linphone_call_params_enable_realtime_text",
                "linphone_chat_message_put_char",
            ],
            "mediaImplementation": "Mediastreamer2 RFC 4103 text stream/source/sink",
            "payloadImplementation": "oRTP t140/red payload definitions",
        },
        "sourceSurfaces": surfaces,
        "requiredBeforeOracleAdmission": [
            "build a Baudot-owned driver against the exact external checkout",
            "observe an RTT-enabled SIP offer",
            "select direct PT 98 t140/1000 in the controlled answer",
            "observe implementation-generated text-media datagrams",
            "independently reduce first non-empty T.140 text to H",
            "publish rttReady=true only from the independent terminal reducer",
        ],
        "claimBoundary": {
            "linphoneConformance": False,
            "sipConformance": False,
            "rtpConformance": False,
            "rfc4103Conformance": False,
            "rfc2198Conformance": False,
            "t140Conformance": False,
            "vrsConformance": False,
            "productionInterop": False,
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as failure:
        print(f"linphone candidate admission failed: {failure}", file=sys.stderr)
        raise SystemExit(2) from failure
