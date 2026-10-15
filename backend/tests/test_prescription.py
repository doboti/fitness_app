import pytest

from app.prescription import parse_target


@pytest.mark.parametrize("target, default_sets, expected", [
    ("4 kör x 10 ismétlés (Vállra figyelni, kontrolláltan!)", None,
     dict(sets=4, unit="reps", min=10, max=10, per_side=False, to_failure=False)),
    ("4 kör x 8-10 ismétlés (Extrém lassan engedd le magad)", None,
     dict(sets=4, unit="reps", min=8, max=10, per_side=False)),
    ("4 kör x 12-12 lépés", None, dict(sets=4, unit="reps", min=12, max=12, per_side=True)),
    ("12-12 ismétlés lábanként", 4, dict(sets=4, unit="reps", min=12, max=12, per_side=True)),
    ("20 ismétlés (10-10 oldalra)", 3, dict(sets=3, unit="reps", min=20, max=20, per_side=False)),
    ("4 kör x 1 perc 15 másodperc (Tudom, hogy utálod)", None, dict(sets=4, unit="s", min=75, max=75)),
    ("4 kör x 45 másodperc", None, dict(sets=4, unit="s", min=45, max=45)),
    ("30 másodperc megtartás", 4, dict(sets=4, unit="s", min=30, max=30)),
    ("4 kör x 10-15 másodperc megtartás (Könyveken)", None, dict(sets=4, unit="s", min=10, max=15, per_side=False)),
    ("3 kör x Max idő (Cél: 1 perc 15 másodperc)", None, dict(sets=3, unit="s", to_failure=True, min=None)),
    ("3 kör x Maximum szabályos ismétlés", None, dict(sets=3, unit="reps", to_failure=True)),
    ("3 kör x Maximum (Cél: 15+ szabályos ismétlés)", None, dict(sets=3, to_failure=True)),
    ("3 sets x 25 reps", None, dict(sets=3, unit="reps", min=25, max=25)),
    ("4 kör x 15-15 ismétlés (9kg-os szalag, lassú kivitelezés)", None,
     dict(sets=4, min=15, max=15, per_side=True, band_kg=9.0)),
    ("4 kör x 15 ismétlés (6.75kg-os szalag a talpba akasztva)", None, dict(band_kg=6.75, min=15)),
    ("4 kör x 10 fekvő vagy 12 dolphin", None, dict(sets=4, min=10, max=10)),
    ("", 4, dict(sets=4, unit=None, min=None)),
    (None, None, dict(sets=None, unit=None)),
])
def test_parse_target(target, default_sets, expected):
    result = parse_target(target, default_sets).to_dict()
    for key, value in expected.items():
        assert result[key] == value, f"{key}: {result}"
