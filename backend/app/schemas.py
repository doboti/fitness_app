"""API / szinkron dokumentumformátumok.

Egy edzés (session) egyetlen dokumentumként utazik a gyakorlataival és sorozataival együtt:
egyszerre egy eszközön szerkesztik, így a dokumentum szintű last-write-wins elég, és nem kell
gyakorlatonként ütközést kezelni.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Difficulty = Literal["easy", "ok", "hard", "failed"]
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


class _Doc(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- katalógus --------------------------------------------------------------

class MuscleOut(_Doc):
    code: str
    name_hu: str
    region: str


class ExerciseOut(_Doc):
    id: str
    name_hu: str
    name_en: str | None
    equipment: str
    measure: str
    unilateral: bool
    rehab_suitable: bool
    chain: str | None
    level: int | None
    image: str | None
    description: str | None
    muscles: dict[str, float]
    aliases: list[str]


# --- felhasználó ------------------------------------------------------------

class UserOut(_Doc):
    id: int
    name: str
    gender: str
    height_cm: float | None
    age: int | None
    target_weight_kg: float | None
    updated_at: str


class UserUpdate(BaseModel):
    height_cm: float | None = Field(default=None, ge=100, le=250)
    age: int | None = Field(default=None, ge=10, le=100)
    target_weight_kg: float | None = Field(default=None, ge=30, le=250)


# --- szinkronizált dokumentumok ---------------------------------------------

class DailyLogDoc(_Doc):
    date: str = Field(pattern=DATE_PATTERN)
    weight_kg: float | None = None
    water_ml: int | None = None
    body_fat_pct: float | None = None
    neck_cm: float | None = None
    waist_cm: float | None = None
    hip_cm: float | None = None
    notes: str | None = None
    updated_at: str
    deleted: bool = False


class SetDoc(_Doc):
    set_no: int
    reps: int | None = None
    duration_s: int | None = None
    band_kg: float | None = None
    difficulty: Difficulty | None = None


class EntryDoc(_Doc):
    position: int
    exercise_id: str | None = None
    name_raw: str
    target_raw: str | None = None
    presc_sets: int | None = None
    presc_unit: Literal["reps", "s"] | None = None
    presc_min: int | None = None
    presc_max: int | None = None
    presc_per_side: bool = False
    presc_to_failure: bool = False
    band_kg: float | None = None
    completed: bool = False
    difficulty: Difficulty | None = None
    rpe_legacy: int | None = None
    comment: str | None = None
    is_rehab: bool = False
    archived: bool = False
    sets: list[SetDoc] = []


class SessionDoc(_Doc):
    id: str = Field(min_length=1, max_length=64)
    date: str = Field(pattern=DATE_PATTERN)
    title: str | None = None
    program_week_id: str | None = None
    program_day: int | None = None
    notes: str | None = None
    cardio_distance_km: float | None = None
    cardio_duration_min: float | None = None
    cardio_notes: str | None = None
    source: str = "app"
    updated_at: str
    deleted: bool = False
    entries: list[EntryDoc] = []


class PainReportDoc(_Doc):
    id: str = Field(min_length=1, max_length=64)
    date: str = Field(pattern=DATE_PATTERN)
    session_id: str | None = None
    exercise_id: str | None = None
    muscle_code: str | None = None
    body_area: str | None = None
    side: Literal["left", "right", "both"] | None = None
    intensity: int = Field(ge=0, le=10)
    kind: Literal["sharp", "dull", "discomfort"]
    note: str | None = None
    resolved_at: str | None = None
    updated_at: str
    deleted: bool = False


class ProgramDoc(_Doc):
    week_id: str
    label: str | None
    source: str
    days: dict[str, dict]
    updated_at: str


class SyncRequest(BaseModel):
    cursor: int = 0
    daily_logs: list[DailyLogDoc] = []
    sessions: list[SessionDoc] = []
    pain_reports: list[PainReportDoc] = []


class SyncChanges(BaseModel):
    daily_logs: list[DailyLogDoc] = []
    sessions: list[SessionDoc] = []
    pain_reports: list[PainReportDoc] = []
    programs: list[ProgramDoc] = []
    user: UserOut | None = None


class SyncResponse(BaseModel):
    cursor: int
    applied: int
    stale: list[str]          # régebbi, ezért el nem fogadott dokumentumok kulcsai
    rejected: dict[str, str]  # kulcs → hibaok
    changes: SyncChanges


# --- heti terv import (a régi app formátuma) --------------------------------

class LegacyWeeklyProgram(BaseModel):
    week_id: str = Field(pattern=r"^\d{4}-W\d{2}$")
    week_label: str | None = None
    program: dict[str, dict]
