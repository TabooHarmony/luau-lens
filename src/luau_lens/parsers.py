"""Parse output from luau-lsp analyze and selene into structured diagnostics."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass
class Diagnostic:
    file: str
    line: int
    column: int
    end_line: int | None
    end_column: int | None
    code: str
    severity: str  # "error" | "warning"
    message: str
    source: str  # "luau-lsp" | "selene"


# ---------------------------------------------------------------------------
# luau-lsp plain format parser
# ---------------------------------------------------------------------------
# Format: file:line:col-endcol: (W0) CategoryName: message
# Example: test.luau:1:1-25: (W0) TypeError: Expected this to be 'number', but got 'string'
# Example: test.luau:5:7-12: (W0) LocalUnused: Variable 'result' is never used; prefix with '_' to silence

_LUAU_LSP_RE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+)(?:-(?P<endcol>\d+))?"
    r":\s+\(W0\)\s+(?P<category>\w+):\s+(?P<message>.+)$"
)

# Lines to skip (INFO/WARN/DEBUG noise from luau-lsp)
_SKIP_PREFIXES = ("[INFO]", "[WARN]", "[DEBUG]", "WARNING:", "Analyzing")


def parse_luau_lsp(output: str, stderr: str = "") -> list[Diagnostic]:
    """Parse luau-lsp analyze --formatter plain output."""
    diagnostics: list[Diagnostic] = []
    for line in (output + "\n" + stderr).splitlines():
        line = line.strip()
        if not line:
            continue
        if any(line.startswith(p) for p in _SKIP_PREFIXES):
            continue

        m = _LUAU_LSP_RE.match(line)
        if not m:
            continue

        category = m.group("category")
        # TypeError → error, everything else → warning
        severity = "error" if "Error" in category else "warning"

        end_col = m.group("endcol")
        diagnostics.append(Diagnostic(
            file=m.group("file"),
            line=int(m.group("line")),
            column=int(m.group("col")),
            end_line=None,  # luau-lsp plain format doesn't give end line separately
            end_column=int(end_col) if end_col else None,
            code=category,
            severity=severity,
            message=m.group("message"),
            source="luau-lsp",
        ))
    return diagnostics


# ---------------------------------------------------------------------------
# selene JSON parser
# ---------------------------------------------------------------------------
# selene --display-style json outputs one JSON object per line, then a "Results:" summary.
# Each line is a JSON object with: severity, code, message, primary_label {filename, span {start_line, start_column, end_line, end_column}}

_SELENE_SEVERITY_MAP = {
    "Error": "error",
    "Warning": "warning",
}


def parse_selene(output: str) -> list[Diagnostic]:
    """Parse selene --display-style json output."""
    diagnostics: list[Diagnostic] = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith("Results:"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        label = obj.get("primary_label", {})
        span = label.get("span", {})
        filename = label.get("filename", "unknown")

        # selene uses 0-indexed lines, convert to 1-indexed
        line_num = span.get("start_line", 0) + 1
        col_num = span.get("start_column", 0) + 1
        end_line = span.get("end_line", 0) + 1
        end_col = span.get("end_column", 0) + 1

        severity_str = obj.get("severity", "Warning")
        severity = _SELENE_SEVERITY_MAP.get(severity_str, "warning")

        diagnostics.append(Diagnostic(
            file=filename,
            line=line_num,
            column=col_num,
            end_line=end_line,
            end_column=end_col,
            code=obj.get("code", "unknown"),
            severity=severity,
            message=obj.get("message", ""),
            source="selene",
        ))
    return diagnostics


# ---------------------------------------------------------------------------
# Merge + deduplicate
# ---------------------------------------------------------------------------

def merge_diagnostics(*lists: list[Diagnostic]) -> list[Diagnostic]:
    """Merge diagnostic lists, deduplicating by (file, line, column, code)."""
    seen: set[tuple[str, int, int, str]] = set()
    merged: list[Diagnostic] = []
    for lst in lists:
        for d in lst:
            key = (d.file, d.line, d.column, d.code)
            if key not in seen:
                seen.add(key)
                merged.append(d)
    # Sort by file, then line, then column
    merged.sort(key=lambda d: (d.file, d.line, d.column))
    return merged


def to_dict(diagnostics: list[Diagnostic]) -> dict:
    """Convert diagnostics to the MCP response format."""
    errors = sum(1 for d in diagnostics if d.severity == "error")
    warnings = sum(1 for d in diagnostics if d.severity == "warning")
    return {
        "diagnostics": [
            {
                "file": d.file,
                "line": d.line,
                "column": d.column,
                "endLine": d.end_line,
                "endColumn": d.end_column,
                "code": d.code,
                "severity": d.severity,
                "message": d.message,
                "source": d.source,
            }
            for d in diagnostics
        ],
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "total": len(diagnostics),
        },
    }
