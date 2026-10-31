//! Resolution caching bounds. Analysis behaviour is covered through the Python compiler tests.

use crate::{
    ExpectedReference, ParsedModel, ProjectionTypeCache, RelationCache, SqlDialect, analyze_model,
    validated_relation_rewrite,
};

fn references(sql: &str, name: &str) -> Vec<ExpectedReference> {
    let needle: String = format!("__ref(\"{name}\")");
    sql.match_indices(&needle)
        .map(|(byte_start, _)| {
            let start: usize = sql[..byte_start].chars().count();
            ExpectedReference {
                relation_type: "ref".to_owned(),
                name: name.to_owned(),
                ref_type: None,
                start,
                end: start + needle.chars().count(),
            }
        })
        .collect()
}

#[test]
fn repeated_targets_are_parsed_and_generated_once_per_invocation() {
    let dialect: SqlDialect = SqlDialect::new("clickhouse");
    let resolver = |name: &str| (name == "orders").then(|| "tbl__orders".to_owned());
    let mut type_cache: ProjectionTypeCache = ProjectionTypeCache::new();
    let mut cache: RelationCache = RelationCache::default();
    let models: [&str; 2] = [
        r#"SELECT CAST(a.id AS UInt64) AS id FROM __ref("orders") AS a JOIN __ref("orders") AS b ON a.id = b.id"#,
        r#"SELECT CAST(count() AS UInt64) AS orders FROM __ref("orders")"#,
    ];
    for sql in models {
        let model: ParsedModel = analyze_model(sql, &dialect, &mut type_cache).expect("analyzes");
        let references: Vec<ExpectedReference> = references(sql, "orders");
        let resolved = cache
            .resolve(&model, sql, &references, &resolver, &dialect, "__db__")
            .expect("resolves");
        assert!(resolved.database_template.contains("__db__.tbl__orders"));
        assert!(!resolved.canonical_sql.contains("__ref"));
    }
    assert_eq!(cache.parses, 1);
    assert_eq!(cache.generations, 2);
}

#[test]
fn shared_rewrite_cache_reuses_relations_across_queries() {
    let dialect: SqlDialect = SqlDialect::new("clickhouse");
    let resolver = |name: &str| (name == "orders").then(|| "analytics.orders".to_owned());
    let mut cache: RelationCache = RelationCache::default();
    for sql in [
        r#"SELECT * FROM __ref("orders") first_orders"#,
        r#"SELECT count() FROM __ref("orders") second_orders"#,
    ] {
        let rewritten: Vec<(String, String)> = validated_relation_rewrite(
            sql,
            &references(sql, "orders"),
            &resolver,
            &mut cache,
            &dialect,
        )
        .expect("rewrites");
        assert_eq!(
            rewritten,
            vec![("analytics.orders".to_owned(), "analytics.orders".to_owned())]
        );
    }
    assert_eq!(cache.parses, 1);
    assert_eq!(cache.generations, 1);
}
