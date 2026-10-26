"""A szabálymotor bemeneteinek betöltése az adatbázisból, javaslatok mentése és jóváhagyása."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date as Date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalog import ExerciseMatcher
from .engine import ActivePain, CatalogExercise, Engine, HISTORY_DAYS, Performance, apply_changes, next_week_id
from .legacy import upsert_program
from .models import Exercise, MuscleGroup, PainReport, PlanProposal, User, WeeklyProgram, WorkoutSession
from .prescription import Prescription
from .stats import weekly_muscle_sets
from .util import iso_week_id, now_iso

PAIN_LOOKBACK_DAYS = 14   # a "nem múlt el" jelölésű panaszokat ennyi ideig vesszük figyelembe


class PlanningError(ValueError):
    pass


def load_catalog(db: Session) -> tuple[dict[str, CatalogExercise], dict[str, str]]:
    regions = dict(db.execute(select(MuscleGroup.code, MuscleGroup.region)).all())
    names = dict(db.execute(select(MuscleGroup.code, MuscleGroup.name_hu)).all())
    catalog = {}
    for ex in db.scalars(select(Exercise).where(Exercise.active.is_(True))):
        muscles = {m.muscle_code: m.weight for m in ex.muscles}
        primary = max(muscles, key=muscles.get) if muscles else None
        catalog[ex.id] = CatalogExercise(
            id=ex.id, name=ex.name_hu, measure=ex.measure, muscles=muscles, region=regions.get(primary, ""),
            chain=ex.chain, level=ex.level, rehab_suitable=ex.rehab_suitable, equipment=ex.equipment,
            unilateral=ex.unilateral)
    return catalog, names


def load_histories(db: Session, user: User, until: Date) -> tuple[dict[str, list[Performance]], list[float]]:
    """Gyakorlatonkénti teljesítmények (legújabb elöl) az utolsó HISTORY_DAYS napból + a használt szalagok."""
    since = until - timedelta(days=HISTORY_DAYS)
    sessions = db.scalars(select(WorkoutSession).where(
        WorkoutSession.user_id == user.id, WorkoutSession.deleted.is_(False),
        WorkoutSession.date >= since.isoformat(), WorkoutSession.date < until.isoformat(),
    ).order_by(WorkoutSession.date.desc()))
    histories: dict[str, list[Performance]] = {}
    bands: set[float] = set()
    for session in sessions:
        for e in session.entries:
            if e.archived:
                continue
            presc = Prescription(sets=e.presc_sets, unit=e.presc_unit, min=e.presc_min, max=e.presc_max,
                                 per_side=e.presc_per_side, to_failure=e.presc_to_failure, band_kg=e.band_kg)
            values = [v for v in ((s.reps if s.reps is not None else s.duration_s) for s in e.sets) if v is not None]
            key = e.exercise_id or f"name:{e.name_raw}"
            histories.setdefault(key, []).append(Performance(
                date=session.date, presc=presc, values=values, completed=e.completed,
                difficulty=e.difficulty, band_kg=e.band_kg, is_rehab=e.is_rehab))
            bands.update(b for b in [e.band_kg, *(s.band_kg for s in e.sets)] if b)
    return histories, sorted(bands)


def load_active_pains(db: Session, user: User, ref: Date) -> list[ActivePain]:
    since = (ref - timedelta(days=PAIN_LOOKBACK_DAYS)).isoformat()
    rows = db.scalars(select(PainReport).where(
        PainReport.user_id == user.id, PainReport.deleted.is_(False), PainReport.resolved_at.is_(None),
        PainReport.date >= since, PainReport.date <= ref.isoformat()))
    return [ActivePain(body_area=r.body_area, muscle_code=r.muscle_code, intensity=r.intensity, kind=r.kind) for r in rows]


def weekly_average(db: Session, user: User, today: Date, weeks: int = 3) -> dict[str, float]:
    """Izmonkénti átlagos heti terhelés azokra a hetekre, amikor volt edzés."""
    stats = weekly_muscle_sets(db, user, weeks, today)
    trained = [i for i in range(weeks) if any(values[i] for values in stats["muscles"].values())]
    if not trained:
        return {}
    catalog_muscles = set(db.scalars(select(MuscleGroup.code)))
    return {m: round(sum(stats["muscles"].get(m, [0] * weeks)[i] for i in trained) / len(trained), 1)
            for m in catalog_muscles}


def base_program(db: Session, user: User, before_week: str) -> WeeklyProgram | None:
    """A céllhét előtti legutóbbi heti terv (ebből indul a javaslat)."""
    return db.scalar(select(WeeklyProgram).where(WeeklyProgram.user_id == user.id, WeeklyProgram.week_id < before_week)
                     .order_by(WeeklyProgram.week_id.desc()).limit(1))


def target_week_for(db: Session, user: User, today: Date) -> str:
    """Az aktuális hét, ha arra még nincs terv (pl. hétfő reggel); különben a következő hét."""
    current = iso_week_id(today)
    has_current = db.scalar(select(WeeklyProgram.id).where(WeeklyProgram.user_id == user.id,
                                                          WeeklyProgram.week_id == current)) is not None
    return next_week_id(current) if has_current else current


@dataclass
class PlanningContext:
    """Minden, ami egy javaslathoz kell (a szabálymotor és az LLM-edző közösen használja)."""
    today: Date
    current_week: str
    target_week: str
    base: WeeklyProgram
    base_days: dict
    catalog: dict[str, CatalogExercise]
    muscle_names: dict[str, str]
    histories: dict[str, list[Performance]]
    bands: list[float]
    pains: list[ActivePain]
    weekly_avg: dict[str, float]

    def engine(self) -> Engine:
        return Engine(self.catalog, self.pains, self.muscle_names)


def build_context(db: Session, user: User, today: Date | None = None) -> PlanningContext:
    today = today or Date.today()
    current = iso_week_id(today.isoformat())
    target = target_week_for(db, user, today)
    base = base_program(db, user, target)
    if base is None:
        raise PlanningError("Nincs heti terv, amiből javaslatot lehetne készíteni. Tölts fel egy heti tervet.")
    target_monday = Date.fromisocalendar(*map(int, target.replace("-W", " ").split()), 1)
    catalog, muscle_names = load_catalog(db)
    histories, bands = load_histories(db, user, target_monday)
    return PlanningContext(
        today=today, current_week=current, target_week=target, base=base, base_days=json.loads(base.payload),
        catalog=catalog, muscle_names=muscle_names, histories=histories, bands=bands,
        pains=load_active_pains(db, user, today), weekly_avg=weekly_average(db, user, today))


def store_proposal(db: Session, user: User, ctx: PlanningContext, source: str, payload: dict) -> PlanProposal:
    """Új függő javaslat mentése; a korábbi függő javaslat érvényét veszti."""
    existing_target = db.scalar(select(WeeklyProgram).where(WeeklyProgram.user_id == user.id,
                                                            WeeklyProgram.week_id == ctx.target_week))
    for old in db.scalars(select(PlanProposal).where(PlanProposal.user_id == user.id, PlanProposal.status == "pending")):
        old.status = "superseded"
    proposal = PlanProposal(
        user_id=user.id, base_week_id=ctx.base.week_id, target_week_id=ctx.target_week, source=source,
        status="pending", created_at=now_iso(),
        payload=json.dumps({
            "base_label": ctx.base.label,
            "target_exists": existing_target is not None and existing_target.source not in ("engine", "llm"),
            **payload,
        }, ensure_ascii=False),
    )
    db.add(proposal)
    db.commit()
    return proposal


def generate_proposal(db: Session, user: User, today: Date | None = None) -> PlanProposal:
    ctx = build_context(db, user, today)
    result = ctx.engine().propose(ctx.base_days, ctx.histories, ctx.bands, ctx.weekly_avg)
    if next_week_id(ctx.base.week_id) != ctx.target_week:
        result.insights.insert(0, f"A legutóbbi heti terv a {ctx.base.week_id} hétre szól, ebből indul a javaslat.")
    if not ctx.histories:
        result.insights.append("Az elmúlt 4 hétben nincs naplózott edzés, ezért nincs mi alapján nehezíteni vagy könnyíteni.")
    return store_proposal(db, user, ctx, "engine", {
        "changes": [asdict(c) for c in result.changes],
        "unchanged": result.unchanged,
        "insights": result.insights,
    })


def accept_proposal(db: Session, user: User, proposal: PlanProposal, change_ids: list[str]) -> WeeklyProgram:
    if proposal.status != "pending":
        raise PlanningError("Ez a javaslat már nem aktív.")
    base = db.scalar(select(WeeklyProgram).where(WeeklyProgram.user_id == user.id,
                                                 WeeklyProgram.week_id == proposal.base_week_id))
    if base is None:
        raise PlanningError("A kiinduló heti terv már nem létezik.")
    payload = json.loads(proposal.payload)
    known = {c["id"] for c in payload["changes"]}
    unknown = set(change_ids) - known
    if unknown:
        raise PlanningError(f"Ismeretlen változás: {', '.join(sorted(unknown))}")

    days = apply_changes(json.loads(base.payload), payload["changes"], set(change_ids))
    who = "Gemini edzői" if proposal.source == "llm" else "Motor"
    label = f"{who} javaslat alapján ({len(change_ids)} változás, kiindulás: {proposal.base_week_id})"
    program = upsert_program(db, user, proposal.target_week_id, label, days, proposal.source, ExerciseMatcher(db))
    proposal.status = "accepted"
    proposal.decided_at = now_iso()
    db.commit()
    return program


def proposal_to_dict(p: PlanProposal) -> dict:
    return {"id": p.id, "base_week_id": p.base_week_id, "target_week_id": p.target_week_id, "source": p.source,
            "status": p.status, "created_at": p.created_at, "decided_at": p.decided_at, **json.loads(p.payload)}
