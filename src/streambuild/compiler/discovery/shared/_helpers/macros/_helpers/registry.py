"""Registry loading for authored Python SQL macros."""

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import inspect
from pathlib import Path
from types import ModuleType

from streambuild.compiler.discovery.shared._helpers.macros.constants import (
    MACRO_DIRECTORY_NAME,
    PROJECT_FILE_NAME,
)
from streambuild.compiler.discovery.shared._helpers.macros.models import LoadedMacro


def load_project_macros(file_path: Path) -> dict[str, LoadedMacro]:
    """Load all public Python macro functions for the project containing a SQL file."""

    project_file_path: Path | None = _find_project_file(file_path)
    if project_file_path is None:
        return {}
    macros_root: Path = project_file_path.parent / MACRO_DIRECTORY_NAME
    if not macros_root.exists():
        return {}
    loaded_macros: dict[str, LoadedMacro] = {}
    macro_file_path: Path
    for macro_file_path in sorted(macros_root.rglob("*.py")):
        module: ModuleType = _load_macro_module(macro_file_path)
        loaded_macro: LoadedMacro
        for loaded_macro in _load_public_macros_from_module(
            module=module, file_path=macro_file_path
        ):
            existing_macro: LoadedMacro | None = loaded_macros.get(loaded_macro.name)
            if existing_macro is not None:
                raise ValueError(
                    f"Macro name collision for '{loaded_macro.name}' in '{macro_file_path}' and "
                    f"'{existing_macro.file_path}'"
                )
            loaded_macros[loaded_macro.name] = loaded_macro
    return loaded_macros


def _find_project_file(path: Path) -> Path | None:
    current_path: Path = path if path.is_dir() else path.parent
    candidate_root: Path
    for candidate_root in [current_path, *current_path.parents]:
        candidate_file: Path = candidate_root / PROJECT_FILE_NAME
        if candidate_file.exists():
            return candidate_file
    return None


def _load_macro_module(macro_file_path: Path) -> ModuleType:
    module_name: str = _macro_module_name(macro_file_path)
    module_spec: importlib.machinery.ModuleSpec | None = importlib.util.spec_from_file_location(
        module_name,
        macro_file_path,
    )
    if module_spec is None or module_spec.loader is None:
        raise ValueError(f"Failed to load {macro_file_path}: could not build import spec")
    module: ModuleType = importlib.util.module_from_spec(module_spec)
    try:
        module_spec.loader.exec_module(module)
    except Exception as error:
        raise ValueError(f"Failed to load {macro_file_path}: {error}") from error
    return module


def _load_public_macros_from_module(
    *, module: ModuleType, file_path: Path
) -> tuple[LoadedMacro, ...]:
    loaded_macros: list[LoadedMacro] = []
    name: str
    function: object
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if name.startswith("_") or function.__module__ != module.__name__:
            continue
        loaded_macros.append(
            LoadedMacro(name=name, file_path=file_path, module=module, function=function)
        )
    return tuple(loaded_macros)


def _macro_module_name(macro_file_path: Path) -> str:
    digest: str = hashlib.sha1(str(macro_file_path).encode("utf-8")).hexdigest()[:12]
    return f"streambuild_project_macros_{digest}"
