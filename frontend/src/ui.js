// HTML-sablon automatikus escape-eléssel: a felhasználói szöveg (komment, név) soha nem kerül nyersen a DOM-ba.

class Raw {
    constructor(value) { this.value = value; }
    toString() { return this.value; }
}

const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ESCAPES[c]);
export const raw = (value) => new Raw(value);

function renderValue(value) {
    if (value instanceof Raw) return value.value;
    if (Array.isArray(value)) return value.map(renderValue).join('');
    if (value === null || value === undefined || value === false) return '';
    return esc(value);
}

export function html(strings, ...values) {
    let out = strings[0];
    values.forEach((value, i) => { out += renderValue(value) + strings[i + 1]; });
    return new Raw(out);
}

export const when = (condition, fn) => (condition ? fn() : '');

/** Űrlapmező értéke → nem negatív szám vagy null (tizedesvesszőt is elfogad). */
export function parseNumber(value) {
    const n = parseFloat(String(value ?? '').replace(',', '.'));
    return Number.isFinite(n) && n >= 0 ? n : null;
}

// --- toast -----------------------------------------------------------------

export function toast(message, type = 'success', { action, onAction, duration } = {}) {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = message;
    const dismiss = () => {
        el.classList.add('toast-hide');
        setTimeout(() => el.remove(), 300);
    };
    if (action) {
        const btn = document.createElement('button');
        btn.className = 'btn-primary btn-sm mt-2 w-full';
        btn.textContent = action;
        btn.addEventListener('click', (e) => { e.stopPropagation(); dismiss(); onAction(); });
        el.appendChild(document.createElement('br'));
        el.appendChild(btn);
    }
    el.addEventListener('click', dismiss);
    container.appendChild(el);
    setTimeout(dismiss, duration ?? (action ? 8000 : type === 'error' ? 6000 : 3000));
}

// --- modal -----------------------------------------------------------------

export function openModal(content) {
    const root = document.getElementById('modal-root');
    root.innerHTML = html`
        <div class="fixed inset-0 z-50 flex items-end md:items-center justify-center bg-black/60 p-0 md:p-6" data-action="modal-backdrop">
            <div class="w-full md:max-w-lg max-h-[92dvh] overflow-y-auto rounded-t-3xl md:rounded-3xl bg-slate-800 border border-slate-700 p-5 safe-bottom"
                 role="dialog" aria-modal="true">
                ${content}
            </div>
        </div>`.value;
}

export function closeModal() {
    document.getElementById('modal-root').innerHTML = '';
}

export const isModalOpen = () => !!document.getElementById('modal-root').firstElementChild;
