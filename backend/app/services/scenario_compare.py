"""Side-by-side view of *stored* scenario results.

Read-only: nothing is calculated or recalculated here. Scenarios whose ``results`` are NULL
are reported as not calculated rather than filled in.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Scenario
from app.services.errors import ServiceError

MIN_SCENARIOS = 2
MAX_SCENARIOS = 10


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


def compare_stored(db: Session, project_id: int, scenario_ids: Sequence[int]) -> dict[str, Any]:
    ids = list(dict.fromkeys(scenario_ids))  # drop duplicates, keep order
    if not MIN_SCENARIOS <= len(ids) <= MAX_SCENARIOS:
        raise ServiceError(422, f"Provide between {MIN_SCENARIOS} and {MAX_SCENARIOS} distinct scenario ids.")

    rows = db.scalars(select(Scenario).where(Scenario.project_id == project_id, Scenario.id.in_(ids))).all()
    by_id = {row.id: row for row in rows}
    missing = [i for i in ids if i not in by_id]
    if missing:
        # Same answer for "does not exist" and "belongs to another project".
        raise ServiceError(404, f"Scenario {missing[0]} not found.")

    ordered = [by_id[i] for i in ids]
    metrics: dict[str, dict[int, Any]] = {}
    for scenario in ordered:
        for key, value in (scenario.results or {}).items():
            if _is_scalar(value):
                metrics.setdefault(key, {})
    for key in metrics:
        for scenario in ordered:
            value = (scenario.results or {}).get(key)
            metrics[key][scenario.id] = value if _is_scalar(value) else None

    return {
        "project_id": project_id,
        "scenarios": [
            {
                "id": s.id,
                "name": s.name,
                "kind": s.kind,
                "calculated": s.results is not None,
                "calculated_at": s.calculated_at,
                "results": s.results,
            }
            for s in ordered
        ],
        "metrics": metrics,
        "not_calculated": [s.id for s in ordered if s.results is None],
    }
