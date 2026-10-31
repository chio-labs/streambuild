//! Parsing to and generating from serde trees, and the small key lookups every walk shares.

use std::fmt;

use polyglot_sql::{Dialect, Expression, ast_json};
use serde_json::{Map, Value};

pub(crate) type Object = Map<String, Value>;

/// One SQL analysis failure, carrying the exact message the compiler reports.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AnalysisError(pub String);

impl AnalysisError {
    pub(crate) fn new(message: impl Into<String>) -> Self {
        Self(message.into())
    }
}

impl fmt::Display for AnalysisError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for AnalysisError {}

pub(crate) type AnalysisResult<T> = Result<T, AnalysisError>;

fn parse_failure(error: impl fmt::Display) -> AnalysisError {
    AnalysisError(format!("SQL could not be parsed with Polyglot: {error}"))
}

fn generate_failure(error: impl fmt::Display) -> AnalysisError {
    AnalysisError(format!("SQL could not be generated with Polyglot: {error}"))
}

/// A Polyglot dialect looked up once per analyzer rather than once per statement.
pub struct SqlDialect {
    name: String,
    dialect: Option<Dialect>,
}

impl SqlDialect {
    /// Look up a dialect by name. An unknown name fails on first use, as it did when every call
    /// looked the dialect up again.
    #[must_use]
    pub fn new(name: &str) -> Self {
        Self {
            name: name.to_owned(),
            dialect: Dialect::get_by_name(name),
        }
    }

    fn dialect(&self) -> Result<&Dialect, String> {
        self.dialect
            .as_ref()
            .ok_or_else(|| format!("Unknown dialect: {}", self.name))
    }

    /// Parse every statement in `sql` into serde trees.
    ///
    /// # Errors
    ///
    /// Returns the parse failure for invalid SQL or an unknown dialect.
    pub fn parse(&self, sql: &str) -> AnalysisResult<Vec<Value>> {
        let dialect: &Dialect = self.dialect().map_err(parse_failure)?;
        let expressions: Vec<Expression> = dialect.parse(sql).map_err(parse_failure)?;
        expressions
            .iter()
            .map(|expression| ast_json::expression_to_value(expression).map_err(parse_failure))
            .collect()
    }

    /// Parse exactly one statement.
    ///
    /// # Errors
    ///
    /// Returns the parse failure for invalid SQL or any statement count other than one.
    pub fn parse_one(&self, sql: &str) -> AnalysisResult<Value> {
        let mut trees: Vec<Value> = self.parse(sql)?;
        if trees.len() != 1 {
            return Err(parse_failure(format!(
                "Expected 1 statement, found {}",
                trees.len()
            )));
        }
        Ok(trees.remove(0))
    }

    /// Generate SQL for one serde tree.
    ///
    /// # Errors
    ///
    /// Returns the generation failure when the tree does not decode or cannot be generated.
    pub fn generate(&self, tree: &Value, pretty: bool) -> AnalysisResult<String> {
        let dialect: &Dialect = self.dialect().map_err(generate_failure)?;
        let expression: Expression =
            ast_json::expression_from_value(tree.clone()).map_err(|error| {
                generate_failure(format!("Failed to decode AST expression: {error}"))
            })?;
        let generated = if pretty {
            dialect.generate_pretty(&expression)
        } else {
            dialect.generate(&expression)
        };
        generated.map_err(generate_failure)
    }
}

pub(crate) fn object(value: Option<&Value>) -> Option<&Object> {
    value.and_then(Value::as_object)
}

pub(crate) fn text(value: Option<&Value>) -> Option<&str> {
    value.and_then(Value::as_str)
}

pub(crate) fn is_nested(value: &Value) -> bool {
    matches!(value, Value::Object(_) | Value::Array(_))
}

/// Python truthiness, which `a or b` lookups in the original walks relied on.
pub(crate) fn truthy(value: Option<&Value>) -> bool {
    match value {
        None | Some(Value::Null) => false,
        Some(Value::Bool(flag)) => *flag,
        Some(Value::Number(number)) => number.as_f64().is_some_and(|number| number != 0.0),
        Some(Value::String(text)) => !text.is_empty(),
        Some(Value::Array(items)) => !items.is_empty(),
        Some(Value::Object(entries)) => !entries.is_empty(),
    }
}

/// The `name` of an identifier payload.
pub(crate) fn identifier_name(payload: Option<&Value>) -> Option<&str> {
    text(object(payload)?.get("name"))
}

/// The names a SELECT payload's `WITH` clause declares.
pub(crate) fn select_cte_names(select: &Object) -> Vec<String> {
    let Some(ctes) = object(select.get("with"))
        .and_then(|with| with.get("ctes"))
        .and_then(Value::as_array)
    else {
        return Vec::new();
    };
    ctes.iter()
        .filter_map(Value::as_object)
        .filter_map(|cte| identifier_name(cte.get("alias")))
        .map(str::to_owned)
        .collect()
}

/// The visible CTE names below `value`: `visible` plus whatever `value` itself declares.
pub(crate) fn with_ctes(visible: &[String], value: &Object) -> Option<Vec<String>> {
    let declared: Vec<String> = select_cte_names(value);
    if declared.is_empty() {
        return None;
    }
    let mut names: Vec<String> = visible.to_vec();
    names.extend(declared);
    Some(names)
}

/// Whether `key` appears anywhere in the tree.
pub(crate) fn contains_key(value: &Value, key: &str) -> bool {
    match value {
        Value::Object(entries) => {
            entries.contains_key(key) || entries.values().any(|child| contains_key(child, key))
        }
        Value::Array(items) => items.iter().any(|child| contains_key(child, key)),
        _ => false,
    }
}
