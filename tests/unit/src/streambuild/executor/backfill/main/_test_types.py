from dataclasses import dataclass


@dataclass(frozen=True)
class DeploymentIdentityTestCase:
    description: str
    deployment_id: str
    expected_error_fragment: str


@dataclass(frozen=True)
class ExplicitDeploymentIdentityTestCase:
    description: str
    deployment_id: str
    expected_created_at: str
