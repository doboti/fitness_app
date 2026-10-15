"""A heti tervek szabad szöveges céljainak ("4 kör x 12-12 ismétlés (9kg-os szalag)") strukturált értelmezése."""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict


@dataclass
class Prescription:
    sets: int | None = None
    unit: str | None = None          # 'reps' | 's'
    min: int | None = None           # ismétlés vagy másodperc
    max: int | None = None
    per_side: bool = False
    to_failure: bool = False
    band_kg: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


_SETS = re.compile(r"(\d+)\s*(?:kör|sets?|sorozat)\s*[x×]", re.I)
_BAND = re.compile(r"(\d+(?:[.,]\d+)?)\s*kg", re.I)
_MAX = re.compile(r"\bmax(?:imum|imális)?\b", re.I)
_TIME_WORDS = re.compile(r"\bidő|másodperc|\bmp\b|\bperc\b|\bsec\b", re.I)
_REP_WORDS = re.compile(r"ismétlés|\breps?\b", re.I)
_PER_SIDE_WORDS = re.compile(r"lábanként|oldalanként|karonként", re.I)
_MINUTES_ONLY = re.compile(r"(\d+)\s*perc", re.I)
_SECONDS = re.compile(r"(\d+)(?:\s*-\s*(\d+))?\s*(?:másodperc|mp\b|sec\b)", re.I)
_COUNT = re.compile(r"(\d+)(?:\s*-\s*(\d+))?")


def _strip_notes(text: str) -> str:
    """A zárójeles megjegyzéseket ("(Cél: 1 perc 15 másodperc)") nem tekintjük az előírás részének."""
    return re.sub(r"\([^)]*\)", " ", text)


def parse_target(target: str | None, default_sets: int | None = None) -> Prescription:
    p = Prescription(sets=default_sets)
    if not target:
        return p

    band = _BAND.search(target)
    if band:
        p.band_kg = float(band.group(1).replace(",", "."))

    core = _strip_notes(target)
    sets = _SETS.search(core)
    if sets:
        p.sets = int(sets.group(1))
        core = core[sets.end():]

    if _MAX.search(core):
        p.to_failure = True
        p.unit = "s" if _TIME_WORDS.search(core) else ("reps" if _REP_WORDS.search(core) else None)
        return p

    minutes = _MINUTES_ONLY.search(core)
    seconds = _SECONDS.search(core)
    if minutes or seconds:
        base = int(minutes.group(1)) * 60 if minutes else 0
        lo = int(seconds.group(1)) if seconds else 0
        hi = int(seconds.group(2)) if seconds and seconds.group(2) else lo
        p.unit = "s"
        if seconds and seconds.group(2) and lo == hi:
            p.per_side = True
        p.min, p.max = base + lo, base + hi
        return p

    count = _COUNT.search(core)
    if count:
        lo = int(count.group(1))
        hi = int(count.group(2)) if count.group(2) else lo
        p.unit = "reps"
        if count.group(2) and lo == hi:
            p.per_side = True             # "12-12" = oldalanként 12
        p.min, p.max = (lo, hi) if lo <= hi else (hi, lo)
        if _PER_SIDE_WORDS.search(core):
            p.per_side = True
    return p
