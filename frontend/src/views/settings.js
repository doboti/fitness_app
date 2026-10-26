import { createApi } from '../api.js';
import { listAccounts, switchAccount } from '../accounts.js';
import { openProfile, profileLabel } from './login.js';
import { setMeta } from '../db.js';
import { html, parseNumber, when } from '../ui.js';

export async function render(ctx) {
    const user = ctx.user;
    const failed = [
        ...(await ctx.db.daily_logs.filter((d) => !!d._error).toArray()).map((d) => ({ label: `Napi napló ${d.date}`, error: d._error })),
        ...(await ctx.db.sessions.filter((d) => !!d._error).toArray()).map((d) => ({ label: `Edzés ${d.date}`, error: d._error })),
        ...(await ctx.db.pain_reports.filter((d) => !!d._error).toArray()).map((d) => ({ label: `Fájdalom ${d.date}`, error: d._error })),
    ];
    const programs = (await ctx.db.programs.toArray()).sort((a, b) => b.week_id.localeCompare(a.week_id));
    const profiles = await ctx.api.get('/api/profiles', { timeout: 3000 }).catch(() => []);
    const lastSync = ctx.state.lastSync ? new Date(ctx.state.lastSync).toLocaleString('hu-HU') : 'még nem volt';

    return html`
        <div class="card mb-4">
            <div class="card-title">Profilváltás</div>
            <select class="input" data-change="profile-switch" aria-label="Profil">
                ${profiles.length
        ? profiles.map((p) => html`<option value="${p.id}" ${p.id === ctx.account.uid ? 'selected' : ''}>${profileLabel(p)}</option>`)
        : html`<option>${ctx.user.name} (a profillistához kapcsolat kell)</option>`}
            </select>
            <p class="text-xs text-slate-500 mt-2">Mindkét profil adatai külön tárolódnak ezen az eszközön is, váltáskor nem vesznek el.</p>
        </div>

        <div class="card mb-4">
            <div class="card-title">Profil · ${user.name}</div>
            <div class="grid grid-cols-3 gap-3">
                <div><label class="label">Magasság (cm)</label><input type="number" class="input" id="pf-height" value="${user.height_cm ?? ''}"></div>
                <div><label class="label">Életkor</label><input type="number" class="input" id="pf-age" value="${user.age ?? ''}"></div>
                <div><label class="label">Célsúly (kg)</label><input type="number" step="0.1" class="input" id="pf-target" value="${user.target_weight_kg ?? ''}"></div>
            </div>
            <button class="btn-primary mt-3" data-action="profile-save">Profil mentése</button>
        </div>

        <div class="card mb-4">
            <div class="card-title">Szinkronizáció</div>
            <div class="grid grid-cols-2 gap-2 text-sm">
                <div class="text-slate-400">Utolsó szinkron</div><div>${lastSync}</div>
                <div class="text-slate-400">Küldésre vár</div><div>${ctx.state.pending} bejegyzés</div>
                <div class="text-slate-400">Állapot</div><div class="${ctx.state.syncError ? 'text-red-300' : 'text-primary'}">${ctx.state.syncError || 'rendben'}</div>
            </div>
            ${when(failed.length, () => html`
                <div class="mt-3 rounded-xl bg-red-500/10 border border-red-500/30 p-3 text-sm">
                    <div class="font-medium text-red-200 mb-1">A szerver által elutasított bejegyzések:</div>
                    ${failed.map((f) => html`<div class="text-red-200/80">${f.label}: ${f.error}</div>`)}
                </div>`)}
            <button class="btn-secondary mt-3" data-action="sync-now">Szinkron most</button>
        </div>

        <div class="card mb-4">
            <div class="card-title">Heti terv és régi adatok</div>
            <label class="btn-secondary w-full cursor-pointer">
                📅 Heti terv feltöltése (YYYY-WXX.json)
                <input type="file" accept=".json,application/json" class="hidden" data-change="upload-program">
            </label>
            <label class="btn-secondary w-full cursor-pointer mt-2">
                📦 Régi app exportjának betöltése
                <input type="file" accept=".json,application/json" class="hidden" data-change="upload-legacy">
            </label>
            <p class="text-xs text-slate-500 mt-2">Feltöltéshez internetkapcsolat kell. Ugyanaz a fájl újra feltölthető, felülírja önmagát.</p>
            ${when(programs.length, () => html`
                <div class="mt-3 text-sm text-slate-400">Betöltött hetek: ${programs.map((p) => p.week_id.split('-')[1]).join(', ')}</div>`)}
        </div>`;
}

async function readJsonFile(input) {
    const file = input.files?.[0];
    input.value = '';
    if (!file) return null;
    try {
        return JSON.parse(await file.text());
    } catch {
        throw new Error('A fájl nem érvényes JSON.');
    }
}

export const actions = {
    'profile-save': async (ctx) => {
        const num = (id) => parseNumber(document.getElementById(id).value);
        const user = await ctx.api.put('/api/me', { height_cm: num('pf-height'), age: num('pf-age'), target_weight_kg: num('pf-target') });
        ctx.user = user;
        await setMeta(ctx.db, 'user', user);
        ctx.toast('Profil mentve.');
        await ctx.render();
    },
    'upload-program': async (ctx, el) => {
        const data = await readJsonFile(el);
        if (!data) return;
        const program = await ctx.api.post('/api/programs', data);
        await ctx.syncNow();
        const unmatched = Object.values(program.days).flatMap((d) => d.exercises || []).filter((e) => !e.exercise_id).map((e) => e.name);
        ctx.toast(`Heti terv betöltve: ${program.week_id}${unmatched.length ? `\nNincs a katalógusban: ${unmatched.join(', ')}` : ''}`,
            unmatched.length ? 'warn' : 'success');
    },
    'upload-legacy': async (ctx, el) => {
        const data = await readJsonFile(el);
        if (!data) return;
        const report = await ctx.api.post('/api/import/legacy', data);
        await ctx.syncNow();
        const unmatched = Object.keys(report.unmatched_exercises || {});
        ctx.toast(`Betöltve: ${report.sessions} edzés, ${report.daily_logs} napi napló, ${report.programs} heti terv.`
            + (unmatched.length ? `\nNincs a katalógusban: ${unmatched.join(', ')}` : ''), unmatched.length ? 'warn' : 'success');
    },
    'profile-switch': async (ctx, el) => {
        const uid = Number(el.value);
        if (!uid || uid === ctx.account.uid) return;
        // ha ezen az eszközön már volt ez a profil és a kulcsa még érvényes, azt és a helyi adatait használjuk;
        // érvénytelen kulcsnál (pl. lecserélt szerver-adatbázis) új kulcsot kérünk ugyanahhoz a profilhoz
        const existing = listAccounts().find((a) => a.uid === uid);
        const valid = existing && await createApi(existing.token).get('/api/me').then(() => true, (e) => e.status !== 401);
        if (valid) switchAccount(uid);
        else await openProfile({ id: uid });
        location.reload();
    },
};

