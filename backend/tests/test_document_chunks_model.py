"""DocumentChunk constraints, cascades and the Document.extraction_info column."""
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Company, Document, DocumentChunk, Project


def _doc(session):
    company = Company(name="Acme")
    session.add(company)
    session.flush()
    project = Project(company_id=company.id, name="P")
    session.add(project)
    session.flush()
    doc = Document(project_id=project.id, original_filename="t.pdf", storage_path="uploads/t.pdf")
    session.add(doc)
    session.flush()
    return doc


def _chunk(doc, index=0, **kw):
    return DocumentChunk(
        document_id=doc.id,
        chunk_index=index,
        text=kw.pop("text", "some text"),
        char_count=kw.pop("char_count", 9),
        **kw,
    )


def test_chunk_round_trip_and_ordering(session):
    doc = _doc(session)
    session.add_all([_chunk(doc, 1, page_start=2, page_end=3, sources=[{"segment_index": 1}]), _chunk(doc, 0, page_start=1, page_end=1)])
    session.commit()
    session.expire_all()
    got = session.get(Document, doc.id)
    assert [c.chunk_index for c in got.chunks] == [0, 1]
    assert got.chunks[1].sources == [{"segment_index": 1}] and got.chunks[0].sources == []
    assert got.chunks[0].document is got



def test_extraction_info_round_trip(session):
    doc = _doc(session)
    doc.extraction_info = {"warnings": ["w"], "metadata": {"sheets_read": ["BOQ"]}}
    session.commit()
    session.expire_all()

    assert session.get(Document, doc.id).extraction_info["metadata"]["sheets_read"] == ["BOQ"]
    assert doc.extraction_info == {"warnings": ["w"], "metadata": {"sheets_read": ["BOQ"]}}




def test_chunk_index_is_unique_per_document(session):
    doc = _doc(session)
    session.add(_chunk(doc, 0))
    session.flush()
    session.add(_chunk(doc, 0))
    with pytest.raises(IntegrityError):
        session.flush()


@pytest.mark.parametrize(
    "bad",
    [{"text": "   "}, {"page_start": 0}, {"page_start": 3, "page_end": 2}, {"char_count": -1}],
)
def test_chunk_constraints(session, bad):
    doc = _doc(session)
    session.add(_chunk(doc, 0, **bad))
    with pytest.raises(IntegrityError):
        session.flush()


def test_negative_chunk_index_rejected(session):
    doc = _doc(session)
    session.add(_chunk(doc, -1))
    with pytest.raises(IntegrityError):
        session.flush()


def test_chunks_are_removed_with_their_document(session):
    doc = _doc(session)
    session.add(_chunk(doc, 0))
    session.commit()
    session.delete(doc)
    session.commit()
    assert session.scalars(select(DocumentChunk)).all() == []
