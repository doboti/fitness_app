import { describe, expect, it } from 'vitest';
import { addDays, isoWeekId, isoWeekday, weekStart, formatHu } from '../src/domain/dates.js';
import { bmi, bodyFatNavy, estimateBodyFat, weeklyWeights } from '../src/domain/body.js';
import { buildSession, programForDate, plannedSetCount, describeTarget, sessionHasData } from '../src/domain/program.js';
import { analyzeComment, restingMuscles, restConflicts } from '../src/domain/pain.js';
import { weeklyMuscleSets } from '../src/domain/stats.js';

describe('dátumok', () => {
    it('ISO hét és hétköznap', () => {
        expect(isoWeekId('2026-07-31')).toBe('2026-W31');
        expect(isoWeekId('2026-10-15')).toBe('2026-W42');
        expect(isoWeekId('2027-01-01')).toBe('2026-W53'); // péntek → az előző év 53. hete
        expect(isoWeekId('2024-12-30')).toBe('2025-W01');
        expect(isoWeekday('2026-10-18')).toBe(7);
        expect(weekStart('2026-10-18')).toBe('2026-10-12');
    });
    it('hónapváltás és szökőnap', () => {
        expect(addDays('2026-01-31', 1)).toBe('2026-02-01');
        expect(addDays('2028-02-28', 1)).toBe('2028-02-29');
        expect(formatHu('2026-10-15')).toBe('2026. október 15. (csütörtök)');
    });
});

describe('testösszetétel', () => {
    it('BMI és Navy', () => {
        expect(bmi(75.4, 175)).toBe(24.6);
        expect(bodyFatNavy({ waist: 83, neck: 38.5, height: 175, gender: 'male' })).toBe(15);
        expect(bodyFatNavy({ waist: 30, neck: 38.5, height: 175, gender: 'male' })).toBeNull();
        expect(estimateBodyFat({ weight_kg: 75 }, { height_cm: 175, age: 30, gender: 'male' }).method)
            .toBe('BMI alapú becslés');
    });
    it('heti súly-átlag és előző hét', () => {
        const logs = new Map([
            ['2026-10-12', { weight_kg: 76 }], ['2026-10-14', { weight_kg: 75 }],
            ['2026-10-07', { weight_kg: 77 }], ['2026-10-13', { weight_kg: 74, deleted: true }],
        ]);
        const w = weeklyWeights(logs, '2026-10-15');
        expect(w.days).toEqual([76, null, 75, null, null, null, null]);
        expect(w.average).toBe(75.5);
        expect(w.previousAverage).toBe(77);
    });
});

const PROGRAMS = new Map([['2026-W42', {
    week_id: '2026-W42',
    days: {
        '4': { name: 'Csütörtök', circuits: 4, exercises: [
            { name: 'Standard Push-up', target: '4 kör x 10', exercise_id: 'push_up',
              prescription: { sets: 4, unit: 'reps', min: 10, max: 10, per_side: false, to_failure: false, band_kg: null } },
            { name: 'Clamshell', target: '3 kör x 15-15', exercise_id: 'clamshell', rehab: true,
              prescription: { sets: 3, unit: 'reps', min: 15, max: 15, per_side: true, to_failure: false, band_kg: null } },
        ] },
        '6': { name: 'Szombati futás', exercises: [] },
    },
}]]);

const CATALOG = new Map([
    ['push_up', { id: 'push_up', measure: 'reps', muscles: { chest: 1, triceps: 0.6, front_delt: 0.5, abs: 0.2 } }],
    ['clamshell', { id: 'clamshell', measure: 'reps', rehab_suitable: true, muscles: { glute_med: 1, glutes: 0.3 } }],
    ['air_squat', { id: 'air_squat', measure: 'reps', muscles: { quads: 1, glutes: 0.7 } }],
]);

describe('terv → edzés', () => {
    it('napi program kiválasztása, hétvége', () => {
        expect(programForDate(PROGRAMS, '2026-10-15').day.name).toBe('Csütörtök');
        expect(programForDate(PROGRAMS, '2026-10-17').day.name).toBe('Szombati futás');
        expect(programForDate(PROGRAMS, '2026-10-18').isRestDay).toBe(true);
        expect(programForDate(PROGRAMS, '2026-10-16')).toMatchObject({ day: null, isRestDay: false });
    });
    it('edzés felépítése az előírásból', () => {
        const s = buildSession({ uid: 3, dateStr: '2026-10-15', plan: programForDate(PROGRAMS, '2026-10-15'), catalog: CATALOG });
        expect(s.id).toBe('u3-2026-10-15');
        expect(s.program_week_id).toBe('2026-W42');
        const [push, clam] = s.entries;
        expect(plannedSetCount(push)).toBe(4);
        expect(describeTarget(push)).toBe('10 ism.');
        expect(describeTarget(clam)).toBe('15 ism. / oldal');
        expect(clam.is_rehab).toBe(true);
        expect(sessionHasData(s)).toBe(false);
        push.sets.push({ set_no: 1, reps: 10 });
        expect(sessionHasData(s)).toBe(true);
    });
});

describe('fájdalom', () => {
    it('komment-elemzés ékezet nélkül és tagadással', () => {
        expect(analyzeComment('A térdem fájt a végén')).toMatchObject({ pain: true });
        expect(analyzeComment('szurt a derekam')).toMatchObject({ pain: true });
        expect(analyzeComment('Nem fájt semmi, jó volt')).toMatchObject({ pain: false });
        expect(analyzeComment('másik fajta szalaggal csináltam')).toMatchObject({ pain: false });
        expect(analyzeComment('Túl könnyű volt')).toMatchObject({ easy: true, pain: false });
        expect(analyzeComment('az utolsó kört alig bírtam')).toMatchObject({ hard: true });
        expect(analyzeComment('')).toEqual({ pain: false, easy: false, hard: false });
    });
    it('pihentetés: időtartam, súlyosság, rehab kivétel', () => {
        const reports = [
            { id: 'a', date: '2026-10-14', body_area: 'knee_lateral', intensity: 5, kind: 'dull' },
            { id: 'b', date: '2026-10-10', body_area: 'shoulder', intensity: 3, kind: 'discomfort' },   // lejárt
            { id: 'c', date: '2026-10-12', body_area: 'wrist', intensity: 8, kind: 'sharp' },          // 7 nap
            { id: 'd', date: '2026-10-15', body_area: 'chest', intensity: 9, kind: 'sharp', resolved_at: '2026-10-15' },
        ];
        const resting = restingMuscles(reports, '2026-10-15');
        expect([...resting.keys()].sort()).toEqual(['chest', 'forearms', 'quads', 'triceps']);
        expect(resting.get('quads').until).toBe(2);

        const push = { is_rehab: false };
        expect(restConflicts(push, CATALOG.get('push_up'), resting)).toEqual(['chest', 'triceps']);
        expect(restConflicts({ is_rehab: true }, CATALOG.get('air_squat'), resting)).toEqual([]);
        expect(restConflicts(push, CATALOG.get('air_squat'), resting)).toEqual(['quads']);
    });
});

describe('izomterhelés', () => {
    it('sorozatok × izomszorzó hetente, régi (sorozat nélküli) naplóval', () => {
        const sessions = [
            { date: '2026-10-13', entries: [
                { exercise_id: 'push_up', sets: [{}, {}, {}], completed: true },
                { exercise_id: null, sets: [{}], completed: true },
            ] },
            { date: '2026-10-06', entries: [{ exercise_id: 'air_squat', sets: [], completed: true, presc_sets: 4 }] },
            { date: '2026-10-14', deleted: true, entries: [{ exercise_id: 'push_up', sets: [{}], completed: true }] },
        ];
        const r = weeklyMuscleSets(sessions, CATALOG, 2, '2026-10-15');
        expect(r.weeks).toEqual(['2026-W41', '2026-W42']);
        expect(r.muscles.chest).toEqual([0, 3]);
        expect(r.muscles.quads).toEqual([4, 0]);
        expect(r.muscles.glutes).toEqual([2.8, 0]);
        expect(r.unmatched).toBe(1);
    });
});
