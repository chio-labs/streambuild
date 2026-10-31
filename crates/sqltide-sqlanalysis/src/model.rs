//! Parse one authored model and derive its compiler-critical facts, keeping the tree for
//! resolution.

use serde_json::Value;
use sqltide_sqltext::sql_scan::{self, ScanError, SourceSpan};

use crate::facts::{Path, TreeFacts, collect_tree_facts};
use crate::projections::{Projection, ProjectionTypeCache, build_model_projections};
use crate::tree::{AnalysisError, SqlDialect, contains_key};

const SET_OPERATION_KEYS: [&str; 3] = ["union", "intersect", "except"];

/// Why a model could not be analyzed, in the precedence the compiler reports it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ModelError {
    Analysis(AnalysisError),
    Scan(ScanError),
    StatementCount(usize),
    QueryShape {
        statement_type: String,
        statement_sql: String,
        is_set_operation: bool,
    },
    UntypedProjection {
        index: usize,
        projection_sql: String,
        span: SourceSpan,
    },
    StarProjection {
        index: usize,
        span: SourceSpan,
    },
    DuplicateAlias {
        alias: String,
        span: SourceSpan,
    },
}

impl From<AnalysisError> for ModelError {
    fn from(error: AnalysisError) -> Self {
        Self::Analysis(error)
    }
}

/// One analyzed model's parsed tree and the facts its later resolution needs.
#[derive(Debug)]
pub struct ParsedModel {
    pub(crate) tree: Value,
    pub(crate) reference_slots: Vec<Path>,
    pub(crate) raw_relation: Option<String>,
    pub function_names: Vec<String>,
    pub has_group_by: bool,
    pub projections: Vec<Projection>,
}

impl ParsedModel {
    /// Whether the query contains a PREWHERE clause anywhere.
    #[must_use]
    pub fn uses_prewhere(&self) -> bool {
        contains_key(&self.tree, "prewhere")
    }
}

/// Parse `sql` as one SELECT and validate its typed outer projections.
///
/// # Errors
///
/// Returns the first failure in the order the compiler checks: parsing, statement count, query
/// shape, projection scanning, then each projection in authored order.
pub fn analyze_model(
    sql: &str,
    dialect: &SqlDialect,
    type_cache: &mut ProjectionTypeCache,
) -> Result<ParsedModel, ModelError> {
    let mut trees: Vec<Value> = dialect.parse(sql)?;
    if trees.len() != 1 {
        return Err(ModelError::StatementCount(trees.len()));
    }
    let mut tree: Value = trees.remove(0);
    let statement_type: String = tree
        .as_object()
        .and_then(|entries| entries.keys().next())
        .map_or_else(|| "unknown".to_owned(), Clone::clone);
    if !tree.get("select").is_some_and(Value::is_object) {
        return Err(ModelError::QueryShape {
            statement_sql: dialect.generate(&tree, true)?,
            is_set_operation: SET_OPERATION_KEYS.contains(&statement_type.as_str()),
            statement_type,
        });
    }
    let facts: TreeFacts = collect_tree_facts(&tree);
    let characters: Vec<char> = sql.chars().collect();
    let spans: Vec<SourceSpan> =
        sql_scan::outer_projection_spans(&characters).map_err(ModelError::Scan)?;
    let Some(select) = tree.get_mut("select").and_then(Value::as_object_mut) else {
        unreachable!("the SELECT payload was checked above");
    };
    let projections: Vec<Projection> =
        build_model_projections(select, &characters, &spans, dialect, type_cache)?;
    Ok(ParsedModel {
        tree,
        reference_slots: facts.reference_slots,
        raw_relation: facts.raw_relation,
        function_names: facts.function_names,
        has_group_by: facts.has_group_by,
        projections,
    })
}
