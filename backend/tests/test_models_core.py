"""Tests for Company, Project, Document, Requirement and ExtractedFact."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, StatementError

from app.models import (
    Company,
    CompanyCertification,
    CompanyEquipment,
    CompanyPastProject,
    CompanyWorkforceRole,
    Document,
    DocumentType,
    ExtractedFact,
    MatchStatus,
    ProcessingStatus,
    Project,
    ProjectStatus,
    Requirement,
    RequirementCategory,
    VerificationStatus,
)

SHA = "a" * 64


def make_company(session, **kw):
    c = Company(name=kw.pop("name", "Acme Steel Works"), **kw)
    session.add(c)
    session.flush()
    return c


def make_project(session, company, **kw):
    p = Project(company_id=company.id, name=kw.pop("name", "Steel Factory"), **kw)
    session.add(p)
    session.flush()
    return p


_counter = iter(range(1, 10_000))


def make_doc(session, *, project=None, company=None, **kw):
    d = Document(
        project_id=project.id if project else None,
        company_id=company.id if company else None,
        original_filename=kw.pop("original_filename", "tender.pdf"),
        storage_path=kw.pop("storage_path", f"uploads/{next(_counter)}.pdf"),
        **kw,
    )
    session.add(d)
    session.flush()
    return d


def make_fact(session, doc, **kw):
    f = ExtractedFact(
        document_id=doc.id,
        label=kw.pop("label", "Submission deadline"),
        value=kw.pop("value", "30 November 2026"),
        quotation=kw.pop("quotation", "Bids must be received by 30 November 2026."),
        **kw,
    )
    session.add(f)
    session.flush()
    return f


# --------------------------------------------------------------------------- happy path
def test_full_graph_and_relationships(session):
    company = make_company(session)
    project = make_project(session, company)
    tender = make_doc(session, project=project, document_type=DocumentType.TENDER)
    req = Requirement(
        project_id=project.id,
        source_document_id=tender.id,
        code="REQ-001",
        description="ISO 9001 certification",
        page_number=4,
        quotation="Bidders must hold ISO 9001.",
    )
    session.add(req)
    make_fact(session, tender)
    session.commit()

    assert project.company is company
    assert project in company.projects
    assert tender in project.documents
    assert req in project.requirements
    assert req.source_document is tender
    assert tender.requirements == [req]
    assert len(tender.extracted_facts) == 1
    assert tender.extracted_facts[0].document is tender


def test_defaults_are_conservative(session):
    company = make_company(session)
    project = make_project(session, company)
    doc = make_doc(session, project=project)
    req = Requirement(project_id=project.id, code="REQ-001", description="x")
    fact = make_fact(session, doc)
    session.add(req)
    session.commit()

    assert req.match_status is MatchStatus.UNKNOWN
    assert req.verification_status is VerificationStatus.REQUIRES_REVIEW
    assert req.is_mandatory is None  # "source does not say" stays unknown
    assert req.category is RequirementCategory.OTHER
    assert fact.verification_status is VerificationStatus.REQUIRES_REVIEW
    assert fact.last_verified_at is None
    assert doc.processing_status is ProcessingStatus.QUEUED
    assert doc.version == 1
    assert project.status is ProjectStatus.DRAFT
    assert company.locations == [] and company.field_verification == {}


def test_timestamps_are_aware_utc_and_updated_at_moves(session):
    company = make_company(session)
    session.commit()
    assert company.created_at.tzinfo is not None
    assert company.created_at.utcoffset() == timedelta(0)

    session.expire_all()  # force a real round trip through SQLite
    reloaded = session.get(Company, company.id)
    assert reloaded.created_at.tzinfo is not None
    before = reloaded.updated_at
    reloaded.name = "Renamed"
    session.commit()
    assert reloaded.updated_at > before


def test_naive_datetime_rejected(session):
    company = make_company(session)
    with pytest.raises((StatementError, ValueError), match="Naive datetime"):
        make_project(session, company, deadline=datetime(2026, 11, 30))


def test_deadline_round_trips_as_aware(session):
    company = make_company(session)
    when = datetime(2026, 11, 30, 17, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    project = make_project(session, company, deadline=when)
    session.commit()
    session.expire_all()
    got = session.get(Project, project.id).deadline
    assert got == when and got.utcoffset() == timedelta(0)


# --------------------------------------------------------------------------- company
def test_company_children_and_cascade(session):
    company = make_company(session)
    session.add_all(
        [
            CompanyWorkforceRole(company_id=company.id, role="Welder", headcount=12, available_headcount=5),
            CompanyEquipment(company_id=company.id, name="50t crane", quantity=2),
            CompanyCertification(
                company_id=company.id, name="ISO 9001", issued_date=date(2024, 1, 1), expiry_date=date(2027, 1, 1)
            ),
            CompanyPastProject(company_id=company.id, title="Warehouse", contract_value="1250000.505"),
        ]
    )
    session.commit()
    assert len(company.workforce_roles) == len(company.equipment) == 1
    assert company.past_projects[0].contract_value == Decimal("1250000.51")

    session.delete(company)
    session.commit()
    for model in (CompanyWorkforceRole, CompanyEquipment, CompanyCertification, CompanyPastProject):
        assert session.scalars(select(model)).all() == []


def test_employed_is_not_available(session):
    company = make_company(session)
    session.add(CompanyWorkforceRole(company_id=company.id, role="Welder", headcount=3))
    session.commit()
    assert session.scalars(select(CompanyWorkforceRole)).one().available_headcount is None

    session.add(CompanyWorkforceRole(company_id=company.id, role="Fitter", headcount=3, available_headcount=4))
    with pytest.raises(IntegrityError):
        session.flush()


def test_certification_dates_must_be_ordered(session):
    company = make_company(session)
    session.add(
        CompanyCertification(
            company_id=company.id, name="X", issued_date=date(2025, 1, 1), expiry_date=date(2024, 1, 1)
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_field_verification_tracking(session):
    company = make_company(session, industry="Steel fabrication", annual_revenue="5000000")
    assert company.get_field_status("legal_name") is VerificationStatus.MISSING
    assert company.get_field_status("industry") is VerificationStatus.REQUIRES_REVIEW

    company.set_field_verification("annual_revenue", VerificationStatus.ESTIMATED, source_document_id=7)
    company.set_field_verification("industry", VerificationStatus.VERIFIED)
    session.commit()
    session.expire_all()

    company = session.get(Company, company.id)
    assert company.get_field_status("annual_revenue") is VerificationStatus.ESTIMATED
    assert company.field_verification["industry"]["last_verified_at"] is not None


def test_field_verification_rejects_bad_input(session):
    company = make_company(session)
    with pytest.raises(ValueError):
        company.field_verification = {"favourite_colour": {"status": "Verified"}}
    with pytest.raises(ValueError):
        company.field_verification = {"industry": {"status": "Definitely"}}


# --------------------------------------------------------------------------- project
def test_currency_and_budget_validation(session):
    company = make_company(session)
    project = make_project(session, company, currency=" inr ", budget="1000.999")
    assert project.currency == "INR" and project.budget == Decimal("1001.00")
    with pytest.raises(ValueError):
        project.currency = "RUPEES"
    with pytest.raises(ValueError):
        project.budget = -1
    with pytest.raises(ValueError):
        project.budget = "lots"


def test_default_currency_comes_from_settings(session):
    company = make_company(session)
    assert company.currency == "USD"


# --------------------------------------------------------------------------- document
def test_document_needs_exactly_one_owner(session):
    company = make_company(session)
    project = make_project(session, company)
    with pytest.raises(IntegrityError):
        make_doc(session)  # no owner
    session.rollback()

    company = make_company(session)
    project = make_project(session, company)
    with pytest.raises(IntegrityError):
        make_doc(session, project=project, company=company)  # both owners


def test_company_document_is_flagged(session):
    company = make_company(session)
    doc = make_doc(session, company=company, document_type=DocumentType.CERTIFICATE)
    assert doc.is_company_document


def test_failed_document_requires_reason(session):
    company = make_company(session)
    project = make_project(session, company)
    doc = make_doc(session, project=project)
    with pytest.raises(ValueError):
        doc.mark_failed("  ")
    doc.mark_failed("PDF is scanned and unreadable")
    session.commit()
    assert doc.processing_status is ProcessingStatus.FAILED
    assert doc.processed_at is not None

    doc.processing_error = None  # bypass the helper; the DB must still refuse
    with pytest.raises(IntegrityError):
        session.flush()


def test_document_mark_done_clears_error(session):
    company = make_company(session)
    doc = make_doc(session, project=make_project(session, company))
    doc.mark_failed("boom")
    doc.mark_done()
    session.commit()
    assert doc.processing_error is None and doc.processing_status is ProcessingStatus.DONE


def test_sha256_validation_and_unique_storage_path(session):
    company = make_company(session)
    project = make_project(session, company)
    doc = make_doc(session, project=project, sha256=SHA.upper())
    assert doc.sha256 == SHA
    with pytest.raises(ValueError):
        doc.sha256 = "not-a-hash"
    make_doc(session, project=project, storage_path="uploads/dup.pdf")
    with pytest.raises(IntegrityError):
        make_doc(session, project=project, storage_path="uploads/dup.pdf")


# --------------------------------------------------------------------------- requirement
def test_requirement_code_unique_per_project(session):
    company = make_company(session)
    p1, p2 = make_project(session, company, name="A"), make_project(session, company, name="B")
    session.add_all(
        [
            Requirement(project_id=p1.id, code="REQ-001", description="a"),
            Requirement(project_id=p2.id, code="REQ-001", description="b"),  # same code, other project: fine
        ]
    )
    session.flush()
    session.add(Requirement(project_id=p1.id, code="REQ-001", description="dup"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_requirement_match_status_and_evidence(session):
    company = make_company(session)
    project = make_project(session, company)
    req = Requirement(
        project_id=project.id,
        code="REQ-002",
        description="Hold EN 1090 certification",
        match_status=MatchStatus.NOT_MET,
        missing_evidence="No EN 1090 certificate in uploaded documents",
        is_mandatory=True,
    )
    session.add(req)
    session.commit()
    assert req.match_status.value == "Not met"
    assert req.is_mandatory is True


def test_invalid_enum_values_rejected(session):
    company = make_company(session)
    project = make_project(session, company)
    session.add(Requirement(project_id=project.id, code="R", description="d", match_status="Definitely met"))
    with pytest.raises((StatementError, LookupError)):
        session.flush()
    session.rollback()

    # The CHECK constraint is a second line of defence against raw writes.
    company = make_company(session)
    project = make_project(session, company)
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO requirements (project_id, code, description, category, match_status, origin, "
                "verification_status, created_at, updated_at) VALUES "
                f"({project.id}, 'R', 'd', 'other', 'Totally fine', 'manual', 'Requires review', "
                "'2026-01-01', '2026-01-01')"
            )
        )


def test_verified_without_date_is_refused(session):
    company = make_company(session)
    project = make_project(session, company)
    req = Requirement(project_id=project.id, code="R1", description="d")
    session.add(req)
    session.flush()

    req.verification_status = VerificationStatus.VERIFIED  # no last_verified_at
    with pytest.raises(IntegrityError):
        session.flush()


def test_mark_verified_helper(session):
    company = make_company(session)
    project = make_project(session, company)
    req = Requirement(project_id=project.id, code="R1", description="d")
    session.add(req)
    session.flush()
    req.mark_verified()
    session.commit()
    assert req.verification_status is VerificationStatus.VERIFIED
    assert req.last_verified_at.tzinfo is not None
    req.mark_rejected()
    assert req.verification_status is VerificationStatus.REJECTED


def test_page_number_must_be_positive(session):
    company = make_company(session)
    project = make_project(session, company)
    req = Requirement(project_id=project.id, code="R1", description="d")
    with pytest.raises(ValueError):
        req.page_number = 0
    req.page_number = 3
    assert req.page_number == 3


def test_deleting_document_keeps_requirement_and_quote(session):
    company = make_company(session)
    project = make_project(session, company)
    doc = make_doc(session, project=project)
    req = Requirement(
        project_id=project.id,
        source_document_id=doc.id,
        code="R1",
        description="d",
        quotation="Original wording",
        page_number=2,
    )
    session.add(req)
    session.commit()

    session.delete(doc)
    session.commit()
    session.refresh(req)
    assert req.source_document_id is None
    assert req.quotation == "Original wording" and req.page_number == 2


# --------------------------------------------------------------------------- extracted facts
@pytest.mark.parametrize("bad", [{"quotation": "   "}, {"value": ""}])
def test_fact_rejects_blank_quotation_or_value(session, bad):
    company = make_company(session)
    doc = make_doc(session, project=make_project(session, company))
    with pytest.raises(IntegrityError):
        make_fact(session, doc, **bad)


def test_fact_without_quotation_is_a_hard_error(session):
    company = make_company(session)
    doc = make_doc(session, project=make_project(session, company))
    session.add(ExtractedFact(document_id=doc.id, label="x", value="y"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_fact_source_reference_round_trip(session):
    company = make_company(session)
    doc = make_doc(session, project=make_project(session, company))
    fact = make_fact(session, doc, page_number=7, location_ref="Sheet BOQ!C14", quote_verified=True)
    session.commit()
    session.expire_all()
    got = session.get(ExtractedFact, fact.id)
    assert (got.page_number, got.location_ref, got.quote_verified) == (7, "Sheet BOQ!C14", True)


def test_facts_are_removed_with_their_document(session):
    company = make_company(session)
    doc = make_doc(session, project=make_project(session, company))
    make_fact(session, doc)
    session.commit()
    session.delete(doc)
    session.commit()
    assert session.scalars(select(ExtractedFact)).all() == []


# --------------------------------------------------------------------------- cascades
def test_deleting_project_cascades_everything_below(session):
    company = make_company(session)
    project = make_project(session, company)
    doc = make_doc(session, project=project)
    make_fact(session, doc)
    session.add(Requirement(project_id=project.id, source_document_id=doc.id, code="R1", description="d"))
    session.commit()

    session.delete(project)
    session.commit()
    for model in (Document, ExtractedFact, Requirement):
        assert session.scalars(select(model)).all() == []
    assert session.get(Company, company.id) is not None  # company survives


def test_deleting_company_cascades_to_projects_and_documents(session):
    company = make_company(session)
    project = make_project(session, company)
    make_doc(session, project=project)
    make_doc(session, company=company, document_type=DocumentType.CERTIFICATE)
    session.commit()
    session.delete(company)
    session.commit()
    for model in (Project, Document):
        assert session.scalars(select(model)).all() == []


def test_foreign_keys_are_enforced(session):
    session.add(Project(company_id=999, name="orphan"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_profile_fact_source_document_set_null(session):
    company = make_company(session)
    doc = make_doc(session, company=company, document_type=DocumentType.EQUIPMENT_REGISTER)
    eq = CompanyEquipment(company_id=company.id, name="Press", source_document_id=doc.id, source_location="Sheet1!A2")
    session.add(eq)
    session.commit()
    session.delete(doc)
    session.commit()
    session.refresh(eq)
    assert eq.source_document_id is None and eq.source_location == "Sheet1!A2"
