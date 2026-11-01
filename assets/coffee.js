// Coffee section: same tab layout as cotton and sugar. Brazil physical basis ladder, certified stocks and the Antwerp
// signal, the arabica/robusta arb, Colombia, Vietnam, ICO and the world balance come from coffee/data/coffee.json
// (built by coffee/scripts/build.py); COT, spreads/vol, seasonality and technicals use the desk modules with KC.
const Coffee = (() => {
  let built = false, tab = 'kc-primer', K = null;
  const TABS = [['kc-primer', 'Primer'], ['kc-geo', "Where it's grown, trade &amp; weather"], ['kc-bal', 'World balance'], ['kc-br', 'Brazil: basis ladder &amp; exports'], ['kc-cecafe', 'Cecafé daily registrations'], ['kc-wx', 'Brazil weather by production'],
    ['kc-certs', 'Certified stocks &amp; structure'], ['kc-arb', 'Arabica / robusta'], ['kc-orig', 'Colombia, Vietnam &amp; ICO'],
    ['kc-flows', 'Futures, options &amp; COT'], ['kc-rv', 'Spreads &amp; vol'], ['kc-outlook', 'Outlook'], ['kc-seas', 'Seasonality &amp; technicals']];
  const body = () => $('#kcBody');
  const f0 = v => fmt(v, 0), f1 = v => fmt(v, 1), f2 = v => fmt(v, 2);
  const ord = p => p == null ? '–' : `${f0(p)}th pct`;
  const load = () => K ? Promise.resolve(K) : getJSON('coffee/data/coffee.json').then(d => (K = d));
  function shell() {
    $('#coffee').innerHTML = `<nav class="tabs" id="kcTabs">${TABS.map(([k, l], i) => `<button data-t="${k}" class="${k === tab ? 'on' : ''}">${i + 1} · ${l}</button>`).join('')}</nav><main><div id="kcBody"></div></main>`;
    $$('#kcTabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; $$('#kcTabs button').forEach(x => x.classList.toggle('on', x === b)); render(); });
  }
  function show() {
    if (!built) { shell(); built = true; }
    const h = location.hash.slice(1); if (TABS.some(t => t[0] === h)) { tab = h; $$('#kcTabs button').forEach(x => x.classList.toggle('on', x.dataset.t === tab)); }
    render();
  }
  const guard = fn => async () => { try { await fn(); } catch (e) { console.error(e); body().innerHTML = '<div class="card"><p class="note">This tab failed to load.</p></div>'; } };
  function render() {
    history.replaceState(null, '', '#' + tab);
    body().innerHTML = '<div class="card"><p class="note">Loading…</p></div>';
    ({ 'kc-primer': primer, 'kc-geo': () => Geo.mount(body(), 'coffee'), 'kc-bal': guard(balance), 'kc-br': guard(brazil), 'kc-certs': guard(certs), 'kc-cecafe': guard(cecafe), 'kc-wx': guard(weather),
      'kc-arb': guard(arb), 'kc-orig': guard(origins), 'kc-flows': guard(flows), 'kc-rv': () => RVView.mount(body(), 'KC'),
      'kc-outlook': guard(outlook), 'kc-seas': () => MktStudy.mount(body(), ['KC']) })[tab]();
  }
  const kpi = (lab, v, sub) => `<div class="kpi card" style="padding:10px"><div class="lbl">${lab}</div><div class="val" style="font-size:19px">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
  const box = (id, h = 280) => `<div style="position:relative;height:${h}px"><canvas id="${id}"></canvas></div>`;
  const asof = () => `<p class="note">Coffee data built ${K.built}. Sources: ICE and B3 futures (TradingView), Notícias Agrícolas / CEPEA (Brazil physical), Cecafé and MDIC/SECEX (Brazil exports), FNC (Colombia), Vietnam local prices, ICO (prices, exports, certified stocks), CFTC, USDA FAS PSD.</p>`;
  const since = (dates, yrs) => { const c = new Date(); c.setFullYear(c.getFullYear() - yrs); const s = c.toISOString().slice(0, 10); return Math.max(0, dates.findIndex(d => d >= s)); };

  function primer() {
    body().innerHTML = Specs.slot('coffee') + `<div class="grid g2">
      <div class="card"><h2>ICE Coffee C (KC)</h2><div class="tbl"><table>
        <tr><td>Size</td><td class="l">37,500 lb (≈283 bags of 60 kg) of washed arabica</td></tr><tr><td>Quote / tick</td><td class="l">¢/lb; 0.05¢ = $18.75</td></tr>
        <tr><td>Months</td><td class="l">Mar, May, Jul, Sep, Dec</td></tr>
        <tr><td>Delivery</td><td class="l">Certified washed arabica from 19 origins in ICE-licensed warehouses (New York, New Orleans, Houston, Miami, Antwerp, Hamburg/Bremen, Barcelona). Origin and port differentials apply; semi-washed Brazil has been deliverable since 2024.</td></tr>
        <tr><td>Notice / last trade</td><td class="l">First notice 7 business days before the delivery month; options expire on the second Friday of the month before. Low certified stocks make the spot month a squeeze risk.</td></tr>
        <tr><td>Robusta</td><td class="l">ICE London (RC), $/t, Jan/Mar/May/Jul/Sep/Nov. Vietnam, Brazil conilon, Indonesia and Uganda supply it; roasters swap between the two when the arb moves.</td></tr></table></div>
        <h3>Calendar</h3><p>Brazil harvests April–September (conilon first, then arabica); its September–November flowering sets next year's crop, and June–August frost in South Minas and Paraná can damage two crops at once. Vietnam harvests November–January, Colombia's main crop October–January with a mitaca in April–June, Central America November–March. The ICO coffee year runs October–September.</p></div>
      <div class="card"><h2>What moves coffee</h2><div class="tbl"><table><tr><th class="l">Driver</th><th class="l">Mechanism</th><th class="l">Where on this desk</th></tr>
        <tr><td class="l">Brazil crop</td><td class="l">Brazil is ~40% of world output. Arabica alternates big and small ("on/off") years; rain at flowering and frost decide the next crop.</td><td class="l">Brazil, weather</td></tr>
        <tr><td class="l">Certified stocks</td><td class="l">Coffee graded and stored in ICE warehouses is what the futures deliver. Low certs keep the curve inverted and the spot month tight; rising certs ease it.</td><td class="l">Certified stocks &amp; structure</td></tr>
        <tr><td class="l">Physical basis</td><td class="l">The discount Brazilian and other origins sell at under KC. A widening discount means physical is plentiful and futures are rich; a narrowing one means origin is holding back.</td><td class="l">Brazil basis ladder</td></tr>
        <tr><td class="l">Arabica/robusta arb</td><td class="l">When arabica is expensive against robusta, roasters blend in more robusta, cutting arabica demand (and the reverse).</td><td class="l">Arabica / robusta</td></tr>
        <tr><td class="l">Currencies</td><td class="l">A weaker real or peso raises local-currency prices and encourages farmer selling; a stronger one slows it.</td><td class="l">Brazil, Colombia</td></tr>
        <tr><td class="l">Funds and trade hedging</td><td class="l">Managed money swings; producer/merchant short hedges fall when prices are high and margin calls hurt, which thins liquidity.</td><td class="l">Futures, options &amp; COT</td></tr></table></div></div></div>`;
  }

  async function balance() {
    await load();
    const P = K.psd, W = P.World, n = W.years.length - 1, yl = y => `${y}/${String(y + 1).slice(2)}`;
    const ctry = ['Brazil', 'Vietnam', 'Colombia', 'Indonesia', 'Ethiopia', 'Honduras', 'Uganda', 'India'];
    const d = (c, k) => P[c][k][n] - P[c][k][n - 1];
    const est = (K.estimates || []).slice().sort((a, b) => a.country.localeCompare(b.country) || b.date.localeCompare(a.date));
    body().innerHTML = `<div class="grid g4">${kpi(`World production ${yl(W.years[n])}`, f1(W.prod[n]) + 'm bags', `${sgn(d('World', 'prod'), 1)}m on the year; arabica ${f1(W.ara[n])}, robusta ${f1(W.rob[n])}`)}
        ${kpi('World consumption', f1(W.cons[n]) + 'm bags', `${sgn(d('World', 'cons'), 1)}m`)}
        ${kpi('Surplus (prod − cons)', sgn(W.prod[n] - W.cons[n], 1) + 'm', `last year ${sgn(W.prod[n - 1] - W.cons[n - 1], 1)}m`)}
        ${kpi('Ending stocks', f1(W.end[n]) + 'm bags', `${f1(100 * W.end[n] / W.cons[n])}% of use; last year ${f1(100 * W.end[n - 1] / W.cons[n - 1])}%`)}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>World arabica and robusta output, consumption and stocks</h2>${box('kcW', 300)}<p class="note">USDA PSD, million 60-kg bags, green bean equivalent; marketing years as USDA reports them.</p></div>
        <div class="card"><h2>Main producers, ${yl(W.years[n])}</h2><div class="tbl"><table><tr><th class="l">Country</th><th>Production</th><th>±</th><th>Arabica</th><th>Robusta</th><th>Exports</th><th>±</th><th>Ending stocks</th></tr>
          ${ctry.map(c => `<tr><td class="l">${c}</td><td class="n">${f1(P[c].prod[n])}</td><td class="n">${sgn(d(c, 'prod'), 1)}</td><td class="n">${f1(P[c].ara[n])}</td><td class="n">${f1(P[c].rob[n])}</td><td class="n">${f1(P[c].exp[n])}</td><td class="n">${sgn(d(c, 'exp'), 1)}</td><td class="n">${f1(P[c].end[n])}</td></tr>`).join('')}</table></div>
          ${box('kcP', 200)}</div></div>
      <div class="card" style="margin-top:12px"><h2>Latest estimates from the trade and agencies</h2><div class="tbl"><table><tr><th class="l">Country</th><th>Season</th><th class="l">Item</th><th>Value</th><th class="l">Source</th><th>Date</th></tr>
        ${est.map(e => `<tr><td class="l">${e.country}</td><td>${e.season}</td><td class="l">${e.item}</td><td class="n"><b>${f2(e.value)}</b> ${e.unit}</td><td class="l">${e.url ? `<a href="${e.url}" target="_blank" rel="noopener">${e.source}</a>` : e.source}</td><td>${e.date}</td></tr>`).join('')}</table></div></div>${asof()}`;
    const lab = W.years.map(yl);
    chart('kcW', { type: 'bar', data: { labels: lab, datasets: [{ label: 'Arabica', data: W.ara, backgroundColor: '#7d3c98', stack: 'p' }, { label: 'Robusta', data: W.rob, backgroundColor: '#d68910', stack: 'p' },
      { type: 'line', label: 'Consumption', data: W.cons, borderColor: '#2c6fbb', pointRadius: 0 }, { type: 'line', label: 'Ending stocks', data: W.end, borderColor: '#c0392b', borderDash: [4, 3], pointRadius: 0 }] },
      options: { scales: { x: { stacked: true }, y: { stacked: true } } } });
    chart('kcP', { type: 'line', data: { labels: lab, datasets: ctry.slice(0, 4).map((c, q) => ({ label: c, data: P[c].prod, borderColor: PAL[q], pointRadius: 0, borderWidth: 1.6 })) } });
  }

  async function brazil() {
    await load();
    const B = K.brazil, L = B.ladder, LH = B.ladder_hist, E = K.br_exports, BE = E.belgium, Q = B.quotes, cy = E.cy[E.cur_cy], py = E.cy[E.cur_cy - 1], m = cy.n - 1;
    const qtab = (t, q, cur) => q ? `<h3>${t} <span class="note">${q.date}</span></h3><div class="tbl"><table><tr><th class="l">Place</th><th>R$/bag</th><th>1 week ago</th><th>${cur}</th></tr>
      ${q.rows.map(r => `<tr><td class="l">${r.place}</td><td class="n">${f0(r.brl)}</td><td class="n">${f0(r.brl_1w)}</td><td class="n">${fmt(r.usd, 1)}</td></tr>`).join('')}</table></div>` : '';
    body().innerHTML = `<div class="grid g4">
        ${L.map(x => kpi(x.name.replace(/ —.*| \(.*/, ''), sgn(x.basis, 1, '¢'), `under KC; 1-yr avg ${sgn(x.avg1y, 1, '¢')}, ${ord(x.pct)} of 5 yrs`)).slice(0, 4).join('')}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Brazil arabica basis ladder by quality</h2><div class="tbl"><table><tr><th class="l">Quality</th><th>Date</th><th>¢/lb</th><th>Basis to KC front</th><th>1-yr average</th><th>5-yr rank</th></tr>
          ${L.map(x => `<tr><td class="l">${x.name}</td><td>${x.date}</td><td class="n">${f1(x.c_lb)}</td><td class="n"><b>${sgn(x.basis, 1, '¢')}</b></td><td class="n">${sgn(x.avg1y, 1, '¢')}</td><td class="n">${ord(x.pct)}</td></tr>`).join('')}</table></div>
          <p class="note">Local prices (R$ per 60-kg bag) converted to ¢/lb at the day's real. Basis = physical minus the KC front month. A low rank (wide discount) means Brazilian physical is plentiful or farmers are selling; a high rank means origin is tight. Fine-cup export differentials are not published freely; B3's 4/5 good-cup contract is the closest public benchmark.</p></div>
        <div class="card"><h2>Basis history</h2>${box('kcLad', 300)}</div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Brazil coffee exports by crop year (Jul–Jun)</h2>${box('kcEx', 260)}
          <p class="note">${E.cur_cy}/${String(E.cur_cy + 1).slice(2)} to ${E.last}: <b>${f2(cy.cum[m])}m bags</b> against ${f2(py.cum[m])}m a year earlier (${sgn(100 * (cy.cum[m] / py.cum[m] - 1), 1, '%')}). MDIC/SECEX, all forms, million bags.</p></div>
        <div class="card"><h2>Green coffee to Belgium: the Antwerp certification signal</h2>${box('kcBel', 260)}
          <p class="note">${BE.now.months}: ${f0(BE.now.last3)}k bags, ${sgn(BE.now.vs_avg, 0, '%')} against the same months' prior three-year average, ${f1(BE.now.share)}% of Brazil's green exports. Antwerp holds ICE certified warehouses, so a surge to Belgium tends to come before certified-stock builds.</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Top destinations this crop year</h2><div class="tbl"><table><tr><th class="l">Country</th><th>m bags</th><th>Same time last year</th><th>Change</th></tr>
          ${E.dest.map(r => `<tr><td class="l">${r.country}</td><td class="n">${f2(r.bags)}</td><td class="n">${f2(r.prev)}</td><td class="n">${sgn(r.bags - r.prev, 2)}</td></tr>`).join('')}</table></div></div>
        <div class="card"><h2>Co-operative and port quotes</h2>${qtab('Arabica tipo 6 (co-ops)', Q.coop_arabica, 'US$/bag')}${qtab('Semi-washed (cereja descascado)', Q.coop_cd, 'US$/bag')}${qtab('Conilon, Vitória', Q.vitoria_conillon, 'US$/t')}</div></div>${asof()}`;
    const i0 = since(LH.dates, 4);
    chart('kcLad', { type: 'line', data: { labels: LH.dates.slice(i0), datasets: [['icf', 'B3 4/5 good cup'], ['cd', 'Semi-washed'], ['t6', 'Tipo 6'], ['cepea', 'CEPEA tipo 6']]
      .map(([k, l], q) => ({ label: l, data: LH[k].slice(i0), borderColor: PAL[q], pointRadius: 0, borderWidth: 1.4, spanGaps: true })) }, options: { scales: { y: { title: { display: true, text: '¢/lb vs KC' } } } } });
    const ys = Object.keys(E.cy).map(Number).sort().slice(-5), ML = ['Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];
    chart('kcEx', { type: 'line', data: { labels: ML, datasets: ys.map((y, q) => ({ label: `${y}/${String(y + 1).slice(2)}`, data: E.cy[y].cum, borderColor: PAL[q], borderWidth: y === E.cur_cy ? 2.6 : 1.2, pointRadius: 0 })) } });
    const j0 = Math.max(0, BE.ym.length - 36);
    chart('kcBel', { type: 'bar', data: { labels: BE.ym.slice(j0), datasets: [{ label: 'Brazil green to Belgium, k bags', data: BE.bags.slice(j0), backgroundColor: '#7d3c98' },
      { type: 'line', label: 'Prior 3-yr avg', data: BE.avg3.slice(j0), borderColor: '#7f8c8d', borderDash: [5, 4], pointRadius: 0 }] } });
  }

  // ---------- Cecafé daily ----------
  async function cecafe() {
    const C = await getJSON('data/coffee/cecafe.json').catch(() => null);
    if (!C) { body().innerHTML = '<div class="card"><p class="note">Cecafé daily registrations not collected yet; they start with the first daily run.</p></div>'; return; }
    const T = [['arabica', 'Arabica'], ['conilon', 'Conilon'], ['soluble', 'Soluble'], ['total', 'Total']];
    const k = v => v == null ? '–' : fmt(v / 1000, 0) + 'k', S = C.same_point_prev_month, P = C.prev_month_total;
    const mn = m => { const [y, mo] = m.split('-'); return MON[+mo - 1] + ' ' + y; };
    body().innerHTML = `<div class="grid g4">${T.map(([t, l]) => kpi(`${l}, ${mn(C.month)} to ${C.asof.slice(8)}th`, k(C.mtd[t]) + ' bags',
        `today ${k(C.day[t])}; ${S ? `same point of ${mn(C.prev_month)} ${k(S[t])} (${sgn(100 * (C.mtd[t] / S[t] - 1), 0, '%')})` : `all of ${mn(C.prev_month)} ${k(P[t])}`}`)).join('')}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Month-to-date registrations by type</h2><div style="position:relative;height:280px"><canvas id="kcCe"></canvas></div>
          <p class="note">Certificates of origin issued, 60-kg bags, cumulative through the month (one point per Cecafé report). Dotted: previous months. History starts ${C.history_from}; the page shows only the latest day, so the desk stores each day as it comes.</p></div>
        <div class="card"><h2>${mn(C.month)} by port of shipment</h2><div class="tbl"><table><tr><th class="l">Port / unit</th>${T.map(([, l]) => `<th>${l}</th>`).join('')}</tr>
          ${C.ports_mtd.map(r => `<tr><td class="l">${r.unit}</td>${T.map(([t]) => `<td class="n">${k(r[t])}</td>`).join('')}</tr>`).join('')}</table></div>
          <h3>Completed months</h3><div class="tbl"><table><tr><th class="l">Month</th>${T.map(([, l]) => `<th>${l}</th>`).join('')}</tr>
          ${Object.entries(C.finals).reverse().slice(0, 12).map(([m, r]) => `<tr><td class="l">${mn(m)}</td>${T.map(([t]) => `<td class="n">${k(r[t])}</td>`).join('')}</tr>`).join('')}</table></div></div></div>
      <p class="note">Source: <a href="${C.source}" target="_blank" rel="noopener">Cecafé, Resumo Diário</a>; ${C.measure}. Registrations lead shipments by days to weeks; SECEX shipment data are on the Brazil tab. Updated ${C.generated}.</p>`;
    const ms = Object.keys(C.path).sort().slice(-3);
    chart('kcCe', { type: 'line', data: { labels: Array.from({ length: 31 }, (_, i) => i + 1), datasets: ms.flatMap((m, q) => [['arabica', '#7d3c98'], ['conilon', '#d68910']].map(([t, col]) => ({
      label: `${t} ${mn(m)}`, data: C.path[m].day.map((d, i) => d ? { x: d, y: C.path[m][t][i] } : null).filter(Boolean), borderColor: col, borderDash: m === C.month ? [] : [3, 3],
      borderWidth: m === C.month ? 2.4 : 1.1, pointRadius: m === C.month ? 2 : 0, parsing: false }))) },
      options: { scales: { x: { type: 'linear', min: 1, max: 31 } } } });
  }

  // ---------- production-weighted weather ----------
  async function weather() {
    const W = await getJSON('data/coffee/weather_weighted.json').catch(() => null);
    if (!W) { body().innerHTML = '<div class="card"><p class="note">Weighted coffee weather not built yet.</p></div>'; return; }
    const H = await getCSV('data/coffee/weather_weighted_hist.csv').catch(() => []);
    const pc = v => v == null ? '–' : fmt(v, 0) + '%';
    const card = (t, lab) => { const X = W.types[t]; return `<div class="card"><h2>${lab}: weather weighted by Conab production</h2>
      <div class="grid g3">${kpi('Last 30 days rain', pc(X.r30_pct_normal), 'of the 2011–25 average')}${kpi('Last 90 days', pc(X.r90_pct_normal), 'of average')}
        ${kpi('Since season start', pc(X.rstd_pct_normal), t === 'arabica' ? 'from Sep 1 (flowering)' : 'from Jul 1')}
        ${kpi('Next 16 days (forecast)', pc(X.f16_rain_pct_normal), 'of the usual rain for those dates')}
        ${kpi('Root-zone soil moisture', X.sm100_p == null ? '–' : fmt(X.sm100_p, 0) + 'th pct', '28–100 cm, vs same week 2011–25')}
        ${kpi('Frost watch', X.f16_tmin == null ? '–' : fmt(X.f16_tmin, 1) + ' °C', X.coldest_forecast ? `coldest forecast night, weighted; lowest point ${X.coldest_forecast[1].toFixed(1)} °C; ${pc(X.frost_risk_share)} of output ≤3 °C` : '')}</div>
      <div class="tbl" style="margin-top:8px"><table><tr><th class="l">Region (weather point)</th><th>Conab ${W.conab.season} output, k bags</th><th>Share</th><th>30d rain, mm</th><th>vs avg</th><th>Season rain</th><th>vs avg</th><th>Soil moisture pct</th><th>16-day rain</th><th>Coldest night ahead</th></tr>
        ${X.regions.map(r => `<tr><td class="l">${r.name}<br><span class="note">${r.conab_rows.join(', ')}</span></td><td class="n">${fmt(r.prod_k, 0)}</td><td class="n">${fmt(r.share, 1)}%</td>
          <td class="n">${r.has_weather ? fmt(r.r30, 0) : '<span class="note">pending</span>'}</td><td class="n">${r.r30_n ? sgn(100 * (r.r30 / r.r30_n - 1), 0, '%') : '–'}</td>
          <td class="n">${r.rstd != null ? fmt(r.rstd, 0) : '–'}</td><td class="n">${r.rstd_n ? sgn(100 * (r.rstd / r.rstd_n - 1), 0, '%') : '–'}</td>
          <td class="n">${r.sm100_p ?? '–'}</td><td class="n">${r.f16_rain != null ? fmt(r.f16_rain, 0) : '–'}</td><td class="n">${r.f16_tmin != null ? fmt(r.f16_tmin, 1) + ' °C' : '–'}</td></tr>`).join('')}</table></div>
      <p class="note">Covers ${pc(X.mapped_share)} of Brazil's ${t} output; weather available for ${pc(X.weather_share)} of that (missing points drop out and the rest are re-weighted).</p></div>`; };
    body().innerHTML = card('arabica', 'Arabica') + `<div style="margin-top:12px"></div>` + card('conilon', 'Conilon') +
      (H.length > 1 ? `<div class="card" style="margin-top:12px"><h2>Weighted rain index over time</h2><div style="position:relative;height:240px"><canvas id="kcWh"></canvas></div></div>` : '') +
      `<p class="note">Weights: Conab survey ${W.conab.survey} of ${W.conab.season}, production by state and by Minas Gerais and Bahia region. Weather: Open-Meteo ERA5 and forecast at one point per region, against 2011–2025 (see Where it's grown for each point). Weather through ${W.weather_through || '–'}. For forecasts also check Somar Meteorologia and Climatempo.</p>`;
    if (H.length > 1) chart('kcWh', { type: 'line', data: { labels: H.map(r => r.date), datasets: [['arabica_r30_pct_normal', 'Arabica 30-day rain % of avg', '#7d3c98'], ['conilon_r30_pct_normal', 'Conilon 30-day rain % of avg', '#d68910'],
      ['arabica_rstd_pct_normal', 'Arabica season rain % of avg', '#2c6fbb']].map(([k, l, c]) => ({ label: l, data: H.map(r => r[k]), borderColor: c, pointRadius: 0 })) } });
  }

  async function certs() {
    await load();
    const St = K.structure, I = K.ico.stocks, n = I.month.length - 1, sn = St.now;
    body().innerHTML = `<div class="grid g4">
        ${kpi('NY certified stocks', f2(I.ny[n]) + 'm bags', `${I.month[n]} (ICO); ${sgn(I.ny[n] - I.ny[Math.max(0, n - 12)], 2)}m on the year`)}
        ${kpi('London robusta certs', f2(I.ldn[n]) + 'm bags', `${sgn(I.ldn[n] - I.ldn[Math.max(0, n - 12)], 2)}m on the year`)}
        ${kpi('KC front spread', sgn(sn.spread, 1, '¢'), `front minus second, ${sn.date}; ${ord(sn.pct5y)} of 5 years`)}
        ${kpi('Full carry', f2(sn.carry) + '¢', `cost of carry at ${f2(sn.rate)}% rates; spread ${sn.spread > 0 ? 'inverted: the market pays to have coffee now' : 'in contango'}`)}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Certified stocks</h2>${box('kcSt', 280)}<p class="note">ICE-graded coffee in licensed warehouses, million bags (ICO monthly report).</p></div>
        <div class="card"><h2>Front spread against certified stocks</h2>${box('kcSc', 280)}<p class="note">Each point is a month: NY certified stocks (x) against the KC front-month spread (y, ¢/lb, positive = inverted). Low certs go with inverted curves; the latest month is highlighted.</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>KC front spread history</h2>${box('kcSp', 260)}</div>
        <div class="card"><h2>KC curve</h2><div class="tbl"><table><tr><th class="l">Contract</th><th>Price</th><th>1 week ago</th><th>Change</th><th>Volume</th></tr>
          ${K.curves.KC.map(r => `<tr><td class="l">${r.label}</td><td class="n">${f2(r.px)}</td><td class="n">${f2(r.px_1w)}</td><td class="n">${sgn(r.px - r.px_1w, 2)}</td><td class="n">${f0(r.vol)}</td></tr>`).join('')}</table></div></div></div>${asof()}`;
    chart('kcSt', { type: 'line', data: { labels: I.month, datasets: [{ label: 'New York (arabica)', data: I.ny, borderColor: '#7d3c98', pointRadius: 0 }, { label: 'London (robusta)', data: I.ldn, borderColor: '#d68910', pointRadius: 0 }] } });
    const V = St.vs_certs;
    chart('kcSc', { type: 'scatter', data: { datasets: [{ label: 'Months', data: V.slice(0, -1).map(p => ({ x: p.x, y: p.y })), backgroundColor: 'rgba(125,60,152,.35)' },
      { label: 'Latest ' + V.at(-1).m, data: [{ x: V.at(-1).x, y: V.at(-1).y }], backgroundColor: '#c0392b', pointRadius: 6 }] },
      options: { interaction: { mode: 'nearest', intersect: true }, scales: { x: { title: { display: true, text: 'NY certs, m bags' } }, y: { title: { display: true, text: 'front spread ¢/lb' } } } } });
    const i0 = since(St.dates, 6);
    chart('kcSp', { type: 'line', data: { labels: St.dates.slice(i0), datasets: [{ label: 'Front − second, ¢/lb', data: St.spread.slice(i0), borderColor: '#2c6fbb', pointRadius: 0 }, { label: 'Full carry (negative)', data: St.carry.slice(i0).map(x => -x), borderColor: '#7f8c8d', borderDash: [4, 3], pointRadius: 0 }] } });
  }

  async function arb() {
    await load();
    const A = K.arb, V = K.vietnam, Cb = K.brazil.conillon, i0 = since(A.dates, 8), j0 = since(Cb.dates, 4);
    body().innerHTML = `<div class="grid g4">
        ${kpi('Arabica − robusta', f0(A.now.arb) + ' $/t', `${A.now.date}; ${ord(A.now.pct5y)} of 5 years`)}
        ${kpi('Arabica / robusta ratio', f2(A.now.ratio) + '×', 'KC front in $/t over RC front')}
        ${kpi('Vietnam robusta, Dak Lak', f0(V.now.usd_t) + ' $/t', `${f0(V.now.vnd)} VND/kg (${V.now.date}); ${sgn(V.now.usd_t - V.now.rc, 0)} vs London`)}
        ${kpi('Robusta front (RC)', f0(K.snapshot['RC1!']?.last) + ' $/t', `${sgn(K.snapshot['RC1!']?.w1, 1, '%')} on the week`)}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Arabica/robusta arbitrage</h2>${box('kcArb', 300)}<p class="note">KC front converted to $/t minus London RC front. A wide arb pushes roasters to blend more robusta (Brazil conilon, Vietnam), which caps arabica; a narrow one does the reverse.</p></div>
        <div class="card"><h2>Brazil conilon against London</h2>${box('kcCon', 300)}<p class="note">Conilon tipo 7 (Espírito Santo), US$/t, and its basis to RC. Brazil's conilon crop and exports have made it a direct competitor to Vietnamese robusta.</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Vietnam local price against London</h2>${box('kcVn', 240)}<p class="note">Dak Lak farm-gate robusta converted to US$/t; difference to the RC front.</p></div>
        <div class="card"><h2>Robusta curve</h2><div class="tbl"><table><tr><th class="l">Contract</th><th>$/t</th><th>1 week ago</th><th>Change</th><th>Volume</th></tr>
          ${K.curves.RC.map(r => `<tr><td class="l">${r.label}</td><td class="n">${f0(r.px)}</td><td class="n">${f0(r.px_1w)}</td><td class="n">${sgn(r.px - r.px_1w, 0)}</td><td class="n">${f0(r.vol)}</td></tr>`).join('')}</table></div></div></div>${asof()}`;
    chart('kcArb', { type: 'line', data: { labels: A.dates.slice(i0), datasets: [{ label: 'Arb, $/t', data: A.arb.slice(i0), borderColor: '#7d3c98', pointRadius: 0, yAxisID: 'y' }, { label: 'Ratio', data: A.ratio.slice(i0), borderColor: '#d68910', pointRadius: 0, yAxisID: 'y1' }] },
      options: { scales: { y1: { position: 'right', grid: { display: false } } } } });
    chart('kcCon', { type: 'line', data: { labels: Cb.dates.slice(j0), datasets: [{ label: 'Conilon, $/t', data: Cb.usd_t.slice(j0), borderColor: '#2f6b3a', pointRadius: 0, yAxisID: 'y' }, { label: 'London RC', data: Cb.rc.slice(j0), borderColor: '#d68910', pointRadius: 0, yAxisID: 'y' },
      { label: 'Basis, $/t', data: Cb.basis.slice(j0), borderColor: '#7f8c8d', borderDash: [4, 3], pointRadius: 0, yAxisID: 'y1' }] }, options: { scales: { y1: { position: 'right', grid: { display: false } } } } });
    chart('kcVn', { type: 'bar', data: { labels: V.dates, datasets: [{ label: 'Diff to RC, $/t', data: V.diff, backgroundColor: '#2c6fbb' }, { type: 'line', label: 'Dak Lak, $/t', data: V.usd_t, borderColor: '#2f6b3a', pointRadius: 0, yAxisID: 'y1' }] },
      options: { scales: { y1: { position: 'right', grid: { display: false } } } } });
  }

  async function origins() {
    await load();
    const Co = K.colombia, In = Co.internal, Mo = Co.monthly, G = K.ico.groups, Ex = K.ico.exports, n = G.month.length - 1, r = Ex.roll12, rn = r.month.length - 1;
    const yrs = Object.keys(Co.prod_cy).map(Number).sort(), cy = yrs.at(-1);
    body().innerHTML = `<div class="grid g4">
        ${kpi('Colombia internal price', f0(In.now.cop / 1000) + 'k COP/carga', `${f1(In.now.c_lb)} ¢/lb at ${f0(In.now.fx)} COP/US$ (${In.now.date}); ${sgn(In.now.c_lb - In.now.kc, 1, '¢')} vs KC`)}
        ${kpi('Colombia ex-dock premium', sgn(Mo.diff.at(-1), 1, '¢'), `${Mo.month.at(-1)}: UGQ ex-dock over KC`)}
        ${kpi('ICO composite', f1(G.composite[n]) + ' ¢/lb', `${G.month[n]}`)}
        ${kpi('World exports, 12 months', f1(r.total[rn]) + 'm bags', `to ${r.month[rn]}: arabica ${f1(r.arabicas[rn])}, robusta ${f1(r.robustas[rn])}`)}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Colombia: production by calendar year</h2>${box('kcCoP', 260)}<p class="note">FNC registered production, cumulative million bags. ${cy}: ${f2(Co.prod_cy[cy].total)}m in ${Co.prod_cy[cy].n} months.</p></div>
        <div class="card"><h2>Colombia: internal price against KC</h2>${box('kcCoI', 260)}<p class="note">FNC daily purchase price (COP per 125-kg carga of parchment) converted to green ¢/lb, and its difference to KC. A high internal price relative to KC pulls coffee out of farms.</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>ICO group differentials to the composite</h2>${box('kcIco', 260)}<p class="note">Colombian milds, other milds, Brazilian naturals and robustas, ¢/lb over/under the ICO composite. Brazilian naturals at a deep discount means Brazil is pricing to sell.</p></div>
        <div class="card"><h2>World exports (ICO), 12-month total</h2>${box('kcIx', 260)}</div></div>
      <div class="card" style="margin-top:12px"><h2>Vietnam</h2><p>Vietnam grows ~95% robusta in the Central Highlands (Dak Lak, Lam Dong, Gia Lai, Dak Nong), harvests November–January and sells through the dry season; irrigation water in February–April sets flowering for the next crop. Local prices and the difference to London are on the <a href="#kc-arb" onclick="document.querySelector('#kcTabs button[data-t=kc-arb]').click();return false">Arabica / robusta</a> tab; Highlands rainfall against history is on <a href="#kc-geo" onclick="document.querySelector('#kcTabs button[data-t=kc-geo]').click();return false">Where it's grown</a>.</p></div>${asof()}`;
    const ML = MON;
    chart('kcCoP', { type: 'line', data: { labels: ML, datasets: yrs.slice(-5).map((y, q, a) => ({ label: String(y), data: Co.prod_cy[y].cum, borderColor: PAL[q], borderWidth: q === a.length - 1 ? 2.6 : 1.2, pointRadius: 0 })) } });
    const i0 = since(In.dates, 5);
    chart('kcCoI', { type: 'line', data: { labels: In.dates.slice(i0), datasets: [{ label: 'Colombia internal, ¢/lb', data: In.c_lb.slice(i0), borderColor: '#2f6b3a', pointRadius: 0 }, { label: 'KC', data: In.kc.slice(i0), borderColor: '#7d3c98', pointRadius: 0 },
      { label: 'Difference', data: In.diff.slice(i0), borderColor: '#7f8c8d', borderDash: [4, 3], pointRadius: 0, yAxisID: 'y1' }] }, options: { scales: { y1: { position: 'right', grid: { display: false } } } } });
    const g0 = Math.max(0, G.month.length - 72);
    chart('kcIco', { type: 'line', data: { labels: G.month.slice(g0), datasets: [['col_d', 'Colombian milds'], ['oth_d', 'Other milds'], ['bra_d', 'Brazilian naturals'], ['rob_d', 'Robustas']].map(([k, l], q) => ({ label: l, data: G[k].slice(g0), borderColor: PAL[q], pointRadius: 0 })) } });
    chart('kcIx', { type: 'line', data: { labels: r.month, datasets: [{ label: 'Total', data: r.total, borderColor: '#2f6b3a', pointRadius: 0 }, { label: 'Arabicas', data: r.arabicas, borderColor: '#7d3c98', pointRadius: 0 }, { label: 'Robustas', data: r.robustas, borderColor: '#d68910', pointRadius: 0 }] } });
  }

  async function flows() {
    await load();
    const C = K.cot;
    body().innerHTML = `<div id="kcCot"></div><div class="card" style="margin-top:12px"><h2>Producer and merchant short hedges</h2>${box('kcPm', 240)}
      <p class="note">Producer/merchant gross shorts, contracts: ${f0(C.pm_now.short)} now against a five-year average of ${f0(C.pm_now.avg5y)}. Trade hedging shrinks when prices and margins are high, which leaves the market thinner and more volatile. Full report categories: <a href="#cot" onclick="document.querySelector('nav.comm button[data-c=cotfull]').click();return false">COT (full) tab</a>.</p></div>`;
    CotDesk.mount($('#kcCot'), ['KC']);
    const i0 = since(C.dates, 6);
    chart('kcPm', { type: 'line', data: { labels: C.dates.slice(i0), datasets: [{ label: 'Producer/merchant short', data: C.pm_short.slice(i0), borderColor: '#2f6b3a', pointRadius: 0 }, { label: '5-yr average', data: C.pm_short_5y.slice(i0), borderColor: '#7f8c8d', borderDash: [4, 3], pointRadius: 0 },
      { label: 'Managed money net', data: C.mm_net.slice(i0), borderColor: '#c0392b', pointRadius: 0 }] } });
  }

  async function outlook() {
    await load();
    const W = K.psd.World, n = W.years.length - 1, St = K.structure.now, A = K.arb.now, L = K.brazil.ladder, BE = K.br_exports.belgium.now, C = K.cot.now;
    const tilt = (v, t) => v > t ? '<span class="up">supportive</span>' : v < -t ? '<span class="dn">bearish</span>' : 'neutral';
    const t6 = L.find(x => x.key === 't6') || L[0];
    const F = [
      ['World balance', tilt(-(W.prod[n] - W.cons[n]), 2), `USDA: production ${f1(W.prod[n])}m bags against consumption ${f1(W.cons[n])}m (${W.prod[n] >= W.cons[n] ? 'surplus' : 'deficit'} ${f1(Math.abs(W.prod[n] - W.cons[n]))}m); ending stocks ${f1(W.end[n])}m.`],
      ['Curve and certs', tilt(St.spread, 3), `Front spread ${sgn(St.spread, 1, '¢')} (${ord(St.pct5y)} of 5 years): ${St.spread > 0 ? 'the market still pays for nearby coffee' : 'the curve is in carry, nearby supply is comfortable'}.`],
      ['Brazil physical', tilt((t6.pct ?? 50) - 50, 25), `${t6.name} at ${sgn(t6.basis, 1, '¢')} under KC, ${ord(t6.pct)} of 5 years: ${(t6.pct ?? 50) < 30 ? 'Brazil is offering coffee at a deep discount' : (t6.pct ?? 50) > 70 ? 'origin is holding coffee back' : 'normal selling'}.`],
      ['Certification flow', tilt(-(BE.vs_avg || 0), 30), `Brazil green to Belgium ${sgn(BE.vs_avg, 0, '%')} vs normal over ${BE.months}${BE.vs_avg > 30 ? ': more coffee heading for ICE grading, which would rebuild certs and ease the inversion' : ''}.`],
      ['Robusta substitution', tilt(-(A.pct5y - 50), 30), `Arabica − robusta ${f0(A.arb)} $/t (${ord(A.pct5y)} of 5 years)${A.pct5y > 70 ? ': roasters have reason to blend more robusta' : ''}.`],
      ['Funds', tilt(-(C.pct5y - 50), 30), `Managed money net ${sgn(C.mm_net, 0)} contracts (${ord(C.pct5y)} of 5 years) on ${C.date}.`],
    ];
    body().innerHTML = `<div class="card"><h2>Coffee outlook factors</h2><div class="tbl"><table>${F.map(([a, t, x]) => `<tr><td class="l"><b>${a}</b></td><td>${t}</td><td class="l sv-w">${x}</td></tr>`).join('')}</table></div>
        <p class="note">Rule-of-thumb read of the data on these tabs; not a forecast.</p></div>
      <div id="kcTech" style="margin-top:12px"></div>
      <div class="grid g2" style="margin-top:12px"><div class="card"><h2>Next events</h2><div id="kcCal"></div></div><div class="card"><h2>Coffee headlines</h2><div id="kcNews"></div></div></div>
      <div id="kcSzUp" style="margin-top:12px"></div>`;
    Tech.mount($('#kcTech'), ['KC']);
    try { MktStudy.upcoming($('#kcSzUp'), ['KC'], () => $('#kcTabs button[data-t="kc-seas"]').click()); } catch (e) { /* no seasonal data yet */ }
    try { Intel.calendar($('#kcCal'), { markets: ['KC'], days: 30, minImp: 1 }); } catch (e) { $('#kcCal').innerHTML = '<p class="note">Calendar not available.</p>'; }
    try { Intel.news($('#kcNews'), { tags: ['coffee'], n: 20, chips: false }); } catch (e) { $('#kcNews').innerHTML = '<p class="note">No headlines.</p>'; }
  }
  return { show };
})();
