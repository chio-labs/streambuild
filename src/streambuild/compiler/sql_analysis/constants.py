"""SQL scanner and Polyglot vocabulary."""

SQL_QUOTE_CHARACTERS: frozenset[str] = frozenset({"'", '"', "`"})
SQL_IDENTIFIER_PREFIX: str = "_"
SQL_OPEN_PARENTHESIS: str = "("
SQL_CLOSE_PARENTHESIS: str = ")"
SQL_ARGUMENT_SEPARATOR: str = ","
SQL_NAMED_ARGUMENT_SEPARATOR: str = "="
SQL_STATEMENT_DELIMITER: str = ";"
SQL_LINE_COMMENT: str = "--"
SQL_HASH_COMMENT: str = "#"
SQL_BLOCK_COMMENT_OPEN: str = "/*"
SQL_BLOCK_COMMENT_CLOSE: str = "*/"
SQL_ESCAPE_CHARACTER: str = "\\"
SQL_WILDCARD: str = "*"
SQL_WITH_KEYWORD: str = "WITH"
SQL_RECURSIVE_KEYWORD: str = "RECURSIVE"
SQL_AS_KEYWORD: str = "AS"
CLICKHOUSE_AGGREGATE_STATE_TYPE_NAMES: frozenset[str] = frozenset(
    {"aggregatefunction", "simpleaggregatefunction"}
)
CLICKHOUSE_NAMED_FIELD_TYPE_NAMES: frozenset[str] = frozenset({"tuple", "nested"})

SOURCE_REFERENCE_FUNCTION: str = "__source"
MODEL_REFERENCE_FUNCTION: str = "__ref"
REFERENCE_FUNCTIONS: tuple[str, ...] = (
    SOURCE_REFERENCE_FUNCTION,
    MODEL_REFERENCE_FUNCTION,
)
REFERENCE_TYPE_KEYWORD: str = "ref_type"
REFERENCE_WITH_TYPE_ARGUMENT_COUNT: int = 2
PAIRED_QUOTE_CHARACTER_COUNT: int = 2
VALID_REFERENCE_ARGUMENT_COUNTS: frozenset[int] = frozenset({1, REFERENCE_WITH_TYPE_ARGUMENT_COUNT})

POLYGLOT_ALIAS_KEY: str = "alias"
POLYGLOT_ALIAS_VALUE_KEY: str = "this"
POLYGLOT_AND_KEY: str = "and"
POLYGLOT_ARGUMENTS_KEY: str = "args"
POLYGLOT_COLUMN_KEY: str = "column"
POLYGLOT_COMBINED_PARAMETERIZED_AGGREGATE_KEY: str = "combined_parameterized_agg"
POLYGLOT_EQ_KEY: str = "eq"
POLYGLOT_EXPRESSIONS_KEY: str = "expressions"
POLYGLOT_FROM_KEY: str = "from"
POLYGLOT_INSERT_KEY: str = "insert"
POLYGLOT_FUNCTION_KEY: str = "function"
POLYGLOT_JOINS_KEY: str = "joins"
POLYGLOT_LEFT_KEY: str = "left"
POLYGLOT_LITERAL_KEY: str = "literal"
POLYGLOT_NAME_KEY: str = "name"
POLYGLOT_RIGHT_KEY: str = "right"
POLYGLOT_PAREN_KEY: str = "paren"
POLYGLOT_QUERY_KEY: str = "query"
POLYGLOT_SELECT_KEY: str = "select"
POLYGLOT_VALUE_KEY: str = "value"
POLYGLOT_AGGREGATE_FUNCTION_KEY: str = "aggregate_function"
POLYGLOT_CAST_KEY: str = "cast"
POLYGLOT_CTES_KEY: str = "ctes"
POLYGLOT_DATA_TYPE_KEY: str = "data_type"
POLYGLOT_DOUBLE_COLON_SYNTAX_KEY: str = "double_colon_syntax"
POLYGLOT_GROUP_BY_KEY: str = "group_by"
POLYGLOT_SCHEMA_KEY: str = "schema"
POLYGLOT_STAR_KEY: str = "star"
POLYGLOT_TABLE_KEY: str = "table"
POLYGLOT_TO_KEY: str = "to"
POLYGLOT_TRY_CAST_KEY: str = "try_cast"
POLYGLOT_UNION_KEY: str = "union"
POLYGLOT_INTERSECT_KEY: str = "intersect"
POLYGLOT_IDENTIFIER_KEY: str = "identifier"
POLYGLOT_EXCEPT_KEY: str = "except"
POLYGLOT_WITH_KEY: str = "with"
POLYGLOT_WHERE_CLAUSE_KEY: str = "where_clause"

POLYGLOT_COMPACT_PROJECTIONS_KEY: str = "projections"
POLYGLOT_COMPACT_SET_OPERATIONS_KEY: str = "setOperations"
POLYGLOT_COMPACT_BRANCHES_KEY: str = "branches"
POLYGLOT_COMPACT_NAME_KEY: str = "name"
POLYGLOT_COMPACT_IS_STAR_KEY: str = "isStar"
POLYGLOT_COMPACT_UPSTREAM_KEY: str = "upstream"
POLYGLOT_COMPACT_SOURCE_NAME_KEY: str = "sourceName"
POLYGLOT_COMPACT_CONFIDENCE_KEY: str = "confidence"
POLYGLOT_COMPACT_COLUMN_KEY: str = "column"
POLYGLOT_COMPACT_INDEX_KEY: str = "index"

CLICKHOUSE_AGGREGATE_COMBINATORS: tuple[str, ...] = (
    "MergeState",
    "SimpleState",
    "OrDefault",
    "OrNull",
    "Resample",
    "Distinct",
    "ForEach",
    "Merge",
    "State",
    "Array",
    "Map",
    "If",
)
CLICKHOUSE_AGGREGATE_FUNCTION_NAMES: frozenset[str] = frozenset(
    {
        "aggthrow",
        "analysisofvariance",
        "anova",
        "any",
        "anyheavy",
        "anylast",
        "anylast_respect_nulls",
        "any_respect_nulls",
        "any_value",
        "any_value_respect_nulls",
        "approx_top_count",
        "approx_top_k",
        "approx_top_sum",
        "argmax",
        "argmin",
        "array_agg",
        "array_concat_agg",
        "avg",
        "avgweighted",
        "bit_and",
        "bit_or",
        "bit_xor",
        "boundingratio",
        "categoricalinformationvalue",
        "contingency",
        "corr",
        "corrmatrix",
        "corrstable",
        "count",
        "covar_pop",
        "covar_samp",
        "covarpop",
        "covarpopmatrix",
        "covarpopstable",
        "covarsamp",
        "covarsampmatrix",
        "covarsampstable",
        "cramersv",
        "cramersvbiascorrected",
        "deltasum",
        "deltasumtimestamp",
        "denserank",
        "dense_rank",
        "entropy",
        "exponentialmovingaverage",
        "exponentialtimedecayedavg",
        "exponentialtimedecayedcount",
        "exponentialtimedecayedmax",
        "exponentialtimedecayedsum",
        "first_value",
        "first_value_respect_nulls",
        "flamegraph",
        "grouparray",
        "grouparrayinsertat",
        "grouparrayintersect",
        "grouparraylast",
        "grouparraymovingavg",
        "grouparraymovingsum",
        "grouparraysample",
        "grouparraysorted",
        "groupbitand",
        "groupbitor",
        "groupbitxor",
        "groupbitmap",
        "groupbitmapand",
        "groupbitmapor",
        "groupbitmapxor",
        "groupconcat",
        "groupuniqarray",
        "group_concat",
        "histogram",
        "interval_length_sum",
        "intervallengthsum",
        "kolmogorovsmirnovtest",
        "kurtpop",
        "kurtsamp",
        "laginframe",
        "largesttrianglethreebuckets",
        "last_value",
        "last_value_respect_nulls",
        "leadinframe",
        "lttb",
        "mannwhitneyutest",
        "max",
        "maxintersections",
        "maxintersectionsposition",
        "maxmappedarrays",
        "meanztest",
        "median",
        "medianbfloat16",
        "medianbfloat16weighted",
        "mediandd",
        "mediandeterministic",
        "medianexact",
        "medianexacthigh",
        "medianexactlow",
        "medianexactweighted",
        "mediangk",
        "medianinterpolatedweighted",
        "mediantdigest",
        "mediantdigestweighted",
        "mediantiming",
        "mediantimingweighted",
        "min",
        "minmappedarrays",
        "nonnegativederivative",
        "n_tile",
        "nothing",
        "nothingnull",
        "nothinguint64",
        "nth_value",
        "ntile",
        "percentrank",
        "percent_rank",
        "quantile",
        "quantilebfloat16",
        "quantilebfloat16weighted",
        "quantiledd",
        "quantiledeterministic",
        "quantileexact",
        "quantileexactexclusive",
        "quantileexacthigh",
        "quantileexactinclusive",
        "quantileexactlow",
        "quantileexactweighted",
        "quantilegk",
        "quantileinterpolatedweighted",
        "quantiletdigest",
        "quantiletdigestweighted",
        "quantiletiming",
        "quantiletimingweighted",
        "quantiles",
        "quantilesbfloat16",
        "quantilesbfloat16weighted",
        "quantilesdd",
        "quantilesdeterministic",
        "quantilesexact",
        "quantilesexactexclusive",
        "quantilesexacthigh",
        "quantilesexactinclusive",
        "quantilesexactlow",
        "quantilesexactweighted",
        "quantilesgk",
        "quantilesinterpolatedweighted",
        "quantilestdigest",
        "quantilestdigestweighted",
        "quantilestiming",
        "quantilestimingweighted",
        "rank",
        "rankcorr",
        "retention",
        "row_number",
        "sequencecount",
        "sequencematch",
        "sequencenextnode",
        "simplelinearregression",
        "singlevalueornull",
        "skewpop",
        "skewsamp",
        "sparkbar",
        "std",
        "stddev_pop",
        "stddev_samp",
        "stddevpop",
        "stddevpopstable",
        "stddevsamp",
        "stddevsampstable",
        "stochasticlinearregression",
        "stochasticlogisticregression",
        "studentttest",
        "sum",
        "sumcount",
        "sumkahan",
        "summap",
        "summapfiltered",
        "summapfilteredwithoverflow",
        "summapwithoverflow",
        "summappedarrays",
        "sumwithoverflow",
        "theilsu",
        "theilslope",
        "topk",
        "topkweighted",
        "uniq",
        "uniqcombined",
        "uniqcombined64",
        "uniqexact",
        "uniqhll12",
        "uniqtheta",
        "uniqupto",
        "var_pop",
        "var_samp",
        "varpop",
        "varpopstable",
        "varsamp",
        "varsampstable",
        "welchttest",
        "windowfunnel",
    }
)
CLICKHOUSE_AGGREGATE_STATE_FUNCTION_NAMES: frozenset[str] = frozenset(
    {"finalizeaggregation", "initializeaggregation"}
)
CLICKHOUSE_AGGREGATING_ENGINE_NAMES: frozenset[str] = frozenset(
    {"aggregatingmergetree", "summingmergetree"}
)
