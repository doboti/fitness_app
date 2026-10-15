# Heti terv JSON-formátuma

A heti terv egyetlen JSON fájl (`YYYY-WXX.json`, pl. `2026-W43.json`). Feltölthető a telefonos appból
(Beállítások → *Heti terv feltöltése*) vagy az API-n (`POST /api/programs`). Ugyanarra a hétre újra feltöltve felülírja
a korábbit. A szabálymotor és a Gemini-edző is ilyen tervet készít. Sablon: [weekly-program-template.json](weekly-program-template.json).

```json
{
  "week_id": "2026-W43",
  "week_label": "Opcionális leírás",
  "program": {
    "1": {
      "name": "Hétfő – Push & Core",
      "circuits": 4,
      "exercises": [
        { "name": "Standard Push-up", "target": "4 kör x 10 ismétlés" },
        { "name": "Clamshell", "target": "3 kör x 15-15 ismétlés", "rehab": true },
        { "name": "Standard Plank", "target": "4 kör x 1 perc 15 másodperc (Törzs feszít!)",
          "description": "Opcionális leírás a gyakorlatkönyvtárhoz" }
      ]
    },
    "6": { "name": "Szombati futás + mobilitás", "circuits": 1, "exercises": [] }
  }
}
```

| Mező | Kötelező | Jelentés |
|---|---|---|
| `week_id` | igen | ISO hét, `YYYY-WXX` (vezető nullával: `W01`) |
| `program` | igen | napok: `"1"` = hétfő … `"5"` = péntek, `"6"` = szombat, `"7"` = vasárnap. A hiányzó hétvégi nap pihenőnap. |
| `circuits` | nem | körök száma; ha a célban nincs „N kör x”, ez lesz a sorozatszám |
| `name` | igen | gyakorlatnév – a [katalógus](../backend/app/seed/exercises.json) neve vagy aliasa (magyar vagy angol); zárójeles utótag megengedett |
| `target` | igen | szabad szöveg, amit a backend értelmez (lásd lent); a zárójeles megjegyzés csak információ |
| `rehab` | nem | `true` = rehab gyakorlat: a motor nem nehezíti, a fájdalom miatti kímélés nem tiltja |
| `description` | nem | leírás a gyakorlatkönyvtárhoz |

## A cél (`target`) értelmezése

| Szöveg | Értelmezés |
|---|---|
| `4 kör x 10 ismétlés` | 4 sorozat × 10 ismétlés |
| `4 kör x 8-10 ismétlés` | 4 sorozat, 8–10 ismétlés tartomány |
| `4 kör x 12-12 ismétlés` / `12 ismétlés lábanként` | oldalanként 12 |
| `4 kör x 1 perc 15 másodperc` / `45 másodperc` / `30 mp` | időre (75 / 45 / 30 mp) |
| `3 kör x Maximum` / `Max idő` | bukásig (ismétlés / idő) |
| `… (9kg-os szalag)` | 9 kg-os gumiszalag |

A fel nem ismert gyakorlatnevet a feltöltés jelzi. Ezt aliasként kell felvenni a katalógusba, különben az a gyakorlat
nem számít bele az izomstatisztikába, és a motor sem tud vele számolni.
