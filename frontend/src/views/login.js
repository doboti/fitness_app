import { createApi } from '../api.js';
import { listAccounts, saveAccount } from '../accounts.js';
import { html } from '../ui.js';

export function renderLogin(root, { canCancel = false } = {}) {
    root.innerHTML = html`
        <div class="min-h-dvh flex items-center justify-center p-6">
            <form class="card w-full max-w-sm" id="login-form">
                <div class="text-3xl mb-2">💪</div>
                <h1 class="text-xl font-bold mb-1">Edzésnapló</h1>
                <p class="text-sm text-slate-400 mb-4">
                    Add meg a fiókod tokenjét. Ezt a szerveren a <code class="text-slate-300">create-user</code> parancs írja ki.
                </p>
                <label class="label" for="login-token">Token</label>
                <input id="login-token" class="input font-mono text-sm" autocomplete="off" autocapitalize="off" spellcheck="false" required>
                <p class="text-sm text-red-300 mt-2 hidden" id="login-error"></p>
                <button class="btn-primary w-full mt-4" type="submit">Belépés</button>
                ${canCancel ? html`<button class="btn-ghost w-full mt-2" type="button" id="login-cancel">Mégse</button>` : ''}
            </form>
        </div>`.value;

    return new Promise((resolve) => {
        root.querySelector('#login-cancel')?.addEventListener('click', () => resolve(null));
        root.querySelector('#login-form').addEventListener('submit', async (event) => {
            event.preventDefault();
            const token = root.querySelector('#login-token').value.trim();
            const errorEl = root.querySelector('#login-error');
            const button = event.submitter;
            button.disabled = true;
            try {
                const me = await createApi(token).get('/api/me');
                const account = { uid: me.id, name: me.name, gender: me.gender, token };
                saveAccount(account);
                resolve(account);
            } catch (error) {
                errorEl.textContent = error.status === 401 ? 'Érvénytelen token.' : error.message;
                errorEl.classList.remove('hidden');
                button.disabled = false;
            }
        });
    });
}

export const hasAccounts = () => listAccounts().length > 0;
