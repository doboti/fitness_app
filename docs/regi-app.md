# Fitness & Workout Tracker – Dokumentáció

> A régi, egyfájlos app leírása: [legacy/fitness_tracker.html](../legacy/fitness_tracker.html). Az új rendszer
> (backend + PWA) a gyökér [README.md](../README.md)-ben van leírva; a lent található változásnapló a teljes projektre vonatkozik.

## 1. Áttekintés

Egyetlen HTML fájlból álló, szerver nélküli webalkalmazás napi testsúly-, testösszetétel-, vízfogyasztás- és edzésnaplózásra. A heti edzésterveket külső JSON fájlokból lehet betölteni (`YYYY-WXX.json`). Minden adat a böngésző `localStorage`-ában tárolódik, a mentés/szinkronizáció kézi JSON exporttal/importtal történik.

**Technológia**

| Elem | Megoldás |
|---|---|
| UI | HTML + előre generált, beágyazott Tailwind CSS (v3.4.17) + saját CSS |
| Logika | Vanilla JavaScript, egy `<script>` blokk |
| Betűtípus | Google Fonts – Inter (offline a rendszer betűtípusa lép be) |
| Tárolás | `localStorage` (profilonként külön kulcs) |
| Képek | `assets/img/*.png` |

**Indítás:** a `fitness_tracker.html` megnyitása böngészőben (dupla kattintás). Internet nélkül is működik.

**Tailwind CSS újragenerálása:** ha a HTML-ben vagy a JS sablonokban **új** Tailwind osztályt használsz (pl. `bg-purple-600`), futtasd a projekt mappájából (Node.js szükséges):

```
node legacy/tools/build-tailwind.mjs
```

A script a `/* tailwind:start */` és `/* tailwind:end */` jelölők közötti CSS-t cseréli le. Ha kihagyod, az új osztálynak nem lesz hatása.

## 2. Fájlok

A régi app a `legacy/` mappában van: `fitness_tracker.html`, a gyakorlatképek (`assets/img/`) és a Tailwind CSS
újragenerálója (`tools/build-tailwind.mjs`, futtatás: `node legacy/tools/build-tailwind.mjs`). A régi exportok és
heti tervek a gitignore-olt `data/` mappában vannak, és a telefonos app Beállításaiból tölthetők át az új rendszerbe.

## 3. Funkciók (nézetek)

| Nézet | Tartalom |
|---|---|
| **📊 Dashboard** | Mentés-emlékeztető sáv (ha 7+ napja nem volt export, vagy még soha); heti átlagsúly KPI + előző héthez viszonyított trend + heti SVG grafikon; súly / nyak / derék (/ csípő női profilnál) rögzítése; vízfogyasztás (+250/+500 ml, cél 2500 ml); mai edzés állapota; BMI és testzsír%; kezdősúly / célsúly / leadott kg |
| **🏋️ Edzés** | A kiválasztott nap gyakorlatai az aktuális heti tervből: kép, cél, „Teljesítve” kapcsoló, RPE (1–5), komment; extra kardió (táv, idő, automatikus tempó, megjegyzés). **Minden mező azonnal mentődik**; az „Edzés Mentése” gomb csak összesítőt mutat. |
| **📅 Naptár** | Havi nézet, pötty jelzi az adatot tartalmazó napokat, napra kattintva az a nap lesz aktív |
| **⚙️ Beállítások** | Magasság, célsúly, életkor; adatbázis export/import; heti edzésterv import; profil adatainak törlése |
| **💪 Gyakorlatok** | Dinamikus könyvtár: a 21 beépített leírásos gyakorlat + a betöltött heti tervek összes gyakorlata, a legutóbb használtak elöl, hetek jelölésével. Leírás a heti JSON `description` mezőjéből is jöhet. |
| **Heti gyorsváltó** | Oldalsávban (csak asztali nézetben) a hét 7 napja, gyors dátumváltás |
| **Profilváltó** | Jobb felső gomb: Férfi (zöld téma) ↔ Női (rózsaszín téma), külön adatbázissal |

### Számítások
- **BMI** = súly / (magasság m)²
- **Testzsír – U.S. Navy módszer** (ha megvannak a méretek):
  - Férfi: `495 / (1.0324 − 0.19077·log10(derék−nyak) + 0.15456·log10(magasság)) − 450`
  - Nő: `495 / (1.29579 − 0.35004·log10(derék+csípő−nyak) + 0.22100·log10(magasság)) − 450`
- **Testzsír – BMI alapú becslés** (tartalék): `1.20·BMI + 0.23·kor − 16.2` (férfi) / `− 5.4` (nő)
- **Heti átlag**: az adott ISO hét összes rögzített súlyának átlaga; trend = eltérés az előző hét átlagától.
- **Tempó**: perc / km → `p:mm min/km`.

### Szabályok
- A heti tervet a dátum ISO hetéhez (`getISOWeekString`) rendelt `weekly_programs[weekId]` alapján választja (`getProgramForDate`); a nap kulcsa `1`=hétfő … `5`=péntek, `6`=szombat, `7` (vagy `0`)=vasárnap.
- Szombat/vasárnap akkor **pihenőnap**, ha a terv nem ad meg rá edzést.
- Napló csak akkor jön létre, ha ténylegesen beírsz valamit (súly, víz, pipa, RPE, komment, kardió) – a puszta megtekintés nem hoz létre bejegyzést. Betöltéskor és importáláskor az üres naplók automatikusan törlődnek.
- Ha egy hét tervét újraimportálod, a meglévő napló **név szerint** fésülődik össze az új tervvel: az azonos nevű gyakorlatok pipája/RPE-je/kommentje megmarad, a cél szövege frissül, a tervből kikerült, de kitöltött gyakorlatok a napló `archived_exercises` listájába kerülnek.
- Az export időpontja profilonként a `localStorage`-ban (`<adatbázis-kulcs>_last_export`) tárolódik; ebből számol a mentés-emlékeztető.

## 4. Adatmodell (localStorage)

Kulcsok: `fitness_tracker_db` (férfi), `fitness_tracker_db_female` (női).

```jsonc
{
  "user_info": { "gender": "male", "height_cm": 175, "target_weight_kg": 70, "age": 30 },
  "weekly_programs": {
    "2026-W32": {
      "week_id": "2026-W32",
      "imported_at": "2026-07-31T13:41:03.000Z",
      "program": {
        "1": { "name": "…", "circuits": 4,
               "exercises": [ { "name": "Hand-Release Push-up", "target": "4 kör x 10" } ] }
      }
    }
  },
  "daily_logs": {
    "2026-07-31": { "weight_kg": 76.2, "water_ml": 1500, "body_fat_pct": 17.9,
                    "neck_cm": 38.5, "waist_cm": 86, "hip_cm": null, "notes": "" }
  },
  "workout_logs": {
    "2026-07-31": {
      "workout_type": "Friday Calisthenics Form Check",
      "completed_circuits": 0,
      "exercises": [ { "name": "…", "target": "…", "completed": true, "rpe": 4, "comment": "" } ],
      "extra_cardio": { "distance_km": 5.2, "duration_minutes": 31, "notes": "" },
      "archived_exercises": [ /* opcionális: újraimport után a tervből kikerült, kitöltött gyakorlatok */ ]
    }
  }
}
```

**Export fájlnév:** `<profil>_results_<év>_w<hét>.json`, pl. `male_results_2026_w31.json`.
**Import:** dátumonként/hetenként felülíró összefésülés (az importált fájl nyer).

## 5. Heti edzésterv JSON formátum

```json
{
  "week_id": "2026-W32",
  "week_label": "opcionális leírás",
  "program": {
    "1": { "name": "Hétfői edzés", "circuits": 4,
           "exercises": [ { "name": "Standard Push-up", "target": "4 kör x 8 ismétlés",
                            "description": "opcionális leírás a gyakorlatkönyvtárhoz" } ] },
    "2": { … }, "3": { … }, "4": { … }, "5": { … },
    "6": { … }
  }
}
```
- `week_id` kötelező, formátuma `YYYY-WXX`.
- `"6"` (szombat) és `"7"` (vasárnap) opcionális; ha hiányzik, pihenőnap.
- `description` opcionális; a gyakorlatkönyvtárban jelenik meg.
- A gyakorlat `name` mezője alapján választja ki a képet (`getExerciseImagePath`).
- Ugyanarra a hétre újraimportálás felülírja a korábbi tervet.

## 6. Kódstruktúra (fő függvények)

| Szakasz | Függvények |
|---|---|
| Állapot | `appState` (`currentDate`, `calendarDate`, `data`), `getInitialState`, `currentProfile`, `STORAGE_KEYS` |
| Profil | `toggleProfile` – menti az aktuális, betölti a másik profilt, téma-osztály váltás |
| Segéd | `formatDate`, `formatDateHungarian`, `getISOWeekString`, `getWeekStartDate`, `getProgramForDate`, `showToast`, `calculateBMI`, `getBMIStatus`, `calculateBodyFatBMI`, `calculateBodyFatNavy` |
| Napló-takarítás | `hasExerciseData`, `hasCardioData`, `isEmptyDailyLog`, `isEmptyWorkoutLog`, `pruneEmptyLogs` |
| Heti KPI | `getWeightsForWeek`, `computeWeeklyAverage`, `computePreviousWeekId`, `renderWeeklyKPI`, `drawWeeklyChart` |
| Képek | `getExerciseImagePath` (név → fájl térkép), `getExerciseImageHTML` (kép + monogramos tartalék) |
| Tárolás | `loadData` (migrációkkal), `saveData`, `ensureDailyLog` |
| Dashboard | `renderDashboard`, `saveWeight`, `addWater`, `resetWater` |
| Edzés | `buildWorkoutLog` (név szerinti összefésülés), `getEditableWorkoutLog` (napló létrehozása első módosításkor), `renderWorkout`, `updateCardio`, `toggleExerciseCompleted`, `updateExerciseRPE`, `updateExerciseComment`, `saveWorkout` |
| Mentés-emlékeztető | `getLastExportKey`, `getLastExportDate`, `renderBackupReminder` |
| Naptár / navigáció | `renderWeeklyRibbon`, `hasAnyDataForDate`, `selectDateFromRibbon`, `renderCalendar`, `selectDate`, `changeMonth`, `goToToday`, `navigateToView` |
| Beállítások / adat | `renderSettings`, `saveUserProfile`, `exportData`, `importData`, `importWeeklyProgram`, `clearAllData` |
| Könyvtár | `BUILTIN_EXERCISES` (beépített leírások), `renderExerciseLibrary` (beépített + tervekből gyűjtött) |

Renderelési minta: minden nézet teljes `innerHTML` újraépítéssel frissül; az eseménykezelők inline `onclick`/`onchange` attribútumok.

## 7. Változásnapló

### 2026-10-15 – havi Gemini edzői kör (3. fázis)
- A backend összefoglalót készít a 4 hétről, a Gemini értékel és változásokat javasol; a backend validálja (katalógus,
  ésszerű számok, rehab- és fájdalomvédelem), a felhasználó változásonként hagyja jóvá.
- Automatikus mód API-kulccsal (gomb az appban + havi cron), kézi mód kulcs nélkül (prompt másolása / válasz beillesztése).
- Ezzel kiváltható a folytonos JSON import/export: a heti terv a szabálymotorból vagy a havi edzői körből jön.

### 2026-10-15 – szabálymotor (2. fázis)
- Jövő heti tervjavaslat dupla progresszióval, szalag-/variánsváltással, kudarc utáni visszalépéssel, rehab-védelemmel,
  fájdalom szerinti könnyítéssel/cserével és az alulterhelt izmok pótlásával. Változásonként jóváhagyható (Haladás nézet).
- Edzés közben minden gyakorlatnál látszik a legutóbbi teljesítmény.

### 2026-10-15 – PWA frontend (1. fázis, 2. rész)
- Új `frontend/`: telefonra telepíthető, offline is működő app (Vite + Dexie + Service Worker), amit a backend konténere szolgál ki.
- Sorozatonkénti naplózás, nehézség-chipek, fájdalom-rögzítés testterülettel/oldallal/erősséggel, pihentetési figyelmeztetés, rehab-jelölés.
- Izomterhelés-táblázat hetekre bontva, gyakorlatkönyvtár progressziós lánccal és saját előzményekkel, naptár.
- Backend: a szinkronban az elutasított dokumentum nyertes változata mindig visszajön; új `POST /api/import/legacy`.
- A régi `fitness_tracker.html` az átállásig változatlanul használható; az adatai a Beállításokból tölthetők át.

### 2026-10-15 – backend, 1. fázis
- Új `backend/`: FastAPI + SQLite, Docker service az Optiplexre, Tailscale HTTPS, éjszakai S3 mentés.
- Relációs adatmodell: sorozatszintű naplózás, nehézség-chipek (könnyű/ok/nehéz/nem sikerült), fájdalom-bejegyzések, rehab jelölés.
- Saját gyakorlat-katalógus: 37 gyakorlat, 19 izomcsoport, izomszorzók, 9 progressziós lánc. A régi tervek mind a 46 gyakorlatneve felismerve.
- Régi exportok importja: a célszövegekből („4 kör x 12-12 ismétlés (9kg-os szalag)”) strukturált előírás lesz.
- Offline-first szinkron API a készülő PWA-hoz. A mostani HTML app változatlanul használható az átállásig.

### 2026-10-15 – optimalizálás
- **Javítva:** pipáláskor nem vész el a beírt kardió (gépelés közben mentődik).
- **Javítva:** terv újraimportálásakor a napló név szerint fésülődik össze, nem törlődik.
- **Javítva:** megtekintés nem hoz létre üres naplót; a régi üres naplók automatikusan törlődnek (a W31 exporton: 40 → 32 edzésnapló, 58 → 49 napi napló; súlyadat nem veszett el).
- **Teljesítmény:** a Tailwind CDN helyett ~11,5 KB-os beágyazott CSS (korábban ~400 KB JS + futásidejű fordítás); offline is működik.
- **Új:** dinamikus gyakorlatkönyvtár, mentés-emlékeztető, toast értesítések az `alert()` ablakok helyett, hétvégi edzés a tervből.

## 8. Ismert hibák és korlátok (még nyitott)

### Hibák
1. **Idézőjel a kommentben eltöri az űrlapot** – a komment és a kardió-megjegyzés escape nélkül kerül a HTML-be (`"` → levágott szöveg; `<` → HTML-befecskendezés).
2. **Rossz kép ismeretlen gyakorlatnál** – a térképben nem szereplő gyakorlatok (a betöltött 44 névből ~25) a fekvőtámasz képét kapják a monogramos tartalék helyett. A dinamikus könyvtár miatt ez most sokkal feltűnőbb.
3. **Naptár hónaplépés hónap végén** – 29–31-én a „Következő” gomb hónapot ugorhat (pl. jan. 31 → márc. 3).
4. **A profilválasztás nem marad meg** újratöltés után (mindig a férfi profil indul).
5. **`week_label` elveszik** importáláskor.
6. **Kis/nagybetű eltérés a képfájlnévben** – a kód `Gumiszalagos evezés ülve.png`-t kér, a fájl `gumiszalagos evezés ülve.png`; Windowson működik, de webszerveren / telefonon nem.
7. A súly-dátumok `new Date('YYYY-MM-DD')` UTC-ként értelmeződnek (negatív időzónában rossz hétre eshetnek).

### Teljesítmény / karbantartás
- **Képek:** ~20 MB az `assets/img`-ben; egy 80 px-es bélyegképhez 5,3 MB-os, 2382×1792-es PNG töltődik. A `push-up`, `plank`, `incline-push-up`, `dolphin-plank` négy azonos fájl. A `original.png`, `band original.png`, `calf-raise----.png` (~10 MB) nincs használva.
- Minden kattintás több teljes nézetet is újrarajzol; a kódban a dátum- és naplókezelés sokszor ismétlődik.
- ~~Fölösleges másolatok~~ – rendezve: az `_archiv/` mappába kerültek (2026-10-15).
- A böngészőadatok törlése továbbra is mindent visz – az emlékeztető csak figyelmeztet, a mentést neked kell exportálni.
