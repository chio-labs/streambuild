//! Line-leading `KEYWORD (...);` extension headers such as `MODEL (...);`.

use super::primitives::{
    ScanError, ScanResult, find_matching_parenthesis, is_identifier_character, skip_non_code,
    skip_trivia, starts_with, text,
};
use crate::python_text::python_isspace;

/// One extension header and the SQL body that follows it up to the next header.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SqlHeaderBlock {
    pub start: usize,
    pub body_start: usize,
    pub header: String,
    pub body: String,
}

/// Split SQL at each line-leading `keyword (...);` header outside comments and quoted text.
///
/// # Errors
///
/// Returns an error for a header without a terminating semicolon or for unclosed syntax.
pub fn split_header_blocks(sql: &[char], keyword: &str) -> ScanResult<Vec<SqlHeaderBlock>> {
    let mut markers: Vec<(usize, usize, usize)> = Vec::new();
    let mut index: usize = 0;
    while index < sql.len() {
        if let Some(next) = skip_non_code(sql, index)? {
            index = next;
            continue;
        }
        if let Some(marker) = header_marker(sql, keyword, index)? {
            index = marker.2;
            markers.push(marker);
            continue;
        }
        index += 1;
    }
    let mut blocks: Vec<SqlHeaderBlock> = Vec::with_capacity(markers.len());
    for (position, (start, header_start, body_start)) in markers.iter().copied().enumerate() {
        let next_start: usize = markers.get(position + 1).map_or(sql.len(), |next| next.0);
        let close_index: usize =
            find_matching_parenthesis(sql, header_start - 1, "SQL extension header")?;
        blocks.push(SqlHeaderBlock {
            start,
            body_start,
            header: text(&sql[header_start..close_index]),
            body: text(&sql[body_start..next_start]),
        });
    }
    Ok(blocks)
}

fn header_marker(
    sql: &[char],
    keyword: &str,
    start: usize,
) -> ScanResult<Option<(usize, usize, usize)>> {
    if !starts_with(sql, start, keyword) || !line_prefix_is_whitespace(sql, start) {
        return Ok(None);
    }
    let keyword_end: usize = start + keyword.chars().count();
    if keyword_end < sql.len() && is_identifier_character(sql[keyword_end]) {
        return Ok(None);
    }
    let open_index: usize = skip_trivia(sql, keyword_end)?;
    if sql.get(open_index) != Some(&'(') {
        return Ok(None);
    }
    let close_index: usize =
        find_matching_parenthesis(sql, open_index, &format!("{keyword} header"))?;
    let semicolon_index: usize = skip_trivia(sql, close_index + 1)?;
    if sql.get(semicolon_index) != Some(&';') {
        return Err(ScanError::unlocated(format!(
            "{keyword} header must end with a semicolon"
        )));
    }
    Ok(Some((start, open_index + 1, semicolon_index + 1)))
}

fn line_prefix_is_whitespace(sql: &[char], start: usize) -> bool {
    let line_start: usize = sql[..start]
        .iter()
        .rposition(|character| *character == '\n')
        .map_or(0, |newline| newline + 1);
    sql[line_start..start]
        .iter()
        .all(|character| python_isspace(*character))
}
