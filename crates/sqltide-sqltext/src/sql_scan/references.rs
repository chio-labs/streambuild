//! `__source(name)` and `__ref(name[, ref_type='...'])` logical relation references.

use super::primitives::{
    REFERENCE_CONTEXT, ScanError, ScanResult, SourceSpan, find_matching_parenthesis,
    is_identifier_character, is_identifier_start, is_quote, skip_block_comment, skip_line_comment,
    skip_non_code, skip_quoted_text, skip_trivia, source_span, starts_with, text,
};
use crate::python_text::python_strip;

const SOURCE_FUNCTION: &str = "__source";
const REF_FUNCTION: &str = "__ref";
const REF_TYPE_KEYWORD: &str = "ref_type";
const REF_TYPE_ARGUMENT_ERROR: &str =
    "__ref(...) optional second argument must be ref_type='reference' or ref_type='mutable'";

/// One logical relation reference in authored SQL.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SqlReference {
    pub name: String,
    /// `"source"` or `"ref"`.
    pub relation_type: &'static str,
    /// `"reference"` or `"mutable"` when declared.
    pub ref_type: Option<&'static str>,
    pub span: SourceSpan,
}

/// Return the references outside comments and quoted text, in authored order.
///
/// # Errors
///
/// Returns an error for malformed reference calls or unclosed quotes, comments and parentheses.
pub fn extract_references(sql: &[char]) -> ScanResult<Vec<SqlReference>> {
    let mut references: Vec<SqlReference> = Vec::new();
    let mut index: usize = 0;
    while index < sql.len() {
        if let Some(next) = skip_non_code(sql, index)? {
            index = next;
            continue;
        }
        if let Some((reference, next)) = parse_reference_at(sql, index)? {
            references.push(reference);
            index = next;
            continue;
        }
        index += 1;
    }
    Ok(references)
}

fn parse_reference_at(sql: &[char], start: usize) -> ScanResult<Option<(SqlReference, usize)>> {
    let Some(function) = [SOURCE_FUNCTION, REF_FUNCTION]
        .into_iter()
        .find(|name| starts_with(sql, start, name))
    else {
        return Ok(None);
    };
    if start > 0 && is_identifier_character(sql[start - 1]) {
        return Ok(None);
    }
    let open_index: usize = skip_trivia(sql, start + function.len())?;
    if sql.get(open_index) != Some(&'(') {
        return Ok(None);
    }
    let close_index: usize = find_matching_parenthesis(sql, open_index, REFERENCE_CONTEXT)?;
    let end: usize = close_index + 1;
    let arguments: Vec<Vec<char>> = split_arguments(sql, open_index + 1, close_index)?;
    if !(1..=2).contains(&arguments.len()) {
        return Err(ScanError::located(
            sql,
            "__source(...) and __ref(...) must contain one name argument and optional ref_type",
            start,
            end,
        ));
    }
    let name: String = parse_name(&arguments[0], sql, start, end)?;
    let mut ref_type: Option<&'static str> = None;
    if arguments.len() == 2 {
        if function != REF_FUNCTION {
            return Err(ScanError::located(
                sql,
                "__source(...) must not declare ref_type",
                start,
                end,
            ));
        }
        ref_type = Some(parse_ref_type(&arguments[1], sql, start, end)?);
    }
    let relation_type: &'static str = if function == SOURCE_FUNCTION {
        "source"
    } else {
        "ref"
    };
    Ok(Some((
        SqlReference {
            name,
            relation_type,
            ref_type,
            span: source_span(sql, start, end),
        },
        end,
    )))
}

fn split_arguments(sql: &[char], start: usize, end: usize) -> ScanResult<Vec<Vec<char>>> {
    let mut arguments: Vec<Vec<char>> = Vec::new();
    let mut argument_start: usize = start;
    let mut depth: i64 = 0;
    let mut index: usize = start;
    while index < end {
        if let Some(next) = skip_non_code(sql, index)? {
            index = next;
            continue;
        }
        match sql[index] {
            '(' => depth += 1,
            ')' => depth -= 1,
            ',' if depth == 0 => {
                arguments.push(argument_text(sql, argument_start, index)?);
                argument_start = index + 1;
            }
            _ => {}
        }
        index += 1;
    }
    arguments.push(argument_text(sql, argument_start, end)?);
    if arguments.iter().any(Vec::is_empty) {
        return Err(ScanError::located(
            sql,
            "__source(...) and __ref(...) arguments must not be empty",
            start,
            end,
        ));
    }
    Ok(arguments)
}

/// The argument text with each comment replaced by one space, stripped.
fn argument_text(sql: &[char], start: usize, end: usize) -> ScanResult<Vec<char>> {
    let mut parts: Vec<char> = Vec::new();
    let mut index: usize = start;
    while index < end {
        if starts_with(sql, index, "--") || sql[index] == '#' {
            parts.push(' ');
            index = skip_line_comment(sql, index).min(end);
        } else if starts_with(sql, index, "/*") {
            parts.push(' ');
            index = skip_block_comment(sql, index)?.min(end);
        } else if is_quote(sql[index]) {
            let quoted_end: usize = skip_quoted_text(sql, index)?.min(end);
            parts.extend_from_slice(&sql[index..quoted_end]);
            index = quoted_end;
        } else {
            parts.push(sql[index]);
            index += 1;
        }
    }
    Ok(python_strip(&parts).to_vec())
}

fn parse_name(raw: &[char], sql: &[char], start: usize, end: usize) -> ScanResult<String> {
    let value: &[char] = python_strip(raw);
    if value.len() >= 2 && value[0] == value[value.len() - 1] && is_quote(value[0]) {
        let quoted_end: usize = skip_quoted_text(value, 0)?;
        let unquoted: String = unquote(value);
        if quoted_end == value.len() && !unquoted.is_empty() {
            return Ok(unquoted);
        }
    }
    if value.first().copied().is_some_and(is_identifier_start)
        && value[1..]
            .iter()
            .all(|character| is_identifier_character(*character))
    {
        return Ok(text(value));
    }
    Err(ScanError::located(
        sql,
        "__source(...) and __ref(...) name arguments must be a quoted string or identifier",
        start,
        end,
    ))
}

fn unquote(value: &[char]) -> String {
    let quote: char = value[0];
    let last: usize = value.len() - 1;
    let mut result: String = String::new();
    let mut index: usize = 1;
    while index < last {
        if value[index] == '\\' && index + 1 < last {
            result.push(value[index + 1]);
            index += 2;
        } else if value[index] == quote && index + 1 < last && value[index + 1] == quote {
            result.push(quote);
            index += 2;
        } else {
            result.push(value[index]);
            index += 1;
        }
    }
    result
}

fn parse_ref_type(
    raw: &[char],
    sql: &[char],
    start: usize,
    end: usize,
) -> ScanResult<&'static str> {
    let mut separators = raw
        .iter()
        .enumerate()
        .filter(|(_, character)| **character == '=')
        .map(|(index, _)| index);
    let (Some(separator), None) = (separators.next(), separators.next()) else {
        return Err(ScanError::located(sql, REF_TYPE_ARGUMENT_ERROR, start, end));
    };
    if text(python_strip(&raw[..separator])) != REF_TYPE_KEYWORD {
        return Err(ScanError::located(
            sql,
            "__ref(...) optional second argument must use the ref_type keyword",
            start,
            end,
        ));
    }
    match parse_name(&raw[separator + 1..], sql, start, end)?.as_str() {
        "reference" => Ok("reference"),
        "mutable" => Ok("mutable"),
        _ => Err(ScanError::located(
            sql,
            "__ref(...) ref_type value must be 'reference' or 'mutable'",
            start,
            end,
        )),
    }
}
