"""Apache-2.0: SQLBuild cli/commands/_helpers/compile/output.py@7e3b2f854f05."""

import json
from collections.abc import Mapping
from pathlib import Path

from streambuild.diagnostics.models import (
    CompilerDiagnostic,
    RelatedDiagnosticLocation,
    SourceLocation,
)


def render_diagnostic_text(
    *, diagnostic: CompilerDiagnostic, source_by_path: Mapping[Path, str]
) -> str:
    """Render one diagnostic with stable source context when available."""

    lines: list[str] = [
        f"{diagnostic.severity} [{diagnostic.code}] {diagnostic.message}",
        f"phase: {diagnostic.phase}",
    ]
    if diagnostic.resource_name is not None:
        lines.append(f"resource: {diagnostic.resource_name}")
    if diagnostic.location is not None:
        lines.extend(
            _render_location(
                location=diagnostic.location,
                source=source_by_path.get(diagnostic.location.path),
                label=None,
            )
        )
    related: RelatedDiagnosticLocation
    for related in diagnostic.related_locations:
        lines.extend(
            _render_location(
                location=related.location,
                source=source_by_path.get(related.location.path),
                label=related.label,
            )
        )
        if related.message is not None:
            lines.append(related.message)
    if diagnostic.help is not None:
        lines.append(f"help: {diagnostic.help}")
    return "\n".join(lines)


def render_diagnostic_json_text(*, diagnostic: CompilerDiagnostic) -> str:
    """Serialize one structured diagnostic deterministically."""

    payload: dict[str, object] = {
        "code": diagnostic.code,
        "help": diagnostic.help,
        "location": _location_payload(diagnostic.location),
        "message": diagnostic.message,
        "phase": diagnostic.phase,
        "related_locations": tuple(
            {
                "label": related.label,
                "location": _location_payload(related.location),
                "message": related.message,
            }
            for related in diagnostic.related_locations
        ),
        "resource_name": diagnostic.resource_name,
        "severity": diagnostic.severity,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _render_location(
    *, location: SourceLocation, source: str | None, label: str | None
) -> list[str]:
    label_prefix: str = "" if label is None else f"{label}: "
    lines: list[str] = [f"{label_prefix}--> {location.path}:{location.line}:{location.column}"]
    source_lines: list[str] = [] if source is None else source.splitlines()
    if location.line < 1 or location.line > len(source_lines):
        return lines
    source_line: str = source_lines[location.line - 1]
    start_column: int = max(location.column, 1)
    end_column: int = (
        start_column
        if location.end_column is None or location.end_line != location.line
        else max(location.end_column, start_column)
    )
    lines.extend(
        (
            "  |",
            f"{location.line:>3} | {source_line}",
            "  | " + " " * (start_column - 1) + "^" * max(end_column - start_column + 1, 1),
        )
    )
    return lines


def _location_payload(location: SourceLocation | None) -> dict[str, object] | None:
    if location is None:
        return None
    return {
        "column": location.column,
        "end_column": location.end_column,
        "end_line": location.end_line,
        "line": location.line,
        "path": str(location.path),
    }
