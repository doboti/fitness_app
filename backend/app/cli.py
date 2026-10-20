"""Parancssori karbantartás.

    python -m app.cli create-user --name Boti --gender male
    python -m app.cli rename-user --name ferfi --new-name Boti
    python -m app.cli list-users
    python -m app.cli rotate-token --name ferfi
    python -m app.cli import-legacy --name ferfi ../results/male_results_2026_w31.json ../edzestervek_backup/*.json
    python -m app.cli backup /data/backups --keep 14
    python -m app.cli coach-review --name ferfi          # havi Gemini edzői kör (GEMINI_API_KEY kell)
"""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from . import config
from .auth import hash_token, new_token
from .db import new_session
from .legacy import import_legacy
from .main import init_database
from .models import User
from .util import next_seq, now_iso


def _get_user(db, name: str) -> User:
    user = db.scalar(select(User).where(User.name == name))
    if user is None:
        sys.exit(f"Nincs ilyen felhasználó: {name}")
    return user


def cmd_create_user(args) -> None:
    with new_session() as db:
        if db.scalar(select(User).where(User.name == args.name)):
            sys.exit(f"Már létezik: {args.name}")
        token = new_token()
        db.add(User(name=args.name, gender=args.gender, height_cm=args.height, age=args.age,
                    target_weight_kg=args.target_weight, token_hash=hash_token(token),
                    updated_at=now_iso(), server_seq=next_seq(db)))
        db.commit()
    print(f"Profil létrehozva: {args.name} – az appban a profilválasztóban jelenik meg.")
    print(f"API-token szkriptekhez (az apphoz nem kell): {token}")


def cmd_rename_user(args) -> None:
    with new_session() as db:
        user = _get_user(db, args.name)
        if db.scalar(select(User).where(User.name == args.new_name)):
            sys.exit(f"Már létezik: {args.new_name}")
        user.name = args.new_name
        user.updated_at = now_iso()
        user.server_seq = next_seq(db)
        db.commit()
    print(f"Átnevezve: {args.name} → {args.new_name}")


def cmd_list_users(_args) -> None:
    with new_session() as db:
        for u in db.scalars(select(User).order_by(User.id)):
            print(f"{u.id}\t{u.name}\t{u.gender}\tmagasság={u.height_cm}\tkor={u.age}\tcél={u.target_weight_kg}")


def cmd_rotate_token(args) -> None:
    with new_session() as db:
        user = _get_user(db, args.name)
        token = new_token()
        user.token_hash = hash_token(token)
        db.commit()
    print(f"Új token ({args.name}):\n{token}")


def cmd_import_legacy(args) -> None:
    # Fájlnév szerinti sorrend: a későbbi heti export felülírja a korábbit (mint a régi app importja).
    files = sorted({Path(f) for f in args.files}, key=lambda p: p.name)
    totals: dict = {}
    unmatched: dict[str, int] = {}
    with new_session() as db:
        user = _get_user(db, args.name)
        for path in files:
            report = import_legacy(db, user, json.loads(path.read_text(encoding="utf-8")))
            for name, count in report.pop("unmatched_exercises").items():
                unmatched[name] = unmatched.get(name, 0) + count
            print(f"{path.name}: " + ", ".join(f"{k}={v}" for k, v in report.items()))
            for k, v in report.items():
                totals[k] = totals.get(k, 0) + v
    print("Összesen: " + ", ".join(f"{k}={v}" for k, v in totals.items()))
    if unmatched:
        print("\nFelismeretlen gyakorlatnevek (vedd fel aliasként a seed/exercises.json-ba):")
        for name, count in sorted(unmatched.items(), key=lambda kv: -kv[1]):
            print(f"  {count:4d}×  {name}")
    else:
        print("Minden gyakorlatnév felismerve.")


def cmd_coach_review(args) -> None:
    """Havi edzői kör (cronból): Gemini értékelés → jóváhagyásra váró javaslat az appban."""
    from .coach import run_review
    from .planning import proposal_to_dict
    with new_session() as db:
        user = _get_user(db, args.name)
        proposal = proposal_to_dict(run_review(db, user))
    print(f"{args.name}: {proposal['base_week_id']} → {proposal['target_week_id']}, "
          f"{len(proposal['changes'])} változás ({proposal['model']}). Jóváhagyás az appban: Haladás → Jövő heti terv.")
    for line in proposal["insights"]:
        print(f"  ! {line}")


def cmd_backup(args) -> None:
    """Konzisztens online mentés (sqlite3 backup API) + gzip + régi mentések törlése."""
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    raw = out_dir / f"workout-{stamp}.db"
    src = sqlite3.connect(config.DB_PATH)
    dst = sqlite3.connect(raw)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    with raw.open("rb") as f_in, gzip.open(f"{raw}.gz", "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    raw.unlink()
    backups = sorted(out_dir.glob("workout-*.db.gz"))
    for old in backups[:-args.keep]:
        old.unlink()
    print(f"{raw}.gz")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("create-user")
    p.add_argument("--name", required=True)
    p.add_argument("--gender", choices=["male", "female"], required=True)
    p.add_argument("--height", type=float)
    p.add_argument("--age", type=int)
    p.add_argument("--target-weight", type=float)
    p.set_defaults(func=cmd_create_user)

    sub.add_parser("list-users").set_defaults(func=cmd_list_users)

    p = sub.add_parser("rename-user")
    p.add_argument("--name", required=True)
    p.add_argument("--new-name", required=True)
    p.set_defaults(func=cmd_rename_user)

    p = sub.add_parser("rotate-token")
    p.add_argument("--name", required=True)
    p.set_defaults(func=cmd_rotate_token)

    p = sub.add_parser("import-legacy")
    p.add_argument("--name", required=True)
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_import_legacy)

    p = sub.add_parser("coach-review")
    p.add_argument("--name", required=True)
    p.set_defaults(func=cmd_coach_review)

    p = sub.add_parser("backup")
    p.add_argument("out_dir")
    p.add_argument("--keep", type=int, default=14)
    p.set_defaults(func=cmd_backup)

    args = parser.parse_args(argv)
    if args.cmd != "backup":
        init_database()
    args.func(args)


if __name__ == "__main__":
    main()
