from conftest import auth

PROGRAM = {
    "week_id": "2026-W42", "week_label": "Teszt hét",
    "program": {
        "1": {"name": "Hétfő", "circuits": 4, "exercises": [
            {"name": "Standard Push-up", "target": "4 kör x 10 ismétlés"},
            {"name": "Standard Plank", "target": "3 kör x 60 másodperc"},
        ]},
    },
}


def _session(date, push_sets, plank_sets, plank_difficulty="easy"):
    return {
        "id": f"s-{date}", "date": date, "updated_at": f"{date}T18:00:00Z",
        "entries": [
            {"position": 0, "exercise_id": "push_up", "name_raw": "Fekvőtámasz", "presc_sets": 4, "presc_unit": "reps",
             "presc_min": 10, "presc_max": 10, "completed": True, "difficulty": "ok",
             "sets": [{"set_no": i + 1, "reps": r} for i, r in enumerate(push_sets)]},
            {"position": 1, "exercise_id": "plank", "name_raw": "Plank", "presc_sets": 3, "presc_unit": "s",
             "presc_min": 60, "presc_max": 60, "completed": True, "difficulty": plank_difficulty,
             "sets": [{"set_no": i + 1, "duration_s": d} for i, d in enumerate(plank_sets)]},
        ],
    }


def test_proposal_lifecycle(client, user):
    _, token = user
    h = auth(token)
    assert client.post("/api/plan/proposals?today=2026-10-15", headers=h).status_code == 422   # még nincs terv

    client.post("/api/programs", headers=h, json=PROGRAM)
    client.post("/api/sync", headers=h, json={"sessions": [_session("2026-10-12", [10, 10, 10, 10], [60, 60, 60])]})

    proposal = client.post("/api/plan/proposals?today=2026-10-15", headers=h).json()
    assert (proposal["base_week_id"], proposal["target_week_id"], proposal["status"]) == ("2026-W42", "2026-W43", "pending")
    by_exercise = {c["before"]["exercise_id"]: c for c in proposal["changes"] if c["before"]}
    assert by_exercise["push_up"]["after"]["target"] == "4 kör x 11 ismétlés"
    assert by_exercise["plank"]["after"]["target"] == "3 kör x 1 perc 5 másodperc"

    # csak a fekvőtámasz-változást fogadjuk el
    program = client.post(f"/api/plan/proposals/{proposal['id']}/accept", headers=h,
                          json={"change_ids": [by_exercise["push_up"]["id"]]}).json()
    assert program["week_id"] == "2026-W43" and program["source"] == "engine"
    targets = [e["target"] for e in program["days"]["1"]["exercises"]]
    assert targets[:2] == ["4 kör x 11 ismétlés", "3 kör x 60 másodperc"]
    assert program["days"]["1"]["exercises"][0]["prescription"]["max"] == 11

    # a telefonra a szinkronnal jut el
    pulled = client.post("/api/sync", headers=h, json={"cursor": 0}).json()["changes"]["programs"]
    assert {p["week_id"] for p in pulled} == {"2026-W42", "2026-W43"}

    # már elfogadott javaslat nem fogadható el újra
    again = client.post(f"/api/plan/proposals/{proposal['id']}/accept", headers=h, json={"change_ids": []})
    assert again.status_code == 422
    assert client.get("/api/plan/proposals", headers=h).json()[0]["status"] == "accepted"


def test_new_proposal_supersedes_and_reject(client, user, other_user):
    _, token = user
    h = auth(token)
    client.post("/api/programs", headers=h, json=PROGRAM)
    first = client.post("/api/plan/proposals?today=2026-10-15", headers=h).json()
    second = client.post("/api/plan/proposals?today=2026-10-16", headers=h).json()
    statuses = {p["id"]: p["status"] for p in client.get("/api/plan/proposals", headers=h).json()}
    assert statuses == {first["id"]: "superseded", second["id"]: "pending"}
    assert second["changes"] == [] and second["unchanged"] == 2      # nincs napló → minden marad
    assert any("nincs naplózott edzés" in i for i in second["insights"])


    _, other_token = other_user
    assert client.post(f"/api/plan/proposals/{second['id']}/reject", headers=auth(other_token)).status_code == 404
    assert client.post(f"/api/plan/proposals/{second['id']}/accept", headers=h, json={"change_ids": ["c99"]}).status_code == 422
    assert client.post(f"/api/plan/proposals/{second['id']}/reject", headers=h).json()["status"] == "rejected"

    later = client.post("/api/plan/proposals?today=2026-11-05", headers=h).json()   # régi terv → jelzés
    assert later["insights"][0].startswith("A legutóbbi heti terv a 2026-W42")


def test_pain_and_failure_drive_proposal(client, user):
    _, token = user
    h = auth(token)
    client.post("/api/programs", headers=h, json=PROGRAM)
    client.post("/api/sync", headers=h, json={
        "sessions": [_session("2026-10-12", [10, 8, 7, 6], [40, 30, 30], "failed"),
                     _session("2026-10-09", [10, 10, 10, 10], [35, 30, 30], "failed")],
        "pain_reports": [{"id": "p1", "date": "2026-10-13", "body_area": "chest", "muscle_code": "chest",
                          "intensity": 2, "kind": "discomfort", "updated_at": "2026-10-13T10:00:00Z"}],
    })
    proposal = client.post("/api/plan/proposals?today=2026-10-15", headers=h).json()
    by_exercise = {c["before"]["exercise_id"]: c for c in proposal["changes"] if c["before"]}
    assert by_exercise["push_up"]["kind"] == "regress" and by_exercise["push_up"]["after"]["exercise_id"] == "incline_push_up"
    assert "Mellizom" in by_exercise["push_up"]["reason"]
    assert by_exercise["plank"]["kind"] == "regress" and by_exercise["plank"]["after"]["prescription"]["max"] == 50
    assert any("Mellizom" in i for i in proposal["insights"])
