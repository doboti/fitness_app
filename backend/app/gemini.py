"""Minimális Gemini API kliens (generateContent, JSON kimenet) – csak standard könyvtár, nincs extra függőség."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-3.8-flash"


class GeminiError(RuntimeError):
    pass


@dataclass
class GeminiResult:
    data: dict
    model: str
    usage: dict


def configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def model_name() -> str:
    return os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def _post(url: str, body: dict, api_key: str, timeout: int) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise GeminiError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise GeminiError(f"A Gemini API nem érhető el: {exc}") from exc


def extract_json(text: str) -> dict:
    """A modell válaszából a JSON objektum (a kézzel bemásolt válasz ```json blokkban is lehet)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise GeminiError("A válaszban nincs JSON objektum.")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise GeminiError(f"A válasz nem érvényes JSON: {exc}") from exc


def generate_json(system: str, prompt: str, schema: dict, *, model: str | None = None,
                  api_key: str | None = None, timeout: int = 180, post=None) -> GeminiResult:
    """Strukturált (JSON) válasz kérése.

    A séma-mező neve API-verziónként eltért (responseJsonSchema / responseSchema), ezért 400-as hibánál
    egyszerűbb formára lépünk vissza; a választ a hívó amúgy is teljes körűen validálja.
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    post = post or _post
    if not api_key:
        raise GeminiError("Nincs beállítva GEMINI_API_KEY.")
    model = model or model_name()
    base = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
    }
    attempts = [
        {"responseMimeType": "application/json", "responseJsonSchema": schema, "temperature": 0.4},
        {"responseMimeType": "application/json", "temperature": 0.4},
    ]
    last_error = None
    for config in attempts:
        try:
            response = post(API_URL.format(model=model), {**base, "generationConfig": config}, api_key, timeout)
            break
        except GeminiError as exc:
            last_error = exc
            if not str(exc).startswith("HTTP 400"):
                raise
    else:
        raise last_error

    candidates = response.get("candidates") or []
    if not candidates:
        reason = (response.get("promptFeedback") or {}).get("blockReason", "ismeretlen")
        raise GeminiError(f"A modell nem adott választ (ok: {reason}).")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return GeminiResult(data=extract_json(text), model=model, usage=response.get("usageMetadata") or {})
