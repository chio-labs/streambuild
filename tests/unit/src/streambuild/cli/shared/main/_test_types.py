from dataclasses import dataclass


@dataclass(frozen=True)
class CliSelectionResolutionTestCase:
    description: str
    selectors: tuple[str, ...]
    expected_selected_model_names: tuple[str, ...]
    expected_object_names: tuple[str, ...]


@dataclass(frozen=True)
class CliSelectionResolutionErrorTestCase:
    description: str
    selectors: tuple[str, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class CliSelectionLineageMismatchTestCase:
    description: str
    selectors: tuple[str, ...]
    mutated_pipeline_name: str
    expected_error_fragment: str


@dataclass(frozen=True)
class CliStartTimeNormalizationTestCase:
    description: str
    raw_value: str
    expected_normalized_value: str


@dataclass(frozen=True)
class CliStartTimeNormalizationErrorTestCase:
    description: str
    raw_value: str
    expected_error_fragment: str


@dataclass(frozen=True)
class CliStartTimeConversionTestCase:
    description: str
    timezone_name: str
    utc_timestamp: str
    expected_converted_value: str


@dataclass(frozen=True)
class CliReplaySourceWarningTestCase:
    description: str
    replay_source_row_count: int
    active_row_count: int | None
    expected_warning_message_fragment: str


@dataclass(frozen=True)
class CliExternalSourceValidationErrorTestCase:
    description: str
    existing_column_names: tuple[str, ...]
    expected_error_fragment: str
