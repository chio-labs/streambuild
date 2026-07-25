def build_ref_resolver() -> dict[str, str]:
    return {
        "orders": "raw__orders",
        "customers": "tbl__customers",
    }
