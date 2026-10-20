from contextlib import asynccontextmanager
from datetime import date as Date

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import coach, config, gemini, schemas
from .auth import hash_token, new_token
from .catalog import ExerciseMatcher, load_seed
from .db import get_db, get_engine, new_session
from .legacy import import_legacy, upsert_program
from .models import Base, DeviceToken, Exercise, MuscleGroup, PlanProposal, User
from .planning import PlanningError, accept_proposal, generate_proposal, proposal_to_dict
from .stats import weekly_muscle_sets
from .sync import apply_sync, current_cursor, program_to_doc
from .util import next_seq, now_iso


def init_database() -> None:
    Base.metadata.create_all(get_engine())
    with new_session() as db:
        load_seed(db)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(title="Workout Tracker API", version="0.1.0", lifespan=lifespan)

if config.CORS_ORIGINS:
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS,
                       allow_methods=["*"], allow_headers=["*"])


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Hiányzó token", headers={"WWW-Authenticate": "Bearer"})
    digest = hash_token(token)
    device = db.get(DeviceToken, digest)
    user = db.get(User, device.user_id) if device else db.scalar(select(User).where(User.token_hash == digest))
    if user is None:
        raise HTTPException(401, "Érvénytelen token", headers={"WWW-Authenticate": "Bearer"})
    return user


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    return {"status": "ok", "cursor": current_cursor(db)}


# --- profilválasztás (jelszó nélkül; a szerver csak a Tailscale-en érhető el) ---

@app.get("/api/profiles", response_model=list[schemas.ProfileOut])
def list_profiles(db: Session = Depends(get_db)):
    """A választható profilok a belépő képernyő legördülő menüjéhez."""
    return db.scalars(select(User).order_by(User.name)).all()


@app.post("/api/profiles/{user_id}/session")
def open_profile(user_id: int, request: Request, db: Session = Depends(get_db)):
    """Profil kiválasztása: az eszköz saját hozzáférési kulcsot kap ehhez a profilhoz."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Nincs ilyen profil")
    token = new_token()
    db.add(DeviceToken(token_hash=hash_token(token), user_id=user.id, created_at=now_iso(),
                       user_agent=(request.headers.get("user-agent") or "")[:200] or None))
    db.commit()
    return {"token": token, "user": schemas.UserOut.model_validate(user)}


@app.post("/api/logout")
def logout(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    """Az adott eszköz kulcsának érvénytelenítése."""
    _, _, token = authorization.partition(" ")
    device = db.get(DeviceToken, hash_token(token)) if token else None
    if device:
        db.delete(device)
        db.commit()
    return {"ok": True}


# --- katalógus --------------------------------------------------------------

@app.get("/api/muscles", response_model=list[schemas.MuscleOut])
def list_muscles(db: Session = Depends(get_db)):
    return db.scalars(select(MuscleGroup).order_by(MuscleGroup.region, MuscleGroup.code)).all()


@app.get("/api/exercises", response_model=list[schemas.ExerciseOut])
def list_exercises(db: Session = Depends(get_db)):
    rows = db.scalars(select(Exercise).where(Exercise.active.is_(True))
                      .order_by(Exercise.chain, Exercise.level, Exercise.name_hu))
    return [
        schemas.ExerciseOut(
            **{c: getattr(ex, c) for c in ("id", "name_hu", "name_en", "equipment", "measure", "unilateral",
                                            "rehab_suitable", "chain", "level", "image", "description")},
            muscles={m.muscle_code: m.weight for m in ex.muscles},
            aliases=sorted(a.alias for a in ex.aliases),
        )
        for ex in rows
    ]


# --- felhasználó ------------------------------------------------------------

@app.get("/api/me", response_model=schemas.UserOut)
def get_me(user: User = Depends(current_user)):
    return user


@app.put("/api/me", response_model=schemas.UserOut)
def update_me(body: schemas.UserUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user = db.merge(user)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    user.updated_at = now_iso()
    user.server_seq = next_seq(db)
    db.commit()
    return user


# --- szinkron ---------------------------------------------------------------

@app.post("/api/sync", response_model=schemas.SyncResponse)
def sync(body: schemas.SyncRequest, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return apply_sync(db, db.merge(user), body)


# --- heti tervek ------------------------------------------------------------

@app.post("/api/programs", response_model=schemas.ProgramDoc)
def import_program(body: schemas.LegacyWeeklyProgram, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    """Heti terv feltöltése a régi app JSON formátumában (week_id, week_label, program)."""
    row = upsert_program(db, db.merge(user), body.week_id, body.week_label, body.program, "manual",
                         ExerciseMatcher(db))
    db.commit()
    return program_to_doc(row)


@app.post("/api/import/legacy")
def import_legacy_export(body: dict = Body(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """A régi egyfájlos app exportja (results/*.json) vagy egy heti terv fájl betöltése a saját fiókba."""
    if not any(k in body for k in ("daily_logs", "workout_logs", "weekly_programs", "program")):
        raise HTTPException(422, "Ez nem a régi app exportja vagy heti terve.")
    return import_legacy(db, db.merge(user), body)


# --- tervjavaslatok (szabálymotor) ------------------------------------------

class AcceptBody(BaseModel):
    change_ids: list[str]


def _own_proposal(db: Session, user: User, proposal_id: int) -> PlanProposal:
    proposal = db.get(PlanProposal, proposal_id)
    if proposal is None or proposal.user_id != user.id:
        raise HTTPException(404, "Nincs ilyen javaslat")
    return proposal


@app.get("/api/plan/proposals")
def list_proposals(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(PlanProposal).where(PlanProposal.user_id == user.id)
                      .order_by(PlanProposal.id.desc()).limit(10))
    return [proposal_to_dict(p) for p in rows]


@app.post("/api/plan/proposals")
def create_proposal(today: Date | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Javaslat a jövő hétre a jelenlegi heti tervből és a naplóból. A korábbi függő javaslatot felváltja."""
    try:
        return proposal_to_dict(generate_proposal(db, db.merge(user), today))
    except PlanningError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/plan/proposals/{proposal_id}/accept", response_model=schemas.ProgramDoc)
def accept(proposal_id: int, body: AcceptBody, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user = db.merge(user)
    try:
        return program_to_doc(accept_proposal(db, user, _own_proposal(db, user, proposal_id), body.change_ids))
    except PlanningError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/plan/proposals/{proposal_id}/reject")
def reject(proposal_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    proposal = _own_proposal(db, db.merge(user), proposal_id)
    if proposal.status == "pending":
        proposal.status = "rejected"
        proposal.decided_at = now_iso()
        db.commit()
    return proposal_to_dict(proposal)


# --- LLM-edző (Gemini) --------------------------------------------------------

class CoachImportBody(BaseModel):
    response: str | dict


@app.get("/api/coach/status")
def coach_status(user: User = Depends(current_user)):
    return {"configured": gemini.configured(), "model": gemini.model_name()}


@app.get("/api/coach/prompt")
def coach_prompt(today: Date | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Kézi mód: a Gemini chatbe másolható prompt (API-kulcs nélkül)."""
    try:
        return coach.manual_prompt(db, db.merge(user), today)
    except PlanningError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/coach/review")
def coach_review(today: Date | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Automatikus mód: értékelés és javaslat a Gemini API-val (GEMINI_API_KEY kell). 10-60 mp is lehet."""
    if not gemini.configured():
        raise HTTPException(503, "A szerveren nincs beállítva GEMINI_API_KEY – használd a kézi módot.")
    try:
        return proposal_to_dict(coach.run_review(db, db.merge(user), today))
    except PlanningError as exc:
        raise HTTPException(422, str(exc)) from exc
    except gemini.GeminiError as exc:
        raise HTTPException(502, f"Gemini hiba: {exc}") from exc


@app.post("/api/coach/import")
def coach_import(body: CoachImportBody, today: Date | None = None, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    """Kézi mód: a Gemini chat válaszának betöltése (validálás után jóváhagyható javaslat lesz)."""
    try:
        return proposal_to_dict(coach.import_response(db, db.merge(user), body.response, today))
    except PlanningError as exc:
        raise HTTPException(422, str(exc)) from exc
    except gemini.GeminiError as exc:
        raise HTTPException(422, str(exc)) from exc


# --- statisztika ------------------------------------------------------------

@app.get("/api/stats/muscle-volume")
def muscle_volume(weeks: int = Query(4, ge=1, le=52), today: Date | None = None,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    return weekly_muscle_sets(db, user, weeks, today)


# A buildelt PWA (ha van) a gyökérben; az /api útvonalak előbb illeszkednek.
if config.STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")
