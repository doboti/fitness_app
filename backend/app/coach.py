"""Havi LLM-edzői kör (Gemini).

1. A backend tömör, strukturált összefoglalót készít (profil, súlytrend, izomterhelés, gyakorlatonkénti napló
   kommentekkel, fájdalmak, aktuális terv, a használható gyakorlatok katalógusa).
2. A modell szigorú JSON-sémában válaszol: edzői megjegyzés + változások a jövő heti tervhez.
3. A választ teljes körűen validáljuk (létező gyakorlat, érvényes nap/pozíció, ésszerű számok, rehab-védelem,
   pihentetendő izom tilalma) – ami nem felel meg, kimarad, és ezt jelezzük.
4. Az eredmény ugyanolyan, változásonként jóváhagyható javaslat, mint a szabálymotoré.

Kulcs nélkül is használható: a prompt kimásolható a Gemini chatbe, a válasz visszailleszthető (import_response).
"""
from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import gemini
from .engine import Engine
from .models import DailyLog, PainReport, User, WorkoutSession
from .planning import PlanningContext, build_context, store_proposal
from .prescription import Prescription
from .stats import weekly_muscle_sets
from .util import iso_week_id

ALLOWED_KINDS = ("progress", "band", "variant", "regress", "replace", "remove", "add")
MAX_CHANGES = 12
LIMITS = {"sets": (1, 6), "reps": (1, 60), "s": (5, 300), "band_kg": (0.5, 40)}

SYSTEM_PROMPT = """Te egy tapasztalt, óvatos személyi edző vagy, aki otthoni, saját testsúlyos és gumiszalagos edzéseket tervez.
Magyarul válaszolsz, tegezve, röviden és konkrétan.

Feladat: az összefoglaló alapján értékeld az elmúlt 4 hetet, és javasolj változásokat a jövő heti tervhez.

Szabályok:
- Csak a "catalog" listában szereplő exercise_id-ket használhatod.
- Meglévő gyakorlat módosításánál a "current_plan" napját (day) és pozícióját (position) add meg; új gyakorlatnál position = null.
- kind: progress (több ismétlés/idő), band (erősebb szalag), variant (nehezebb variáns), regress (könnyítés),
  replace (csere), remove (kihagyás), add (új gyakorlat).
- Rehab gyakorlatot ("rehab": true) SOHA ne nehezíts.
- Aktív fájdalomnál ("active_pains") ne adj olyan gyakorlatot, ami az érintett izmot erősen terheli; inkább könnyíts vagy cserélj rehab gyakorlatra.
- Óvatos progresszió: hetente legfeljebb ~10-15% ismétlés-/időnövelés gyakorlatonként.
- Vedd figyelembe a kommenteket (pl. "nehéz volt", "fájt") és a nehézség-visszajelzéseket.
- Az izomegyensúly cél: izomcsoportonként heti 10-20 súlyozott sorozat; a futás nincs benne, de terheli a lábat.
- Legfeljebb 12 változás. Ha valami jól megy, hagyd változatlanul.
- Minden változáshoz rövid, konkrét indoklás (reason).
- A coach_note 3-6 mondatos értékelés: mi ment jól, mire figyeljen, mi a következő hónap fókusza.
Nem adsz orvosi diagnózist; tartós vagy éles fájdalomnál javasold szakember felkeresését."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "coach_note": {"type": "string", "description": "3-6 mondatos értékelés magyarul"},
        "focus": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "changes": {
            "type": "array",
            "maxItems": MAX_CHANGES,
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(ALLOWED_KINDS)},
                    "day": {"type": "string", "description": "A hét napja: '1' = hétfő … '7' = vasárnap"},
                    "position": {"type": ["integer", "null"]},
                    "exercise_id": {"type": ["string", "null"]},
                    "sets": {"type": ["integer", "null"]},
                    "unit": {"type": ["string", "null"], "enum": ["reps", "s", None]},
                    "value": {"type": ["integer", "null"], "description": "ismétlés vagy másodperc sorozatonként"},
                    "per_side": {"type": "boolean"},
                    "band_kg": {"type": ["number", "null"]},
                    "reason": {"type": "string"},
                },
                "required": ["kind", "day", "reason"],
            },
        },
    },
    "required": ["coach_note", "changes"],
}


# --- összefoglaló --------------------------------------------------------------------------------

def build_summary(db: Session, user: User, ctx: PlanningContext) -> dict:
    since = (ctx.today - timedelta(days=28)).isoformat()
    names = ctx.muscle_names

    weights = {}
    for log in db.scalars(select(DailyLog).where(DailyLog.user_id == user.id, DailyLog.deleted.is_(False),
                                                 DailyLog.weight_kg.is_not(None),
                                                 DailyLog.date >= (ctx.today - timedelta(weeks=8)).isoformat())):
        weights.setdefault(iso_week_id(log.date), []).append(log.weight_kg)

    sessions = list(db.scalars(select(WorkoutSession).where(
        WorkoutSession.user_id == user.id, WorkoutSession.deleted.is_(False),
        WorkoutSession.date >= since, WorkoutSession.date <= ctx.today.isoformat()).order_by(WorkoutSession.date)))
    exercise_log: dict[str, dict] = {}
    planned = completed = 0
    cardio = []
    for s in sessions:
        if s.cardio_distance_km or s.cardio_duration_min:
            cardio.append({"date": s.date, "km": s.cardio_distance_km, "min": s.cardio_duration_min})
        for e in s.entries:
            if e.archived:
                continue
            planned += 1
            completed += int(e.completed)
            key = e.exercise_id or e.name_raw
            item = exercise_log.setdefault(key, {"exercise_id": e.exercise_id, "name": e.name_raw, "sessions": []})
            item["sessions"].append({k: v for k, v in {
                "date": s.date, "target": e.target_raw, "completed": e.completed,
                "values": [x.reps if x.reps is not None else x.duration_s for x in e.sets] or None,
                "difficulty": e.difficulty, "band_kg": e.band_kg, "rehab": e.is_rehab or None,
                "comment": (e.comment or "")[:200] or None}.items() if v is not None})
    for item in exercise_log.values():
        item["sessions"] = item["sessions"][-6:]

    pains = db.scalars(select(PainReport).where(PainReport.user_id == user.id, PainReport.deleted.is_(False),
                                                PainReport.date >= (ctx.today - timedelta(days=30)).isoformat()))
    volume = weekly_muscle_sets(db, user, 4, ctx.today)

    return {
        "today": ctx.today.isoformat(),
        "base_week": ctx.base.week_id,
        "target_week": ctx.target_week,
        "profile": {"gender": user.gender, "age": user.age, "height_cm": user.height_cm,
                    "target_weight_kg": user.target_weight_kg},
        "weight_weekly_avg": {w: round(sum(v) / len(v), 2) for w, v in sorted(weights.items())},
        "muscle_weekly_sets": {"weeks": volume["weeks"],
                               "muscles": {names.get(m, m): v for m, v in volume["muscles"].items()}},
        "adherence_last_4_weeks": {"planned_exercises": planned, "completed_exercises": completed},
        "cardio": cardio,
        "active_pains": [{"date": p.date, "area": p.body_area, "muscle": names.get(p.muscle_code, p.muscle_code),
                          "side": p.side, "intensity": p.intensity, "kind": p.kind, "note": p.note,
                          "resolved": bool(p.resolved_at)} for p in pains],
        "exercise_log": list(exercise_log.values()),
        "current_plan": {
            day: {"name": d.get("name"), "exercises": [
                {"position": i, "exercise_id": ex.get("exercise_id"), "name": ex.get("name"), "target": ex.get("target"),
                 "rehab": bool(ex.get("rehab"))} for i, ex in enumerate(d.get("exercises", []))]}
            for day, d in sorted(ctx.base_days.items())},
        "known_bands_kg": ctx.bands,
        "catalog": [
            {"id": c.id, "name": c.name, "measure": c.measure, "equipment": c.equipment, "unilateral": c.unilateral,
             "chain": c.chain, "level": c.level, "rehab": c.rehab_suitable,
             "main_muscles": [names.get(m, m) for m, w in sorted(c.muscles.items(), key=lambda kv: -kv[1]) if w >= 0.5]}
            for c in sorted(ctx.catalog.values(), key=lambda c: c.id)],
    }


def build_prompt(summary: dict) -> str:
    return ("Az elmúlt 4 hét összefoglalója (JSON). Készítsd el az értékelést és a jövő heti terv változásait "
            "a megadott JSON formátumban.\n\n" + json.dumps(summary, ensure_ascii=False, indent=1))


def manual_prompt(db: Session, user: User, today=None) -> dict:
    """A Gemini chatbe másolható teljes szöveg (rendszer-utasítás + séma + adatok)."""
    ctx = build_context(db, user, today)
    summary = build_summary(db, user, ctx)
    text = (SYSTEM_PROMPT + "\n\nKizárólag egyetlen JSON objektummal válaszolj, ennek a sémának megfelelően:\n"
            + json.dumps(RESPONSE_SCHEMA, ensure_ascii=False) + "\n\n" + build_prompt(summary))
    return {"prompt": text, "base_week_id": ctx.base.week_id, "target_week_id": ctx.target_week}


# --- válasz validálása -----------------------------------------------------------------------------

def _in_range(value, key) -> bool:
    lo, hi = LIMITS[key]
    return value is not None and lo <= value <= hi


def validate_changes(raw_changes: list, ctx: PlanningContext) -> tuple[list[dict], list[str]]:
    engine: Engine = ctx.engine()
    accepted: list[dict] = []
    dropped: list[str] = []
    used_positions: set[tuple[str, int]] = set()

    for i, raw in enumerate(raw_changes[:MAX_CHANGES * 2]):
        label = f"#{i + 1}"
        try:
            if not isinstance(raw, dict):
                raise ValueError("hibás formátum")
            kind = raw.get("kind")
            day = str(raw.get("day", ""))
            reason = str(raw.get("reason") or "").strip()[:400]
            if kind not in ALLOWED_KINDS:
                raise ValueError(f"ismeretlen típus: {kind}")
            if day not in ctx.base_days:
                raise ValueError(f"nincs ilyen edzésnap a tervben: {day}")
            exercises = ctx.base_days[day].get("exercises", [])

            before = None
            if kind != "add":
                position = raw.get("position")
                if not isinstance(position, int) or not 0 <= position < len(exercises):
                    raise ValueError(f"érvénytelen pozíció: {position}")
                if (day, position) in used_positions:
                    raise ValueError("ugyanarra a gyakorlatra több változás")
                before = exercises[position]
                label = f"{before.get('name')} ({day}. nap)"
                if before.get("rehab") and kind in ("progress", "band", "variant"):
                    raise ValueError("rehab gyakorlatot nem nehezítünk")
            else:
                position = None

            if kind == "remove":
                after = None
            else:
                exercise_id = raw.get("exercise_id") or (before or {}).get("exercise_id")
                exercise = ctx.catalog.get(exercise_id)
                if exercise is None:
                    raise ValueError(f"nincs a katalógusban: {exercise_id}")
                label = f"{exercise.name} ({day}. nap)"
                conflicts = engine.conflicts(exercise)
                # könnyítés fájdalomnál is mehet (csökkenti a terhelést), minden más tilos a kímélt izmon
                if conflicts and not exercise.rehab_suitable and kind != "regress":
                    raise ValueError("aktív fájdalom miatt kímélt izmot terhel: " + ", ".join(ctx.muscle_names.get(m, m) for m in conflicts))
                old = (before or {}).get("prescription") or {}
                unit = raw.get("unit") or old.get("unit") or ("s" if exercise.measure == "time" else "reps")
                sets = raw.get("sets") or old.get("sets") or 3
                value = raw.get("value")
                band = raw.get("band_kg") if raw.get("band_kg") is not None else old.get("band_kg")
                if unit not in ("reps", "s"):
                    raise ValueError(f"érvénytelen egység: {unit}")
                if not _in_range(sets, "sets"):
                    raise ValueError(f"irreális sorozatszám: {sets}")
                if not _in_range(value, unit if unit == "s" else "reps"):
                    raise ValueError(f"irreális érték: {value}")
                if band is not None and not _in_range(band, "band_kg"):
                    raise ValueError(f"irreális szalag: {band}")
                presc = Prescription(sets=int(sets), unit=unit, min=int(value), max=int(value),
                                     per_side=bool(raw.get("per_side", old.get("per_side", exercise.unilateral))),
                                     band_kg=band)
                rehab = exercise.rehab_suitable and kind in ("replace", "add") or bool((before or {}).get("rehab"))
                after = Engine.planned_item(exercise.name, exercise.id, presc, rehab=rehab)

            if position is not None:
                used_positions.add((day, position))
            accepted.append({
                "id": f"c{len(accepted) + 1}", "day": day, "position": position, "kind": kind,
                "reason": reason or "(nincs indoklás)",
                "before": {k: before.get(k) for k in ("name", "exercise_id", "target", "prescription")} if before else None,
                "after": after,
            })
        except ValueError as exc:
            dropped.append(f"{label}: {exc}")
        if len(accepted) >= MAX_CHANGES:
            break
    return accepted, dropped


def _proposal_from_response(db: Session, user: User, ctx: PlanningContext, data: dict, meta: dict):
    if not isinstance(data, dict) or not isinstance(data.get("changes"), list):
        raise gemini.GeminiError("A válaszból hiányzik a 'changes' lista.")
    changes, dropped = validate_changes(data["changes"], ctx)
    changed_positions = {(c["day"], c["position"]) for c in changes if c["position"] is not None}
    total = sum(len(d.get("exercises", [])) for d in ctx.base_days.values())
    insights = [f"A Gemini javaslatából kihagyva – {d}" for d in dropped]
    focus = [str(f)[:200] for f in (data.get("focus") or []) if f][:4]
    return store_proposal(db, user, ctx, "llm", {
        "coach_note": str(data.get("coach_note") or "")[:2000],
        "focus": focus,
        "changes": changes,
        "unchanged": total - len(changed_positions),
        "insights": insights,
        **meta,
    })


def run_review(db: Session, user: User, today=None, generate=None):
    """Automatikus kör a Gemini API-val (GEMINI_API_KEY kell)."""
    ctx = build_context(db, user, today)
    result = (generate or gemini.generate_json)(SYSTEM_PROMPT, build_prompt(build_summary(db, user, ctx)), RESPONSE_SCHEMA)
    return _proposal_from_response(db, user, ctx, result.data, {"model": result.model, "usage": result.usage})


def import_response(db: Session, user: User, response, today=None):
    """Kézi kör: a Gemini chatből bemásolt válasz (szöveg vagy már dekódolt JSON)."""
    ctx = build_context(db, user, today)
    data = gemini.extract_json(response) if isinstance(response, str) else response
    return _proposal_from_response(db, user, ctx, data, {"model": "kézi (Gemini chat)"})
