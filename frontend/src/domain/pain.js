import { daysBetween } from './dates.js';

/**
 * Testterületek a fájdalom rögzítéséhez.
 * muscle: a backend izomcsoport-kódja (ha a terület izom), rest: mely izomcsoportokat terhelő gyakorlatokat kell kímélni.
 */
export const PAIN_AREAS = [
    { key: 'neck', label: 'Nyak', group: 'Felsőtest', muscle: 'upper_back', rest: ['upper_back'] },
    { key: 'shoulder', label: 'Váll', group: 'Felsőtest', muscle: 'front_delt', rest: ['front_delt', 'side_delt', 'rear_delt'] },
    { key: 'chest', label: 'Mell', group: 'Felsőtest', muscle: 'chest', rest: ['chest'] },
    { key: 'upper_back', label: 'Felső hát', group: 'Felsőtest', muscle: 'upper_back', rest: ['upper_back', 'rear_delt'] },
    { key: 'lats', label: 'Hát oldalt', group: 'Felsőtest', muscle: 'lats', rest: ['lats'] },
    { key: 'biceps', label: 'Bicepsz', group: 'Kar', muscle: 'biceps', rest: ['biceps'] },
    { key: 'triceps', label: 'Tricepsz', group: 'Kar', muscle: 'triceps', rest: ['triceps'] },
    { key: 'elbow', label: 'Könyök', group: 'Kar', muscle: null, rest: ['biceps', 'triceps'] },
    { key: 'wrist', label: 'Csukló', group: 'Kar', muscle: 'forearms', rest: ['forearms', 'chest', 'triceps'] },
    { key: 'abs', label: 'Has', group: 'Törzs', muscle: 'abs', rest: ['abs'] },
    { key: 'obliques', label: 'Oldalsó has', group: 'Törzs', muscle: 'obliques', rest: ['obliques'] },
    { key: 'lower_back', label: 'Derék', group: 'Törzs', muscle: 'lower_back', rest: ['lower_back'] },
    { key: 'hip_front', label: 'Csípő elöl', group: 'Csípő', muscle: 'hip_flexors', rest: ['hip_flexors'] },
    { key: 'hip_lateral', label: 'Csípő oldalt', group: 'Csípő', muscle: 'glute_med', rest: ['glute_med'] },
    { key: 'glutes', label: 'Farizom', group: 'Csípő', muscle: 'glutes', rest: ['glutes'] },
    { key: 'quads', label: 'Comb elöl', group: 'Láb', muscle: 'quads', rest: ['quads'] },
    { key: 'hamstrings', label: 'Comb hátul', group: 'Láb', muscle: 'hamstrings', rest: ['hamstrings'] },
    { key: 'adductors', label: 'Comb belső oldala', group: 'Láb', muscle: 'adductors', rest: ['adductors'] },
    { key: 'knee', label: 'Térd', group: 'Láb', muscle: null, rest: ['quads'] },
    { key: 'knee_lateral', label: 'Térd külső oldala (IT-szalag)', group: 'Láb', muscle: null, rest: ['quads'] },
    { key: 'calves', label: 'Vádli', group: 'Láb', muscle: 'calves', rest: ['calves'] },
    { key: 'ankle', label: 'Boka', group: 'Láb', muscle: null, rest: ['calves'] },
    { key: 'foot', label: 'Talp', group: 'Láb', muscle: null, rest: ['calves'] },
];

export const PAIN_AREA_BY_KEY = new Map(PAIN_AREAS.map((a) => [a.key, a]));

export const PAIN_KINDS = [
    { key: 'discomfort', label: 'Kellemetlen érzés' },
    { key: 'dull', label: 'Tompa fájdalom' },
    { key: 'sharp', label: 'Éles / szúró' },
];

/** Meddig kíméljük az érintett izmokat a bejelentés után (napok). */
export function restDays(report) {
    if (report.kind === 'sharp' || report.intensity >= 7) return 7;
    if (report.kind === 'dull' || report.intensity >= 4) return 3;
    return 2;
}

export function isSeriousPain(report) {
    return report.kind === 'sharp' || report.intensity >= 7;
}

/** Pihentetendő izomcsoportok a dátumon: muscle → a legsúlyosabb releváns bejelentés. */
export function restingMuscles(painReports, dateStr) {
    const resting = new Map();
    for (const r of painReports) {
        if (r.deleted || r.resolved_at) continue;
        const age = daysBetween(r.date, dateStr);
        if (age < 0 || age >= restDays(r)) continue;
        const area = PAIN_AREA_BY_KEY.get(r.body_area);
        const muscles = area ? area.rest : r.muscle_code ? [r.muscle_code] : [];
        for (const m of muscles) {
            const prev = resting.get(m);
            if (!prev || r.intensity > prev.intensity) resting.set(m, { ...r, age, until: restDays(r) - age });
        }
    }
    return resting;
}

/** A gyakorlat mely izmai pihentetendők (≥0.5 szorzóval terhelt izmok). A rehab gyakorlatok kivételek. */
export function restConflicts(entry, exercise, resting) {
    if (!exercise || entry.is_rehab || !resting.size) return [];
    return Object.entries(exercise.muscles)
        .filter(([muscle, weight]) => weight >= 0.5 && resting.has(muscle))
        .map(([muscle]) => muscle);
}

// --- komment-elemzés -------------------------------------------------------------------------

const fold = (s) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

const NEGATED_PAIN = /\b(nem|semmi|egyaltalan nem) (faj|fajt|fajdalom|szurt|huzodott)\w*/g;
const PAIN_WORDS = /\b(faj(?!ta)|szur|sajog|huzod|huzodas|kenyelmetlen|diszkomfort|ropog|kattog|zsibbad|bizsereg|serul|gyullad|becsipod|hasogat|nyilall)\w*/;
const EASY_WORDS = /\b(konnyu|konnyen|siman|tul konnyu|meg ment volna|unalmas)\w*/;
const HARD_WORDS = /\b(nehez|nehezen|alig|nem birtam|nem ment|kinszenved|bukas|elfogyott|szetestem)\w*/;

/** Egyszerű kulcsszavas felismerés a gyakorlat-kommentekben (ékezet-független, a tagadást kiszűri). */
export function analyzeComment(comment) {
    if (!comment || !comment.trim()) return { pain: false, easy: false, hard: false };
    const text = fold(comment).replace(NEGATED_PAIN, ' ');
    return { pain: PAIN_WORDS.test(text), easy: EASY_WORDS.test(text), hard: HARD_WORDS.test(text) };
}
