"""Error type raised by the service layer.

Services never import FastAPI. They raise ``ServiceError`` with the HTTP status the caller
should answer with and a message that is safe to show to the user; routers translate it into
an ``HTTPException`` (see ``app.routers._common.http_errors``).
"""
from __future__ import annotations


class ServiceError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
