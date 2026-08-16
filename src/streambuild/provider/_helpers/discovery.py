"""Apache-2.0: SQLBuild compiler/discovery/_helpers/filesystem/core.py@7625d22e2716."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType

from pydantic import ValidationError

from streambuild.provider.exceptions import ProviderDiscoveryError, ProviderInputError
from streambuild.provider.models import DiscoveredProvider
from streambuild.providers import Provider

_PYTHON_INIT_MODULE_STEM: str = "__init__"


def discover_provider_classes(*, project_dir: Path) -> tuple[DiscoveredProvider, ...]:
    """Discover provider classes under providers/."""

    providers_root: Path = project_dir / "providers"
    if not providers_root.is_dir():
        return ()

    discovered_providers: list[DiscoveredProvider] = []
    seen_names: dict[str, Path] = {}
    file_path: Path
    for file_path in sorted(providers_root.rglob("*.py")):
        if file_path.stem == _PYTHON_INIT_MODULE_STEM or file_path.name.startswith("_"):
            continue
        module: ModuleType = _load_provider_module(file_path=file_path, project_dir=project_dir)
        for _, value in inspect.getmembers(module, inspect.isclass):
            if value.__module__ != module.__name__:
                continue
            if value is Provider or not issubclass(value, Provider) or inspect.isabstract(value):
                continue
            provider_class: type[Provider] = value
            provider_name: str = _provider_name(
                provider_class=provider_class,
                file_path=file_path,
                project_dir=project_dir,
            )
            existing_path: Path | None = seen_names.get(provider_name)
            if existing_path is not None:
                raise ProviderDiscoveryError(
                    f"Duplicate provider name '{provider_name}' found in "
                    f"{existing_path.relative_to(project_dir)} and "
                    f"{file_path.relative_to(project_dir)}"
                )
            seen_names[provider_name] = file_path
            discovered_providers.append(
                DiscoveredProvider(
                    file_path=file_path,
                    relative_path=file_path.relative_to(project_dir),
                    name=provider_name,
                    provider_class=provider_class,
                    settings=_provider_instance(
                        provider_class=provider_class,
                        provider_name=provider_name,
                        file_path=file_path,
                        project_dir=project_dir,
                    ),
                )
            )
    return tuple(discovered_providers)


def _provider_name(*, provider_class: type[Provider], file_path: Path, project_dir: Path) -> str:
    try:
        return provider_class.name()
    except ProviderInputError as error:
        raise ProviderDiscoveryError(
            f"Provider class {provider_class.__name__} in {file_path.relative_to(project_dir)} "
            f"has an invalid provider name: {error}"
        ) from error


def _provider_instance(
    *, provider_class: type[Provider], provider_name: str, file_path: Path, project_dir: Path
) -> Provider:
    try:
        return provider_class()
    except ValidationError as error:
        relative_path: Path = file_path.relative_to(project_dir)
        raise ProviderDiscoveryError(
            f"Provider '{provider_name}' in {relative_path} has invalid settings:\n"
            f"{_format_provider_validation_error(error)}"
        ) from error


def _format_provider_validation_error(error: ValidationError) -> str:
    details: list[str] = []
    for item in error.errors(include_input=False):
        location: object = item.get("loc", ())
        location_text: str = ".".join(str(part) for part in location) if location else "<root>"
        message: object = item.get("msg", "invalid value")
        error_type: object = item.get("type", "validation_error")
        details.append(f"{location_text}: {message} [{error_type}]")
    return "\n".join(details) or "invalid provider settings"


def _load_provider_module(*, file_path: Path, project_dir: Path) -> ModuleType:
    module_name: str = ".".join(file_path.relative_to(project_dir).with_suffix("").parts)
    _evict_stale_project_package_modules(
        root_module=module_name.split(".", maxsplit=1)[0],
        project_dir=project_dir,
    )
    existing_module: ModuleType | None = sys.modules.get(module_name)
    if existing_module is not None:
        existing_file: object = getattr(existing_module, "__file__", None)
        if isinstance(existing_file, str) and Path(existing_file).resolve() == file_path.resolve():
            return existing_module
        sys.modules.pop(module_name, None)
    spec: ModuleSpec | None = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ProviderDiscoveryError(f"Could not load provider file {file_path}")
    module: ModuleType = importlib.util.module_from_spec(spec)
    old_path: list[str] = list(sys.path)
    sys.path.insert(0, str(project_dir))
    try:
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as error:
        raise ProviderDiscoveryError(
            f"Failed to import provider file {file_path.relative_to(project_dir)}: {error}"
        ) from error
    finally:
        sys.path = old_path
    return module


def _evict_stale_project_package_modules(*, root_module: str, project_dir: Path) -> None:
    root_path: Path = (project_dir / root_module).resolve()
    module_name: str
    module: ModuleType
    for module_name, module in tuple(sys.modules.items()):
        if module_name != root_module and not module_name.startswith(f"{root_module}."):
            continue
        module_file: object = getattr(module, "__file__", None)
        if isinstance(module_file, str):
            try:
                Path(module_file).resolve().relative_to(project_dir.resolve())
                continue
            except ValueError:
                sys.modules.pop(module_name, None)
                continue
        module_paths: object = getattr(module, "__path__", None)
        if module_paths is None:
            sys.modules.pop(module_name, None)
            continue
        if any(Path(path).resolve() == root_path for path in module_paths):
            continue
        sys.modules.pop(module_name, None)
