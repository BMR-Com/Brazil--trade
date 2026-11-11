// Cocoa section (basic): primer, ICCO world balance, West Africa and Ecuador weather, futures/options & COT,
// seasonality & technicals, news flow and the outlook tile. Uses the desk modules with symbol CC.
const Cocoa = (() => {
  let built = false, tab = 'cc-primer', I = null;
  const TABS = [['cc-primer', 'Primer'], ['cc-bal', 'World balance (ICCO)'], ['cc-wx', 'West Africa &amp; Ecuador weather'],
    ['cc-flows', 'Futures, options &amp; COT'], ['cc-seas', 'Seasonality &amp; technicals'], ['cc-news', 'News'], ['cc-outlook', 'Outlook']];
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
    ({ 'cc-primer': guard(primer), 'cc-bal': guard(balance), 'cc-wx': guard(weather), 'cc-flows': guard(flows),
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
    const pct = p => p == null ? '' : `<span class="note">(${n(p)}th pct)</span>`;
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
