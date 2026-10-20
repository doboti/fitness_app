"""Szabálymotor: a következő hét tervének javaslata a napló, a nehézség-visszajelzések és a fájdalmak alapján.

Elvek (ahogy egy edző is dolgozna, ML nélkül, minden döntés indoklással):
- Dupla progresszió: ha minden sorozat elérte a célt és nem volt nehéz → több ismétlés / hosszabb tartás.
  A felső határ fölött erősebb szalag (ha ismert), különben a progressziós lánc következő variánsa kisebb ismétléssel.
- Kudarc (nem sikerült / kevesebb sorozat / cél alatti ismétlés): egyszer → marad, kétszer egymás után → visszalépés.
- A rehab gyakorlatot sosem nehezítjük; ismételt nehézségnél könnyítünk.
- Aktív fájdalom: az érintett izmot erősen (≥0.5) terhelő gyakorlat enyhe panasznál könnyebb lesz,
  erősebbnél rehab gyakorlatra cseréljük (vagy kihagyjuk, ha nincs megfelelő).
- Izomegyensúly: a tartósan alulterhelt izomcsoportokra legfeljebb 2 új gyakorlatot javaslunk.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from datetime import date as Date, timedelta

from .prescription import Prescription, parse_target

REP_CAP = 20            # efölött inkább nehezebb szalag / variáns
REP_HARD_CAP = 30
TIME_CAP_S = 90
TIME_HARD_CAP_S = 120
HISTORY_DAYS = 28
UNDERTRAINED_SETS = 5   # heti súlyozott sorozat, ami alatt "alulterhelt"
MAX_ADDITIONS = 2

# Fájdalom-terület → kímélendő izmok (a frontend domain/pain.js PAIN_AREAS rest listájával azonos).
PAIN_AREA_REST = {
    "neck": ["upper_back"], "shoulder": ["front_delt", "side_delt", "rear_delt"], "chest": ["chest"],
    "upper_back": ["upper_back", "rear_delt"], "lats": ["lats"], "biceps": ["biceps"], "triceps": ["triceps"],
    "elbow": ["biceps", "triceps"], "wrist": ["forearms", "chest", "triceps"], "abs": ["abs"],
    "obliques": ["obliques"], "lower_back": ["lower_back"], "hip_front": ["hip_flexors"],
    "hip_lateral": ["glute_med"], "glutes": ["glutes"], "quads": ["quads"], "hamstrings": ["hamstrings"],
    "adductors": ["adductors"], "knee": ["quads"], "knee_lateral": ["quads"], "calves": ["calves"],
    "ankle": ["calves"], "foot": ["calves"],
}


# --- bemeneti adatok (ORM-független, hogy könnyen tesztelhető legyen) ---------------------------

@dataclass
class CatalogExercise:
    id: str
    name: str
    measure: str                      # reps | time
    muscles: dict[str, float]
    region: str                       # a fő izom régiója
    chain: str | None = None
    level: int | None = None
    rehab_suitable: bool = False
    equipment: str = "bodyweight"
    unilateral: bool = False


@dataclass
class Performance:
    """Egy gyakorlat egy edzésen: előírás + eredmény."""
    date: str
    presc: Prescription
    values: list[int]                 # sorozatonkénti ismétlés / mp
    completed: bool
    difficulty: str | None
    band_kg: float | None
    is_rehab: bool


@dataclass
class ActivePain:
    body_area: str | None
    muscle_code: str | None
    intensity: int
    kind: str

    @property
    def muscles(self) -> list[str]:
        if self.body_area in PAIN_AREA_REST:
            return PAIN_AREA_REST[self.body_area]
        return [self.muscle_code] if self.muscle_code else []

    @property
    def severe(self) -> bool:
        return self.kind == "sharp" or self.intensity >= 4


@dataclass
class Change:
    day: str
    position: int | None              # None = új gyakorlat
    kind: str                         # progress | band | variant | regress | replace | remove | add
    reason: str
    before: dict | None
    after: dict | None
    id: str = ""


@dataclass
class ProposalResult:
    changes: list[Change] = field(default_factory=list)
    unchanged: int = 0
    insights: list[str] = field(default_factory=list)


# --- segédfüggvények -----------------------------------------------------------------------------

def format_seconds(seconds: int) -> str:
    minutes, sec = divmod(seconds, 60)
    if minutes and sec:
        return f"{minutes} perc {sec} másodperc"
    if minutes:
        return f"{minutes} perc"
    return f"{sec} másodperc"


def format_target(p: Prescription) -> str:
    """Előírás → a heti tervekben megszokott szöveg; a parse_target visszaolvassa."""
    prefix = f"{p.sets} kör x " if p.sets else ""
    if p.to_failure:
        body = "Maximum idő" if p.unit == "s" else "Maximum ismétlés"
    elif p.unit == "s":
        if p.per_side and p.min and p.min < 60:
            body = f"{p.min}-{p.min} másodperc"
        else:
            body = format_seconds(p.max or p.min or 0)
    else:
        lo, hi = p.min or 0, p.max or p.min or 0
        if p.per_side:
            body = f"{hi}-{hi} ismétlés"
        elif lo != hi:
            body = f"{lo}-{hi} ismétlés"
        else:
            body = f"{hi} ismétlés"
    band = f" ({p.band_kg:g}kg-os szalag)" if p.band_kg else ""
    return prefix + body + band


def _target(p: Prescription) -> int | None:
    return p.max if p.max is not None else p.min


def _with_target(p: Prescription, value: int, **overrides) -> Prescription:
    new = copy.copy(p)
    new.min = new.max = value
    for k, v in overrides.items():
        setattr(new, k, v)
    return new


def outcome(perf: Performance) -> str:
    """failed | hard | ok | easy | skipped"""
    if not perf.completed and not perf.values:
        return "skipped"
    if perf.difficulty == "failed":
        return "failed"
    if perf.presc.sets and len(perf.values) and len(perf.values) < perf.presc.sets:
        return "failed"
    if perf.values and perf.presc.min and not perf.presc.to_failure and min(perf.values) < perf.presc.min:
        return "failed"
    return perf.difficulty or "ok"


def target_reached(perf: Performance) -> bool:
    goal = _target(perf.presc)
    if perf.presc.to_failure or goal is None:
        return False
    if perf.values:
        return min(perf.values) >= goal and (not perf.presc.sets or len(perf.values) >= perf.presc.sets)
    return perf.completed   # régi napló: a "teljesítve" pipa = elérte a célt


def _starter(ex: CatalogExercise) -> Prescription:
    """Kezdő előírás egy újonnan bekerülő gyakorlathoz: 3 × 12 ismétlés vagy 3 × 30 mp."""
    value = 30 if ex.measure == "time" else 12
    return Prescription(sets=3, unit="s" if ex.measure == "time" else "reps", min=value, max=value, per_side=ex.unilateral)


def _rep_step(value: int) -> int:
    return max(1, math.ceil(value * 0.1))


class Engine:
    def __init__(self, catalog: dict[str, CatalogExercise], pains: list[ActivePain],
                 muscle_names: dict[str, str] | None = None):
        self.catalog = catalog
        self.pains = pains
        self.muscle_names = muscle_names or {}
        self.resting: dict[str, ActivePain] = {}
        for pain in pains:
            for muscle in pain.muscles:
                prev = self.resting.get(muscle)
                if prev is None or pain.intensity > prev.intensity:
                    self.resting[muscle] = pain

    # --- lánc navigáció ---
    def _chain_neighbour(self, ex: CatalogExercise, delta: int) -> CatalogExercise | None:
        if not ex.chain or ex.level is None:
            return None
        candidates = [c for c in self.catalog.values() if c.chain == ex.chain and c.level == ex.level + delta]
        return sorted(candidates, key=lambda c: c.id)[0] if candidates else None

    def conflicts(self, ex: CatalogExercise | None) -> list[str]:
        """A gyakorlat által erősen (≥0.5) terhelt, jelenleg kímélt izmok."""
        if ex is None:
            return []
        return [m for m, w in ex.muscles.items() if w >= 0.5 and m in self.resting]

    def _rehab_substitute(self, original: CatalogExercise) -> CatalogExercise | None:
        # Csak azonos testtájra cserélünk (fekvőtámasz helyett vádliemelés nem értelmes csere) – ha nincs ilyen, kihagyás.
        pool = [c for c in self.catalog.values()
                if c.rehab_suitable and not self.conflicts(c) and c.id != original.id and c.region == original.region]
        return sorted(pool, key=lambda c: (c.level or 0, c.id))[0] if pool else None

    # --- döntés egy tervezett gyakorlatról ---
    def decide(self, planned: dict, history: list[Performance], known_bands: list[float]) -> tuple[str, dict, str] | None:
        """(kind, after, reason) vagy None, ha marad. planned: a heti terv gyakorlata (name, target, exercise_id, prescription)."""
        ex = self.catalog.get(planned.get("exercise_id"))
        presc = Prescription(**planned["prescription"]) if planned.get("prescription") else parse_target(planned.get("target"))
        is_rehab = bool(planned.get("rehab")) or any(h.is_rehab for h in history[:1])
        name = ex.name if ex else planned["name"]

        # 1. fájdalom
        conflicts = self.conflicts(ex)
        if conflicts and not is_rehab:
            pain = max((self.resting[m] for m in conflicts), key=lambda p: p.intensity)
            muscles = ", ".join(self.muscle_names.get(m, m) for m in conflicts)
            if pain.severe:
                sub = self._rehab_substitute(ex)
                if sub is None:
                    return "remove", {}, f"Aktív fájdalom ({muscles}, {pain.intensity}/10) – kihagyjuk, amíg el nem múlik."
                return "replace", self.planned_item(sub.name, sub.id, _starter(sub), rehab=True), \
                    f"Aktív fájdalom ({muscles}, {pain.intensity}/10) – helyette kímélő rehab gyakorlat."
            easier = self._chain_neighbour(ex, -1)
            if easier:
                return "regress", self.planned_item(easier.name, easier.id, presc), \
                    f"Enyhe panasz ({muscles}) – könnyebb variáns, amíg el nem múlik."
            if presc.sets and presc.sets > 2:
                fewer = copy.copy(presc)
                fewer.sets -= 1
                return "regress", self.planned_item(name, planned.get("exercise_id"), fewer), \
                    f"Enyhe panasz ({muscles}) – egy sorozattal kevesebb."
            return None

        recent = [h for h in history if outcome(h) != "skipped"][:3]
        if not recent:
            return None
        last = recent[0]
        last_outcome = outcome(last)
        prev_outcome = outcome(recent[1]) if len(recent) > 1 else None
        goal = _target(presc)
        if goal is None or presc.to_failure:
            return None   # bukásig végzett / ismeretlen célú gyakorlat: a cél a "max", nincs mit léptetni
        unit_time = presc.unit == "s"

        # 2. kudarc → visszalépés kétszeri kudarcnál
        if last_outcome == "failed":
            if prev_outcome != "failed":
                return None
            easier = self._chain_neighbour(ex, -1) if ex else None
            if easier and not unit_time and goal <= 6:
                return "regress", self.planned_item(easier.name, easier.id, _with_target(presc, 10)), \
                    "Kétszer egymás után nem sikerült – könnyebb variáns több ismétléssel."
            new = max(10, goal - 10) if unit_time else max(3, round(goal * 0.85))
            if new >= goal:
                return None
            return "regress", self.planned_item(name, planned.get("exercise_id"), _with_target(presc, new)), \
                f"Kétszer egymás után nem sikerült – visszalépés {goal} → {new} {'mp' if unit_time else 'ismétlésre'}."

        # 3. rehab: sosem nehezítjük
        if is_rehab:
            if last_outcome == "hard" and prev_outcome in ("hard", "failed"):
                new = max(10, goal - 5) if unit_time else max(5, round(goal * 0.85))
                if new < goal:
                    return "regress", self.planned_item(name, planned.get("exercise_id"), _with_target(presc, new), rehab=True), \
                        "Rehab gyakorlat, ismételten nehéz volt – könnyítünk."
            return None

        # 4. progresszió
        if last_outcome == "hard" or not target_reached(last):
            return None
        double = last_outcome == "easy" and prev_outcome == "easy"
        best = min(last.values) if last.values else goal
        base = max(goal, best)
        why = "kétszer egymás után könnyű volt" if double else ("könnyű volt" if last_outcome == "easy" else "minden sorozat megvolt")

        if unit_time:
            new = base + (10 if double else 5)
            if new > TIME_CAP_S:
                harder = self._chain_neighbour(ex, 1) if ex else None
                if harder:
                    start = max(15, round(base * 0.5 / 5) * 5)
                    return "variant", self.planned_item(harder.name, harder.id, _with_target(presc, start)), \
                        f"{name}: {base} mp már stabil – jöhet a nehezebb variáns ({start} mp-től)."
                if new > TIME_HARD_CAP_S:
                    return None
            return "progress", self.planned_item(name, planned.get("exercise_id"), _with_target(presc, new)), \
                f"{why.capitalize()} – {base} → {new} mp."

        step = _rep_step(base) * (2 if double else 1)
        new = base + step
        if new > REP_CAP:
            band = presc.band_kg or last.band_kg
            heavier = sorted(b for b in known_bands if band and b > band)
            if ex and ex.equipment == "band" and heavier:
                return "band", self.planned_item(name, planned.get("exercise_id"), _with_target(presc, 12, band_kg=heavier[0])), \
                    f"{base} ismétlés {band:g} kg-mal már megy – erősebb szalag ({heavier[0]:g} kg) 12 ismétléssel."
            harder = self._chain_neighbour(ex, 1) if ex else None
            if harder:
                start = max(5, round(base * 0.6))
                return "variant", self.planned_item(harder.name, harder.id, _with_target(presc, start)), \
                    f"{base} ismétlés már megy – jöhet a nehezebb variáns ({start} ismétléssel)."
            if new > REP_HARD_CAP:
                return None
        return "progress", self.planned_item(name, planned.get("exercise_id"), _with_target(presc, new)), \
            f"{why.capitalize()} – {base} → {new} ismétlés{' / oldal' if presc.per_side else ''}."

    @staticmethod
    def planned_item(name: str, exercise_id: str | None, presc: Prescription, rehab: bool = False) -> dict:
        """Heti terv-elem (a feltöltött tervekkel azonos formában)."""
        after = {"name": name, "exercise_id": exercise_id, "target": format_target(presc), "prescription": presc.to_dict()}
        if rehab:
            after["rehab"] = True
        return after

    # --- izomegyensúly ---
    def additions(self, weekly_avg: dict[str, float], base_days: dict) -> list[Change]:
        trained_days = [k for k, d in base_days.items() if d.get("exercises")]
        if not trained_days or not weekly_avg:
            return []
        changes = []
        for muscle, avg in sorted(weekly_avg.items(), key=lambda kv: kv[1]):
            if len(changes) >= MAX_ADDITIONS or avg >= UNDERTRAINED_SETS or muscle in self.resting:
                continue
            options = [c for c in self.catalog.values() if c.muscles.get(muscle, 0) >= 1.0 and not self.conflicts(c)]
            if not options:
                continue
            pick = sorted(options, key=lambda c: (c.level or 1, not c.rehab_suitable, c.id))[0]
            # a legkevesebb gyakorlatot tartalmazó edzésnapra kerül
            day = min(trained_days, key=lambda k: (len(base_days[k]["exercises"]), k))
            changes.append(Change(
                day=day, position=None, kind="add", before=None,
                after=self.planned_item(pick.name, pick.id, _starter(pick), rehab=pick.rehab_suitable),
                reason=f"{self.muscle_names.get(muscle, muscle)}: átlagosan csak {avg:g} súlyozott sorozat/hét (ajánlott 10–20). A futás nem számít bele.",
            ))
            base_days[day]["exercises"] = [*base_days[day]["exercises"], {"_placeholder": True}]
        return changes

    def propose(self, base_days: dict, histories: dict[str, list[Performance]], known_bands: list[float],
                weekly_avg: dict[str, float]) -> ProposalResult:
        result = ProposalResult()
        for day_key in sorted(base_days, key=lambda k: int(k)):
            for position, planned in enumerate(base_days[day_key].get("exercises", [])):
                key = planned.get("exercise_id") or f"name:{planned['name']}"
                decision = self.decide(planned, histories.get(key, []), known_bands)
                if decision is None:
                    result.unchanged += 1
                    continue
                kind, after, reason = decision
                before = {k: planned.get(k) for k in ("name", "exercise_id", "target", "prescription")}
                result.changes.append(Change(day=day_key, position=position, kind=kind, reason=reason,
                                             before=before, after=after or None))
        result.changes.extend(self.additions(weekly_avg, copy.deepcopy(base_days)))
        for i, change in enumerate(result.changes):
            change.id = f"c{i + 1}"
        if self.resting:
            names = sorted(self.muscle_names.get(m, m) for m in self.resting)
            result.insights.append("Kímélt izmok aktív fájdalom miatt: " + ", ".join(names) + ".")
        return result


def apply_changes(base_days: dict, changes: list[dict], accepted_ids: set[str]) -> dict:
    """A jóváhagyott változások alkalmazása a kiinduló hét tervére → a következő hét terve."""
    days = copy.deepcopy(base_days)
    accepted = [c for c in changes if c["id"] in accepted_ids]
    removals: dict[str, list[int]] = {}
    for c in accepted:
        exercises = days[c["day"]]["exercises"]
        if c["kind"] == "add":
            exercises.append(c["after"])
        elif c["kind"] == "remove":
            removals.setdefault(c["day"], []).append(c["position"])
        else:
            exercises[c["position"]] = {**c["after"]}
    for day, positions in removals.items():
        for pos in sorted(positions, reverse=True):
            del days[day]["exercises"][pos]
    return days


def next_week_id(week_id: str) -> str:
    year, week = week_id.split("-W")
    monday = Date.fromisocalendar(int(year), int(week), 1) + timedelta(weeks=1)
    y, w, _ = monday.isocalendar()
    return f"{y}-W{w:02d}"
