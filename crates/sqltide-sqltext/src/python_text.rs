//! Python `str` predicates the compiler must reproduce exactly.

/// Whether Python's `str.isspace` accepts `character`. Rust's `char::is_whitespace` omits the
/// four separator controls U+001C to U+001F that Python treats as whitespace.
#[must_use]
pub fn python_isspace(character: char) -> bool {
    character.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&character)
}
