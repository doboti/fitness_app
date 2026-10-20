# Workout Tracker – backend (technikai leírás)

FastAPI + SQLite szolgáltatás a fitness trackerhez. Ez tárolja a gyakorlat-katalógust, a naplókat
(súly, edzés, sorozatok, fájdalom) és a heti terveket, és ugyanez a konténer szolgálja ki a telefonra
telepíthető, offline is működő PWA-t (`../frontend`).

A telepítés, a telefonos beállítás és a mappaszerkezet a gyökér [README.md](../README.md)-ben van.

## API

Jelszó nincs: a belépéskor a profilt egy legördülő menüből lehet választani (`GET /api/profiles`), és az eszköz ekkor
kap egy hozzáférési kulcsot (`POST /api/profiles/{id}/session`). A szerver csak a gépen belül és a Tailscale-en érhető el,
ezért ez elég védelem. A többi végpont ezt a kulcsot várja `Authorization: Bearer <token>` fejlécben (a CLI
`create-user` által kiírt token szkriptekhez is használható).

| Végpont | Leírás |
|---|---|
| `GET /api/health` | állapot + aktuális szinkron-kurzor |
| `GET /api/exercises`, `GET /api/muscles` | katalógus: izomszorzók, progressziós láncok, aliasok |
| `GET /api/profiles` | a választható profilok (név, nem) – kulcs nélkül |
| `POST /api/profiles/{id}/session` | profil kiválasztása → `{"token", "user"}` az adott eszköznek |
| `POST /api/logout` | az eszköz kulcsának érvénytelenítése |
| `GET/PUT /api/me` | profil (magasság, kor, célsúly) |
| `POST /api/sync` | push + pull egy hívásban (lásd lent) |
| `POST /api/programs` | heti terv feltöltése a régi `YYYY-WXX.json` formátumban |
| `POST /api/import/legacy` | a régi app exportjának (`*_results_*.json`) betöltése a saját fiókba |
| `GET /api/stats/muscle-volume?weeks=4` | heti súlyozott sorozatszám izomcsoportonként |
| `GET /api/plan/proposals` | a legutóbbi 10 tervjavaslat |
| `POST /api/plan/proposals` | új javaslat a jövő hétre (a függő javaslatot felváltja) |
| `POST /api/plan/proposals/{id}/accept` | `{"change_ids": [...]}` – a kiválasztott változásokkal elkészül a jövő heti terv |
| `POST /api/plan/proposals/{id}/reject` | javaslat elvetése |

Interaktív dokumentáció: `/docs`.

### Szinkron

```jsonc
// kérés
{ "cursor": 1234,                       // az utolsó válaszban kapott cursor (első alkalommal 0)
  "daily_logs":   [ { "date": "2026-10-15", "weight_kg": 75.2, "updated_at": "2026-10-15T07:12:00.000Z" } ],
  "sessions":     [ { "id": "<uuid>", "date": "2026-10-15", "updated_at": "…", "entries": [ … ] } ],
  "pain_reports": [ { "id": "<uuid>", "date": "2026-10-15", "muscle_code": "glute_med", "intensity": 4,
                      "kind": "dull", "side": "right", "updated_at": "…" } ] }
// válasz
{ "cursor": 1240, "applied": 3, "stale": [], "rejected": {},
  "changes": { "daily_logs": [], "sessions": [], "pain_reports": [], "programs": [], "user": null } }
```

- **Last-write-wins** dokumentumonként az `updated_at` alapján. A régebbi dokumentum a `stale` listába kerül, és a nyertes szerverváltozat mindig visszajön a `changes`-ben (akkor is, ha a kliens kurzora már túl van rajta).
- Egy **edzés egy dokumentum** a gyakorlataival (`entries`) és sorozataival (`sets`) együtt.
- **Törlés:** `deleted: true` (soft delete), így a többi eszközre is eljut.
- A kliens generálja az azonosítót (UUID) az edzéshez és a fájdalom-bejegyzéshez; a napi napló kulcsa a dátum.

## Szabálymotor (tervjavaslat)

A [app/engine.py](app/engine.py) a jelenlegi heti tervből, az elmúlt 4 hét naplójából és az aktív fájdalmakból javasol
változásokat a jövő hétre. Minden változásnak van indoklása, és **egyenként** hagyható jóvá (PWA → Haladás → Jövő heti terv).

| Helyzet | Javaslat |
|---|---|
| Minden sorozat megvolt, nem volt nehéz | +10% ismétlés (min. +1), időnél +5 mp; kétszer egymás után „könnyű” → dupla lépés |
| 20 ismétlés / 90 mp fölött | erősebb szalag (ha már használtál ilyet) 12 ismétléssel, különben a lánc következő variánsa ~60%-kal |
| „Nehéz”, vagy egyszer nem sikerült | marad |
| Kétszer egymás után nem sikerült | −15% ismétlés / −10 mp; nagyon alacsony ismétlésnél könnyebb variáns 10-zel |
| Rehab gyakorlat | soha nem nehezedik; ismételt „nehéz” → könnyítés |
| Aktív, enyhe fájdalom (<4, nem éles) a terhelt izmon | könnyebb variáns vagy egy sorozattal kevesebb |
| Aktív, erősebb vagy éles fájdalom | csere ugyanazon testtáj rehab gyakorlatára, ha nincs ilyen, kihagyás |
| Izomcsoport átlagosan <5 súlyozott sorozat/hét | legfeljebb 2 új gyakorlat (3×12 / 3×30 mp) a legkevésbé terhelt napra |
| Bukásig végzett („Maximum”) gyakorlat | marad (a cél maga a maximum) |

„Aktív” fájdalom: az „Elmúlt” jelölés nélküli bejelentés az elmúlt 14 napból. A küszöbök az `engine.py` elején állíthatók.
A régi (sorozat nélküli) naplóknál a „teljesítve” pipa számít a cél elérésének, a régi RPE 1–2 „könnyű”, 4–5 „nehéz”.

## Havi edzői kör (Gemini)

A backend tömör összefoglalót készít az elmúlt 4 hétről: profil, heti súlyátlag, izomterhelés, gyakorlatonkénti napló
a kommentekkel, fájdalmak, aktuális terv, és a használható gyakorlatok katalógusa. Erre a Gemini szigorú JSON-sémában
válaszol: szöveges értékelés, fókuszpontok és változások. A választ a backend teljes körűen ellenőrzi:

- csak létező gyakorlat lehet benne;
- csak érvényes nap és pozíció;
- csak ésszerű sorozatszám, ismétlés, idő és szalag;
- rehab gyakorlatot nem nehezíthet;
- kímélt izmot nem terhelhet.

Ami nem felel meg, kimarad (ezt a javaslat jelzi). A többi ugyanúgy változásonként hagyható jóvá, mint a szabálymotor javaslata.

**Automatikus mód** (API-kulccsal, https://aistudio.google.com → *Get API key*):
1. A compose-ban: `GEMINI_API_KEY=...`, opcionálisan `GEMINI_MODEL` (alapértelmezett: `gemini-3.8-flash`; olcsóbb a `gemini-3.5-flash-lite`).
2. Az appban: Haladás → *Értékelés kérése*. Havonta automatikusan, crontabból (minden hónap 1-jén 7:00-kor):
   ```
   0 7 1 * *  docker exec workout-api python -m app.cli coach-review --name Boti >> /var/log/workout-coach.log 2>&1
   5 7 1 * *  docker exec workout-api python -m app.cli coach-review --name Johi  >> /var/log/workout-coach.log 2>&1
   ```
   A javaslat jóváhagyásra vár az appban, semmi nem élesedik magától.

**Kézi mód** (kulcs nélkül, a Gemini chattel): Haladás → *Kézi mód* → prompt másolása → beillesztés a gemini.google.com-ra
→ a válasz visszamásolása. A ```json blokkba csomagolt választ is elfogadja.

**Adatvédelem:** mindkét módban az összefoglaló (kommentekkel és fájdalomadatokkal) a Google-hoz kerül. A tokenek és a
nyers napló nem, a profilból csak a nem, a kor, a magasság és a célsúly.

| Végpont | Leírás |
|---|---|
| `GET /api/coach/status` | be van-e állítva API-kulcs, melyik modell |
| `GET /api/coach/prompt` | a kézi módhoz bemásolható teljes prompt |
| `POST /api/coach/review` | automatikus értékelés a Gemini API-val (10–60 mp) |
| `POST /api/coach/import` | `{"response": "<a Gemini válasza>"}` – kézi mód |

## Adatmodell

```
users ─┬─ daily_logs (user, date)
       ├─ workout_sessions ── exercise_entries ── set_entries
       │                        │  presc_* (értelmezett előírás), difficulty (easy/ok/hard/failed),
       │                        │  is_rehab, archived, rpe_legacy, comment
       ├─ pain_reports (izom vagy testtérkép-terület, oldal, 0–10, sharp/dull/discomfort)
       └─ weekly_programs (week_id, payload JSON, source: legacy/manual/engine/llm)

exercises ─┬─ exercise_muscles (izomszorzó 0–1)    muscle_groups (19 izomcsoport)
           ├─ exercise_aliases (tervekben használt nevek)
           └─ chain + level (progressziós lánc)
```

A katalógus egyetlen forrása az [app/seed/exercises.json](app/seed/exercises.json): induláskor szinkronizálódik.
A seedből kivett gyakorlat nem törlődik, csak inaktív lesz, mert a régi naplók hivatkozhatnak rá.

## Fejlesztés

```bash
# backend
cd backend
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest                                           # 111 teszt
WORKOUT_DB=./data/dev.db uvicorn app.main:app --reload --port 8420

# frontend (másik terminálban; a Vite az /api-t a 8420-as portra proxyzza)
cd frontend
npm install
npm test                                         # 13 unit teszt (domain + szinkron)
npm run dev                                      # http://localhost:5173
```

### Frontend felépítése

| Fájl | Szerep |
|---|---|
| `src/domain/*` | tiszta logika (DOM nélkül, tesztelt): dátumok, testösszetétel, terv → edzés, fájdalom és pihentetés, izomstatisztika |
| `src/db.js`, `src/sync.js` | Dexie (IndexedDB) fiókonként; `_dirty` jelzés, push/pull, last-write-wins |
| `src/store.js` | a nézetek közös adatelérése |
| `src/views/*` | nézetek: `render(ctx)` → HTML, `actions` → `data-action` / `data-change` / `data-input` kezelők |
| `src/ui.js` | `html` sablon automatikus escape-eléssel, toast, modal |
| `public/sw.js` | Service Worker: app shell precache (a build írja bele a hash-elt assetek listáját), az `/api` soha nincs cache-elve |

### Fájdalom és pihentetés (jelenlegi szabályok)

- Bejelentés után az érintett terület izmait kíméljük: kellemetlen érzésnél 2, tompa vagy ≥4-es fájdalomnál 3, éles vagy ≥7-es fájdalomnál 7 napig.
  „Elmúlt” jelöléssel azonnal feloldható.
- Az edzésnél figyelmeztetés jelenik meg minden gyakorlatnál, amely ≥0,5 szorzóval terheli a kímélt izmot. A **rehab** jelölésű gyakorlatok kivételek.
- A gyakorlat-kommentet egy ékezet-független magyar kulcsszavas elemző nézi, ami a tagadást is kezeli („nem fájt”). Fájdalomszónál
  felajánlja a rögzítést, „könnyű” / „nehéz” szónál kitölti a nehézség-chipet, ha még üres.
