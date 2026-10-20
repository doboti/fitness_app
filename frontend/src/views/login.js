import { createApi } from '../api.js';
import { listAccounts, saveAccount } from '../accounts.js';
import { html } from '../ui.js';

export const profileLabel = (p) => `${p.name} (${p.gender === 'female' ? 'nő' : 'férfi'})`;

/** Profil megnyitása: a szerver ehhez az eszközhöz saját hozzáférési kulcsot ad, amit a fiók-listába mentünk. */
export async function openProfile(profile) {
    const { token, user } = await createApi(null).post(`/api/profiles/${profile.id}/session`);
    const account = { uid: user.id, name: user.name, gender: user.gender, token };
    saveAccount(account);
    return account;
}

export function renderLogin(root) {
    root.innerHTML = html`
        <div class="min-h-dvh flex items-center justify-center p-6">
            <form class="card w-full max-w-sm" id="login-form">
                <div class="text-3xl mb-2">💪</div>
                <h1 class="text-xl font-bold mb-4">Edzésnapló</h1>
                <label class="label" for="login-profile">Ki edz?</label>
                <select id="login-profile" class="input" disabled><option>Betöltés…</option></select>
                <p class="text-sm text-red-300 mt-2 hidden" id="login-error"></p>
                <button class="btn-primary w-full mt-4" type="submit" disabled>Belépés</button>
            </form>
        </div>`.value;

    const select = root.querySelector('#login-profile');
    const button = root.querySelector('button[type=submit]');
    const errorEl = root.querySelector('#login-error');
    const showError = (message) => {
        errorEl.textContent = message;
        errorEl.classList.remove('hidden');
    };
    let profiles = [];

    createApi(null).get('/api/profiles')
        .then((list) => {
            profiles = list;
            if (!list.length) throw new Error('Még nincs profil a szerveren (create-user paranccsal hozható létre).');
            select.innerHTML = list.map((p) => html`<option value="${p.id}">${profileLabel(p)}</option>`.value).join('');
            select.disabled = false;
            button.disabled = false;
        })
        .catch((error) => showError(error.message));

    return new Promise((resolve) => {
        root.querySelector('#login-form').addEventListener('submit', async (event) => {
            event.preventDefault();
            button.disabled = true;
            try {
                resolve(await openProfile(profiles.find((p) => p.id === Number(select.value))));
            } catch (error) {
                showError(error.message);
                button.disabled = false;
            }
        });
    });
}

export const hasAccounts = () => listAccounts().length > 0;
