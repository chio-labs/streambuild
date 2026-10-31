//! ClickHouse-aware lexical scanning of authored SQL.
//!
//! Scans skip `--` and `#` line comments, `/* */` block comments and `'`, `"` and `` ` ``
//! quoted text, and recognise the compiler's own syntax outside them: `__source(...)` and
//! `__ref(...)` references, line-leading extension headers, top-level CTEs, the outer projection
//! list and `@macro(...)` calls. Positions count characters, not bytes, so offsets and spans match
//! the Python callers.
//!
//! Ported from SQLTide's Python scanner, which adapted Apache-2.0 SQLBuild
//! `sql_analysis/scanning.py`, `compile/refs/references.py` and the `sql_tests/core.py` CTE scanner
//! at 7e3b2f854f05.

mod ctes;
mod headers;
mod macros;
mod primitives;
mod projections;
mod references;
mod templates;

pub use ctes::{SqlCommonTableExpression, SqlTopLevelCtes, extract_top_level_ctes};
pub use headers::{SqlHeaderBlock, split_header_blocks};
pub use macros::find_next_macro_start;
pub use primitives::{
    ScanError, ScanErrorKind, ScanResult, SourceSpan, find_matching_parenthesis,
    find_next_unquoted_character, normalized_statement_sql, skip_block_comment, skip_line_comment,
    skip_quoted_text, skip_trivia, source_span, try_consume_keyword,
};
pub use projections::{outer_double_colon_type, outer_projection_spans, outer_star_span};
pub use references::{SqlReference, extract_references};
pub use templates::{
    RelationRewrite, append_template_predicate, merge_template_ctes, rewrite_template_relations,
};

#[cfg(test)]
mod tests;
