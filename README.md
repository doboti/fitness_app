# Edzésnapló – otthoni edzés, izomkövetés, fájdalomnapló

Saját testsúlyos / gumiszalagos otthoni edzések naplózása telefonról (offline is), izomcsoportonkénti terhelés-követés,
fájdalom esetén automatikus kímélés, heti tervjavaslat szabálymotorral és havi edzői értékelés a Geminivel.

```
┌────────────── telefon (PWA, offline) ─────────────┐      Tailscale HTTPS      ┌──────── Optiplex (Docker) ────────┐
│ napló → IndexedDB (Dexie) ── szinkron, ha elérhető ├──────────────────────────▶│ FastAPI + SQLite  ·  szabálymotor │
└────────────────────────────────────────────────────┘                          │ havi Gemini edzői kör (opcionális)│
                                                                                └───────────────────────────────────┘
```

## Mappaszerkezet

```
├── backend/            FastAPI + SQLite: API, szinkron, szabálymotor, Gemini-edző, gyakorlat-katalógus (seed)
├── frontend/           PWA (Vite + Dexie + Service Worker), a backend konténere szolgálja ki
├── .github/workflows/  CI (tesztek minden pushnál) és Deploy PROD (kézi indítás → Optiplex)
├── scripts/            deploy.sh (PROD telepítés), backup.sh (mentés), run-local.ps1 (helyi futtatás)
├── docs/               heti terv JSON-formátuma + sablon, a régi app leírása és változásnaplója
├── legacy/             a régi egyfájlos app (fitness_tracker.html + képek) – az átállásig használható
├── Dockerfile, docker-compose.yml
├── data/               (gitignore) személyes adatok: régi exportok, heti tervek, dokumentumok
└── _archiv/            (gitignore) régi másolatok, használaton kívüli képek, elavult jegyzetek – törölhető
```

| Dokumentum | Tartalom |
|---|---|
| [backend/README.md](backend/README.md) | API, szinkron, adatmodell, szabálymotor, Gemini-edző, fejlesztés és tesztek |
| [docs/deploy.md](docs/deploy.md) | CI/CD: egyszeri beállítás és napi használat (GitHub Actions → Tailscale → Optiplex) |
| [docs/heti-terv-formatum.md](docs/heti-terv-formatum.md) | a heti terv JSON-formátuma |
| [docs/regi-app.md](docs/regi-app.md) | a régi egyfájlos app leírása és a teljes változásnapló |

| | |
|---|---|
| Futtatás | Docker konténer az Optiplexen, `127.0.0.1:8420` |
| Elérés | Tailscale (`tailscale serve`) → `https://<gép>.<tailnet>.ts.net` |
| Adat | egyetlen SQLite fájl: `/data/workout.db` (volume) |
| Erőforrás | ~60–100 MB RAM, üresjáratban ~0% CPU |

## Telepítés az Optiplexre (CI/CD)

A PROD-ot a GitHub Actions telepíti, kézi indításra: **Actions → Deploy PROD → Run workflow → ág kiválasztása**.
A tesztek után a GitHub gépe Tailscale-en és SSH-n keresztül szól az Optiplexnek, ami menti az adatbázist, újrabuildel,
ellenőrzi az appot, és hiba esetén visszaáll az előző verzióra. Minden pushnál a CI lefuttatja a teszteket.

Az egyszeri beállítás (Optiplex, Tailscale, GitHub-titkok, adatátvitel, mentés) lépésről lépésre: **[docs/deploy.md](docs/deploy.md)**.

A konténer csak a `127.0.0.1`-en figyel; kívülről kizárólag a tailneten keresztül érhető el (`tailscale serve`, HTTPS).
Régi exportok szerveroldali betöltése: `docker exec workout-api python -m app.cli import-legacy --name Boti /data/import/*.json`.

## Telefon beállítása

1. Telepítsd a **Tailscale** appot, és lépj be ugyanabba a tailnetbe.
2. Nyisd meg a `https://<gép>.<tailnet>.ts.net` címet (Chrome / Safari), és válaszd ki a profilodat (Boti / Johi).
3. **Telepítés:** Android Chrome → menü → *Alkalmazás telepítése*; iPhone Safari → Megosztás → *Főképernyőhöz adás*.
4. Az első betöltés után az app **offline is indul**. A rögzített adat a telefonon marad (IndexedDB), és amint
   eléri a szervert, magától szinkronizál (a fejlécben: *mentve* / *N vár* / *nincs kapcsolat*).

Egy eszközön több fiók is lehet (Beállítások → *Másik fiók hozzáadása*), a fiókok között egy koppintással lehet váltani.
A régi app exportját és új heti terveket a Beállításokból is fel lehet tölteni, nem kell hozzá `docker exec`.

### iPhone – tudnivalók

- **HTTPS kell.** Az offline mód és a fájdalom-rögzítés csak biztonságos kapcsolaton működik, ezért a Tailscale-es
  `https://….ts.net` címet használd, ne a gép `http://192.168…` IP-címét.
- **Safariban add hozzá a főképernyőhöz,** és onnan indítsd: így teljes képernyős, saját ikonnal fut, és az iOS nem törli
  az adatait (a sima Safari-lapok tárhelyét 7 nap használatlanság után törölheti).
- Az első megnyitáskor töltsd be egyszer online, utána offline is indul. Az adat amúgy is a szerverre szinkronizálódik.
- **Johinak:** a Tailscale admin felületén oszd meg vele a szervert (*Share* a gépnél, vagy hívd meg a tailnetbe), majd ő
  is a fenti lépésekkel telepíti a saját telefonjára, és a profilválasztóban a „Johi (nő)”-t választja.

## Helyi kipróbálás (Windows, Docker nélkül)

Python 3.12+ és Node.js kell. A repó gyökeréből, PowerShellben:

```powershell
.\scripts\run-local.ps1          # első futáskor környezet + build, utána: http://localhost:8420
# másik ablakban: fiók létrehozása és régi adatok betöltése
.\scripts\run-local.ps1 -Cli create-user --name Boti --gender male --height 175 --age 30 --target-weight 70
.\scripts\run-local.ps1 -Cli import-legacy --name Boti data\exports\male_results_2026_w42.json
```

A helyi adatbázis a `backend\data\local.db` fájl (gitignore-ban), független a szerverétől. Törlésével tiszta lappal indulhatsz.
Böngészőben a `localhost`-on minden működik, az offline mód is. Telefonról a géped IP-címén csak HTTPS nélkül érhető el,
így az offline mód és a fájdalom-rögzítés nem működik. Telefonos teszthez a Tailscale kell (lásd fent).

## Fejlesztés

Lásd: [backend/README.md → Fejlesztés](backend/README.md#fejlesztés). Röviden: `cd backend && pytest`, `cd frontend && npm test`,
`npm run dev` (a Vite az `/api`-t a `127.0.0.1:8420`-as backendre proxyzza).
