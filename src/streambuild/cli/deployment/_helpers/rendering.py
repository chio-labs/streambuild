"""Render deployment inventory for text and JSON output."""

import json

from streambuild.executor.deployment.models import DeploymentInventory, DeploymentSummary


def render_deployment_inventory(*, inventory: DeploymentInventory, json_output: bool) -> str:
    """Render a complete deployment inventory."""
    if json_output:
        return json.dumps(
            {
                "database": inventory.database,
                "deployments": [_deployment_payload(value) for value in inventory.deployments],
            },
            indent=2,
        )
    lines: list[str] = ["Deployments", f"Database: {inventory.database}"]
    if not inventory.deployments:
        lines.append("\n- none")
        return "\n".join(lines)
    deployment: DeploymentSummary
    for deployment in inventory.deployments:
        lines.extend(("", f"- {deployment.deployment_id}", f"  state: {deployment.state.value}"))
        if deployment.created_at is not None:
            lines.append(f"  created at: {deployment.created_at}")
        if deployment.root_names:
            lines.append(f"  roots: {', '.join(deployment.root_names)}")
    return "\n".join(lines)


def render_deployment(*, deployment: DeploymentSummary, database: str, json_output: bool) -> str:
    """Render one deployment summary."""
    if json_output:
        return json.dumps({"database": database, **_deployment_payload(deployment)}, indent=2)
    lines: list[str] = [
        "Deployment",
        f"Database: {database}",
        f"Deployment ID: {deployment.deployment_id}",
        f"State: {deployment.state.value}",
        f"Created at: {deployment.created_at or 'unknown'}",
        f"Persisted status: {deployment.persisted_status or 'missing'}",
        f"Roots: {', '.join(deployment.root_names) if deployment.root_names else 'none'}",
        "Physical relations:",
        *(f"- {name}" for name in deployment.physical_relation_names),
        "Missing physical relations:",
        *(f"- {name}" for name in deployment.missing_physical_relation_names),
        "Active bindings:",
        *(f"- {name}" for name in deployment.active_binding_names),
        f"Latest publication: {deployment.latest_published_at or 'none'}",
    ]
    return "\n".join(lines)


def _deployment_payload(deployment: DeploymentSummary) -> dict[str, object]:
    return {
        "deployment_id": deployment.deployment_id,
        "state": deployment.state.value,
        "created_at": deployment.created_at,
        "persisted_status": deployment.persisted_status,
        "root_names": deployment.root_names,
        "physical_relation_names": deployment.physical_relation_names,
        "missing_physical_relation_names": deployment.missing_physical_relation_names,
        "active_binding_names": deployment.active_binding_names,
        "latest_published_at": deployment.latest_published_at,
    }
