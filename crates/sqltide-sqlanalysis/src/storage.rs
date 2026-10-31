//! Find the columns one storage expression references.

use serde_json::Value;

use crate::tree::{AnalysisResult, SqlDialect, identifier_name, object};

/// The column names `expression` references, in tree order with repeats.
///
/// # Errors
///
/// Returns the parse failure when the expression is not exactly one valid statement.
pub fn storage_column_names(expression: &str, dialect: &SqlDialect) -> AnalysisResult<Vec<String>> {
    let tree: Value = dialect.parse_one(expression)?;
    let mut names: Vec<String> = Vec::new();
    collect_column_names(&tree, &mut names);
    Ok(names)
}

fn collect_column_names(node: &Value, names: &mut Vec<String>) {
    match node {
        Value::Array(items) => {
            for item in items {
                collect_column_names(item, names);
            }
        }
        Value::Object(entries) => {
            if let Some(column) = object(entries.get("column")) {
                if let Some(name) = identifier_name(column.get("name")) {
                    names.push(name.to_owned());
                }
                return;
            }
            for value in entries.values() {
                collect_column_names(value, names);
            }
        }
        _ => {}
    }
}
