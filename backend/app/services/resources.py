"""Rules for project resources: links to company capacity must stay inside the project's
own company and match the resource type."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models import CompanyEquipment, CompanyWorkforceRole, Project, ProjectResource, ResourceType
from app.services import records
from app.services.errors import ServiceError

NON_NULLABLE = ("name", "required_quantity", "resource_type", "currency")


def _check(db: Session, project: Project, resource: ProjectResource) -> None:
    if resource.company_workforce_role_id is not None and resource.company_equipment_id is not None:
        raise ServiceError(422, "A resource can link to a workforce role or equipment, not both.")
    if resource.company_workforce_role_id is not None:
        role = db.get(CompanyWorkforceRole, resource.company_workforce_role_id)
        if role is None or role.company_id != project.company_id:
            raise ServiceError(422, "Workforce role does not belong to this project's company.")
        if resource.resource_type is not ResourceType.PERSONNEL:
            raise ServiceError(422, "A workforce role link requires resource_type 'personnel'.")
    if resource.company_equipment_id is not None:
        equipment = db.get(CompanyEquipment, resource.company_equipment_id)
        if equipment is None or equipment.company_id != project.company_id:
            raise ServiceError(422, "Equipment does not belong to this project's company.")
        if resource.resource_type is not ResourceType.EQUIPMENT:
            raise ServiceError(422, "An equipment link requires resource_type 'equipment'.")
    if (
        resource.required_from is not None
        and resource.required_to is not None
        and resource.required_to < resource.required_from
    ):
        raise ServiceError(422, "required_to cannot be before required_from.")


def create_resource(db: Session, project: Project, values: Mapping[str, Any]) -> ProjectResource:
    values = dict(values)
    verification = values.pop("verification_status", None)
    resource = ProjectResource(project_id=project.id)
    records.apply_values(resource, values)
    if verification is not None:
        records.apply_verification(resource, verification)
    _check(db, project, resource)
    db.add(resource)
    records.commit(db)
    return resource


def update_resource(
    db: Session, project: Project, resource: ProjectResource, values: Mapping[str, Any]
) -> ProjectResource:
    values = dict(values)
    verification = None
    if "verification_status" in values:
        verification = values.pop("verification_status")
        if verification is None:
            raise ServiceError(422, "verification_status cannot be null.")
    records.apply_values(resource, values, non_nullable=NON_NULLABLE)
    if verification is not None:
        records.apply_verification(resource, verification)
    _check(db, project, resource)
    records.commit(db)
    return resource
