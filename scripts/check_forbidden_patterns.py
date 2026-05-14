#!/usr/bin/env python3
"""Pre-commit hook: block staged files that contain identifying patterns.

Implements the "no patient data, no maintainer-identifying paths" rule
from CLAUDE.md section 1. The patterns below come from the Phase 1
audit and are deliberately filtered to literals with very low false-
positive risk against bilingual ES/EN documentation.

Run by pre-commit with the staged file paths as arguments. Exits 0 when
no forbidden pattern is found, 1 (with details on stderr) otherwise.

Allowlist
---------
Files that legitimately contain one or more of the patterns are skipped.
See the ALLOWLIST definition below for the current entries and their
justification. Every entry weakens the protection — keep the list short.

Encoding
--------
Files are read as UTF-8 with errors="replace" so a cp1252-encoded
accidental file does not silently bypass the check.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Literal patterns. Case-sensitive. Each must be specific enough that an
# ES/EN doc reader does not legitimately use it.
LITERAL_PATTERNS: tuple[str, ...] = (
    "Daniel",
    "daniel",
    "Iñiguez",
    "Iniguez",
    "ininiguez",
    "OctoPC",
    "IRM_2022",
    "sk-ant-",
)

# Regex patterns for hardcoded Windows paths and specific dates.
REGEX_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"C:\\Users\\OctoPC", re.IGNORECASE),
    re.compile(r"C:/Users/OctoPC", re.IGNORECASE),
    re.compile(r"\b2019\.03\.09\b"),
    re.compile(r"\b9/03/2019\b"),
    re.compile(r"\b09/03/2019\b"),
)

# ALLOWLIST: files that legitimately contain one of the literal patterns
# we block elsewhere. Adding paths here weakens the protection — every
# entry must be justified:
#
#   * CLAUDE.md — documents the audit patterns by design (Phase 1 section).
#   * .pre-commit-config.yaml — references this script by path.
#   * scripts/check_forbidden_patterns.py — this script itself names the
#     literal patterns it blocks; self-allowlist is necessary.
#   * src/neuro_analyzer/main.py — contains the literal "sk-ant-..." as a
#     pedagogical placeholder in the CLI help message advising users to
#     set ANTHROPIC_API_KEY. Not a real key. If a real key ever appears
#     here, gitleaks will catch it via its higher-entropy detector.
#
# Paths are compared as POSIX-style relative paths.
ALLOWLIST: frozenset[str] = frozenset({
    "CLAUDE.md",
    ".pre-commit-config.yaml",
    "scripts/check_forbidden_patterns.py",
    "src/neuro_analyzer/main.py",
})


def _is_allowlisted(path: Path) -> bool:
    rel = path.as_posix()
    return rel in ALLOWLIST


def _scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return a list of (line_number, pattern, line_excerpt) for matches."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, IsADirectoryError):
        return []

    findings: list[tuple[int, str, str]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for literal in LITERAL_PATTERNS:
            if literal in line:
                findings.append((line_no, literal, line.strip()[:200]))
        for regex in REGEX_PATTERNS:
            m = regex.search(line)
            if m:
                findings.append((line_no, regex.pattern, line.strip()[:200]))
    return findings


def main(argv: list[str]) -> int:
    if not argv:
        return 0

    any_finding = False
    for arg in argv:
        path = Path(arg)
        if not path.is_file():
            continue
        if _is_allowlisted(path):
            continue

        findings = _scan_file(path)
        if findings:
            any_finding = True
            print(f"\nForbidden pattern(s) in {path.as_posix()}:", file=sys.stderr)
            for line_no, pattern, excerpt in findings:
                print(f"  line {line_no}: {pattern!r} -> {excerpt}", file=sys.stderr)

    if any_finding:
        print(
            "\nThese patterns are blocked by CLAUDE.md section 1 (no PHI, no "
            "maintainer-identifying paths, no API keys). If a match is a "
            "legitimate documented pattern, add the file path to ALLOWLIST in "
            "scripts/check_forbidden_patterns.py.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
