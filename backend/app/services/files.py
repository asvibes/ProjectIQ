"""Cleanup of stored files when the database rows that own them are deleted.

The database cascades row deletion, but files on disk need explicit removal. Callers collect
the paths *before* deleting the rows, commit, and only then remove the files, so a failed
commit never leaves rows pointing at deleted files.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Artifact, Document, Project
from app.services.documents import storage

logger = logging.getLogger(__name__)


@dataclass
class StoredFiles:
    uploads: list[str] = field(default_factory=list)  # relative to the uploads folder
    generated: list[str] = field(default_factory=list)  # relative to the storage folder


def collect_for_projects(db: Session, project_ids: Iterable[int]) -> StoredFiles:
    ids = list(project_ids)
    if not ids:
        return StoredFiles()
    uploads = db.scalars(select(Document.storage_path).where(Document.project_id.in_(ids))).all()
    generated = db.scalars(
        select(Artifact.storage_path).where(Artifact.project_id.in_(ids), Artifact.storage_path.is_not(None))
    ).all()
    return StoredFiles(uploads=list(uploads), generated=list(generated))


def collect_for_company(db: Session, company_id: int) -> StoredFiles:
    project_ids = db.scalars(select(Project.id).where(Project.company_id == company_id)).all()
    found = collect_for_projects(db, project_ids)
    found.uploads.extend(
        db.scalars(select(Document.storage_path).where(Document.company_id == company_id)).all()
    )
    return found


def remove_files(files: StoredFiles, *, uploads_dir: Path, storage_dir: Optional[Path] = None) -> None:
    """Best-effort removal; anything resolving outside its folder is refused and logged."""
    for relative in files.uploads:
        _remove(uploads_dir, relative)
    if storage_dir is not None:
        for relative in files.generated:
            _remove(storage_dir, relative)


def _remove(root: Path, relative: str) -> None:
    try:
        storage.remove_stored_file(storage.resolve_storage_path(root, relative))
    except ValueError:
        logger.error("Refusing to delete a file outside its storage folder: %r", relative)
