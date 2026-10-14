"""Enumerations shared by the ORM models.

Values are the human-readable labels from the PRD. They are stored as those strings
(not as member names), with a CHECK constraint on each column.
"""
import enum


class VerificationStatus(str, enum.Enum):
    """Trust level of a stored fact. Extracted values start as REQUIRES_REVIEW and
    only become VERIFIED when a person confirms them."""

    VERIFIED = "Verified"
    ESTIMATED = "Estimated"
    ASSUMPTION = "Assumption"
    MISSING = "Missing"
    CONFLICTING = "Conflicting"
    REQUIRES_REVIEW = "Requires review"
    OUTDATED = "Outdated"
    REJECTED = "Rejected"


class MatchStatus(str, enum.Enum):
    """Result of comparing a requirement with company evidence. UNKNOWN is the default
    and is never upgraded just because related words appear."""

    MET = "Met"
    PARTIALLY_MET = "Partially met"
    NOT_MET = "Not met"
    UNKNOWN = "Unknown"
    NOT_APPLICABLE = "Not applicable"


class ProjectStatus(str, enum.Enum):
    DRAFT = "draft"
    ANALYSING = "analysing"
    IN_REVIEW = "in_review"
    PURSUING = "pursuing"
    DECLINED = "declined"
    ARCHIVED = "archived"


class DocumentType(str, enum.Enum):
    # Project-side (tender) documents
    TENDER = "tender"
    TENDER_ADDENDUM = "tender_addendum"
    BILL_OF_QUANTITIES = "bill_of_quantities"
    SPECIFICATION = "specification"
    CONTRACT = "contract"
    # Company-side documents
    CERTIFICATE = "certificate"
    PAST_PROJECTS = "past_projects"
    EQUIPMENT_REGISTER = "equipment_register"
    COMPANY_PROFILE = "company_profile"
    OTHER = "other"


class ProcessingStatus(str, enum.Enum):
    QUEUED = "queued"
    EXTRACTING = "extracting"
    ANALYSING = "analysing"
    DONE = "done"
    FAILED = "failed"


class RequirementCategory(str, enum.Enum):
    ELIGIBILITY = "eligibility"
    TECHNICAL = "technical"
    FINANCIAL = "financial"
    CERTIFICATION = "certification"
    LEGAL_CONTRACTUAL = "legal_contractual"
    SCHEDULE = "schedule"
    DELIVERABLE = "deliverable"
    DOCUMENTATION = "documentation"
    EVALUATION = "evaluation"
    OTHER = "other"


class RequirementOrigin(str, enum.Enum):
    EXTRACTED = "extracted"
    MANUAL = "manual"


class FactType(str, enum.Enum):
    DATE = "date"
    COST = "cost"
    QUANTITY = "quantity"
    DELIVERABLE = "deliverable"
    ROLE = "role"
    DEPENDENCY = "dependency"
    CONTRACT_CONDITION = "contract_condition"
    ELIGIBILITY_CRITERION = "eligibility_criterion"
    CERTIFICATION = "certification"
    EQUIPMENT = "equipment"
    LOCATION = "location"
    OTHER = "other"


class EquipmentOwnership(str, enum.Enum):
    OWNED = "owned"
    LEASED = "leased"
    UNKNOWN = "unknown"
