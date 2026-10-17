"""Company profile API: the company, its workforce roles, equipment, certifications and past
projects, and per-field verification of the profile.

Every fact carries a verification status. New child records start as "Requires review";
only an explicit request marks one "Verified" (which stamps ``last_verified_at``). Editing a
profile field that was Verified resets that field to "Requires review".

Deleting a company deletes its projects and documents too (and their stored files).
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Company, VerificationStatus
from app.routers._common import get_storage_dir, http_errors
from app.routers.documents import get_upload_dir
from app.schemas import company as s
from app.schemas.common import Page
from app.services import companies as company_service
from app.services import records

router = APIRouter(prefix="/companies", tags=["companies"])


def _get_company(company_id: int, db: Session = Depends(get_db)) -> Company:
    with http_errors():
        return records.get_or_404(db, Company, company_id, "Company")


# ---------------------------------------------------------------------------- company
@router.post("", response_model=s.CompanyRead, status_code=201, summary="Create a company profile")
def create_company(body: s.CompanyCreate, db: Session = Depends(get_db)) -> Company:
    with http_errors():
        return company_service.create_company(db, body.model_dump(exclude_none=True))


@router.get("", response_model=Page[s.CompanyRead], summary="List companies")
def list_companies(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Page[s.CompanyRead]:
    rows, total = records.paginate(db, Company, [], [Company.id.desc()], limit, offset)
    return Page[s.CompanyRead](
        items=[s.CompanyRead.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{company_id}", response_model=s.CompanyRead, summary="Get one company")
def get_company(company: Company = Depends(_get_company)) -> Company:
    return company


@router.patch("/{company_id}", response_model=s.CompanyRead, summary="Update a company")
def update_company(
    body: s.CompanyUpdate,
    company: Company = Depends(_get_company),
    db: Session = Depends(get_db),
) -> Company:
    with http_errors():
        return company_service.update_company(db, company, body.model_dump(exclude_unset=True))


@router.put(
    "/{company_id}/field-verification/{field}",
    response_model=s.CompanyRead,
    summary="Set the verification state of one profile field",
)
def set_field_verification(
    field: str,
    body: s.FieldVerificationUpdate,
    company: Company = Depends(_get_company),
    db: Session = Depends(get_db),
) -> Company:
    with http_errors():
        return company_service.set_field_verification(
            db,
            company,
            field,
            body.status,
            source_document_id=body.source_document_id,
            last_verified_at=body.last_verified_at,
        )


@router.delete("/{company_id}", status_code=204, summary="Delete a company and everything it owns")
def delete_company(
    company: Company = Depends(_get_company),
    db: Session = Depends(get_db),
    uploads_dir: Path = Depends(get_upload_dir),
    storage_dir: Path = Depends(get_storage_dir),
) -> Response:
    with http_errors():
        company_service.delete_company(db, company, uploads_dir=uploads_dir, storage_dir=storage_dir)
    return Response(status_code=204)


# ------------------------------------------------------------- child record collections
def _register_children(segment: str, create_schema, update_schema, read_schema, order_by) -> None:
    """Add list / create / get / update / delete routes for one child collection."""
    spec = company_service.CHILDREN[segment]
    base = f"/{{company_id}}/{segment}"
    key = segment.replace("-", "_")

    def list_children(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        verification_status: Optional[VerificationStatus] = Query(None),
        company: Company = Depends(_get_company),
        db: Session = Depends(get_db),
    ):
        conditions = [spec.model.company_id == company.id]
        if verification_status is not None:
            conditions.append(spec.model.verification_status == verification_status)
        rows, total = records.paginate(db, spec.model, conditions, order_by(spec.model), limit, offset)
        return Page[read_schema](
            items=[read_schema.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
        )

    def create_child(body: create_schema, company: Company = Depends(_get_company), db: Session = Depends(get_db)):
        with http_errors():
            return company_service.create_child(db, spec, company, body.model_dump(exclude_none=True))

    def get_child(record_id: int, company: Company = Depends(_get_company), db: Session = Depends(get_db)):
        with http_errors():
            return company_service.get_child(db, spec, company, record_id)

    def update_child(
        record_id: int,
        body: update_schema,
        company: Company = Depends(_get_company),
        db: Session = Depends(get_db),
    ):
        with http_errors():
            record = company_service.get_child(db, spec, company, record_id)
            return company_service.update_child(
                db, spec, company, record, body.model_dump(exclude_unset=True)
            )

    def delete_child(record_id: int, company: Company = Depends(_get_company), db: Session = Depends(get_db)):
        with http_errors():
            record = company_service.get_child(db, spec, company, record_id)
            records.delete_record(db, record)
        return Response(status_code=204)

    label = spec.label.lower()
    router.add_api_route(
        base, list_children, methods=["GET"], response_model=Page[read_schema],
        name=f"list_{key}", summary=f"List {label}s", tags=["companies"],
    )
    router.add_api_route(
        base, create_child, methods=["POST"], response_model=read_schema, status_code=201,
        name=f"create_{key}", summary=f"Add a {label}", tags=["companies"],
    )
    router.add_api_route(
        base + "/{record_id}", get_child, methods=["GET"], response_model=read_schema,
        name=f"get_{key}", summary=f"Get one {label}", tags=["companies"],
    )
    router.add_api_route(
        base + "/{record_id}", update_child, methods=["PATCH"], response_model=read_schema,
        name=f"update_{key}", summary=f"Update a {label}", tags=["companies"],
    )
    router.add_api_route(
        base + "/{record_id}", delete_child, methods=["DELETE"], status_code=204,
        name=f"delete_{key}", summary=f"Delete a {label}", tags=["companies"],
    )


_register_children(
    "workforce-roles", s.WorkforceRoleCreate, s.WorkforceRoleUpdate, s.WorkforceRoleRead,
    lambda m: [m.department, m.role, m.id],
)
_register_children(
    "equipment", s.EquipmentCreate, s.EquipmentUpdate, s.EquipmentRead, lambda m: [m.name, m.id]
)
_register_children(
    "certifications", s.CertificationCreate, s.CertificationUpdate, s.CertificationRead,
    lambda m: [m.name, m.id],
)
_register_children(
    "past-projects", s.PastProjectCreate, s.PastProjectUpdate, s.PastProjectRead,
    lambda m: [m.id.desc()],
)
