//! Byte-preserving edits to rendered query templates: relation renames, an outer predicate and
//! prepended CTEs.

use super::primitives::{
    ScanResult, is_identifier_character, is_identifier_start, is_quote, skip_quoted_text,
    skip_trivia, text, try_consume_keyword,
};
use crate::python_text::{python_strip, python_upper};

const PREDICATE_BOUNDARY_KEYWORDS: [&str; 12] = [
    "GROUP",
    "HAVING",
    "WINDOW",
    "QUALIFY",
    "ORDER",
    "LIMIT",
    "OFFSET",
    "SETTINGS",
    "FORMAT",
    "UNION",
    "EXCEPT",
    "INTERSECT",
];

/// One placeholder-qualified relation to replace in a template.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RelationRewrite {
    pub source_name: String,
    pub target_relation: String,
    pub preserve_source_database: bool,
}

/// Replace each `placeholder.source_name` token bounded by non-identifier characters.
#[must_use]
pub fn rewrite_template_relations(
    template: &str,
    rewrites: &[RelationRewrite],
    database_placeholder: &str,
) -> String {
    let mut rewritten: String = template.to_owned();
    for rewrite in rewrites {
        let replacement: String = if rewrite.preserve_source_database {
            format!("{database_placeholder}.{}", rewrite.target_relation)
        } else {
            rewrite.target_relation.clone()
        };
        let token: String = format!("{database_placeholder}.{}", rewrite.source_name);
        rewritten = replace_bounded_token(&rewritten, &token, &replacement);
    }
    rewritten
}

fn replace_bounded_token(template: &str, token: &str, replacement: &str) -> String {
    let mut output: String = String::with_capacity(template.len());
    let mut cursor: usize = 0;
    while let Some(offset) = template[cursor..].find(token) {
        let index: usize = cursor + offset;
        let end: usize = index + token.len();
        let bounded_before: bool = template[..index]
            .chars()
            .next_back()
            .is_none_or(|character| !is_identifier_character(character));
        let bounded_after: bool = template[end..]
            .chars()
            .next()
            .is_none_or(|character| !is_identifier_character(character));
        if bounded_before && bounded_after {
            output.push_str(&template[cursor..index]);
            output.push_str(replacement);
        } else {
            output.push_str(&template[cursor..end]);
        }
        cursor = end;
    }
    output.push_str(&template[cursor..]);
    output
}

/// Conjoin `predicate` into the outer `WHERE` clause, adding one when absent.
///
/// # Errors
///
/// Returns an error for unclosed quoted text or block comments.
pub fn append_template_predicate(template: &[char], predicate: &str) -> ScanResult<String> {
    let (where_end, boundary) = outer_predicate_positions(template)?;
    let head: String = text(&template[..boundary]);
    let tail: String = text(&template[boundary..]);
    let Some(where_end) = where_end else {
        if boundary == template.len() {
            return Ok(format!("{head}\nWHERE ({predicate})"));
        }
        return Ok(format!("{head}WHERE ({predicate})\n{tail}"));
    };
    let segment: String = text(python_strip(&template[where_end..boundary]));
    let tail: String = if boundary == template.len() {
        String::new()
    } else {
        format!("\n{tail}")
    };
    Ok(format!(
        "{} ({segment}) AND ({predicate}){tail}",
        text(&template[..where_end])
    ))
}

fn outer_predicate_positions(template: &[char]) -> ScanResult<(Option<usize>, usize)> {
    let mut where_end: Option<usize> = None;
    let mut depth: usize = 0;
    let mut index: usize = 0;
    while index < template.len() {
        index = skip_trivia(template, index)?;
        if index >= template.len() {
            break;
        }
        let character: char = template[index];
        if is_quote(character) {
            index = skip_quoted_text(template, index)?;
            continue;
        }
        if character == '(' {
            depth += 1;
            index += 1;
            continue;
        }
        if character == ')' {
            depth = depth.saturating_sub(1);
            index += 1;
            continue;
        }
        if !is_identifier_start(character) {
            index += 1;
            continue;
        }
        let mut end: usize = index + 1;
        while end < template.len() && is_identifier_character(template[end]) {
            end += 1;
        }
        let word: String = python_upper(&template[index..end]);
        if depth == 0 && word == "WHERE" && where_end.is_none() {
            where_end = Some(end);
        } else if depth == 0 && PREDICATE_BOUNDARY_KEYWORDS.contains(&word.as_str()) {
            return Ok((where_end, index));
        }
        index = end;
    }
    Ok((where_end, template.len()))
}

/// Prepend `(name, query)` CTEs into the template's leading `WITH` clause, adding one when absent.
///
/// # Errors
///
/// Returns an error for an unclosed block comment.
pub fn merge_template_ctes(
    template: &[char],
    named_queries: &[(String, String)],
) -> ScanResult<String> {
    if named_queries.is_empty() {
        return Ok(text(template));
    }
    let rendered: String = named_queries
        .iter()
        .map(|(name, query)| format!("{name} AS (\n{query}\n)"))
        .collect::<Vec<String>>()
        .join(",\n");
    let offset: usize = skip_trivia(template, 0)?;
    let Some(with_end) = try_consume_keyword(template, offset, "WITH") else {
        return Ok(format!("WITH {rendered}\n{}", text(template)));
    };
    let trivia_end: usize = skip_trivia(template, with_end)?;
    let insertion_point: usize =
        try_consume_keyword(template, trivia_end, "RECURSIVE").unwrap_or(with_end);
    Ok(format!(
        "{} {rendered},{}",
        text(&template[..insertion_point]),
        text(&template[insertion_point..])
    ))
}
