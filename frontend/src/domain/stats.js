import { addDays, isoWeekId, weekStart } from './dates.js';

/** Hatékony heti sorozatszám-tartomány izomcsoportonként (hipertrófia-ajánlás, súlyozott sorozatban). */
export const WEEKLY_SET_TARGET = { min: 10, max: 20 };

export function entrySetCount(entry) {
    if (entry.sets.length) return entry.sets.length;
    return entry.completed ? (entry.presc_sets || 1) : 0;
}

/** Heti súlyozott sorozatszám izomcsoportonként (sorozat × izomszorzó), a backend stats.py logikájával azonosan. */
export function weeklyMuscleSets(sessions, exercisesById, weeks, todayStr) {
    const firstMonday = addDays(weekStart(todayStr), -7 * (weeks - 1));
    const weekIds = Array.from({ length: weeks }, (_, i) => isoWeekId(addDays(firstMonday, 7 * i)));
    const volume = new Map();
    let unmatched = 0;

    for (const s of sessions) {
        if (s.deleted || s.date < firstMonday || s.date > todayStr) continue;
        const week = isoWeekId(s.date);
        for (const entry of s.entries) {
            const sets = entrySetCount(entry);
            if (!sets) continue;
            const exercise = exercisesById.get(entry.exercise_id);
            if (!exercise) { unmatched += 1; continue; }
            for (const [muscle, weight] of Object.entries(exercise.muscles)) {
                if (!volume.has(muscle)) volume.set(muscle, new Map());
                const byWeek = volume.get(muscle);
                byWeek.set(week, (byWeek.get(week) || 0) + sets * weight);
            }
        }
    }

    const muscles = {};
    for (const [muscle, byWeek] of volume) {
        muscles[muscle] = weekIds.map((w) => Math.round((byWeek.get(w) || 0) * 10) / 10);
    }
    return { weeks: weekIds, muscles, unmatched };
}

/** Gyakorlatonkénti történet: dátum, sorozatok, legjobb sorozat, nehézség – a progresszió követéséhez. */
export function exerciseHistory(sessions, exerciseId, limit = 8) {
    return sessions
        .filter((s) => !s.deleted)
        .flatMap((s) => s.entries
            .filter((e) => e.exercise_id === exerciseId && (e.sets.length || e.completed))
            .map((e) => ({
                date: s.date,
                sets: e.sets.length || e.presc_sets || 0,
                best: e.sets.reduce((m, set) => Math.max(m, set.reps ?? set.duration_s ?? 0), 0) || null,
                values: e.sets.map((set) => set.reps ?? set.duration_s).filter((v) => v != null),
                unit: e.presc_unit,
                band_kg: e.band_kg,
                difficulty: e.difficulty,
                is_rehab: e.is_rehab,
            })))
        .sort((a, b) => b.date.localeCompare(a.date))
        .slice(0, limit);
}
