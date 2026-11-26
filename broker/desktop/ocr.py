"""Text from screenshots (tesseract). Knows nothing about Chrome.

Only run on screenshots taken before any secret is typed. Images arrive as bytes and go to
tesseract through a pipe: nothing is written to disk.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Line:
    text: str
    top: int


def _tesseract(png: bytes, *args: str) -> str:
    r = subprocess.run(["tesseract", "stdin", "stdout", *args], input=png, capture_output=True)
    return r.stdout.decode(errors="replace")


def lines(png: bytes, psm: str = "6") -> list[Line]:
    """OCR lines, top to bottom."""
    tsv = _tesseract(png, "--psm", psm, "tsv")
    grouped: dict[tuple, dict] = {}
    for row in tsv.splitlines()[1:]:
        c = row.split("\t")
        if len(c) == 12 and c[11].strip():
            g = grouped.setdefault((c[2], c[3], c[4]), {"w": [], "top": int(c[7])})
            g["w"].append(c[11])
    return [Line(" ".join(g["w"]), g["top"]) for g in sorted(grouped.values(), key=lambda g: g["top"])]


def count(png: bytes, pattern: re.Pattern) -> int:
    """Matches of `pattern`, max over several layout modes (OCR is flaky on dimmed overlays)."""
    best = 0
    for psm in ("6", "11", "3"):
        text = _tesseract(png, "--psm", psm)
        best = max(best, len(pattern.findall(text)))
    return best
