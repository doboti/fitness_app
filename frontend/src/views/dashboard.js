import { bmi, bmiStatus, estimateBodyFat, weeklyWeights } from '../domain/body.js';
import { daysBetween, formatShortHu } from '../domain/dates.js';
import { PAIN_AREA_BY_KEY, PAIN_KINDS, isSeriousPain, restingMuscles } from '../domain/pain.js';
import { sessionProgress } from '../domain/program.js';
import { activePainReports, getDaily, loadDailyMap, loadSessionForDate, saveDaily } from '../store.js';
import { html, parseNumber, raw, when } from '../ui.js';

const WATER_TARGET_ML = 2500;
const TONE = { good: 'bg-emerald-500/15 text-emerald-300', warn: 'bg-amber-500/15 text-amber-300', bad: 'bg-red-500/15 text-red-300' };

export async function render(ctx) {
    const date = ctx.state.date;
    const user = ctx.user;
    const log = await getDaily(ctx, date);
    const dailyMap = await loadDailyMap(ctx);
    const { session, plan, isDraft } = await loadSessionForDate(ctx, date);
    const pains = await activePainReports(ctx);
    const openPains = pains.filter((p) => !p.resolved_at && p.date <= date).sort((a, b) => b.date.localeCompare(a.date));
    const resting = restingMuscles(pains, date);
    const week = weeklyWeights(dailyMap, date);

    const bmiValue = bmi(log.weight_kg, user.height_cm);
    const fat = log.weight_kg ? estimateBodyFat(log, user) : null;
    const weights = [...dailyMap.values()].filter((d) => d.weight_kg).sort((a, b) => a.date.localeCompare(b.date));
    const startWeight = weights[0]?.weight_kg;
    const latestWeight = weights.filter((d) => d.date <= date).at(-1)?.weight_kg;
    const progress = sessionProgress(session);
    const water = log.water_ml || 0;
    const trend = week.average != null && week.previousAverage != null ? Math.round((week.average - week.previousAverage) * 100) / 100 : null;

    return html`
        ${when(openPains.length, () => painCard(ctx, openPains, date))}

        <div class="card mb-4">
            <div class="flex items-center justify-between mb-2">
                <div class="card-title mb-0">Mai edzés</div>
                ${when(!isDraft || progress.done, () => html`<span class="text-sm text-slate-400">${progress.done}/${progress.total} kész</span>`)}
            </div>
            <div class="text-lg font-semibold">
                ${plan.isRestDay && isDraft ? '🌴 Pihenőnap' : session.title || (plan.day ? plan.day.name : 'Nincs betöltött terv')}
            </div>
            ${when(progress.total, () => html`<div class="progress mt-3"><div style="width:${(100 * progress.done) / progress.total}%"></div></div>`)}
            ${when(resting.size, () => html`<p class="text-sm text-amber-300 mt-2">⚠️ Pihentetendő: ${[...resting.keys()].map(ctx.muscleName).join(', ')}</p>`)}
            ${when(session.cardio_distance_km, () => html`<p class="text-sm text-slate-400 mt-2">🏃 ${session.cardio_distance_km} km</p>`)}
            <button class="btn-primary w-full mt-4" data-action="nav" data-view="workout">Edzés megnyitása</button>
        </div>

        <div class="grid md:grid-cols-2 gap-4 mb-4">
            <div class="card">
                <div class="card-title">Testsúly és méretek</div>
                <div class="flex items-baseline gap-2 mb-3">
                    <div class="text-3xl font-bold text-primary">${log.weight_kg ?? '--'}</div><div class="text-slate-400">kg</div>
                </div>
                <div class="grid grid-cols-2 gap-2">
                    <div class="col-span-2"><label class="label">Súly (kg)</label>
                        <input type="number" inputmode="decimal" step="0.05" class="input" data-key="weight" id="in-weight" value="${log.weight_kg ?? ''}"></div>
                    <div><label class="label">Nyak (cm)</label>
                        <input type="number" inputmode="decimal" step="0.5" class="input" data-key="neck" id="in-neck" value="${log.neck_cm ?? ''}"></div>
                    <div><label class="label">Derék (cm)</label>
                        <input type="number" inputmode="decimal" step="0.5" class="input" data-key="waist" id="in-waist" value="${log.waist_cm ?? ''}"></div>
                    ${when(user.gender === 'female', () => html`
                        <div class="col-span-2"><label class="label">Csípő (cm)</label>
                            <input type="number" inputmode="decimal" step="0.5" class="input" data-key="hip" id="in-hip" value="${log.hip_cm ?? ''}"></div>`)}
                </div>
                <button class="btn-primary w-full mt-3" data-action="save-weight">Mentés</button>
            </div>

            <div class="card">
                <div class="card-title">Testösszetétel</div>
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <div class="text-xs text-slate-400">BMI</div>
                        <div class="text-2xl font-bold">${bmiValue ?? '--'}</div>
                        ${when(bmiValue, () => html`<span class="badge ${TONE[bmiStatus(bmiValue).tone]}">${bmiStatus(bmiValue).label}</span>`)}
                    </div>
                    <div>
                        <div class="text-xs text-slate-400">Testzsír</div>
                        <div class="text-2xl font-bold text-primary">${fat ? `${fat.value}%` : '--'}</div>
                        <div class="text-xs text-slate-500">${fat?.method ?? ''}</div>
                    </div>
                </div>
                <div class="border-t border-slate-700 mt-4 pt-4 grid grid-cols-3 gap-2 text-center">
                    <div><div class="text-xs text-slate-400">Kezdő</div><div class="font-semibold">${startWeight ?? '--'} kg</div></div>
                    <div><div class="text-xs text-slate-400">Cél</div><div class="font-semibold text-primary">${user.target_weight_kg ?? '--'} kg</div></div>
                    <div><div class="text-xs text-slate-400">Változás</div><div class="font-semibold">
                        ${startWeight && latestWeight ? `${latestWeight - startWeight > 0 ? '+' : ''}${(latestWeight - startWeight).toFixed(1)} kg` : '--'}</div></div>
                </div>
            </div>
        </div>

        <div class="card mb-4">
            <div class="flex items-start justify-between gap-4">
                <div>
                    <div class="card-title">Heti átlagsúly · ${week.weekId}</div>
                    <div class="flex items-baseline gap-3">
                        <div class="text-3xl font-bold text-primary">${week.average ?? '--'} <span class="text-base text-slate-400">kg</span></div>
                        ${when(trend !== null, () => html`
                            <span class="text-sm ${trend < 0 ? 'text-primary' : trend > 0 ? 'text-red-400' : 'text-slate-400'}">
                                ${trend < 0 ? '▼' : trend > 0 ? '▲' : '±'} ${Math.abs(trend).toFixed(2)} kg</span>`)}
                    </div>
                </div>
            </div>
            ${weekChart(week)}
        </div>

        <div class="card">
            <div class="card-title">Folyadék</div>
            <div class="flex items-baseline gap-2"><div class="text-3xl font-bold text-sky-400">${water}</div><div class="text-slate-400">/ ${WATER_TARGET_ML} ml</div></div>
            <div class="progress mt-3"><div class="!bg-sky-400" style="width:${Math.min(100, (100 * water) / WATER_TARGET_ML)}%"></div></div>
            <div class="grid grid-cols-3 gap-2 mt-3">
                <button class="btn-secondary" data-action="water" data-amount="250">+250</button>
                <button class="btn-secondary" data-action="water" data-amount="500">+500</button>
                <button class="btn-ghost" data-action="water" data-amount="reset">Nullázás</button>
            </div>
        </div>`;
}

function painCard(ctx, pains, date) {
    const kindLabel = (k) => PAIN_KINDS.find((x) => x.key === k)?.label || k;
    return html`
        <div class="card mb-4 border-amber-500/40">
            <div class="flex items-center justify-between">
                <div class="card-title mb-2 text-amber-300">🩹 Aktív panaszok</div>
                <button class="btn-ghost btn-sm" data-action="pain-new">+ új</button>
            </div>
            <div class="space-y-2">
                ${pains.map((p) => html`
                    <div class="flex items-center gap-3 rounded-xl bg-slate-900 p-3">
                        <div class="flex-1 min-w-0">
                            <div class="font-medium">${PAIN_AREA_BY_KEY.get(p.body_area)?.label || ctx.muscleName(p.muscle_code)}
                                ${p.side ? html`<span class="text-slate-400 text-sm">(${{ left: 'bal', right: 'jobb', both: 'mindkét oldal' }[p.side]})</span>` : ''}</div>
                            <div class="text-xs ${isSeriousPain(p) ? 'text-red-300' : 'text-slate-400'}">
                                ${kindLabel(p.kind)} · ${p.intensity}/10 · ${formatShortHu(p.date)} (${daysBetween(p.date, date)} napja)
                            </div>
                        </div>
                        <button class="btn-secondary btn-sm" data-action="pain-resolve" data-id="${p.id}">Elmúlt</button>
                    </div>`)}
            </div>
        </div>`;
}

function weekChart(week) {
    const width = 320;
    const height = 110;
    const pad = 22;
    const labels = ['H', 'K', 'Sze', 'Cs', 'P', 'Szo', 'V'];
    const values = week.days.filter((v) => v != null);
    const x = (i) => pad + (i * (width - 2 * pad)) / 6;
    if (!values.length) {
        return html`<p class="text-sm text-slate-500 mt-4">Ezen a héten még nincs súlyadat.</p>`;
    }
    const lo = Math.floor(Math.min(...values) - 0.5);
    const hi = Math.ceil(Math.max(...values) + 0.5);
    const y = (v) => height - pad - ((v - lo) / (hi - lo || 1)) * (height - 2 * pad);

    let path = '';
    let pen = false;
    week.days.forEach((v, i) => {
        if (v == null) { pen = false; return; }
        path += `${pen ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)} `;
        pen = true;
    });
    const avgY = y(week.average).toFixed(1);
    // Csak számokból és fix szövegből épül, ezért raw-ként beilleszthető.
    return raw(`
        <svg viewBox="0 0 ${width} ${height}" class="w-full h-28 mt-3" role="img" aria-label="Heti súlygrafikon">
            <line x1="${pad}" x2="${width - pad}" y1="${avgY}" y2="${avgY}" stroke="#64748b" stroke-dasharray="4 4" stroke-width="1"/>
            <path d="${path}" fill="none" stroke="rgb(var(--primary))" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            ${week.days.map((v, i) => (v == null ? '' : `<circle cx="${x(i)}" cy="${y(v)}" r="4" fill="#0f172a" stroke="rgb(var(--primary))" stroke-width="2"><title>${v} kg</title></circle>`)).join('')}
            ${labels.map((l, i) => `<text x="${x(i)}" y="${height - 4}" fill="#94a3b8" font-size="10" text-anchor="middle">${l}</text>`).join('')}
        </svg>`);
}

const readNum = (id) => parseNumber(document.getElementById(id)?.value) || null;

export const actions = {
    'save-weight': async (ctx) => {
        const weight = readNum('in-weight');
        if (!weight || weight < 25 || weight > 300) {
            ctx.toast('Adj meg egy érvényes súlyt.', 'error');
            return;
        }
        const log = await getDaily(ctx, ctx.state.date);
        const updated = { ...log, weight_kg: weight, neck_cm: readNum('in-neck'), waist_cm: readNum('in-waist') };
        if (ctx.user.gender === 'female') updated.hip_cm = readNum('in-hip');
        updated.body_fat_pct = estimateBodyFat(updated, ctx.user)?.value ?? null;
        await saveDaily(ctx, updated);
        ctx.toast(`Mentve: ${weight} kg${updated.body_fat_pct ? ` · testzsír ${updated.body_fat_pct}%` : ''}`);
        await ctx.render();
    },
    water: async (ctx, el) => {
        const log = await getDaily(ctx, ctx.state.date);
        const amount = el.dataset.amount;
        await saveDaily(ctx, { ...log, water_ml: amount === 'reset' ? 0 : (log.water_ml || 0) + Number(amount) });
        await ctx.render();
    },
};
