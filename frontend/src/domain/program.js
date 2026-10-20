import { isoWeekId, isoWeekday } from './dates.js';

export const DIFFICULTIES = [
    { key: 'easy', label: 'Könnyű' },
    { key: 'ok', label: 'Ok' },
    { key: 'hard', label: 'Nehéz' },
    { key: 'failed', label: 'Nem sikerült' },
];
export const DIFFICULTY_LABEL = Object.fromEntries(DIFFICULTIES.map((d) => [d.key, d.label.toLowerCase()]));

/** A dátumhoz tartozó napi program a heti tervből ("1" = hétfő … "7"/"0" = vasárnap). */
export function programForDate(programsByWeek, dateStr) {
    const weekId = isoWeekId(dateStr);
    const weekday = isoWeekday(dateStr);
    const week = programsByWeek.get(weekId);
    const keys = weekday === 7 ? ['7', '0'] : [String(weekday)];
    const day = week ? keys.map((k) => week.days[k]).find(Boolean) || null : null;
    return { weekId, weekday, week, day, isRestDay: weekday >= 6 && !day };
}

/** Az edzés azonosítója felhasználónként és naponként determinisztikus, így két eszköz nem hoz létre duplikátumot. */
export function sessionIdFor(uid, dateStr) {
    return `u${uid}-${dateStr}`;
}

export function entryFromPlanned(ex, position, catalogEntry) {
    const p = ex.prescription || {};
    return {
        position,
        exercise_id: ex.exercise_id || null,
        name_raw: ex.name,
        target_raw: ex.target || null,
        presc_sets: p.sets ?? null,
        presc_unit: p.unit ?? (catalogEntry?.measure === 'time' ? 's' : catalogEntry ? 'reps' : null),
        presc_min: p.min ?? null,
        presc_max: p.max ?? null,
        presc_per_side: !!p.per_side,
        presc_to_failure: !!p.to_failure,
        band_kg: p.band_kg ?? null,
        completed: false,
        difficulty: null,
        rpe_legacy: null,
        comment: null,
        is_rehab: !!ex.rehab,
        archived: false,
        sets: [],
    };
}

export function entryFromCatalog(exercise, position) {
    return {
        position,
        exercise_id: exercise.id,
        name_raw: exercise.name_hu,
        target_raw: null,
        presc_sets: 3,
        presc_unit: exercise.measure === 'time' ? 's' : 'reps',
        presc_min: null,
        presc_max: null,
        presc_per_side: exercise.unilateral,
        presc_to_failure: false,
        band_kg: null,
        completed: false,
        difficulty: null,
        rpe_legacy: null,
        comment: null,
        is_rehab: exercise.rehab_suitable,
        archived: false,
        sets: [],
    };
}

export function buildSession({ uid, dateStr, plan, catalog }) {
    const { weekId, weekday, day } = plan;
    return {
        id: sessionIdFor(uid, dateStr),
        date: dateStr,
        title: day ? day.name : 'Szabad edzés',
        program_week_id: day ? weekId : null,
        program_day: day ? weekday : null,
        notes: null,
        cardio_distance_km: null,
        cardio_duration_min: null,
        cardio_notes: null,
        source: 'app',
        deleted: false,
        entries: day ? (day.exercises || []).map((ex, i) => entryFromPlanned(ex, i, catalog.get(ex.exercise_id))) : [],
    };
}

export function plannedSetCount(entry) {
    return Math.max(entry.presc_sets || 0, entry.sets.length, 1);
}

/** Az előírt cél egy sorozatra (ismétlés vagy mp); bukásig/ismeretlen esetén null. */
export function targetValue(entry) {
    if (entry.presc_to_failure) return null;
    return entry.presc_max ?? entry.presc_min ?? null;
}

export function describeTarget(entry) {
    if (entry.presc_to_failure) return entry.presc_unit === 's' ? 'max idő' : 'max ismétlés';
    if (entry.presc_min == null) return '';
    const range = entry.presc_min === entry.presc_max ? `${entry.presc_min}` : `${entry.presc_min}–${entry.presc_max}`;
    const unit = entry.presc_unit === 's' ? 'mp' : 'ism.';
    return `${range} ${unit}${entry.presc_per_side ? ' / oldal' : ''}`;
}

export function isEntryComplete(entry) {
    return entry.sets.length >= plannedSetCount(entry);
}

export function sessionProgress(session) {
    const active = session.entries.filter((e) => !e.archived);
    const done = active.filter((e) => e.completed).length;
    return { done, total: active.length };
}

/** Van-e a felhasználó által bevitt adat (különben nem érdemes tárolni / szinkronizálni). */
export function sessionHasData(session) {
    return session.entries.some((e) => e.completed || e.sets.length || e.difficulty || (e.comment || '').trim())
        || !!(session.cardio_distance_km || session.cardio_duration_min || (session.cardio_notes || '').trim());
}
