// Consumer-side tabs: who holds the stocks and how the buyers are covered.
// Coffee: consuming-country stocks (Europe ports, Japan, ICE certified) against their seasonal range, roaster inventory and
// hedging disclosures. Cocoa: regional grinds, ICE certs, chocolate makers. Cotton: US clothing-store inventory vs sales,
// apparel retailers' inventory against sales growth, Brazil growers' forward sales. Sugar: Brazil mills' hedge books.
// Data: data/consumers/{coffee,cocoa,cotton,producers}.json (pipelines/consumers_build.py).
const Consumers = (() => {
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const f0 = v => v == null ? '–' : Math.round(v).toLocaleString('en-US');
  const f1 = v => fmt(v, 1), f2 = v => fmt(v, 2);
  const pc = (v, d = 1) => v == null ? '–' : sgn(v, d, '%');
  const pp = v => v == null ? '–' : sgn(v, 1, ' pp');
  const MN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const mlab = m => m ? `${MN[+m.slice(5, 7) - 1]} ${m.slice(0, 4)}` : '–';
  const dlab = d => d ? `${+d.slice(8, 10)} ${MN[+d.slice(5, 7) - 1]} ${d.slice(0, 4)}` : '–';
  const box = (id, h = 260) => `<div style="position:relative;height:${h}px"><canvas id="${id}"></canvas></div>`;
  const kpi = (lab, v, sub) => `<div class="kpi card" style="padding:10px"><div class="lbl">${lab}</div><div class="val" style="font-size:19px">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
  // percentile chip: low = scarce (red), high = ample (green); for inventory-to-sales and grinds the reading is the same direction
  const pctChip = (p, n) => {
    if (p == null) return `<span class="note">–${n != null && n < 3 ? ` (${n} yr)` : ''}</span>`;
    const bg = p <= 20 ? '#fbe3e1' : p <= 40 ? '#fdf0dc' : p < 60 ? '#eef2ee' : p < 80 ? '#e2f0e5' : '#cfe8d5';
    return `<span class="pill" style="background:${bg};color:#222">${ordn(p)}${n ? ` <span class="note">of ${n}</span>` : ''}</span>`;
  };
  const scale = (v, unit) => unit === 't' ? `${f0(v / 1000)}k t` : unit === 'm bags' ? `${f2(v)}m bags` : unit === '$m' ? `$${f1(v / 1000)}bn` : unit === 'x' ? f2(v) : f0(v);

  // monthly seasonal chart from a block {months, vals}
  function seasChart(id, b, yfmt) {
    const s = seasonal(b.months, b.vals);
    chart(id, { type: 'line', data: { labels: MON, datasets: seasonalDatasets(s) },
      options: { plugins: { legend: legendNoMin, tooltip: { callbacks: { label: c => c.dataset.label.startsWith('_') ? null : `${c.dataset.label}: ${yfmt ? yfmt(c.parsed.y) : c.parsed.y}` } } },
        scales: { y: { ticks: { callback: v => yfmt ? yfmt(v) : v } } } } });
  }
  function stockRow(b) {
    const L = b.latest;
    return `<tr><td class="l"><b>${esc(b.name)}</b></td><td>${mlab(L.month)}</td><td>${scale(L.val, b.unit)}</td><td>${pc(L.yoy_pct)}</td><td>${pc(L.vs5y_pct)}</td>
      <td>${pctChip(L.pct_season, L.n_season)}</td><td>${pctChip(L.pct_all, L.n_all)}</td></tr>`;
  }
  // factual one-liners generated from the numbers
  function stockLine(b) {
    const L = b.latest, parts = [];
    parts.push(`${esc(b.name.replace(/ \(.*\)/, ''))}: ${scale(L.val, b.unit)} at ${mlab(L.month)}`);
    if (L.yoy_pct != null) parts.push(`${L.yoy_pct > 0 ? 'up' : 'down'} ${f1(Math.abs(L.yoy_pct))}% on a year earlier`);
    if (L.vs5y_pct != null) parts.push(`${f1(Math.abs(L.vs5y_pct))}% ${L.vs5y_pct < 0 ? 'below' : 'above'} the five-year average for the month`);
    if (L.pct_season != null) parts.push(L.pct_season === 0 ? `the lowest for the month in ${L.n_season} years` : L.pct_season === 100 ? `the highest for the month in ${L.n_season} years` : `${ordn(L.pct_season)} percentile for the month`);
    return parts.join(', ') + '.';
  }
  const latestPeriod = c => (c.periods || []).filter(p => p.period_end).sort((a, b) => a.period_end < b.period_end ? -1 : 1).at(-1) || {};
  const val = o => o == null ? null : typeof o === 'object' ? (o.value ?? o.total ?? null) : o;
  const vu = o => o == null || typeof o !== 'object' ? '' : o.unit || '';
  const money = (o) => { const v = val(o); if (v == null) return '–'; const u = vu(o); return u.includes('thousand') ? `${f0(v / 1000)}m` : `${f0(v)}${/m\b/.test(u) || u.includes(' m') ? 'm' : ''}`; };
  const ccyOf = o => { const u = vu(o); return /EUR|€/.test(u) ? '€' : /CHF/.test(u) ? 'CHF ' : /GBP|£/.test(u) ? '£' : /USD|\$/.test(u) ? '$' : ''; };

  // company inventory vs sales scoreboard (from filings feeds)
  function scoreboard(cos, id, title) {
    const rows = cos.filter(c => c.latest && !c.stale).map(c => ({ c, L: c.latest })).sort((a, b) => (b.L.gap ?? -99) - (a.L.gap ?? -99));
    if (!rows.length) return '';
    const hp = rows.some(r => r.L.n_hist >= 3);
    const read = g => g == null ? '' : g > 5 ? '<span class="pill" style="background:#fbe3e1">building</span>' : g < -5 ? '<span class="pill" style="background:#e2f0e5">lean</span>' : '<span class="pill">in line</span>';
    return `<div class="card" style="margin-top:12px"><h2>${title}</h2><div class="tbl"><table id="${id}">
      <tr><th class="l">Company</th><th>Period end</th><th>Sales y/y</th><th>Inventory y/y</th><th>Inventory minus sales growth</th><th></th><th>Inventory / quarterly sales</th>${hp ? '<th>vs same quarter, history</th>' : ''}</tr>
      ${rows.map(({ c, L }) => `<tr><td class="l"><b>${esc(c.name)}</b> <span class="note">${esc(c.ticker)}</span></td><td>${L.label ? esc(L.label) : dlab(L.end)}</td><td>${pc(L.sales_yoy)}</td><td>${pc(L.inv_yoy)}</td><td>${pp(L.gap)}</td><td>${read(L.gap)}</td>
        <td>${L.ratio == null ? '–' : f2(L.ratio)}</td>${hp ? `<td>${pctChip(L.ratio_pct, L.n_hist)}</td>` : ''}</tr>`).join('')}</table></div>
      <p class="note">Year-on-year changes compare each period end with the one a year earlier, in the reporting currency. "Building" means inventory growing more than 5 points faster than sales; "lean" more than 5 points slower. Inventory to sales divides period-end inventory by the period's sales. Gildan's figures include HanesBrands after the merger.</p></div>`;
  }

  // ------------------------------------------------------------------ coffee
  async function coffee(el) {
    const [C, P] = await Promise.all([getJSON('data/consumers/coffee.json'), getJSON('data/consumers/producers.json')]);
    const S = C.stocks.filter(b => !b.stale);
    const by = k => S.find(b => b.key === k);
    const below = S.filter(b => b.latest.vs5y_pct != null && b.latest.vs5y_pct < 0).length;
    const H = C.hedging;
    const sb = H.find(c => c.ticker === 'SBUX');
    const sbP = (sb?.periods || []).filter(p => p.green_purchase_commitments);
    el.innerHTML = `
      <div class="card"><h2>Consuming-country coffee stocks against their seasonal range</h2>
        <p>${below} of ${S.length} stock series sit below their five-year average for the month.</p>
        <ul style="margin:4px 0 8px 18px;font-size:13px">${S.map(b => `<li>${stockLine(b)}</li>`).join('')}</ul>
        <div class="tbl"><table><tr><th class="l">Series</th><th>As of</th><th>Latest</th><th>y/y</th><th>vs 5-yr avg (month)</th><th>Percentile, same month</th><th>Percentile, all months</th></tr>
        ${S.map(stockRow).join('')}</table></div>
        <p class="note">Percentiles rank the latest reading against the same calendar month in every earlier year of the series (and against all months); a low percentile means stocks are tight for the time of year. Japan's monthly detail starts in 2024, so its seasonal rank uses December year-ends (chart below).</p></div>
      <div class="grid g2" style="margin-top:12px">
        ${['ecf', 'ecf_arabica', 'ice_ny', 'ice_ldn'].filter(by).map(k => `<div class="card"><h3>${esc(by(k).name)}</h3>${box('cs_' + k)}<p class="note">${esc(by(k).note || '')} As of ${mlab(by(k).latest.month)}.</p></div>`).join('')}
        ${by('jca') ? `<div class="card"><h3>Japan green coffee stocks: monthly (JCA)</h3>${box('cs_jca')}<p class="note">Month-end inventory, tonnes. As of ${mlab(by('jca').latest.month)}.</p></div>
          <div class="card"><h3>Japan: December stocks since 1996</h3>${box('cs_jcaye')}<p class="note">Year-end inventory from JCA's supply and demand table; the last bar is the latest month.</p></div>` : ''}
      </div>
      <div class="grid g2" style="margin-top:12px">
        ${by('ecf')?.types ? `<div class="card"><h3>Europe port stocks by type (ECF)</h3>${box('cs_ecft')}<p class="note">Robusta, natural arabica (includes Brazil semi-washed) and washed arabica, tonnes.</p></div>` : ''}
        ${by('jca')?.origins ? `<div class="card"><h3>Japan stocks by origin (JCA)</h3>${box('cs_jcao')}</div>` : ''}
      </div>
      <div class="card" style="margin-top:12px"><h2>Roasters: inventory and hedging disclosures</h2>
        <div class="tbl"><table><tr><th class="l">Company</th><th>Latest period</th><th>Total inventory</th><th>Coffee inventory</th><th>Green coffee purchase commitments</th><th>Fixed-price share</th><th>Derivative notional</th><th class="l">Coverage stated</th></tr>
        ${H.map(c => { const p = latestPeriod(c), ci = p.coffee_inventory; return `<tr><td class="l"><b>${esc(c.name.replace(/ \(.*/, ''))}</b> <span class="note">${esc(c.ticker || '')}</span></td><td>${dlab(p.period_end)}<br><span class="note">${esc(p.filing || '')}</span></td>
          <td>${ccyOf(p.total_inventory)}${money(p.total_inventory)}</td><td>${ci ? `${ccyOf(ci)}${f0(ci.total_coffee ?? ci.value ?? ci.unroasted)}m${ci.unroasted != null ? `<br><span class="note">unroasted ${f0(ci.unroasted)}m</span>` : ''}` : '–'}</td>
          <td>${p.green_purchase_commitments ? `${ccyOf(p.green_purchase_commitments)}${f0(val(p.green_purchase_commitments))}m` : '–'}</td><td>${p.fixed_price_share != null ? f0(100 * p.fixed_price_share) + '%' : '–'}</td>
          <td>${p.derivative_notional ? `${ccyOf(p.derivative_notional)}${money(p.derivative_notional)}<br><span class="note">${/all commod/i.test(vu(p.derivative_notional)) ? 'all commodities' : /coffee/i.test(vu(p.derivative_notional)) ? 'coffee' : ''}</span>` : '–'}</td>
          <td class="l note" style="max-width:280px">${esc(p.hedge_horizon || p.months_covered || '–')}</td></tr>`; }).join('')}</table></div>
        <p class="note">Figures as disclosed in each company's latest filing or results report (Nestlé and JDE Peet's report half-yearly). Smucker's and Keurig Dr Pepper's derivative notionals cover all commodities, not coffee alone; Keurig Dr Pepper consolidates JDE Peet's from April 2026.</p>
        ${sbP.length ? `<div class="grid g2"><div><h3>Starbucks green coffee commitments and unroasted inventory ($m)</h3>${box('cs_sbux', 240)}</div><div><h3>Derivative notionals ($m)</h3>${box('cs_notl', 240)}</div></div>` : ''}
        <details style="margin-top:8px"><summary class="note">Every disclosed period, with the companies' own cost and pricing commentary</summary>${H.map(c => `<h3>${esc(c.name)}</h3><div class="tbl"><table class="ts"><tr><th>Period end</th><th>Filing</th><th>Inventory</th><th>Commitments</th><th>Notional</th><th class="l">Coverage</th><th class="l">Commentary</th></tr>
          ${(c.periods || []).slice().sort((a, b) => a.period_end < b.period_end ? 1 : -1).map(p => `<tr><td>${dlab(p.period_end)}</td><td>${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.filing || 'filing')}</a>` : esc(p.filing || '')}</td><td>${ccyOf(p.total_inventory)}${money(p.total_inventory)}</td>
            <td>${p.green_purchase_commitments ? f0(val(p.green_purchase_commitments)) + 'm' : '–'}</td><td>${p.derivative_notional ? money(p.derivative_notional) : '–'}</td><td class="l">${esc(p.hedge_horizon || p.months_covered || '')}</td><td class="l">${esc(p.commentary || '')}</td></tr>`).join('')}</table></div>`).join('')}</details></div>
      ${scoreboard(C.companies, 'cs_score', 'Coffee companies: inventory against sales growth (latest quarter or half-year)')}
      <div class="card" style="margin-top:12px"><h2>Brazil producers</h2><p>No Brazilian coffee grower is listed on B3; the large growers are private or cooperatives, so there is no public hedge book for coffee. Listed growers' cotton, soybean and corn books are on the Cotton tab, mills' sugar books on the Sugar tab.</p></div>
      ${appendix([['European Coffee Federation, Stocks in European ports (yearly PDF, updated every two months)', 'https://www.ecf-coffee.org/category/publications/stocks/'],
        ['All Japan Coffee Association, monthly inventory survey and supply/demand table', 'https://coffee.ajca.or.jp/data/'],
        ['ICE Futures US, daily certified stock report (coffee "C")', 'https://www.ice.com/report-center'], ['International Coffee Organization, monthly coffee market report', 'https://ico.org/resources/coffee-market-report-statistics-section/'],
        ['SEC EDGAR filings (Starbucks, J.M. Smucker, Keurig Dr Pepper, Dutch Bros)', 'https://www.sec.gov/edgar/search/'], ["JDE Peet's and Nestlé half-year and annual reports", 'https://www.jdepeets.com/investors/'],
        ['Company quarterly fundamentals: Yahoo Finance', 'https://finance.yahoo.com/']], C.built)}`;
    const kt = v => f0(v / 1000) + 'k';
    ['ecf', 'ecf_arabica'].filter(by).forEach(k => seasChart('cs_' + k, by(k), kt));
    ['ice_ny', 'ice_ldn'].filter(by).forEach(k => seasChart('cs_' + k, by(k), v => f2(v)));
    const J = by('jca');
    if (J) {
      const jm = J.months.map((m, i) => [m, J.vals[i]]).filter(x => x[0] >= '2024-01');
      const yrs = [...new Set(jm.map(x => x[0].slice(0, 4)))];
      chart('cs_jca', { type: 'line', data: { labels: MON, datasets: yrs.map((y, i) => ({ label: y, data: MON.map((_, k) => (jm.find(x => x[0] === `${y}-${String(k + 1).padStart(2, '0')}`) || [])[1] ?? null),
        borderColor: i === yrs.length - 1 ? '#c0392b' : i === yrs.length - 2 ? '#2c6fbb' : '#999', borderWidth: i === yrs.length - 1 ? 2.4 : 1.4, pointRadius: 1.5 })) },
        options: { scales: { y: { ticks: { callback: kt } } } } });
      const ye = J.year_end || { years: [], vals: [] };
      const lbl = [...ye.years.filter(y => y < J.latest.month.slice(0, 4)), mlab(J.latest.month)];
      const vv = [...ye.vals.slice(0, lbl.length - 1), J.latest.val];
      chart('cs_jcaye', { type: 'bar', data: { labels: lbl, datasets: [{ label: 't', data: vv, backgroundColor: vv.map((_, i) => i === vv.length - 1 ? '#c0392b' : '#2f6b3a') }] },
        options: { plugins: { legend: { display: false } }, scales: { y: { ticks: { callback: kt } } } } });
      if (J.origins) {
        const o = J.origins, n = o.months.length, cut = Math.max(0, n - 24);
        chart('cs_jcao', { type: 'bar', data: { labels: o.months.slice(cut).map(mlab), datasets: Object.entries(o.series).map(([k, v], i) => ({ label: k.replace('_', ' ').replace(/^./, c => c.toUpperCase()), data: v.slice(cut), backgroundColor: PAL[i] })) },
          options: { scales: { x: { stacked: true }, y: { stacked: true, ticks: { callback: kt } } } } });
      }
    }
    const E = by('ecf');
    if (E?.types) {
      const t = E.types, cut = Math.max(0, t.months.length - 48);
      chart('cs_ecft', { type: 'bar', data: { labels: t.months.slice(cut).map(mlab), datasets: Object.entries(t.series).map(([k, v], i) => ({ label: { robusta: 'Robusta', natural: 'Natural arabica', washed: 'Washed arabica' }[k], data: v.slice(cut), backgroundColor: ['#a04000', '#d68910', '#2f6b3a'][i] })) },
        options: { scales: { x: { stacked: true }, y: { stacked: true, ticks: { callback: kt } } } } });
    }
    if (sbP.length) {
      const ps = sbP.slice().sort((a, b) => a.period_end < b.period_end ? -1 : 1);
      chart('cs_sbux', { type: 'bar', data: { labels: ps.map(p => dlab(p.period_end)), datasets: [
        { label: 'Fixed-price', data: ps.map(p => p.green_purchase_commitments.fixed_price), backgroundColor: '#2f6b3a', stack: 'c' },
        { label: 'Price-to-be-fixed', data: ps.map(p => p.green_purchase_commitments.price_to_be_fixed), backgroundColor: '#d68910', stack: 'c' },
        { label: 'Unroasted coffee inventory', data: ps.map(p => p.coffee_inventory?.unroasted ?? null), type: 'line', borderColor: '#c0392b', pointRadius: 2 }] },
        options: { scales: { x: { stacked: true }, y: { stacked: true } } } });
      const nl = H.filter(c => ['SBUX', 'SJM', 'KDP'].includes(c.ticker));
      const dates = [...new Set(nl.flatMap(c => c.periods.filter(p => val(p.derivative_notional) != null).map(p => p.period_end.slice(0, 7))))].sort();
      chart('cs_notl', { type: 'line', data: { labels: dates.map(mlab), datasets: nl.map((c, i) => ({ label: c.ticker + (c.ticker === 'SBUX' ? ' coffee' : ' all commodities'), spanGaps: true, pointRadius: 2, borderColor: PAL[i],
        data: dates.map(d => { const p = c.periods.find(p => p.period_end.slice(0, 7) === d); const v = p && val(p.derivative_notional); return v == null ? null : vu(p.derivative_notional).includes('thousand') ? v / 1000 : v; }) })) } });
    }
  }

  // ------------------------------------------------------------------ cocoa
  async function cocoa(el) {
    const C = await getJSON('data/consumers/cocoa.json');
    const G = C.grinds, M = C.makers.filter(c => !/^Secondary/.test(latestPeriod(c).commentary || ''));
    const qlab = q => q.replace('-', ' ');
    const cd = C.certs;
    el.innerHTML = `
      <div class="grid g4">${G.map(g => kpi(`${esc(g.region)} grind ${qlab(g.latest.quarter)}`, `${f0(g.latest.tonnes / 1000)}k t`,
        `${pc(g.latest.yoy_pct)} y/y · ${pctChip(g.latest.pct_season, g.latest.n_season)} for the quarter · 4-quarter total ${pctChip(g.latest.roll4_pct)}`)).join('')}
        ${cd.dates.length ? kpi('ICE cocoa certified stocks', `${f0(cd.bags.at(-1) / 1000)}k bags`, `as of ${dlab(cd.dates.at(-1))}`) : ''}</div>
      <div class="card" style="margin-top:12px"><h2>Cocoa grindings by region</h2>
        <ul style="margin:4px 0 8px 18px;font-size:13px">${G.map(g => `<li>${esc(g.region)}: ${f0(g.latest.tonnes)} t in ${qlab(g.latest.quarter)}, ${g.latest.yoy_pct > 0 ? 'up' : 'down'} ${f1(Math.abs(g.latest.yoy_pct))}% y/y and ${f1(Math.abs(g.latest.vs5y_pct))}% ${g.latest.vs5y_pct < 0 ? 'below' : 'above'} the five-year average for the quarter; the four-quarter total of ${f0(g.latest.roll4 / 1000)}k t ranks in the ${ordn(g.latest.roll4_pct)} percentile of its history.</li>`).join('')}</ul>
        <div class="grid g3">${G.map((g, i) => `<div><h3>${esc(g.region)}: by quarter</h3>${box('cg_q' + i, 220)}</div>`).join('')}</div>
        <div class="grid g2" style="margin-top:8px"><div><h3>Four-quarter rolling totals (t)</h3>${box('cg_roll', 240)}</div><div><h3>Year-on-year change (%)</h3>${box('cg_yoy', 240)}</div></div>
        <p class="note">Quarterly releases by the European Cocoa Association, the National Confectioners Association (North America) and the Cocoa Association of Asia, out about two weeks after each quarter; next release ${esc(C.next_release)}. Reporting membership changes over time (North America's plant count in particular), so year-on-year figures are the associations' own like-for-like numbers.</p></div>
      ${cd.dates.length > 1 ? `<div class="card" style="margin-top:12px"><h2>ICE cocoa certified stocks (bags)</h2>${box('cg_certs', 220)}<p class="note">From the desk's ICE daily report history, which starts in October 2026; origin and warehouse detail is on the Certs tab.</p></div>` : ''}
      <div class="card" style="margin-top:12px"><h2>Chocolate makers: inventory, hedging and pricing</h2>
        <div class="tbl"><table><tr><th class="l">Company</th><th>Latest period</th><th>Inventory</th><th>Commodity derivative notional</th><th>Price</th><th>Volume</th><th class="l">Hedge coverage as stated</th></tr>
        ${M.map(c => { const p = latestPeriod(c); return `<tr><td class="l"><b>${esc(c.name.replace(/^The /, ''))}</b> <span class="note">${esc(c.ticker || '')}</span></td><td>${dlab(p.period_end)}<br><span class="note">${esc(p.filing || '')}</span></td>
          <td>${ccyOf(p.total_inventory)}${money(p.total_inventory)}</td><td>${p.derivative_notional ? ccyOf(p.derivative_notional) + money(p.derivative_notional) : '–'}</td><td>${pc(p.price_change_pct)}</td><td>${pc(p.volume_change_pct)}</td>
          <td class="l note" style="max-width:320px">${esc(p.hedge_coverage || '–')}</td></tr>`; }).join('')}</table></div>
        <div class="grid g2"><div><h3>Hershey and Mondelez: open commodity derivative notional</h3>${box('cg_notl', 240)}</div><div><h3>Inventory by period</h3>${box('cg_inv', 240)}</div></div>
        <details style="margin-top:8px"><summary class="note">Every disclosed period, with the companies' commentary</summary>${M.map(c => `<h3>${esc(c.name)}</h3><div class="tbl"><table class="ts"><tr><th>Period end</th><th>Filing</th><th>Inventory</th><th>Notional</th><th>Price</th><th>Volume</th><th class="l">Commentary</th></tr>
          ${(c.periods || []).slice().sort((a, b) => a.period_end < b.period_end ? 1 : -1).map(p => `<tr><td>${dlab(p.period_end)}</td><td>${p.url ? `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.filing || 'filing')}</a>` : esc(p.filing || '')}</td><td>${ccyOf(p.total_inventory)}${money(p.total_inventory)}</td>
            <td>${p.derivative_notional ? money(p.derivative_notional) : '–'}</td><td>${pc(p.price_change_pct)}</td><td>${pc(p.volume_change_pct)}</td><td class="l">${esc(p.commentary || '')}</td></tr>`).join('')}</table></div>`).join('')}</details></div>
      ${scoreboard(C.companies, 'cg_score', 'Cocoa and chocolate companies: inventory against sales growth')}
      ${appendix([['European Cocoa Association, quarterly grindings', 'https://www.eurococoa.com/'], ['National Confectioners Association, North American grind', 'https://candyusa.com/'],
        ['Cocoa Association of Asia', 'https://www.cocoaasia.org/'], ['ICE Futures US, cocoa certified stock report', 'https://www.ice.com/report-center'],
        ['SEC EDGAR filings (Hershey, Mondelez)', 'https://www.sec.gov/edgar/search/'], ['Barry Callebaut, Lindt & Sprüngli and Nestlé results reports', 'https://www.barry-callebaut.com/en/group/investors'],
        ['Company fundamentals: Yahoo Finance', 'https://finance.yahoo.com/']], C.built)}`;
    G.forEach((g, i) => {
      const by = Object.fromEntries(g.quarters.map((q, k) => [q, g.tonnes[k]]));
      const y = +g.latest.quarter.slice(0, 4), Q = ['Q1', 'Q2', 'Q3', 'Q4'];
      const p5 = q => [1, 2, 3, 4, 5].map(k => by[`${y - k}-${q}`]).filter(v => v != null);
      chart('cg_q' + i, { type: 'bar', data: { labels: Q, datasets: [
        { label: String(y), data: Q.map(q => by[`${y}-${q}`] ?? null), backgroundColor: '#c0392b' },
        { label: String(y - 1), data: Q.map(q => by[`${y - 1}-${q}`] ?? null), backgroundColor: '#2c6fbb' },
        { label: '5y avg', type: 'line', data: Q.map(q => { const a = p5(q); return a.length ? a.reduce((s, v) => s + v, 0) / a.length : null; }), borderColor: '#555', borderDash: [4, 3], pointRadius: 2 },
        { label: '5y min', type: 'line', data: Q.map(q => { const a = p5(q); return a.length ? Math.min(...a) : null; }), borderColor: '#bbb', borderWidth: 1, pointRadius: 0 },
        { label: '5y max', type: 'line', data: Q.map(q => { const a = p5(q); return a.length ? Math.max(...a) : null; }), borderColor: '#bbb', borderWidth: 1, pointRadius: 0 }] },
        options: { scales: { y: { beginAtZero: false, ticks: { callback: v => f0(v / 1000) + 'k' } } } } });
    });
    const allQ = [...new Set(G.flatMap(g => g.quarters))].sort().filter(q => q >= '2016-Q1');
    chart('cg_roll', { type: 'line', data: { labels: allQ.map(qlab), datasets: G.map((g, i) => ({ label: g.region, spanGaps: true, pointRadius: 0, borderColor: PAL[i], borderWidth: 1.8,
      data: allQ.map(q => { const k = g.quarters.indexOf(q); return k < 0 ? null : g.roll4[k]; }) })) }, options: { scales: { y: { ticks: { callback: v => f0(v / 1000) + 'k' } } } } });
    const lastQ = allQ.slice(-12);
    chart('cg_yoy', { type: 'bar', data: { labels: lastQ.map(qlab), datasets: G.map((g, i) => ({ label: g.region, backgroundColor: PAL[i], data: lastQ.map(q => { const k = g.quarters.indexOf(q); return k < 0 ? null : g.yoy[k]; }) })) } });
    if (cd.dates.length > 1) chart('cg_certs', { type: 'line', data: { labels: cd.dates.map(dlab), datasets: [{ label: 'Certified bags', data: cd.bags, borderColor: '#7d3c98', pointRadius: 1 }] }, options: { plugins: { legend: { display: false } } } });
    const nm = M.filter(c => /Hershey|Mondelez/.test(c.name));
    const dts = [...new Set(nm.flatMap(c => c.periods.filter(p => val(p.derivative_notional) != null).map(p => p.period_end.slice(0, 7))))].sort();
    const toM = p => { const v = val(p.derivative_notional); return v == null ? null : vu(p.derivative_notional).includes('thousand') ? v / 1000 : v; };
    chart('cg_notl', { type: 'line', data: { labels: dts.map(mlab), datasets: nm.map((c, i) => ({ label: c.name.replace(/^The | Company| International/g, '') + ' ($m)', spanGaps: true, pointRadius: 2, borderColor: PAL[i],
      data: dts.map(d => { const p = c.periods.find(p => p.period_end.slice(0, 7) === d); return p ? toM(p) : null; }) })) } });
    const idts = [...new Set(M.flatMap(c => c.periods.filter(p => val(p.total_inventory) != null).map(p => p.period_end.slice(0, 7))))].sort();
    const invM = p => { const v = val(p.total_inventory); return v == null ? null : vu(p.total_inventory).includes('thousand') ? v / 1000 : /bn/.test(vu(p.total_inventory)) ? v * 1000 : v; };
    chart('cg_inv', { type: 'line', data: { labels: idts.map(mlab), datasets: M.filter(c => c.periods.some(p => val(p.total_inventory) != null)).map((c, i) => ({ label: `${c.name.replace(/^The | Company| International|& Spruengli/g, '').trim()} (${ccyOf(latestPeriod(c).total_inventory).trim() || '$'}m)`, spanGaps: true, pointRadius: 2, borderColor: PAL[i],
      data: idts.map(d => { const p = c.periods.find(p => p.period_end.slice(0, 7) === d); return p ? invM(p) : null; }) })) } });
  }

  // ------------------------------------------------------------------ cotton
  async function cotton(el) {
    const [C, P] = await Promise.all([getJSON('data/consumers/cotton.json'), getJSON('data/consumers/producers.json')]);
    const Z = C.census;
    const cos = C.companies;
    const inv = Z?.inventory, sal = Z?.sales, rat = Z?.ratio;
    el.innerHTML = `
      ${Z && !inv.stale ? `<div class="grid g4">${kpi(`US ${esc(Z.label.toLowerCase())}: sales`, `${pc(sal.yoy.at(-1))} y/y`, `${mlab(sal.latest.month)}, seasonally adjusted`)}
        ${kpi('Inventories', `${pc(inv.yoy.at(-1))} y/y`, `${scale(inv.latest.val, '$m')} at ${mlab(inv.latest.month)}`)}
        ${kpi('Inventory / sales', f2(rat.latest.val), `${pctChip(rat.latest.pct_all, rat.latest.n_all)} of all months since ${rat.months[0].slice(0, 4)}`)}
        ${kpi('Inventory minus sales growth', pp(inv.yoy.at(-1) - sal.yoy.at(-1)), 'positive = shelves filling faster than sales')}</div>
      <div class="card" style="margin-top:12px"><h2>US ${esc(Z.label.toLowerCase())}: inventory against sales (Census monthly retail trade)</h2>
        <div class="grid g2"><div><h3>Year-on-year change (%)</h3>${box('ct_cen', 250)}</div><div><h3>Inventory-to-sales ratio</h3>${box('ct_ratio', 250)}</div></div>
        <p class="note">US Census Bureau Monthly Retail Trade survey, seasonally adjusted, as of ${mlab(inv.latest.month)}. Retail inventories are valued at cost.</p></div>` : `<div class="card"><p class="note">US Census retail trade data are not loaded yet.</p></div>`}
      ${scoreboard(cos, 'ct_score', 'Apparel retailers and brands: inventory against sales growth (latest reported period)')}
      <div class="card" style="margin-top:12px"><h2>Garment demand: what the companies said in their latest results</h2>
        <div class="tbl"><table class="ts"><tr><th class="l">Company</th><th>Period</th><th class="l">Inventory</th><th class="l">Demand</th><th class="l">Costs</th></tr>
        ${C.commentary.filter(c => c.inventory_comment || c.demand_comment).sort((a, b) => (b.release_date || '') < (a.release_date || '') ? -1 : 1).map(c => `<tr><td class="l"><b>${esc(c.name)}</b></td><td>${c.url ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.period || '')}</a>` : esc(c.period || '')}</td>
          <td class="l">${esc(c.inventory_comment || '')}</td><td class="l">${esc(c.demand_comment || '')}</td><td class="l">${esc(c.cost_comment || '')}</td></tr>`).join('')}</table></div></div>
      ${producerPanel(P, ['cotton', 'soybean', 'corn'], 'ct')}
      ${appendix([['US Census Bureau, Monthly Retail Trade (sales and inventories)', 'https://www.census.gov/retail/index.html'], ['SEC EDGAR filings and results releases of US retailers and brands', 'https://www.sec.gov/edgar/search/'],
        ['Inditex, H&M, Fast Retailing, ABF (Primark), Next, Shenzhou, Crystal results releases', 'https://www.inditex.com/itxcomweb/en/investors'], ['Company fundamentals: Yahoo Finance', 'https://finance.yahoo.com/'],
        ['SLC Agrícola and BrasilAgro quarterly results releases', 'https://ri.slcagricola.com.br/']], C.built)}`;
    if (Z && !inv.stale) {
      const cut = Math.max(0, inv.months.length - 72), ms = inv.months.slice(cut);
      chart('ct_cen', { type: 'line', data: { labels: ms.map(mlab), datasets: [
        { label: 'Sales y/y', data: sal.yoy.slice(cut), borderColor: '#2c6fbb', pointRadius: 0 }, { label: 'Inventory y/y', data: inv.yoy.slice(cut), borderColor: '#c0392b', pointRadius: 0 }] },
        options: { scales: { y: { suggestedMin: -15, suggestedMax: 25 } } } });
      seasChart('ct_ratio', rat, v => f2(v));
    }
    producerCharts(P, ['cotton', 'soybean', 'corn'], 'ct');
  }

  // ------------------------------------------------------------------ Brazil producers' hedge books
  const pxs = r => r.hedged_price == null ? '–' : `${(r.approx && r.hedged_pct == null) ? '~' : ''}${r.hedged_price >= 100 ? f0(r.hedged_price) : f2(r.hedged_price)} <span class="note">${esc(r.price_unit || '')}</span>`;
  function producerPanel(P, crops, pre) {
    const rows = P.rows.filter(r => crops.includes(r.crop));
    if (!rows.length) return '';
    const cos = [...new Set(rows.map(r => r.company))];
    const latest = [];
    cos.forEach(co => crops.forEach(cr => {
      const rs = rows.filter(r => r.company === co && r.crop === cr && (r.hedged_pct != null || r.volume_t != null || r.hedged_price != null));
      const seasons = [...new Set(rs.map(r => r.season))].sort();
      seasons.slice(-2).forEach(se => { const x = rs.filter(r => r.season === se).sort((a, b) => a.release_date < b.release_date ? -1 : 1); if (x.length && (Date.now() - new Date(x.at(-1).release_date)) / 864e5 < 400) latest.push({ ...x.at(-1), prev: x.at(-2) }); });
    }));
    return `<div class="card" style="margin-top:12px"><h2>Listed Brazil producers: share of the crop sold forward</h2>
      <div class="tbl"><table><tr><th class="l">Company</th><th>Crop</th><th>Season</th><th>Latest release</th><th>Hedged</th><th>Avg price</th><th>Previous release</th><th>FX hedged</th></tr>
      ${latest.map(r => `<tr><td class="l"><b>${esc(r.company)}</b></td><td>${esc(r.crop)}</td><td>${esc(r.season)}</td><td>${esc(r.release)} <span class="note">${dlab(r.release_date)}</span></td>
        <td>${r.hedged_pct != null ? (r.approx ? '~' : '') + f0(r.hedged_pct) + '%' : r.volume_t != null ? f0(r.volume_t) + ' t' : '–'}${r.secondary ? '*' : ''}</td><td>${pxs(r)}</td>
        <td>${r.prev ? `${r.prev.hedged_pct != null ? f0(r.prev.hedged_pct) + '%' : pxs(r.prev)} <span class="note">${esc(r.prev.release)}</span>` : '–'}</td><td>${r.fx_hedged_pct != null ? f1(r.fx_hedged_pct) + '%' + (r.fx_rate ? ` at ${f2(r.fx_rate)}` : '') : '–'}</td></tr>`).join('')}</table></div>
      <div class="grid g2">${crops.slice(0, 2).map((cr, i) => `<div><h3>${cr === 'sugar' ? 'Sugar' : cr[0].toUpperCase() + cr.slice(1)}: % of the crop hedged at each release</h3>${box(`${pre}_ph${i}`, 240)}</div>`).join('')}</div>
      <p class="note">From each company's quarterly results release; percentages are of the company's own expected production or sales for the season, as each company defines it. * From press coverage of the results or call, where the company's own table could not be read. São Martinho publishes prices for the tonnes it has fixed rather than a share of the crop.</p></div>`;
  }
  function producerCharts(P, crops, pre) {
    crops.slice(0, 2).forEach((cr, i) => {
      const rs = P.rows.filter(r => r.crop === cr && r.hedged_pct != null && r.release_date);
      if (!document.getElementById(`${pre}_ph${i}`) || !rs.length) return;
      const keys = [...new Set(rs.map(r => `${r.company}|${r.season}`))].filter(k => rs.filter(r => `${r.company}|${r.season}` === k).length >= 2);
      chart(`${pre}_ph${i}`, { type: 'line', data: { datasets: keys.map((k, j) => ({ label: k.replace('|', ' '), pointRadius: 3, borderColor: PAL[j % PAL.length], borderDash: /BrasilAgro|Jalles/.test(k) ? [4, 3] : undefined,
        data: rs.filter(r => `${r.company}|${r.season}` === k).sort((a, b) => a.release_date < b.release_date ? -1 : 1).map(r => ({ x: r.release_date, y: r.hedged_pct, p: r.hedged_price, u: r.price_unit })) })) },
        options: { parsing: false, scales: { x: { type: 'category', labels: [...new Set(rs.map(r => r.release_date))].sort() }, y: { min: 0, max: 100, ticks: { callback: v => v + '%' } } },
          plugins: { tooltip: { callbacks: { label: c => `${c.dataset.label}: ${f1(c.raw.y)}% at ${f2(c.raw.p)} ${c.raw.u || ''}` } } } } });
    });
  }
  async function sugar(el) {
    const P = await getJSON('data/consumers/producers.json');
    el.innerHTML = producerPanel(P, ['sugar', 'ethanol'], 'su') + appendix([['São Martinho, Jalles Machado, Raízen, Adecoagro and BrasilAgro quarterly results releases', 'https://ri.saomartinho.com.br/'],
      ['Adecoagro filings on SEC EDGAR', 'https://www.sec.gov/edgar/search/']], P.built);
    producerCharts(P, ['sugar', 'ethanol'], 'su');
  }

  function appendix(list, built) {
    return `<div class="card" style="margin-top:12px"><h3>Sources</h3><ol class="note" style="margin:4px 0 0 18px">${list.map(([l, u]) => `<li><a href="${u}" target="_blank" rel="noopener">${esc(l)}</a></li>`).join('')}</ol>
      <p class="note">Each figure is shown as of the period or month stated next to it. Page data built ${esc(built)}. Research use only.</p></div>`;
  }

  async function mount(el, kind) {
    el.innerHTML = '<div class="card"><p class="note">Loading…</p></div>';
    try { await ({ coffee, cocoa, cotton, sugar })[kind](el); }
    catch (e) { console.error(e); el.innerHTML = '<div class="card"><p class="note">This tab failed to load.</p></div>'; }
  }
  return { mount };
})();
