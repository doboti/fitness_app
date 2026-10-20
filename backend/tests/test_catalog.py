import json

import pytest
from sqlalchemy import func, select

from app import config
from app.catalog import ExerciseMatcher, load_seed
from app.models import Exercise, ExerciseAlias, ExerciseMuscle, MuscleGroup

# Az összes gyakorlatnév, ami 2026-W23..W32 között a heti tervekben és naplókban előfordult.
LEGACY_NAMES = [
    "Standard Push-up", "Standard Plank", "Prone Cobra", "Standard Sit-up", "Air Squat", "Walking Lunge",
    "Standing Calf Raise", "Plank Hip Dips", "Incline Push-up or Dolphin Plank", "Lying Leg Raise", "Superman Hold",
    "High Knees", "Reverse Lunge", "Russian Twist", "Squat to Cross-Body Knee Drive", "Plank to Failure",
    "Állványos mély fekvőtámasz", "Gumiszalagos evezés ülve", "Állványos Dolphin Plank or Push-up",
    "Gumiszalagos bicepsz hajlítás", "Gumiszalagos húzás mellhez (Pull-Apart)",
    "Gumiszalagos íjász evezés (Archer Row)", "Bicycle Crunches", "Lassú negatív fekvőtámasz",
    "Egykezes mellkasi bicepsz (szalaggal)", "Gumiszalagos íjász evezés", "Gumiszalagos evezés (9kg)",
    "Gumiszalagos evezés (Kétkezes)", "Gumiszalagos íjász evezés (9kg)", "Robbanékony (Plyo) Fekvőtámasz",
    "Tuck Dragon Flag Negatív", "Seated Pike Pulses (Nyújtott lábemelés talajon ülve)",
    "Állványos lassú negatív fekvőtámasz", "Tuck L-Sit Hold (Zsugor L-ülés támaszban)",
    "Hanyattfekvő csípőemelés (Dragon Flag alap)", "Gumiszalagos evezés (Kétkezes pumpa)",
    "Robbanékony Fekvőtámasz", "Tuck L-Sit Hold", "Hand-Release Push-up", "Seated Pike Pulses",
    "Tuck L-Sit Hold (Megemelve)", "Hanyattfekvő csípőemelés (Farizom fókusz)", "Hollow Body Hold",
    "Nyújtott karú szalagos letolás (Front Lever Prep)", "Hasonfekvő törölközős lehúzás (Prone Towel Pulldown)",
    "Gumiszalagos evezés ülve (Kétkezes)",
]


def test_seed_loaded(db):
    seed = json.loads(config.SEED_FILE.read_text(encoding="utf-8"))
    assert db.scalar(select(func.count()).select_from(MuscleGroup)) == len(seed["muscles"])
    assert db.scalar(select(func.count()).select_from(Exercise)) == len(seed["exercises"])


def test_seed_is_idempotent(db):
    before = db.scalar(select(func.count()).select_from(ExerciseAlias))
    load_seed(db)
    load_seed(db)
    assert db.scalar(select(func.count()).select_from(ExerciseAlias)) == before
    assert db.scalar(select(func.count()).select_from(ExerciseMuscle)) > 0


def test_seed_references_valid_muscles_and_weights():
    seed = json.loads(config.SEED_FILE.read_text(encoding="utf-8"))
    codes = {m["code"] for m in seed["muscles"]}
    for ex in seed["exercises"]:
        assert set(ex["muscles"]) <= codes, ex["id"]
        assert all(0 < w <= 1 for w in ex["muscles"].values()), ex["id"]
        assert max(ex["muscles"].values()) == 1.0, f"{ex['id']}: kell egy fő mozgató izom (1.0)"
        assert ex["measure"] in ("reps", "time")


@pytest.mark.parametrize("name", LEGACY_NAMES)
def test_all_legacy_names_match(db, name):
    assert ExerciseMatcher(db).match(name).exercise_id is not None


def test_matcher_specific_cases(db):
    m = ExerciseMatcher(db)
    assert m.match("Hanyattfekvő csípőemelés (Farizom fókusz)").exercise_id == "glute_bridge"
    assert m.match("Hanyattfekvő csípőemelés (Dragon Flag alap)").exercise_id == "reverse_hip_lift"
    assert m.match("  standard   push-up ").exercise_id == "push_up"
    result = m.match("Gumiszalagos íjász evezés (9kg)")
    assert (result.exercise_id, result.band_kg) == ("band_archer_row", 9.0)
    assert m.match("Tuck L-Sit Hold (bármi új megjegyzés)").exercise_id == "tuck_l_sit_hold"
    assert m.match("Teljesen ismeretlen gyakorlat").exercise_id is None


def test_removed_seed_exercise_is_deactivated(db, tmp_path):
    seed = json.loads(config.SEED_FILE.read_text(encoding="utf-8"))
    seed["exercises"] = [e for e in seed["exercises"] if e["id"] != "clamshell"]
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(seed), encoding="utf-8")
    load_seed(db, path)
    assert db.get(Exercise, "clamshell").active is False
    assert ExerciseMatcher(db).match("Clamshell").exercise_id is None
