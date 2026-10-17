"""Importing this package registers every model on ``Base.metadata``."""
from app.models.artifact import Artifact, ArtifactFormat, ArtifactType
from app.models.audit import AuditActorType, AuditLog
from app.models.company import (
    Company,
    CompanyCertification,
    CompanyEquipment,
    CompanyPastProject,
    CompanyWorkforceRole,
)
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
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
from app.models.financial_model import (
    CostBehavior,
    CostCategory,
    FinancialCostItem,
    FinancialModel,
)
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.resource import ProjectResource, ResourceType
from app.models.risk import Risk, RiskCategory, RiskStatus
from app.models.scenario import Scenario, ScenarioKind

__all__ = [
    "Artifact",
    "ArtifactFormat",
    "ArtifactType",
    "AuditActorType",
    "AuditLog",
    "Company",
    "CompanyCertification",
    "CompanyEquipment",
    "CompanyPastProject",
    "CompanyWorkforceRole",
    "CostBehavior",
    "CostCategory",
    "Document",
    "DocumentChunk",
    "DocumentType",
    "EquipmentOwnership",
    "ExtractedFact",
    "FactType",
    "FinancialCostItem",
    "FinancialModel",
    "MatchStatus",
    "ProcessingStatus",
    "Project",
    "ProjectResource",
    "ProjectStatus",
    "Requirement",
    "RequirementCategory",
    "RequirementOrigin",
    "ResourceType",
    "Risk",
    "RiskCategory",
    "RiskStatus",
    "Scenario",
    "ScenarioKind",
    "VerificationStatus",
]