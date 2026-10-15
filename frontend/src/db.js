import Dexie from 'dexie';

/**
 * Helyi adatbázis felhasználónként (több fiók egy eszközön, pl. közös tablet).
 * A szinkronizált dokumentumok a szerver formátumát követik, plusz:
 *   _dirty: 1 = helyben módosult, még nincs a szerveren; _error: a szerver elutasításának oka.
 */
export function openDb(uid) {
    const db = new Dexie(`workout-u${uid}`);
    db.version(1).stores({
        daily_logs: 'date, _dirty',
        sessions: 'id, date, _dirty',
        pain_reports: 'id, date, _dirty',
        programs: 'week_id',
        exercises: 'id',
        muscles: 'code',
        meta: 'key',
    });
    return db;
}

export async function getMeta(db, key, fallback = null) {
    const row = await db.meta.get(key);
    return row ? row.value : fallback;
}

export function setMeta(db, key, value) {
    return db.meta.put({ key, value });
}
