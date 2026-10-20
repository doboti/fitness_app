import { monthTitle, parseDate, toDateStr, todayStr } from '../domain/dates.js';
import { sessionHasData } from '../domain/program.js';
import { activePainReports, allSessions, loadDailyMap } from '../store.js';
import { html } from '../ui.js';

const WEEKDAYS = ['H', 'K', 'Sze', 'Cs', 'P', 'Szo', 'V'];

export async function render(ctx) {
    const anchor = ctx.state.calendarMonth || ctx.state.date.slice(0, 7);
    const [year, month] = anchor.split('-').map(Number);
    const first = new Date(year, month - 1, 1);
    const daysInMonth = new Date(year, month, 0).getDate();
    const offset = (first.getDay() + 6) % 7;

    const daily = await loadDailyMap(ctx);
    const workoutDays = new Set((await allSessions(ctx)).filter(sessionHasData).map((s) => s.date));
    const painDays = new Set((await activePainReports(ctx)).map((p) => p.date));
    const today = todayStr();

    const cells = [];
    for (let i = 0; i < offset; i++) cells.push(html`<div></div>`);
    for (let d = 1; d <= daysInMonth; d++) {
        const date = toDateStr(new Date(year, month - 1, d));
        const classes = [
            'aspect-square rounded-xl flex flex-col items-center justify-center gap-1 text-sm transition',
            date === ctx.state.date ? 'bg-primary text-slate-900 font-bold' : 'bg-slate-800 hover:bg-slate-700',
            date === today && date !== ctx.state.date ? 'ring-2 ring-primary' : '',
        ].join(' ');
        cells.push(html`
            <button class="${classes}" data-action="calendar-pick" data-date="${date}">
                <span>${d}</span>
                <span class="flex gap-0.5 h-1.5">
                    ${workoutDays.has(date) ? html`<span class="sync-dot !w-1.5 !h-1.5 bg-primary ${date === ctx.state.date ? '!bg-slate-900' : ''}"></span>` : ''}
                    ${daily.get(date)?.weight_kg ? html`<span class="sync-dot !w-1.5 !h-1.5 bg-sky-400"></span>` : ''}
                    ${painDays.has(date) ? html`<span class="sync-dot !w-1.5 !h-1.5 bg-red-400"></span>` : ''}
                </span>
            </button>`);
    }

    return html`
        <div class="card">
            <div class="flex items-center justify-between mb-4">
                <button class="btn-secondary btn-sm" data-action="calendar-month" data-delta="-1">‹</button>
                <div class="font-semibold">${monthTitle(year, month - 1)}</div>
                <button class="btn-secondary btn-sm" data-action="calendar-month" data-delta="1">›</button>
            </div>
            <div class="grid grid-cols-7 gap-1.5 text-center text-xs text-slate-500 mb-1.5">${WEEKDAYS.map((w) => html`<div>${w}</div>`)}</div>
            <div class="grid grid-cols-7 gap-1.5">${cells}</div>
            <div class="flex flex-wrap gap-4 mt-4 text-xs text-slate-400">
                <span class="flex items-center gap-1.5"><span class="sync-dot bg-primary"></span>edzés</span>
                <span class="flex items-center gap-1.5"><span class="sync-dot bg-sky-400"></span>súly</span>
                <span class="flex items-center gap-1.5"><span class="sync-dot bg-red-400"></span>fájdalom</span>
                <button class="ml-auto text-primary" data-action="calendar-today">Ugrás a mai napra</button>
            </div>
        </div>`;
}

export const actions = {
    'calendar-month': (ctx, el) => {
        const anchor = ctx.state.calendarMonth || ctx.state.date.slice(0, 7);
        const d = parseDate(`${anchor}-01`);
        d.setMonth(d.getMonth() + Number(el.dataset.delta)); // 1-jén állítunk, így nincs hónap-átugrás
        ctx.state.calendarMonth = toDateStr(d).slice(0, 7);
        return ctx.render();
    },
    'calendar-today': (ctx) => {
        ctx.state.calendarMonth = null;
        return ctx.setDate(todayStr());
    },
    'calendar-pick': (ctx, el) => {
        ctx.state.date = el.dataset.date;
        ctx.state.calendarMonth = el.dataset.date.slice(0, 7);
        return ctx.navigate('dashboard');
    },
};
