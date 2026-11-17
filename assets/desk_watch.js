// Desk watch: "What changed" strip, alerts, track record and delivery summary on top of the Overview tab, the full
// delivery-period dashboard (#delivery), and the sugar ethanol-parity read on the Ethanol parity tab.
// Data: data/overview/what_changed.json, data/alerts/state.json, data/scorecard/scorecard.json, data/delivery/delivery.json,
// data/sugar/parity_read.json (all written by the desk-watch workflow).
const DeskWatch = (() => {
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const n = (v, d = 2) => v == null || isNaN(v) ? '–' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }).replace('-', '−');
  const s = (v, d = 2) => v == null || isNaN(v) ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v > 0 ? '+' : ''}${n(v, d)}</span>`;
  const get = u => getJSON(u).catch(() => null);
  const css = `
  .dw-row{display:grid;grid-template-columns:150px 1fr;gap:8px;padding:7px 0;border-bottom:1px solid var(--line);align-items:start}
  .dw-row:last-child{border-bottom:0}
  .dw-row .nm{font-weight:600;font-size:13px}.dw-row .nm span{display:block;font-weight:400;font-size:11px;color:var(--muted)}
  .dw-chips{display:flex;flex-wrap:wrap;gap:4px}
  .dw-chip{font-size:12px;padding:2px 8px;border-radius:6px;background:#fff7d1;border:1px solid #e8d27a}
  .dw-chip.q{background:#f3f3f1;border-color:var(--line);color:#555}
  .dw-det summary{cursor:pointer;font-size:12px;color:#1d4f91;margin-top:3px}
  .dw-det table{font-size:12px}.dw-det td.l,.dw-det th.l{text-align:left;white-space:normal}
  .dw-al{font-size:12.5px;padding:4px 8px;border-radius:6px;margin:3px 0;background:#fdf1f0;border:1px solid #f0b0aa}
  .dw-al b{font-size:10px;background:#111;color:#fff;border-radius:4px;padding:0 4px;margin-right:5px}
  .dw-al.data{background:#f3f3f1;border-color:var(--line)}
  .dw-g2{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));margin-top:12px}
  .dw-read li{margin:3px 0;line-height:1.4}
  .dw-mk{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0}
  @media (max-width:600px){.dw-row{grid-template-columns:1fr}}`;
  function addCss() { if (!document.getElementById('dw-css')) { const st = document.createElement('style'); st.id = 'dw-css'; st.textContent = css; document.head.appendChild(st); } }

  // ---------- What changed ----------
  function itemRow(i) {
    if (i.kind === 'na') return `<tr><td class="l">${esc(i.item)}</td><td colspan="4" class="l note">${esc(i.note)}</td></tr>`;
    const u = esc(i.unit), fl = (v, f) => f ? `<b>${s(v, i.dp)}</b>` : s(v, i.dp);
    return `<tr><td class="l">${esc(i.item)}</td><td>${n(i.now, i.dp)} ${u}</td><td>${i.kind === 'weekly' ? '<span class="note">weekly</span>' : fl(i.d1, i.flag1)}${i.norm1 != null && i.kind !== 'weekly' ? ` <span class="note">±${n(i.norm1, i.dp)}</span>` : ''}</td>
      <td>${fl(i.d5, i.flag5)}${i.norm5 != null ? ` <span class="note">±${n(i.norm5, i.dp)}</span>` : ''}</td><td class="l note">${esc(i.date)}${i.note ? ' · ' + esc(i.note) : ''}</td></tr>`;
  }
  function wcCard(W) {
    if (!W) return `<div class="card"><h2>What changed</h2><p class="note">Not built yet: it fills after the next desk-watch run.</p></div>`;
    return `<div class="card"><h2>What changed <span class="note">settlements of ${esc(W.asof)} vs the previous business day and a week earlier · built ${esc(W.generated)}</span></h2>
      ${W.markets.map(m => `<div class="dw-row"><div class="nm">${esc(m.name)}</div><div>
        <div class="dw-chips">${m.flags.length ? m.flags.map(f => `<span class="dw-chip">${esc(f)}</span>`).join('') : '<span class="dw-chip q">No notable change.</span>'}</div>
        <details class="dw-det"><summary>All items</summary><div class="tbl"><table><tr><th class="l">Item</th><th>Now</th><th>1 day (normal)</th><th>1 week (normal)</th><th class="l">Date · source</th></tr>
          ${m.items.map(itemRow).join('')}</table></div>
          ${m.weather && m.weather.length ? `<div class="tbl"><table><tr><th class="l">Main region</th><th class="l">Next 15 days</th><th class="l">Previous run</th><th>Rain p50 / normal, mm</th><th>Frost odds</th></tr>
          ${m.weather.map(r => `<tr><td class="l">${esc(r.name)}</td><td class="l">${r.flip ? '<b>' : ''}${esc(r.read || '–')}${r.flip ? '</b>' : ''} <span class="note">${esc(r.src || '')}</span></td><td class="l">${esc(r.prev || '–')}</td><td>${n(r.rain_p50, 0)} / ${n(r.rain_normal, 0)}</td><td>${r.frost == null ? '–' : n(r.frost * 100, 0) + '%'}</td></tr>`).join('')}</table></div>
          <p class="note">Ensemble run ${esc(W.weather.generated || '–')} against ${esc(W.weather.prev_generated || 'no earlier run')}; frost odds = share of members at or below 3 °C.</p>` : ''}
          ${m.errors && m.errors.length ? `<p class="note">Not read this run: ${m.errors.map(esc).join('; ')}</p>` : ''}</details></div></div>`).join('')}
      <p class="note">${esc(W.rule)} Implied vol uses the first option series with at least 15 days to expiry. Cotton on-call: old-crop Dec, Mar, May, Jul only.</p></div>`;
  }

  // ---------- Alerts ----------
  function alCard(A) {
    if (!A) return `<div class="card"><h2>Alerts</h2><p class="note">Not built yet.</p></div>`;
    const mk = A.active.filter(a => a.market !== 'Data'), dt = A.active.filter(a => a.market === 'Data');
    return `<div class="card"><h2>Alerts <span class="note">checked ${esc(A.generated)} · ${A.rules_checked} levels</span></h2>
      ${mk.length ? mk.map(a => `<div class="dw-al">${a.new ? '<b>NEW</b>' : ''}<span class="note">${esc(a.market)} · since ${esc(a.since)} ·</span> ${esc(a.text)}</div>`).join('') : '<p class="note">No market alert is on.</p>'}
      ${dt.length ? `<details class="dw-det"><summary>Data late or missing (${dt.length})</summary>${dt.map(a => `<div class="dw-al data">${esc(a.text)}</div>`).join('')}</details>` : ''}
      <h3 style="margin-top:10px">Next levels to watch</h3><ul class="dw-read">${A.watch.map(w => `<li><span class="note">${esc(w.market)}:</span> ${esc(w.text)}</li>`).join('')}</ul>
      <details class="dw-det"><summary>Rules</summary><ul class="dw-read">${A.rules.map(r => `<li>${esc(r)}</li>`).join('')}</ul></details>
      <p class="note">Email: one message a day at most, new alerts only${A.last_email ? `; last sent ${esc(A.last_email)}` : ''}.</p></div>`;
  }

  // ---------- Track record ----------
  function scCard(S) {
    if (!S) return `<div class="card"><h2>Track record</h2><p class="note">Not built yet.</p></div>`;
    const dir = r => r.kind === 'spread' ? (r.direction === 'up' ? 'spread firmer' : 'spread weaker') : (r.direction === 'up' ? 'higher' : 'lower');
    const leg = r => r.kind === 'spread' ? `${r.leg1}/${r.leg2}` : r.leg1;
    return `<div class="card"><h2>Track record <span class="note">desk calls with a direction and a horizon · ${esc(S.asof)}</span></h2>
      <div class="grid g4"><div class="kpi"><div class="lbl">Open calls</div><div class="val">${S.open.length}</div></div>
        <div class="kpi"><div class="lbl">Closed</div><div class="val">${S.n_closed}</div><div class="sub">${S.hits} right</div></div>
        <div class="kpi"><div class="lbl">Hit rate</div><div class="val">${S.hit_rate == null ? 'n too small' : S.hit_rate + '%'}</div><div class="sub">${S.hit_rate == null ? `shown from ${S.min_n} closed calls` : ''}</div></div></div>
      <div class="tbl"><table><tr><th class="l">Logged</th><th class="l">Call</th><th class="l">Contract</th><th>Entry</th><th class="l">By</th></tr>
        ${S.open.map(r => `<tr><td class="l">${esc(r.logged)}</td><td class="l">${esc(r.source)} · ${esc(r.market)} ${dir(r)}</td><td class="l">${esc(leg(r))}</td><td>${esc(r.entry)}</td><td class="l">${esc(r.horizon)}</td></tr>`).join('')}</table></div>
      ${S.closed.length ? `<details class="dw-det"><summary>Closed calls (${S.closed.length})</summary><div class="tbl"><table><tr><th class="l">Logged</th><th class="l">Call</th><th>Entry</th><th>Exit</th><th>Move</th><th class="l">Result</th></tr>
        ${S.closed.slice().reverse().map(r => `<tr><td class="l">${esc(r.logged)}</td><td class="l">${esc(r.source)} · ${esc(leg(r))} ${dir(r)}</td><td>${esc(r.entry)}</td><td>${esc(r.exit)} <span class="note">${esc(r.exit_date)}</span></td><td>${esc(r.move)}</td><td class="l"><b class="${r.status === 'hit' ? 'up' : 'dn'}">${r.status}</b></td></tr>`).join('')}</table></div></details>` : ''}
      <p class="note">Logged since ${esc(S.logging_since)}. A call is scored on settlements at its horizon: right if the price (or spread) moved the called way.</p></div>`;
  }

  // ---------- Delivery ----------
  const unit = m => m.sym === 'CC' ? '$/t' : '¢/lb', dp = m => m.sym === 'CC' ? 0 : 2;
  function dvSummary(X) {
    if (!X) return `<div class="card"><h2>Delivery period</h2><p class="note">Not built yet.</p></div>`;
    return `<div class="card"><h2>Delivery period <span class="note">${esc(X.asof)}</span></h2>
      ${X.markets.filter(m => m.calendar).map(m => { const fn = m.calendar[0]; return `<div class="dw-row"><div class="nm">${esc(m.name)} ${esc(m.label)}<span>${esc(fn.event.toLowerCase())} ${esc(fn.date)} (${fn.bd} bd)</span></div>
        <div>${esc((m.read || []).slice(-1)[0] || '')} <a href="#delivery/${m.sym}" data-dv="${m.sym}">Full dashboard →</a></div></div>`; }).join('')}</div>`;
  }
  function dvMarket(m) {
    if (!m.calendar) return `<div class="card"><p class="note">${esc(m.name)}: not built (${esc((m.errors || []).join('; '))}).</p></div>`;
    const O = m.oi, Sp = m.spread, C = Sp.carry, Ce = m.certs, Oc = m.oncall, M = m.mm, Op = m.options, IR = m.index_roll;
    const kp = (l, v, sub) => `<div class="kpi card" style="padding:10px"><div class="lbl">${l}</div><div class="val" style="font-size:19px">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
    return `<div class="card" id="dv-${m.sym}" style="margin-top:12px"><h2>${esc(m.name)} ${esc(m.label)} <span class="note">against ${esc(m.spread ? m.spread.pair.split("/")[1] : "")}</span></h2>
      <ul class="dw-read">${(m.read || []).map(t => `<li>${esc(t)}</li>`).join('')}</ul>
      <div class="grid g4">${m.calendar.map(r => kp(esc(r.event), esc(r.date), r.bd >= 0 ? `${r.bd} business days` : `${-r.bd} business days ago`)).join('')}
        ${kp('Index roll', `GSCI ${esc(IR.gsci[0].slice(5))} – ${esc(IR.gsci[1].slice(5))}`, `BCOM ${esc(IR.bcom[0])} to ${esc(IR.bcom[1])}${m.index_roll_past ? ' (done)' : ''}`)}</div>
      <div class="dw-g2">
        <div><h3>Open interest in ${esc(m.label)}</h3>${O ? `<p>${n(O.oi, 0)} lots on ${esc(O.asof)}: ${n(O.pct_left, 1)}% of its level ${O.K0} business days before ${esc(O.T0_kind)} (past rolls ${n(O.band.lo, 1)}–${n(O.band.hi, 1)}%, median ${n(O.band.mid, 1)}%); ${n(O.share_of_all_oi, 1)}% of all open interest. Recent pace ${n(O.pace_lots_per_day, 0)} lots a day.</p>
          <div class="tbl"><table><tr><th class="l">Report</th><th>bd to notice</th><th>Open interest</th><th>Change</th><th>% left</th><th>Spread</th></tr>${O.path.slice().reverse().map(r => `<tr><td class="l">${esc(r.date)}</td><td>${r.bd_to_notice}</td><td>${n(r.oi, 0)}</td><td>${s(r.chg, 0)}</td><td>${n(r.pct_left, 1)}%</td><td>${s(r.spread, dp(m))}</td></tr>`).join('')}</table></div><p class="note">${esc(O.src)}.</p>` : '<p class="note">– No open-interest file for this contract on the desk.</p>'}</div>
        <div><h3>Spread ${esc(Sp.pair)}</h3><p>${s(Sp.now, dp(m))} ${unit(m)} on ${esc(Sp.date)} (${esc(Sp.sign)}), ${s(Sp.chg_1w, dp(m))} on the week. Front ${n(Sp.front, dp(m))}, next ${n(Sp.next, dp(m))}.</p>
          ${C ? `<div class="tbl"><table><tr><td class="l">Next over front</td><td>${s(C.next_over_front)}¢</td></tr><tr><td class="l">Full carry (storage ${n(C.storage)}, financing ${n(C.financing)}, penalties ${n(C.penalties)})</td><td>${n(C.full_carry)}¢</td></tr>
            <tr><td class="l">Share of full carry</td><td><b>${n(C.pct_of_full_carry, 1)}%</b>${C.pct_1w_ago != null ? ` <span class="note">week ago ${n(C.pct_1w_ago, 1)}%</span>` : ''}</td></tr><tr><td class="l">Average ICE premium of the certs on board</td><td>${s(C.cert_premium_pts, 0)} pts</td></tr></table></div><p class="note">${esc(C.date)}; full carry and premiums as on the Certs tab (${esc(C.basis)}).</p>` : ''}
          <h3>Certified stocks</h3>${Ce ? `<p>${n(Ce.now, 0)} ${esc(Ce.unit)} on ${esc(Ce.date)}${Ce.chg_1w != null ? `, ${s(Ce.chg_1w, 0)} on the week` : Ce.chg != null ? `, ${s(Ce.chg, 0)} since ${esc(Ce.chg_vs)}` : ''}${Ce.pending != null ? `; ${n(Ce.pending, 0)} bags pending grading` : ''}. <span class="note">${esc(Ce.src)}</span></p>` : `<p class="note">– ${m.sym === 'SB' ? 'No. 11 has no certified stocks (FOB origin delivery).' : 'Not collected on the desk.'}</p>`}</div>
        ${Oc ? `<div><h3>On-call against ${esc(Oc.contract)}</h3><p>Unfixed call sales ${n(Oc.sales, 0)} lots (${s(Oc.sales_chg, 0)}), unfixed call purchases ${n(Oc.purchases, 0)} (${s(Oc.purchases_chg, 0)}), net ${s(Oc.net, 0)} lots. <span class="note">${esc(Oc.src)}, ${esc(Oc.date)}</span></p></div>` : ''}
        ${M ? `<div><h3>Managed money</h3><p>Long ${n(M.long, 0)}, short ${n(M.short, 0)}, net ${s(M.net, 0)} lots; spreading ${n(M.spreading, 0)} (${s(M.spreading_chg, 0)}), ${n(M.spreading_share_oi, 1)}% of open interest, ${ordn(M.spreading_pct3y)} percentile of 3 years. <span class="note">${esc(M.src)}, ${esc(M.date)}</span></p></div>` : ''}
        ${Op ? `<div><h3>Options: ${esc(Op.series)} on ${esc(Op.underlying)}</h3><p>Expiry ${esc(Op.expiry)} (${Op.bd_to_expiry} bd). Call OI ${n(Op.call_oi, 0)}, put OI ${n(Op.put_oi, 0)} (P/C ${n(Op.pc_oi)}).${Op.expired.length ? ` <span class="note">${Op.expired.map(esc).join('; ')}.</span>` : ''}</p>
          <div class="tbl"><table><tr><th>Call strike</th><th>OI</th><th>1d</th><th>Put strike</th><th>OI</th><th>1d</th></tr>${[0, 1, 2, 3, 4].map(i => { const c = Op.top_calls[i], p = Op.top_puts[i]; return `<tr><td>${c ? '<b>' + c.K + '</b>' : ''}</td><td>${c ? n(c.oi, 0) : ''}</td><td>${c ? s(c.chg, 0) : ''}</td><td>${p ? '<b>' + p.K + '</b>' : ''}</td><td>${p ? n(p.oi, 0) : ''}</td><td>${p ? s(p.chg, 0) : ''}</td></tr>`; }).join('')}</table></div><p class="note">${esc(Op.src)}.</p></div>` : ''}
      </div>${m.errors && m.errors.length ? `<p class="note">Not read: ${m.errors.map(esc).join('; ')}</p>` : ''}</div>`;
  }
  async function showDelivery() {
    addCss();
    const el = document.getElementById('delivery');
    const X = await get('data/delivery/delivery.json');
    const want = (location.hash.match(/^#delivery\/(\w+)/) || [])[1];
    if (!X) { el.innerHTML = '<div class="card"><p class="note">Delivery dashboard not built yet.</p></div>'; return; }
    el.innerHTML = `<div style="max-width:1400px;margin:0 auto;padding:12px 16px"><div class="card"><b>Delivery period</b> — the contract nearest first notice (sugar: expiry) in each soft, from settlements of ${esc(X.asof)}; built ${esc(X.generated)}.
      <div class="dw-mk">${X.markets.map(m => `<button class="chip" data-go="${m.sym}">${esc(m.name)} ${esc(m.label || '')}</button>`).join('')}</div>
      <p class="note">Reads are rule-based summaries of the numbers shown, not forecasts. Index roll: GSCI 5th–9th, BCOM 6th–10th business day of the month before delivery. Research only.</p></div>
      ${X.markets.map(dvMarket).join('')}</div>`;
    el.querySelectorAll('[data-go]').forEach(b => b.onclick = () => { history.replaceState(null, '', '#delivery/' + b.dataset.go); document.getElementById('dv-' + b.dataset.go)?.scrollIntoView({ behavior: 'smooth' }); });
    if (want) setTimeout(() => document.getElementById('dv-' + want)?.scrollIntoView(), 50); else history.replaceState(null, '', '#delivery');
  }

  // ---------- Overview hook ----------
  async function intoOverview() {
    addCss();
    const host = document.getElementById('overview'); if (!host) return;
    const box = host.firstElementChild; if (!box || document.getElementById('dw-top')) return;
    const top = document.createElement('div'); top.id = 'dw-top'; top.innerHTML = '<div class="card"><p class="note">Loading what changed…</p></div>';
    box.insertBefore(top, box.firstChild);
    const [W, A, S, X] = await Promise.all([get('data/overview/what_changed.json'), get('data/alerts/state.json'), get('data/scorecard/scorecard.json'), get('data/delivery/delivery.json')]);
    top.innerHTML = wcCard(W) + `<div class="dw-g2">${alCard(A)}${dvSummary(X)}</div><div class="dw-g2">${scCard(S)}</div>`;
    top.querySelectorAll('[data-dv]').forEach(a => a.onclick = e => { e.preventDefault(); history.replaceState(null, '', '#delivery/' + a.dataset.dv); document.querySelector('nav.comm button[data-c="delivery"]')?.click(); });
  }
  if (typeof Overview !== 'undefined') {
    const orig = Overview.show;
    Overview.show = async (...a) => { const r = await orig(...a); try { await intoOverview(); } catch (e) { console.error(e); } return r; };
  }

  // ---------- Sugar parity card ----------
  async function sugarCard(el) {
    if (!el) return;
    const P = await get('data/sugar/parity_read.json'); if (!P) { el.innerHTML = ''; return; }
    const w = P.now, K = P.constants, U = P.mix.unica, F = P.mix.fortnight;
    el.innerHTML = `<div class="card" style="margin-bottom:12px"><h2>Export vs ethanol: where sugar stands <span class="note">No. 11 ${esc(w.contract_label)} settlement ${esc(w.date)}</span></h2>
      <div class="grid g4"><div class="kpi"><div class="lbl">No. 11 ${esc(w.contract_label)}</div><div class="val">${n(w.sb)} ¢/lb</div><div class="sub">ICE settlement ${esc(w.date)}</div></div>
        <div class="kpi"><div class="lbl">Hydrous ethanol parity</div><div class="val">${n(w.parity)} ¢/lb</div><div class="sub">R$${n(w.eth, 0)}/m³ (${esc(w.eth_date)}${w.eth_age_bd > 1 ? `, ${w.eth_age_bd} business days old` : ''}) at R$${n(w.fx, 4)}/US$ (${esc(w.fx_date)})</div></div>
        <div class="kpi"><div class="lbl">Sugar over ethanol</div><div class="val">${s(w.gap)} ¢/lb</div><div class="sub">${w.sugar_pays ? 'sugar pays more: mills keep the sugar mix up' : 'ethanol pays more: mills shift cane to ethanol'}</div></div>
        <div class="kpi"><div class="lbl">Break-even levels</div><div class="val" style="font-size:17px">${n(w.sb_level_ethanol_equal)} ¢/lb</div><div class="sub">No. 11 at which ethanol pays the same; or hydrous at R$${n(w.eth_level_sugar_equal, 0)}/m³ to match today's No. 11</div></div></div>
      <p>${U ? `UNICA sugar mix ${n(U.mix_sugar, 1)}% in ${esc(U.month)} (${esc(U.season)}; ${n(U.mix_sugar_ly, 1)}% a year earlier).` : ''} ${F ? `Fortnight to ${esc(F.end)}: ${n(F.mix_sugar, 1)}% (${esc(F.src)}).` : ''}</p>
      <p class="note">Ethanol price: ${esc(w.eth_src)}.${w.b3_parity != null && !/^B3/.test(w.eth_src) ? ` B3 hydrous futures front: R$${n(w.b3_eth, 0)}/m³ (${esc(w.b3_date)}), parity ${n(w.b3_parity)} ¢/lb.` : ''} Parity ¢/lb = (ethanol R$/m³ × ${K.atr_kg_per_kg_sugar} ÷ ${K.atr_kg_per_litre_hydrous} + R$${n(K.fob_logistics_brl_t, 0)}/t mill-to-FOB Santos) ÷ USD/BRL ÷ ${K.lb_per_tonne_over_100} ÷ (1 + ${n(K.pol_premium * 100, 2)}% VHP polarisation premium). ATR factors: CONSECANA (kg of ATR per kg of sugar and per litre of hydrous ethanol). Built ${esc(P.generated)}.</p></div>`;
  }
  return { showDelivery, sugarCard, intoOverview };
})();
