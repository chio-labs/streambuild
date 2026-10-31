//! Recognise ClickHouse aggregate functions among the keys and payloads of a parsed tree.

use serde_json::Value;

use crate::tree::{object, text};
use crate::vocabulary::{
    AGGREGATE_COMBINATORS, AGGREGATE_FUNCTION_NAMES, AGGREGATE_STATE_FUNCTION_NAMES,
};

const FUNCTION_KEY: &str = "function";
const AGGREGATE_FUNCTION_KEY: &str = "aggregate_function";
const COMBINED_PARAMETERIZED_AGGREGATE_KEY: &str = "combined_parameterized_agg";

/// The aggregate function name one `key: payload` entry contributes, if any.
///
/// Generic function payloads contribute their name when it is a ClickHouse aggregate. Any other
/// key contributes itself when Polyglot spells that aggregate as a dedicated variant key.
pub(crate) fn aggregate_key_name<'a>(key: &'a str, payload: &'a Value) -> Option<&'a str> {
    if matches!(
        key,
        FUNCTION_KEY | AGGREGATE_FUNCTION_KEY | COMBINED_PARAMETERIZED_AGGREGATE_KEY
    ) {
        return function_name(key, payload).filter(|name| is_clickhouse_aggregate(name));
    }
    keyed_function_name(key)
}

fn keyed_function_name(key: &str) -> Option<&str> {
    if is_aggregate_function_name(key) {
        return Some(key);
    }
    (!python_islower(key) && is_aggregate_function_name(&key.to_lowercase())).then_some(key)
}

fn function_name<'a>(key: &'a str, payload: &'a Value) -> Option<&'a str> {
    if matches!(key, FUNCTION_KEY | AGGREGATE_FUNCTION_KEY)
        && let Some(function) = payload.as_object()
    {
        return text(function.get("name"));
    }
    if key == COMBINED_PARAMETERIZED_AGGREGATE_KEY
        && let Some(identifier) = object(object(Some(payload)).and_then(|agg| agg.get("this")))
            .and_then(|wrapper| object(wrapper.get("identifier")))
    {
        return text(identifier.get("name"));
    }
    is_aggregate_function_name(&key.to_lowercase()).then_some(key)
}

fn is_clickhouse_aggregate(function_name: &str) -> bool {
    let lowered: String = function_name.to_lowercase();
    if is_aggregate_function_name(&lowered) || AGGREGATE_STATE_FUNCTION_NAMES.contains(&&*lowered) {
        return true;
    }
    let mut base: Vec<char> = function_name.chars().collect();
    'strip: loop {
        let lowered_base: String = base.iter().collect::<String>().to_lowercase();
        for combinator in AGGREGATE_COMBINATORS {
            if lowered_base.ends_with(&combinator.to_lowercase()) {
                base.truncate(base.len().saturating_sub(combinator.chars().count()));
                continue 'strip;
            }
        }
        break;
    }
    is_aggregate_function_name(&base.iter().collect::<String>().to_lowercase())
}

fn is_aggregate_function_name(name: &str) -> bool {
    AGGREGATE_FUNCTION_NAMES.binary_search(&name).is_ok()
}

/// Python's `str.islower()`: at least one cased character and no uppercase ones.
fn python_islower(text: &str) -> bool {
    let mut cased: bool = false;
    for character in text.chars() {
        if character.is_uppercase() {
            return false;
        }
        cased |= character.is_lowercase();
    }
    cased
}
