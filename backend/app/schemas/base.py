"""Pydantic 2 conventions for request/response schemas.

Response schemas inherit ``ORMModel`` so they can be built straight from SQLAlchemy
objects (``MySchema.model_validate(orm_obj)``). Request schemas inherit ``RequestModel``,
which rejects unknown fields so typos fail loudly instead of being ignored.
"""
from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
