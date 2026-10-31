from dataclasses import dataclass

from sqltide.adapter.models import CatalogRelation
from sqltide.executor.doctor.models import DoctorResult


@dataclass(frozen=True)
class DoctorCatalogInspectionTestCase:
    description: str
    relations: tuple[CatalogRelation, ...]
    expected_catalog_databases: tuple[str, ...]
    expected_result: DoctorResult
