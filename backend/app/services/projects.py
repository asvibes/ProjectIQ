"""Project rules: a project belongs to an existing company; deleting one removes its files."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import Company, Project
from app.services import files, records

NON_NULLABLE = ("name", "currency", "status", "deliverables", "constraints")


def create_project(db: Session, values: Mapping[str, Any]) -> Project:
    records.get_or_404(db, Company, values["company_id"], "Company")
    return records.create_record(db, Project, values)


def update_project(db: Session, project: Project, values: Mapping[str, Any]) -> Project:
    return records.update_record(db, project, values, non_nullable=NON_NULLABLE)


def delete_project(db: Session, project: Project, *, uploads_dir: Path, storage_dir: Path) -> None:
    """Delete the project (its documents, requirements, risks, ... cascade), then its files."""
    stored = files.collect_for_projects(db, [project.id])
    records.delete_record(db, project)
    files.remove_files(stored, uploads_dir=uploads_dir, storage_dir=storage_dir)
