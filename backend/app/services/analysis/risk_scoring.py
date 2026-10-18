"""Deterministic risk scoring, priority bands and the risk matrix (FR-23).

``Risk.score`` is derived data: the model stores it, this module computes it. Like
``services/finance`` everything here is a *pure function* of the stored ratings: no database
access, no clock, no randomness and no language model, so the same ratings always give the
same score, band, matrix and ordering.

Formula
-------
::

    score = probability * impact        (both whole numbers 1..5, so score is 1..25)

Priority bands (the conventional 5 x 5 matrix; thresholds are the module constants below)::

    1-4 Low      5-9 Medium      10-14 High      15-25 Critical

Unknown stays unknown
---------------------
* A missing rating is **not assessed**, never zero and never a default. If probability or
  impact is ``None`` the score is ``None`` and the band is ``None``. Nothing is guessed.
* What *is* known is still reported: ``potential_min_score`` / ``potential_max_score`` give the
  range the score could take once the missing rating is supplied, and an unassessed risk that
  could reach High or Critical is flagged ``unassessed_could_be_high`` and listed separately so
  that a severe-impact risk with unknown likelihood is never silently left out of a briefing.
* A rating outside 1..5 or not a whole number (including ``True``/``False`` and floats) is
  reported as ``invalid_rating``; no score is produced for it and the other risks are unaffected.
  ``compute_score`` itself is strict and raises ``RiskScoringError``.

Which risks count
-----------------
* ``Rejected`` risks (verification status) are excluded from the matrix, the summary and the
  high-priority list; they are still returned, flagged ``excluded``.
* ``closed`` risks keep their score but are not open exposure.
* ``accepted`` risks are still open exposure: accepting a risk is a decision to live with it,
  not a reason to hide it from the briefing.
* Ratings that a person has not confirmed (verification status other than Verified) are scored
  but flagged ``needs_review``.

Stale scores
------------
``score_is_current`` compares the stored ``Risk.score`` with the score computed from the stored
ratings. ``apply_score`` writes the computed score (or ``None``) onto a risk object; the caller
owns the transaction.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from app.models.enums import RequirementOrigin, VerificationStatus
from app.models.risk import RATING_MAX, RATING_MIN, SCORE_MAX, RiskStatus

RISK_SCORING_VERSION = "risk-scoring-1.0.0"

_REVIEW_STATUSES = frozenset(
    {
        VerificationStatus.REQUIRES_REVIEW.value,
        VerificationStatus.ESTIMATED.value,
        VerificationStatus.ASSUMPTION.value,
        VerificationStatus.CONFLICTING.value,
        VerificationStatus.OUTDATED.value,
        VerificationStatus.MISSING.value,
    }
)
_REJECTED = VerificationStatus.REJECTED.value


class RiskScoringError(ValueError):
    """Raised by ``compute_score`` for ratings that are not whole numbers 1..5."""


class PriorityBand(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


# (lowest score in the band, band), highest first. Changing these changes every band.
BAND_THRESHOLDS: tuple[tuple[int, PriorityBand], ...] = (
    (15, PriorityBand.CRITICAL),
    (10, PriorityBand.HIGH),
    (5, PriorityBand.MEDIUM),
    (1, PriorityBand.LOW),
)
HIGH_THRESHOLD = 10  # High and Critical are "high priority" (always shown in the briefing)

PROBABILITY_AXIS = tuple(range(RATING_MIN, RATING_MAX + 1))  # matrix columns, plus "Unknown"
IMPACT_AXIS = tuple(range(RATING_MAX, RATING_MIN - 1, -1))  # matrix rows, highest first


def band_range(band: PriorityBand) -> tuple[int, int]:
    """Inclusive (lowest, highest) score of a band."""
    floors = [f for f, _ in BAND_THRESHOLDS]
    floor = next(f for f, b in BAND_THRESHOLDS if b is band)
    higher = [f for f in floors if f > floor]
    return floor, (min(higher) - 1 if higher else SCORE_MAX)


# ---------------------------------------------------------------------------- helpers
def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _value(v: Any) -> Any:
    return getattr(v, "value", v)


def _code_key(code: str) -> tuple:
    """Natural-sort key ("REQ-2" < "REQ-10"). Parts are tagged so digits and text never compare."""
    return tuple(
        (0, int(p), "") if p.isdigit() else (1, 0, p.lower())
        for p in re.split(r"(\d+)", str(code or ""))
        if p
    )


def _valid_rating(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and RATING_MIN <= value <= RATING_MAX


def compute_score(probability: Optional[int], impact: Optional[int]) -> Optional[int]:
    """``probability * impact``, or ``None`` when either rating is not yet assessed."""
    for name, value in (("probability", probability), ("impact", impact)):
        if value is not None and not _valid_rating(value):
            raise RiskScoringError(f"{name} must be a whole number between {RATING_MIN} and {RATING_MAX}")
    if probability is None or impact is None:
        return None
    return probability * impact


def band_for_score(score: Optional[int]) -> Optional[PriorityBand]:
    if score is None:
        return None
    if isinstance(score, bool) or not isinstance(score, int) or not RATING_MIN <= score <= SCORE_MAX:
        raise RiskScoringError(f"score must be a whole number between {RATING_MIN} and {SCORE_MAX}")
    for floor, band in BAND_THRESHOLDS:
        if score >= floor:
            return band
    return PriorityBand.LOW  # pragma: no cover - unreachable for score >= 1


# ----------------------------------------------------------------------------- result
@dataclass(frozen=True)
class RiskAssessment:
    """Scoring outcome for one risk. ``flags`` are stable codes the UI can map to labels."""

    risk_id: Optional[int]
    code: str
    title: str
    category: Optional[str]
    status: Optional[str]
    probability: Optional[int]
    impact: Optional[int]
    score: Optional[int]  # computed; None = not assessed
    band: Optional[PriorityBand]
    stored_score: Optional[int]
    score_is_current: bool
    potential_min_score: Optional[int]
    potential_max_score: Optional[int]
    is_open: bool
    excluded: bool  # verification status Rejected
    flags: tuple[str, ...]
    explanation: str
    version: str = RISK_SCORING_VERSION

    @property
    def assessed(self) -> bool:
        return self.score is not None

    @property
    def high_priority(self) -> bool:
        return self.score is not None and self.score >= HIGH_THRESHOLD

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "code": self.code,
            "title": self.title,
            "category": self.category,
            "status": self.status,
            "probability": self.probability,
            "impact": self.impact,
            "score": self.score,
            "band": self.band.value if self.band else None,
            "stored_score": self.stored_score,
            "score_is_current": self.score_is_current,
            "potential_min_score": self.potential_min_score,
            "potential_max_score": self.potential_max_score,
            "is_open": self.is_open,
            "excluded": self.excluded,
            "flags": list(self.flags),
            "explanation": self.explanation,
            "version": self.version,
        }


def _potential_range(probability: Optional[int], impact: Optional[int]) -> tuple[Optional[int], Optional[int]]:
    if probability is None and impact is None:
        return None, None
    known = probability if probability is not None else impact
    return known * RATING_MIN, known * RATING_MAX


def assess_risk(risk: Any) -> RiskAssessment:
    """Score one risk (ORM object or mapping). Never raises for bad data: it is flagged."""
    probability, impact = _get(risk, "probability"), _get(risk, "impact")
    stored = _get(risk, "score")
    status = _value(_get(risk, "status"))
    verification = _value(_get(risk, "verification_status")) or VerificationStatus.REQUIRES_REVIEW.value
    flags: list[str] = []

    invalid = [n for n, v in (("probability", probability), ("impact", impact)) if v is not None and not _valid_rating(v)]
    if invalid:
        flags.append("invalid_rating")
        score = None
        explanation = (
            f"Not scored: {' and '.join(invalid)} must be a whole number between "
            f"{RATING_MIN} and {RATING_MAX}."
        )
        low = high = None
    else:
        score = compute_score(probability, impact)
        low, high = _potential_range(probability, impact)
        if score is None:
            if probability is None:
                flags.append("probability_unknown")
            if impact is None:
                flags.append("impact_unknown")
            missing = " and ".join(f for f in ("probability", "impact") if f"{f}_unknown" in flags)
            explanation = f"Not scored: {missing} not assessed yet."
            if low is not None:
                known = f"impact {impact}" if impact is not None else f"probability {probability}"
                explanation += f" With {known} the score would be {low} to {high}."
        else:
            band = band_for_score(score)
            lo, hi = band_range(band)
            explanation = (
                f"Score {score} = probability {probability} x impact {impact}, band {band.value} ({lo}-{hi})."
            )

    band = band_for_score(score)
    excluded = verification == _REJECTED
    is_open = status != RiskStatus.CLOSED.value and not excluded
    if excluded:
        flags.append("excluded")
    elif status == RiskStatus.CLOSED.value:
        flags.append("closed")
    if verification in _REVIEW_STATUSES:
        flags.append("needs_review")

    if score is None and not invalid and high is not None and high >= HIGH_THRESHOLD:
        flags.append("unassessed_could_be_high")
    if score is not None and stored is None:
        flags.append("score_missing")
    elif stored != score:
        flags.append("score_stale")
    if score is not None and score >= HIGH_THRESHOLD and is_open:
        if not str(_get(risk, "mitigation") or "").strip():
            flags.append("mitigation_missing")
        if not str(_get(risk, "owner") or "").strip():
            flags.append("owner_missing")
    origin = _value(_get(risk, "origin"))
    has_source = bool(_get(risk, "source_document_id") is not None and (
        _get(risk, "quotation") or _get(risk, "location_ref") or _get(risk, "page_number")
    ))
    if origin == RequirementOrigin.EXTRACTED.value and not has_source:
        flags.append("source_missing")
    if _get(risk, "quote_verified") is False:
        flags.append("quote_unverified")

    return RiskAssessment(
        risk_id=_get(risk, "id"),
        code=str(_get(risk, "code") or ""),
        title=str(_get(risk, "title") or ""),
        category=_value(_get(risk, "category")),
        status=status,
        probability=probability if not invalid else None,
        impact=impact if not invalid else None,
        score=score,
        band=band,
        stored_score=stored,
        score_is_current=(stored == score) and not invalid,
        potential_min_score=low,
        potential_max_score=high,
        is_open=is_open,
        excluded=excluded,
        flags=tuple(flags),
        explanation=explanation,
    )


def _priority_key(a: RiskAssessment) -> tuple:
    """Open assessed (score desc) -> open unassessed (potential desc) -> closed -> excluded."""
    if a.excluded:
        group, rank = 3, 0
    elif not a.is_open:
        group, rank = 2, -(a.score or 0)
    elif a.assessed:
        group, rank = 0, -a.score
    else:
        group, rank = 1, -(a.potential_max_score or 0)
    return (group, rank, _code_key(a.code), a.risk_id or 0)


def assess_risks(risks: Iterable[Any]) -> list[RiskAssessment]:
    """Score every risk and return them in priority order (deterministic)."""
    return sorted((assess_risk(r) for r in risks), key=_priority_key)


def apply_score(risk: Any) -> bool:
    """Write the computed score onto ``risk.score`` (``None`` when not assessable).

    Returns True when the stored value changed. The caller owns the transaction. Invalid ratings
    clear the stored score rather than leaving a number that no longer matches the ratings.
    """
    a = assess_risk(risk)
    if _get(risk, "score") == a.score:
        return False
    risk.score = a.score
    return True


def apply_scores(risks: Iterable[Any]) -> list[RiskAssessment]:
    """Apply scores to all risks and return the assessments in priority order."""
    risks = list(risks)
    for r in risks:
        apply_score(r)
    return assess_risks(risks)


# ----------------------------------------------------------------- matrix and summaries
def build_matrix(assessments: Iterable[RiskAssessment]) -> dict[str, Any]:
    """Likelihood-versus-impact matrix with an Unknown-probability column.

    Rows are impact (5 at the top), columns probability 1..5 then ``"Unknown"``. Every cell is
    present, empty ones with ``codes == []``. Risks whose impact is unknown cannot be placed on
    a row and are listed in ``impact_unknown``. Closed and rejected risks are not plotted.
    """
    cells: dict[tuple[Optional[int], int], list[str]] = {}
    impact_unknown: list[str] = []
    for a in assessments:
        if not a.is_open:
            continue
        if a.impact is None:
            impact_unknown.append(a.code)
        else:
            cells.setdefault((a.probability, a.impact), []).append(a.code)
    out_cells = []
    for impact in IMPACT_AXIS:
        for probability in (*PROBABILITY_AXIS, None):
            score = None if probability is None else probability * impact
            band = band_for_score(score)
            out_cells.append(
                {
                    "probability": probability if probability is not None else "Unknown",
                    "impact": impact,
                    "score": score,
                    "band": band.value if band else None,
                    "codes": sorted(cells.get((probability, impact), []), key=_code_key),
                }
            )
    return {
        "probability_axis": [*PROBABILITY_AXIS, "Unknown"],
        "impact_axis": list(IMPACT_AXIS),
        "cells": out_cells,
        "impact_unknown": sorted(impact_unknown, key=_code_key),
    }


def high_priority(assessments: Iterable[RiskAssessment]) -> list[RiskAssessment]:
    """Open High/Critical risks, highest score first: always shown in the briefing."""
    return [a for a in sorted(assessments, key=_priority_key) if a.is_open and a.high_priority]


def summarise(assessments: Iterable[RiskAssessment]) -> dict[str, Any]:
    """Counts for the register header and briefing. No overall score is produced."""
    items = list(assessments)
    counted = [a for a in items if not a.excluded]
    open_items = [a for a in counted if a.is_open]
    by_band = {b.value: 0 for _, b in reversed(BAND_THRESHOLDS)}
    for a in open_items:
        if a.band:
            by_band[a.band.value] += 1
    return {
        "total": len(items),
        "excluded_rejected": len(items) - len(counted),
        "open": len(open_items),
        "closed": sum(1 for a in counted if not a.is_open),
        "open_by_band": by_band,
        "open_unassessed": sum(1 for a in open_items if not a.assessed),
        "unassessed_could_be_high": [a.code for a in open_items if "unassessed_could_be_high" in a.flags],
        "high_priority": [a.code for a in high_priority(items)],
        "needs_review": sum(1 for a in open_items if "needs_review" in a.flags),
        "stale_scores": sum(1 for a in counted if "score_stale" in a.flags or "score_missing" in a.flags),
        "high_without_mitigation": [a.code for a in open_items if "mitigation_missing" in a.flags],
        "basis": (
            "score = probability x impact (1-5 each). Missing ratings are not assessed and are "
            "never counted as zero; no overall risk score is produced."
        ),
        "version": RISK_SCORING_VERSION,
    }