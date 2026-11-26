"""Text from screenshots (tesseract). Knows nothing about Chrome.

Only run on screenshots taken before any secret is typed.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class Line:
    text: str
    top: int


def lines(png: str, psm: str = "6") -> list[Line]:
    """OCR lines, top to bottom."""
    tsv = subprocess.run(["tesseract", png, "-", "--psm", psm, "tsv"],
                         capture_output=True, text=True).stdout
    grouped: dict[tuple, dict] = {}
    for row in tsv.splitlines()[1:]:
        c = row.split("\t")
        if len(c) == 12 and c[11].strip():
            g = grouped.setdefault((c[2], c[3], c[4]), {"w": [], "top": int(c[7])})
            g["w"].append(c[11])
    return [Line(" ".join(g["w"]), g["top"]) for g in sorted(grouped.values(), key=lambda g: g["top"])]


def count(png: str, pattern: re.Pattern) -> int:
    """Matches of `pattern`, max over several layout modes (OCR is flaky on dimmed overlays)."""
    best = 0
    for psm in ("6", "11", "3"):
        text = subprocess.run(["tesseract", png, "-", "--psm", psm], capture_output=True, text=True).stdout
        best = max(best, len(pattern.findall(text)))
    return best
