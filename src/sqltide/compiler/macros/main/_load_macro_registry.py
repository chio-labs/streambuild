"""Load one invocation-scoped Python macro registry."""

from sqltide.compiler.discovery.models import DiscoveredProjectFile
from sqltide.compiler.macros._helpers.registry import load_project_macros
from sqltide.compiler.macros.models import MacroRegistry


def load_macro_registry(*, macro_files: tuple[DiscoveredProjectFile, ...]) -> MacroRegistry:
    """Load one deterministic registry from retained source snapshots."""

    return load_project_macros(macro_files=macro_files)
