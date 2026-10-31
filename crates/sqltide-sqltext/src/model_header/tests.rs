use super::{HeaderValue, MAX_HEADER_NESTING_DEPTH, parse_model_header};

fn text(value: &str) -> HeaderValue {
    HeaderValue::Text(value.to_owned())
}

#[test]
fn parses_literals_lists_and_maps_in_authored_order() {
    let parsed = parse_model_header(
        "engine \"MergeTree()\", order_by [a, 'b'], size 12, ratio .5, on true, off false, \
         gone null, settings (granularity 8192), retention (duration '7d')",
    )
    .expect("valid header");

    assert_eq!(
        parsed,
        vec![
            ("engine".to_owned(), text("MergeTree()")),
            (
                "order_by".to_owned(),
                HeaderValue::List(vec![text("a"), text("b")])
            ),
            ("size".to_owned(), HeaderValue::Integer("12".to_owned())),
            ("ratio".to_owned(), HeaderValue::Float(0.5)),
            ("on".to_owned(), HeaderValue::Bool(true)),
            ("off".to_owned(), HeaderValue::Bool(false)),
            ("gone".to_owned(), HeaderValue::Null),
            (
                "settings".to_owned(),
                HeaderValue::Map(vec![(
                    "granularity".to_owned(),
                    HeaderValue::Integer("8192".to_owned())
                )])
            ),
            (
                "retention".to_owned(),
                HeaderValue::Map(vec![("duration".to_owned(), text("7d"))])
            ),
        ]
    );
}

#[test]
fn word_followed_by_parentheses_becomes_a_single_entry_map() {
    let parsed = parse_model_header("kind incremental(unique_key id)").expect("valid header");

    assert_eq!(
        parsed,
        vec![(
            "kind".to_owned(),
            HeaderValue::Map(vec![(
                "incremental".to_owned(),
                HeaderValue::Map(vec![("unique_key".to_owned(), text("id"))])
            )])
        )]
    );
}

#[test]
fn repeated_key_keeps_first_position_and_last_value() {
    let parsed = parse_model_header("a 1, b 2, a 3").expect("valid header");

    assert_eq!(
        parsed,
        vec![
            ("a".to_owned(), HeaderValue::Integer("3".to_owned())),
            ("b".to_owned(), HeaderValue::Integer("2".to_owned())),
        ]
    );
}

#[test]
fn signed_and_partial_numbers_follow_the_python_patterns() {
    let parsed =
        parse_model_header("a +7, b -0, c 1., d -.25, e 1.2.3, f +, g 1e3").expect("valid header");

    assert_eq!(
        parsed,
        vec![
            ("a".to_owned(), HeaderValue::Integer("+7".to_owned())),
            ("b".to_owned(), HeaderValue::Integer("-0".to_owned())),
            ("c".to_owned(), HeaderValue::Float(1.0)),
            ("d".to_owned(), HeaderValue::Float(-0.25)),
            ("e".to_owned(), text("1.2.3")),
            ("f".to_owned(), text("+")),
            ("g".to_owned(), text("1e3")),
        ]
    );
}

#[test]
fn escapes_keep_the_next_character_and_positions_count_characters() {
    assert_eq!(
        parse_model_header(r#"d "say \"hi\" \\ é""#).expect("valid header"),
        vec![("d".to_owned(), text("say \"hi\" \\ é"))]
    );
    assert_eq!(
        parse_model_header("d 'é', x {").expect_err("brace"),
        "YAML-like brace mappings are not supported at position 9; use SQLBuild parenthesized \
         mapping syntax"
    );
}

#[test]
fn python_separator_controls_are_whitespace() {
    assert_eq!(
        parse_model_header("a\u{1c}1").expect("valid header"),
        vec![("a".to_owned(), HeaderValue::Integer("1".to_owned()))]
    );
}

#[test]
fn reports_each_syntax_error_with_the_python_message() {
    let cases: [(&str, &str); 9] = [
        (
            "engine: x",
            "unexpected ':' after key 'engine'; use SQLBuild syntax 'engine value'",
        ),
        (
            "engine",
            "unexpected token 'engine' without a value; quote values with spaces",
        ),
        (
            "a (b)",
            "unexpected token 'b' without a value; quote values with spaces",
        ),
        (
            "a x\"y\"",
            "unexpected double quote inside bare value at position 3; quote the whole value",
        ),
        ("a 'x", "unterminated single-quoted string at position 2"),
        ("a 'x\\", "unterminated escape at position 4"),
        ("a [1, 2", "expected value at position 7"),
        ("[a 1]", "expected key at position 0"),
        ("a )", "expected value at position 2"),
    ];
    for (header, message) in cases {
        assert_eq!(
            parse_model_header(header).expect_err(header),
            message,
            "{header}"
        );
    }
}

#[test]
fn empty_header_is_an_empty_map() {
    assert_eq!(parse_model_header(" \n ").expect("empty"), Vec::new());
}

#[test]
fn nesting_beyond_the_limit_is_rejected_without_overflowing_the_stack() {
    let accepted: String = format!(
        "a {}{}",
        "[".repeat(MAX_HEADER_NESTING_DEPTH),
        "]".repeat(MAX_HEADER_NESTING_DEPTH)
    );
    let rejected: String = format!("a {}", "[".repeat(100_000));

    assert!(parse_model_header(&accepted).is_ok());
    assert_eq!(
        parse_model_header(&rejected).expect_err("too deep"),
        format!(
            "nesting deeper than {MAX_HEADER_NESTING_DEPTH} levels at position {}",
            2 + MAX_HEADER_NESTING_DEPTH + 1
        )
    );
}
