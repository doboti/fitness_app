# A repó gyökeréből: docker compose up -d --build   (vagy: docker build -t workout-api .)

# --- 1. PWA frontend build ---------------------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Python backend -------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WORKOUT_DB=/data/workout.db \
    STATIC_DIR=/app/static

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 1000 --create-home workout \
    && mkdir -p /data && chown workout:workout /data

COPY backend/app ./app
COPY --from=frontend /frontend/dist ./static

USER workout
EXPOSE 8420
VOLUME ["/data"]

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8420/api/health', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8420", "--workers", "1", "--proxy-headers"]
