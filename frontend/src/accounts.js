// Fiókok az eszközön: [{ uid, name, gender, token }]. A token az eszköz localStorage-ában marad.
const ACCOUNTS_KEY = 'workout.accounts';
const ACTIVE_KEY = 'workout.active';

function read() {
    try {
        return JSON.parse(localStorage.getItem(ACCOUNTS_KEY)) || [];
    } catch {
        return [];
    }
}

function write(accounts) {
    localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(accounts));
}

export const listAccounts = read;

export function activeAccount() {
    const accounts = read();
    const uid = Number(localStorage.getItem(ACTIVE_KEY));
    return accounts.find((a) => a.uid === uid) || accounts[0] || null;
}

export function saveAccount(account) {
    write([...read().filter((a) => a.uid !== account.uid), account]);
    localStorage.setItem(ACTIVE_KEY, String(account.uid));
}

export function switchAccount(uid) {
    localStorage.setItem(ACTIVE_KEY, String(uid));
}

export function removeAccount(uid) {
    write(read().filter((a) => a.uid !== uid));
    if (Number(localStorage.getItem(ACTIVE_KEY)) === uid) localStorage.removeItem(ACTIVE_KEY);
}
