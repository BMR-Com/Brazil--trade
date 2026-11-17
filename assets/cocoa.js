// Cocoa section (basic): primer, ICCO world balance, West Africa and Ecuador weather, futures/options & COT,
// seasonality & technicals, news flow and the outlook tile. Uses the desk modules with symbol CC.
const Cocoa = (() => {
  let built = false, tab = 'cc-primer', I = null;
  const TABS = [['cc-primer', 'Primer'], ['cc-bal', 'World balance (ICCO)'], ['cc-wx', 'West Africa &amp; Ecuador weather'],
    ['cc-certs', 'Certs profile &amp; delivery value'], ['cc-flows', 'Futures, options &amp; COT'], ['cc-seas', 'Seasonality &amp; technicals'], ['cc-news', 'News'], ['cc-outlook', 'Outlook']];
  const body = () => $('#ccBody');
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const k = v => v == null ? '–' : Math.round(v).toLocaleString('en-US');
  const sk = v => v == null ? '–' : `<span class="${v > 0 ? 'up' : v < 0 ? 'dn' : ''}">${v > 0 ? '+' : ''}${k(v)}</span>`;
  const load = () => I ? Promise.resolve(I) : getJSON('data/cocoa/icco.json').then(d => (I = d));
  const guard = fn => async () => { try { await fn(); } catch (e) { console.error(e); body().innerHTML = '<div class="card"><p class="note">This tab failed to load.</p></div>'; } };

  function shell() {
    $('#cocoa').innerHTML = `<nav class="tabs" id="ccTabs">${TABS.map(([t, l], i) => `<button data-t="${t}" class="${t === tab ? 'on' : ''}">${i + 1} · ${l}</button>`).join('')}</nav><main><div id="ccBody"></div></main>`;
    $$('#ccTabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; $$('#ccTabs button').forEach(x => x.classList.toggle('on', x === b)); render(); });
  }
  function show() {
    if (!built) { shell(); built = true; }
    const h = location.hash.slice(1); if (TABS.some(t => t[0] === h)) { tab = h; $$('#ccTabs button').forEach(x => x.classList.toggle('on', x.dataset.t === tab)); }
    render();
  }
  function render() {
    history.replaceState(null, '', '#' + tab);
    body().innerHTML = '<div class="card"><p class="note">Loading…</p></div>';
    ({ 'cc-primer': guard(primer), 'cc-bal': guard(balance), 'cc-wx': guard(weather), 'cc-certs': guard(certs), 'cc-flows': guard(flows),
      'cc-seas': () => MktStudy.mount(body(), ['CC']), 'cc-news': guard(news), 'cc-outlook': guard(outlook) })[tab]();
  }

  async function primer() {
    await load();
    body().innerHTML = `<div class="grid g2">
      <div class="card"><h2>ICE Cocoa (CC, New York)</h2><div class="tbl"><table>
        <tr><td>Size</td><td class="l">10 metric tons of cocoa beans</td></tr>
        <tr><td>Quote / tick</td><td class="l">US$ per tonne; $1 = $10 per contract</td></tr>
        <tr><td>Months</td><td class="l">Mar, May, Jul, Sep, Dec</td></tr>
        <tr><td>Delivery</td><td class="l">Exchange-graded beans from many origins held in ICE-licensed warehouses at the delivery ports, invoiced with differentials by origin group. What sits in those warehouses is the certified stock.</td></tr>
        <tr><td>Notice / last trade</td><td class="l">First notice ten business days before the delivery month; last trade eleven business days before the month's last business day. Options expire in the month before delivery (exact dates on the ICE contract page).</td></tr>
        <tr><td>London cocoa</td><td class="l">ICE Europe (C), £/t, 10 t. Sterling pricing and different delivery terms; the NY–London arb moves with GBP/USD and with which side holds deliverable stock.</td></tr></table></div>
        <h3>Calendar</h3><p>Cocoa year runs October–September. The <b>main crop</b> (Oct–Mar, about 70–80% of West African output) grows on the April–July rains and the shorter Sep–Nov rains; the <b>mid crop</b> (Apr–Sep) depends on rain in Oct–Feb. The dry, dusty <b>harmattan</b> (Dec–Feb) can shrivel young pods. Côte d'Ivoire and Ghana set farmgate prices at the start of each crop (October, and April for the mid crop).</p></div>
      <div class="card"><h2>What moves cocoa</h2><div class="tbl"><table><tr><th class="l">Driver</th><th class="l">Mechanism</th></tr>
        <tr><td class="l">West African weather</td><td class="l">Côte d'Ivoire and Ghana grow over half the world's beans. Rain at flowering and pod-setting and soil moisture before the harmattan decide the next crop; El Niño tends to dry the region.</td></tr>
        <tr><td class="l">Port arrivals</td><td class="l">Weekly bean arrivals at Ivorian ports (reported by exporters) are the most-watched supply gauge against last season.</td></tr>
        <tr><td class="l">Tree health</td><td class="l">Swollen-shoot virus, ageing trees and illegal gold mining have cut yields structurally in Ghana and eastern Côte d'Ivoire.</td></tr>
        <tr><td class="l">Farmgate pricing and forward sales</td><td class="l">The two state boards sell much of each crop forward and fix farmer prices; a farmgate price far below world prices encourages smuggling and under-investment, and defaults on forward contracts tighten the market.</td></tr>
        <tr><td class="l">Grindings (demand)</td><td class="l">Quarterly grind data for Europe (ECA), North America (NCA) and Asia (CAA), out about two weeks after each quarter, are the demand gauge; high prices cut grinding and chocolate volumes with a lag.</td></tr>
        <tr><td class="l">Certified stocks</td><td class="l">ICE-certified cocoa is what the futures deliver; a steady build means supply is outrunning demand and eases the nearby spreads.</td></tr>
        <tr><td class="l">Funds</td><td class="l">Managed money swings; producer hedging thins when prices and margins are high, which makes moves larger.</td></tr></table></div></div></div>
      <div class="card" style="margin-top:12px"><h2>Origins</h2><div class="tbl"><table><tr><th class="l">Origin</th><th class="l">Role</th><th class="l">What to watch</th></tr>
        ${I.origins.map(o => `<tr><td class="l"><b>${esc(o.country)}</b></td><td class="l">${esc(o.role)}</td><td class="l">${esc(o.watch)}</td></tr>`).join('')}</table></div>
        <h3>Free sources</h3><p class="note"><a href="https://www.icco.org/statistics/" target="_blank" rel="noopener">ICCO statistics and monthly market reports</a> ·
          <a href="https://www.conseilcafecacao.ci/" target="_blank" rel="noopener">Conseil Café-Cacao (Côte d'Ivoire)</a> ·
          <a href="https://cocobod.gh/" target="_blank" rel="noopener">Ghana COCOBOD</a> ·
          <a href="https://www.ice.com/report-center" target="_blank" rel="noopener">ICE Report Center (certified stocks)</a> ·
          <a href="https://www.eurococoa.com/" target="_blank" rel="noopener">European Cocoa Association (grind)</a></p></div>`;
  }

  async function balance() {
    await load();
    const R = I.releases;
    const latest = {}; R.forEach(r => { latest[r.season] = r; });
    const rows = R.map(r => `<tr><td class="l">${esc(r.label)}</td><td>${r.season}</td><td class="note">${r.kind}</td><td>${k(r.production)}</td><td>${k(r.grindings)}</td><td>${sk(r.surplus)}</td><td>${k(r.stocks)}</td><td>${r.stocks_grind_pct?.toFixed(1)}%</td><td class="l note">${esc(r.note || '')}</td></tr>`).join('');
    const seasons = Object.values(latest);
    body().innerHTML = `<div class="grid g2">
      <div class="card"><h2>ICCO world balance (latest estimate per season)</h2><div class="tbl"><table>
        <tr><th>Season</th><th>Production</th><th>Grindings</th><th>Surplus / deficit</th><th>End stocks</th><th>Stocks/grind</th></tr>
        ${seasons.map(r => `<tr><td>${r.season}</td><td>${k(r.production)}</td><td>${k(r.grindings)}</td><td>${sk(r.surplus)}</td><td>${k(r.stocks)}</td><td>${r.stocks_grind_pct.toFixed(1)}%</td></tr>`).join('')}</table></div>
        <p class="note">Thousand tonnes. After the record 2023/24 deficit, the 2024/25 surplus estimate has been revised down at each bulletin since February — a smaller cushion than first thought. Read the revisions, not the level.</p></div>
      <div class="card"><h2>How ICCO's 2024/25 surplus estimate moved</h2><div style="position:relative;height:240px"><canvas id="ccRev"></canvas></div></div></div>
      <div class="card" style="margin-top:12px"><h2>Every bulletin</h2><div class="tbl"><table><tr><th class="l">Bulletin</th><th>Season</th><th></th><th>Production</th><th>Grindings</th><th>Surplus</th><th>Stocks</th><th>Stocks/grind</th><th class="l"></th></tr>${rows}</table></div></div>
      <div class="card" style="margin-top:12px"><h2>Other published forecasts (surplus, thousand tonnes)</h2><div class="tbl"><table><tr><th class="l">Source</th><th>Season</th><th>Surplus</th><th class="l">When / note</th></tr>
        ${I.others.map(o => `<tr><td class="l">${esc(o.source)}</td><td>${o.season}</td><td>${sk(o.surplus)}</td><td class="l note">${esc(o.when)}${o.note ? ' · ' + esc(o.note) : ''}</td></tr>`).join('')}</table></div>
        <p class="note">Industry forecasts as reported publicly; they differ widely, so watch each source's revisions. ${esc(I.about)} Updated ${I.updated}.</p></div>`;
    const r25 = R.filter(r => r.season === '2024/25');
    chart('ccRev', { type: 'bar', data: { labels: r25.map(r => r.label), datasets: [{ label: '2024/25 surplus (kt)', data: r25.map(r => r.surplus), backgroundColor: '#2f6b3a' },
      { label: 'Stocks/grindings %', data: r25.map(r => r.stocks_grind_pct), type: 'line', yAxisID: 'y1', borderColor: '#c0392b' }] },
      options: { scales: { y1: { position: 'right', grid: { display: false }, ticks: { font: { size: 10 } } } } } });
  }

  async function weather() {
    const W = await getJSON('data/geo/weather.json').catch(() => null);
    const rs = (W?.regions || []).filter(r => (r.commodities || []).includes('cocoa'));
    if (!rs.length) { body().innerHTML = '<div class="card"><p class="note">Cocoa-belt weather is collected with the next weather run (twice a day).</p></div>'; return; }
    const n = (v, d = 0) => v == null || v === '' ? '–' : (+v).toFixed(d);
    const pct = p => p == null ? '' : `<span class="note">(${ordn(p)} pct)</span>`;
    const tone = p => p == null ? '' : p <= 20 ? 'dn' : p >= 80 ? 'up' : '';
    body().innerHTML = `<div class="card"><h2>Cocoa belt weather vs history</h2><div class="tbl"><table>
      <tr><th class="l">Region</th><th>Rain 30 d (mm)</th><th>Rain 90 d</th><th>Season to date (from)</th><th>Soil moisture 0-100 cm</th><th>Next 16 days rain</th><th>Max temp 30 d</th><th class="l">Flags</th></tr>
      ${rs.map(r => `<tr><td class="l"><b>${esc(r.name)}</b><br><span class="note">${esc(r.note)}</span></td>
        <td class="${tone(r.r30_p)}">${n(r.r30)} <span class="note">vs ${n(r.r30_n)}</span> ${pct(r.r30_p)}</td>
        <td class="${tone(r.r90_p)}">${n(r.r90)} <span class="note">vs ${n(r.r90_n)}</span> ${pct(r.r90_p)}</td>
        <td class="${tone(r.rstd_p)}">${n(r.rstd)} <span class="note">vs ${n(r.rstd_n)} (${esc(r.season_from)})</span></td>
        <td class="${tone(r.sm100_p)}">${n(r.sm100, 2)} ${pct(r.sm100_p)}</td>
        <td class="${tone(r.f16_rain_p)}">${n(r.f16_rain)} <span class="note">vs ${n(r.f16_rain_n)}</span></td>
        <td>${n(r.tmax30, 1)}°C</td><td class="l note">${(r.flags || []).map(esc).join('; ')}</td></tr>`).join('')}</table></div>
      <p class="note">Open-Meteo (ERA5 history, forecast); normals and percentiles against the same dates in past years (red = dry, green = wet). Through ${esc(rs[0].data_through)}.
      Main-crop pods need the Apr–Jul and Sep–Nov rains; soil moisture going into the Dec–Feb harmattan sets mid-crop prospects.</p></div>`;
  }

  // Certs profile and delivery value: data/cocoa/certs_profile.json (models/cocoa_certs_profile.py).
  let CPc = null;
  const loadCPc = () => CPc ? Promise.resolve(CPc) : getJSON('data/cocoa/certs_profile.json').then(d => (CPc = d));
  const box = (id, h = 260) => `<div style="position:relative;height:${h}px"><canvas id="${id}"></canvas></div>`;
  const kpi = (lab, v, sub) => `<div class="kpi card" style="padding:10px"><div class="lbl">${lab}</div><div class="val" style="font-size:19px">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
  const marks = (ms, labels) => ({ id: 'ccMarks', afterDatasetsDraw(ch) {
    const { ctx, chartArea: a, scales: { x } } = ch; if (!a) return; ctx.save(); ctx.font = '10px system-ui,sans-serif';
    ms.forEach(m => { const i = labels.indexOf(m.date); if (i < 0) return; const px = x.getPixelForValue(i); if (px < a.left || px > a.right) return;
      ctx.strokeStyle = 'rgba(192,57,43,.55)'; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = '#a93226'; ctx.save(); ctx.translate(px + 3, a.top + 4); ctx.rotate(Math.PI / 2); ctx.fillText(m.label, 0, 0); ctx.restore(); });
    ctx.restore(); } });
  async function certs() {
    const D = await loadCPc(), C = D.current, E = D.economics, H = D.history, SP = D.spreads, R = D.rules, Ph = D.physical, al = E.all, fu = E.futures;
    const f0 = v => fmt(v, 0), d$ = v => sgn(v, 0, ' $/t');
    const ec = E.by_origin.find(r => r.origin === 'Ecuador'), ctd1 = E.ctd.find(r => r.lots === 1000), Vd = E.validity;
    const MONl = m => MON[+m.slice(5) - 1] + ' ' + m.slice(2, 4);
    const wa = E.cells.filter(r => r.group === 'A'), waR = wa.length ? `${sgn(Math.min(...wa.map(r => r.value)), 0, '')} to ${sgn(Math.max(...wa.map(r => r.value)), 0, ' $/t')}` : 'none';
    const sp = SP.same_point.slice(0, -1), wider = sp.filter(r => r.pct < SP.now.pct).length;
    const brief = `<div class="card" style="margin:0 0 12px;border-left:4px solid var(--acc)"><h3 style="margin-top:0">Cocoa certs: ${f0(C.lots)} lots (${f0(C.tonnes / 1000)}k t), almost all Group B Latin American beans; ${SP.now.pair} carry wider than usual</h3><ul style="margin:0;padding-left:18px">
      <li style="margin:4px 0"><b>Size and trend.</b> ${f0(C.bags)} bags certified on ${C.date} (${f0(C.lots)} lots, ${f0(C.tonnes)} t), up from ${f0(C.first_lots)} lots on ${C.first_report}; another ${f0(C.pending_lots)} lots wait for grading (mostly Ecuador). Ecuador is ${f0(ec.lots / C.lots * 100)}% of the pile; West African Group A beans are only ${f0(C.by_group.A || 0)} lots.</li>
      <li style="margin:4px 0"><b>Cost to stop everything.</b> Delivered on ${fu.front} on its existing weight notes, the whole stock invoices on average at <b>${d$(al.value)} against the futures</b> (${f0(fu.front_settle)}, ${fu.date}): growth premium ${d$(al.premium)}, bean count and waste ${d$(al.weight_usd)} (${fmt(al.weight_pct, 2)}% of weight), loss-of-weight allowance ${d$(al.allow_usd)} (0.25% per 30 days since weighing, about ${fmt(al.allow_pct, 1)}%), regrade effect ${d$(al.regrade_usd)}. Re-weighed lots avoid the allowance: before it the stock is ${d$(al.value_before_allow)}. There is no port differential in cocoa.</li>
      <li style="margin:4px 0"><b>Regrading before March.</b> A cocoa grade certificate covers two delivery periods, not a year. About <b>${f0(Vd.need_front_lots)} lots (${f0(Vd.need_front_lots / C.lots * 100)}%) were graded before October and must be regraded to deliver on ${fu.front}</b>; every lot now certified needs a regrade before ${MONl(Vd.second_month)}. Recently about ${f0(Vd.survival_median_pct)}% of lapsing cocoa has come back as regrades (range ${Vd.survival_range_last8[0]}–${Vd.survival_range_last8[1]}%), so roughly ${f0(Vd.at_risk_lots)} lots could drop out of the deliverable supply for March unless new gradings replace them.</li>
      <li style="margin:4px 0"><b>Cheapest to deliver.</b> The first 1,000 lots tendered average ${d$(ctd1?.avg)}: high-count Ecuador and Venezuela in the Delaware River, where weight discounts and the loss-of-weight allowance eat the $80 Group B premium. West African Group A lots (${waR}) keep less of their +$160 than it seems: their high bean counts cost about 2% of weight. The order is by origin and port averages, not lot by lot.</li>
      <li style="margin:4px 0"><b>Age.</b> Unlike coffee, a lapsed cocoa grade can be renewed by regrading (Rule 9.18(c)(i)); there is no fixed one-year expiry. ${f0(C.regrade_12m_t)} t were re-graded in the last 12 months against ${f0(C.initial_12m_t)} t graded for the first time; estimated average time since first grading ${f0(C.avg_age_days_known)} days (estimate from grading history).</li>
      <li style="margin:4px 0"><b>Spread.</b> ${SP.now.pair} is ${sgn(SP.now.s12, 0, ' $/t')} (${sgn(SP.now.pct, 2, '%')} of price), ${SP.now.bd_to_fnd} business days before first notice; at the same point of the ${SP.now.pair} spread in ${sp.length} earlier years it was wider (more carry) only ${wider} times. A growing pile of cheap-to-deliver Group B cocoa is what keeps the front in carry.</li>
      <li style="margin:4px 0"><b>Exchange vs physical: low confidence.</b> No public dated series of physical cocoa differentials was found, so the adjusted gap (now against past deliveries) cannot be shown. The one public physical premium is the $${f0(Ph.lid_usd_t)}/t Living Income Differential on Ivorian and Ghanaian sales against ICE's +$${f0(Ph.group_a)} for Group A: a $${f0(Ph.west_africa_gap)}/t shortfall, which is why West African beans are rarely certified.</li></ul>
      <p class="note" style="margin-bottom:0">Certs ${C.date}; grading to ${H.grading.months.at(-1)}; futures ${fu.date}. ${fu.spot} is in its delivery period (first notice passed); values use ${fu.front}.</p></div>`;
    const ageT = `<table><tr><th class="l">Origin</th><th>Lots</th><th>Group</th><th>Premium</th><th>Count+waste</th><th>Count+waste $/t</th><th>Slate</th><th>Weight allowance</th><th>Regrade share / $</th><th>Value vs ${fu.front}</th><th>Pending (bags)</th>${C.age_groups.map(g => `<th>${g}</th>`).join('')}</tr>
      ${E.by_origin.map(r => `<tr><td class="l">${r.origin}</td><td class="n">${f0(r.lots)}</td><td class="n">${r.premium >= 150 ? 'A' : r.premium > 0 ? 'B' : 'C'}</td><td class="n">${f0(r.premium)}</td><td class="n">${fmt(r.weight_pct, 2)}%</td><td class="n">${fmt(r.weight_usd, 0)}</td><td class="n">${fmt(r.slate, 0)}</td><td class="n">${fmt(r.allow_pct, 2)}% / ${fmt(r.allow_usd, 0)}</td><td class="n">${f0(r.regrade_share)}% / ${fmt(r.regrade_usd, 0)}</td><td class="n"><b>${d$(r.value)}</b></td><td class="n">${r.pending_bags ? f0(r.pending_bags) : '–'}</td>${C.age_groups.map(g => `<td class="n">${r.age[g] ? f0(r.age[g] / 10) : '–'}</td>`).join('')}</tr>`).join('')}
      <tr><td class="l"><b>All certs</b></td><td class="n"><b>${f0(C.lots)}</b></td><td></td><td class="n">${f0(al.premium)}</td><td class="n">${fmt(al.weight_pct, 2)}%</td><td class="n">${f0(al.weight_usd)}</td><td class="n">${f0(al.slate)}</td><td class="n">${fmt(al.allow_pct, 2)}% / ${f0(al.allow_usd)}</td><td class="n">${f0(Vd.need_front_lots / C.lots * 100)}% / ${fmt(al.regrade_usd, 0)}</td><td class="n"><b>${d$(al.value)}</b></td><td class="n">${f0(C.pending_bags)}</td>${C.age_groups.map(() => '<td></td>').join('')}</tr></table>`;
    const ruleRows = R.changes.slice().reverse().map(r => `<tr><td class="l" style="white-space:nowrap">${r.effective_date}</td><td class="l">${r.first_contract}</td><td class="l">${r.rule_area}</td><td class="l">${r.plain_english}</td><td class="l"><a href="${r.source_url}" target="_blank" rel="noopener">source</a></td></tr>`).join('');
    const vts = Object.keys(Vd.by_valid).sort(), gvK = {};
    Vd.by_cell.forEach(c => { const k = c.origin + '|' + c.port; (gvK[k] ||= { origin: c.origin, port: c.port, v: {} }).v[c.valid_through] = c.lots; });
    const gvRows = Object.values(gvK).sort((a, b) => Object.values(b.v).reduce((t, x) => t + x, 0) - Object.values(a.v).reduce((t, x) => t + x, 0));
    const vlab = v => /^\d{4}-\d{2}$/.test(v) ? MONl(v) : v;
    const gvT = `<table><tr><th class="l">Origin</th><th class="l">Port</th>${vts.map(v => `<th>${vlab(v)}${v < Vd.front_month ? ' (regrade before ' + MONl(Vd.front_month) + ')' : ''}</th>`).join('')}<th>Total</th></tr>
      ${gvRows.map(r => `<tr><td class="l">${r.origin}</td><td class="l">${r.port}</td>${vts.map(v => `<td class="n">${r.v[v] ? f0(r.v[v]) : '–'}</td>`).join('')}<td class="n"><b>${f0(Object.values(r.v).reduce((t, x) => t + x, 0))}</b></td></tr>`).join('')}
      <tr><td class="l"><b>All</b></td><td></td>${vts.map(v => `<td class="n"><b>${f0(Vd.by_valid[v])}</b></td>`).join('')}<td class="n"><b>${f0(C.lots)}</b></td></tr></table>`;
    const RB = `<a href="${R.source}" target="_blank" rel="noopener">ICE rulebook Chapter 9 Cocoa</a>`;
    body().innerHTML = `${brief}
      <div class="grid g4">${kpi('Certified now', f0(C.lots) + ' lots', `${C.date}; ${f0(C.tonnes)} t; ${f0(C.pending_lots)} lots pending`)}
        ${kpi('Cost to stop all certs', d$(al.value), `lot-weighted, vs ${fu.front} ${f0(fu.front_settle)}`)}
        ${kpi('First 1,000 lots delivered', d$(ctd1?.avg), 'cheapest to deliver first')}
        ${kpi(`${SP.now.pair} spread`, sgn(SP.now.s12, 0, ' $/t'), `${sgn(SP.now.pct, 2, '%')} of price; ${SP.now.bd_to_fnd} business days to first notice`)}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Certified cocoa by origin, daily (lots)</h2>${box('ccD', 280)}<p class="note">ICE daily certified-stock report; the desk holds it from ${C.first_report}. A long certified-stock history is not in the desk yet (see below).</p></div>
        <div class="card"><h2>Cocoa graded each month since 2016 (t)</h2>${box('ccG', 280)}<p class="note">ICE monthly grading results: first-time gradings by class (A +$160, B +$80, C par) and re-gradings of cocoa whose certificate expired. Red lines: rule changes.</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Delivery value of newly graded cocoa ($/t vs futures)</h2>${box('ccV', 240)}<p class="note">Tonnage-weighted premium less weight and slate discounts of each month's first-time gradings, at that month's average front futures price.</p></div>
        <div class="card"><h2>Front / second spread since ${SP.first.slice(0, 4)} (% of price)</h2>${box('ccS', 240)}<p class="note">Monthly average of front minus second (negative = carry), front rolled at first notice; per-contract ICE settlements. Red lines: rule changes.</p></div></div>
      <div class="card" style="margin-top:12px"><h2>Current certs by origin: delivery value and age <span class="note">$/t vs ${fu.front}; age columns in lots since first grading (estimate)</span></h2><div class="tbl">${ageT}</div>
        <p class="note">Premium from the growth group on ICE's daily report (a Nigeria lot with a high bean count is certified in Group B). Weight discount (bean count above standard and waste, % of invoice weight) and slate discount: tonnage-weighted ICE grading results for that origin and port over the last 12 months, priced at ${fu.front}. Age: newest first-time gradings of each origin and port are assumed to make up the stock (an <b>estimate</b>; ICE does not publish cocoa age). Weight allowance (Rule 9.23(b)(ii)(B)): 0.25% of weight per 30 days or part from the weight date (taken as the first grading date, an estimate; cocoa older than the 2016 file taken as 1,200 days) to mid-${MONl(Vd.front_month)}; Sanchez's tiered schedule is not modelled. A deliverer can re-weigh within 13 business days of delivery instead. Regrade: share of each origin and port that must be regraded before ${fu.front}, times the average change in discount between regrades and first gradings of that origin (last 3 years).</p></div>
      <div class="card" style="margin-top:12px"><h2>Grade valid through <span class="note">lots, by origin and port; estimated from grading dates</span></h2><div class="tbl">${gvT}</div>
        <p class="note">Each lot's latest grading date (first grading or regrade) is estimated from ICE's grading results and daily passes (newest gradings make up the stock first). Rule 9.18(d)(ii)(1): graded in a delivery month → valid for the rest of it and the next delivery period; graded outside → the next two delivery periods (delivery period taken as the delivery month). Lots whose grade runs out before ${MONl(Vd.front_month)} must be regraded to deliver on ${fu.front}: <b>${f0(Vd.need_front_lots)} lots</b>; before ${MONl(Vd.second_month)}: ${f0(Vd.need_second_lots)} lots. A regrade can fail or lower the class; recent regrades returned about ${f0(Vd.survival_median_pct)}% of the lapsing tonnage.</p></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Cheapest to deliver</h2><div class="tbl"><table><tr><th class="l">Lots delivered</th><th>Average $/t</th><th>Range</th></tr>${E.ctd.map(r => `<tr><td class="l">${r.lots === 'all' ? `All (${f0(C.lots)})` : 'First ' + f0(r.lots)}</td><td class="n"><b>${d$(r.avg)}</b></td><td class="n">${f0(r.worst)} to ${f0(r.best)}</td></tr>`).join('')}</table></div>
          <div class="tbl"><table><tr><th class="l">Order</th><th class="l">Origin</th><th class="l">Port</th><th>Lots</th><th>Cum. lots</th><th>$/t</th></tr>${E.cells.map((r, i) => `<tr><td class="l">${i + 1}</td><td class="l">${r.origin} (${r.group})</td><td class="l">${r.port}</td><td class="n">${f0(r.lots)}</td><td class="n">${f0(r.cum_lots)}</td><td class="n">${d$(r.value)}</td></tr>`).join('')}</table></div>
          <p class="note">Lots sorted by invoice value against the futures, lowest first: the deliverer tenders what is worth least on the invoice. ${fu.spot} delivery is under way; the same order applies to ${fu.front}.</p></div>
        <div class="card"><h2>${SP.now.pair} at the same point, every year</h2>${box('ccY', 240)}<p class="note">Average ${SP.now.pair} spread (% of the front price) within two business days of the same distance to first notice (${SP.now.bd_to_fnd} business days), by year of the front contract; red = now.</p>
          <h3>Exchange vs physical</h3><p class="note" style="margin-top:0">${Ph.note} Confidence: <b>${Ph.confidence}</b>. If Ma has a dated physical-differential series (Ecuador, Ivory Coast, Ghana, Nigeria vs NY or London), the gap now vs at past deliveries can be added.</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>ICE cocoa delivery rules</h2><div class="tbl"><table>
          <tr><td class="l"><b>Unit, price</b></td><td class="l">10 t net in the original bags (45–75 kg); US$/t, $1 tick; Mar, May, Jul, Sep, Dec. First notice 10 business days before the delivery month.</td></tr>
          <tr><td class="l"><b>Growth premiums</b></td><td class="l">Group A +$160/t: ${R.groups.A.join(', ')}. Group B +$80/t: Latin America (Ecuador incl. CCN-51 and Arriba, Colombia, Peru, Venezuela, Dominican Republic/Sanchez, Mexico, Brazil, Nicaragua …), Cameroon, Indonesia-Java, PNG, Tanzania, Uganda. Group C par: Bolivia, Haiti, Indonesia-Sulawesi, Malaysia, all others.</td></tr>
          <tr><td class="l"><b>Bean count</b></td><td class="l">Class A standard 1,000 / max 1,200 beans per kg; B 1,100 / 1,300; C 1,200 / 1,400; over max = next class's premium; over 1,400 not deliverable. Above standard: 0.5% of weight per 25 beans (up to 4%).</td></tr>
          <tr><td class="l"><b>Grade</b></td><td class="l">Mould ≤4%, insect ≤4%, combined ≤6%; slaty ≤10%, then $2.20/t per 1% (none for Sulawesi, Sanchez, Haiti); smoky/hammy not deliverable. Waste: par to 1%, deduction above, not deliverable over 5%.</td></tr>
          <tr><td class="l"><b>Ports</b></td><td class="l">New York, Delaware River, Albany, Baltimore, Hampton Roads; seller's choice; no port differential.</td></tr>
          <tr><td class="l"><b>Certificate life</b></td><td class="l">${R.certificate_validity}</td></tr>
          <tr><td class="l"><b>Weight</b></td><td class="l">10 t ±1%; 9.5–9.9 t partial default; over 10.3 t invoiced at 10.3 t (Rule 9.07(f)). ${R.weight_loss_allowance}</td></tr>
          <tr><td class="l"><b>Customs, EUDR</b></td><td class="l">${R.customs}. ${R.eudr}</td></tr></table></div>
          <p class="note">${RB} (read ${R.read_on}).</p></div>
        <div class="card"><h2>Dated rule changes</h2><div class="tbl"><table><tr><th class="l">Effective</th><th class="l">First contract</th><th class="l">Rule</th><th class="l">What it means</th><th class="l">Source</th></tr>${ruleRows}</table></div>
          <p class="note"><b>Long certified-stock history:</b> the desk has ICE's daily cocoa certs only from ${C.first_report}. ICE's report centre (historical cocoa certified stocks) is captcha-protected and is not downloaded automatically: drop the historical certified-stock file into the ICE inbox and it will be added.</p></div></div>
      <p class="note">Variables used: ${D.variables.join('; ')}. Built ${D.built}.</p>`;
    const pal = ['#7d3c98', '#2c6fbb', '#17a589', '#d68910', '#c0392b', '#2f6b3a', '#7f8c8d'];
    const dd = H.daily;
    chart('ccD', { type: 'line', data: { labels: dd.dates, datasets: Object.entries(dd.series).map(([o, v], i) => ({ label: o, data: v, backgroundColor: pal[i % 7], borderColor: pal[i % 7], fill: true, pointRadius: 0, borderWidth: 0, stack: 's' })) },
      options: { scales: { y: { stacked: true, beginAtZero: true } } } });
    const G = H.grading, gl = G.months;
    chart('ccG', { type: 'bar', data: { labels: gl, datasets: [...Object.entries(G.initial_by_class).map(([c, v], i) => ({ label: 'First grading, class ' + c, data: v, backgroundColor: ['#c0392b', '#2c6fbb', '#7f8c8d'][i], stack: 'i' })),
      { label: 'Re-graded', data: G.regrade_t, backgroundColor: '#d68910', stack: 'r' }] }, plugins: [marks(H.markers, gl)], options: { scales: { x: { stacked: true }, y: { stacked: true } } } });
    chart('ccV', { type: 'line', data: { labels: gl, datasets: [{ label: '$/t vs futures', data: G.value_new, borderColor: '#2c6fbb', pointRadius: 1.5, spanGaps: true }] }, plugins: [marks(H.markers, gl)] });
    chart('ccS', { type: 'line', data: { labels: SP.months, datasets: [{ label: 'Front − second, % of price', data: SP.s12_pct, borderColor: '#7d3c98', pointRadius: 0 }] },
      plugins: [marks(H.markers.concat(D.rules.changes.filter(r => r.effective_date < '2016').map(r => ({ date: r.effective_date.slice(0, 7), label: r.short }))), SP.months)] });
    chart('ccY', { type: 'bar', data: { labels: SP.same_point.map(r => r.year), datasets: [{ label: `${SP.now.pair}, % of price`, data: SP.same_point.map(r => Math.max(-3, Math.min(3, r.pct))), backgroundColor: SP.same_point.map((r, i) => i === SP.same_point.length - 1 ? '#c0392b' : '#7d3c98') }] },
      options: { scales: { y: { title: { display: true, text: '% (capped at ±3)' } } } } });
  }
  async function flows() {
    body().innerHTML = `<div id="ccCot"></div>`;
    CotDesk.mount($('#ccCot'), ['CC']);
  }

  async function news() {
    body().innerHTML = `<div class="card"><h2>Cocoa news flow</h2><div id="ccNews"></div></div>`;
    Intel.news($('#ccNews'), { tags: ['cocoa'], n: 40, chips: false });
  }

  async function outlook() {
    const O = await getJSON('data/overview/overview.json').catch(() => null);
    const m = O?.markets?.find(x => x.key === 'cocoa');
    body().innerHTML = `<div id="ccOv"></div><p class="note">Same read as the Overview tab; refreshed hourly in trading hours.</p>`;
    if (!m) { $('#ccOv').innerHTML = '<div class="card"><p class="note">Outlook not built yet.</p></div>'; return; }
    // reuse the Overview tile renderer
    const host = document.createElement('div');
    $('#ccOv').appendChild(host);
    Overview.tileInto(host, m);
  }
  return { show };
})();
