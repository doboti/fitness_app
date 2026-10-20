import json
from datetime import date

from sqlalchemy import func, select

from app.legacy import import_legacy, rpe_to_difficulty
from app.models import DailyLog, WeeklyProgram, WorkoutSession
from app.stats import weekly_muscle_sets
from conftest import auth

LEGACY_EXPORT = {
    "user_info": {"height_cm": 176, "target_weight_kg": 72, "gender": "male", "age": 25},
    "weekly_programs": {
        "2026-W31": {"week_id": "2026-W31", "program": {
            "5": {"name": "Friday Form Check", "circuits": 3, "exercises": [
                {"name": "Hand-Release Push-up", "target": "3 kör x Maximum"},
                {"name": "Gumiszalagos íjász evezés (9kg)", "target": "15-15 ismétlés"},
                {"name": "Valami új gyakorlat", "target": "4 kör x 30 másodperc"},
            ]}}},
    },
    "daily_logs": {
        "2026-07-31": {"weight_kg": 75.4, "water_ml": 1500, "notes": ""},
        "2026-08-01": {"weight_kg": None, "water_ml": 0, "notes": ""},          # üres → kihagyva
    },
    "workout_logs": {
        "2026-07-31": {
            "workout_type": "Friday Form Check",
            "exercises": [
                {"name": "Hand-Release Push-up", "target": "3 kör x Maximum", "completed": True, "rpe": 5, "comment": ""},
                {"name": "Gumiszalagos íjász evezés (9kg)", "target": "15-15 ismétlés", "completed": True, "rpe": 2,
                 "comment": "könnyű volt"},
                {"name": "Valami új gyakorlat", "target": "4 kör x 30 másodperc", "completed": False, "rpe": None,
                 "comment": ""},
            ],
            "archived_exercises": [{"name": "Standard Plank", "target": "4 kör x 1 perc", "completed": True}],
            "extra_cardio": {"distance_km": 5.2, "duration_minutes": 31, "notes": "jó volt"},
        },
        "2026-07-30": {"workout_type": "x", "exercises": [{"name": "Air Squat", "completed": False, "rpe": None}],
                       "extra_cardio": {"distance_km": None, "duration_minutes": None, "notes": ""}},  # üres
    },
}


def test_rpe_mapping():
    assert [rpe_to_difficulty(r) for r in (None, 1, 2, 3, 4, 5)] == [None, "easy", "easy", "ok", "hard", "hard"]


def test_import_legacy(db, user):
    u, _ = user
    report = import_legacy(db, u, json.loads(json.dumps(LEGACY_EXPORT)))
    assert report["programs"] == 1 and report["daily_logs"] == 1 and report["sessions"] == 1
    assert report["skipped_empty"] == 2
    assert report["unmatched_exercises"] == {"Valami új gyakorlat": 2}
    assert u.height_cm == 176 and u.age == 25

    session = db.get(WorkoutSession, f"legacy-{u.id}-2026-07-31")
    assert session.program_week_id == "2026-W31" and session.program_day == 5
    assert session.cardio_distance_km == 5.2
    hrp, archer, unknown, plank = session.entries
    assert (hrp.exercise_id, hrp.presc_sets, hrp.presc_to_failure, hrp.difficulty) == ("hand_release_push_up", 3, True, "hard")
    assert (archer.exercise_id, archer.band_kg, archer.presc_per_side, archer.presc_sets) == ("band_archer_row", 9.0, True, 3)
    assert archer.difficulty == "easy" and archer.comment == "könnyű volt"
    assert unknown.exercise_id is None and unknown.presc_unit == "s"
    assert plank.archived and plank.exercise_id == "plank"

    program = json.loads(db.scalar(select(WeeklyProgram.payload)))
    assert program["5"]["exercises"][1]["exercise_id"] == "band_archer_row"
    assert program["5"]["exercises"][1]["prescription"]["band_kg"] == 9.0

    # Újraimport: ugyanannyi sor marad
    import_legacy(db, u, json.loads(json.dumps(LEGACY_EXPORT)))
    assert db.scalar(select(func.count()).select_from(WorkoutSession)) == 1
    assert db.scalar(select(func.count()).select_from(DailyLog)) == 1
    assert len(db.get(WorkoutSession, f"legacy-{u.id}-2026-07-31").entries) == 4


def test_muscle_volume(db, user):
    u, _ = user
    import_legacy(db, u, json.loads(json.dumps(LEGACY_EXPORT)))
    stats = weekly_muscle_sets(db, u, weeks=2, today=date(2026, 8, 2))
    assert stats["weeks"] == ["2026-W30", "2026-W31"]
    # HRP 3 sorozat × mell 1.0; felső hát: íjász evezés 3 × 1.0 + HRP 3 × 0.2; plank (archivált, teljesítve) 4 × has 1.0
    assert stats["muscles"]["chest"] == [0.0, 3.0]
    assert stats["muscles"]["upper_back"] == [0.0, 3.6]
    assert stats["muscles"]["abs"] == [0.0, 4.0 + 3 * 0.3]
    assert stats["unmatched_entries"] == 0   # a teljesítetlen ismeretlen gyakorlat nem számít


def test_api_catalog_and_profile(client, user):
    _, token = user
    exercises = client.get("/api/exercises").json()
    push_up = next(e for e in exercises if e["id"] == "push_up")
    assert push_up["muscles"]["chest"] == 1.0 and push_up["chain"] == "push"
    assert "standard push-up" in push_up["aliases"]
    assert len(client.get("/api/muscles").json()) == 19

    me = client.put("/api/me", headers=auth(token), json={"age": 31}).json()
    assert me["age"] == 31 and me["height_cm"] == 175
    assert client.put("/api/me", headers=auth(token), json={"age": 5}).status_code == 422
    assert client.get("/api/health").json()["status"] == "ok"


def test_api_program_upload_and_pull(client, user):
    _, token = user
    res = client.post("/api/programs", headers=auth(token), json={
        "week_id": "2026-W43", "week_label": "Teszt hét",
        "program": {"1": {"name": "Hétfő", "circuits": 4, "exercises": [{"name": "Air Squat", "target": "4 kör x 20"}]}},
    })
    assert res.status_code == 200
    assert res.json()["days"]["1"]["exercises"][0]["exercise_id"] == "air_squat"
    programs = client.post("/api/sync", headers=auth(token), json={"cursor": 0}).json()["changes"]["programs"]
    assert programs[0]["week_id"] == "2026-W43" and programs[0]["label"] == "Teszt hét"
    assert client.post("/api/programs", headers=auth(token), json={"week_id": "2026-43", "program": {}}).status_code == 422


def test_api_legacy_import(client, user):
    _, token = user
    res = client.post("/api/import/legacy", headers=auth(token), json=LEGACY_EXPORT).json()
    assert res["sessions"] == 1 and res["unmatched_exercises"] == {"Valami új gyakorlat": 2}
    pulled = client.post("/api/sync", headers=auth(token), json={"cursor": 0}).json()["changes"]
    assert len(pulled["sessions"]) == 1 and len(pulled["programs"]) == 1
    assert client.post("/api/import/legacy", headers=auth(token), json={"foo": 1}).status_code == 422


def test_muscle_volume_endpoint(client, user):
    _, token = user
    res = client.get("/api/stats/muscle-volume?weeks=3&today=2026-08-02", headers=auth(token)).json()
    assert res["weeks"] == ["2026-W29", "2026-W30", "2026-W31"] and res["muscles"] == {}
