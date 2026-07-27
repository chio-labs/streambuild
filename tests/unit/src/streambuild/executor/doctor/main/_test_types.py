from dataclasses import dataclass

from streambuild.adapter.models import CatalogRelation
from streambuild.executor.doctor.models import DoctorResult


@dataclass(frozen=True)
class DoctorCatalogInspectionTestCase:
    description: str
    relations: tuple[CatalogRelation, ...]
    expected_catalog_databases: tuple[str, ...]
    expected_result: DoctorResult
