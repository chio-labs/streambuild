//! Validate a model's outer projections and render each one's cast type.

use std::collections::{HashMap, HashSet};

use serde_json::{Value, json};
use sqltide_sqltext::sql_scan::{self, SourceSpan};

use crate::model::ModelError;
use crate::tree::{AnalysisError, Object, SqlDialect, object, text, truthy};

/// Rendered cast types keyed by their serialized type payload, shared across one invocation.
pub type ProjectionTypeCache = HashMap<String, String>;

/// One typed, aliased outer projection.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Projection {
    pub index: usize,
    pub name: String,
    pub type_sql: String,
    pub span: SourceSpan,
}

pub(crate) fn build_model_projections(
    select: &mut Object,
    sql: &[char],
    spans: &[SourceSpan],
    dialect: &SqlDialect,
    type_cache: &mut ProjectionTypeCache,
) -> Result<Vec<Projection>, ModelError> {
    let Some(Value::Array(expressions)) = select.get_mut("expressions") else {
        return Err(count_mismatch());
    };
    if expressions.len() != spans.len() {
        return Err(count_mismatch());
    }
    let mut projections: Vec<Projection> = Vec::with_capacity(spans.len());
    let mut seen_aliases: HashSet<String> = HashSet::new();
    for (offset, (expression, span)) in expressions.iter_mut().zip(spans).enumerate() {
        let index: usize = offset + 1;
        let Some(expression_tree) = expression.as_object() else {
            return Err(ModelError::UntypedProjection {
                index,
                projection_sql: String::new(),
                span: *span,
            });
        };
        if is_outer_star(expression_tree) {
            let star: Option<SourceSpan> =
                sql_scan::outer_star_span(sql, span.start, span.end).map_err(ModelError::Scan)?;
            return Err(ModelError::StarProjection {
                index,
                span: star.unwrap_or(*span),
            });
        }
        let alias_payload: Option<&Value> = expression_tree.get("alias");
        let alias: Option<String> = projection_alias(alias_payload).map(str::to_owned);
        let (Some(cast), Some(alias)) = (cast_payload(alias_payload), alias) else {
            return Err(untyped(expression, index, *span, dialect));
        };
        let double_colon: bool = cast.get("double_colon_syntax") == Some(&Value::Bool(true));
        if double_colon
            && let Some(authored_type) =
                sql_scan::outer_double_colon_type(sql, span.start, span.end)
                    .map_err(ModelError::Scan)?
            && let Some(cast) = cast_payload_mut(expression)
        {
            cast.insert(
                "to".to_owned(),
                json!({"data_type": "custom", "name": authored_type}),
            );
        }
        if !seen_aliases.insert(alias.clone()) {
            return Err(ModelError::DuplicateAlias { alias, span: *span });
        }
        let Some(type_payload) =
            cast_payload(expression.get("alias")).and_then(|cast| cast.get("to"))
        else {
            return Err(untyped(expression, index, *span, dialect));
        };
        if !type_payload.is_object() {
            return Err(untyped(expression, index, *span, dialect));
        }
        let type_sql: String = projection_type_sql(type_payload, dialect, type_cache)?;
        projections.push(Projection {
            index,
            name: alias,
            type_sql,
            span: *span,
        });
    }
    Ok(projections)
}

fn count_mismatch() -> ModelError {
    ModelError::Analysis(AnalysisError::new(
        "Polyglot projection count did not match authored SQL",
    ))
}

fn untyped(expression: &Value, index: usize, span: SourceSpan, dialect: &SqlDialect) -> ModelError {
    match dialect.generate(expression, false) {
        Ok(projection_sql) => ModelError::UntypedProjection {
            index,
            projection_sql,
            span,
        },
        Err(error) => ModelError::Analysis(error),
    }
}

fn projection_type_sql(
    type_payload: &Value,
    dialect: &SqlDialect,
    type_cache: &mut ProjectionTypeCache,
) -> Result<String, ModelError> {
    let key: String = type_payload.to_string();
    if let Some(type_sql) = type_cache.get(&key) {
        return Ok(type_sql.clone());
    }
    let type_sql: String = dialect
        .generate(&json!({"data_type": type_payload}), false)
        .map_err(ModelError::Analysis)?;
    type_cache.insert(key, type_sql.clone());
    Ok(type_sql)
}

fn is_outer_star(expression: &Object) -> bool {
    expression.contains_key("star")
        || object(expression.get("alias"))
            .and_then(|alias| object(alias.get("this")))
            .is_some_and(|aliased| aliased.contains_key("star"))
}

fn cast_payload(alias_payload: Option<&Value>) -> Option<&Object> {
    let expression: &Object = object(object(alias_payload)?.get("this"))?;
    let cast: Option<&Value> = expression.get("cast");
    let cast: Option<&Value> = if truthy(cast) {
        cast
    } else {
        expression.get("try_cast")
    };
    object(cast)
}

fn cast_payload_mut(expression: &mut Value) -> Option<&mut Object> {
    let aliased: &mut Object = expression
        .get_mut("alias")?
        .get_mut("this")?
        .as_object_mut()?;
    let key: &str = if truthy(aliased.get("cast")) {
        "cast"
    } else {
        "try_cast"
    };
    aliased.get_mut(key)?.as_object_mut()
}

fn projection_alias(alias_payload: Option<&Value>) -> Option<&str> {
    text(object(object(alias_payload)?.get("alias"))?.get("name")).filter(|name| !name.is_empty())
}
