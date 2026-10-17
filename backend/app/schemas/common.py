"""Field types and envelopes shared by the API schemas."""
from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import Field, StringConstraints

from app.models.types import MAX_MONEY
from app.schemas.base import ORMModel

T = TypeVar("T")

# Money: non-negative, below the Numeric(14, 2) limit. The model rounds to 2 decimal places.
MoneyIn = Annotated[Decimal, Field(ge=0, lt=MAX_MONEY)]
# Fractions between 0 and 1 (0.10 = 10%).
RateIn = Annotated[Decimal, Field(ge=0, le=1)]
Currency = Annotated[str, StringConstraints(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")]
Name200 = Annotated[str, StringConstraints(min_length=1, max_length=200)]
Text255 = Annotated[str, StringConstraints(min_length=1, max_length=255)]
Code32 = Annotated[str, StringConstraints(min_length=1, max_length=32)]


class Page(ORMModel, Generic[T]):
    """List envelope, same shape as the document API's lists."""

    items: list[T]
    total: int
    limit: int
    offset: int
