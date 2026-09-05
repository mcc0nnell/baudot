"""Minimal reference reducer for Baudot's T.140 baseline vectors.

This module intentionally implements only behavior covered by the current
standards-grounded baseline suite. Unsupported or underspecified cases fail
closed rather than silently extending the protocol model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class BaselineSemanticGap(ValueError):
    """Raised when an input asks the baseline reducer to invent semantics."""


@dataclass(frozen=True)
class PresentationResult:
    display_text: str
    alerts: int
    missing_text_markers: int
    line_breaks: int

    def as_dict(self) -> dict[str, object]:
        return {
            "displayText": self.display_text,
            "alerts": self.alerts,
            "missingTextMarkers": self.missing_text_markers,
            "lineBreaks": self.line_breaks,
        }


def _validate_scalar(code_point: int) -> None:
    if not isinstance(code_point, int):
        raise TypeError("code points must be integers")
    if code_point < 0 or code_point > 0x10FFFF or 0xD800 <= code_point <= 0xDFFF:
        raise ValueError(f"invalid Unicode scalar value U+{code_point:04X}")


def encode_utf8(code_points: Iterable[int]) -> bytes:
    values = list(code_points)
    for code_point in values:
        _validate_scalar(code_point)
    return "".join(chr(code_point) for code_point in values).encode("utf-8")


def apply_t140_baseline(code_points: Iterable[int]) -> PresentationResult:
    values = list(code_points)
    for code_point in values:
        _validate_scalar(code_point)

    display: list[str] = []
    alerts = 0
    missing = 0
    line_breaks = 0
    index = 0

    while index < len(values):
        code_point = values[index]

        if code_point == 0x0007:  # BEL
            alerts += 1
        elif code_point == 0x0008:  # BS
            if not display or display[-1] == "\n":
                raise BaselineSemanticGap(
                    "BS without a preceding baseline text character is outside the current vector set"
                )
            display.pop()
        elif code_point == 0x2028:  # LINE SEPARATOR
            display.append("\n")
            line_breaks += 1
        elif code_point == 0x000D:  # Supported CR LF new-line form.
            if index + 1 >= len(values) or values[index + 1] != 0x000A:
                raise BaselineSemanticGap("isolated CR is outside the current T.140 baseline")
            display.append("\n")
            line_breaks += 1
            index += 1
        elif code_point == 0x000A:
            raise BaselineSemanticGap("isolated LF is outside the current T.140 baseline")
        elif code_point == 0xFFFD:
            display.append("\uFFFD")
            missing += 1
        elif code_point < 0x0020 or 0x007F <= code_point <= 0x009F:
            raise BaselineSemanticGap(
                f"control U+{code_point:04X} is not modeled by the current T.140 baseline"
            )
        else:
            display.append(chr(code_point))

        index += 1

    return PresentationResult(
        display_text="".join(display),
        alerts=alerts,
        missing_text_markers=missing,
        line_breaks=line_breaks,
    )
