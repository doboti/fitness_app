# Heti Edzésterv Rendszer

## Áttekintés

A Fitness Tracker alkalmazás mostantól dinamikus, heti alapú edzésterveket támogat JSON fájlok importálásával. Nem kell módosítani a kódot új hetek hozzáadásához!

## JSON Fájl Formátum

### Fájlnév Konvenció
```
YYYY-WXX.json
```
Például: `2026-W23.json`, `2026-W24.json`, stb.

### Kötelező Mezők

```json
{
  "week_id": "2026-W23",
  "week_label": "1. Hét: Strand-Alapozás (opcionális)",
  "program": {
    "1": { /* Hétfő */ },
    "2": { /* Kedd */ },
    "3": { /* Szerda */ },
    "4": { /* Csütörtök */ },
    "5": { /* Péntek */ }
  }
}
```

### Napi Program Struktúra

```json
"1": {
  "name": "Upper Body & Core A",
  "circuits": 4,
  "exercises": [
    { 
      "name": "Standard Push-up", 
      "target": "4 kör x 8 ismétlés" 
    }
  ]
}
```

## ISO Hét Számítás

Az alkalmazás automatikusan kiszámítja, hogy egy adott dátum melyik ISO hétre esik:
- **2026. június 5.** → `2026-W23`
- **2026. június 12.** → `2026-W24`

## Használat

### 1. Heti Program Importálása

1. Nyisd meg a **⚙️ Beállítások** tab-ot
2. Görgess le az **"Adatkezelés & Szinkronizáció"** részhez
3. Kattints a **"📅 Heti Edzésterv Importálása"** gombra
4. Válaszd ki a JSON fájlt (pl. `2026-W23.json`)
5. Sikeres importálás után megjelenik egy megerősítő üzenet

### 2. Edzés Megtekintése

Ha a jelenlegi hétre van betöltött program:
- A **Dashboard** mutatja a mai edzést
- Az **🏋️ Edzés** tab-on látható a részletes naplózó felület
- Minden gyakorlat tartalmaz képet, célt, és teljesítés gombot

Ha nincs program:
- Figyelmeztetés jelenik meg: **"⚠️ Nincs edzésterv betöltve erre a hétre"**
- Link a Beállításokhoz a program importálásához

## Gyakorlat Nevek (Képek Miatt Fontos!)

A következő gyakorlat nevek automatikusan párosulnak a megfelelő képekkel:

| Gyakorlat Név | Kép Fájl |
|---------------|----------|
| Standard Push-up | push-up.png |
| Incline Push-up | incline-push-up.png |
| Incline Push-up or Dolphin Plank | incline-push-up.png |
| Standard Plank | plank.png |
| Plank to Failure | plank.png |
| Prone Cobra | prone-cobra.png |
| Standard Sit-up | sit-up.png |
| Air Squat | squat.png |
| Walking Lunge | lunge.png |
| Reverse Lunge | lunge.png |
| Standing Calf Raise | calf-raise.png |
| Plank Hip Dips | plank-dips.png |
| Dolphin Plank | dolphin-plank.png |
| Lying Leg Raise | leg-raise.png |
| Superman Hold | superman.png |
| High Knees | high-knees.png |
| Russian Twist | russian-twist.png |
| Squat to Cross-Body Knee Drive | squat-knee-drive.png |

**Fontos:** A JSON fájlban pontosan ezeket a neveket használd a képek automatikus betöltéséhez!

## Adatok Tárolása

- A betöltött heti programok mentődnek a `localStorage`-ba
- Az **"Adatbázis Exportálása"** funkció tartalmazza az összes heti programot
- Több hetet is be tudsz tölteni párhuzamosan
- Minden hét független egymástól

## Példa JSON Fájlok

### Egyszerű Példa
Lásd: `weekly-program-template.json`

### Teljes Példa
Lásd: `2026-W23.json`

## Hibaelhárítás

### "Hibás fájlformátum" hiba
- Ellenőrizd, hogy a JSON valid-e
- Kötelező mezők: `week_id`, `program`
- A `program` objektumban legalább 1-5 napnak kell lennie

### "Hibás week_id formátum" hiba
- A formátum: `YYYY-WXX` (pl. `2026-W23`)
- Az év 4 számjegy, a hét 2 számjegy (00-53)
- Használj vezető nullát: `W01`, `W02`, ..., `W23`

### "Nincs edzésterv betöltve" üzenet
- Importálj egy JSON fájlt a jelenlegi hétre
- Ellenőrizd a hét azonosítót (megjelenik az üzenetben)
- Nevezd át a JSON fájlt, hogy megfeleljen az azonosítónak

## 12 Hónapos Program Kezelése

Ha 52 hetes programot használsz:
1. Készíts 52 JSON fájlt: `2026-W01.json` ... `2026-W52.json`
2. Importáld őket egyesével, ahogy haladnak a hetek
3. Vagy importálj előre több hetet egyszerre
4. Az alkalmazás automatikusan a megfelelő hetet tölti be a dátum alapján

Jó edzést! 💪
