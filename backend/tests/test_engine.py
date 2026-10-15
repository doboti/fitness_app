import json

import pytest

from app import config
from app.engine import ActivePain, CatalogExercise, Engine, Performance, apply_changes, format_target, next_week_id
from app.prescription import Prescription, parse_target

SEED = json.loads(config.SEED_FILE.read_text(encoding="utf-8"))
REGIONS = {m["code"]: m["region"] for m in SEED["muscles"]}
NAMES = {m["code"]: m["name_hu"] for m in SEED["muscles"]}
CATALOG = {
    e["id"]: CatalogExercise(
        id=e["id"], name=e["name_hu"], measure=e["measure"], muscles=e["muscles"],
        region=REGIONS[max(e["muscles"], key=e["muscles"].get)], chain=e.get("chain"), level=e.get("level"),
        rehab_suitable=e.get("rehab_suitable", False), equipment=e["equipment"], unilateral=e.get("unilateral", False))
    for e in SEED["exercises"]
}


def planned(exercise_id, target, rehab=False):
    item = {"name": CATALOG[exercise_id].name, "exercise_id": exercise_id, "target": target,
            "prescription": parse_target(target).to_dict()}
    if rehab:
        item["rehab"] = True
    return item


def perf(target, values=None, difficulty="ok", completed=True, band=None, date="2026-10-12", rehab=False):
    p = parse_target(target)
    if band:
        p.band_kg = band
    return Performance(date=date, presc=p, values=values or [], completed=completed,
                       difficulty=difficulty, band_kg=band, is_rehab=rehab)


def decide(item, history, bands=(), pains=()):
    return Engine(CATALOG, list(pains), NAMES).decide(item, history, list(bands))


@pytest.mark.parametrize("p", [
    Prescription(sets=4, unit="reps", min=11, max=11),
    Prescription(sets=3, unit="reps", min=12, max=12, per_side=True),
    Prescription(sets=4, unit="reps", min=8, max=10),
    Prescription(sets=4, unit="s", min=75, max=75),
    Prescription(sets=3, unit="s", min=45, max=45),
    Prescription(sets=3, unit="s", min=30, max=30, per_side=True),
    Prescription(sets=4, unit="reps", min=12, max=12, band_kg=6.75),
    Prescription(sets=3, unit="reps", to_failure=True),
])
def test_format_target_roundtrip(p):
    assert parse_target(format_target(p)) == p


def test_progression_reps_and_double_step():
    item = planned("push_up", "4 kör x 10 ismétlés")
    kind, after, reason = decide(item, [perf("4 kör x 10", [10, 10, 10, 10])])
    assert (kind, after["prescription"]["max"], after["target"]) == ("progress", 11, "4 kör x 11 ismétlés")
    assert "10 → 11" in reason

    kind, after, _ = decide(item, [perf("4 kör x 10", [10] * 4, "easy"), perf("4 kör x 10", [10] * 4, "easy")])
    assert after["prescription"]["max"] == 12

    # többet csinált a célnál → a ténylegesből lépünk
    _, after, _ = decide(item, [perf("4 kör x 10", [13, 12, 12, 12])])
    assert after["prescription"]["max"] == 14


def test_hold_cases():
    item = planned("push_up", "4 kör x 10 ismétlés")
    assert decide(item, [perf("4 kör x 10", [10] * 4, "hard")]) is None                 # nehéz → marad
    assert decide(item, [perf("4 kör x 10", [10, 10, 9, 8])]) is None                   # nem érte el → marad
    assert decide(item, [perf("4 kör x 10", [10] * 4, "failed")]) is None                # egy kudarc → marad
    assert decide(item, []) is None                                                     # nincs előzmény
    assert decide(item, [perf("4 kör x 10", completed=False)]) is None                  # kihagyta
    assert decide(planned("hand_release_push_up", "3 kör x Maximum"), [perf("3 kör x Maximum", [12, 10, 9])]) is None


def test_legacy_completed_without_sets_counts_as_reached():
    kind, after, _ = decide(planned("air_squat", "3 kör x 20"), [perf("3 kör x 20", None, None)])
    assert kind == "variant" or (kind == "progress" and after["prescription"]["max"] == 22)


def test_regress_after_two_failures():
    item = planned("push_up", "4 kör x 10 ismétlés")
    kind, after, _ = decide(item, [perf("4 kör x 10", [10, 9, 7, 6], None), perf("4 kör x 10", [10, 10], "failed")])
    assert (kind, after["prescription"]["max"]) == ("regress", 8)

    low = planned("hand_release_push_up", "4 kör x 5 ismétlés")
    kind, after, _ = decide(low, [perf("4 kör x 5", difficulty="failed"), perf("4 kör x 5", difficulty="failed")])
    assert (kind, after["exercise_id"], after["prescription"]["max"]) == ("regress", "deficit_push_up_stand", 10)


def test_rep_cap_band_and_variant():
    row = planned("band_seated_row", "4 kör x 20 ismétlés (6.75kg-os szalag)")
    kind, after, reason = decide(row, [perf("4 kör x 20", [20] * 4, band=6.75)], bands=[4.5, 6.75, 9])
    assert (kind, after["prescription"]["band_kg"], after["prescription"]["max"]) == ("band", 9.0, 12)
    assert "9kg-os szalag" in after["target"]

    push = planned("push_up", "4 kör x 20 ismétlés")
    kind, after, _ = decide(push, [perf("4 kör x 20", [20] * 4)])
    assert (kind, after["exercise_id"], after["prescription"]["max"]) == ("variant", "deficit_push_up_stand", 12)


def test_time_progression_and_variant():
    kind, after, _ = decide(planned("plank", "4 kör x 1 perc"), [perf("4 kör x 1 perc", [60] * 4)])
    assert (kind, after["target"]) == ("progress", "4 kör x 1 perc 5 másodperc")
    kind, after, _ = decide(planned("plank", "4 kör x 90 másodperc"), [perf("4 kör x 90 másodperc", [90] * 4)])
    assert (kind, after["exercise_id"], after["prescription"]["max"]) == ("variant", "hollow_body_hold", 45)


def test_rehab_never_progresses():
    clam = planned("clamshell", "3 kör x 15-15 ismétlés", rehab=True)
    assert decide(clam, [perf("3 kör x 15-15", [15] * 3, "easy"), perf("3 kör x 15-15", [15] * 3, "easy")]) is None
    kind, after, _ = decide(clam, [perf("3 kör x 15-15", [15] * 3, "hard"), perf("3 kör x 15-15", [15] * 3, "hard")])
    assert (kind, after["prescription"]["max"], after["rehab"]) == ("regress", 13, True)


def test_pain_rules():
    push = planned("push_up", "4 kör x 10 ismétlés")
    history = [perf("4 kör x 10", [10] * 4, "easy")]

    mild = ActivePain(body_area="chest", muscle_code="chest", intensity=2, kind="discomfort")
    kind, after, reason = decide(push, history, pains=[mild])
    assert (kind, after["exercise_id"]) == ("regress", "incline_push_up")
    assert "Mellizom" in reason

    severe = ActivePain(body_area="wrist", muscle_code="forearms", intensity=7, kind="sharp")
    kind, after, _ = decide(push, history, pains=[severe])   # csukló → mell/tricepsz kímélése → felsőtestes rehab
    assert (kind, after["exercise_id"]) == ("replace", "band_pull_apart")

    shoulder = ActivePain(body_area="shoulder", muscle_code="front_delt", intensity=6, kind="dull")
    kind, _, _ = decide(push, history, pains=[shoulder])     # váll: a széthúzás is a vállat terheli → nincs csere, kihagyás
    assert kind == "remove"

    knee = ActivePain(body_area="knee_lateral", muscle_code=None, intensity=5, kind="dull")
    kind, after, _ = decide(planned("walking_lunge", "4 kör x 12-12 lépés"), [perf("4 kör x 12-12", [12] * 4)], pains=[knee])
    assert kind == "replace" and CATALOG[after["exercise_id"]].rehab_suitable and after["rehab"]
    assert CATALOG[after["exercise_id"]].muscles.get("quads", 0) < 0.5

    # a rehab gyakorlatot a fájdalom nem érinti
    assert decide(planned("glute_bridge", "3 kör x 15", rehab=True), [], pains=[knee]) is None


def test_additions_for_undertrained_muscles():
    base = {"1": {"name": "H", "exercises": [planned("push_up", "4 kör x 10")] * 3},
            "3": {"name": "Sze", "exercises": [planned("plank", "4 kör x 60 másodperc")]}}
    engine = Engine(CATALOG, [], NAMES)
    result = engine.propose(base, {}, [], {"quads": 1.6, "glute_med": 0.0, "hamstrings": 0.0, "chest": 15})
    adds = [c for c in result.changes if c.kind == "add"]
    assert [a.after["exercise_id"] for a in adds] == ["clamshell", "air_squat"]
    assert [a.day for a in adds] == ["3", "3"]       # a kevésbé terhelt napra
    assert "Középső farizom" in adds[0].reason
    assert result.unchanged == 4


def test_apply_changes():
    base = {"1": {"name": "H", "exercises": [planned("push_up", "4 kör x 10"), planned("plank", "4 kör x 1 perc"),
                                             planned("air_squat", "3 kör x 20")]}}
    changes = [
        {"id": "c1", "day": "1", "position": 0, "kind": "progress", "after": planned("push_up", "4 kör x 11")},
        {"id": "c2", "day": "1", "position": 1, "kind": "remove", "after": None},
        {"id": "c3", "day": "1", "position": None, "kind": "add", "after": planned("clamshell", "3 kör x 12-12")},
        {"id": "c4", "day": "1", "position": 2, "kind": "progress", "after": planned("air_squat", "3 kör x 22")},
    ]
    days = apply_changes(base, changes, {"c1", "c2", "c3"})
    assert [e["target"] for e in days["1"]["exercises"]] == ["4 kör x 11", "3 kör x 20", "3 kör x 12-12"]
    assert base["1"]["exercises"][0]["target"] == "4 kör x 10"   # az eredeti nem módosul


def test_next_week_id():
    assert next_week_id("2026-W42") == "2026-W43"
    assert next_week_id("2026-W53") == "2027-W01"
