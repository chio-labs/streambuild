"""Recognize deployment-suffixed physical object names."""

import re

from streambuild.compiler.planner.constants import DEPLOYMENT_ID_PATTERN


def is_deployment_physical_name(physical_name: str) -> bool:
    """Return whether the name is a StreamBuild deployment-suffixed physical name."""

    logical_name, separator, deployment_id = physical_name.rpartition("__")
    return bool(logical_name and separator and re.fullmatch(DEPLOYMENT_ID_PATTERN, deployment_id))
