import re
from datetime import date as Date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .models import SyncCounter


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_ts(value: str) -> datetime:
    """ISO időbélyeg → aware datetime (a 'Z' végződést és a naiv értéket UTC-nek vesszük)."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).casefold()


def next_seq(db: Session) -> int:
    """Növeli és visszaadja a globális szinkron-sorszámot (ugyanabban a tranzakcióban)."""
    counter = db.get(SyncCounter, 1)
    if counter is None:
        counter = SyncCounter(id=1, value=0)
        db.add(counter)
    counter.value += 1
    db.flush()
    return counter.value


def iso_week_id(value: Date | str) -> str:
    """Dátum (vagy 'YYYY-MM-DD') → ISO hét azonosító, pl. '2026-W42'."""
    d = Date.fromisoformat(value) if isinstance(value, str) else value
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def week_monday(d: Date) -> Date:
    return d - timedelta(days=d.weekday())
