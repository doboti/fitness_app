import { getMeta, setMeta } from './db.js';

const TABLES = [
    { name: 'daily_logs', key: 'date', prefix: 'daily' },
    { name: 'sessions', key: 'id', prefix: 'session' },
    { name: 'pain_reports', key: 'id', prefix: 'pain' },
];

const stripLocal = ({ _dirty, _error, ...doc }) => doc;
const newer = (a, b) => Date.parse(a) > Date.parse(b);

/** Helyi módosítás mentése: frissíti az updated_at-et és megjelöli szinkronizálandónak. */
export async function saveLocal(db, tableName, doc) {
    const stamped = { ...doc, updated_at: new Date().toISOString(), _dirty: 1, _error: null };
    await db[tableName].put(stamped);
    return stamped;
}

export async function pendingCount(db) {
    const counts = await Promise.all(TABLES.map((t) => db[t.name].where('_dirty').equals(1).count()));
    return counts.reduce((a, b) => a + b, 0);
}

/**
 * Egy push+pull kör.
 * - A sikeresen elküldött dokumentum _dirty jelzése csak akkor törlődik, ha közben nem módosult tovább helyben.
 * - Bejövő változás nem írja felül a helyben újabb, még el nem küldött változatot.
 */
export async function runSync(db, api) {
    const cursor = await getMeta(db, 'cursor', 0);
    const pushed = {};
    for (const t of TABLES) pushed[t.name] = await db[t.name].where('_dirty').equals(1).toArray();

    const response = await api.post('/api/sync', {
        cursor,
        daily_logs: pushed.daily_logs.map(stripLocal),
        sessions: pushed.sessions.map(stripLocal),
        pain_reports: pushed.pain_reports.map(stripLocal),
    });

    let pulled = 0;
    await db.transaction('rw', db.daily_logs, db.sessions, db.pain_reports, db.programs, db.meta, async () => {
        for (const t of TABLES) {
            for (const doc of pushed[t.name]) {
                const id = doc[t.key];
                const current = await db[t.name].get(id);
                if (!current || current.updated_at !== doc.updated_at) continue; // közben újra módosult
                const error = response.rejected[`${t.prefix}:${id}`] || null;
                await db[t.name].update(id, { _dirty: 0, _error: error });
            }
            for (const incoming of response.changes[t.name]) {
                const current = await db[t.name].get(incoming[t.key]);
                if (current && current._dirty && newer(current.updated_at, incoming.updated_at)) continue;
                await db[t.name].put({ ...incoming, _dirty: 0, _error: null });
                pulled += 1;
            }
        }
        for (const program of response.changes.programs) {
            await db.programs.put(program);
            pulled += 1;
        }
        if (response.changes.user) await setMeta(db, 'user', response.changes.user);
        await setMeta(db, 'cursor', response.cursor);
        await setMeta(db, 'lastSync', new Date().toISOString());
    });

    const result = {
        pushed: TABLES.reduce((n, t) => n + pushed[t.name].length, 0),
        pulled,
        rejected: response.rejected,
        stale: response.stale,
    };

    // A szerver sorszáma visszalépett (pl. az adatbázisát egy mentésből állították vissza): a régi kurzorral
    // változások maradnának ki, ezért az elejétől újraszinkronizálunk (a második kör kurzora 0, nem ismétlődik).
    if (response.cursor < cursor) {
        await setMeta(db, 'cursor', 0);
        const again = await runSync(db, api);
        return { ...again, pushed: result.pushed + again.pushed, pulled: result.pulled + again.pulled,
                 rejected: { ...result.rejected, ...again.rejected }, resynced: true };
    }
    return result;
}

/** A gyakorlat-katalógus frissítése (ritkán változik; offline a helyi másolatot használjuk). */
export async function refreshCatalog(db, api) {
    const [exercises, muscles] = await Promise.all([api.get('/api/exercises'), api.get('/api/muscles')]);
    await db.transaction('rw', db.exercises, db.muscles, db.meta, async () => {
        await db.exercises.clear();
        await db.exercises.bulkPut(exercises);
        await db.muscles.clear();
        await db.muscles.bulkPut(muscles);
        await setMeta(db, 'catalogAt', new Date().toISOString());
    });
}
