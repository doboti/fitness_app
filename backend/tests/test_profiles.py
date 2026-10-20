from app.cli import main as cli_main
from conftest import auth


def test_profile_list_needs_no_auth(client, user, other_user):
    profiles = client.get("/api/profiles").json()
    assert [(p["name"], p["gender"]) for p in profiles] == [("masik", "female"), ("teszt", "male")]
    assert set(profiles[0]) == {"id", "name", "gender"}          # tokent / egyéb adatot nem ad ki


def test_select_profile_gives_device_token(client, user, other_user):
    u, cli_token = user
    res = client.post(f"/api/profiles/{u.id}/session")
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["name"] == "teszt"
    device_token = body["token"]
    assert device_token != cli_token
    assert client.get("/api/me", headers=auth(device_token)).json()["name"] == "teszt"
    # a profilhoz tartozó adatok ugyanazok, akárhonnan választják
    client.post("/api/sync", headers=auth(device_token), json={
        "daily_logs": [{"date": "2026-10-20", "weight_kg": 75, "updated_at": "2026-10-20T08:00:00Z"}]})
    pulled = client.post("/api/sync", headers=auth(cli_token), json={"cursor": 0}).json()["changes"]["daily_logs"]
    assert pulled[0]["weight_kg"] == 75

    assert client.post("/api/profiles/9999/session").status_code == 404


def test_logout_invalidates_only_that_device(client, user):
    u, cli_token = user
    a = client.post(f"/api/profiles/{u.id}/session").json()["token"]
    b = client.post(f"/api/profiles/{u.id}/session").json()["token"]
    assert client.post("/api/logout", headers=auth(a)).json() == {"ok": True}
    assert client.get("/api/me", headers=auth(a)).status_code == 401
    assert client.get("/api/me", headers=auth(b)).status_code == 200
    assert client.get("/api/me", headers=auth(cli_token)).status_code == 200   # a CLI-token nem törölhető így
    assert client.post("/api/logout").json() == {"ok": True}                   # kulcs nélkül sem hibázik


def test_cli_rename_user(database, client, capsys):
    cli_main(["create-user", "--name", "ferfi", "--gender", "male"])
    cli_main(["create-user", "--name", "noi", "--gender", "female"])
    cli_main(["rename-user", "--name", "ferfi", "--new-name", "Boti"])
    cli_main(["rename-user", "--name", "noi", "--new-name", "Johi"])
    assert "Boti" in capsys.readouterr().out
    assert [p["name"] for p in client.get("/api/profiles").json()] == ["Boti", "Johi"]
