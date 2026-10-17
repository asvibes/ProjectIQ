"""Access to stored generated outputs (artifacts). Generation itself is not implemented: the
DOCX/PPTX/CSV builders and the briefing drafter are empty placeholders."""
from __future__ import annotations

from pathlib import Path

from app.models import Artifact
from app.services.documents import storage
from app.services.errors import ServiceError


def artifact_file(storage_dir: Path, artifact: Artifact) -> Path:
    """Absolute path of an artifact's stored file, confined to the storage folder."""
    if not artifact.storage_path:
        raise ServiceError(404, "This output has no stored file.")
    try:
        path = storage.resolve_storage_path(storage_dir, artifact.storage_path)
    except ValueError as exc:
        raise ServiceError(404, "The stored file is not available.") from exc
    if not path.is_file():
        raise ServiceError(404, "The stored file is not available.")
    return path
