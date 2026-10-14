"""Custom column types and small validation helpers shared by the models."""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import DateTime, Enum as SAEnum, Numeric
from sqlalchemy.types import TypeDecorator

MAX_MONEY = Decimal("1000000000000")  # fits Numeric(14, 2)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on every backend.

    SQLite drops tzinfo, so without this a value written as aware UTC comes back naive.
    Naive datetimes are rejected on write instead of being silently guessed.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect: Any) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime not allowed; use a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: Optional[datetime], dialect: Any) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


# Money: 2 decimal places, always handled as Decimal in Python. SQLite has no exact decimal
# type, so values are stored with NUMERIC affinity; amounts below MAX_MONEY round-trip
# exactly at 2 dp (checked up to 999999999999.99). PostgreSQL would give true NUMERIC.
Money = Numeric(14, 2, asdecimal=True)


def enum_type(enum_cls: type[enum.Enum]) -> SAEnum:
    """Store enum *values* as short strings with a named CHECK constraint (no native ENUM)."""
    return SAEnum(
        enum_cls,
        name=enum_cls.__name__.lower(),
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=max(len(m.value) for m in enum_cls),
        values_callable=lambda e: [m.value for m in e],
    )


def normalize_currency(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    code = str(value).strip().upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError(f"Currency must be a 3-letter ISO 4217 code, got {value!r}")
    return code


def normalize_money(value: Any, field: str = "amount") -> Optional[Decimal]:
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a valid number: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError(f"{field} must be finite")
    if amount < 0:
        raise ValueError(f"{field} cannot be negative")
    if amount >= MAX_MONEY:
        raise ValueError(f"{field} is too large")
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
