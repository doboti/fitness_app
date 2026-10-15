"""Gyakorlat-katalógus: seed betöltése és szabad szöveges gyakorlatnév → katalógus-azonosító."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import config
from .models import Exercise, ExerciseAlias, ExerciseMuscle, MuscleGroup
from .util import normalize_name

_PARENS_SUFFIX = re.compile(r"\s*\([^)]*\)\s*$")
_BAND_IN_NAME = re.compile(r"(\d+(?:[.,]\d+)?)\s*kg", re.I)


def load_seed(db: Session, seed_file: Path | None = None) -> dict:
    """Idempotens: a seed a katalógus egyetlen forrása, minden induláskor szinkronizáljuk."""
    seed = json.loads(Path(seed_file or config.SEED_FILE).read_text(encoding="utf-8"))

    for m in seed["muscles"]:
        db.merge(MuscleGroup(code=m["code"], name_hu=m["name_hu"], region=m["region"]))
    db.flush()

    seed_ids = set()
    alias_owner: dict[str, str] = {}
    for ex in seed["exercises"]:
        seed_ids.add(ex["id"])
        row = db.get(Exercise, ex["id"]) or Exercise(id=ex["id"])
        row.name_hu = ex["name_hu"]
        row.name_en = ex.get("name_en")
        row.equipment = ex["equipment"]
        row.measure = ex["measure"]
        row.unilateral = ex.get("unilateral", False)
        row.rehab_suitable = ex.get("rehab_suitable", False)
        row.chain = ex.get("chain")
        row.level = ex.get("level")
        row.image = ex.get("image")
        row.description = ex.get("description")
        row.active = True
        db.add(row)

        # Különbség-alapú frissítés: a teljes lista cseréje azonos kulcsú törlés+beszúrást okozna egy flush-ban.
        weights = ex["muscles"]
        for link in list(row.muscles):
            if link.muscle_code not in weights:
                row.muscles.remove(link)
            else:
                link.weight = weights[link.muscle_code]
        existing_muscles = {link.muscle_code for link in row.muscles}
        row.muscles.extend(ExerciseMuscle(muscle_code=code, weight=w)
                           for code, w in weights.items() if code not in existing_muscles)

        db.flush()

        names = {ex["name_hu"], *([ex["name_en"]] if ex.get("name_en") else []), *ex.get("aliases", [])}
        for alias in {normalize_name(n) for n in names}:
            if alias_owner.setdefault(alias, ex["id"]) != ex["id"]:
                raise ValueError(f"Az '{alias}' alias két gyakorlatnál is szerepel: {alias_owner[alias]}, {ex['id']}")

    # Az aliasokat egyben írjuk újra (más kulcsok nem hivatkoznak rájuk), így gyakorlatok között is áthelyezhetők.
    db.execute(delete(ExerciseAlias))
    db.add_all(ExerciseAlias(alias=a, exercise_id=eid) for a, eid in alias_owner.items())
    db.flush()
    db.expire_all()

    # A seedből kikerült gyakorlatokat nem töröljük (naplók hivatkozhatnak rájuk), csak inaktiváljuk.
    for row in db.scalars(select(Exercise).where(Exercise.id.not_in(seed_ids))):
        row.active = False
    db.commit()
    return {"muscles": len(seed["muscles"]), "exercises": len(seed_ids)}


@dataclass
class MatchResult:
    exercise_id: str | None
    band_kg: float | None = None


class ExerciseMatcher:
    """Név → gyakorlat. Sorrend: pontos alias, majd a zárójeles utótag nélküli név."""

    def __init__(self, db: Session):
        self._aliases = dict(db.execute(select(ExerciseAlias.alias, ExerciseAlias.exercise_id)).all())

    def match(self, name: str) -> MatchResult:
        band = _BAND_IN_NAME.search(name)
        band_kg = float(band.group(1).replace(",", ".")) if band else None
        key = normalize_name(name)
        if key in self._aliases:
            return MatchResult(self._aliases[key], band_kg)
        stripped = normalize_name(_PARENS_SUFFIX.sub("", name))
        return MatchResult(self._aliases.get(stripped), band_kg)
