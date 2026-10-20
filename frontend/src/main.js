import './styles.css';
import { activeAccount } from './accounts.js';
import { startApp } from './app.js';
import { renderLogin } from './views/login.js';

async function boot() {
    const root = document.getElementById('app');
    const addingAccount = sessionStorage.getItem('workout.addAccount') === '1';
    sessionStorage.removeItem('workout.addAccount');

    let account = activeAccount();
    if (!account || addingAccount) {
        const loggedIn = await renderLogin(root, { canCancel: !!account });
        account = loggedIn || account;
    }
    await startApp(account);
}

if ('serviceWorker' in navigator && import.meta.env.PROD) {
    window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(console.error));
}

boot().catch((error) => {
    console.error(error);
    document.getElementById('app').textContent = `Hiba az indításkor: ${error.message}`;
});
