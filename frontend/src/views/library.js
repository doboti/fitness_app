import { formatShortHu } from '../domain/dates.js';
import { DIFFICULTY_LABEL } from '../domain/program.js';
import { exerciseHistory } from '../domain/stats.js';
import { allSessions } from '../store.js';
import { html, when } from '../ui.js';

const EQUIPMENT = { bodyweight: 'Saját testsúly', band: 'Gumiszalag', stand: 'Állvány', towel: 'Törölköző' };
const CHAINS = {
    push: 'Fekvőtámasz', core_static: 'Statikus törzs', core_lever: 'Törzsemelés', l_sit: 'L-ülés', squat: 'Guggolás',
    lunge: 'Kitörés', bridge: 'Farizomhíd', band_row: 'Szalagos evezés', band_curl: 'Szalagos bicepsz',
};
const FILTERS = [['all', 'Mind'], ['upper', 'Felsőtest'], ['core', 'Törzs'], ['lower', 'Alsótest'], ['rehab', 'Rehab']];

export async function render(ctx) {
    const filter = ctx.state.libraryFilter || 'all';
    const query = (ctx.state.librarySearch || '').trim().toLowerCase();
    const sessions = await allSessions(ctx);
    const chainMax = {};
    for (const ex of ctx.catalog.values()) if (ex.chain) chainMax[ex.chain] = Math.max(chainMax[ex.chain] || 0, ex.level);

    const matchesFilter = (ex) => {
        if (filter === 'all') return true;
        if (filter === 'rehab') return ex.rehab_suitable;
        const [primary] = Object.entries(ex.muscles).sort((a, b) => b[1] - a[1])[0];
        return ctx.muscles.get(primary)?.region === filter;
    };
    const exercises = [...ctx.catalog.values()]
        .filter(matchesFilter)
        .filter((ex) => !query || [ex.name_hu, ex.name_en, ...ex.aliases].some((n) => (n || '').toLowerCase().includes(query)))
        .sort((a, b) => (a.chain || 'zz').localeCompare(b.chain || 'zz') || (a.level || 0) - (b.level || 0)
            || a.name_hu.localeCompare(b.name_hu, 'hu'));

    if (!ctx.catalog.size) {
        return html`<div class="card text-sm text-slate-400">A gyakorlat-katalógus az első sikeres szinkronnál töltődik le.</div>`;
    }

    return html`
        <input type="search" class="input mb-3" placeholder="Keresés…" value="${ctx.state.librarySearch || ''}"
               data-key="library-search" data-input="library-search">
        <div class="flex flex-wrap gap-2 mb-4">
            ${FILTERS.map(([k, l]) => html`<button class="chip ${filter === k ? 'chip-active' : ''}" data-action="library-filter" data-value="${k}">${l}</button>`)}
        </div>
        <div class="grid md:grid-cols-2 gap-4">
            ${exercises.map((ex) => card(ctx, ex, chainMax, exerciseHistory(sessions, ex.id, 4)))}
        </div>
        ${when(!exercises.length, () => html`<p class="text-sm text-slate-500">Nincs találat.</p>`)}`;
}

function card(ctx, ex, chainMax, history) {
    const muscles = Object.entries(ex.muscles).sort((a, b) => b[1] - a[1]);
    return html`
        <div class="card">
            <div class="flex items-start justify-between gap-2">
                <div>
                    <h3 class="font-semibold text-lg leading-tight">${ex.name_hu}</h3>
                    ${when(ex.name_en && ex.name_en !== ex.name_hu, () => html`<div class="text-xs text-slate-500">${ex.name_en}</div>`)}
                </div>
                ${when(ex.rehab_suitable, () => html`<span class="badge bg-sky-500/15 text-sky-300 shrink-0">rehab</span>`)}
            </div>
            <div class="flex flex-wrap gap-1.5 mt-2 text-xs">
                <span class="badge bg-slate-700 text-slate-200">${EQUIPMENT[ex.equipment] || ex.equipment}</span>
                <span class="badge bg-slate-700 text-slate-200">${ex.measure === 'time' ? 'időre' : 'ismétlésre'}${ex.unilateral ? ' · oldalanként' : ''}</span>
                ${when(ex.chain, () => html`<span class="badge bg-primary/15 text-primary">${CHAINS[ex.chain] || ex.chain} ${ex.level}/${chainMax[ex.chain]}</span>`)}
            </div>
            <div class="mt-3 space-y-1">
                ${muscles.map(([code, w]) => html`
                    <div class="flex items-center gap-2 text-xs">
                        <span class="w-32 shrink-0 text-slate-400 truncate">${ctx.muscleName(code)}</span>
                        <div class="flex-1 h-1.5 rounded-full bg-slate-900"><div class="h-full rounded-full bg-primary" style="width:${w * 100}%"></div></div>
                    </div>`)}
            </div>
            ${when(ex.description, () => html`<p class="text-sm text-slate-300 mt-3 leading-relaxed">${ex.description}</p>`)}
            ${when(history.length, () => html`
                <div class="mt-3 border-t border-slate-700 pt-2 text-xs text-slate-400 space-y-0.5">
                    ${history.map((h) => html`<div class="flex justify-between">
                        <span>${formatShortHu(h.date)}</span>
                        <span>${h.sets}× ${h.best ? `${h.best} ${h.unit === 's' ? 'mp' : 'ism.'}` : ''}${h.band_kg ? ` · ${h.band_kg} kg` : ''}${h.difficulty ? ` · ${DIFFICULTY_LABEL[h.difficulty]}` : ''}</span>
                    </div>`)}
                </div>`)}
        </div>`;
}

export const actions = {
    'library-filter': (ctx, el) => {
        ctx.state.libraryFilter = el.dataset.value;
        return ctx.render();
    },
    'library-search': (ctx, el) => {
        ctx.state.librarySearch = el.value;
        return ctx.render();
    },
};
