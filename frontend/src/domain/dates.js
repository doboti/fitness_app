// Minden dátum helyi 'YYYY-MM-DD' string; így nincs időzóna-csúszás (a régi app UTC-hibája).

const MONTHS = ['január', 'február', 'március', 'április', 'május', 'június',
    'július', 'augusztus', 'szeptember', 'október', 'november', 'december'];
const DAYS = ['vasárnap', 'hétfő', 'kedd', 'szerda', 'csütörtök', 'péntek', 'szombat'];
export const DAY_SHORT = ['H', 'K', 'Sze', 'Cs', 'P', 'Szo', 'V'];

export function toDateStr(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

export function parseDate(str) {
    const [y, m, d] = str.split('-').map(Number);
    return new Date(y, m - 1, d);
}

export const todayStr = () => toDateStr(new Date());

export function addDays(str, n) {
    const d = parseDate(str);
    d.setDate(d.getDate() + n);
    return toDateStr(d);
}

/** 1 = hétfő … 7 = vasárnap */
export function isoWeekday(str) {
    return parseDate(str).getDay() || 7;
}

export function weekStart(str) {
    return addDays(str, 1 - isoWeekday(str));
}

export function isoWeekId(str) {
    const d = parseDate(str);
    d.setDate(d.getDate() + 4 - (d.getDay() || 7)); // az adott hét csütörtökje dönti el az évet
    const yearStart = new Date(d.getFullYear(), 0, 1);
    const week = Math.ceil(((d - yearStart) / 86400000 + 1) / 7);
    return `${d.getFullYear()}-W${String(week).padStart(2, '0')}`;
}

export function daysBetween(a, b) {
    return Math.round((parseDate(b) - parseDate(a)) / 86400000);
}

export function formatHu(str) {
    const d = parseDate(str);
    return `${d.getFullYear()}. ${MONTHS[d.getMonth()]} ${d.getDate()}. (${DAYS[d.getDay()]})`;
}

export function formatShortHu(str) {
    const d = parseDate(str);
    return `${MONTHS[d.getMonth()].slice(0, 3)}. ${d.getDate()}.`;
}

export function monthTitle(year, month) {
    return `${year}. ${MONTHS[month]}`;
}

export function nowIso() {
    return new Date().toISOString();
}
