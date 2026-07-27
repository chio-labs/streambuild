import pytest

from streambuild.adapter.models import (
    AdapterIdentity,
    CatalogColumn,
    CatalogIdentity,
    CatalogRelation,
    CatalogSnapshot,
)
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.plan.main._source_validation import (
    validate_declared_external_sources,
)
from tests.unit.src.streambuild.cli.plan.main._test_types import (
    CliExternalSourceValidationErrorTestCase,
)
from tests.unit.src.streambuild.cli.plan.main.helpers import (
    build_realized_external_source_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CliExternalSourceValidationErrorTestCase(
            description="rejects replay alias collision with an existing physical column",
            existing_column_names=(
                "order_id",
                "event_partition",
                "event_offset",
                "event_timestamp",
                "_replay_offset",
            ),
            expected_error_fragment="conflicts with the injected replay alias",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_external_source_alias_collision_when_validating_then_it_raises_clear_error(
    test_case: CliExternalSourceValidationErrorTestCase,
) -> None:
    catalog: CatalogSnapshot = CatalogSnapshot(
        identity=CatalogIdentity(adapter=AdapterIdentity(name="clickhouse"), database="default"),
        warehouse_timezone="UTC",
        relations=(
            CatalogRelation(
                name="orders_existing",
                engine="MergeTree",
                columns=tuple(
                    CatalogColumn(name=column_name, type="DateTime64(3)")
                    for column_name in test_case.existing_column_names
                ),
            ),
        ),
    )

    with pytest.raises(CliUserError, match=test_case.expected_error_fragment):
        validate_declared_external_sources(
            catalog=catalog,
            external_source_replay_configs=(
                build_realized_external_source_project().desired_state.external_source_replay_configs
            ),
            database="default",
        )
