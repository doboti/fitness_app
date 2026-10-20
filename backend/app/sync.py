"""Offline-first szinkron.

Push: a kliens elküldi a módosított dokumentumokat; dokumentumonként last-write-wins az `updated_at` alapján.
Pull: a szerver visszaadja a felhasználó minden olyan dokumentumát, amelynek `server_seq`-je nagyobb a kliens
kurzoránál. A server_seq-et az írási tranzakción belül osztjuk ki; SQLite-ban az írók sorban futnak,
ezért nem keletkezhet olyan rés, amit a kliens átugorhatna.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import schemas
from .models import (DAILY_LOG_FIELDS, DailyLog, Exercise, ExerciseEntry, MuscleGroup, PainReport, SetEntry, SyncCounter, User,
                     WeeklyProgram, WorkoutSession)
from .util import next_seq, parse_ts

_DAILY_FIELDS = (*DAILY_LOG_FIELDS, "updated_at", "deleted")
_SESSION_FIELDS = ("date", "title", "program_week_id", "program_day", "notes", "cardio_distance_km",
                   "cardio_duration_min", "cardio_notes", "source", "updated_at", "deleted")
_PAIN_FIELDS = ("date", "session_id", "exercise_id", "muscle_code", "body_area", "side", "intensity", "kind",
                "note", "resolved_at", "updated_at", "deleted")


def _is_stale(existing_ts: str | None, incoming_ts: str) -> bool:
    return existing_ts is not None and parse_ts(existing_ts) > parse_ts(incoming_ts)


def build_entries(entries: list[schemas.EntryDoc]) -> list[ExerciseEntry]:
    return [
        ExerciseEntry(
            **e.model_dump(exclude={"sets"}),
            sets=[SetEntry(**s.model_dump()) for s in e.sets],
        )
        for e in entries
    ]


def session_to_doc(row: WorkoutSession) -> schemas.SessionDoc:
    return schemas.SessionDoc.model_validate(row)


def program_to_doc(row: WeeklyProgram) -> schemas.ProgramDoc:
    return schemas.ProgramDoc(week_id=row.week_id, label=row.label, source=row.source,
                              days=json.loads(row.payload), updated_at=row.updated_at)


def current_cursor(db: Session) -> int:
    counter = db.get(SyncCounter, 1)
    return counter.value if counter else 0


def apply_sync(db: Session, user: User, req: schemas.SyncRequest) -> schemas.SyncResponse:
    exercise_ids = set(db.scalars(select(Exercise.id)))
    muscle_codes = set(db.scalars(select(MuscleGroup.code)))
    applied: set[str] = set()
    stale: list[str] = []
    rejected: dict[str, str] = {}

    # --- push ---------------------------------------------------------------
    for doc in req.daily_logs:
        key = f"daily:{doc.date}"
        try:
            parse_ts(doc.updated_at)  # hibás időbélyeg → rejected
            row = db.get(DailyLog, (user.id, doc.date))
            if row and _is_stale(row.updated_at, doc.updated_at):
                stale.append(key)
                continue
            row = row or DailyLog(user_id=user.id, date=doc.date)
            for f in _DAILY_FIELDS:
                setattr(row, f, getattr(doc, f))
            row.server_seq = next_seq(db)
            db.add(row)
            applied.add(key)
        except ValueError as exc:
            rejected[key] = str(exc)

    for doc in req.sessions:
        key = f"session:{doc.id}"
        try:
            parse_ts(doc.updated_at)  # hibás időbélyeg → rejected
            unknown = {e.exercise_id for e in doc.entries if e.exercise_id and e.exercise_id not in exercise_ids}
            if unknown:
                rejected[key] = f"Ismeretlen gyakorlat-azonosító: {', '.join(sorted(unknown))}"
                continue
            row = db.get(WorkoutSession, doc.id)
            if row and row.user_id != user.id:
                rejected[key] = "Az azonosító már egy másik felhasználóé."
                continue
            if row and _is_stale(row.updated_at, doc.updated_at):
                stale.append(key)
                continue
            row = row or WorkoutSession(id=doc.id, user_id=user.id)
            for f in _SESSION_FIELDS:
                setattr(row, f, getattr(doc, f))
            row.entries = build_entries(doc.entries)
            row.server_seq = next_seq(db)
            db.add(row)
            applied.add(key)
        except ValueError as exc:
            rejected[key] = str(exc)

    for doc in req.pain_reports:
        key = f"pain:{doc.id}"
        try:
            parse_ts(doc.updated_at)  # hibás időbélyeg → rejected
            if doc.exercise_id and doc.exercise_id not in exercise_ids:
                rejected[key] = f"Ismeretlen gyakorlat-azonosító: {doc.exercise_id}"
                continue
            if doc.muscle_code and doc.muscle_code not in muscle_codes:
                rejected[key] = f"Ismeretlen izomcsoport: {doc.muscle_code}"
                continue
            row = db.get(PainReport, doc.id)
            if row and row.user_id != user.id:
                rejected[key] = "Az azonosító már egy másik felhasználóé."
                continue
            if row and _is_stale(row.updated_at, doc.updated_at):
                stale.append(key)
                continue
            row = row or PainReport(id=doc.id, user_id=user.id)
            for f in _PAIN_FIELDS:
                setattr(row, f, getattr(doc, f))
            row.server_seq = next_seq(db)
            db.add(row)
            applied.add(key)
        except ValueError as exc:
            rejected[key] = str(exc)

    db.commit()

    # --- pull ---------------------------------------------------------------
    since = req.cursor
    changes = schemas.SyncChanges()
    for row in db.scalars(select(DailyLog).where(DailyLog.user_id == user.id, DailyLog.server_seq > since)):
        if f"daily:{row.date}" not in applied:
            changes.daily_logs.append(schemas.DailyLogDoc.model_validate(row))
    for row in db.scalars(select(WorkoutSession).where(WorkoutSession.user_id == user.id,
                                                       WorkoutSession.server_seq > since)):
        if f"session:{row.id}" not in applied:
            changes.sessions.append(session_to_doc(row))
    for row in db.scalars(select(PainReport).where(PainReport.user_id == user.id, PainReport.server_seq > since)):
        if f"pain:{row.id}" not in applied:
            changes.pain_reports.append(schemas.PainReportDoc.model_validate(row))
    for row in db.scalars(select(WeeklyProgram).where(WeeklyProgram.user_id == user.id,
                                                      WeeklyProgram.server_seq > since)):
        changes.programs.append(program_to_doc(row))
    if user.server_seq > since:
        changes.user = schemas.UserOut.model_validate(user)

    # Az elutasított (régebbi) dokumentumok nyertes szerverváltozatát akkor is visszaküldjük,
    # ha a kliens kurzora már túl van rajta – különben az eszköz sosem kapná meg.
    included = {f"daily:{d.date}" for d in changes.daily_logs} | {f"session:{s.id}" for s in changes.sessions} \
        | {f"pain:{p.id}" for p in changes.pain_reports}
    for key in stale:
        if key in included:
            continue
        kind, _, ident = key.partition(":")
        if kind == "daily":
            changes.daily_logs.append(schemas.DailyLogDoc.model_validate(db.get(DailyLog, (user.id, ident))))
        elif kind == "session":
            changes.sessions.append(session_to_doc(db.get(WorkoutSession, ident)))
        elif kind == "pain":
            changes.pain_reports.append(schemas.PainReportDoc.model_validate(db.get(PainReport, ident)))

    return schemas.SyncResponse(cursor=current_cursor(db), applied=len(applied), stale=stale,
                                rejected=rejected, changes=changes)
