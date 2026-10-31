//! The authored top-level `WITH` clause of a statement.

use std::collections::HashSet;

use super::primitives::{
    ScanError, ScanErrorKind, ScanResult, SourceSpan, find_matching_parenthesis,
    is_identifier_character, is_identifier_start, skip_trivia, source_span, text,
    try_consume_keyword,
};
use crate::python_text::python_strip;

/// One top-level common table expression and the span of its body.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SqlCommonTableExpression {
    pub name: String,
    pub query: String,
    pub span: SourceSpan,
}

/// The CTEs of a leading `WITH` clause and the statement after them.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SqlTopLevelCtes {
    pub ctes: Vec<SqlCommonTableExpression>,
    pub trailing_sql: String,
    pub trailing_span: SourceSpan,
}

/// Scan the leading `WITH [RECURSIVE]` clause into its CTEs and the trailing statement.
///
/// # Errors
///
/// Returns a [`ScanErrorKind::MissingWithClause`] error when the statement does not open with
/// `WITH`, and an analysis error naming `context` for malformed or duplicate CTEs.
pub fn extract_top_level_ctes(sql: &[char], context: &str) -> ScanResult<SqlTopLevelCtes> {
    let mut index: usize = consume_with_clause_start(sql, context)?;
    let mut ctes: Vec<SqlCommonTableExpression> = Vec::new();
    let mut seen_names: HashSet<String> = HashSet::new();
    loop {
        let (cte, next) = read_cte(sql, index, context)?;
        if !seen_names.insert(cte.name.clone()) {
            return Err(ScanError::located(
                sql,
                format!("{context} defines duplicate CTE '{}'", cte.name),
                cte.span.start,
                sql.len(),
            ));
        }
        ctes.push(cte);
        index = skip_trivia(sql, next)?;
        if sql.get(index) == Some(&',') {
            index = skip_trivia(sql, index + 1)?;
            continue;
        }
        break;
    }
    Ok(SqlTopLevelCtes {
        ctes,
        trailing_sql: text(python_strip(&sql[index..])),
        trailing_span: source_span(sql, index, sql.len()),
    })
}

fn consume_with_clause_start(sql: &[char], context: &str) -> ScanResult<usize> {
    let index: usize = skip_trivia(sql, 0)?;
    let Some(with_end) = try_consume_keyword(sql, index, "WITH") else {
        return Err(ScanError {
            kind: ScanErrorKind::MissingWithClause,
            message: format!("{context} must declare CTEs in a WITH clause"),
            span: Some(source_span(sql, index, sql.len())),
        });
    };
    let index: usize = skip_trivia(sql, with_end)?;
    match try_consume_keyword(sql, index, "RECURSIVE") {
        None => Ok(index),
        Some(recursive_end) => skip_trivia(sql, recursive_end),
    }
}

fn read_cte(
    sql: &[char],
    start: usize,
    context: &str,
) -> ScanResult<(SqlCommonTableExpression, usize)> {
    if !sql.get(start).copied().is_some_and(is_identifier_start) {
        return Err(ScanError::located(
            sql,
            format!("{context} expected a CTE name"),
            start,
            sql.len(),
        ));
    }
    let mut index: usize = start;
    while index < sql.len() && is_identifier_character(sql[index]) {
        index += 1;
    }
    let name: String = text(&sql[start..index]);
    index = skip_trivia(sql, index)?;
    if sql.get(index) == Some(&'(') {
        let close_index: usize = find_matching_parenthesis(sql, index, context)?;
        index = skip_trivia(sql, close_index + 1)?;
    }
    let as_error = || {
        ScanError::located(
            sql,
            format!("{context} CTE '{name}' must use AS (...)"),
            start,
            sql.len(),
        )
    };
    let as_end: usize = try_consume_keyword(sql, index, "AS").ok_or_else(as_error)?;
    let body_open: usize = skip_trivia(sql, as_end)?;
    if sql.get(body_open) != Some(&'(') {
        return Err(as_error());
    }
    let body_close: usize = find_matching_parenthesis(sql, body_open, context)?;
    Ok((
        SqlCommonTableExpression {
            query: text(python_strip(&sql[body_open + 1..body_close])),
            span: source_span(sql, body_open + 1, body_close),
            name,
        },
        body_close + 1,
    ))
}
