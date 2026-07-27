"""Registry loading for authored Python SQL macros."""

from __future__ import annotations

import ast
import hashlib
import inspect
from types import ModuleType

from streambuild.compiler.discovery.models import DiscoveredProjectFile
from streambuild.compiler.macros.exceptions import MacroError
from streambuild.compiler.macros.models import LoadedMacro, MacroRegistry
from streambuild.diagnostics.models import RelatedDiagnosticLocation, SourceLocation


def load_project_macros(*, macro_files: tuple[DiscoveredProjectFile, ...]) -> MacroRegistry:
    """Load one deterministic registry from retained project macro sources."""

    loaded_macros: dict[str, LoadedMacro] = {}
    macro_file: DiscoveredProjectFile
    for macro_file in macro_files:
        module: ModuleType = _load_macro_module(
            macro_file=macro_file,
        )
        loaded_macro: LoadedMacro
        for loaded_macro in _load_public_macros_from_module(
            module=module,
            macro_file=macro_file,
        ):
            existing_macro: LoadedMacro | None = loaded_macros.get(loaded_macro.name)
            if existing_macro is not None:
                collision_paths: str = f"'{macro_file.file_path}' and '{existing_macro.file_path}'"
                raise MacroError(
                    f"Macro name collision for '{loaded_macro.name}' in {collision_paths}",
                    location=_definition_location(loaded_macro),
                    related_locations=(
                        RelatedDiagnosticLocation(
                            label="first macro definition",
                            location=_definition_location(existing_macro),
                        ),
                    ),
                )
            loaded_macros[loaded_macro.name] = loaded_macro
    return MacroRegistry(macros=loaded_macros)


def _load_macro_module(*, macro_file: DiscoveredProjectFile) -> ModuleType:
    module_name: str = _macro_module_name(macro_file)
    module: ModuleType = ModuleType(module_name)
    module.__file__ = str(macro_file.file_path)
    try:
        exec(
            compile(macro_file.contents, str(macro_file.file_path), "exec"),
            module.__dict__,
        )
    except SyntaxError as error:
        raise MacroError(
            f"Failed to load {macro_file.file_path}: {error}",
            location=SourceLocation(
                path=macro_file.file_path,
                line=error.lineno or 1,
                column=error.offset or 1,
            ),
        ) from error
    except Exception as error:
        raise MacroError(
            f"Failed to load {macro_file.file_path}: {error}",
            location=SourceLocation(path=macro_file.file_path, line=1, column=1),
        ) from error
    return module


def _load_public_macros_from_module(
    *, module: ModuleType, macro_file: DiscoveredProjectFile
) -> tuple[LoadedMacro, ...]:
    definition_line_by_name: dict[str, int] = _definition_lines(macro_file)
    loaded_macros: list[LoadedMacro] = []
    name: str
    function: object
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if (
            name.startswith("_")
            or function.__module__ != module.__name__
            or inspect.iscoroutinefunction(function)
        ):
            continue
        loaded_macros.append(
            LoadedMacro(
                name=name,
                file_path=macro_file.file_path,
                relative_path=macro_file.relative_path,
                source=macro_file.contents,
                definition_line=definition_line_by_name[name],
                function=function,
            )
        )
    return tuple(loaded_macros)


def _macro_module_name(macro_file: DiscoveredProjectFile) -> str:
    digest: str = hashlib.sha1(str(macro_file.file_path).encode("utf-8")).hexdigest()[:12]
    return f"streambuild_project_macros_{digest}"


def _definition_lines(macro_file: DiscoveredProjectFile) -> dict[str, int]:
    try:
        tree: ast.Module = ast.parse(macro_file.contents, filename=str(macro_file.file_path))
    except SyntaxError as error:
        raise MacroError(
            f"Failed to load {macro_file.file_path}: {error}",
            location=SourceLocation(
                path=macro_file.file_path,
                line=error.lineno or 1,
                column=error.offset or 1,
            ),
        ) from error
    return {
        node.name: node.lineno
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _definition_location(macro: LoadedMacro) -> SourceLocation:
    return SourceLocation(
        path=macro.file_path,
        line=macro.definition_line,
        column=1,
    )
