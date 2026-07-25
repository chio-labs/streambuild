from dataclasses import dataclass


@dataclass(frozen=True)
class BuildMetadataStateTestCase:
    description: str
    expected_object_state_keys: tuple[tuple[str | None, str, str], ...]
    expected_deployment_ids: tuple[str, ...]
    expected_first_deployment_root_keys: tuple[tuple[str | None, str, str], ...]
    expected_first_deployment_warning_codes: tuple[str, ...]
    expected_first_deployment_mapping_names: tuple[str, ...]
    expected_watermark_boundary_keys: tuple[str, ...]
    expected_runtime_detail_target_names: tuple[str, ...]
