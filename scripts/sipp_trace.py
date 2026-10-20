#!/usr/bin/env python3
"""Small parser for SIP message blocks preserved by SIPp `-trace_msg`.

The parser intentionally exposes structural message facts only. It does not
classify SIP conformance, SDP semantics, media behavior, or accessibility.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MESSAGE_START = re.compile(
    r"(?im)^[ \t]*(?:(?:INVITE|ACK|BYE|REFER|NOTIFY|OPTIONS|CANCEL|UPDATE|INFO|PRACK|REGISTER|SUBSCRIBE)"
    r"\s+\S+\s+SIP/2\.0|SIP/2\.0\s+\d{3}\b[^\r\n]*)[ \t]*\r?$"
)
CSEQ = re.compile(r"(?im)^CSeq:\s*(\d+)\s+([A-Z]+)[ \t]*\r?$")
CONTENT_LENGTH = re.compile(
    r"(?im)^(?:Content-Length|l):\s*(\d+)[ \t]*\r?$"
)


@dataclass(frozen=True)
class SipMessage:
    offset: int
    start_line: str
    raw: str
    cseq: int | None
    cseq_method: str | None

    @property
    def is_response(self) -> bool:
        return self.start_line.upper().startswith("SIP/2.0 ")

    @property
    def status(self) -> int | None:
        if not self.is_response:
            return None
        match = re.match(r"(?i)^SIP/2\.0\s+(\d{3})\b", self.start_line)
        return int(match.group(1)) if match else None

    @property
    def request_method(self) -> str | None:
        if self.is_response:
            return None
        return self.start_line.split(None, 1)[0].upper()

    def has_header(self, name: str, contains: str | None = None) -> bool:
        pattern = re.compile(rf"(?im)^{re.escape(name)}:\s*(.*?)\s*$")
        match = pattern.search(self.raw)
        if match is None:
            return False
        if contains is None:
            return True
        return contains.lower() in match.group(1).lower()

    @property
    def body(self) -> str:
        boundary = _header_boundary(self.raw, 0)
        if boundary is None:
            return ""
        header_end, separator = boundary
        body_start = header_end + len(separator)
        length_match = CONTENT_LENGTH.search(self.raw[:header_end])
        body_end = (
            body_start + int(length_match.group(1))
            if length_match is not None
            else len(self.raw)
        )
        return self.raw[body_start:body_end].strip()


def _header_boundary(trace: str, start: int) -> tuple[int, str] | None:
    separators = tuple(
        (position, separator)
        for separator in ("\r\n\r\n", "\n\n")
        if (position := trace.find(separator, start)) >= 0
    )
    return min(separators, key=lambda item: item[0]) if separators else None


def _declared_body_end(trace: str, start: int) -> int:
    boundary = _header_boundary(trace, start)
    if boundary is None:
        return start

    header_end, separator = boundary
    length_match = CONTENT_LENGTH.search(trace[start:header_end])
    if length_match is None:
        return start
    return header_end + len(separator) + int(length_match.group(1))


def parse_messages(trace: str) -> list[SipMessage]:
    starts = []
    body_end = -1
    for match in MESSAGE_START.finditer(trace):
        if match.start() < body_end:
            continue
        starts.append(match)
        body_end = _declared_body_end(trace, match.start())

    messages: list[SipMessage] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(trace)
        raw = trace[match.start():end]
        start_line = match.group(0).strip()
        cseq_match = CSEQ.search(raw)
        messages.append(
            SipMessage(
                offset=match.start(),
                start_line=start_line,
                raw=raw,
                cseq=int(cseq_match.group(1)) if cseq_match else None,
                cseq_method=cseq_match.group(2).upper() if cseq_match else None,
            )
        )
    return messages


def find_request(
    messages: list[SipMessage], method: str, cseq: int | None = None
) -> SipMessage | None:
    method = method.upper()
    return next(
        (
            message
            for message in messages
            if not message.is_response
            and message.request_method == method
            and (cseq is None or message.cseq == cseq)
            and (message.cseq_method is None or message.cseq_method == method)
        ),
        None,
    )


def find_response(
    messages: list[SipMessage],
    status: int,
    cseq: int | None = None,
    method: str | None = None,
) -> SipMessage | None:
    normalized_method = method.upper() if method is not None else None
    return next(
        (
            message
            for message in messages
            if message.is_response
            and message.status == status
            and (cseq is None or message.cseq == cseq)
            and (normalized_method is None or message.cseq_method == normalized_method)
        ),
        None,
    )
