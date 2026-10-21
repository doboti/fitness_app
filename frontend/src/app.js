import { removeAccount } from './accounts.js';
import { createApi } from './api.js';
import { getMeta, openDb, setMeta } from './db.js';
import { addDays, formatHu, todayStr } from './domain/dates.js';
import { pendingCount, refreshCatalog, runSync } from './sync.js';
import { closeModal, html, isModalOpen, toast } from './ui.js';
import * as calendar from './views/calendar.js';
import * as dashboard from './views/dashboard.js';
import * as library from './views/library.js';
import { openProfile } from './views/login.js';
import * as pain from './views/pain.js';
import * as plan from './views/plan.js';
import * as settings from './views/settings.js';
import * as stats from './views/stats.js';
import * as workout from './views/workout.js';

const VIEWS = { dashboard, workout, calendar, stats, library, settings };
const NAV = [
    { view: 'dashboard', icon: '📊', label: 'Ma' },
    { view: 'workout', icon: '🏋️', label: 'Edzés' },
    { view: 'calendar', icon: '📅', label: 'Naptár' },
    { view: 'stats', icon: '📈', label: 'Haladás' },
    { view: 'library', icon: '📚', label: 'Gyakorlatok' },
    { view: 'settings', icon: '⚙️', label: 'Beállítások' },
];
const DATED_VIEWS = new Set(['dashboard', 'workout']);
const SYNC_DEBOUNCE_MS = 1500;
const SYNC_INTERVAL_MS = 5 * 60 * 1000;
const CATALOG_MAX_AGE_MS = 24 * 60 * 60 * 1000;

/** Az összes nézet akcióit egy helyen gyűjtjük: data-action / data-change / data-input → handler(ctx, el, event). */
const ACTIONS = Object.assign({}, ...[...Object.values(VIEWS), pain, plan].map((v) => v.actions || {}));

export async function startApp(account) {
    const db = openDb(account.uid);
    await db.open();
    const ctx = {
        account,
        db,
        api: createApi(account.token),
        user: (await getMeta(db, 'user')) || { name: account.name, gender: account.gender },
        catalog: new Map(),
        muscles: new Map(),
        state: {
            view: location.hash.slice(1) in VIEWS ? location.hash.slice(1) : 'dashboard',
            date: todayStr(),
            lastActiveDay: todayStr(),
            syncing: false,
            syncError: null,
            pending: 0,
            lastSync: await getMeta(db, 'lastSync'),
        },
    };

    ctx.loadCatalog = async () => {
        ctx.catalog = new Map((await db.exercises.toArray()).map((e) => [e.id, e]));
        ctx.muscles = new Map((await db.muscles.toArray()).map((m) => [m.code, m]));
    };
    ctx.muscleName = (code) => ctx.muscles.get(code)?.name_hu || code;
    ctx.render = () => render(ctx);
    ctx.navigate = (view) => {
        ctx.state.view = view;
        history.replaceState(null, '', `#${view}`);
        window.scrollTo(0, 0);
        return render(ctx);
    };
    ctx.setDate = (date) => {
        ctx.state.date = date;
        return render(ctx);
    };
    ctx.toast = toast;
    ctx.closeModal = closeModal;

    let syncTimer = null;
    ctx.scheduleSync = () => {
        clearTimeout(syncTimer);
        syncTimer = setTimeout(() => ctx.syncNow(), SYNC_DEBOUNCE_MS);
        pendingCount(db).then((n) => { ctx.state.pending = n; updateSyncIndicator(ctx); });
    };
    /**
     * A szerver nem ismeri az eszköz kulcsát (pl. a szerver adatbázisát lecserélték / visszaállították).
     * Ha ugyanez a profil (azonosító és név) megvan, új kulcsot kérünk hozzá és mindent újraszinkronizálunk;
     * különben a profilválasztóra lépünk (a helyi adat egy másik szerver-profilhoz tartozott).
     */
    ctx.reauthenticate = async () => {
        const profiles = await createApi(null).get('/api/profiles');
        const knownNames = [ctx.account.name, ctx.user?.name].filter(Boolean);
        const same = profiles.find((p) => p.id === ctx.account.uid && knownNames.includes(p.name));
        if (same) {
            ctx.account = await openProfile(same);
            ctx.api = createApi(ctx.account.token);
            await setMeta(db, 'cursor', 0);
            toast('A szerver adatbázisa megváltozott – új kulccsal beléptettelek, és mindent újraszinkronizálok.', 'warn');
            return true;
        }
        removeAccount(ctx.account.uid);
        await db.delete();
        location.reload();
        return false;
    };

    ctx.syncNow = async ({ manual = false, retried = false } = {}) => {
        if (ctx.state.syncing) return;
        ctx.state.syncing = true;
        updateSyncIndicator(ctx);
        let retry = false;
        try {
            const catalogAt = await getMeta(db, 'catalogAt');
            if (!catalogAt || Date.now() - Date.parse(catalogAt) > CATALOG_MAX_AGE_MS || !ctx.catalog.size) {
                await refreshCatalog(db, ctx.api);
                await ctx.loadCatalog();
            }
            const result = await runSync(db, ctx.api);
            ctx.state.syncError = null;
            ctx.state.lastSync = await getMeta(db, 'lastSync');
            const user = await getMeta(db, 'user');
            if (user) ctx.user = user;
            if (Object.keys(result.rejected).length) {
                toast(`${Object.keys(result.rejected).length} bejegyzést a szerver elutasított – részletek a Beállításokban.`, 'warn');
            }
            if (manual) toast(`Szinkron kész: ${result.pushed} küldve, ${result.pulled} fogadva.`);
            if (result.pulled || manual) await render(ctx);
        } catch (error) {
            ctx.state.syncError = error.message;
            ctx.state.syncErrorStatus = error.status;
            if (error.status === 401 && !retried) {
                retry = await ctx.reauthenticate().catch((e) => {
                    toast(`Újrabelépés sikertelen: ${e.message}`, 'error');
                    return false;
                });
            } else if (manual) {
                toast(`Szinkron sikertelen: ${error.message}`, 'error');
            }
        } finally {
            ctx.state.syncing = false;
            ctx.state.pending = await pendingCount(db);
            updateSyncIndicator(ctx);
        }
        if (retry) await ctx.syncNow({ manual, retried: true });
    };

    document.body.classList.toggle('theme-female', ctx.user.gender === 'female');
    await ctx.loadCatalog();
    bindEvents(ctx);
    await render(ctx);

    ctx.syncNow();
    setInterval(() => ctx.syncNow(), SYNC_INTERVAL_MS);
    window.addEventListener('online', () => ctx.syncNow());
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'visible') return;
        // Ha éjfél előtt a „mai” napot nézte, visszatéréskor álljon át az új napra.
        if (ctx.state.date === ctx.state.lastActiveDay && ctx.state.lastActiveDay !== todayStr()) {
            ctx.state.date = todayStr();
            render(ctx);
        }
        ctx.state.lastActiveDay = todayStr();
        ctx.syncNow();
    });
    return ctx;
}

// --- renderelés ------------------------------------------------------------------------------

async function render(ctx) {
    const view = VIEWS[ctx.state.view];
    const body = await view.render(ctx);
    const app = document.getElementById('app');

    // Fókusz és kurzor megőrzése újrarajzoláskor (data-key alapján)
    const active = document.activeElement;
    const focusKey = active?.dataset?.key;
    let selection = null;
    try { selection = focusKey ? [active.selectionStart, active.selectionEnd] : null; } catch { /* number input */ }

    app.innerHTML = shell(ctx, body).value;

    if (focusKey) {
        const el = app.querySelector(`[data-key="${CSS.escape(focusKey)}"]`);
        if (el) {
            el.focus({ preventScroll: true });
            try { if (selection) el.setSelectionRange(...selection); } catch { /* number input */ }
        }
    }
    ctx.state.pending = await pendingCount(ctx.db);
    updateSyncIndicator(ctx);
}

function shell(ctx, body) {
    const { view, date } = ctx.state;
    const isToday = date === todayStr();
    const navItems = NAV.map((n) => html`
        <a href="#${n.view}" data-action="nav" data-view="${n.view}" class="nav-item ${n.view === view ? 'active' : ''}">
            <span class="text-xl md:text-lg">${n.icon}</span>
            <span class="text-[11px] md:text-sm font-medium">${n.label}</span>
        </a>`);

    return html`
        <div class="md:flex">
            <aside class="hidden md:flex md:flex-col md:w-60 md:shrink-0 md:h-dvh md:sticky md:top-0 border-r border-slate-800 p-4 gap-1">
                <div class="text-xl font-bold text-primary px-3 pb-4">💪 Edzésnapló</div>
                ${navItems}
                <div class="mt-auto px-3 text-xs text-slate-500">${ctx.user.name}</div>
            </aside>
            <div class="flex-1 min-w-0">
                <header class="sticky top-0 z-30 bg-slate-900/95 backdrop-blur border-b border-slate-800 safe-top">
                    <div class="max-w-3xl mx-auto flex items-center gap-2 px-4 h-14">
                        ${DATED_VIEWS.has(view) ? html`
                            <button class="btn-ghost btn-sm" data-action="date-shift" data-days="-1" aria-label="Előző nap">‹</button>
                            <button class="flex-1 text-center font-semibold truncate" data-action="date-today">
                                ${formatHu(date)}${isToday ? '' : html` <span class="text-xs text-primary">→ ma</span>`}
                            </button>
                            <button class="btn-ghost btn-sm" data-action="date-shift" data-days="1" aria-label="Következő nap">›</button>
                        ` : html`<div class="flex-1 font-semibold">${NAV.find((n) => n.view === view).label}</div>`}
                        <button class="flex items-center gap-1.5 text-xs text-slate-400 pl-2" data-action="sync-now" id="sync-indicator"></button>
                    </div>
                </header>
                <main class="max-w-3xl mx-auto px-4 pt-4 pb-28 md:pb-10">${body}</main>
            </div>
        </div>
        <nav class="md:hidden fixed bottom-0 inset-x-0 z-40 bg-slate-900/95 backdrop-blur border-t border-slate-800 safe-bottom">
            <div class="grid grid-cols-6 px-1 py-1">${navItems}</div>
        </nav>`;
}

function updateSyncIndicator(ctx) {
    const el = document.getElementById('sync-indicator');
    if (!el) return;
    const { syncing, syncError, pending } = ctx.state;
    const [color, label] = syncing ? ['bg-sky-400', 'szinkron…']
        : syncError ? ['bg-red-400', ctx.state.syncErrorStatus === 0 ? 'nincs kapcsolat' : 'hiba']
            : pending ? ['bg-amber-400', `${pending} vár`]
                : ['bg-primary', 'mentve'];
    el.innerHTML = html`<span class="sync-dot ${color} ${syncing ? 'animate-pulse' : ''}"></span><span>${label}</span>`.value;
    el.title = syncError ? `Utolsó hiba: ${syncError}` : '';
}

// --- események -------------------------------------------------------------------------------

const SHARED_ACTIONS = {
    nav: (ctx, el, event) => { event.preventDefault(); return ctx.navigate(el.dataset.view); },
    'date-shift': (ctx, el) => ctx.setDate(addDays(ctx.state.date, Number(el.dataset.days))),
    'date-today': (ctx) => ctx.setDate(todayStr()),
    'sync-now': (ctx) => ctx.syncNow({ manual: true }),
    'modal-backdrop': (ctx, el, event) => { if (event.target === el) closeModal(); },
    'modal-close': () => closeModal(),
};

function bindEvents(ctx) {
    const dispatch = (attr) => async (event) => {
        const el = event.target.closest(`[data-${attr}]`);
        if (!el) return;
        const name = el.dataset[attr];
        const handler = SHARED_ACTIONS[name] || ACTIONS[name];
        if (!handler) return console.warn('Ismeretlen akció:', name);
        try {
            await handler(ctx, el, event);
        } catch (error) {
            console.error(error);
            toast(error.message || String(error), 'error');
        }
    };
    document.addEventListener('click', dispatch('action'));
    document.addEventListener('change', dispatch('change'));
    document.addEventListener('input', dispatch('input'));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && isModalOpen()) closeModal(); });
}
