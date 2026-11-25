// Sugar tab: public-data panels built by models/sugar_world.py into data/sugar/world.json.
// Brazil cane weather (rain vs normal, estimated harvest-stoppage days, ensemble forecast), Centre-South fortnight scorecard
// and season range, fuel policy; India (crush tracker, crop projection, balance and import need); Europe; expiry deliveries and agency revisions. Outputs only: the rules sit in the model.
const SugarWorld = (() => {
  let W = null;
  const load = () => W ? Promise.resolve(W) : getJSON('data/sugar/world.json').then(d => (W = d));
  const f0 = v => fmt(v, 0), f1 = v => fmt(v, 1), f2 = v => fmt(v, 2);
  const kpi = (lab, v, sub) => `<div class="kpi card" style="padding:10px"><div class="lbl">${lab}</div><div class="val" style="font-size:19px">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const link = (src, url) => url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(src)}</a>` : esc(src);
  const pct = v => v == null ? '–' : sgn(v, 0, '%');
  const age = d => { if (!d) return ''; const n = Math.round((Date.now() - new Date(d + 'T12:00:00')) / 864e5); return n > 30 ? ` <span class="dn">(${n} days old)</span>` : ''; };
  const foot = () => `<p class="note">Built ${W.built} by the desk from public data. Manual-entry rows show their release date and link; anything older than a month is marked.</p>`;

  // ---------- Brazil cane weather, scorecard, range, fuel policy ----------
  function cane(el) {
    const C = W.cane_weather, R = W.range, K = W.scorecard, fc = C.forecast || {};
    const cs = C.rows.find(r => r.id === 'CS');
    const m = (fc.models || {}).ecmwf_ens || (fc.models || {}).gefs;
    const prev = fc.previous && fc.previous.cs && (fc.previous.cs.ecmwf_ens || fc.previous.cs.gefs);
    const fcTxt = m ? `${f0(m.rain_p50)} mm (normal ${f0(m.rain_normal)})` : (fc.fallback ? `${f0(fc.fallback.rain_p50)} mm (normal ${f0(fc.fallback.rain_normal)})` : '–');
    const fcSub = m ? `${m.from} to ${m.to}, ECMWF ENS median; ${f1(m.stop_p50)} stoppage days (normal ${f1(m.stop_normal)})${prev ? `; previous run ${f0(prev.rain_p50)} mm, ${f1(prev.stop_p50)} days` : ''}`
      : (fc.fallback ? `${fc.fallback.from} to ${fc.fallback.to}, ECMWF ENS median (desk ensemble summary); stoppage forecast pending` : '');
    const row = r => `<tr><td class="l">${r.id === 'CS' ? '<b>' + r.name + '</b>' : r.name}</td><td class="n">${r.id === 'CS' ? '' : f1(r.weight) + '%'}</td>
      <td class="n">${f0(r.rain_mtd.now)}</td><td class="n">${f0(r.rain_mtd.avg)}</td><td class="n">${f0(r.rain_mtd.ly)}</td><td class="n">${pct(r.rain_mtd.vs_avg_pct)}</td>
      <td class="n">${f0(r.stop_mtd.now)}</td><td class="n">${f1(r.stop_mtd.avg)}</td>
      <td class="n">${f0(r.rain_atd.now)}</td><td class="n">${f0(r.rain_atd.avg)}</td><td class="n">${pct(r.rain_atd.vs_avg_pct)}</td>
      <td class="n">${f0(r.stop_atd.now)}</td><td class="n">${f1(r.stop_atd.avg)}</td></tr>`;
    const fn = K.fortnight, cu = K.cumulative;
    const sc = (lab, o, d, pctChg = true) => `<tr><td class="l">${lab}</td><td class="n"><b>${fmt(o.now, d)}</b></td><td class="n">${fmt(o.ly, d)}</td><td class="n">${pctChg ? sgn(100 * (o.now / o.ly - 1), 1, '%') : sgn(o.now - o.ly, d)}</td><td class="n">${fmt(o.avg5, d)}</td><td class="n">${pctChg ? sgn(100 * (o.now / o.avg5 - 1), 1, '%') : sgn(o.now - o.avg5, d)}</td></tr>`;
    const cases = ['wet', 'base', 'dry'].map(k => [k, R.cases[k]]);
    const fp = W.fuel_policy || [], fs = W.fuel_sensitivity;
    el.innerHTML = `<div class="grid g4">
        ${kpi(`Rain this month, CS weighted (to ${C.asof})`, f0(cs.rain_mtd.now) + ' mm', `normal ${f0(cs.rain_mtd.avg)} mm (${pct(cs.rain_mtd.vs_avg_pct)}); last year ${f0(cs.rain_mtd.ly)} mm`)}
        ${kpi('Estimated stoppage days this month', f0(cs.stop_mtd.now), `normal ${f1(cs.stop_mtd.avg)}; last year ${f0(cs.stop_mtd.ly)}`)}
        ${kpi('Rain since 1 April', f0(cs.rain_atd.now) + ' mm', `normal ${f0(cs.rain_atd.avg)} mm (${pct(cs.rain_atd.vs_avg_pct)}); stoppage days ${f0(cs.stop_atd.now)} vs ${f1(cs.stop_atd.avg)}`)}
        ${kpi('Next 15 days rain', fcTxt, fcSub)}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Rain and estimated harvest-stoppage days by state</h2><div class="tbl"><table>
          <tr><th class="l" rowspan="2">State</th><th rowspan="2">Weight</th><th colspan="4">This month, mm</th><th colspan="2">Stoppage days</th><th colspan="3">Since 1 April, mm</th><th colspan="2">Stoppage days</th></tr>
          <tr><th>2026</th><th>Normal</th><th>2025</th><th>vs normal</th><th>2026</th><th>Normal</th><th>2026</th><th>Normal</th><th>vs normal</th><th>2026</th><th>Normal</th></tr>
          ${C.rows.map(row).join('')}</table></div>
          <p class="note">ERA5 daily rain (Open-Meteo) at representative points: São Paulo north-east (Ribeirão Preto), west (Araçatuba) and centre (Piracicaba/Jaú), Goiás (Rio Verde), Triângulo Mineiro (Uberaba), Mato Grosso do Sul (Nova Alvorada do Sul), Paraná (Paranavaí). Normal = 2011–2025 average for the same dates. Weights: ${C.weights_from}. <b>Stoppage days are an estimate from rainfall</b>, not reported mill downtime. ${C.rule}</p></div>
        <div class="card"><h2>Cumulative rain this month, Centre-South weighted</h2><div style="position:relative;height:260px"><canvas id="swRain"></canvas></div>
          <p class="note">mm since the 1st. Forecast: ${fc.available ? `ensembles run ${fc.generated}` : 'per-member stoppage forecast pending the first ensemble fetch; rain from the desk\'s ensemble summary'}.</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Centre-South fortnight to ${K.end} (MAPA)</h2><div class="tbl"><table>
          <tr><th class="l"></th><th>This year</th><th>Last year</th><th>Change</th><th>5-yr avg</th><th>vs avg</th></tr>
          <tr><td class="l" colspan="6"><b>Fortnight</b></td></tr>
          ${sc('Cane, mt', fn.cane_mt, 2)}${sc('Sugar, mt', fn.sugar_mt, 2)}${sc('Ethanol incl. corn, bn L', fn.eth_bnl, 2)}${sc('Sugar kg per t cane', fn.kgt, 1, false)}${sc('Sugar share of ATR, %', fn.mix_raw, 1, false)}
          <tr><td class="l" colspan="6"><b>Season to date</b></td></tr>
          ${sc('Cane, mt', cu.cane_mt, 1)}${sc('Sugar, mt', cu.sugar_mt, 2)}${sc('Ethanol incl. corn, bn L', cu.eth_bnl, 2)}${sc('Sugar kg per t cane', cu.kgt, 1, false)}</table></div>
          <p class="note">5-yr average: ${K.seasons_in_avg.join(', ')}. ${K.mix_corn_adjusted != null ? `Cane sugar mix with corn ethanol taken out (desk estimate): <b>${f1(K.mix_corn_adjusted)}%</b>. ` : ''}${K.note} ATR is published by UNICA, not MAPA. <b>UNICA last published: ${K.unica_last_published || K.unica_position}</b>${K.unica_checked ? ` (checked ${K.unica_checked})` : ''}; UNICA has not been publishing regularly this season, so MAPA is the main series here.</p></div>
        <div class="card"><h2>What the public data implies for the season</h2>
          <p>From the fortnight to ${R.from_fortnight} on, under three rain cases for the rest of the harvest:</p>
          <div class="tbl"><table><tr><th class="l">Case</th><th>Stoppage days to 31 Dec</th><th>Cane still to crush, mt</th><th>Season cane, mt</th><th>Season sugar, mt</th><th>Jan–Mar cane, mt</th></tr>
          ${cases.map(([k, c]) => `<tr><td class="l">${k === 'base' ? '<b>Normal</b>' : k === 'wet' ? 'Wet' : 'Dry'}</td><td class="n">${f1(c.stop_days_to_dec31)}</td><td class="n">${f1(c.remaining_cane_mt)}</td><td class="n">${f1(c.season_cane_mt)}</td><td class="n"><b>${f2(c.season_sugar_mt)}</b></td><td class="n">${f1(c.jan_mar_cane_mt)}</td></tr>`).join('')}</table></div>
          <h3>Season sugar (mt) by sugar per tonne of the remaining cane</h3><div class="tbl"><table><tr><th class="l">Case</th>${R.grid_kgt.map(k => `<th>${f1(k)} kg/t</th>`).join('')}</tr>
          ${R.grid.map(g => `<tr><td class="l">${g.case}</td>${g.season_sugar.map(v => `<td class="n">${f2(v)}</td>`).join('')}</tr>`).join('')}</table></div>
          <p class="note">So far ${f1(R.so_far.cane_mt)} mt cane and ${f2(R.so_far.sugar_mt)} mt sugar; last fortnight ${f2(R.last_fortnight.cane_mt)} mt cane at ${f1(R.last_fortnight.kgt)} kg sugar per tonne (central case for the remaining cane: ${f1(R.last_fortnight.kgt_remaining)} kg/t; last season's post-October crush ran nearer the left-hand columns).
          Cross-checks: the desk's pace projection on the crush tab is ${f1(R.checks.desk_pace_projection_cane)} mt cane and ${f2(R.checks.desk_pace_projection_sugar)} mt sugar; Conab's all-Brazil cane estimate (${R.checks.conab_date}) is ${f1(R.checks.conab_brazil_cane)} mt, about ${f1(R.checks.conab_cs_implied)} mt for the Centre-South at its ${f1(R.checks.cs_share_of_brazil_cane)}% share in ${R.checks.cs_share_season}.</p>
          <details><summary>Assumptions (public inputs only)</summary><ul>${R.assumptions.map(a => `<li class="note">${a}</li>`).join('')}</ul></details></div></div>
      <div class="card" style="margin-top:12px"><h2>Brazil fuel policy that moves ethanol parity</h2><div class="tbl"><table><tr><th class="l">From</th><th class="l">Until</th><th class="l">Measure</th><th class="l">Detail</th><th class="l">Why it matters for sugar</th><th class="l">Source</th></tr>
        ${fp.map(r => `<tr><td class="l">${r.date}</td><td class="l">${esc(r.until)}</td><td class="l"><b>${esc(r.item)}</b></td><td class="l">${esc(r.detail)}</td><td class="l">${esc(r.effect_on_ethanol_parity)}</td><td class="l">${link(r.source, r.url)}</td></tr>`).join('')}</table></div>
        ${fs ? `<p class="note">At USD/BRL ${f2(fs.fx)} (${fs.date}), R$1 per litre of hydrous ethanol at the mill is worth <b>${f2(fs.c_lb_per_real_litre)}¢/lb</b> of sugar-equivalent; the R$${fs.subsidy_r_l}/l producer subsidy is about <b>${f2(fs.subsidy_c_lb)}¢/lb</b>. Hydrous parity now ${f2(fs.parity_now)}¢/lb against No. 11 front ${f2(fs.sb_now)}¢ (Ethanol parity tab). Whether mills keep the subsidy or pass it to the pump decides how much of it reaches parity.</p>` : ''}</div>${foot()}`;
    const ch = C.chart;
    chart('swRain', { type: 'line', data: { labels: ch.days.map(d => d.slice(5)), datasets: [
      { label: '2026', data: ch.cur, borderColor: PAL[2], borderWidth: 2.4, pointRadius: 0 },
      { label: '2011–2025 average', data: ch.avg, borderColor: '#7f8c8d', borderDash: [4, 3], borderWidth: 1.4, pointRadius: 0 },
      ...(ch.ly ? [{ label: '2025', data: ch.ly, borderColor: PAL[3], borderWidth: 1.2, pointRadius: 0 }] : [])] },
      options: { scales: { y: { title: { display: true, text: 'mm' } } } } });
  }

  // ---------- India ----------
  function india(el) {
    const I = W.india, P = I.parity, rows = I.releases, inp = P.inputs;
    const prod = rows.filter(r => r.kind === 'production'), pol = rows.filter(r => r.kind === 'policy'), pr = rows.filter(r => r.kind === 'price');
    const dom = P.domestic, sm = prod.find(r => /^all-india/i.test(r.item) && /to date/i.test(r.item));
    el.innerHTML = `<div class="grid g4">
        ${sm ? kpi(`Sugar made to ${sm.date}`, f2(+sm.value) + ' lakh t', `${f2(+sm.prev_value)} lakh t a year ago; ${esc(sm.note)}`) : ''}
        ${kpi('Raw import parity (TRQ, zero duty)', 'Rs ' + f0(P.raw_trq_rs_qtl) + '/qtl', `No. 11 Mar ${f2(inp.sb_mar27_c_lb)}¢ = $${f1(P.raw_usd_t)}/t × ${f2(inp.usd_inr)} INR; ex-freight, before refining`)}
        ${kpi('White import parity, full duty', 'Rs ' + f0(P.white_full_duty_rs_qtl) + '/qtl', `No. 5 Mar $${f1(inp.w_mar27_usd_t)}/t × INR × (1 + ${f0(inp.duty_full_pct)}% duty); at zero duty Rs ${f0(P.white_zero_duty_rs_qtl)}`)}
        ${dom ? kpi('Domestic ex-mill (latest public quote)', 'Rs ' + f0(dom.value) + '/qtl', `${esc(dom.item)}, ${dom.date}${age(dom.date)}`) : ''}</div>
      ${crushCards(I.crush, P)}
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Production by state (ISMA)</h2><div class="tbl"><table><tr><th class="l">As of</th><th class="l">Item</th><th>2026/27</th><th>Year ago</th><th class="l">Note</th><th class="l">Source</th></tr>
          ${prod.map(r => `<tr><td class="l">${r.date}${age(r.date)}</td><td class="l">${esc(r.item)}</td><td class="n"><b>${f2(+r.value)}</b> ${esc(r.unit)}</td><td class="n">${r.prev_value ? f2(+r.prev_value) : '–'}</td><td class="l">${esc(r.note)}</td><td class="l">${link(r.source, r.url)}</td></tr>`).join('')}</table></div>
          <p class="note">ISMA publishes production twice a month in season. Karnataka and other states are added when a release gives them.</p></div>
        <div class="card"><h2>Import parity: what the inputs say</h2>
          <div class="tbl"><table><tr><th class="l">Input</th><th>Value</th><th class="l">Date</th></tr>
          <tr><td class="l">ICE No. 11 Mar 27</td><td class="n">${f2(inp.sb_mar27_c_lb)}¢/lb</td><td class="l">${inp.sb_date}</td></tr>
          <tr><td class="l">ICE No. 5 Mar 27</td><td class="n">$${f1(inp.w_mar27_usd_t)}/t</td><td class="l">${inp.w_date}</td></tr>
          <tr><td class="l">USD/INR (Yahoo)</td><td class="n">${f2(inp.usd_inr)}</td><td class="l">${inp.inr_date}</td></tr>
          <tr><td class="l">Duty on raws inside the TRQ</td><td class="n">0%</td><td class="l">to 31 Mar 2027</td></tr>
          <tr><td class="l">Basic duty outside the TRQ</td><td class="n">${f0(inp.duty_full_pct)}%</td><td class="l">see policy table</td></tr>
          <tr><td class="l">Freight, port, refining</td><td class="n">not included</td><td class="l">no public series</td></tr></table></div>
          ${dom ? `<p>Raw sugar landed under the TRQ before freight and refining is Rs ${f0(P.raw_trq_rs_qtl)}/qtl against a domestic ex-mill quote of Rs ${f0(dom.value)}/qtl (${dom.date}). The gap, Rs ${f0(dom.value - P.raw_trq_rs_qtl)}/qtl, is what freight, refining and the mill margin must fit inside. Outside the TRQ, the 100% duty keeps white imports far above domestic prices.</p>` : ''}
          <p class="note">${esc(P.note)}</p></div></div>
      ${I.prices ? `<div class="card" style="margin-top:12px"><h2>Ex-mill prices by state, ${I.prices.date} (Rs per quintal, excluding GST)</h2><div class="tbl"><table><tr><th class="l">State</th><th class="l">Grade</th><th>Low</th><th>High</th></tr>
        ${I.prices.latest.map(r => `<tr><td class="l">${esc(r.state)}</td><td class="l">${r.grade}</td><td class="n">${f0(r.lo)}</td><td class="n">${f0(r.hi)}</td></tr>`).join('')}</table></div>
        <p class="note">Source: ${link(I.prices.source, I.prices.url)}, collected daily by the desk.</p></div>`
        : `<div class="card" style="margin-top:12px"><p class="note">Daily ex-mill price collector: ${I.collector ? `last run ${I.collector.run}, ${I.collector.pages_with_prices} pages with prices` : 'not run yet'}. Showing the last manual quote.</p></div>`}
      ${histCard(I.history)}
      <div class="card" style="margin-top:12px"><h2>Policy and quotas</h2><div class="tbl"><table><tr><th class="l">Date</th><th class="l">Item</th><th>Value</th><th class="l">Detail</th><th class="l">Source</th></tr>
        ${pol.map(r => `<tr><td class="l">${r.date}</td><td class="l"><b>${esc(r.item)}</b></td><td class="n">${esc(r.value)} ${esc(r.unit === 'date' ? '' : r.unit)}</td><td class="l">${esc(r.note)}</td><td class="l">${link(r.source, r.url)}</td></tr>`).join('')}
        ${pr.map(r => `<tr><td class="l">${r.date}${age(r.date)}</td><td class="l">${esc(r.item)}</td><td class="n">${f0(+r.value)} ${esc(r.unit)}</td><td class="l">${esc(r.note)}</td><td class="l">${link(r.source, r.url)}</td></tr>`).join('')}</table></div>
        <p class="note">Fortnightly sales quotas (DFPD) are entered when the order is published. Weather in the Indian cane belt is on the "Where it's grown" tab.</p></div>${foot()}`;
    crushChart(I.crush);
    const zb = document.getElementById('swCrushZ'), rs = document.getElementById('swCrushReg');
    if (zb) zb.onclick = () => { const z = zb.dataset.z !== '1'; zb.dataset.z = z ? '1' : '0'; zb.textContent = z ? 'Show full season' : 'Show first weeks'; crushChart(I.crush, z); };
    if (rs) rs.onchange = () => crushChart(I.crush, zb ? zb.dataset.z === '1' : undefined);
    const H = I.history;
    if (H && H.n >= 20 && document.getElementById('swInH')) {
      const R = H.rows;
      chart('swInH', { type: 'line', data: { labels: R.map(r => r.date), datasets: [
        { label: 'India ex-mill, Maharashtra S/30', data: R.map(r => r.mh_c), borderColor: PAL[3], borderWidth: 2.2, pointRadius: 0, spanGaps: true },
        { label: 'India ex-mill, Uttar Pradesh M/30', data: R.map(r => r.up_c), borderColor: PAL[1], borderWidth: 1.4, pointRadius: 0, spanGaps: true },
        { label: 'London No. 5 white, front', data: R.map(r => r.w5_c), borderColor: PAL[2], borderWidth: 1.6, pointRadius: 0, spanGaps: true },
        { label: 'NY No. 11 raw, front', data: R.map(r => r.sb_c), borderColor: PAL[0], borderWidth: 1.6, pointRadius: 0, spanGaps: true }] },
        options: { scales: { y: { title: { display: true, text: 'US cents per lb' } } } } });
    }
  }

  // ---------- India crush tracker, season projection, balance and import need ----------
  function crushCards(C, par) {
    if (!C) return '';
    const p = C.projection, B = C.balance, L = C.latest || [];
    const lt = v => v == null ? '–' : f2(v);
    const chg = (a, b) => a != null && b ? sgn(100 * (a / b - 1), 0, '%') : '–';
    const rel = { low: 'early season: crushing pace says little yet, so the range leans on the cane-area estimate', medium: 'mid-season: pace and area estimate carry similar weight', high: 'late season: the crushing pace now drives the projection' };
    const mc = C.mh_crush || [];
    const grid = B ? `<div class="tbl"><table><tr><th class="l">Production case</th><th>Production</th>${B.norms.map(n => `<th>${fmt(n, 1)} months</th>`).join('')}</tr>
        ${B.grid.map(g => `<tr><td class="l">${g.case === 'mid' ? '<b>Mid</b>' : g.case === 'low' ? 'Low' : 'High'}</td><td class="n">${f1(g.production)}</td>${g.need.map((v, i) => `<td class="n">${B.norms[i] === 2.5 && g.case === 'mid' ? '<b>' + f1(Math.max(v, 0)) + '</b>' : f1(Math.max(v, 0))}</td>`).join('')}</tr>`).join('')}</table></div>` : '';
    const E = B && B.economics;
    return `<div class="grid g2" style="margin-top:12px">
      <div class="card"><h2>Crush tracker: sugar made so far, ${C.season} <span class="note">ISMA, to ${C.as_of}</span></h2>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px"><select id="swCrushReg" aria-label="Region"><option value="IN">All India</option><option value="MH">Maharashtra</option></select>
          <button type="button" class="btn" id="swCrushZ" data-z="${C.days_into_season < 120 ? 1 : 0}">${C.days_into_season < 120 ? 'Show full season' : 'Show first weeks'}</button></div>
        <div style="position:relative;height:270px"><canvas id="swCrush"></canvas></div>
        <div class="tbl" style="margin-top:8px"><table><tr><th class="l">To ${C.as_of}</th><th>${C.season}, lakh t</th><th>Mills</th><th>Year ago</th><th>Mills</th><th>Change</th><th>Last season final</th></tr>
          ${L.map(r => `<tr><td class="l">${r.region === 'All India' ? '<b>All India</b>' : r.region}</td><td class="n"><b>${lt(r.now)}</b></td><td class="n">${r.mills ? f0(r.mills) : '–'}</td><td class="n">${lt(r.year_ago)}</td><td class="n">${r.mills_year_ago ? f0(r.mills_year_ago) : '–'}</td><td class="n">${chg(r.now, r.year_ago)}</td><td class="n">${lt(r.final_last_season)}</td></tr>`).join('')}</table></div>
        <p class="note">Season-to-date sugar production (net of any sugar diverted to ethanol) at each ISMA release, by days since 1 October; past seasons for comparison, final production at the right on the full-season view. Maharashtra began crushing on ${C.mh_start} this season, earlier than in any season since 2018/19, so early totals run far ahead of last year without implying a bigger crop. Source of the latest release: ${link(C.source, C.url)}. ISMA publishes twice a month in season; the desk adds each release the day it is reported.</p>
        ${mc.length ? `<h3>Maharashtra cane crushing</h3><div class="tbl"><table><tr><th class="l">As of</th><th>Mills</th><th>Cane crushed, lakh t</th><th>Sugar, lakh t</th><th>Recovery %</th><th class="l">Source</th></tr>
          ${mc.slice(0, 8).map(r => `<tr><td class="l">${r.as_of}${r.season !== C.season ? ` <span class="note">(${r.season})</span>` : ''}</td><td class="n">${r.mills ? f0(r.mills) : '–'}</td><td class="n">${f1(r.cane_lakh_t)}</td><td class="n">${f2(r.sugar_lakh_t)}</td><td class="n">${r.recovery_pct ? f2(r.recovery_pct) : '–'}</td><td class="l">${link(r.source, r.url)}</td></tr>`).join('')}</table></div>
          <p class="note">State figures (Sugar Commissionerate, or NFCSF early in the season) as reported in the press; the Commissionerate's own site is checked each run (${C.collector && C.collector.direct_sources ? Object.entries(C.collector.direct_sources).map(([k, v]) => `${esc(k)}: ${v === 200 ? 'reachable' : 'not reachable from the desk, so news reports of the releases are used'}`).join('; ') : 'first check pending'}).</p>` : ''}
      </div>
      <div class="card"><h2>2026/27 crop: where the crush points</h2>
        ${p ? `<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(130px,1fr))">
          ${kpi('Low', f1(p.low) + ' lakh t', '')}${kpi('<b>Mid</b>', '<b>' + f1(p.mid) + ' lakh t</b>', `${sgn(p.vs_isma_pct, 1, '%')} vs ISMA`)}${kpi('High', f1(p.high) + ' lakh t', '')}</div>
          <div class="tbl" style="margin-top:8px"><table><tr><th class="l"></th><th>Lakh t</th><th class="l">Note</th></tr>
            <tr><td class="l">Desk projection (mid; 80% range)</td><td class="n"><b>${f1(p.mid)}</b></td><td class="l">${f1(p.low)} to ${f1(p.high)}, as of the ${p.as_of} release</td></tr>
            <tr><td class="l">ISMA first estimate (${p.isma_date})</td><td class="n">${f2(p.isma)}</td><td class="l">No sugar to ethanol this season, so gross = net; revision due January 2027</td></tr>
            <tr><td class="l">Last season (2025/26, net)</td><td class="n">${f2(p.last_season_final)}</td><td class="l">after 32.42 lakh t to ethanol</td></tr>
            <tr><td class="l">Made so far</td><td class="n">${f2(p.to_date)}</td><td class="l">${f1(p.share_of_mid_made)}% of the mid projection</td></tr></table></div>
          <p>Reading: ${rel[p.reliability]}. The projection is ${p.vs_isma_pct < -1 ? 'below' : p.vs_isma_pct > 1 ? 'above' : 'in line with'} ISMA's ${f2(p.isma)} lakh t${p.mh_vs_isma ? `. Measured from its early start, Maharashtra's crush pace points ${p.mh_vs_isma === 'in line' ? 'in line with' : p.mh_vs_isma} ISMA's ${f2(p.isma_mh)} lakh t for the state` : ''}${(L.find(r => r.region === 'Uttar Pradesh') || {}).now < (L.find(r => r.region === 'Uttar Pradesh') || {}).year_ago ? '; Uttar Pradesh is behind last year on fewer mills' : ''}.</p>
          <details><summary>Variables used</summary><ul>${C.variables.map(v => `<li class="note">${esc(v)}</li>`).join('')}</ul></details>` : '<p class="note">Projection needs a release with all-India and Maharashtra figures.</p>'}
      </div></div>
      ${B ? `<div class="grid g2" style="margin-top:12px">
      <div class="card"><h2>2026/27 balance (Oct–Sep) and import need</h2>
        <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">${kpi('Imports needed (mid)', f1(B.need_mid) + ' lakh t', `to end the season at 2.5 months of consumption; range ${f1(Math.max(B.need_low, 0))} to ${f1(B.need_high)}`)}
          ${kpi('Duty-free quota left', f1(B.trq_left) + ' lakh t', `${f0(B.trq_quota)} lakh t TRQ, about ${f1(B.trq_used)} used by ${B.trq_used_date}; deadline 31 Mar 2027`)}
          ${kpi('Need beyond the quota', f1(B.need_vs_trq_left) + ' lakh t', 'mid case, at full duty unless the quota is widened')}</div>
        <div class="tbl" style="margin-top:8px"><table><tr><th class="l">Item</th><th>Lakh t</th><th class="l">Note</th><th class="l">Source</th></tr>
          ${B.rows.map(r => `<tr><td class="l">${esc(r.item)}</td><td class="n"><b>${f1(r.value)}</b></td><td class="l">${esc(r.note)}</td><td class="l">${r.url ? link(r.source, r.url) : esc(r.source)}</td></tr>`).join('')}</table></div>
        <h3>Imports needed (lakh t) by closing stock and crop size</h3>${grid}
        <p class="note">Closing stock in months of consumption at ${f0(B.rows[2].value)} lakh t a year. Zero means the crop alone reaches that stock. If only the unused part of the duty-free quota arrives, the season ends with about <b>${f1(B.closing_if_trq_only)} lakh t</b> (${f1(B.closing_if_trq_only_months)} months of consumption).</p></div>
      <div class="card"><h2>Do imports pay?</h2>
        ${E ? `<div class="tbl"><table><tr><th class="l"></th><th>Rs per quintal</th></tr>
          <tr><td class="l">Raw sugar landed under the TRQ (zero duty), before freight and refining</td><td class="n">${f0(E.raw_trq_rs_qtl)}</td></tr>
          <tr><td class="l">${esc(E.domestic_item)} (${E.domestic_date})</td><td class="n">${f0(E.domestic_rs_qtl)}</td></tr>
          <tr><td class="l"><b>Room for freight, refining and margin</b></td><td class="n"><b>${f0(E.gap_rs_qtl)}</b></td></tr>
          ${E.white_full_duty_rs_qtl ? `<tr><td class="l">White sugar at full duty (outside the quota)</td><td class="n">${f0(E.white_full_duty_rs_qtl)}</td></tr>` : ''}</table></div>
          <p>Inside the quota, imported raws have Rs ${f0(E.gap_rs_qtl)}/qtl below the domestic ex-mill price to cover ocean freight, port, refining and margin; outside it, the full duty prices imports far above the home market, so any need beyond the quota requires a policy change (wider quota or lower duty) rather than price alone. Same inputs as the import-parity table below.</p>` : '<p class="note">Import parity needs the latest No. 11, USD/INR and a domestic ex-mill quote.</p>'}
        <h3>2027/28</h3><p>${esc(B.next_season.text)}</p></div></div>` : ''}`;
  }

  function crushChart(C, zoom) {
    const el = document.getElementById('swCrush');
    if (!C || !el) return;
    zoom = zoom ?? (C.days_into_season < 120);
    const reg = (document.getElementById('swCrushReg') || {}).value || 'IN';
    const P = reg === 'MH' ? C.chart.mh_points : C.chart.points, ss = Object.keys(P).filter(x => P[x].length).sort(), past = ss.filter(x => x !== C.season);
    const pc = ['#d0d0d0', '#b8b8b8', '#9a9a9a', PAL[5], PAL[3], PAL[2]].slice(-past.length);
    const xmax = zoom ? Math.max(92, C.days_into_season + 30) : 364;
    const day = t => { const d = new Date(Date.UTC(2001, 9, 1) + t * 864e5); return d.getUTCDate() + ' ' + MON[d.getUTCMonth()]; };
    const data = x => P[x].filter(q => q[0] <= xmax).map(q => ({ x: q[0], y: q[1] }));
    chart('swCrush', { type: 'line', data: { datasets: ss.map(x => x === C.season
      ? { label: x, data: data(x), borderColor: PAL[1], backgroundColor: PAL[1], borderWidth: 3, pointRadius: 3.5 }
      : { label: x, data: data(x), borderColor: pc[past.indexOf(x)], backgroundColor: pc[past.indexOf(x)], borderWidth: 1.4, pointRadius: 1.5 }) },
      options: { interaction: { mode: 'nearest', intersect: false },
        plugins: { tooltip: { callbacks: { title: it => it.length ? (it[0].parsed.x >= 364 ? 'Season final' : day(it[0].parsed.x)) : '' } } },
        scales: { x: { type: 'linear', min: 0, max: xmax, ticks: { stepSize: zoom ? 15 : 30.5, callback: v => v >= 364 ? 'Final' : day(Math.round(v)) } },
                  y: { min: 0, title: { display: true, text: 'lakh tonnes, season to date' } } } } });
  }

  function histCard(H) {
    if (!H || !H.rows || !H.rows.length) return '';
    const wk = H.weekly.slice(-26).reverse();
    const gp = v => v == null ? '–' : sgn(v, 2);
    return `<div class="card" style="margin-top:12px"><h2>Indian domestic sugar in ¢/lb against New York and London <span class="note">${H.first} to ${H.last}</span></h2>
      ${H.n >= 20 ? '<div style="position:relative;height:300px"><canvas id="swInH"></canvas></div>' : ''}
      <div class="tbl" style="margin-top:8px"><table><tr><th class="l">Date</th><th>Maharashtra S/30, Rs/qtl</th><th>USD/INR</th><th>Maharashtra, ¢/lb</th><th>UP M/30, ¢/lb</th><th>No. 11 front, ¢/lb</th><th>No. 5 front, ¢/lb</th><th>India − No. 5</th><th>India − No. 11</th></tr>
        ${wk.map(r => `<tr><td class="l">${r.date}</td><td class="n">${f0(r.mh_rs)}</td><td class="n">${f2(r.inr)}</td><td class="n"><b>${f2(r.mh_c)}</b></td><td class="n">${f2(r.up_c)}</td><td class="n">${f2(r.sb_c)}</td><td class="n">${f2(r.w5_c)}</td><td class="n">${gp(r.gap_w5)}</td><td class="n">${gp(r.gap_sb)}</td></tr>`).join('')}</table></div>
      <p class="note">Last quote of each week, newest first${H.weekly.length > 26 ? ' (latest 26 weeks; the chart has every day)' : ''}. Ex-mill prices are per quintal (100 kg) excluding GST, at the mid of the quoted range; converted as Rs per quintal ÷ rupees per dollar ÷ 220.462 lb × 100. London No. 5 is in $/t ÷ 22.046.
        <b>How to read the gap:</b> India − No. 5 below zero means Indian white sugar at the mill is cheaper than London whites, so exports start to pay (before inland freight, port costs and the discount Indian plantation white takes against refined No. 5 quality); above zero, the home market pays more than the world and mills prefer to sell at home, even with an export quota. India − No. 11 shows how far domestic prices sit above the raw-sugar world price. Sources: ${esc(H.sources)}; history is added on every run of the collector.</p></div>`;
  }

  // ---------- Europe ----------
  function europe(el) {
    const E = W.europe, ec = E.ec || [], bw = E.beet_weather || [], pr = E.prices || [];
    const rv = r => `<tr><td class="l">${r.release_date}${age(r.release_date)}</td><td class="l">${esc(r.item)} ${r.season}</td><td class="n"><b>${f2(+r.value)}</b> ${r.unit}</td><td class="n">${r.prev_value !== '' ? f2(+r.prev_value) : '–'}</td><td class="l">${r.prev_release}</td><td class="n">${r.prev_value !== '' ? sgn(r.value - r.prev_value, 2) : '–'}</td><td class="l">${esc(r.note)}</td><td class="l">${link(r.source, r.url)}</td></tr>`;
    const sm = x => x == null ? '–' : fmt(x, 3);
    el.innerHTML = `<div class="grid g2">
        <div class="card"><h2>European Commission balance: what changed</h2><div class="tbl"><table><tr><th class="l">Release</th><th class="l">Item</th><th>Latest</th><th>Previous</th><th class="l">Previous release</th><th>Revision</th><th class="l">Note</th><th class="l">Source</th></tr>${ec.map(rv).join('')}</table></div>
          <p class="note">Revisions, not levels: each agency's balance differs, the direction of its changes is what the market trades.</p></div>
        <div class="card"><h2>EU white sugar price vs London No. 5</h2><div class="tbl"><table><tr><th class="l">Month</th><th>EU average €/t</th><th>Region 1</th><th>Region 2</th><th>Region 3</th><th>No. 5 front in €/t</th><th>EU over No. 5</th><th class="l">Source</th></tr>
          ${pr.map(p => `<tr><td class="l">${p.month}</td><td class="n"><b>${f0(p.eu_avg)}</b></td><td class="n">${f0(p.r1)}</td><td class="n">${f0(p.r2)}</td><td class="n">${f0(p.r3)}</td><td class="n">${f0(p.no5_eur)}</td><td class="n">${sgn(p.premium_eur, 0)}</td><td class="l">${link('EC price reporting, released ' + p.released, p.url)}</td></tr>`).join('')}</table></div>
          <p class="note">No. 5 = monthly average of the front contract (TradingView) converted at the month's average EUR/USD (Yahoo). Region 1: AT, CZ, DK, FI, HU, LT, PL, SE, SK; Region 2: BE, DE, FR, NL; Region 3: ES, HR, IT, RO. The EC publishes each month's price with about a six-week lag.</p></div></div>
      <div class="card" style="margin-top:12px"><h2>Beet regions: October rain and soil moisture</h2><div class="tbl"><table>
        <tr><th class="l" rowspan="2">Region</th><th colspan="4">October rain, mm</th><th colspan="4">Root-zone soil moisture (28–100 cm), m³/m³</th><th colspan="2">Last 30 days rain, mm</th></tr>
        <tr><th>2026</th><th>2025</th><th>2021–25</th><th>2011–25</th><th>2026</th><th>2025</th><th>2021–25</th><th>2011–25</th><th>Now</th><th>Normal</th></tr>
        ${bw.map(r => `<tr><td class="l">${esc(r.name)}</td><td class="n"><b>${f0(r.rain?.oct_2026)}</b></td><td class="n">${f0(r.rain?.oct_2025)}</td><td class="n">${f0(r.rain?.avg_2021_25)}</td><td class="n">${f0(r.rain?.avg_2011_25)}</td>
          <td class="n"><b>${sm(r.sm100?.oct_2026)}</b></td><td class="n">${sm(r.sm100?.oct_2025)}</td><td class="n">${sm(r.sm100?.avg_2021_25)}</td><td class="n">${sm(r.sm100?.avg_2011_25)}</td><td class="n">${f0(r.rain30?.now)}</td><td class="n">${f0(r.rain30?.avg_2011_25)}</td></tr>`).join('') || '<tr><td class="note">Beet-region history is fetched on the first workflow run.</td></tr>'}</table></div>
        <p class="note">ERA5 / ERA5-Land via Open-Meteo, one representative point per beet area (France north and centre, Lower Saxony, Saxony-Anhalt, Kujawy, Flevoland, Hesbaye, Haná). Late-season rain matters for lifting and for the sugar content of beet still in the ground; root-zone moisture shows how much of the summer drought is left. The JRC MARS bulletin (monthly) gives the official beet-yield forecast.</p></div>${foot()}`;
  }

  // ---------- deliveries and revisions ----------
  function deliveries(el) {
    const D = W.deliveries || [], R = W.revisions || [];
    const t = v => v ? fmt(+v / 1000, 0) + 'k t' : '–';
    el.innerHTML = `<div class="grid g2">
        <div class="card"><h2>Expiry deliveries, No. 11 and No. 5</h2><div class="tbl"><table><tr><th class="l">Contract</th><th class="l">Expiry</th><th>Tonnes</th><th>Lots</th><th class="l">Status</th><th class="l">Deliverers</th><th class="l">Receivers</th><th class="l">Source</th></tr>
          ${D.map(r => `<tr><td class="l"><b>${esc(r.contract)}</b></td><td class="l">${r.expiry_date}</td><td class="n">${t(r.tonnes)}</td><td class="n">${r.lots ? f0(+r.lots) : '–'}</td><td class="l">${esc(r.status)}</td><td class="l">${esc(r.deliverers)}</td><td class="l">${esc(r.receivers)}</td><td class="l">${link(r.source + (r.source_date ? ', ' + r.source_date : ''), r.url)}</td></tr>`).join('')}</table></div>
          <p class="note">Tonnages from news reports of the tender (most are preliminary trade figures published the day after expiry); ICE's own delivery reports confirm them later. A large delivery with one natural receiver (a refiner) is absorbed; a large delivery that has to be resold weighs on the next spread. History is added expiry by expiry.</p></div>
        <div class="card"><h2>What the agencies changed at their latest update</h2><div class="tbl"><table><tr><th class="l">Agency</th><th class="l">Item</th><th>Season</th><th>Latest</th><th class="l">Released</th><th>Previous</th><th class="l">Released</th><th>Change</th><th class="l">Source</th></tr>
          ${R.map(r => `<tr><td class="l"><b>${esc(r.agency)}</b></td><td class="l">${esc(r.item)}</td><td>${r.season}</td><td class="n">${f2(+r.value)} ${r.unit}</td><td class="l">${r.release_date}${age(r.release_date)}</td><td class="n">${r.prev_value !== '' ? f2(+r.prev_value) : '–'}</td><td class="l">${r.prev_release}</td><td class="n">${r.prev_value !== '' ? sgn(r.value - r.prev_value, 2) : '–'}</td><td class="l">${link(r.source, r.url)}${r.note ? `<div class="note">${esc(r.note)}</div>` : ''}</td></tr>`).join('')}</table></div>
          <p class="note">Shown as changes because each agency's level differs. USDA's country-by-country revisions appear on the World balance tab after each PSD update (May and November).</p></div></div>${foot()}`;
  }

  async function mount(el, k) {
    await load();
    ({ cane, india, europe, deliveries })[k](el);
  }
  return { mount };
})();
