import os
from pathlib import Path

DB_PATH = Path(os.environ.get("WORKOUT_DB", Path(__file__).resolve().parent.parent / "data" / "workout.db"))
# Vesszővel elválasztott lista, pl. a Vite fejlesztői szerverhez: http://localhost:5173
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
# A buildelt PWA frontend helye (ha létezik, a backend szolgálja ki)
STATIC_DIR = Path(os.environ.get("STATIC_DIR", Path(__file__).resolve().parent.parent / "static"))
SEED_FILE = Path(__file__).resolve().parent / "seed" / "exercises.json"
