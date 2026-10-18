"""Fakes and builders for the AI service tests. No test needs a running Ollama server."""
from __future__ import annotations

import json
from typing import Any, Callable, Optional, Sequence

from app.services.ai.ollama_client import OllamaClient
from app.services.ingestion.chunker import Chunk, chunk_document
from app.services.ingestion.sanitizer import ExtractedDocument, ExtractionStatus, SegmentKind, TextSegment

MODEL = "gemma3:4b"


def text_reply(content: str, *, done_reason: str = "stop", status: int = 200) -> tuple[int, bytes]:
    body = {"model": MODEL, "message": {"role": "assistant", "content": content}, "done": True, "done_reason": done_reason}
    return status, json.dumps(body).encode()


def json_reply(value: Any, **kwargs: Any) -> tuple[int, bytes]:
    return text_reply(json.dumps(value), **kwargs)


def raw_reply(status: int, body: Any) -> tuple[int, bytes]:
    return status, body if isinstance(body, bytes) else json.dumps(body).encode()


class FakeOllama:
    """A ``Transport`` that records every request and plays back queued replies (or exceptions).

    Pass ``handler`` instead to compute each reply from the request payload."""

    def __init__(self, *replies: Any, handler: Optional[Callable[[dict], Any]] = None) -> None:
        self.replies = list(replies)
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    def __call__(self, method: str, url: str, body: Optional[bytes], timeout: float):
        payload = json.loads(body) if body else None
        self.calls.append({"method": method, "url": url, "payload": payload, "timeout": timeout})
        if self.handler is not None:
            reply = self.handler(payload)
        else:
            assert self.replies, "the service made more model calls than the test expected"
            reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    @property
    def prompts(self) -> list[str]:
        """User-message text of every chat call."""
        return [c["payload"]["messages"][-1]["content"] for c in self.calls if c["payload"]]

    @property
    def systems(self) -> list[str]:
        return [c["payload"]["messages"][0]["content"] for c in self.calls if c["payload"]]


def make_client(fake: FakeOllama, *, model: str = MODEL) -> OllamaClient:
    return OllamaClient("http://localhost:11434", model, timeout=5, transport=fake)


def make_chunks(pages: Sequence[str], *, filename: str = "tender.pdf", max_chars: int = 300) -> list[Chunk]:
    """One PDF page per text; pages are numbered from 1."""
    segments = [
        TextSegment(text=text, kind=SegmentKind.PAGE, source_filename=filename, page_number=n, location_ref=f"page {n}")
        for n, text in enumerate(pages, start=1)
    ]
    return chunk_document(
        ExtractedDocument(filename=filename, file_type="pdf", status=ExtractionStatus.OK, segments=segments, page_count=len(pages)),
        max_chars=max_chars,
    )


def make_sheet_chunks(rows: Sequence[tuple[str, str]], *, sheet: str = "BOQ") -> list[Chunk]:
    """Worksheet rows as ``(location_ref, text)``."""
    segments = [
        TextSegment(text=text, kind=SegmentKind.ROW, source_filename="boq.xlsx", location_ref=ref, sheet_name=sheet)
        for ref, text in rows
    ]
    return chunk_document(ExtractedDocument(filename="boq.xlsx", file_type="xlsx", status=ExtractionStatus.OK, segments=segments))
