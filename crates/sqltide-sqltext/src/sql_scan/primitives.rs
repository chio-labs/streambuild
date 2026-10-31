//! Spans, errors and the comment, quoted text and parenthesis primitives every scan builds on.

use crate::python_text::{python_isalnum, python_isalpha, python_isspace, python_upper};

pub(super) const REFERENCE_CONTEXT: &str = "SQL reference";

/// A half-open character range with 1-based line and column numbers for both ends.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SourceSpan {
    pub start: usize,
    pub end: usize,
    pub line: usize,
    pub column: usize,
    pub end_line: usize,
    pub end_column: usize,
}

/// Which caller-visible failure a scan error represents.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ScanErrorKind {
    Analysis,
    MissingWithClause,
}

/// A scan failure with the message and span the Python implementation reported.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ScanError {
    pub kind: ScanErrorKind,
    pub message: String,
    pub span: Option<SourceSpan>,
}

impl ScanError {
    pub(super) fn located(
        sql: &[char],
        message: impl Into<String>,
        start: usize,
        end: usize,
    ) -> Self {
        Self {
            kind: ScanErrorKind::Analysis,
            message: message.into(),
            span: Some(source_span(sql, start, end)),
        }
    }

    pub(super) fn unlocated(message: impl Into<String>) -> Self {
        Self {
            kind: ScanErrorKind::Analysis,
            message: message.into(),
            span: None,
        }
    }
}

pub type ScanResult<T> = Result<T, ScanError>;

/// Build the span from `start` to `end`.
#[must_use]
pub fn source_span(sql: &[char], start: usize, end: usize) -> SourceSpan {
    let (line, column) = line_and_column(sql, start);
    let (end_line, end_column) = line_and_column(sql, end);
    SourceSpan {
        start,
        end,
        line,
        column,
        end_line,
        end_column,
    }
}

fn line_and_column(sql: &[char], offset: usize) -> (usize, usize) {
    let prefix: &[char] = &sql[..offset.min(sql.len())];
    let line: usize = prefix
        .iter()
        .filter(|character| **character == '\n')
        .count()
        + 1;
    let column: usize = match prefix.iter().rposition(|character| *character == '\n') {
        None => offset + 1,
        Some(newline) => offset - newline,
    };
    (line, column)
}

pub(super) fn text(characters: &[char]) -> String {
    characters.iter().collect()
}

pub(super) fn starts_with(sql: &[char], index: usize, pattern: &str) -> bool {
    (index..)
        .zip(pattern.chars())
        .all(|(position, expected)| sql.get(position) == Some(&expected))
}

pub(super) fn is_quote(character: char) -> bool {
    matches!(character, '\'' | '"' | '`')
}

pub(super) fn is_identifier_start(character: char) -> bool {
    character == '_' || python_isalpha(character)
}

pub(super) fn is_identifier_character(character: char) -> bool {
    character == '_' || python_isalnum(character)
}

fn is_line_comment_start(sql: &[char], index: usize) -> bool {
    starts_with(sql, index, "--") || sql.get(index) == Some(&'#')
}

fn find_char(sql: &[char], target: char, start: usize) -> Option<usize> {
    sql.get(start..)?
        .iter()
        .position(|character| *character == target)
        .map(|offset| start + offset)
}

/// Skip quoted text starting at `start`, honouring doubled and backslash-escaped delimiters.
///
/// # Errors
///
/// Returns an error when the quoted text is not closed.
pub fn skip_quoted_text(sql: &[char], start: usize) -> ScanResult<usize> {
    let quote: char = sql[start];
    let mut index: usize = start + 1;
    while index < sql.len() {
        if sql[index] == '\\' && index + 1 < sql.len() {
            index += 2;
            continue;
        }
        if sql[index] == quote {
            if index + 1 < sql.len() && sql[index + 1] == quote {
                index += 2;
                continue;
            }
            return Ok(index + 1);
        }
        index += 1;
    }
    Err(ScanError::located(
        sql,
        format!("{REFERENCE_CONTEXT} contains unclosed quoted text"),
        start,
        sql.len(),
    ))
}

/// Skip one line comment, including its newline.
#[must_use]
pub fn skip_line_comment(sql: &[char], start: usize) -> usize {
    find_char(sql, '\n', start).map_or(sql.len(), |newline| newline + 1)
}

/// Skip one block comment.
///
/// # Errors
///
/// Returns an error when the comment is not closed.
pub fn skip_block_comment(sql: &[char], start: usize) -> ScanResult<usize> {
    let mut index: usize = start + 2;
    while index + 1 < sql.len() {
        if sql[index] == '*' && sql[index + 1] == '/' {
            return Ok(index + 2);
        }
        index += 1;
    }
    Err(ScanError::located(
        sql,
        format!("{REFERENCE_CONTEXT} contains an unclosed block comment"),
        start,
        sql.len(),
    ))
}

/// The index after the comment or quoted text starting at `index`, or `None` when code starts there.
pub(super) fn skip_non_code(sql: &[char], index: usize) -> ScanResult<Option<usize>> {
    if is_line_comment_start(sql, index) {
        return Ok(Some(skip_line_comment(sql, index)));
    }
    if starts_with(sql, index, "/*") {
        return skip_block_comment(sql, index).map(Some);
    }
    if sql.get(index).copied().is_some_and(is_quote) {
        return skip_quoted_text(sql, index).map(Some);
    }
    Ok(None)
}

/// Find the parenthesis closing the one at `open_index`, skipping comments and quoted text.
///
/// # Errors
///
/// Returns an error naming `context` when the parenthesis is not closed.
pub fn find_matching_parenthesis(
    sql: &[char],
    open_index: usize,
    context: &str,
) -> ScanResult<usize> {
    let mut depth: usize = 1;
    let mut index: usize = open_index + 1;
    while index < sql.len() {
        if let Some(next) = skip_non_code(sql, index)? {
            index = next;
            continue;
        }
        match sql[index] {
            '(' => depth += 1,
            ')' => {
                depth -= 1;
                if depth == 0 {
                    return Ok(index);
                }
            }
            _ => {}
        }
        index += 1;
    }
    Err(ScanError::located(
        sql,
        format!("{context} contains an unclosed parenthesis"),
        open_index,
        sql.len(),
    ))
}

/// Find `target` outside comments and quoted text.
///
/// # Errors
///
/// Returns an error for unclosed quoted text or block comments before the match.
pub fn find_next_unquoted_character(
    sql: &[char],
    target: char,
    start: usize,
) -> ScanResult<Option<usize>> {
    let mut index: usize = start;
    while index < sql.len() {
        if let Some(next) = skip_non_code(sql, index)? {
            index = next;
            continue;
        }
        if sql[index] == target {
            return Ok(Some(index));
        }
        index += 1;
    }
    Ok(None)
}

/// Skip whitespace and comments.
///
/// # Errors
///
/// Returns an error for an unclosed block comment.
pub fn skip_trivia(sql: &[char], start: usize) -> ScanResult<usize> {
    let mut index: usize = start;
    while index < sql.len() {
        if python_isspace(sql[index]) {
            index += 1;
        } else if is_line_comment_start(sql, index) {
            index = skip_line_comment(sql, index);
        } else if starts_with(sql, index, "/*") {
            index = skip_block_comment(sql, index)?;
        } else {
            break;
        }
    }
    Ok(index)
}

/// The index after a case-insensitive `keyword` at `start` that no identifier character follows.
#[must_use]
pub fn try_consume_keyword(sql: &[char], start: usize, keyword: &str) -> Option<usize> {
    let keyword: Vec<char> = keyword.chars().collect();
    let end: usize = start + keyword.len();
    let candidate: &[char] = &sql[start.min(sql.len())..end.min(sql.len())];
    if python_upper(candidate) != python_upper(&keyword) {
        return None;
    }
    if end < sql.len() && is_identifier_character(sql[end]) {
        return None;
    }
    Some(end)
}

/// Remove one terminal statement delimiter while keeping trailing comments and whitespace.
///
/// # Errors
///
/// Returns an error for unclosed quoted text or block comments.
pub fn normalized_statement_sql(sql: &[char]) -> ScanResult<String> {
    let mut index: usize = 0;
    let mut last_significant: Option<usize> = None;
    while index < sql.len() {
        if is_line_comment_start(sql, index) {
            index = skip_line_comment(sql, index);
        } else if starts_with(sql, index, "/*") {
            index = skip_block_comment(sql, index)?;
        } else if is_quote(sql[index]) {
            index = skip_quoted_text(sql, index)?;
            last_significant = Some(index - 1);
        } else {
            if !python_isspace(sql[index]) {
                last_significant = Some(index);
            }
            index += 1;
        }
    }
    Ok(match last_significant {
        Some(delimiter) if sql[delimiter] == ';' => {
            text(&sql[..delimiter]) + &text(&sql[delimiter + 1..])
        }
        _ => text(sql),
    })
}
