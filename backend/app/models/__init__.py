"""Importing this package registers every model on ``Base.metadata``."""
from app.models.company import (
    Company,
    CompanyCertification,
    CompanyEquipment,
    CompanyPastProject,
    CompanyWorkforceRole,
)
from app.models.document import Document
from app.models.enums import (
    DocumentType,
    EquipmentOwnership,
    FactType,
    MatchStatus,
    ProcessingStatus,
    ProjectStatus,
    RequirementCategory,
    RequirementOrigin,
    VerificationStatus,
)
from app.models.extracted_fact import ExtractedFact
from app.models.project import Project
from app.models.requirement import Requirement

__all__ = [
    "Company",
    "CompanyCertification",
    "CompanyEquipment",
    "CompanyPastProject",
    "CompanyWorkforceRole",
    "Document",
    "DocumentType",
    "EquipmentOwnership",
    "ExtractedFact",
    "FactType",
    "MatchStatus",
    "ProcessingStatus",
    "Project",
    "ProjectStatus",
    "Requirement",
    "RequirementCategory",
    "RequirementOrigin",
    "VerificationStatus",
]
