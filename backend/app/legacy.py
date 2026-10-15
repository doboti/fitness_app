"""A régi egyfájlos app adatainak (results/*.json export, YYYY-WXX.json heti terv) betöltése."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date as Date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import ExerciseMatcher
from .models import DAILY_LOG_FIELDS, DailyLog, ExerciseEntry, User, WeeklyProgram, WorkoutSession
from .prescription import parse_target
from .util import iso_week_id, next_seq, now_iso



def rpe_to_difficulty(rpe: int | None) -> str | None:
    """A régi 1-5-ös RPE skála leképezése a nehézség-chipekre."""
    if rpe is None:
        return None
    return "easy" if rpe <= 2 else "ok" if rpe == 3 else "hard"


def _has_exercise_data(ex: dict) -> bool:
    return ex.get("completed") is True or ex.get("rpe") is not None or bool((ex.get("comment") or "").strip())


def _is_empty_daily(log: dict) -> bool:
    return not any(log.get(f) for f in ("weight_kg", "water_ml", "body_fat_pct", "neck_cm", "waist_cm", "hip_cm")) \
        and not (log.get("notes") or "").strip()


def _is_empty_workout(log: dict) -> bool:
    cardio = log.get("extra_cardio") or {}
    return not any(_has_exercise_data(e) for e in log.get("exercises", [])) \
        and not (cardio.get("distance_km") or cardio.get("duration_minutes") or (cardio.get("notes") or "").strip()) \
        and not log.get("archived_exercises")


def upsert_program(db: Session, user: User, week_id: str, label: str | None, days: dict, source: str,
                   matcher: ExerciseMatcher, unmatched: Counter | None = None) -> WeeklyProgram:
    """Elmenti a heti tervet; a gyakorlatokhoz hozzáírja a felismert exercise_id-t és az értelmezett előírást."""
    enriched = {}
    for day_key, day in days.items():
        exercises = []
        for ex in day.get("exercises", []):
            match = matcher.match(ex["name"])
            presc = parse_target(ex.get("target"), day.get("circuits"))
            if presc.band_kg is None:
                presc.band_kg = match.band_kg
            if match.exercise_id is None and unmatched is not None:
                unmatched[ex["name"]] += 1
            exercises.append({**ex, "exercise_id": match.exercise_id, "prescription": presc.to_dict()})
        enriched[str(day_key)] = {**day, "exercises": exercises}

    row = db.scalar(select(WeeklyProgram).where(WeeklyProgram.user_id == user.id, WeeklyProgram.week_id == week_id))
    row = row or WeeklyProgram(user_id=user.id, week_id=week_id)
    row.label = label
    row.source = source
    row.payload = json.dumps(enriched, ensure_ascii=False)
    row.updated_at = now_iso()
    row.server_seq = next_seq(db)
    db.add(row)
    return row


def import_legacy(db: Session, user: User, data: dict) -> dict:
    """Egy régi export (vagy egy heti terv fájl) betöltése. Ugyanaz a fájl újra betölthető: felülírja magát."""
    matcher = ExerciseMatcher(db)
    unmatched: Counter = Counter()
    report = {"programs": 0, "daily_logs": 0, "sessions": 0, "entries": 0, "skipped_empty": 0}
    ts = now_iso()

    # Egyetlen heti terv fájl (YYYY-WXX.json)
    if "week_id" in data and "program" in data:
        upsert_program(db, user, data["week_id"], data.get("week_label"), data["program"], "legacy", matcher, unmatched)
        report["programs"] += 1

    info = data.get("user_info") or {}
    if info:
        for src, dst in (("height_cm", "height_cm"), ("age", "age"), ("target_weight_kg", "target_weight_kg")):
            if info.get(src) is not None:
                setattr(user, dst, info[src])
        user.updated_at = ts
        user.server_seq = next_seq(db)

    programs = data.get("weekly_programs") or {}
    for week_id, wp in programs.items():
        upsert_program(db, user, week_id, wp.get("week_label"), wp.get("program") or {}, "legacy", matcher, unmatched)
        report["programs"] += 1

    for date_str, log in (data.get("daily_logs") or {}).items():
        if not log or _is_empty_daily(log):
            report["skipped_empty"] += 1
            continue
        row = db.get(DailyLog, (user.id, date_str)) or DailyLog(user_id=user.id, date=date_str)
        for f in DAILY_LOG_FIELDS:
            setattr(row, f, log.get(f))
        row.updated_at = ts
        row.deleted = False
        row.server_seq = next_seq(db)
        db.add(row)
        report["daily_logs"] += 1

    for date_str, log in (data.get("workout_logs") or {}).items():
        if not log or _is_empty_workout(log):
            report["skipped_empty"] += 1
            continue

        week_id = iso_week_id(date_str)
        day_no = Date.fromisoformat(date_str).isoweekday()
        day_program = ((programs.get(week_id) or {}).get("program") or {}).get(str(day_no)) or {}
        default_sets = day_program.get("circuits")

        entries = []
        all_exercises = [(e, False) for e in log.get("exercises", [])] + \
                        [(e, True) for e in log.get("archived_exercises", [])]
        for position, (ex, archived) in enumerate(all_exercises):
            match = matcher.match(ex["name"])
            if match.exercise_id is None:
                unmatched[ex["name"]] += 1
            presc = parse_target(ex.get("target"), default_sets)
            entries.append(ExerciseEntry(
                position=position,
                exercise_id=match.exercise_id,
                name_raw=ex["name"],
                target_raw=ex.get("target"),
                presc_sets=presc.sets,
                presc_unit=presc.unit,
                presc_min=presc.min,
                presc_max=presc.max,
                presc_per_side=presc.per_side,
                presc_to_failure=presc.to_failure,
                band_kg=presc.band_kg if presc.band_kg is not None else match.band_kg,
                completed=ex.get("completed") is True,
                difficulty=rpe_to_difficulty(ex.get("rpe")),
                rpe_legacy=ex.get("rpe"),
                comment=ex.get("comment") or None,
                archived=archived,
            ))

        session_id = f"legacy-{user.id}-{date_str}"
        cardio = log.get("extra_cardio") or {}
        row = db.get(WorkoutSession, session_id) or WorkoutSession(id=session_id, user_id=user.id)
        row.date = date_str
        row.title = log.get("workout_type")
        row.program_week_id = week_id
        row.program_day = day_no
        row.cardio_distance_km = cardio.get("distance_km")
        row.cardio_duration_min = cardio.get("duration_minutes")
        row.cardio_notes = cardio.get("notes") or None
        row.source = "legacy"
        row.updated_at = ts
        row.deleted = False
        row.entries = entries
        row.server_seq = next_seq(db)
        db.add(row)
        report["sessions"] += 1
        report["entries"] += len(entries)

    db.commit()
    report["unmatched_exercises"] = dict(unmatched.most_common())
    return report
