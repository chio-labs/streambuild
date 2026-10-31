//! Authored `@name(...)` macro call sites outside comments and quoted text.

use super::primitives::{
    ScanResult, find_next_unquoted_character, is_identifier_character, is_identifier_start,
};
use crate::python_text::python_isspace;

/// The index of the next `@name(` macro call at or after `start`.
///
/// # Errors
///
/// Returns an error for unclosed quoted text or block comments before the call.
pub fn find_next_macro_start(sql: &[char], start: usize) -> ScanResult<Option<usize>> {
    let mut candidate: Option<usize> = find_next_unquoted_character(sql, '@', start)?;
    while let Some(index) = candidate {
        if is_macro_call_start(sql, index) {
            return Ok(Some(index));
        }
        candidate = find_next_unquoted_character(sql, '@', index + 1)?;
    }
    Ok(None)
}

fn is_macro_call_start(sql: &[char], at_index: usize) -> bool {
    if at_index > 0 && is_identifier_character(sql[at_index - 1]) {
        return false;
    }
    if !sql
        .get(at_index + 1)
        .copied()
        .is_some_and(is_identifier_start)
    {
        return false;
    }
    let cursor: usize = skip_whitespace(sql, macro_name_end(sql, at_index));
    sql.get(cursor) == Some(&'(')
}

fn macro_name_end(sql: &[char], call_start: usize) -> usize {
    let mut cursor: usize = call_start + 1;
    while cursor < sql.len() && is_identifier_character(sql[cursor]) {
        cursor += 1;
    }
    cursor
}

fn skip_whitespace(sql: &[char], start: usize) -> usize {
    let mut index: usize = start;
    while index < sql.len() && python_isspace(sql[index]) {
        index += 1;
    }
    index
}
