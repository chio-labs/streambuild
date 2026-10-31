//! The Polyglot entry points SQL analysis uses, returning the same serde trees and error text as
//! the `polyglot-sql` Python package built from this engine.

use polyglot_sql::{AnalyzeQueryOptions, Dialect, DialectType, Error, Expression, ast_json};
use pyo3::create_exception;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use pythonize::{depythonize, pythonize};

create_exception!(_native, PolyglotError, PyValueError);

fn failure(error: impl ToString) -> PyErr {
    PolyglotError::new_err(error.to_string())
}

fn dialect(name: &str) -> PyResult<Dialect> {
    Dialect::get_by_name(name)
        .ok_or_else(|| PyValueError::new_err(format!("Unknown dialect: {name}")))
}

fn to_python<'py, T: serde::Serialize>(py: Python<'py>, value: &T) -> PyResult<Bound<'py, PyAny>> {
    pythonize(py, value).map_err(failure)
}

#[pyfunction]
fn polyglot_parse<'py>(
    py: Python<'py>,
    sql: &str,
    dialect_name: &str,
) -> PyResult<Vec<Bound<'py, PyAny>>> {
    let dialect: Dialect = dialect(dialect_name)?;
    let expressions: Vec<Expression> = py.detach(|| dialect.parse(sql)).map_err(failure)?;
    expressions
        .iter()
        .map(|expression| to_python(py, expression))
        .collect()
}

#[pyfunction]
fn polyglot_parse_one<'py>(
    py: Python<'py>,
    sql: &str,
    dialect_name: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let dialect: Dialect = dialect(dialect_name)?;
    let mut expressions: Vec<Expression> = py.detach(|| dialect.parse(sql)).map_err(failure)?;
    if expressions.len() != 1 {
        return Err(failure(format!(
            "Expected 1 statement, found {}",
            expressions.len()
        )));
    }
    to_python(py, &expressions.remove(0))
}

/// Parse one data type and generate it back, which canonicalises its spelling for the dialect.
#[pyfunction]
fn polyglot_generate_data_type(sql: &str, dialect_name: &str) -> PyResult<String> {
    let dialect_type: DialectType = dialect(dialect_name)?.dialect_type();
    let data_type = polyglot_sql::parse_data_type(sql, dialect_type).map_err(failure)?;
    polyglot_sql::generate_data_type(&data_type, dialect_type).map_err(failure)
}

#[pyfunction]
#[pyo3(signature = (tree, dialect_name, pretty = false))]
fn polyglot_generate(
    tree: &Bound<'_, PyDict>,
    dialect_name: &str,
    pretty: bool,
) -> PyResult<String> {
    let dialect: Dialect = dialect(dialect_name)?;
    let value: serde_json::Value = depythonize(tree)
        .map_err(|error| failure(format!("Failed to decode AST expression: {error}")))?;
    let expression: Expression = ast_json::expression_from_value(value)
        .map_err(|error| failure(format!("Failed to decode AST expression: {error}")))?;
    let generated: Result<String, Error> = if pretty {
        dialect.generate_pretty(&expression)
    } else {
        dialect.generate(&expression)
    };
    generated.map_err(failure)
}

#[pyfunction]
fn polyglot_analyze_query<'py>(
    py: Python<'py>,
    sql: &str,
    dialect_name: &str,
) -> PyResult<Bound<'py, PyAny>> {
    let options = AnalyzeQueryOptions {
        dialect: dialect(dialect_name)?.dialect_type(),
        ..AnalyzeQueryOptions::default()
    };
    let analysis = py
        .detach(|| polyglot_sql::analyze_query(sql, options))
        .map_err(failure)?;
    to_python(py, &analysis)
}

pub(crate) fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("PolyglotError", module.py().get_type::<PolyglotError>())?;
    module.add_function(wrap_pyfunction!(polyglot_parse, module)?)?;
    module.add_function(wrap_pyfunction!(polyglot_parse_one, module)?)?;
    module.add_function(wrap_pyfunction!(polyglot_generate_data_type, module)?)?;
    module.add_function(wrap_pyfunction!(polyglot_generate, module)?)?;
    module.add_function(wrap_pyfunction!(polyglot_analyze_query, module)?)?;
    Ok(())
}
