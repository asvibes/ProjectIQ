"""Project chat API.

Asking questions about a project needs the local Ollama service: ``services/ai/ollama_client``
and ``services/ai/qa`` are empty placeholders and ``config.py`` has no Ollama settings, so
nothing can be sent to a model yet. The endpoint validates the request and the project and
then answers 501. No question text is stored or logged.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.models import Project
from app.routers._common import NOT_IMPLEMENTED_RESPONSE, get_project_or_404, not_implemented
from app.schemas.chat import ChatRequest

router = APIRouter(prefix="/projects/{project_id}/chat", tags=["chat"])


@router.post("", summary="Ask the local AI about a project (not available yet)", responses=NOT_IMPLEMENTED_RESPONSE)
def ask(body: ChatRequest, project: Project = Depends(get_project_or_404)) -> None:
    not_implemented(
        "Project chat",
        "the local AI service (app/services/ai/ollama_client.py and qa.py) and its Ollama configuration",
    )
