# PROD telepítés: GitHub Actions → Optiplex (kézi indítás)

```
fejlesztés → git push (bármelyik ág) ──► CI: tesztek minden pushnál
                                        │
Actions → „Deploy PROD” → Run workflow ─┴► tesztek ──► GitHub gépe belép a tailnetbe (ideiglenes tag:ci eszköz)
                                                         └─► SSH az Optiplexre ──► scripts/deploy.sh <commit>
                                                               mentés → git checkout → docker build → health check
                                                               → hiba esetén automatikus visszaállás az előző verzióra
```

- A repó publikus marad. Az Optiplexen nem fut GitHub-runner, és nem kell portot nyitni; csak a tailneten keresztül,
  SSH-val, egyetlen kötött paranccsal érhető el.
- Az SSH-kulccsal **kizárólag** a `deploy.sh` futtatható, és az is csak egy 40 karakteres commit-azonosítót fogad el,
  ami a GitHub-repóban létezik. Ha a kulcs kiszivárogna, akkor sem lehet vele más kódot futtatni.
- A titkokat (Tailscale, SSH) a GitHub `production` környezete őrzi; ott jóváhagyást is lehet kérni minden telepítéshez.

## Egyszeri beállítás

### 1. Optiplex: felhasználó és mappák

```bash
sudo adduser --disabled-password --gecos "" deploy
sudo usermod -aG docker deploy
sudo mkdir -p /srv/workout/data
sudo chown deploy:deploy /srv/workout
sudo chown 1000:1000 /srv/workout/data          # a konténer 1000-es felhasználóként írja az adatbázist
sudo -u deploy git clone https://github.com/doboti/fitness_app.git /srv/workout/app
```

Opcionális Gemini-kulcs (havi edzői kör): `sudo -u deploy nano /srv/workout/app/.env`
```
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.8-flash
```

**Meglévő adatok átvitele (javasolt):** a helyi adatbázisból készíts egy mentést, és azt vidd át az első telepítés előtt.
Benne van Boti és Johi profilja, és minden eddigi napló. A `local.db`-t **ne** másold közvetlenül: a legutóbbi
változások a mellette lévő `local.db-wal` fájlban vannak, a mentés viszont mindent egyetlen fájlba tesz.
```powershell
# a Windows gépen, a repó gyökeréből (a helyi szerver futhat közben):
.\scripts\run-local.ps1 -Cli backup backend\data\export-a-szerverre --keep 1
scp backend\data\export-a-szerverre\workout-*.db.gz <te>@<optiplex>:/tmp/
```
```bash
# az Optiplexen (ha a konténer már fut: előtte docker stop workout-api, utána docker start workout-api):
sudo rm -f /srv/workout/data/workout.db-wal /srv/workout/data/workout.db-shm
gunzip -c /tmp/workout-*.db.gz | sudo tee /srv/workout/data/workout.db > /dev/null
sudo chown 1000:1000 /srv/workout/data/workout.db && rm /tmp/workout-*.db.gz
```
Ha üresen indulsz: az első telepítés után `docker exec -it workout-api python -m app.cli create-user --name Boti --gender male`
(és ugyanígy Johi), a régi exportok pedig az appból tölthetők be (Beállítások → Régi app exportjának betöltése).

### 2. SSH-kulcs (kötött paranccsal)

A Windows gépen (PowerShell):
```powershell
ssh-keygen -t ed25519 -f $HOME\.ssh\workout-deploy -N '""' -C github-deploy
Get-Content $HOME\.ssh\workout-deploy.pub        # ezt a sort kell az Optiplexre tenni
```

Az Optiplexen (a `<publikus kulcs>` helyére a fenti sort):
```bash
sudo -u deploy mkdir -p -m 700 /home/deploy/.ssh
echo 'command="/srv/workout/app/scripts/deploy.sh",restrict <publikus kulcs>' | sudo -u deploy tee -a /home/deploy/.ssh/authorized_keys
sudo chmod 600 /home/deploy/.ssh/authorized_keys
```

A szerver ujjlenyomata (bármelyik tailnetes gépről, ahol van `ssh-keyscan`; az `<optiplex IP>` a Tailscale-cím, pl. 100.x.y.z):
```bash
ssh-keyscan -t ed25519 <optiplex IP>
```

### 3. Tailscale

**Hozzáférési szabály** (admin → Access controls). A `tag:ci` eszközök csak az Optiplex 22-es portját érhetik el. Ha a
policy még az alapértelmezett „mindenki mindent” szabály, cseréld erre (a saját eszközeid továbbra is mindent elérnek):
```jsonc
{
  "tagOwners": { "tag:ci": ["autogroup:admin"] },
  "hosts":     { "optiplex": "100.x.y.z" },
  "acls": [
    { "action": "accept", "src": ["autogroup:member"], "dst": ["*:*"] },
    { "action": "accept", "src": ["tag:ci"],           "dst": ["optiplex:22"] }
  ]
}
```

**OAuth kliens** (admin → Settings → OAuth clients → Generate): jogosultság *Auth Keys – Write*, tag: `tag:ci`.
A kapott *Client ID* és *Client secret* kell a GitHubba. A CI-eszközök ideiglenesek: a futás végén eltűnnek a tailnetből.

**HTTPS az appnak** (egyszer, az Optiplexen): `sudo tailscale serve --bg 8420`. A `tailscale serve status` kiírja a címet.

### 4. GitHub

Repó → Settings → **Environments** → New environment: `production`
- (ajánlott) *Required reviewers*: te. Így minden telepítés előtt egy kattintással jóvá kell hagynod.
- **Environment secrets:**

| Név | Érték |
|---|---|
| `TS_OAUTH_CLIENT_ID` | a Tailscale OAuth kliens azonosítója |
| `TS_OAUTH_SECRET` | a Tailscale OAuth kliens titka |
| `DEPLOY_HOST` | az Optiplex Tailscale IP-címe (ugyanaz, mint az `ssh-keyscan`-nél) |
| `DEPLOY_USER` | `deploy` |
| `DEPLOY_SSH_KEY` | a `workout-deploy` privát kulcs teljes tartalma (`Get-Content $HOME\.ssh\workout-deploy`) |
| `DEPLOY_KNOWN_HOSTS` | az `ssh-keyscan` kimenete |

**Fontos:** a *Run workflow* gomb csak akkor jelenik meg, ha a `.github/workflows/deploy.yml` az alapértelmezett ágon
(`main`) is ott van. Ehhez egyszer be kell olvasztani a fejlesztői ágat a `main`-be. Utána bármelyik ágat ki lehet
választani a telepítéshez.

## Napi használat

1. Fejlesztés helyben (`.\scripts\run-local.ps1`), commit, `git push`. A CI minden pushnál lefuttatja a teszteket.
2. GitHub → **Actions → Deploy PROD → Run workflow**, és válaszd ki az ágat.
3. (Ha van jóváhagyás) a `production` környezet kérésénél kattints az *Approve*-ra.
4. A futás naplójában látod a telepítés lépéseit; a végén az összefoglaló mutatja a commitot és az eredményt.

**Visszaállás:** sikertelen indulásnál a script magától visszaáll. Egy már telepített, de rossz verziónál vond vissza a
hibás commitot a gitben (`git revert`), és telepíts újra. Végszükség esetén az Optiplexen, `deploy` felhasználóként:
`/srv/workout/app/scripts/deploy.sh <régebbi commit teljes azonosítója>`.

**Hasznos parancsok az Optiplexen:**
```bash
cat /srv/workout/DEPLOYED_COMMIT              # melyik commit fut
docker logs --tail 100 workout-api            # app napló
ls -lt /srv/workout/data/backups | head       # telepítés előtti és éjszakai mentések
```

**Éjszakai mentés** (crontab, `deploy` felhasználóként):
```
15 3 * * *  DATA_DIR=/srv/workout/data /srv/workout/app/scripts/backup.sh >> /srv/workout/backup.log 2>&1
```
Helyben 14 mentést tart meg (`KEEP`). Felhőbe is küldheti: `S3_BUCKET=s3://...` (a hoston kell az `aws` CLI és egy csak
`s3:PutObject` jogú IAM kulcs). Visszaállítás: `gunzip` a mentésre, és cseréld le vele a `/srv/workout/data/workout.db`-t
(leállított konténer mellett: `docker stop workout-api`, csere, `docker start workout-api`).
