import { analyzeComment, restConflicts, restingMuscles } from '../domain/pain.js';
import { DIFFICULTIES, DIFFICULTY_LABEL, describeTarget, entryFromCatalog, plannedSetCount, sessionProgress, targetValue } from '../domain/program.js';
import { exerciseHistory } from '../domain/stats.js';
import { formatShortHu } from '../domain/dates.js';
import { activePainReports, allSessions, loadSessionForDate, saveSession } from '../store.js';
import { html, parseNumber, when } from '../ui.js';
import { openPainModal } from './pain.js';

const DIFFICULTY_FROM_COMMENT = { easy: 'easy', hard: 'hard' };

export async function render(ctx) {
    const { session, plan, isDraft } = await loadSessionForDate(ctx, ctx.state.date);
    const resting = restingMuscles(await activePainReports(ctx), ctx.state.date);
    const earlier = (await allSessions(ctx)).filter((s) => s.date < ctx.state.date);
    const lastOf = (entry) => (entry.exercise_id ? exerciseHistory(earlier, entry.exercise_id, 1)[0] : null);
    const entries = session.entries.map((e, i) => ({ e, i })).filter(({ e }) => !e.archived);
    const progress = sessionProgress(session);

    let header;
    if (session.entries.length || !isDraft) {
        header = html`
            <div class="card mb-4">
                <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                        <h2 class="text-xl font-bold text-primary">${session.title || 'Edzés'}</h2>
                        <div class="text-sm text-slate-400">
                            ${plan.week?.label || session.program_week_id || ''}${plan.day?.circuits ? ` · ${plan.day.circuits} kör` : ''}
                        </div>
                    </div>
                    <div class="text-right shrink-0">
                        <div class="text-2xl font-bold">${progress.done}/${progress.total}</div>
                        <div class="text-xs text-slate-500">gyakorlat kész</div>
                    </div>
                </div>
                <div class="progress mt-3"><div style="width:${progress.total ? (100 * progress.done) / progress.total : 0}%"></div></div>
            </div>`;
    } else if (plan.isRestDay) {
        header = html`
            <div class="card mb-4 text-center py-8">
                <div class="text-4xl mb-2">🌴</div>
                <h2 class="text-xl font-bold">Pihenőnap</h2>
                <p class="text-slate-400 text-sm mt-1">Aktív regeneráció. Rehab gyakorlatot lent hozzáadhatsz.</p>
            </div>`;
    } else {
        header = html`
            <div class="card mb-4">
                <h2 class="text-lg font-bold mb-1">Nincs terv erre a napra</h2>
                <p class="text-sm text-slate-400">
                    ${plan.weekId} hétre nincs betöltött terv. Feltöltheted a Beállításokban, vagy lent szabad edzést rögzíthetsz.
                </p>
            </div>`;
    }

    const restBanner = resting.size ? html`
        <div class="rounded-2xl border border-amber-500/40 bg-amber-500/10 p-3 mb-4 text-sm text-amber-200">
            ⚠️ Pihentetendő: <b>${[...resting.keys()].map(ctx.muscleName).join(', ')}</b>.
            Az ezeket erősen terhelő gyakorlatokat jelöltük – hagyd ki vagy cseréld rehab gyakorlatra.
        </div>` : '';

    return html`
        ${header}
        ${restBanner}
        <div class="space-y-4">${entries.map(({ e, i }) => entryCard(ctx, e, i, resting, lastOf(e)))}</div>
        ${addExerciseCard(ctx)}
        ${cardioCard(session)}`;
}

function lastLine(last) {
    if (!last) return '';
    const unit = last.unit === 's' ? 'mp' : 'ism.';
    const result = last.values.length ? `${last.values.join(' · ')} ${unit}` : `${last.sets} sorozat`;
    return html`<div class="text-xs text-slate-500 mt-1">Legutóbb (${formatShortHu(last.date)}): ${result}${last.band_kg ? ` · ${last.band_kg} kg` : ''}${last.difficulty ? ` · ${DIFFICULTY_LABEL[last.difficulty]}` : ''}</div>`;
}

function entryCard(ctx, entry, i, resting, last) {
    const exercise = ctx.catalog.get(entry.exercise_id);
    const name = exercise?.name_hu || entry.name_raw;
    const conflicts = restConflicts(entry, exercise, resting);
    const planned = plannedSetCount(entry);
    const unit = entry.presc_unit === 's' ? 'mp' : 'ism.';
    const target = targetValue(entry);
    const showBand = exercise?.equipment === 'band' || entry.band_kg != null;
    const mainMuscles = exercise
        ? Object.entries(exercise.muscles).filter(([, w]) => w >= 0.5).sort((a, b) => b[1] - a[1]).map(([m]) => ctx.muscleName(m))
        : [];
    const isAdHoc = !entry.target_raw;

    const setRows = Array.from({ length: planned }, (_, j) => {
        const set = entry.sets.find((s) => s.set_no === j + 1);
        const value = set ? (set.reps ?? set.duration_s ?? '') : '';
        return html`
            <div class="flex items-center gap-2">
                <span class="w-6 text-sm text-slate-500">${j + 1}.</span>
                <input type="number" inputmode="numeric" min="0" class="input py-2 text-center" value="${value}"
                       placeholder="${target ?? 'max'}" data-key="set-${i}-${j}" data-change="set-value"
                       data-entry="${i}" data-set="${j}" aria-label="${j + 1}. sorozat">
                <span class="w-14 text-xs text-slate-500">${unit}${entry.presc_per_side ? '/old.' : ''}</span>
                <button class="set-btn ${set ? 'done' : ''}" data-action="toggle-set" data-entry="${i}" data-set="${j}"
                        aria-label="${j + 1}. sorozat kész">✓</button>
            </div>`;
    });

    return html`
        <div class="card ${entry.completed ? 'border-primary/50' : ''}" data-entry-card="${i}">
            <div class="flex items-start gap-3 mb-3">
                <div class="min-w-0 flex-1">
                    <h3 class="font-semibold text-lg leading-tight ${entry.completed ? 'text-primary' : ''}">
                        ${entry.completed ? '✓ ' : ''}${name}
                    </h3>
                    ${when(entry.target_raw, () => html`<div class="text-sm text-slate-400 mt-0.5">${entry.target_raw}</div>`)}
                    ${lastLine(last)}
                    <div class="flex flex-wrap gap-1.5 mt-2">
                        ${when(describeTarget(entry), () => html`<span class="badge bg-slate-700 text-slate-200">${entry.presc_sets || planned}× ${describeTarget(entry)}</span>`)}
                        ${mainMuscles.map((m) => html`<span class="badge bg-slate-900 text-slate-400">${m}</span>`)}
                        ${when(entry.is_rehab, () => html`<span class="badge bg-sky-500/15 text-sky-300">rehab</span>`)}
                        ${when(!exercise, () => html`<span class="badge bg-slate-900 text-slate-500">nincs a katalógusban</span>`)}
                    </div>
                </div>
                ${when(isAdHoc, () => html`<button class="btn-ghost btn-sm" data-action="remove-entry" data-entry="${i}" aria-label="Eltávolítás">✕</button>`)}
            </div>

            ${when(conflicts.length, () => html`
                <div class="rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-sm p-2.5 mb-3">
                    ⚠️ Pihentetendő izmot terhel: ${conflicts.map(ctx.muscleName).join(', ')}
                </div>`)}

            <div class="space-y-2">${setRows}</div>
            <div class="flex flex-wrap gap-2 mt-2">
                <button class="btn-secondary btn-sm" data-action="all-sets" data-entry="${i}">Mind kész a cél szerint</button>
                <button class="btn-ghost btn-sm" data-action="add-set" data-entry="${i}">+ sorozat</button>
                ${when(showBand, () => html`
                    <label class="flex items-center gap-1 text-sm text-slate-400 ml-auto">Szalag
                        <input type="number" inputmode="decimal" step="0.25" class="input py-1.5 w-20 text-center"
                               value="${entry.band_kg ?? ''}" data-key="band-${i}" data-change="entry-band" data-entry="${i}"> kg
                    </label>`)}
            </div>

            <div class="mt-4">
                <div class="label">Milyen volt?</div>
                <div class="flex flex-wrap gap-2">
                    ${DIFFICULTIES.map((d) => html`
                        <button class="chip chip-${d.key} ${entry.difficulty === d.key ? 'chip-active' : ''}"
                                data-action="difficulty" data-entry="${i}" data-value="${d.key}">${d.label}</button>`)}
                </div>
            </div>

            <div class="mt-3 flex gap-2">
                <input type="text" class="input" placeholder="Megjegyzés (pl. fájt a térdem, könnyű volt)"
                       value="${entry.comment ?? ''}" data-key="comment-${i}" data-change="entry-comment" data-entry="${i}">
                <button class="btn-secondary shrink-0" data-action="open-pain" data-entry="${i}" title="Fájdalom rögzítése">🩹</button>
            </div>
            <div class="mt-2">
                <button class="text-xs ${entry.is_rehab ? 'text-sky-300' : 'text-slate-500'}" data-action="toggle-rehab" data-entry="${i}">
                    ${entry.is_rehab ? '✓ Rehab gyakorlat (nem nehezítjük)' : 'Megjelölés rehab gyakorlatként'}
                </button>
            </div>
        </div>`;
}

function addExerciseCard(ctx) {
    const exercises = [...ctx.catalog.values()].sort((a, b) => a.name_hu.localeCompare(b.name_hu, 'hu'));
    const rehab = exercises.filter((e) => e.rehab_suitable);
    return html`
        <div class="card mt-4">
            <div class="card-title">Gyakorlat hozzáadása</div>
            <select class="input" data-change="add-exercise" aria-label="Gyakorlat hozzáadása">
                <option value="">Válassz gyakorlatot…</option>
                <optgroup label="Rehab / kímélő">${rehab.map((e) => html`<option value="${e.id}">${e.name_hu}</option>`)}</optgroup>
                <optgroup label="Összes">${exercises.map((e) => html`<option value="${e.id}">${e.name_hu}</option>`)}</optgroup>
            </select>
        </div>`;
}

function pace(distance, minutes) {
    if (!(distance > 0 && minutes > 0)) return '--';
    const p = minutes / distance;
    let min = Math.floor(p);
    let sec = Math.round((p - min) * 60);
    if (sec === 60) { min += 1; sec = 0; }
    return `${min}:${String(sec).padStart(2, '0')} /km`;
}

function cardioCard(session) {
    return html`
        <div class="card mt-4">
            <div class="card-title">🏃 Kardió</div>
            <div class="grid grid-cols-3 gap-3">
                <div><label class="label">Táv (km)</label>
                    <input type="number" inputmode="decimal" step="0.1" class="input" value="${session.cardio_distance_km ?? ''}"
                           data-key="cardio-distance" data-change="cardio" data-field="cardio_distance_km"></div>
                <div><label class="label">Idő (perc)</label>
                    <input type="number" inputmode="decimal" class="input" value="${session.cardio_duration_min ?? ''}"
                           data-key="cardio-duration" data-change="cardio" data-field="cardio_duration_min"></div>
                <div><label class="label">Tempó</label>
                    <div class="py-2.5 font-bold text-primary">${pace(session.cardio_distance_km, session.cardio_duration_min)}</div></div>
            </div>
            <input type="text" class="input mt-3" placeholder="Megjegyzés" value="${session.cardio_notes ?? ''}"
                   data-key="cardio-notes" data-change="cardio" data-field="cardio_notes">
        </div>`;
}

// --- akciók ----------------------------------------------------------------------------------

/** Betölti (vagy piszkozatból létrehozza) a nap edzését, módosítja, menti, majd újrarajzol. */
async function mutate(ctx, fn, { rerender = true } = {}) {
    const { session } = await loadSessionForDate(ctx, ctx.state.date);
    const result = fn(session);
    if (result === false) return;
    for (const entry of session.entries) {
        if (entry.sets.length) entry.completed = entry.sets.length >= plannedSetCount(entry);
    }
    await saveSession(ctx, session);
    if (rerender) await ctx.render();
}

const readNumber = (el) => parseNumber(el?.value);

function makeSet(entry, setNo, value) {
    return {
        set_no: setNo,
        reps: entry.presc_unit === 's' ? null : Math.round(value),
        duration_s: entry.presc_unit === 's' ? Math.round(value) : null,
        band_kg: entry.band_kg ?? null,
        difficulty: null,
    };
}

export const actions = {
    'toggle-set': (ctx, el) => {
        const i = Number(el.dataset.entry);
        const j = Number(el.dataset.set);
        const input = document.querySelector(`[data-key="set-${i}-${j}"]`);
        return mutate(ctx, (session) => {
            const entry = session.entries[i];
            const existing = entry.sets.findIndex((s) => s.set_no === j + 1);
            if (existing >= 0) {
                entry.sets.splice(existing, 1);
                if (!entry.sets.length) entry.completed = false;
                return;
            }
            const value = readNumber(input) ?? targetValue(entry);
            if (value === null) {
                ctx.toast('Írd be, hány ismétlés / másodperc ment.', 'warn');
                input?.focus();
                return false;
            }
            entry.sets.push(makeSet(entry, j + 1, value));
            entry.sets.sort((a, b) => a.set_no - b.set_no);
        });
    },

    'set-value': (ctx, el) => {
        const i = Number(el.dataset.entry);
        const j = Number(el.dataset.set);
        const value = readNumber(el);
        return mutate(ctx, (session) => {
            const entry = session.entries[i];
            const set = entry.sets.find((s) => s.set_no === j + 1);
            if (!set || value === null) return false; // még nem kész sorozatnál csak a ✓ ment
            Object.assign(set, makeSet(entry, j + 1, value), { band_kg: set.band_kg, difficulty: set.difficulty });
        }, { rerender: false });
    },

    'all-sets': (ctx, el) => {
        const i = Number(el.dataset.entry);
        return mutate(ctx, (session) => {
            const entry = session.entries[i];
            const target = targetValue(entry);
            const planned = plannedSetCount(entry);
            let missing = 0;
            for (let j = 0; j < planned; j++) {
                if (entry.sets.some((s) => s.set_no === j + 1)) continue;
                const value = readNumber(document.querySelector(`[data-key="set-${i}-${j}"]`)) ?? target;
                if (value === null) { missing += 1; continue; }
                entry.sets.push(makeSet(entry, j + 1, value));
            }
            entry.sets.sort((a, b) => a.set_no - b.set_no);
            if (missing) ctx.toast('Bukásig végzett gyakorlatnál írd be sorozatonként az eredményt.', 'warn');
        });
    },

    'add-set': (ctx, el) => mutate(ctx, (session) => {
        const entry = session.entries[Number(el.dataset.entry)];
        entry.presc_sets = plannedSetCount(entry) + 1;
    }),

    'entry-band': (ctx, el) => mutate(ctx, (session) => {
        const entry = session.entries[Number(el.dataset.entry)];
        entry.band_kg = readNumber(el);
        for (const set of entry.sets) set.band_kg = entry.band_kg;
    }, { rerender: false }),

    difficulty: (ctx, el) => mutate(ctx, (session) => {
        const entry = session.entries[Number(el.dataset.entry)];
        entry.difficulty = entry.difficulty === el.dataset.value ? null : el.dataset.value;
    }),

    'toggle-rehab': (ctx, el) => mutate(ctx, (session) => {
        const entry = session.entries[Number(el.dataset.entry)];
        entry.is_rehab = !entry.is_rehab;
    }),

    'entry-comment': async (ctx, el) => {
        const i = Number(el.dataset.entry);
        const comment = el.value.trim() || null;
        const signals = analyzeComment(comment);
        let autoDifficulty = null;
        await mutate(ctx, (session) => {
            const entry = session.entries[i];
            entry.comment = comment;
            const suggested = signals.easy ? DIFFICULTY_FROM_COMMENT.easy : signals.hard ? DIFFICULTY_FROM_COMMENT.hard : null;
            if (suggested && !entry.difficulty) {
                entry.difficulty = suggested;
                autoDifficulty = suggested;
            }
        }, { rerender: false });
        if (autoDifficulty) {
            ctx.toast(`Nehézség beállítva a megjegyzés alapján: ${DIFFICULTIES.find((d) => d.key === autoDifficulty).label}`);
            await ctx.render();
        }
        if (signals.pain) {
            ctx.toast('Fájdalmat vagy kellemetlenséget írtál. Rögzítsem, hogy az izomcsoportot pihentessük?', 'warn', {
                action: 'Fájdalom rögzítése',
                onAction: () => openPainForEntry(ctx, i, comment),
            });
        }
    },

    'open-pain': (ctx, el) => openPainForEntry(ctx, Number(el.dataset.entry)),

    'remove-entry': (ctx, el) => mutate(ctx, (session) => {
        session.entries.splice(Number(el.dataset.entry), 1);
        session.entries.forEach((e, idx) => { e.position = idx; });
    }),

    'add-exercise': async (ctx, el) => {
        const exercise = ctx.catalog.get(el.value);
        if (!exercise) return;
        await mutate(ctx, (session) => {
            session.entries.push(entryFromCatalog(exercise, session.entries.length));
        });
        ctx.toast(`Hozzáadva: ${exercise.name_hu}`);
    },

    cardio: (ctx, el) => mutate(ctx, (session) => {
        const field = el.dataset.field;
        session[field] = field === 'cardio_notes' ? (el.value.trim() || null) : readNumber(el);
    }),
};

async function openPainForEntry(ctx, i, note = null) {
    const { session } = await loadSessionForDate(ctx, ctx.state.date);
    const entry = session.entries[i];
    openPainModal(ctx, { sessionId: session.id, exerciseId: entry?.exercise_id || null, note,
        exerciseName: ctx.catalog.get(entry?.exercise_id)?.name_hu || entry?.name_raw });
}
