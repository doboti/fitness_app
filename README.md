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
├── scripts/backup.sh   éjszakai SQLite-mentés (+ S3)
├── docs/               heti terv JSON-formátuma + sablon, a régi app leírása és változásnaplója
├── legacy/             a régi egyfájlos app (fitness_tracker.html + képek) – az átállásig használható
├── Dockerfile, docker-compose.yml
├── data/               (gitignore) személyes adatok: régi exportok, heti tervek, dokumentumok
└── _archiv/            (gitignore) régi másolatok, használaton kívüli képek, elavult jegyzetek – törölhető
```

| Dokumentum | Tartalom |
|---|---|
| [backend/README.md](backend/README.md) | API, szinkron, adatmodell, szabálymotor, Gemini-edző, fejlesztés és tesztek |
| [docs/heti-terv-formatum.md](docs/heti-terv-formatum.md) | a heti terv JSON-formátuma |
| [docs/regi-app.md](docs/regi-app.md) | a régi egyfájlos app leírása és a teljes változásnapló |

| | |
|---|---|
| Futtatás | Docker konténer az Optiplexen, `127.0.0.1:8420` |
| Elérés | Tailscale (`tailscale serve`) → `https://<gép>.<tailnet>.ts.net` |
| Adat | egyetlen SQLite fájl: `/data/workout.db` (volume) |
| Erőforrás | ~60–100 MB RAM, üresjáratban ~0% CPU |

## Telepítés az Optiplexre (Ubuntu + Docker)

1. **Klónozd a repót** az Optiplexre, pl. `~/stack/workout-app/` alá (`git clone https://github.com/doboti/fitness_app.git workout-app`).
2. **Compose:** önállóan a repó gyökeréből `docker compose up -d --build`, vagy a [docker-compose.yml](docker-compose.yml) `workout-api`
   blokkját másold a meglévő stackbe (a `context:` a repó mappája legyen). Az első build a frontend miatt 1-2 perc:
   ```bash
   docker compose up -d --build workout-api
   curl http://127.0.0.1:8420/api/health
   ```
3. **Profilok** (az appban a belépéskor egy legördülő menüből választható, jelszó nincs):
   ```bash
   docker exec -it workout-api python -m app.cli create-user --name Boti --gender male --height 175 --age 30 --target-weight 70
   docker exec -it workout-api python -m app.cli create-user --name Johi --gender female
   ```
4. **Régi adatok betöltése:** legegyszerűbb a telefonos appból (Beállítások → *Régi app exportjának betöltése*). Szerveroldalon:
   másold a helyi `data/exports/` és `data/plans/` tartalmát a `workout-data/import/` mappába, majd:
   ```bash
   docker exec workout-api sh -c 'python -m app.cli import-legacy --name Boti /data/import/exports/*.json /data/import/plans/ferfi/*.json'
   docker exec workout-api sh -c 'python -m app.cli import-legacy --name Johi /data/import/plans/noi/*.json'
   ```
   A fájlnév szerinti sorrendben töltődnek be, a későbbi export felülírja a korábbit. Ugyanaz a fájl újra betölthető.
   A végén kiírja a fel nem ismert gyakorlatneveket; ezeket aliasként kell felvenni a [backend/app/seed/exercises.json](backend/app/seed/exercises.json)-ba.
5. **HTTPS a Tailscale-lel** (egyszer kell beállítani; a tailnet admin felületén legyen bekapcsolva a MagicDNS és a HTTPS Certificates):
   ```bash
   sudo tailscale serve --bg 8420
   tailscale serve status      # kiírja a https://… címet
   ```
   A telefonokra a Tailscale app kell. A konténer csak a `127.0.0.1`-en figyel, így kizárólag a tailneten keresztül érhető el.
6. **Éjszakai mentés** a [scripts/backup.sh](scripts/backup.sh)-val (`chmod +x`), crontabba:
   ```
   15 3 * * *  DATA_DIR=/home/<user>/stack/workout-data S3_BUCKET=s3://sajat-workout-backup /home/<user>/stack/workout-app/scripts/backup.sh >> /var/log/workout-backup.log 2>&1
   ```
   Helyben 14 mentést tart meg (`KEEP`). S3-hoz a hoston kell az `aws` CLI és egy csak `s3:PutObject` jogú IAM kulcs.
   Visszaállítás: `gunzip` a mentésre, és cseréld le vele a `workout.db`-t (leállított konténer mellett).

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
