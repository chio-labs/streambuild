"""Extract the logical object name from a deployment-suffixed physical name."""


def logical_name_from_physical_name(physical_name: str) -> str:
    """Return the logical object name encoded in a physical object name."""

    return physical_name.rsplit("__", 1)[0]
