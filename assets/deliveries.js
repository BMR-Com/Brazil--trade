// Expiry deliveries for Coffee C (KC), Cotton No. 2 (CT) and London White Sugar No. 5 (WS): reported notice counts or
// tender totals, named deliverers and receivers, and (KC, CT) spot-month open interest around the notice period.
// Reads data/<market>/deliveries/<kc|ct|ws>_history.json (models/softs_deliveries.py). Outputs only.
const Deliveries = (() => {
  const FILE = { KC: 'data/coffee/deliveries/kc_history.json', CT: 'data/cotton/deliveries/ct_history.json', WS: 'data/sugar/deliveries/ws_history.json' };
  const f0 = v => v == null ? '–' : fmt(v, 0), f2 = v => v == null ? '–' : fmt(v, 2);
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const link = (src, url) => url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(src)}</a>` : esc(src);
  const kpi = (lab, v, sub) => `<div class="kpi card" style="padding:10px"><div class="lbl">${lab}</div><div class="val" style="font-size:19px">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
  const KIND = { total: 'period total', running: 'running total', fnd: 'first notice day', partial: 'part of the period', daily: 'one day' };
  const FIG = { official: 'exchange data', preliminary: 'traders, preliminary', approximate: 'trade report', back_reference: 'later reference' };
  const t = v => v ? fmt(+v / 1000, 0) + 'k t' : '–';
  const firms = (L, unit) => (L || []).map(f => `${f.largest ? '<b>' : ''}${esc(f.firm)}${f.largest ? '</b>' : ''}${f.lots ? ' ' + f0(f.lots) : f.tonnes ? ' ' + t(f.tonnes) : ''}${f.sole ? ' (sole)' : ''}${f.intent ? ' <span class="note">(planned, not a notice)</span>' : ''}`).join('<br>');
  const srcs = e => e.sources.filter(s => s.url).slice(0, 2).map(s => link(s.source + (s.date ? ', ' + s.date : ''), s.url)).join('<br>') || '–';
  const reported = e => e.lots == null ? '<span class="note">not reported</span>' : `<b>${f0(e.lots)}</b>${e.lots_derived ? '*' : ''} <span class="note">${KIND[e.kind] || ''}${e.kind === 'running' && e.as_of ? ', ' + e.as_of : ''}</span>`;

  function lead(H, side) {
    return (H.leaders[side] || []).slice(0, 8).map(a => `<tr><td class="l">${esc(a.firm)}</td><td class="n">${a.expiries}</td><td class="n">${a.largest}</td><td class="n">${a.sole || '–'}</td><td class="l">${a.last}</td></tr>`).join('');
  }

  function usFutures(H, el) {
    const kc = H.sym === 'KC', E = H.expiries;
    const last = E.find(e => e.spot && e.spot.complete) || E[0], cur = E[0];
    const named = E.filter(e => e.deliverers.length || e.receivers.length || e.clearing_deliverers.length || e.clearing_receivers.length);
    const sp = (e, k) => e.spot && e.spot[k] != null ? f0(e.spot[k]) : '–';
    el.innerHTML = `<div class="grid g4">
        ${kpi('Current delivery', cur.label, cur.spot ? `first notice ${cur.spot.fnd}, last trading ${cur.spot.ltd}` : (cur.fnd ? `first notice ${cur.fnd}` : ''))}
        ${kpi('Reported so far, ' + cur.label, cur.lots != null ? f0(cur.lots) + ' lots' : '–', cur.lots != null ? (KIND[cur.kind] || '') + (cur.as_of ? ', ' + cur.as_of : '') : 'no count reported yet')}
        ${kpi('Spot OI into first notice, ' + last.label, last.spot ? f0(last.spot.oi_fnd_open) + ' lots' : '–', last.spot ? `${f0(last.spot.oi_fnd_close)} after the first notice day` : '')}
        ${kpi('Expiries in the history', H.n_expiries, `${H.n_reported} with a reported count, ${named.length} with a named firm`)}</div>
      <div class="card" style="margin-top:12px"><h2>${esc(H.name)} expiries: notices, spot open interest and who delivered</h2><div class="tbl"><table>
        <tr><th class="l">Contract</th><th class="l">First notice</th><th class="l">Last trading</th><th>Spot OI into first notice</th><th>OI after first notice day</th><th>Spot volume, notice period</th><th>OI at last trading</th>${kc ? '<th>Certified bags at first notice</th>' : ''}<th class="l">Reported notices (lots)</th><th>First-day notices</th><th class="l">Deliverers</th><th class="l">Receivers</th><th>Settle on last trading, ¢/lb</th><th class="l">Source</th></tr>
        ${E.map(e => `<tr><td class="l"><b>${e.label}</b></td><td class="l">${(e.spot && e.spot.fnd) || e.fnd || '–'}</td><td class="l">${(e.spot && e.spot.ltd) || e.expiry_date}</td>
          <td class="n">${sp(e, 'oi_fnd_open')}</td><td class="n">${sp(e, 'oi_fnd_close')}</td><td class="n">${sp(e, 'vol_notice_period')}</td><td class="n">${sp(e, 'oi_ltd')}</td>
          ${kc ? `<td class="n">${e.spot && e.spot.certs_bags_fnd ? f0(e.spot.certs_bags_fnd) : '–'}</td>` : ''}
          <td class="l">${reported(e)}${e.auto ? ' <span class="note">(auto)</span>' : ''}</td><td class="n">${f0(e.fnd_notices)}</td>
          <td class="l">${firms(e.deliverers.concat(e.clearing_deliverers.map(f => ({ ...f, firm: f.firm + ' (clearing)' })))) || '–'}</td>
          <td class="l">${firms(e.receivers.concat(e.clearing_receivers.map(f => ({ ...f, firm: f.firm + ' (clearing)' })))) || '–'}</td>
          <td class="n">${f2(e.expiry_price)}</td><td class="l">${srcs(e)}</td></tr>`).join('')}</table></div>
        <p class="note">One lot is ${esc(H.lot)}. Open interest and volume are ICE daily figures for the expiring month; "into first notice" is the close of the session before first notice day. Notice counts and firm names are as published in trade reports; a dash means not reported, not zero. ${kc ? 'Certified bags are the ICE certified stock report nearest before first notice day. ' : ''}Built ${H.built}; new expiries are added automatically during each delivery period.</p></div>`;
  }

  function whiteSugar(H, el) {
    const E = H.expiries, R = E.filter(e => e.lots), last = R[0];
    const mx = Math.max(...R.map(e => e.lots), 1);
    const bar = e => e.lots ? `<div style="background:var(--accent,#4a7dbf);height:8px;width:${(100 * e.lots / mx).toFixed(0)}%;opacity:${e.figure === 'official' ? 1 : .55}"></div>` : '';
    const bm = Object.entries(H.by_month).map(([m, o]) => `<tr><td class="l">${m}</td><td class="n">${o.n}</td><td class="n">${f0(o.avg_lots)}</td><td class="n">${f0(o.min_lots)}</td><td class="n">${f0(o.max_lots)}</td></tr>`).join('');
    el.innerHTML = `<div class="grid g4">
        ${kpi('Latest reported expiry', last.label, `${f0(last.lots)} lots, ${t(last.tonnes)} (${FIG[last.figure] || ''})`)}
        ${kpi('Largest deliverer, latest named', esc(((R.find(e => e.deliverers.length) || {}).deliverers || []).find(f => f.largest)?.firm || '–'), (R.find(e => e.deliverers.length) || {}).label || '')}
        ${kpi('Largest receiver, latest named', esc(((R.find(e => e.receivers.length) || {}).receivers || []).find(f => f.largest)?.firm || '–'), (R.find(e => e.receivers.length) || {}).label || '')}
        ${kpi('Expiries in the history', H.n_expiries, `${H.n_reported} with a total, ${H.n_firms} with named firms`)}</div>
      <div class="card" style="margin-top:12px"><h2>London White Sugar No. 5 expiries: who delivered and who received</h2><div class="tbl"><table>
        <tr><th class="l">Contract</th><th class="l">Expiry</th><th>Lots</th><th>Tonnes</th><th class="l" style="min-width:90px">Size</th><th class="l">Figure</th><th class="l">Origins</th><th class="l">Deliverers (lots)</th><th class="l">Receivers (lots)</th><th class="l">Exchange data: sellers / buyers</th><th>Expiry US$/t</th><th class="l">Source</th></tr>
        ${E.map(e => `<tr><td class="l"><b>${e.label}</b></td><td class="l">${e.expiry_date}</td><td class="n">${e.lots ? f0(e.lots) + (e.lots_derived ? '*' : '') : '–'}</td><td class="n">${t(e.tonnes)}</td><td class="l">${bar(e)}</td>
          <td class="l">${e.figure ? FIG[e.figure] || esc(e.figure) : '<span class="note">not reported</span>'}${e.auto ? ' <span class="note">(auto)</span>' : ''}</td><td class="l">${esc(e.origins) || '–'}</td>
          <td class="l">${firms(e.deliverers) || '–'}</td><td class="l">${firms(e.receivers) || '–'}</td>
          <td class="l">${e.clearing_deliverers.length || e.clearing_receivers.length ? `<span class="note">Sellers:</span> ${firms(e.clearing_deliverers) || '–'}<br><span class="note">Buyers:</span> ${firms(e.clearing_receivers) || '–'}` : '–'}</td>
          <td class="n">${e.expiry_price ? f2(e.expiry_price) : '–'}</td><td class="l">${srcs(e)}</td></tr>`).join('')}</table></div>
        <p class="note">One lot is 50 tonnes; * lots from tonnes. Merchant names come from trade reports of each tender; the exchange data names clearing members, shown in their own column with tonnes. Lighter bars are trader figures not matched to exchange data. Bold = largest on that side; a dash means not reported. Built ${H.built}; new expiries are added automatically after each tender.</p></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Most often the largest receiver</h2><div class="tbl"><table><tr><th class="l">Firm</th><th>Expiries named</th><th>Largest</th><th>Sole</th><th class="l">Last named</th></tr>${lead(H, 'receiver')}</table></div></div>
        <div class="card"><h2>Most often the largest deliverer</h2><div class="tbl"><table><tr><th class="l">Firm</th><th>Expiries named</th><th>Largest</th><th>Sole</th><th class="l">Last named</th></tr>${lead(H, 'deliverer')}</table></div>
          <h2 style="margin-top:12px">Delivery size by contract month</h2><div class="tbl"><table><tr><th class="l">Month</th><th>Expiries</th><th>Average lots</th><th>Smallest</th><th>Largest</th></tr>${bm}</table></div></div></div>`;
  }

  async function mount(el, sym) {
    const H = await getJSON(FILE[sym]).catch(() => null);
    if (!H) { el.innerHTML = '<div class="card"><p class="note">Delivery history not built yet.</p></div>'; return; }
    return sym === 'WS' ? whiteSugar(H, el) : usFutures(H, el);
  }
  return { mount };
})();
