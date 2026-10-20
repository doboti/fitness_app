"""Relációs adatmodell.

Szinkronizált (kliensről is írható) entitások: DailyLog, WorkoutSession (+ entries + sets), PainReport.
Mindegyiknek van `updated_at` (kliens időbélyeg, last-write-wins), `deleted` (soft delete)
és `server_seq` (szerveroldali növekvő sorszám a pull-hoz).
"""
from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Felhasználók
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    gender: Mapped[str] = mapped_column(String(8))                    # male | female
    height_cm: Mapped[float | None] = mapped_column(Float)
    age: Mapped[int | None] = mapped_column(Integer)
    target_weight_kg: Mapped[float | None] = mapped_column(Float)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)   # CLI-ből kiadott token (szkriptekhez)
    updated_at: Mapped[str] = mapped_column(String(32))
    server_seq: Mapped[int] = mapped_column(Integer, default=0, index=True)


class DeviceToken(Base):
    """Profilválasztáskor eszközönként kiadott hozzáférési kulcs (kijelentkezéskor csak ez törlődik)."""
    __tablename__ = "device_tokens"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[str] = mapped_column(String(32))
    user_agent: Mapped[str | None] = mapped_column(String(200))


# ---------------------------------------------------------------------------
# Gyakorlat-katalógus (a seed/exercises.json-ból töltődik)
# ---------------------------------------------------------------------------

class MuscleGroup(Base):
    __tablename__ = "muscle_groups"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name_hu: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(16))                   # upper | core | lower


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name_hu: Mapped[str] = mapped_column(String(128))
    name_en: Mapped[str | None] = mapped_column(String(128))
    equipment: Mapped[str] = mapped_column(String(32))                # bodyweight | band | stand | towel
    measure: Mapped[str] = mapped_column(String(8))                   # reps | time
    unilateral: Mapped[bool] = mapped_column(Boolean, default=False)
    rehab_suitable: Mapped[bool] = mapped_column(Boolean, default=False)
    chain: Mapped[str | None] = mapped_column(String(32), index=True)
    level: Mapped[int | None] = mapped_column(Integer)
    image: Mapped[str | None] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)       # seedből kikerült gyakorlat = inaktív

    muscles: Mapped[list[ExerciseMuscle]] = relationship(cascade="all, delete-orphan", lazy="selectin")
    aliases: Mapped[list[ExerciseAlias]] = relationship(lazy="selectin", viewonly=True)


class ExerciseMuscle(Base):
    __tablename__ = "exercise_muscles"

    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True)
    muscle_code: Mapped[str] = mapped_column(ForeignKey("muscle_groups.code"), primary_key=True)
    weight: Mapped[float] = mapped_column(Float)


class ExerciseAlias(Base):
    __tablename__ = "exercise_aliases"

    alias: Mapped[str] = mapped_column(String(160), primary_key=True)   # normalizált (kisbetűs) név
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), index=True)


# ---------------------------------------------------------------------------
# Heti tervek (szerver → kliens)
# ---------------------------------------------------------------------------

class WeeklyProgram(Base):
    __tablename__ = "weekly_programs"
    __table_args__ = (UniqueConstraint("user_id", "week_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    week_id: Mapped[str] = mapped_column(String(8))                   # 2026-W32
    label: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(16))                   # legacy | manual | engine | llm
    payload: Mapped[str] = mapped_column(Text)                        # JSON: {"1": {name, circuits, exercises: [...]}, ...}
    updated_at: Mapped[str] = mapped_column(String(32))
    server_seq: Mapped[int] = mapped_column(Integer, default=0, index=True)


# ---------------------------------------------------------------------------
# Napló (kliens ↔ szerver)
# ---------------------------------------------------------------------------

DAILY_LOG_FIELDS = ("weight_kg", "water_ml", "body_fat_pct", "neck_cm", "waist_cm", "hip_cm", "notes")


class DailyLog(Base):
    __tablename__ = "daily_logs"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    date: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD (helyi dátum)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    water_ml: Mapped[int | None] = mapped_column(Integer)
    body_fat_pct: Mapped[float | None] = mapped_column(Float)
    neck_cm: Mapped[float | None] = mapped_column(Float)
    waist_cm: Mapped[float | None] = mapped_column(Float)
    hip_cm: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String(32))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    server_seq: Mapped[int] = mapped_column(Integer, default=0, index=True)


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)     # kliens által generált UUID
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[str] = mapped_column(String(10), index=True)
    title: Mapped[str | None] = mapped_column(String(200))
    program_week_id: Mapped[str | None] = mapped_column(String(8))
    program_day: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    cardio_distance_km: Mapped[float | None] = mapped_column(Float)
    cardio_duration_min: Mapped[float | None] = mapped_column(Float)
    cardio_notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(16), default="app")    # app | legacy
    updated_at: Mapped[str] = mapped_column(String(32))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    server_seq: Mapped[int] = mapped_column(Integer, default=0, index=True)

    entries: Mapped[list[ExerciseEntry]] = relationship(
        back_populates="session", cascade="all, delete-orphan",
        order_by="ExerciseEntry.position", lazy="selectin")


class ExerciseEntry(Base):
    """Egy gyakorlat egy edzésen belül: az előírás (presc_*) és a teljesítés összefoglalója."""
    __tablename__ = "exercise_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("workout_sessions.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    exercise_id: Mapped[str | None] = mapped_column(ForeignKey("exercises.id"), index=True)  # None = nem azonosított
    name_raw: Mapped[str] = mapped_column(String(200))
    target_raw: Mapped[str | None] = mapped_column(Text)
    presc_sets: Mapped[int | None] = mapped_column(Integer)
    presc_unit: Mapped[str | None] = mapped_column(String(8))         # reps | s
    presc_min: Mapped[int | None] = mapped_column(Integer)
    presc_max: Mapped[int | None] = mapped_column(Integer)
    presc_per_side: Mapped[bool] = mapped_column(Boolean, default=False)
    presc_to_failure: Mapped[bool] = mapped_column(Boolean, default=False)
    band_kg: Mapped[float | None] = mapped_column(Float)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    difficulty: Mapped[str | None] = mapped_column(String(8))         # easy | ok | hard | failed
    rpe_legacy: Mapped[int | None] = mapped_column(Integer)           # régi app 1-5 skálája
    comment: Mapped[str | None] = mapped_column(Text)
    is_rehab: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)    # tervből kikerült, de kitöltött gyakorlat

    session: Mapped[WorkoutSession] = relationship(back_populates="entries")
    sets: Mapped[list[SetEntry]] = relationship(
        cascade="all, delete-orphan", order_by="SetEntry.set_no", lazy="selectin")


class SetEntry(Base):
    __tablename__ = "set_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("exercise_entries.id", ondelete="CASCADE"), index=True)
    set_no: Mapped[int] = mapped_column(Integer)
    reps: Mapped[int | None] = mapped_column(Integer)
    duration_s: Mapped[int | None] = mapped_column(Integer)
    band_kg: Mapped[float | None] = mapped_column(Float)
    difficulty: Mapped[str | None] = mapped_column(String(8))


class PainReport(Base):
    __tablename__ = "pain_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)     # kliens UUID
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[str] = mapped_column(String(10), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64))
    exercise_id: Mapped[str | None] = mapped_column(ForeignKey("exercises.id"))
    muscle_code: Mapped[str | None] = mapped_column(ForeignKey("muscle_groups.code"))
    body_area: Mapped[str | None] = mapped_column(String(32))         # testtérkép-kulcs, ha nem izom (pl. 'knee_lateral')
    side: Mapped[str | None] = mapped_column(String(8))               # left | right | both
    intensity: Mapped[int] = mapped_column(Integer)                   # 0-10
    kind: Mapped[str] = mapped_column(String(12))                     # sharp | dull | discomfort
    note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[str | None] = mapped_column(String(10))
    updated_at: Mapped[str] = mapped_column(String(32))
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    server_seq: Mapped[int] = mapped_column(Integer, default=0, index=True)


class PlanProposal(Base):
    """A szabálymotor (később az LLM) javaslata a következő hétre; változásonként hagyható jóvá."""
    __tablename__ = "plan_proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    base_week_id: Mapped[str] = mapped_column(String(8))
    target_week_id: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(16), default="engine")   # engine | llm
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | accepted | rejected | superseded
    payload: Mapped[str] = mapped_column(Text)                          # JSON: {changes, unchanged, insights}
    created_at: Mapped[str] = mapped_column(String(32))
    decided_at: Mapped[str | None] = mapped_column(String(32))


class SyncCounter(Base):
    """Egyetlen sor: a globális, monoton növekvő server_seq."""
    __tablename__ = "sync_counter"

    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)
