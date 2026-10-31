"""Compare or rewrite compiler output goldens for the whole corpus."""

import json
import tempfile
from dataclasses import asdict
from pathlib import Path

from scripts.compiler_goldens._helpers.capture import capture_compile
from scripts.compiler_goldens._helpers.generated import write_generated_chain_project
from scripts.compiler_goldens.constants import (
    CORPUS_PROJECT_DIRECTORIES,
    EDGE_CORPUS_DIRECTORY,
    GENERATED_CHAIN_MODEL_COUNT,
    GENERATED_CHAIN_PROJECT_NAME,
    GOLDEN_DIRECTORY,
)
from scripts.compiler_goldens.models import CompilerCapture


def check_compiler_goldens(*, update: bool) -> int:
    """Return 0 when every corpus project matches its golden, rewriting them on update."""

    captures: list[CompilerCapture] = [
        capture_compile(name=project_dir.name, project_dir=project_dir)
        for project_dir in (*CORPUS_PROJECT_DIRECTORIES, *_edge_projects())
    ]
    with tempfile.TemporaryDirectory(prefix="sqltide-generated-") as scratch:
        generated_dir: Path = Path(scratch) / GENERATED_CHAIN_PROJECT_NAME
        write_generated_chain_project(
            project_dir=generated_dir, model_count=GENERATED_CHAIN_MODEL_COUNT
        )
        captures.append(
            capture_compile(name=GENERATED_CHAIN_PROJECT_NAME, project_dir=generated_dir)
        )
    mismatches: list[str] = [
        capture.project for capture in captures if not _matches(capture=capture, update=update)
    ]
    for project in mismatches:
        print(f"compiler golden mismatch: {project} (run `make compiler-goldens-update`)")
    print(f"compiler goldens: {len(captures) - len(mismatches)}/{len(captures)} match")
    return 1 if mismatches else 0


def _edge_projects() -> tuple[Path, ...]:
    return tuple(sorted(path for path in EDGE_CORPUS_DIRECTORY.iterdir() if path.is_dir()))


def _matches(*, capture: CompilerCapture, update: bool) -> bool:
    golden_path: Path = GOLDEN_DIRECTORY / f"{capture.project}.json"
    rendered: str = json.dumps(asdict(capture), indent=2, sort_keys=True) + "\n"
    if update:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(rendered, encoding="utf-8")
        return True
    return golden_path.exists() and golden_path.read_text(encoding="utf-8") == rendered
