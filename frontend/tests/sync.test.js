import 'fake-indexeddb/auto';
import { beforeEach, describe, expect, it } from 'vitest';
import { openDb, getMeta } from '../src/db.js';
import { pendingCount, runSync, saveLocal } from '../src/sync.js';

const emptyChanges = () => ({ daily_logs: [], sessions: [], pain_reports: [], programs: [], user: null });

function stubApi(handler) {
    const calls = [];
    return {
        calls,
        post: async (path, body) => {
            calls.push({ path, body: structuredClone(body) });
            return handler(body, calls.length);
        },
    };
}

let db;
let n = 0;
beforeEach(async () => {
    db = openDb(`test${++n}`);
    await db.open();
});

describe('szinkron', () => {
    it('elküldi a módosítást, törli a dirty jelzést, elmenti a kurzort', async () => {
        await saveLocal(db, 'daily_logs', { date: '2026-10-15', weight_kg: 75, deleted: false });
        expect(await pendingCount(db)).toBe(1);

        const api = stubApi(() => ({ cursor: 7, applied: 1, stale: [], rejected: {}, changes: emptyChanges() }));
        const result = await runSync(db, api);

        expect(result.pushed).toBe(1);
        const sent = api.calls[0].body;
        expect(sent.cursor).toBe(0);
        expect(sent.daily_logs[0]).not.toHaveProperty('_dirty');
        expect(sent.daily_logs[0].weight_kg).toBe(75);
        expect(await pendingCount(db)).toBe(0);
        expect(await getMeta(db, 'cursor')).toBe(7);
    });

    it('a szinkron közben újra módosított dokumentum dirty marad', async () => {
        await saveLocal(db, 'daily_logs', { date: '2026-10-15', weight_kg: 75 });
        const api = stubApi(async () => {
            await new Promise((r) => setTimeout(r, 5));
            await saveLocal(db, 'daily_logs', { date: '2026-10-15', weight_kg: 74.8 });
            return { cursor: 2, applied: 1, stale: [], rejected: {}, changes: emptyChanges() };
        });
        await runSync(db, api);
        expect((await db.daily_logs.get('2026-10-15'))._dirty).toBe(1);
        expect((await db.daily_logs.get('2026-10-15')).weight_kg).toBe(74.8);
    });

    it('bejövő változás nem írja felül a helyben újabb, el nem küldött változatot', async () => {
        await db.sessions.put({ id: 's1', date: '2026-10-15', updated_at: '2026-10-15T12:00:00.000Z', _dirty: 1, entries: [], title: 'helyi' });
        await db.sessions.put({ id: 's2', date: '2026-10-14', updated_at: '2026-10-14T12:00:00.000Z', _dirty: 0, entries: [], title: 'régi' });
        const api = stubApi((body, call) => {
            // az első hívásban a helyi s1-et "elfelejtjük" elküldeni úgy, hogy a válasz előtt
            return {
                cursor: 10, applied: 0, stale: [], rejected: {},
                changes: { ...emptyChanges(), sessions: [
                    { id: 's1', date: '2026-10-15', updated_at: '2026-10-15T11:00:00.000Z', entries: [], title: 'szerver-régebbi' },
                    { id: 's2', date: '2026-10-14', updated_at: '2026-10-15T09:00:00.000Z', entries: [], title: 'szerver-új' },
                ] },
            };
        });
        // a push után a helyi s1 updated_at-je változatlan, így a dirty törlődne – ezért szimuláljuk, hogy közben módosult
        api.post = (orig => async (p, b) => { const r = await orig(p, b);
            await db.sessions.update('s1', { updated_at: '2026-10-15T12:30:00.000Z' }); return r; })(api.post);
        await runSync(db, api);
        expect((await db.sessions.get('s1')).title).toBe('helyi');
        expect((await db.sessions.get('s2')).title).toBe('szerver-új');
    });

    it('elutasított dokumentum hibával, programok és profil mentése', async () => {
        await saveLocal(db, 'pain_reports', { id: 'p1', date: '2026-10-15', intensity: 4, kind: 'dull' });
        const api = stubApi(() => ({
            cursor: 3, applied: 0, stale: [], rejected: { 'pain:p1': 'Ismeretlen izomcsoport: x' },
            changes: { ...emptyChanges(),
                programs: [{ week_id: '2026-W42', label: null, source: 'manual', days: {}, updated_at: 'x' }],
                user: { id: 1, name: 'teszt', gender: 'male' } },
        }));
        const result = await runSync(db, api);
        expect(result.rejected).toEqual({ 'pain:p1': 'Ismeretlen izomcsoport: x' });
        const p1 = await db.pain_reports.get('p1');
        expect(p1._dirty).toBe(0);
        expect(p1._error).toContain('Ismeretlen');
        expect(await db.programs.get('2026-W42')).toBeTruthy();
        expect((await getMeta(db, 'user')).name).toBe('teszt');
    });
});
