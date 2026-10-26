// Heti tervjavaslat (a backend szabálymotorja vagy a Gemini készíti) – az aktuális hétre, ha arra még nincs terv, különben a következőre; változásonként jóváhagyható. Csak online működik.
import { isoWeekId, todayStr } from '../domain/dates.js';
import { html, openModal, when } from '../ui.js';

const weekLabel = (weekId) => (weekId === isoWeekId(todayStr()) ? 'ez a hét' : 'jövő hét');

const GEMINI_TIMEOUT_MS = 180000;

const KIND = {
    progress: ['Nehezítés', 'bg-primary/15 text-primary'],
    band: ['Erősebb szalag', 'bg-primary/15 text-primary'],
    variant: ['Új variáns', 'bg-violet-500/15 text-violet-300'],
    regress: ['Könnyítés', 'bg-amber-500/15 text-amber-300'],
    replace: ['Csere', 'bg-amber-500/15 text-amber-300'],
    remove: ['Kihagyás', 'bg-red-500/15 text-red-300'],
    add: ['Új gyakorlat', 'bg-sky-500/15 text-sky-300'],
};
const DAY_NAMES = { 1: 'Hétfő', 2: 'Kedd', 3: 'Szerda', 4: 'Csütörtök', 5: 'Péntek', 6: 'Szombat', 7: 'Vasárnap', 0: 'Vasárnap' };

/** A legutóbbi javaslat betöltése a háttérben (a nézet nem vár a hálózatra). */
function ensureLoaded(ctx) {
    const plan = ctx.state.plan || (ctx.state.plan = { status: 'idle', proposal: null, excluded: new Set() });
    if (plan.status !== 'idle') return plan;
    plan.status = 'loading';
    Promise.all([ctx.api.get('/api/plan/proposals'), ctx.api.get('/api/coach/status')])
        .then(([list, coach]) => {
            plan.coach = coach;
            plan.proposal = list.find((p) => p.status === 'pending') || null;
            plan.last = list.find((p) => p.status !== 'pending' && p.status !== 'superseded') || null;
            plan.status = 'ready';
        })
        .catch((error) => { plan.status = 'error'; plan.error = error.message; })
        .finally(() => { if (ctx.state.view === 'stats') ctx.render(); });
    return plan;
}

export function planCard(ctx) {
    const plan = ensureLoaded(ctx);
    let body;
    if (plan.status === 'loading' || plan.status === 'idle') {
        body = html`<p class="text-sm text-slate-500">Betöltés…</p>`;
    } else if (plan.status === 'error') {
        body = html`
            <p class="text-sm text-slate-400">A javaslatokhoz kapcsolat kell a szerverrel. (${plan.error})</p>
            <button class="btn-secondary btn-sm mt-2" data-action="plan-reload">Újra</button>`;
    } else if (!plan.proposal) {
        body = html`
            <p class="text-sm text-slate-400">
                A motor az elmúlt 4 hét naplójából, a nehézség-visszajelzésekből és a fájdalmakból javasol változásokat
                a soron következő hétre (ha az aktuálisra még nincs terv, akkor erre a hétre). Semmi nem változik a jóváhagyásod nélkül.
            </p>
            ${when(plan.last, () => html`<p class="text-xs text-slate-500 mt-2">Legutóbbi: ${plan.last.target_week_id} – ${plan.last.status === 'accepted' ? 'elfogadva' : 'elvetve'}</p>`)}
            <button class="btn-primary w-full mt-3" data-action="plan-generate" ${plan.busy ? 'disabled' : ''}>
                ${plan.busy === 'engine' ? 'Készül…' : 'Javaslat a szabálymotortól'}</button>
            <div class="border-t border-slate-700 mt-4 pt-3">
                <div class="text-sm font-medium mb-1">🤖 Havi edzői értékelés (Gemini)</div>
                <p class="text-xs text-slate-500 mb-2">Az elmúlt 4 hét összefoglalóját (napló, kommentek, fájdalmak, súly) elküldi a Gemininek,
                    aki szöveges értékelést és ugyanígy jóváhagyható változásokat ad.</p>
                ${plan.coach?.configured ? html`
                    <button class="btn-secondary w-full" data-action="coach-review" ${plan.busy ? 'disabled' : ''}>
                        ${plan.busy === 'coach' ? 'A Gemini dolgozik… (akár 1 perc)' : `Értékelés kérése (${plan.coach.model})`}</button>`
            : html`<p class="text-xs text-slate-500 mb-2">A szerveren nincs Gemini API-kulcs – kézi módban a Gemini chatet használhatod.</p>`}
                <button class="btn-ghost w-full mt-1" data-action="coach-manual" ${plan.busy ? 'disabled' : ''}>Kézi mód: prompt másolása, válasz beillesztése</button>
            </div>`;
    } else {
        body = proposalBody(plan);
    }
    return html`
        <div class="card mb-4" id="plan-card">
            <div class="card-title">📋 Heti terv javaslat</div>
            ${body}
        </div>`;
}

function proposalBody(plan) {
    const p = plan.proposal;
    const selected = p.changes.filter((c) => !plan.excluded.has(c.id)).length;
    return html`
        <div class="flex items-baseline justify-between gap-2">
            <div class="font-semibold">${p.base_week_id} → ${p.target_week_id} <span class="text-sm font-normal text-slate-400">(${weekLabel(p.target_week_id)})</span>
                <span class="badge ${p.source === 'llm' ? 'bg-violet-500/15 text-violet-300' : 'bg-slate-700 text-slate-300'} ml-1">${p.source === 'llm' ? 'Gemini edző' : 'szabálymotor'}</span></div>
            <div class="text-xs text-slate-500">${p.changes.length} változás · ${p.unchanged} marad</div>
        </div>
        ${when(p.coach_note, () => html`
            <div class="rounded-xl bg-violet-500/10 border border-violet-500/30 p-3 mt-3 text-sm leading-relaxed whitespace-pre-line">${p.coach_note}</div>`)}
        ${when(p.focus?.length, () => html`<div class="flex flex-wrap gap-1.5 mt-2">${p.focus.map((f) => html`<span class="badge bg-slate-700 text-slate-200">🎯 ${f}</span>`)}</div>`)}
        ${p.insights.map((i) => html`<p class="text-sm text-amber-300 mt-2">⚠️ ${i}</p>`)}
        ${when(p.target_exists, () => html`
            <p class="text-sm text-amber-300 mt-2">A ${p.target_week_id} hétre már van feltöltött terv – elfogadáskor ez lecseréli.</p>`)}
        ${when(!p.changes.length, () => html`<p class="text-sm text-slate-400 mt-3">Nincs javasolt változás: a terv maradhat így.</p>`)}
        <div class="space-y-2 mt-3">
            ${p.changes.map((c) => {
        const [label, tone] = KIND[c.kind] || [c.kind, 'bg-slate-700 text-slate-200'];
        const on = !plan.excluded.has(c.id);
        return html`
                    <label class="flex gap-3 rounded-xl bg-slate-900 p-3 cursor-pointer ${on ? '' : 'opacity-50'}">
                        <input type="checkbox" class="mt-1 h-5 w-5 accent-[rgb(var(--primary))] shrink-0" ${on ? 'checked' : ''}
                               data-change="plan-toggle" data-id="${c.id}">
                        <div class="min-w-0 text-sm">
                            <div class="flex flex-wrap items-center gap-1.5">
                                <span class="badge ${tone}">${label}</span>
                                <span class="text-xs text-slate-500">${DAY_NAMES[c.day] || c.day}</span>
                            </div>
                            <div class="mt-1">
                                ${c.before ? html`<span class="text-slate-400">${c.before.name}: ${c.before.target}</span>` : ''}
                                ${c.after ? html`${c.before ? html` <span class="text-slate-500">→</span> ` : ''}<b>${c.after.name}: ${c.after.target}</b>` : ''}
                            </div>
                            <div class="text-xs text-slate-400 mt-1">${c.reason}</div>
                        </div>
                    </label>`;
    })}
        </div>
        <div class="flex gap-2 mt-4">
            <button class="btn-primary flex-1" data-action="plan-accept" ${plan.busy ? 'disabled' : ''}>
                ${p.changes.length ? `Elfogadás (${selected})` : 'Terv átvétele változatlanul'}</button>
            <button class="btn-ghost" data-action="plan-reject" ${plan.busy ? 'disabled' : ''}>Elvetés</button>
        </div>`;
}

async function busy(ctx, fn, kind = true) {
    const plan = ctx.state.plan;
    plan.busy = kind;
    await ctx.render();
    try {
        await fn(plan);
    } finally {
        plan.busy = false;
        await ctx.render();
    }
}

export const actions = {
    'plan-reload': (ctx) => {
        ctx.state.plan.status = 'idle';
        return ctx.render();
    },
    'plan-generate': (ctx) => busy(ctx, async (plan) => {
        await ctx.syncNow();   // a friss helyi naplót is vegye figyelembe
        plan.proposal = await ctx.api.post('/api/plan/proposals');
        plan.excluded = new Set();
    }, 'engine'),
    'coach-review': (ctx) => busy(ctx, async (plan) => {
        await ctx.syncNow();
        plan.proposal = await ctx.api.post('/api/coach/review', undefined, { timeout: GEMINI_TIMEOUT_MS });
        plan.excluded = new Set();
    }, 'coach'),
    'coach-manual': async (ctx) => {
        await ctx.syncNow();
        const { prompt, target_week_id: target } = await ctx.api.get('/api/coach/prompt');
        ctx.state.plan.manualPrompt = prompt;
        openModal(html`
            <div class="flex items-center justify-between mb-2">
                <h2 class="text-lg font-bold">🤖 Kézi Gemini-kör (${target})</h2>
                <button class="btn-ghost btn-sm" data-action="modal-close" aria-label="Bezárás">✕</button>
            </div>
            <ol class="text-sm text-slate-300 space-y-1 list-decimal pl-5 mb-3">
                <li>Másold ki a promptot, és illeszd be a Gemini chatbe (gemini.google.com).</li>
                <li>A Gemini JSON-válaszát másold ide vissza.</li>
                <li>Az ellenőrzött változásokat egyenként hagyhatod jóvá.</li>
            </ol>
            <button class="btn-secondary w-full" data-action="coach-copy">📋 Prompt másolása (${Math.round(prompt.length / 1000)}k karakter)</button>
            <textarea class="input mt-3 font-mono text-xs" rows="8" id="coach-response" placeholder='{"coach_note": "…", "changes": [ … ]}'></textarea>
            <button class="btn-primary w-full mt-3" data-action="coach-import">Válasz feldolgozása</button>`);
    },
    'coach-copy': async (ctx, el) => {
        try {
            await navigator.clipboard.writeText(ctx.state.plan.manualPrompt);
            el.textContent = '✓ Kimásolva – illeszd be a Gemini chatbe';
        } catch {
            // ha a vágólap nem elérhető, a prompt kijelölhető szövegként jelenik meg
            const area = document.getElementById('coach-response');
            area.value = ctx.state.plan.manualPrompt;
            area.select();
            el.textContent = 'Jelöld ki és másold a lenti szöveget, majd töröld és illeszd be a választ';
        }
    },
    'coach-import': async (ctx) => {
        const text = document.getElementById('coach-response').value.trim();
        if (!text) {
            ctx.toast('Illeszd be a Gemini válaszát.', 'warn');
            return;
        }
        const plan = ctx.state.plan;
        plan.proposal = await ctx.api.post('/api/coach/import', { response: text });
        plan.excluded = new Set();
        ctx.closeModal();
        ctx.toast(`Betöltve: ${plan.proposal.changes.length} érvényes változás.`);
        await ctx.render();
    },
    'plan-toggle': (ctx, el) => {
        const { excluded } = ctx.state.plan;
        if (el.checked) excluded.delete(el.dataset.id); else excluded.add(el.dataset.id);
        return ctx.render();
    },
    'plan-accept': (ctx) => busy(ctx, async (plan) => {
        const ids = plan.proposal.changes.map((c) => c.id).filter((id) => !plan.excluded.has(id));
        const program = await ctx.api.post(`/api/plan/proposals/${plan.proposal.id}/accept`, { change_ids: ids });
        plan.last = { ...plan.proposal, status: 'accepted' };
        plan.proposal = null;
        await ctx.syncNow();   // az új heti terv letöltése
        ctx.toast(`${program.week_id} terve elkészült (${ids.length} változással). Jövő héten az Edzés nézetben látod.`);
    }),
    'plan-reject': (ctx) => busy(ctx, async (plan) => {
        await ctx.api.post(`/api/plan/proposals/${plan.proposal.id}/reject`);
        plan.last = { ...plan.proposal, status: 'rejected' };
        plan.proposal = null;
        ctx.toast('Javaslat elvetve.');
    }),
};
