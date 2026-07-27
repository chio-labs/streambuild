from unittest.mock import patch

import polyglot_sql
import pytest

from streambuild.compiler.sql_analysis.classes.sql_reference_rewriter import (
    SqlReferenceRewriter,
)
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError
from streambuild.compiler.sql_analysis.main._rewrite_references import rewrite_references
from tests.unit.src.streambuild.compiler.sql_analysis._test_types import (
    PolyglotCallCountTestCase,
    PolyglotInvocationCacheTestCase,
    ReferenceRewriteErrorTestCase,
    ReferenceRewriteTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReferenceRewriteTestCase(
            description=(
                "rewrites nested CTE source and join refs without changing comments or aliases"
            ),
            sql=(
                'WITH selected AS (SELECT * FROM /* source marker */ __source("orders") o)\n'
                "SELECT '__ref(\"customers\")' AS marker_text\n"
                'FROM selected s /* before join */ JOIN __ref("customers", '
                'ref_type="reference") AS c ON s.customer_id = c.id -- trailing marker comment\n'
            ),
            resolver={"orders": "raw.orders", "customers": "analytics.customers"},
            expected_sql=(
                "WITH selected AS (SELECT * FROM /* source marker */ raw.orders o)\n"
                "SELECT '__ref(\"customers\")' AS marker_text\n"
                "FROM selected s /* before join */ JOIN analytics.customers AS c "
                "ON s.customer_id = c.id -- trailing marker comment\n"
            ),
        ),
        ReferenceRewriteTestCase(
            description="rewrites aliases in nested subqueries and preserves authored formatting",
            sql=(
                'SELECT o.id FROM __source("orders") AS o WHERE o.id IN (\n'
                '  SELECT c.id FROM __ref("customers", ref_type="mutable") c\n'
                ")"
            ),
            resolver={
                "orders": "raw__orders",
                "customers": "analytics.tbl__customers",
            },
            expected_sql=(
                "SELECT o.id FROM raw__orders AS o WHERE o.id IN (\n"
                "  SELECT c.id FROM analytics.tbl__customers c\n"
                ")"
            ),
        ),
        ReferenceRewriteTestCase(
            description="accepts parenthesized adopted source relations",
            sql='SELECT e.id FROM __source("events") e',
            resolver={"events": "(SELECT id FROM raw.events)"},
            expected_sql="SELECT e.id FROM (SELECT id FROM raw.events) e",
        ),
        ReferenceRewriteTestCase(
            description="canonicalizes unsafe replacement comments before source substitution",
            sql=('SELECT * FROM __ref("orders") o JOIN system.one s ON 1 = 1'),
            resolver={"orders": "analytics.orders -- unsafe replacement\n"},
            expected_sql=(
                "SELECT * FROM analytics.orders /* unsafe replacement */ o "
                "JOIN system.one s ON 1 = 1"
            ),
        ),
        ReferenceRewriteTestCase(
            description="rewrites comma-separated relations and canonicalizes quoted targets",
            sql='SELECT * FROM __ref("orders") o, __ref("customers") c',
            resolver={"orders": "`analytics`.`orders`", "customers": "raw.customers"},
            expected_sql='SELECT * FROM "analytics"."orders" o, raw.customers c',
        ),
        ReferenceRewriteTestCase(
            description="removes terminal delimiter while preserving trailing audit comments",
            sql='SELECT * FROM __ref("orders"); -- keep this audit comment\n',
            resolver={"orders": "analytics.orders"},
            expected_sql="SELECT * FROM analytics.orders -- keep this audit comment\n",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_relation_markers_when_rewriting_then_preserves_non_reference_text(
    test_case: ReferenceRewriteTestCase,
) -> None:
    rewritten: str = rewrite_references(
        sql=test_case.sql,
        resolver=test_case.resolver,
        dialect="clickhouse",
    )

    assert rewritten == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        ReferenceRewriteErrorTestCase(
            description="rejects unresolved logical names",
            sql='SELECT * FROM __source("missing")',
            resolver={},
            expected_error_fragment="Unresolved ref: missing",
        ),
        ReferenceRewriteErrorTestCase(
            description="rejects marker calls outside relation positions",
            sql='SELECT __ref("orders") AS relation_name FROM system.one',
            resolver={"orders": "analytics.orders"},
            expected_error_fragment="valid only in FROM or JOIN relation positions",
        ),
        ReferenceRewriteErrorTestCase(
            description="rejects malformed authored SQL without fallback",
            sql='SELECT * FROM __ref("orders") WHERE (',
            resolver={"orders": "analytics.orders"},
            expected_error_fragment="could not be parsed with Polyglot",
        ),
        ReferenceRewriteErrorTestCase(
            description="rejects malformed replacement relations without fallback",
            sql='SELECT * FROM __ref("orders")',
            resolver={"orders": "("},
            expected_error_fragment="could not be parsed with Polyglot",
        ),
        ReferenceRewriteErrorTestCase(
            description="rejects replacement relations that own an alias",
            sql='SELECT * FROM __ref("orders") authored_alias',
            resolver={"orders": "analytics.orders replacement_alias"},
            expected_error_fragment="must not define its own alias",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_relation_rewrite_when_rewriting_then_raises_without_fallback(
    test_case: ReferenceRewriteErrorTestCase,
) -> None:
    with pytest.raises(SqlAnalysisError, match=test_case.expected_error_fragment):
        rewrite_references(
            sql=test_case.sql,
            resolver=test_case.resolver,
            dialect="clickhouse",
        )


@pytest.mark.parametrize(
    "test_case",
    [
        PolyglotCallCountTestCase(
            description="parses authored SQL once and each unique replacement once",
            sql=(
                'SELECT * FROM __ref("orders") o '
                'JOIN __ref("orders") p USING id '
                'JOIN __source("customers") c USING customer_id'
            ),
            resolver={
                "orders": "analytics.orders",
                "customers": "raw.customers",
            },
            expected_parse_calls=3,
            expected_generate_calls=3,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_repeated_targets_when_rewriting_then_bounds_polyglot_calls(
    test_case: PolyglotCallCountTestCase,
) -> None:
    with (
        patch(
            "streambuild.compiler.sql_analysis._helpers.polyglot.polyglot_sql.parse_one",
            wraps=polyglot_sql.parse_one,
        ) as parse_one,
        patch(
            "streambuild.compiler.sql_analysis._helpers.polyglot.polyglot_sql.generate",
            wraps=polyglot_sql.generate,
        ) as generate,
    ):
        _ = rewrite_references(
            sql=test_case.sql,
            resolver=test_case.resolver,
            dialect="clickhouse",
        )

    assert parse_one.call_count == test_case.expected_parse_calls
    assert generate.call_count == test_case.expected_generate_calls


@pytest.mark.parametrize(
    "test_case",
    [
        PolyglotInvocationCacheTestCase(
            description="reuses replacement parsing across models in one invocation",
            first_sql='SELECT * FROM __ref("orders") first_orders',
            second_sql='SELECT count() FROM __ref("orders") second_orders',
            resolver={"orders": "analytics.orders"},
            expected_parse_calls=3,
            expected_generate_calls=3,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_shared_rewriter_when_rewriting_models_then_reuses_invocation_relation_cache(
    test_case: PolyglotInvocationCacheTestCase,
) -> None:
    rewriter: SqlReferenceRewriter = SqlReferenceRewriter(dialect="clickhouse")
    with (
        patch(
            "streambuild.compiler.sql_analysis._helpers.polyglot.polyglot_sql.parse_one",
            wraps=polyglot_sql.parse_one,
        ) as parse_one,
        patch(
            "streambuild.compiler.sql_analysis._helpers.polyglot.polyglot_sql.generate",
            wraps=polyglot_sql.generate,
        ) as generate,
    ):
        _ = rewriter.rewrite(sql=test_case.first_sql, resolver=test_case.resolver)
        _ = rewriter.rewrite(sql=test_case.second_sql, resolver=test_case.resolver)

    assert parse_one.call_count == test_case.expected_parse_calls
    assert generate.call_count == test_case.expected_generate_calls
