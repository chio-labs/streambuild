"""Public connection-lazy configuration interpolation operation."""

from collections.abc import Mapping

from streambuild.compiler.discovery._helpers.interpolation import interpolate_config_value


def interpolate_configuration_value(
    *,
    value: object,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
    field_path: str,
) -> object:
    """Interpolate one effective configuration value at its owning boundary."""

    return interpolate_config_value(
        value=value,
        variables=variables,
        environment=environment,
        field_path=field_path,
    )
