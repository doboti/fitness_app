"""Izomcsoportonkénti heti terhelés: súlyozott sorozatszám (sorozat × izomszorzó)."""
from __future__ import annotations

from collections import defaultdict
from datetime import date as Date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Exercise, User, WorkoutSession
from .util import iso_week_id, week_monday


def entry_set_count(entry) -> float:
    """Rögzített sorozatok száma; régi (sorozat nélküli) naplónál teljesítve = az előírt sorozatszám."""
    if entry.sets:
        return float(len(entry.sets))
    if entry.completed:
        return float(entry.presc_sets or 1)
    return 0.0


def weekly_muscle_sets(db: Session, user: User, weeks: int = 4, today: Date | None = None) -> dict:
    today = today or Date.today()
    first_monday = week_monday(today) - timedelta(weeks=weeks - 1)
    week_ids = [iso_week_id(first_monday + timedelta(weeks=i)) for i in range(weeks)]

    muscle_weights = {ex.id: {m.muscle_code: m.weight for m in ex.muscles} for ex in db.scalars(select(Exercise))}
    volume: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    unmatched = 0

    sessions = db.scalars(select(WorkoutSession).where(
        WorkoutSession.user_id == user.id,
        WorkoutSession.deleted.is_(False),
        WorkoutSession.date >= first_monday.isoformat(),
        WorkoutSession.date <= today.isoformat(),
    ))
    for session in sessions:
        week = iso_week_id(Date.fromisoformat(session.date))
        for entry in session.entries:
            n_sets = entry_set_count(entry)
            if not n_sets:
                continue
            if entry.exercise_id is None:
                unmatched += 1
                continue
            for muscle, weight in muscle_weights.get(entry.exercise_id, {}).items():
                volume[muscle][week] += n_sets * weight

    return {
        "weeks": week_ids,
        "muscles": {m: [round(by_week.get(w, 0.0), 1) for w in week_ids] for m, by_week in sorted(volume.items())},
        "unmatched_entries": unmatched,
    }
