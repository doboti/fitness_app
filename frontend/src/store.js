// A nézetek közös adatelérése: olvasás a helyi DB-ből, írás saveLocal-lal + szinkron ütemezése.
import { buildSession, programForDate, sessionIdFor } from './domain/program.js';
import { saveLocal } from './sync.js';

export async function loadPrograms(ctx) {
    return new Map((await ctx.db.programs.toArray()).map((p) => [p.week_id, p]));
}

export async function loadDailyMap(ctx) {
    return new Map((await ctx.db.daily_logs.toArray()).filter((d) => !d.deleted).map((d) => [d.date, d]));
}

export async function getDaily(ctx, date) {
    const log = await ctx.db.daily_logs.get(date);
    return log && !log.deleted ? log : { date, deleted: false };
}

export async function saveDaily(ctx, log) {
    await saveLocal(ctx.db, 'daily_logs', { deleted: false, ...log });
    ctx.scheduleSync();
}

export async function activePainReports(ctx) {
    return (await ctx.db.pain_reports.toArray()).filter((p) => !p.deleted);
}

export async function savePain(ctx, report) {
    await saveLocal(ctx.db, 'pain_reports', { deleted: false, ...report });
    ctx.scheduleSync();
}

/**
 * A nap edzése: a meglévő (akár régi importból származó) edzés, vagy a tervből felépített piszkozat.
 * A piszkozat csak az első módosításkor kerül az adatbázisba (saveSession).
 */
export async function loadSessionForDate(ctx, date) {
    const sessions = (await ctx.db.sessions.where('date').equals(date).toArray()).filter((s) => !s.deleted);
    const ownId = sessionIdFor(ctx.account.uid, date);
    const existing = sessions.find((s) => s.id === ownId) || sessions[0];
    const plan = programForDate(await loadPrograms(ctx), date);
    if (existing) return { session: existing, plan, isDraft: false };
    return { session: buildSession({ uid: ctx.account.uid, dateStr: date, plan, catalog: ctx.catalog }), plan, isDraft: true };
}

export async function saveSession(ctx, session) {
    const saved = await saveLocal(ctx.db, 'sessions', session);
    ctx.scheduleSync();
    return saved;
}

export async function allSessions(ctx) {
    return (await ctx.db.sessions.toArray()).filter((s) => !s.deleted);
}
