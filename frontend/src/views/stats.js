import { formatShortHu, todayStr } from '../domain/dates.js';
import { PAIN_AREA_BY_KEY } from '../domain/pain.js';
import { WEEKLY_SET_TARGET, weeklyMuscleSets } from '../domain/stats.js';
import { activePainReports, allSessions } from '../store.js';
import { html, when } from '../ui.js';
import { planCard } from './plan.js';

const REGIONS = [['upper', 'Felsőtest'], ['core', 'Törzs'], ['lower', 'Alsótest']];

function cellTone(value) {
    if (value === 0) return 'bg-slate-900 text-slate-600';
    if (value < WEEKLY_SET_TARGET.min / 2) return 'bg-amber-500/10 text-amber-300';
    if (value < WEEKLY_SET_TARGET.min) return 'bg-amber-500/20 text-amber-200';
    if (value <= WEEKLY_SET_TARGET.max) return 'bg-primary/25 text-primary';
    return 'bg-sky-500/25 text-sky-200';
}

export async function render(ctx) {
    const weeks = ctx.state.statsWeeks || (window.innerWidth < 640 ? 4 : 6);
    const result = weeklyMuscleSets(await allSessions(ctx), ctx.catalog, weeks, todayStr());
    const pains = (await activePainReports(ctx)).sort((a, b) => b.date.localeCompare(a.date)).slice(0, 10);
    const muscles = [...ctx.muscles.values()];

    const rows = (region) => muscles.filter((m) => m.region === region).map((m) => {
        const values = result.muscles[m.code] || Array(weeks).fill(0);
        const avg = Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 10) / 10;
        return html`
            <tr>
                <td class="py-1 pr-2 text-sm whitespace-nowrap">${m.name_hu}</td>
                ${values.map((v) => html`<td class="p-0.5"><div class="rounded-md text-center text-xs py-1.5 ${cellTone(v)}">${v || '·'}</div></td>`)}
                <td class="pl-2 text-sm font-semibold text-right ${avg < WEEKLY_SET_TARGET.min ? 'text-amber-300' : 'text-primary'}">${avg}</td>
            </tr>`;
    });

    return html`
        ${planCard(ctx)}
        <div class="card mb-4">
            <div class="flex items-center justify-between gap-2 mb-1">
                <div class="card-title mb-0">Heti terhelés izomcsoportonként</div>
                <div class="flex gap-1">
                    ${[4, 6, 12].map((w) => html`<button class="chip !py-1 ${w === weeks ? 'chip-active' : ''}" data-action="stats-weeks" data-weeks="${w}">${w} hét</button>`)}
                </div>
            </div>
            <p class="text-xs text-slate-500 mb-3">
                Súlyozott sorozatszám (sorozat × izomszorzó). Ajánlott: ${WEEKLY_SET_TARGET.min}–${WEEKLY_SET_TARGET.max}/hét izomcsoportonként.
                A futás még nem számít bele.
            </p>
            <div class="overflow-x-auto -mx-1">
                <table class="w-full border-separate border-spacing-0">
                    <thead><tr>
                        <th></th>
                        ${result.weeks.map((w) => html`<th class="text-[10px] font-normal text-slate-500 px-0.5">${w.split('-')[1]}</th>`)}
                        <th class="text-[10px] font-normal text-slate-500 text-right">átl.</th>
                    </tr></thead>
                    ${REGIONS.map(([key, label]) => html`
                        <tbody>
                            <tr><td colspan="${weeks + 2}" class="pt-3 pb-1 text-xs uppercase tracking-wide text-slate-500">${label}</td></tr>
                            ${rows(key)}
                        </tbody>`)}
                </table>
            </div>
            ${when(result.unmatched, () => html`<p class="text-xs text-slate-500 mt-3">${result.unmatched} gyakorlat nincs a katalógusban, ezért nem számít bele.</p>`)}
        </div>

        <div class="card">
            <div class="flex items-center justify-between">
                <div class="card-title">Fájdalomnapló</div>
                <button class="btn-ghost btn-sm" data-action="pain-new">+ új</button>
            </div>
            ${pains.length ? html`
                <div class="space-y-2">${pains.map((p) => html`
                    <div class="flex items-center justify-between rounded-xl bg-slate-900 px-3 py-2 text-sm">
                        <span>${PAIN_AREA_BY_KEY.get(p.body_area)?.label || ctx.muscleName(p.muscle_code)} · ${p.intensity}/10</span>
                        <span class="text-slate-500">${formatShortHu(p.date)}${p.resolved_at ? ' · elmúlt' : ''}</span>
                    </div>`)}</div>`
        : html`<p class="text-sm text-slate-500">Nincs rögzített fájdalom. 🎉</p>`}
        </div>`;
}

export const actions = {
    'stats-weeks': (ctx, el) => {
        ctx.state.statsWeeks = Number(el.dataset.weeks);
        return ctx.render();
    },
};
