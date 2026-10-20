import { isoWeekId, weekStart, addDays } from './dates.js';

export function bmi(weightKg, heightCm) {
    if (!weightKg || !heightCm) return null;
    const m = heightCm / 100;
    return Math.round((weightKg / (m * m)) * 10) / 10;
}

export function bmiStatus(value) {
    if (value < 18.5) return { label: 'Alulsúly', tone: 'warn' };
    if (value < 25) return { label: 'Normál testsúly', tone: 'good' };
    if (value < 30) return { label: 'Enyhe túlsúly', tone: 'warn' };
    return { label: 'Jelentős túlsúly', tone: 'bad' };
}

/** U.S. Navy módszer; null, ha hiányzik méret vagy értelmetlen a kombináció. */
export function bodyFatNavy({ waist, neck, hip, height, gender }) {
    if (!waist || !neck || !height) return null;
    let value;
    if (gender === 'female') {
        if (!hip || waist + hip <= neck) return null;
        value = 495 / (1.29579 - 0.35004 * Math.log10(waist + hip - neck) + 0.221 * Math.log10(height)) - 450;
    } else {
        if (waist <= neck) return null;
        value = 495 / (1.0324 - 0.19077 * Math.log10(waist - neck) + 0.15456 * Math.log10(height)) - 450;
    }
    return Math.max(0, Math.round(value * 10) / 10);
}

export function bodyFatFromBmi(bmiValue, age, gender) {
    if (!bmiValue || !age) return null;
    const value = 1.2 * bmiValue + 0.23 * age - (gender === 'female' ? 5.4 : 16.2);
    return Math.max(0, Math.round(value * 10) / 10);
}

export function estimateBodyFat(log, user) {
    const navy = bodyFatNavy({ waist: log.waist_cm, neck: log.neck_cm, hip: log.hip_cm,
        height: user.height_cm, gender: user.gender });
    if (navy !== null) return { value: navy, method: 'U.S. Navy módszer' };
    const fromBmi = bodyFatFromBmi(bmi(log.weight_kg, user.height_cm), user.age, user.gender);
    return fromBmi === null ? null : { value: fromBmi, method: 'BMI alapú becslés' };
}

/** A hét napjainak súlyai (H..V), az átlag és az előző hét átlaga. */
export function weeklyWeights(dailyByDate, dateStr) {
    const start = weekStart(dateStr);
    const days = Array.from({ length: 7 }, (_, i) => {
        const log = dailyByDate.get(addDays(start, i));
        return log && !log.deleted && log.weight_kg ? log.weight_kg : null;
    });
    const avg = (values) => {
        const v = values.filter((x) => x != null);
        return v.length ? Math.round((v.reduce((a, b) => a + b, 0) / v.length) * 100) / 100 : null;
    };
    const prevStart = addDays(start, -7);
    const prev = Array.from({ length: 7 }, (_, i) => {
        const log = dailyByDate.get(addDays(prevStart, i));
        return log && !log.deleted && log.weight_kg ? log.weight_kg : null;
    });
    return { weekId: isoWeekId(dateStr), days, average: avg(days), previousAverage: avg(prev) };
}
