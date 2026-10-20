import json

import pytest

from app import gemini
from conftest import auth

PROGRAM = {
    "week_id": "2026-W42",
    "program": {
        "1": {"name": "Hétfő", "circuits": 4, "exercises": [
            {"name": "Standard Push-up", "target": "4 kör x 10 ismétlés"},
            {"name": "Standard Plank", "target": "3 kör x 60 másodperc"},
            {"name": "Clamshell", "target": "3 kör x 15-15 ismétlés", "rehab": True},
        ]},
        "3": {"name": "Szerda", "circuits": 3, "exercises": [
            {"name": "Air Squat", "target": "3 kör x 20 ismétlés"},
        ]},
    },
}

GOOD_RESPONSE = {
    "coach_note": "Szép, egyenletes hónap volt. A fekvőtámasz stabil, jöhet a következő lépés.",
    "focus": ["Farizom erősítése a futáshoz"],
    "changes": [
        {"kind": "regress", "day": "1", "position": 0, "exercise_id": "push_up", "sets": 4, "unit": "reps", "value": 8,
         "reason": "Húzódott a mellizom – egy hétig kevesebb ismétlés."},
        {"kind": "progress", "day": "1", "position": 0, "exercise_id": "push_up", "value": 13, "reason": "duplikált"},
        {"kind": "progress", "day": "1", "position": 2, "exercise_id": "clamshell", "value": 20, "reason": "rehab nehezítés"},
        {"kind": "replace", "day": "3", "position": 0, "exercise_id": "nincs_ilyen", "value": 10, "reason": "?"},
        {"kind": "progress", "day": "3", "position": 0, "exercise_id": "air_squat", "value": 500, "reason": "túl sok"},
        {"kind": "add", "day": "3", "position": None, "exercise_id": "incline_push_up", "value": 10, "reason": "mell"},
        {"kind": "add", "day": "3", "position": None, "exercise_id": "single_leg_glute_bridge", "sets": 3, "unit": "reps",
         "value": 10, "per_side": True, "reason": "Farizom a futáshoz."},
        {"kind": "remove", "day": "1", "position": 1, "reason": "A plank helyett a hollow body van a szerdai napon."},
        {"kind": "progress", "day": "9", "position": 0, "value": 5, "reason": "nincs ilyen nap"},
    ],
}


@pytest.fixture()
def setup(client, user):
    _, token = user
    h = auth(token)
    client.post("/api/programs", headers=h, json=PROGRAM)
    client.post("/api/sync", headers=h, json={
        "sessions": [{"id": "s1", "date": "2026-10-12", "updated_at": "2026-10-12T18:00:00Z", "entries": [
            {"position": 0, "exercise_id": "push_up", "name_raw": "Fekvőtámasz", "presc_sets": 4, "presc_unit": "reps",
             "presc_min": 10, "presc_max": 10, "completed": True, "difficulty": "easy",
             "comment": "könnyen ment, a végén picit húzódott a mellem",
             "sets": [{"set_no": i, "reps": 10} for i in range(1, 5)]}]}],
        "pain_reports": [{"id": "p1", "date": "2026-10-13", "body_area": "chest", "muscle_code": "chest",
                          "intensity": 3, "kind": "discomfort", "updated_at": "2026-10-13T10:00:00Z"}],
    })
    return h


def test_extract_json():
    assert gemini.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert gemini.extract_json('Íme:\n{"a": {"b": [1, 2]}}\nRemélem segít!') == {"a": {"b": [1, 2]}}
    with pytest.raises(gemini.GeminiError):
        gemini.extract_json("nincs itt json")
    with pytest.raises(gemini.GeminiError):
        gemini.extract_json("{hibás: json}")


def test_generate_json_fallback_and_parsing():
    calls = []

    def post(url, body, key, timeout):
        calls.append(body["generationConfig"])
        if "responseJsonSchema" in body["generationConfig"]:
            raise gemini.GeminiError("HTTP 400: Unknown name responseJsonSchema")
        return {"candidates": [{"content": {"parts": [{"text": "gondolkodom…", "thought": True},
                                                      {"text": '{"coach_note": "ok", "changes": []}'}]}}],
                "usageMetadata": {"totalTokenCount": 1234}}

    result = gemini.generate_json("sys", "prompt", {"type": "object"}, api_key="k", model="m", post=post)
    assert result.data == {"coach_note": "ok", "changes": []} and result.usage["totalTokenCount"] == 1234
    assert len(calls) == 2 and "responseJsonSchema" not in calls[1]

    blocked = lambda *a: {"promptFeedback": {"blockReason": "SAFETY"}}  # noqa: E731
    with pytest.raises(gemini.GeminiError, match="SAFETY"):
        gemini.generate_json("s", "p", {}, api_key="k", post=blocked)
    with pytest.raises(gemini.GeminiError, match="GEMINI_API_KEY"):
        gemini.generate_json("s", "p", {}, api_key=None, post=blocked)


def test_prompt_contains_summary(client, setup):
    res = client.get("/api/coach/prompt?today=2026-10-15", headers=setup).json()
    prompt = res["prompt"]
    assert res["target_week_id"] == "2026-W43"
    assert '"id": "single_leg_glute_bridge"' in prompt              # katalógus
    assert "húzódott a mellem" in prompt                            # kommentek
    assert '"intensity": 3' in prompt                               # fájdalom
    assert "Rehab gyakorlatot" in prompt and '"changes"' in prompt   # szabályok + séma


def test_import_validates_and_creates_proposal(client, setup):
    proposal = client.post("/api/coach/import?today=2026-10-15", headers=setup,
                           json={"response": "```json\n" + json.dumps(GOOD_RESPONSE, ensure_ascii=False) + "\n```"}).json()
    assert proposal["source"] == "llm" and proposal["coach_note"].startswith("Szép")
    assert proposal["focus"] == ["Farizom erősítése a futáshoz"]
    kept = [(c["kind"], c["day"], c["position"], (c["after"] or {}).get("exercise_id")) for c in proposal["changes"]]
    assert kept == [("regress", "1", 0, "push_up"), ("add", "3", None, "single_leg_glute_bridge"), ("remove", "1", 1, None)]
    assert proposal["changes"][0]["after"]["target"] == "4 kör x 8 ismétlés"
    assert proposal["changes"][1]["after"]["target"] == "3 kör x 10-10 ismétlés" and proposal["changes"][1]["after"]["rehab"]
    dropped = "\n".join(proposal["insights"])
    for reason in ("több változás", "rehab", "nincs a katalógusban", "irreális érték", "kímélt izmot", "nincs ilyen edzésnap"):
        assert reason in dropped, reason
    assert proposal["unchanged"] == 2

    program = client.post(f"/api/plan/proposals/{proposal['id']}/accept", headers=setup,
                          json={"change_ids": [c["id"] for c in proposal["changes"]]}).json()
    assert program["source"] == "llm"
    assert [e["exercise_id"] for e in program["days"]["1"]["exercises"]] == ["push_up", "clamshell"]
    assert [e["exercise_id"] for e in program["days"]["3"]["exercises"]] == ["air_squat", "single_leg_glute_bridge"]


def test_import_rejects_garbage(client, setup):
    assert client.post("/api/coach/import", headers=setup, json={"response": "bocs, nem tudok segíteni"}).status_code == 422
    assert client.post("/api/coach/import", headers=setup, json={"response": {"coach_note": "x"}}).status_code == 422


def test_review_requires_key_and_uses_gemini(client, setup, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert client.get("/api/coach/status", headers=setup).json()["configured"] is False
    assert client.post("/api/coach/review", headers=setup).status_code == 503

    monkeypatch.setenv("GEMINI_API_KEY", "teszt-kulcs")
    sent = {}

    def fake_post(url, body, key, timeout):
        sent.update(url=url, key=key, body=body)
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(GOOD_RESPONSE)}]}}], "usageMetadata": {"totalTokenCount": 9}}

    monkeypatch.setattr(gemini, "_post", fake_post)
    proposal = client.post("/api/coach/review?today=2026-10-15", headers=setup).json()
    assert sent["key"] == "teszt-kulcs" and ":generateContent" in sent["url"]
    assert sent["body"]["systemInstruction"]["parts"][0]["text"].startswith("Te egy tapasztalt")
    assert proposal["source"] == "llm" and len(proposal["changes"]) == 3 and proposal["usage"]["totalTokenCount"] == 9

    def failing(*a):
        raise gemini.GeminiError("HTTP 429: quota")
    monkeypatch.setattr(gemini, "_post", failing)
    res = client.post("/api/coach/review?today=2026-10-15", headers=setup)
    assert res.status_code == 502 and "429" in res.json()["detail"]
