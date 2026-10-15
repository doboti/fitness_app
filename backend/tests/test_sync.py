from conftest import auth


def _session(updated_at="2026-10-15T10:00:00.000Z", **overrides):
    doc = {
        "id": "s-1", "date": "2026-10-14", "title": "Push A", "updated_at": updated_at,
        "cardio_distance_km": 5.2, "cardio_duration_min": 31,
        "entries": [
            {"position": 0, "exercise_id": "push_up", "name_raw": "Standard Push-up", "target_raw": "4 kör x 10",
             "presc_sets": 4, "presc_unit": "reps", "presc_min": 10, "presc_max": 10, "completed": True,
             "difficulty": "hard", "comment": "utolsó kör nehéz volt",
             "sets": [{"set_no": 1, "reps": 10}, {"set_no": 2, "reps": 10}, {"set_no": 3, "reps": 9, "difficulty": "hard"}]},
            {"position": 1, "exercise_id": "glute_bridge", "name_raw": "Glute Bridge", "is_rehab": True, "completed": True},
        ],
    }
    doc.update(overrides)
    return doc


def test_requires_token(client):
    assert client.post("/api/sync", json={}).status_code == 401
    assert client.post("/api/sync", json={}, headers=auth("rossz")).status_code == 401


def test_push_then_pull_on_second_device(client, user):
    _, token = user
    push = client.post("/api/sync", headers=auth(token), json={
        "cursor": 0,
        "daily_logs": [{"date": "2026-10-14", "weight_kg": 75.4, "water_ml": 1500, "updated_at": "2026-10-14T08:00:00Z"}],
        "sessions": [_session()],
        "pain_reports": [{"id": "p-1", "date": "2026-10-14", "session_id": "s-1", "muscle_code": "glute_med",
                          "side": "right", "intensity": 4, "kind": "dull", "updated_at": "2026-10-14T10:00:00Z"}],
    }).json()
    assert push["applied"] == 3 and not push["rejected"] and not push["stale"]
    # A saját push nem jön vissza visszhangként
    assert not push["changes"]["sessions"] and not push["changes"]["daily_logs"]

    pull = client.post("/api/sync", headers=auth(token), json={"cursor": 0}).json()
    changes = pull["changes"]
    assert changes["daily_logs"][0]["weight_kg"] == 75.4
    session = changes["sessions"][0]
    assert [e["exercise_id"] for e in session["entries"]] == ["push_up", "glute_bridge"]
    assert [s["reps"] for s in session["entries"][0]["sets"]] == [10, 10, 9]
    assert session["entries"][1]["is_rehab"] is True
    assert changes["pain_reports"][0]["muscle_code"] == "glute_med"
    assert changes["user"]["name"] == "teszt"

    # Kurzorral már nincs új változás
    again = client.post("/api/sync", headers=auth(token), json={"cursor": pull["cursor"]}).json()
    assert again["changes"] == {"daily_logs": [], "sessions": [], "pain_reports": [], "programs": [], "user": None}


def test_last_write_wins(client, user):
    _, token = user
    client.post("/api/sync", headers=auth(token), json={"sessions": [_session("2026-10-15T12:00:00Z")]})
    older = client.post("/api/sync", headers=auth(token),
                        json={"sessions": [_session("2026-10-15T11:00:00Z", title="régi")]}).json()
    assert older["stale"] == ["session:s-1"] and older["applied"] == 0

    # A nyertes szerverváltozat akkor is visszajön, ha a kliens kurzora már túl van rajta
    cursor = client.post("/api/sync", headers=auth(token), json={"cursor": 0}).json()["cursor"]
    stale_again = client.post("/api/sync", headers=auth(token), json={
        "cursor": cursor, "sessions": [_session("2026-10-15T11:30:00Z", title="régi")]}).json()
    assert [s["updated_at"] for s in stale_again["changes"]["sessions"]] == ["2026-10-15T12:00:00Z"]

    newer = client.post("/api/sync", headers=auth(token), json={"sessions": [
        _session("2026-10-15T13:00:00Z", title="új", entries=[])]}).json()
    assert newer["applied"] == 1
    pulled = client.post("/api/sync", headers=auth(token), json={"cursor": 0}).json()["changes"]["sessions"][0]
    assert pulled["title"] == "új" and pulled["entries"] == []


def test_soft_delete_propagates(client, user):
    _, token = user
    client.post("/api/sync", headers=auth(token), json={"sessions": [_session()]})
    cursor = client.post("/api/sync", headers=auth(token), json={"cursor": 0}).json()["cursor"]
    client.post("/api/sync", headers=auth(token), json={"sessions": [_session("2026-10-16T00:00:00Z", deleted=True)]})
    changes = client.post("/api/sync", headers=auth(token), json={"cursor": cursor}).json()["changes"]
    assert changes["sessions"][0]["deleted"] is True


def test_rejections(client, user, other_user):
    _, token = user
    _, other_token = other_user
    client.post("/api/sync", headers=auth(other_token), json={"sessions": [_session()]})

    res = client.post("/api/sync", headers=auth(token), json={
        "sessions": [
            _session(),  # s-1 a másik felhasználóé
            _session(id="s-2", entries=[{"position": 0, "exercise_id": "nincs_ilyen", "name_raw": "x"}]),
            _session(id="s-3", updated_at="tegnap"),
        ],
        "pain_reports": [{"id": "p-9", "date": "2026-10-14", "muscle_code": "nincs", "intensity": 3,
                          "kind": "sharp", "updated_at": "2026-10-14T10:00:00Z"}],
    }).json()
    assert set(res["rejected"]) == {"session:s-1", "session:s-2", "session:s-3", "pain:p-9"}
    assert res["applied"] == 0


def test_users_are_isolated(client, user, other_user):
    _, token = user
    _, other_token = other_user
    client.post("/api/sync", headers=auth(token), json={
        "daily_logs": [{"date": "2026-10-14", "weight_kg": 80, "updated_at": "2026-10-14T08:00:00Z"}]})
    other = client.post("/api/sync", headers=auth(other_token), json={"cursor": 0}).json()["changes"]
    assert other["daily_logs"] == [] and other["user"]["name"] == "masik"


def test_validation_errors(client, user):
    _, token = user
    bad = client.post("/api/sync", headers=auth(token), json={
        "pain_reports": [{"id": "p", "date": "2026-10-14", "intensity": 11, "kind": "sharp", "updated_at": "x"}]})
    assert bad.status_code == 422
