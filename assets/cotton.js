// Cotton section: built from the BMR-Com cotton repos (WASDE analytics, export sales, crop progress, on-call, COT)
// plus the desk's own COT desk, technicals, news and calendar.
const Cotton = (() => {
  let built = false, tab = 'ct-primer';
  const ORG = location.hostname === 'bmr-com.github.io' ? '' : 'https://bmr-com.github.io';   // sibling Pages sites (same origin when live)
  const SITE = { wasde: ORG + '/wasde-analytics/', esr: ORG + '/usd-export-sales-email/', crop: ORG + '/cotton-crop-progress/', oncall: ORG + '/cotton-on-call/',
    cot: ORG + '/cftc-cot-full/', opts: ORG + '/softs--options-/' };
  const TABS = [['ct-primer', 'Primer'], ['ct-geo', "Where it's grown, trade &amp; weather"], ['ct-wasde', 'WASDE'], ['ct-esr', 'Export sales'], ['ct-crop', 'Crop progress'], ['ct-ams', 'AMS market review'], ['ct-china', 'China'], ['ct-india', 'India'], ['ct-loan', 'Loan'], ['ct-oncall', 'On-call'], ['ct-basis', 'Basis &amp; ideas'],
    ['ct-flows', 'Futures, options &amp; COT'], ['ct-rv', 'Spreads &amp; vol'], ['ct-outlook', 'Outlook'], ['ct-seas', 'Seasonality &amp; technicals']];
  function shell() {
    $('#cotton').innerHTML = `<nav class="tabs" id="ctTabs">${TABS.map(([k, l], i) => `<button data-t="${k}" class="${k === tab ? 'on' : ''}">${i + 1} · ${l}</button>`).join('')}</nav><main><div id="ctBody"></div></main>`;
    $$('#ctTabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; $$('#ctTabs button').forEach(x => x.classList.toggle('on', x === b)); render(); });
  }
  function show() {
    if (!built) { shell(); built = true; }
    const h = location.hash.slice(1); if (TABS.some(t => t[0] === h)) { tab = h; $$('#ctTabs button').forEach(x => x.classList.toggle('on', x.dataset.t === tab)); }
    render();
  }
  const body = () => $('#ctBody');
  const src = (u, l) => `<a href="${u}" target="_blank" rel="noopener">${l} ↗</a>`;
  function render() {
    history.replaceState(null, '', '#' + tab);
    ({ 'ct-primer': primer, 'ct-geo': () => Geo.mount(body(), 'cotton'), 'ct-wasde': wasde, 'ct-esr': esr, 'ct-crop': cropTab,
      'ct-china': () => { try { typeof ChinaCotton !== 'undefined' ? ChinaCotton.mount(body()) : body().innerHTML = '<div class="card"><p class="note">China module not loaded.</p></div>'; } catch (e) { body().innerHTML = '<div class="card"><p class="note">China tab failed to load.</p></div>'; } }, 'ct-india': () => { try { typeof IndiaCotton !== 'undefined' ? IndiaCotton.mount(body()) : body().innerHTML = '<div class="card"><p class="note">India module not loaded.</p></div>'; } catch (e) { body().innerHTML = '<div class="card"><p class="note">India tab failed to load.</p></div>'; } }, 'ct-loan': () => { try { typeof CottonLoan !== 'undefined' ? CottonLoan.mount(body()) : body().innerHTML = '<div class="card"><p class="note">Loan module not loaded.</p></div>'; } catch (e) { body().innerHTML = '<div class="card"><p class="note">Loan tab failed to load.</p></div>'; } },
      'ct-oncall': () => frame(SITE.oncall, 'Cotton on-call', 'CFTC weekly cotton on-call: unfixed call sales and purchases by contract month, mill fixation pace and what it means for futures.'),
      'ct-basis': () => frame(SITE.crop + 'basis.html', 'Spot basis &amp; trade ideas', 'USDA spot cotton (41-4-34) minus nearby futures: seasonal pattern, current reading, what followed, and the rule-based trade ideas.'),
      'ct-ams': () => { try { AmsReview.mount(body()); } catch (e) { body().innerHTML = '<div class="card"><p class="note">AMS review failed to load.</p></div>'; } }, 'ct-flows': flows, 'ct-rv': () => RVView.mount(body(), 'CT'), 'ct-outlook': outlook, 'ct-seas': () => MktStudy.mount(body(), ['CT']) })[tab]();
  }
  function primer() {
    body().innerHTML = Specs.slot('cotton') + `<div class="grid g2">
      <div class="card"><h2>ICE Cotton No. 2 (CT)</h2><div class="tbl"><table>
        <tr><td>Size</td><td class="l">50,000 lb net weight (~100 running bales)</td></tr><tr><td>Quote / tick</td><td class="l">¢/lb; 0.01¢ = $5</td></tr>
        <tr><td>Months that matter</td><td class="l">Mar, May, Jul (old crop) and Dec (new crop). October trades but is thin and is ignored here.</td></tr>
        <tr><td>Delivery</td><td class="l">Physical, by certificated warehouse receipt at Galveston, Houston, Dallas/Ft Worth, Memphis, Greenville/Spartanburg; base grade Strict Low Middling 1-1/16"</td></tr>
        <tr><td>First notice / last trade</td><td class="l">First notice 5 business days before the delivery month; last trade 17 business days before month end</td></tr></table></div>
        <h3>Calendar</h3><p>US planting Apr–Jun, bolls set Jul–Aug, harvest Sep–Dec. Marketing year Aug–Jul. Texas (≈40% of US area) decides abandonment through dryland West Texas rainfall; FSA failed acres in October understate the final number.</p></div>
      <div class="card"><h2>What moves cotton</h2><div class="tbl"><table><tr><th class="l">Driver</th><th class="l">Mechanism</th><th class="l">Where on this desk</th></tr>
        <tr><td class="l">US crop</td><td class="l">Planted area × (1 − abandonment) × yield; Texas drought sets abandonment.</td><td class="l">Crop progress, WASDE</td></tr>
        <tr><td class="l">Export demand</td><td class="l">~80% of the US crop is exported; the US competes with Brazil, Australia and Africa. India exports only when supply is well above use; China does not export.</td><td class="l">Export sales</td></tr>
        <tr><td class="l">Mill fixation</td><td class="l">Unfixed on-call sales are mills' short futures exposure: they must buy futures to fix, which supports the old-crop months into first notice.</td><td class="l">On-call</td></tr>
        <tr><td class="l">Spec positioning</td><td class="l">Managed money swings are large relative to open interest; crowded shorts fuel short-covering rallies.</td><td class="l">Futures, options &amp; COT</td></tr>
        <tr><td class="l">World balance</td><td class="l">World ex-China stocks/use sets the value of US cotton against polyester and other origins.</td><td class="l">WASDE</td></tr></table></div>
        <h3>Full dashboards</h3><p class="note">${src(SITE.wasde, 'WASDE analytics')} · ${src(SITE.esr, 'Export sales')} · ${src(SITE.crop, 'Crop progress')} · ${src(SITE.oncall, 'On-call')} · ${src(SITE.cot, 'COT desk')} · ${src(SITE.opts, 'Softs options')}</p></div></div>
      <div class="card" style="margin-top:12px"><h2>Delivery: points, quality differentials, age and storage penalties</h2>
        <p>Cotton No. 2 delivers US-grown cotton held as electronic warehouse receipts in ICE-licensed warehouses. Each bale is classed by USDA; the invoice is the notice price plus or minus the quality differentials for each bale, less penalties for cotton that has sat certificated for months.</p>
        <div class="grid g2"><div class="tbl"><table>
          <tr><td class="l"><b>Delivery points</b></td><td class="l">Galveston, Houston and Dallas/Fort Worth (Texas), Memphis (Tennessee), Greenville/Spartanburg (South Carolina), each including warehouses within 15 miles. Savannah, Georgia is added from the October 2028 expiry. The contract sets no location premium or discount between points: the difference is in each warehouse's storage and load-out tariff (Texas ports carry the highest storage caps).</td></tr>
          <tr><td class="l"><b>Basis quality</b></td><td class="l">Strict Low Middling, 1-1/16 inch staple, leaf 4, micronaire 3.5–4.9, strength 25 g/tex or more, colours 11–51 white and 12–32 light spotted. 92–108 bales of 400–650 lb, 50,000 lb net ±1%.</td></tr>
          <tr><td class="l"><b>Quality differentials</b></td><td class="l">Premiums and discounts for grade, leaf and staple are the average of USDA AMS commercial spot quotations on the sixth business day before delivery. 1-1/32 inch staple delivers at twice the quoted 1-1/16 discount. Each bale's points are netted on the invoice.</td></tr>
          <tr><td class="l"><b>Year of growth</b></td><td class="l">No penalty if delivered by 31 December of the year after the crop year; 2¢/lb in the following calendar year and another 2¢/lb for each year after.</td></tr>
          <tr><td class="l"><b>Weight date allowance</b></td><td class="l">½ lb per bale per month from the month after weighing (shrinkage), on top of the age penalty.</td></tr>
          <tr><td class="l"><b>Storage and fees</b></td><td class="l">The deliverer pays storage up to the delivery day (each warehouse's tariff, capped per delivery point); load-out, inspection ($2/bale) and certificate fees per the ICE tariff schedule.</td></tr>
          <tr><td class="l"><b>Timing</b></td><td class="l">First notice 5 business days before the first delivery day; last trading day 17 business days before month end; last notice 12 business days before month end.</td></tr></table></div>
        <div><h3>Aged cotton penalty (months certificated)</h3><div class="tbl"><table><tr><th class="l">Month after original certification</th><th class="l">Penalty, lb per bale</th></tr>
          <tr><td class="l">1–3</td><td class="l">none</td></tr><tr><td class="l">4–10</td><td class="l">3 in month 4, +3 each month (21 in month 10)</td></tr>
          <tr><td class="l">11–16</td><td class="l">25 in month 11, +4 each month (45 in month 16)</td></tr><tr><td class="l">17–22</td><td class="l">50 in month 17, +5 each month (75 in month 22)</td></tr>
          <tr><td class="l">23 on</td><td class="l">81 in month 23, +6 each month (no cap)</td></tr></table></div>
          <div class="grid g2"><label>Months certificated<br><input id="ctAge" type="number" value="10" min="0"></label><label>Price, ¢/lb<br><input id="ctPx" type="number" value="70" step="1"></label>
            <label>Average bale weight, lb<br><input id="ctBw" type="number" value="500" step="10"></label><label>Months since weighing<br><input id="ctWd" type="number" value="10" min="0"></label></div>
          <div id="ctAgeOut" style="margin-top:8px"></div></div></div>
        <div class="tbl" style="margin-top:8px"><table>
          <tr><td class="l"><b>Why it matters</b></td><td class="l">The penalty is taken as pounds off each bale, so in price terms it is (penalty lb ÷ bale weight) × the price, and it grows faster the longer cotton sits. Old certificated stock therefore delivers at a discount and tends to be tendered first, which weighs on the spot month; a fresh certification wave (new-crop cotton, strong basis elsewhere) is cheaper to deliver and can pressure the front spread too. High certificated stocks with an ageing profile are a bearish structure signal; low and fresh ones support the inverse.</td></tr>
          <tr><td class="l"><b>On-call link</b></td><td class="l">Mills fix on-call purchases against the front months; if they leave fixing late into notice period, they compete with longs who want to avoid delivery. See the On-call tab for unfixed sales by month.</td></tr></table></div>
        <p class="note">From the ICE Cotton No. 2 Deliverer's &amp; Receiver's Guide, contract specifications and tariff schedule. Penalties and tariffs change; check the current ICE documents before acting.</p></div>`;
    const kpi = (lab, v, sub) => `<div class="kpi card" style="padding:10px"><div class="lbl">${lab}</div><div class="val" style="font-size:19px">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
    const ct = () => {
      const m = Math.max(0, +$('#ctAge').value || 0), px = +$('#ctPx').value || 0, bw = +$('#ctBw').value || 500, wd = Math.max(0, +$('#ctWd').value || 0);
      let lb = 0;
      if (m >= 4 && m <= 10) lb = 3 * (m - 3); else if (m >= 11 && m <= 16) lb = 25 + 4 * (m - 11); else if (m >= 17 && m <= 22) lb = 50 + 5 * (m - 17); else if (m >= 23) lb = 81 + 6 * (m - 23);
      const wlb = 0.5 * wd, pen = lb / bw * px, wpen = wlb / bw * px;
      $('#ctAgeOut').innerHTML = `<div class="grid g4">${kpi('Age penalty', fmt(lb, 0) + ' lb/bale', `month ${m} of certification`)}${kpi('In price', fmt(pen, 2) + '¢/lb', `${fmt(100 * lb / bw, 1)}% of value at ${fmt(px, 0)}¢`)}
        ${kpi('Weight allowance', fmt(wlb, 1) + ' lb/bale', fmt(wpen, 2) + '¢/lb')}${kpi('Total', fmt(pen + wpen, 2) + '¢/lb', `≈ $${fmt((pen + wpen) * 500, 0)} per contract (50,000 lb)`)}</div>`;
    };
    ['#ctAge', '#ctPx', '#ctBw', '#ctWd'].forEach(id => $(id).addEventListener('input', ct)); ct();
  }
  async function wasde() {
    body().innerHTML = '<div class="card"><p class="note">Loading WASDE analysis…</p></div>';
    const idx = await getJSON('data/grains/derived/wasde_brief/index.json').catch(() => null);
    if (!idx) { body().innerHTML = '<div class="card"><p class="note">WASDE analysis not built yet.</p></div>'; return; }
    WasdeView.mount(body(), { base: 'data/grains/derived/wasde_brief/', index: idx, key: 'cotton' });
    body().insertAdjacentHTML('beforeend', `<p class="note">Cotton brief, factor read and month-history from ${src(SITE.wasde, 'BMR-Com WASDE analytics')} (crop ratings, Texas drought, export sales, Brazil, on-call, COT); balance sheets and revision paths built here.</p>`);
  }
  async function esr() {
    body().innerHTML = '<div class="card"><p class="note">Loading export sales…</p></div>';
    // two sources: the separate cotton export-sales repo and the desk's own Thursday run; show whichever has the later week
    const [X, OWN] = await Promise.all([fetch(SITE.esr + 'data/brief.json?t=' + Date.now()).then(r => r.json()).catch(() => null),
      getJSON('data/grains/derived/esr_brief.json').catch(() => null)]);
    const own = OWN && OWN.commodities.find(c => c.key === 'cotton');
    const wk = d => (d?.commodities || []).map(c => c.week || '').sort().pop() || '';
    const useOwn = own && (!X || (own.week || '') >= wk(X));   // same week: the desk's brief has the fuller destination and Brazil analysis
    const D = useOwn ? { generated: OWN.generated, commodities: [own] } : X;
    if (!D) { body().innerHTML = `<div class="card"><p class="note">Could not load the cotton export sales brief. Open ${src(SITE.esr, 'the export sales page')}.</p></div>`; return; }
    ESR.mount(body(), D, { name: 'Cotton' });
    // China yarn note: text only, from the China module; if it is missing or stale nothing else on this page changes
    try { const N = await getJSON('data/china/esr_note.json').catch(() => null);
      if (N?.items?.length) body().insertAdjacentHTML('beforeend', `<div class="card" style="margin-top:12px"><h2>China's yarn imports and demand in its suppliers (as of ${N.asof})</h2><p>${N.text}</p><ul>${N.items.map(x => `<li>${x}</li>`).join('')}</ul><p class="note">${N.caveat} Built ${N.generated}; see Cotton → China.</p></div>`);
    } catch (e) { /* ignore */ }
    body().insertAdjacentHTML('beforeend', `<p class="note" style="margin:4px 2px">${useOwn ? `Desk's own Thursday export-sales run (upland + Pima, USDA FAS), week ending ${own.week} · ${OWN.generated}${X ? ` · the ${src(SITE.esr, 'cotton export sales page')} has week ending ${wk(X) || '?'}` : ''}` : `From ${src(SITE.esr, 'BMR-Com US cotton export sales')} (upland + Pima, USDA FAS) · ${D.generated}`}.</p>`);
  }
  // Crop progress tab: BMR-Com crop projection card (output of the cotton-crop-progress repo) above the live dashboard
  function cropTab() {
    frame(SITE.crop, 'Cotton crop progress', 'NASS crop progress and condition, crop projection, ginning and classing pace, grades and tenderability, FSA acreage.');
    const host = document.createElement('div');
    host.className = 'card'; host.style.marginBottom = '8px';
    host.innerHTML = '<p class="note">Loading the crop projection…</p>';
    body().insertBefore(host, body().children[1] || null);
    fetch(SITE.crop + 'data/crop_projection.json?' + Date.now()).then(r => r.ok ? r.json() : Promise.reject(r.status)).then(P => {
      const f = x => x.toFixed(2), pc = x => Math.round(x * 100) + '%';
      const u = P.us_upland, a = P.us_all, t = P.texas, U = P.usda || {};
      const row = (lab, x, us) => `<tr><td class="l">${lab}</td><td class="n"><b>${f(x.central)}</b></td><td class="n">${f(x.lo68)}–${f(x.hi68)}</td><td class="n">${f(x.lo95)}–${f(x.hi95)}</td><td class="n">${f(x.lo99)}–${f(x.hi99)}</td><td class="n">${us != null ? f(us) : '–'}</td></tr>`;
      host.innerHTML = `<h2>BMR-Com crop projection <span class="note">as of ${P.asof} · ${P.unit}</span></h2>
        <div class="tbl"><table><tr><th class="l"></th><th>Projection</th><th>68%</th><th>95%</th><th>99%</th><th>USDA ${U.report || ''}</th></tr>
        ${row('US all cotton', a, U.us_all)}${row('US upland', u, U.us_upland)}${row('Texas upland', t, U.tx)}</table></div>
        ${(P.states || []).length ? `<details style="margin:8px 0"><summary>By state (upland)</summary><div class="tbl"><table><tr><th class="l">State</th><th>Projection</th><th>68%</th><th>95%</th><th>99%</th><th>USDA</th></tr>
          ${P.states.map(x => row(x.name, x, x.usda)).join('')}</table></div></details>` : ''}
        ${P.conditional ? (() => { const C = P.conditional, ha = C.tx_harvested_acres, yd = C.tx_yield; return `<p><b>Conditional view</b> (Texas built as harvested acres × yield): abandonment ${pc(C.tx_abandonment.central)} of ${f(C.tx_planted_acres || 0)}m planted leaves ${ha ? f(ha.central) : '–'}m harvested acres (95% ${ha ? f(ha.lo95) + '–' + f(ha.hi95) : '–'}m); at USDA's ${yd ? yd.central : '–'} lb (95% ${yd ? yd.lo95 + '–' + yd.hi95 : '–'}) Texas is ${f(C.texas.central)}m (95% ${f(C.texas.lo95)}–${f(C.texas.hi95)}m). US upland ${f(C.us_upland.central)}m (95% ${f(C.us_upland.lo95)}–${f(C.us_upland.hi95)}m), all cotton ${f(C.us_all.central)}m.${C.analog ? ` Past seasons with similar Texas ratings ended at ${pc(C.analog.min)}–${pc(C.analog.max)} abandonment.` : ''}</p>`; })() : ''}
        <p>Texas final abandonment projected at <b>${pc(t.abandonment.central)}</b> (95% ${pc(t.abandonment.lo95)}–${pc(t.abandonment.hi95)}) against ${pc(U.tx_abandonment || 0)} in USDA's numbers.</p>
        ${P.texas_regions ? `<p>${P.texas_regions}</p>` : ''}${(P.notes || []).map(n => `<p class="note">${n}</p>`).join('')}
        <p class="note">Inputs through: ${Object.entries(P.inputs_through || {}).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(' · ')}. Built from ${(P.variables || []).length} public USDA data sets; see the ${src(SITE.crop, 'crop progress page')}.</p>`;
    }).catch(() => { host.innerHTML = '<p class="note">Crop projection not available yet.</p>'; });
  }
  function frame(u, title, what) {
    body().innerHTML = `<div class="card" style="margin-bottom:8px"><h2 style="display:inline">${title}</h2> <span class="note">${what} Live view of the ${src(u, 'full dashboard')}.</span></div>
      <iframe class="ctframe" src="${u}" title="${title}" loading="lazy" referrerpolicy="no-referrer" sandbox="allow-scripts allow-same-origin allow-popups"></iframe>`;
  }
  function flows() {
    body().innerHTML = `<div id="ctCot"></div><div class="card" style="margin-top:12px"><h2>Options and index traders</h2>
      <p class="note">Options flow, vol surface and skew: ${src(SITE.opts, 'softs options terminal')}. Index-trader (CIT) positions and the full COT read: ${src(SITE.cot, 'COT positioning desk')}.</p></div>`;
    CotDesk.mount($('#ctCot'), ['CT']);
  }
  async function outlook() {
    body().innerHTML = `<div id="ctOb" style="margin-bottom:12px"></div><div id="ctBal" style="margin-bottom:12px"></div><div id="ctPx" style="margin-bottom:12px"></div><div id="ctTech"></div>
      <div class="grid g2" style="margin-top:12px"><div class="card"><h2>WASDE outlook factors</h2><div id="ctFac"><p class="note">Loading…</p></div></div>
      <div class="card"><h2>Next events</h2><div id="ctCal"></div></div></div>
      <div id="ctSzUp" style="margin-top:12px"></div>
      <div class="card" style="margin-top:12px"><h2>Cotton headlines</h2><div id="ctNews"></div></div>`;
    OutlookBrief.mount($('#ctOb'), 'cotton'); BalanceSheet.mount($('#ctBal'), 'cotton'); if (typeof PriceOutlook !== 'undefined') PriceOutlook.mount($('#ctPx'));
    Tech.mount($('#ctTech'), ['CT']);
    MktStudy.upcoming($('#ctSzUp'), ['CT'], () => $('#ctTabs button[data-t="ct-seas"]').click());
    Intel.calendar($('#ctCal'), { markets: ['CT'], days: 30, minImp: 2 });
    Intel.news($('#ctNews'), { tags: ['cotton'], n: 20, chips: false });
    const idx = await getJSON('data/grains/derived/wasde_brief/index.json').catch(() => null);
    const R = idx && await getJSON('data/grains/derived/wasde_brief/' + idx.reports[0].report + '.json').catch(() => null);
    const C = R?.commodities?.cotton;
    $('#ctFac').innerHTML = C ? `<p>${R.label} report, ${C.my}: <b>${C.outlook}</b> (score ${C.score > 0 ? '+' : ''}${C.score}).</p><div class="tbl"><table>${(C.factors || []).map(f => `<tr><td class="l"><b>${f.factor}</b></td><td>${f.tilt}</td><td class="l sv-w">${String(f.text).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')}</td></tr>`).join('')}</table></div>` : '<p class="note">Not available.</p>';
  }
  return { show };
})();
