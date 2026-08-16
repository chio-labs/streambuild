"""Compile one optional retained root access policy."""

import yaml

from streambuild.compiler.access._helpers.fingerprint import access_policy_fingerprint
from streambuild.compiler.access._helpers.schema import build_compiled_roles
from streambuild.compiler.access._helpers.strict_yaml import load_strict_yaml
from streambuild.compiler.access.exceptions import AccessPolicyError
from streambuild.compiler.access.models import CompiledAccessPolicy, CompiledAccessRole
from streambuild.compiler.discovery.models import DiscoveredProjectFile
from streambuild.diagnostics.models import SourceLocation


def compile_access_policy(
    *, source_file: DiscoveredProjectFile | None, pipeline_names: frozenset[str]
) -> CompiledAccessPolicy | None:
    """Compile strict YAML into one immutable policy, or return no policy."""

    if source_file is None:
        return None
    try:
        document: object = load_strict_yaml(contents=source_file.contents)
    except yaml.MarkedYAMLError as error:
        mark: yaml.Mark | None = error.problem_mark
        raise AccessPolicyError(
            error.problem or str(error),
            location=SourceLocation(
                path=source_file.file_path,
                line=1 if mark is None else mark.line + 1,
                column=1 if mark is None else mark.column + 1,
            ),
        ) from error
    roles: tuple[CompiledAccessRole, ...] = build_compiled_roles(
        document=document,
        pipeline_names=pipeline_names,
        source_path=source_file.file_path,
    )
    return CompiledAccessPolicy(
        roles=roles,
        fingerprint=access_policy_fingerprint(roles=roles),
    )
