"""Manifest compiler type aliases."""

from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterTable,
    AdapterView,
)

type ManifestAdapterResource = (
    AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterView
)
