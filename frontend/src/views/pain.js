import { PAIN_AREAS, PAIN_AREA_BY_KEY, PAIN_KINDS, isSeriousPain, restDays } from '../domain/pain.js';
import { todayStr } from '../domain/dates.js';
import { savePain } from '../store.js';
import { html, openModal, when } from '../ui.js';

let draft = null;

/** Ha a gyakorlatnál jelzi, a gyakorlat fő izmához tartozó területet ajánljuk fel elsőként. */
function suggestedArea(ctx, exerciseId) {
    const exercise = ctx.catalog.get(exerciseId);
    if (!exercise) return null;
    const [muscle] = Object.entries(exercise.muscles).sort((a, b) => b[1] - a[1])[0] || [];
    return PAIN_AREAS.find((a) => a.muscle === muscle)?.key || null;
}

export function openPainModal(ctx, { sessionId = null, exerciseId = null, exerciseName = null, note = null } = {}) {
    draft = {
        id: crypto.randomUUID(),
        date: ctx.state.date,
        session_id: sessionId,
        exercise_id: exerciseId,
        body_area: suggestedArea(ctx, exerciseId),
        side: null,
        intensity: 4,
        kind: 'dull',
        note,
        resolved_at: null,
        exerciseName,
    };
    renderModal();
}

function renderModal() {
    const groups = [...new Set(PAIN_AREAS.map((a) => a.group))];
    openModal(html`
        <div class="flex items-center justify-between mb-1">
            <h2 class="text-lg font-bold">🩹 Fájdalom rögzítése</h2>
            <button class="btn-ghost btn-sm" data-action="modal-close" aria-label="Bezárás">✕</button>
        </div>
        ${when(draft.exerciseName, () => html`<p class="text-sm text-slate-400 mb-3">Gyakorlat: ${draft.exerciseName}</p>`)}

        <div class="label mt-3">Hol?</div>
        ${groups.map((g) => html`
            <div class="text-[11px] uppercase tracking-wide text-slate-500 mt-2 mb-1">${g}</div>
            <div class="flex flex-wrap gap-1.5">
                ${PAIN_AREAS.filter((a) => a.group === g).map((a) => html`
                    <button class="chip ${draft.body_area === a.key ? 'chip-active' : ''}" data-action="pain-set"
                            data-field="body_area" data-value="${a.key}">${a.label}</button>`)}
            </div>`)}

        <div class="label mt-4">Melyik oldal?</div>
        <div class="flex gap-2">
            ${[['left', 'Bal'], ['right', 'Jobb'], ['both', 'Mindkettő']].map(([k, l]) => html`
                <button class="chip ${draft.side === k ? 'chip-active' : ''}" data-action="pain-set" data-field="side" data-value="${k}">${l}</button>`)}
        </div>

        <div class="label mt-4">Jellege</div>
        <div class="flex flex-wrap gap-2">
            ${PAIN_KINDS.map((k) => html`
                <button class="chip ${draft.kind === k.key ? 'chip-active' : ''}" data-action="pain-set" data-field="kind" data-value="${k.key}">${k.label}</button>`)}
        </div>

        <div class="label mt-4">Erősség: <b class="text-slate-100" id="pain-intensity-label">${draft.intensity}</b> / 10</div>
        <input type="range" min="0" max="10" step="1" value="${draft.intensity}" class="w-full accent-[rgb(var(--primary))]"
               data-input="pain-intensity" aria-label="Fájdalom erőssége">

        <label class="label mt-4">Megjegyzés</label>
        <textarea class="input" rows="2" data-input="pain-note" placeholder="Mikor jelentkezett, mitől rosszabb?">${draft.note ?? ''}</textarea>

        ${when(isSeriousPain(draft), () => html`
            <div class="rounded-xl bg-red-500/10 border border-red-500/40 text-red-200 text-sm p-3 mt-4">
                Éles vagy erős fájdalomnál hagyd abba a gyakorlatot. Ha néhány nap alatt nem javul, duzzanat vagy
                zsibbadás is van, fordulj orvoshoz vagy gyógytornászhoz.
            </div>`)}

        <button class="btn-primary w-full mt-5" data-action="pain-save" ${draft.body_area ? '' : 'disabled'}>Mentés</button>
    `);
}

export const actions = {
    'pain-set': (ctx, el) => {
        draft[el.dataset.field] = draft[el.dataset.field] === el.dataset.value && el.dataset.field === 'side'
            ? null : el.dataset.value;
        renderModal();
    },
    'pain-intensity': (ctx, el) => {
        const wasSerious = isSeriousPain(draft);
        draft.intensity = Number(el.value);
        document.getElementById('pain-intensity-label').textContent = draft.intensity;
        if (wasSerious !== isSeriousPain(draft)) renderModal();
    },
    'pain-note': (ctx, el) => { draft.note = el.value; },
    'pain-save': async (ctx) => {
        const area = PAIN_AREA_BY_KEY.get(draft.body_area);
        const { exerciseName, ...report } = draft;
        await savePain(ctx, { ...report, muscle_code: area.muscle, note: (report.note || '').trim() || null });
        ctx.closeModal();
        const muscles = area.rest.map(ctx.muscleName).join(', ');
        ctx.toast(`Rögzítve. ${restDays(report)} napig kíméljük: ${muscles}.`, isSeriousPain(report) ? 'warn' : 'success');
        draft = null;
        await ctx.render();
    },
    'pain-resolve': async (ctx, el) => {
        const report = await ctx.db.pain_reports.get(el.dataset.id);
        if (!report) return;
        await savePain(ctx, { ...report, resolved_at: todayStr() });
        ctx.toast('Megjelölve: elmúlt. 👍');
        await ctx.render();
    },
    'pain-new': (ctx) => openPainModal(ctx),
};
