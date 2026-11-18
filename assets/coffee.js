// Coffee section: same tab layout as cotton and sugar. Brazil physical basis ladder, certified stocks and the Antwerp
// signal, the arabica/robusta arb, Colombia, Vietnam, ICO and the world balance come from coffee/data/coffee.json
// (built by coffee/scripts/build.py); COT, spreads/vol, seasonality and technicals use the desk modules with KC.
const Coffee = (() => {
  let built = false, tab = 'kc-primer', K = null;
  const TABS = [['kc-primer', 'Primer'], ['kc-geo', "Where it's grown, trade &amp; weather"], ['kc-bal', 'World balance'], ['kc-br', 'Brazil: basis ladder &amp; exports'], ['kc-cecafe', 'Cecafé daily registrations'], ['kc-wx', 'Brazil weather by production'],
    ['kc-certs', 'Certified stocks &amp; structure'], ['kc-cprof', 'Certs profile &amp; delivery economics'], ['kc-newc', 'KC contract: old vs new'], ['kc-arb', 'Arabica / robusta'], ['kc-orig', 'Colombia, Vietnam &amp; ICO'], ['kc-col', 'Centrals &amp; Col'],
    ['kc-flows', 'Futures, options &amp; COT'], ['kc-rv', 'Spreads &amp; vol'], ['kc-outlook', 'Outlook'], ['kc-reports', 'Reports'], ['kc-seas', 'Seasonality &amp; technicals']];
  const body = () => $('#kcBody');
  const f0 = v => fmt(v, 0), f1 = v => fmt(v, 1), f2 = v => fmt(v, 2);
  const ord = p => p == null ? '–' : `${ordn(p)} pct`;
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
    ({ 'kc-primer': primer, 'kc-geo': () => Geo.mount(body(), 'coffee'), 'kc-bal': guard(balance), 'kc-br': guard(brazil), 'kc-certs': guard(certs), 'kc-cprof': guard(cprof), 'kc-newc': guard(kcnew), 'kc-cecafe': guard(cecafe), 'kc-wx': guard(weather),
      'kc-arb': guard(arb), 'kc-orig': guard(origins), 'kc-col': guard(centrals), 'kc-flows': guard(flows), 'kc-rv': guard(async () => { body().innerHTML = '<div id="kcSA"></div><div id="kcRV" style="margin-top:12px"></div>'; await SpreadTables.mount($('#kcSA'), 'coffee'); await RVView.mount($('#kcRV'), 'KC'); }), 'kc-reports': guard(() => ReportsView.mount(body(), 'coffee')),
      'kc-outlook': guard(outlook), 'kc-seas': () => MktStudy.mount(body(), ['KC']) })[tab]();
  }
  const kpi = (lab, v, sub) => `<div class="kpi card" style="padding:10px"><div class="lbl">${lab}</div><div class="val" style="font-size:19px">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
  const box = (id, h = 280) => `<div style="position:relative;height:${h}px"><canvas id="${id}"></canvas></div>`;
  const asof = () => `<p class="note">Coffee data built ${K.built}. Sources: ICE and B3 futures (TradingView), Notícias Agrícolas / CEPEA (Brazil physical), Cecafé and MDIC/SECEX (Brazil exports), FNC (Colombia), Vietnam local prices, ICO (prices, exports, certified stocks), CFTC, USDA FAS PSD.</p>`;
  const RNG = { '1M': 1, '3M': 3, '6M': 6, '1Y': 12, '2Y': 24, '5Y': 60, 'All': 0 };
  const rngFrom = (dates, r) => { if (!RNG[r]) return 0; const c = new Date(dates.at(-1)); c.setMonth(c.getMonth() - RNG[r]); const s = c.toISOString().slice(0, 10); return Math.max(0, dates.findIndex(d => d >= s)); };
  const rngBar = (id, opts, def) => `<div class="seg rng" data-for="${id}" style="display:flex;gap:4px;margin:0 0 6px">${opts.map(o => `<button data-r="${o}" class="${o === def ? 'on' : ''}" style="padding:2px 9px;font-size:11.5px;border:1px solid #cfd4dc;border-radius:99px;background:${o === def ? 'var(--acc)' : '#fff'};color:${o === def ? '#fff' : 'var(--ink)'};cursor:pointer">${o}</button>`).join('')}</div>`;
  const rngWire = (id, draw) => { const b = document.querySelector(`.rng[data-for=${id}]`); if (!b) return; b.onclick = e => { const r = e.target.dataset.r; if (!r) return;
    b.querySelectorAll('button').forEach(x => { const on = x.dataset.r === r; x.classList.toggle('on', on); x.style.background = on ? 'var(--acc)' : '#fff'; x.style.color = on ? '#fff' : 'var(--ink)'; }); draw(r); }; };
  const since = (dates, yrs) => { const c = new Date(); c.setFullYear(c.getFullYear() - yrs); const s = c.toISOString().slice(0, 10); return Math.max(0, dates.findIndex(d => d >= s)); };

  function primer() {
    body().innerHTML = Specs.slot('coffee') + `<div class="grid g2">
      <div class="card"><h2>ICE Coffee C (KC)</h2><div class="tbl"><table>
        <tr><td>Size</td><td class="l">37,500 lb (≈283 bags of 60 kg) of washed arabica</td></tr><tr><td>Quote / tick</td><td class="l">¢/lb; 0.05¢ = $18.75</td></tr>
        <tr><td>Months</td><td class="l">Mar, May, Jul, Sep, Dec</td></tr>
        <tr><td>Delivery</td><td class="l">Certified washed arabica from 19 origins in ICE-licensed warehouses (New York, New Orleans, Houston, Miami, Antwerp, Hamburg/Bremen, Barcelona). Origin and port differentials apply; Brazil semi-washed has been deliverable since the March 2013 contract and has been the largest origin in the certified pile since the early 2020s.</td></tr>
        <tr><td>Notice / last trade</td><td class="l">First notice 7 business days before the delivery month; options expire on the second Friday of the month before. Low certified stocks make the spot month a squeeze risk.</td></tr>
        <tr><td>Robusta</td><td class="l">ICE London (RC), $/t, Jan/Mar/May/Jul/Sep/Nov. Vietnam, Brazil conilon, Indonesia and Uganda supply it; roasters swap between the two when the arb moves.</td></tr></table></div>
        <h3>Calendar</h3><p>Brazil harvests April–September (conilon first, then arabica); its September–November flowering sets next year's crop, and June–August frost in South Minas and Paraná can damage two crops at once. Vietnam harvests November–January, Colombia's main crop October–January with a mitaca in April–June, Central America November–March (month by month for each origin: harvest calendar on <a href="#kc-geo" onclick="document.querySelector('#kcTabs button[data-t=kc-geo]').click();return false">Where it's grown</a>). The ICO coffee year runs October–September.</p></div>
      <div class="card"><h2>What moves coffee</h2><div class="tbl"><table><tr><th class="l">Driver</th><th class="l">Mechanism</th><th class="l">Where on this desk</th></tr>
        <tr><td class="l">Brazil crop</td><td class="l">Brazil is ~40% of world output. Arabica alternates big and small ("on/off") years; rain at flowering and frost decide the next crop.</td><td class="l">Brazil, weather</td></tr>
        <tr><td class="l">Certified stocks</td><td class="l">Coffee graded and stored in ICE warehouses is what the futures deliver. Low certs keep the curve inverted and the spot month tight; rising certs ease it.</td><td class="l">Certified stocks &amp; structure</td></tr>
        <tr><td class="l">Physical basis</td><td class="l">The discount Brazilian and other origins sell at under KC. A widening discount means physical is plentiful and futures are rich; a narrowing one means origin is holding back.</td><td class="l">Brazil basis ladder</td></tr>
        <tr><td class="l">Arabica/robusta arb</td><td class="l">When arabica is expensive against robusta, roasters blend in more robusta, cutting arabica demand (and the reverse).</td><td class="l">Arabica / robusta</td></tr>
        <tr><td class="l">Currencies</td><td class="l">A weaker real or peso raises local-currency prices and encourages farmer selling; a stronger one slows it.</td><td class="l">Brazil, Colombia</td></tr>
        <tr><td class="l">Funds and trade hedging</td><td class="l">Managed money swings; producer/merchant short hedges fall when prices are high and margin calls hurt, which thins liquidity.</td><td class="l">Futures, options &amp; COT</td></tr></table></div></div></div>
      <div class="card" style="margin-top:12px"><h2>Delivery: grading, origin and port differentials, age discount</h2>
        <p>Coffee C delivers certified washed arabica held in ICE-licensed warehouses. Each lot is graded by the exchange (defects, bean size, cup); the invoice is the settlement price adjusted for the coffee's origin, the port it sits in, its grade and how long ago it was graded. 100 points = 1 ¢/lb.</p>
        <div class="grid g2"><div><h3>Origin (growth) differentials</h3><div class="tbl"><table><tr><th class="l">Origin</th><th>Before Mar 2026</th><th>Now (from Mar 2026)</th></tr>
          <tr><td class="l">Mexico, El Salvador, Nicaragua, Panama, Papua New Guinea, Peru, Honduras, Tanzania, Uganda</td><td class="n">par</td><td class="n">par</td></tr>
          <tr><td class="l">Guatemala</td><td class="n">par</td><td class="n">+5.00¢</td></tr>
          <tr><td class="l">Costa Rica, Kenya</td><td class="n">par</td><td class="n">+10.00¢</td></tr>
          <tr><td class="l">Colombia</td><td class="n">+4.00¢</td><td class="n">+10.00¢</td></tr>
          <tr><td class="l">Venezuela, Burundi, Rwanda, India</td><td class="n">−1.00¢</td><td class="n">−1.00¢</td></tr>
          <tr><td class="l">Dominican Republic, Ecuador</td><td class="n">−4.00¢</td><td class="n">−4.00¢</td></tr>
          <tr><td class="l">Brazil (semi-washed)</td><td class="n">−6.00¢</td><td class="n">−6.00¢</td></tr>
          <tr><td class="l">Vietnam (washed arabica)</td><td class="n">–</td><td class="n">−6.00¢ from May 2027</td></tr></table></div></div>
          <div><h3>Port (warehouse) differentials</h3><div class="tbl"><table><tr><th class="l">Port district</th><th>Differential</th></tr>
          <tr><td class="l">New York, Virginia</td><td class="n">par</td></tr><tr><td class="l">New Orleans, Miami, Houston</td><td class="n">−0.50¢</td></tr>
          <tr><td class="l">Antwerp, Hamburg/Bremen, Barcelona</td><td class="n">−1.25¢</td></tr></table></div>
          <h3>Grade</h3><p>Basis is eight full imperfections (defects) per sample for most origins; each full imperfection worse than basis costs 10 points (0.10¢). No lot can be more than 15 imperfections below basis (23 in total; Colombia 10 below basis). At least half the beans must be screen 15 or larger. Coffee must cup clean, with no unwashed or aged flavour.</p></div></div>
        <h3>Age discount (time since the certificate of grade)</h3>
        <div class="grid g2"><div class="tbl"><table><tr><th class="l">Days since grading</th><th class="l">Deduction</th></tr>
          <tr><td class="l">up to 120</td><td class="l">none</td></tr><tr><td class="l">121–150</td><td class="l">0.50¢</td></tr>
          <tr><td class="l">151–360</td><td class="l">0.50¢ + 0.25¢ per 30 days</td></tr><tr><td class="l">361–720</td><td class="l">2.25¢ + 0.50¢ per 30 days</td></tr>
          <tr><td class="l">721–1,080</td><td class="l">8.25¢ + 1.00¢ per 30 days</td></tr><tr><td class="l">1,081–1,440</td><td class="l">20.25¢ + 1.25¢ per 30 days</td></tr>
          <tr><td class="l">1,441–1,800</td><td class="l">35.25¢ + 1.50¢ per 30 days</td></tr><tr><td class="l">longer</td><td class="l">steps up by a further 0.25¢ per 30 days each year (no cap)</td></tr></table></div>
          <div><div class="grid g2"><label>Days since grading<br><input id="kcAge" type="number" value="400" step="30"></label>
            <label>Origin<br><select id="kcOrg"><option value="0">par origin</option><option value="1000">Colombia, Costa Rica, Kenya (+10¢)</option><option value="500">Guatemala (+5¢)</option><option value="-100">Venezuela/Burundi/Rwanda/India (−1¢)</option><option value="-400">Dominican Rep./Ecuador (−4¢)</option><option value="-600">Brazil (−6¢)</option></select></label>
            <label>Port<br><select id="kcPort"><option value="0">New York / Virginia</option><option value="-50">New Orleans / Miami / Houston</option><option value="-125">Antwerp / Hamburg-Bremen / Barcelona</option></select></label>
            <label>Imperfections below basis<br><input id="kcImp" type="number" value="0" min="0" max="15"></label></div>
            <div id="kcAgeOut" style="margin-top:8px"></div></div></div>
        <div class="tbl" style="margin-top:8px"><table>
          <tr><td class="l"><b>Why it matters</b></td><td class="l">The receiver takes what the deliverer chooses, so the cheapest-to-deliver lot sets the value of the spot month: old Brazilian coffee in Antwerp carries the biggest discounts and is what gets delivered first when it is in the certified pile. The age discount pushes owners to deliver or sell old certified lots before they lose value, so a pile of ageing certs weighs on the front spread; fresh gradings at par origins in US ports support it.</td></tr>
          <tr><td class="l"><b>Timing and costs</b></td><td class="l">Delivery notices can be issued from 7 business days before the first business day of the delivery month to the last notice day (7 business days before the last business day); delivery follows 7 business days after the notice. The deliverer pays storage through the end of the delivery month. Weight can be up to 2% under par.</td></tr>
          <tr><td class="l"><b>Certified-stock signals</b></td><td class="l">Coffee waiting for grading, the grading pass rate and unusual shipments to European warehouse ports (Antwerp, Hamburg/Bremen) show certified supply coming before it is counted. See the Certs &amp; structure tab.</td></tr>
          <tr><td class="l"><b>How the structure changed</b></td><td class="l">Until about 2019 the KC curve sat in carry almost all the time. Old coffee that had been de-certified could be graded again and come back as fresh, escaping the age discount, so whoever took delivery risked receiving stale coffee: there was little reason to stand for delivery or bid up the front month. The spot-month position limit (500 lots unless the exchange grants an exemption) also capped squeezes. Brazil semi-washed became deliverable with the March 2013 contract but entered the certified pile in size only from late 2020. ICE then sped up the age discount and, from 1 December 2023, barred re-grading coffee that had been certified and de-certified. Since then the front month has been inverted almost continuously. Before Brazil, most washed origins went straight into the roasting pipeline and little was graded; now Brazil is the marginal deliverable coffee, so its price relative to other origins sets the value of the spot month and the differentials of Central American, Colombian and East African coffees are judged against it. Spread history before 2021, and especially before 2019, describes a different market.</td></tr>
          <tr><td class="l"><b>Why only washed arabica</b></td><td class="l">Coffee C is a benchmark for washed (mild) arabica, not for arabica as a whole. The seller chooses what to deliver and is paid the same futures price plus or minus a fixed differential, so the cheapest coffee that passes grading sets the tone: for years that was Honduras, and since the early 2020s Brazil semi-washed. Naturals (mostly Brazil and Ethiopia) are kept out because they would swamp the certified pile with the lowest-value arabica, make each certificate less predictable and dull the contract's volatility, pushing price risk into the differentials that hedgers of washed coffee carry. Naturals are priced through differentials to Coffee C and on B3's arabica contract. Washed Vietnamese arabica joins the deliverable list from 2027.</td></tr>
          <tr><td class="l"><b>Inversion and stocks</b></td><td class="l">A hedged importer rolls short futures every two to three months. In an inverted market each roll costs the spread: 1¢ × 37,500 lb = $375 per lot, so a 10¢ inversion costs $3,750 a lot and a 30¢ one $11,250, on top of financing. That makes holding hedged stock expensive, so roasters buy hand to mouth and destination and certified stocks stay low even when world exports rise. Stocks rebuild only when the curve returns to carry, and certification only pays when washed differentials fall to the deliverable parity: low stocks keep the curve inverted and the inversion keeps stocks low until a big crop or a price fall breaks the loop. Low producer/merchant shorts in the COT are the same story seen from the hedge side.</td></tr>
          <tr><td class="l"><b>Tenderable parity</b></td><td class="l">New coffee is certified only when selling it to the exchange beats selling it physically. Certs are rarely pure semi-washed: exporters blend fine or good cup with a smaller share of semi-washed (about 70/30 or less) so the lot passes grading. The exchange pays the futures less 6¢ for Brazil and 1.25¢ for Antwerp; the blend costs its origin price (about FOB) plus all-in shipping to the European warehouse of roughly 8–10¢, about 1¢ of in-charges and grading fees, finance, storage to notice and the cost of failed lots, so Brazil coffee at origin has to trade roughly 20–27¢ under the futures (estimate) before tendering pays (see "Brazil tender parity" on the Brazil tab). In practice Brazil has been certified in size when the ICO Brazilian naturals price traded about 5¢ under the futures, cheaper than the official semi-washed math implies, which suggests blending of cheaper or older coffee (pass rates for new submissions have at times been very low). When differentials are high the flow reverses: certified past-crop washed coffee is cheap to take up and is used as a replacement for Brazil in roaster blends, so certs draw.</td></tr>
          <tr><td class="l"><b>Differentials</b></td><td class="l">Physical coffee is priced as futures plus or minus a differential for origin and quality. Differentials usually move against the futures (growers ask more when futures are low; roasters pay less when futures are high). When they rise together with the futures, origin supply is genuinely short and the market tends to trend; when both fall together, the opposite. An inverted market pushes hedged exporters to discount nearby sales to avoid paying the roll, which is how an inversion starts to break itself.</td></tr>
          <tr><td class="l"><b>Origins that drink their own coffee</b></td><td class="l">Brazil drinks over 20m bags a year, about a third of its crop; Ethiopia keeps about 40%, Indonesia over 40% (mostly robusta). Exports are therefore a poor proxy for the crop in these countries, and a short crop hits exports first. Brazilian roasters switch toward conilon when arabica is expensive, so the same consumption can leave very different arabica and robusta volumes for export, one reason Brazil crop estimates differ by several million bags.</td></tr>
          <tr><td class="l"><b>Index rebalance</b></td><td class="l">Commodity index funds (BCOM, S&amp;P GSCI) reset weights once a year in early January, over about the 6th–10th business day. They sell what outperformed and buy what lagged; the size can be estimated from the CFTC index-trader (CIT) positions and the year's relative performance. Arabica's weight is small (about 3% in BCOM, about 2% in GSCI), so its rebalance flow is usually minor.</td></tr></table></div>
        <p class="note">From the ICE Coffee "C" rules (Appendix IV differentials, Appendix V age adjustments, Rules 8.01–8.14). Premiums for Colombia, Costa Rica, Kenya (+10¢) and Guatemala (+5¢) apply from March 2026; Vietnam is deliverable from May 2027; KC ends with March 2028 and the metric contract (AC) starts May 2028 (see "KC contract: old vs new").</p></div>
      <div class="card" style="margin-top:12px"><h2>Brazil grades, quality and logistics</h2>
        <p>How Brazilian coffee is described, priced and moved, and how that links to what Coffee C will accept. Official classification first, then trade practice and logistics.</p>
        <div class="grid g2"><div><h3>Type by defect count (300 g sample)</h3><div class="tbl"><table><tr><th class="l">Type</th><th>Defects (max)</th></tr>
          <tr><td class="l">2</td><td class="n">4</td></tr><tr><td class="l">3</td><td class="n">12</td></tr><tr><td class="l">4</td><td class="n">26</td></tr>
          <tr><td class="l">5</td><td class="n">46</td></tr><tr><td class="l">6</td><td class="n">86</td></tr><tr><td class="l">7</td><td class="n">160</td></tr>
          <tr><td class="l">8</td><td class="n">360</td></tr><tr><td class="l">beyond 8</td><td class="l">fora de tipo (out of type)</td></tr></table></div>
          <p class="note">Types 2–7 are split into half-steps in the trade (e.g. 4/5, 6/7; IN 8 writes them 2-05 … 2-45, 3, 3-05 …). A lot is also out of type with more than 50 black, 100 sour, 100 black-green beans or 300 defects of certain kinds. A lower type number means a cleaner coffee.</p></div>
          <div><h3>What counts as one defect</h3><div class="tbl"><table><tr><th class="l">Bean or impurity</th><th>Count = 1 defect</th></tr>
          <tr><td class="l">Black bean (preto)</td><td class="n">1</td></tr><tr><td class="l">Sour (ardido), black-green</td><td class="n">2</td></tr>
          <tr><td class="l">Shell (concha)</td><td class="n">3</td></tr><tr><td class="l">Green, underdeveloped (verde, mal granado/chocho), broken</td><td class="n">5</td></tr>
          <tr><td class="l">Insect-bored (brocado): dirty / clean</td><td class="n">2 / 5</td></tr><tr><td class="l">Dried cherry (coco)</td><td class="n">1</td></tr>
          <tr><td class="l">Parchment bean (marinheiro)</td><td class="n">2</td></tr><tr><td class="l">Husk: large / small</td><td class="n">1 / 2–3</td></tr>
          <tr><td class="l">Stick, stone, clod: large / medium / small</td><td class="l">each = 5 / 2 / 1 defects</td></tr></table></div></div></div>
        <div class="grid g2"><div><h3>Screen size (peneira, 1/64 inch)</h3><div class="tbl"><table><tr><th class="l">Screen</th><th class="l">Trade name</th></tr>
          <tr><td class="l">17/18 (and 19)</td><td class="l">large flat bean (chato graúdo), the premium export size</td></tr>
          <tr><td class="l">16, 15</td><td class="l">medium flat (chato médio); screen 16 and up is a common export grade</td></tr>
          <tr><td class="l">14, 13 and below</td><td class="l">small flat (chato miúdo); 13 up is the floor for most standard lots</td></tr>
          <tr><td class="l">Moca 9–13</td><td class="l">peaberry (round bean), screened on its own oval sieves</td></tr>
          <tr><td class="l">Bica corrida</td><td class="l">unscreened run-of-mill</td></tr></table></div>
          <p class="note">Screen 17 lets through beans under 17/64 inch (about 6.7 mm). ICE wants at least half of a Coffee C lot on screen 15 or larger.</p></div>
          <div><h3>Cup (bebida), arabica</h3><div class="tbl"><table><tr><th class="l">Class</th><th class="l">Taste</th><th class="l">Export shorthand</th></tr>
          <tr><td class="l">Estritamente mole</td><td class="l">very soft and sweet, the best of the "mole" group</td><td class="l" rowspan="3">fine cup (strictly soft, soft, softish)</td></tr>
          <tr><td class="l">Mole</td><td class="l">mild, sweet, pleasant</td></tr><tr><td class="l">Apenas mole</td><td class="l">slightly soft, no harshness</td></tr>
          <tr><td class="l">Dura</td><td class="l">harsh, astringent, but no off-taste</td><td class="l">good cup (hard, clean)</td></tr>
          <tr><td class="l">Riada</td><td class="l">a light iodine/medicinal note</td><td class="l" rowspan="3">Rio: phenolic cups, sold at a discount (domestic, soluble and a few traditional export markets)</td></tr>
          <tr><td class="l">Rio</td><td class="l">clear iodine/phenolic taste</td></tr><tr><td class="l">Rio zona</td><td class="l">very strong phenolic taste</td></tr></table></div>
          <p class="note">"Bebida dura para melhor" in a quote means hard cup or better. Rio flavours come from microbial damage during slow or wet drying.</p></div></div>
        <div class="tbl" style="margin-top:8px"><table>
          <tr><td class="l"><b>Processing</b></td><td class="l">Most Brazilian arabica is still natural: the cherry dries whole, which gives heavy body and low acidity and makes it the backbone of espresso blends. Washed coffee has the fruit removed before drying. In between sits the pulped-natural or semi-washed family (cereja descascado, "honey" in specialty): skin off, part of the mucilage left on; more mucilage (black honey) tastes closer to a natural, less (white honey) closer to a washed. Anaerobic and other controlled fermentations are a small premium niche. Cazarini puts a commercial natural Cerrado at roughly −10 to +5 vs KC and an anaerobic natural at about +40 to +80 (Cazarini).</td></tr>
          <tr><td class="l"><b>What ICE will take</b></td><td class="l">Only Brazil semi-washed (pulped natural) is deliverable on Coffee C, at −6¢; naturals are not. In practice certs are blends: about 70% fine or good cup with 30% or less semi-washed, built to pass grading (see "Tenderable parity" above and "Brazil tender parity" on the Brazil tab). The wider semi-washed trades over fine cup (normally about a 10¢ premium), the more it pays to tender.</td></tr>
          <tr><td class="l"><b>The desk's Brazil price series</b></td><td class="l">CEPEA/ESALQ arabica index: type 6, hard cup or better, natural, delivered São Paulo city (domestic). Co-op semi-washed: cereja descascado quotes from Minas Gerais and São Paulo co-ops. Co-op tipo 6 and 6/7: lower naturals. B3 arabica (ICF): type 4/5, hard cup or better ("good cup"), US$ per 60-kg bag. All are origin prices, roughly FOB at best, so add about 8–10¢/lb of all-in shipping to compare with a European ICE warehouse.</td></tr>
          <tr><td class="l"><b>Specialty and new grading</b></td><td class="l">The SCA calls coffee specialty when it cups 80 points or more and has no primary defects in a 350 g sample, a much tighter test than the type table. New 3D scanning machines measure every bean in a sample rather than a hand count, which helps exporters design blends and settle quality disputes (Cazarini).</td></tr>
          <tr><td class="l"><b>Santos and transit</b></td><td class="l">Santos handles over 60% of Brazil's coffee exports, about 25m bags a year; coffee is stuffed into containers in warehouses around the port. Trucks from South Minas (~400 km), Mogiana (~350 km) or the Cerrado (~600 km) take one to two days, plus two to three days of queues at the June–September peak. Sailing times: about 12–15 days to Northern Europe (Antwerp, Hamburg), 18–22 to the US East Coast, 25–30 to the Mediterranean, 35–40 to Japan and Korea (Cazarini). So a lot shipped for grading in Antwerp is in the warehouse within about three weeks of leaving the farm.</td></tr>
          <tr><td class="l"><b>Paperwork</b></td><td class="l">Each shipment needs a MAPA phytosanitary certificate, a certificate of origin and the ICO certificate of origin, plus invoice, packing list and bill of lading; a mistake can hold coffee for weeks. EU buyers now also need farm or co-op geolocation per lot under the EU deforestation rule (EUDR) (Cazarini).</td></tr>
          <tr><td class="l"><b>When growers sell</b></td><td class="l">Brazilian farmers sell mainly when they need cash: inputs, picking wages, land or machinery. Medium and large farms keep stock and can roll coffee from one crop into the next, so a stronger real or high prices do not force sales. In late 2025 a fifth to a third of the arabica crop was still unsold at a point when selling is usually done (end-November), and differentials were at records (Cazarini).</td></tr>
          <tr><td class="l"><b>Exports and where stocks sit</b></td><td class="l">With about 22m bags of home use, a monthly export pace above roughly 3.5m bags points to a big crop. When Brazil differentials are very high, roasters draw on ICE certified stocks instead, the reverse side of tender parity. A stronger real makes it harder for differentials to cheapen, and matters most when farmers want to sell. Exports in 2025 were about 40m bags (−21%), with the US down most (−34%) and Germany the top buyer; US stocks were thin while coffee piled up in Brazil. The shortage was one of location, not of coffee (Cazarini).</td></tr>
          <tr><td class="l"><b>Conilon and the arabica floor</b></td><td class="l">Brazil grows about 20m bags of conilon (Espírito Santo, Bahia, Rondônia), which has filled gaps when Vietnam is short, above all for soluble. Dear robusta means less pressure to swap low-grade arabica (Rio, riada) for robusta, which props up the floor under commodity arabica (Cazarini).</td></tr></table></div>
        <p class="note">Grade tables: MAPA Instrução Normativa nº 8 of 11 June 2003, "Regulamento Técnico de Identidade e de Qualidade para a Classificação do Café Beneficiado Grão Cru" (<a href="https://idrparana.pr.gov.br/sites/iapar/arquivos_restritos/files/documento/2020-07/cafebenef008_03.pdf" target="_blank" rel="noopener">text via IDR-Paraná</a>: defect equivalences, out-of-type limits, screens, cup classes); type-to-defects table from EPAMIG, <a href="https://livrariaepamig.com.br/wp-content/uploads/2023/02/Origem-dos-defeitos-e-procedimentos-para-classificacao-por-tipo-de-cafe-commodity.pdf" target="_blank" rel="noopener">"Origem dos defeitos e procedimentos para classificação por tipo de café commodity"</a>, checked against Conab's <a href="https://antigo.conab.gov.br/images/arquivos/moc/68_NORMAS_ESPECIFICAS_DE_CAFE_SAFRA_2025_2026.pdf" target="_blank" rel="noopener">coffee price-support rules 2025/26</a> (type 6 = up to 86, 7 = 160, 8 = 360). Export shorthand (fine cup, good cup, Rio) is trade usage, not part of IN 8. ICE deliverability from the Coffee "C" rules.
          Sources (Cazarini Coffee Trading blog, read 18 Nov 2026): <a href="https://www.cazarini.com/blog/port-of-santos-coffee-logistics-guide" target="_blank" rel="noopener">Port of Santos</a>, <a href="https://www.cazarini.com/blog/coffee-processing-methods-and-flavor-impact" target="_blank" rel="noopener">processing methods</a>, <a href="https://www.cazarini.com/blog/when-do-producers-sell" target="_blank" rel="noopener">when producers sell</a>, <a href="https://www.cazarini.com/blog/brazil-2025-crop-market-outlook" target="_blank" rel="noopener">2025 crop outlook</a>, <a href="https://www.cazarini.com/blog/january-export-pace-exchange-rates" target="_blank" rel="noopener">export pace and FX</a>, <a href="https://www.cazarini.com/blog/2024-market-wrap-up" target="_blank" rel="noopener">market wrap-up</a>, <a href="https://www.cazarini.com/blog/robusta-vs-arabica-shifting-dynamics" target="_blank" rel="noopener">robusta vs arabica</a>, <a href="https://www.cazarini.com/blog/specialty-coffee-what-sets-it-apart" target="_blank" rel="noopener">specialty coffee</a>, <a href="https://www.cazarini.com/blog/future-grading-3d-scanning-tech" target="_blank" rel="noopener">3D grading</a>.</p></div>
      <div class="card" style="margin-top:12px"><h2>Origin notes: Honduras, Colombia, Brazil</h2>
        <p class="note">Short crop, quality and logistics facts in the desk's words, each with its source. Harvest months for every origin are in the harvest calendar on <a href="#kc-geo" onclick="document.querySelector('#kcTabs button[data-t=kc-geo]').click();return false">Where it's grown</a>. Differential levels are indications from the CIC PNG weekly report (¢/lb vs ICE NY), not trade quotes.</p>
        <div class="tbl"><table><tr><th class="l">Origin</th><th class="l">Topic</th><th class="l">Note</th></tr>
        <tr><td class="l" rowspan="4"><b>Honduras</b></td><td class="l">Regions</td><td class="l">IHCAFE regions Copán, Opalaca, Montecillos, Comayagua, El Paraíso, Agalta; almost all farms above 1,000 m; ~95% smallholders; rust-tolerant types (Lempira, IHCAFE-90) are widespread (<a href="https://sucafina.com/na/origins/honduras" target="_blank" rel="noopener">Sucafina</a>).</td></tr>
        <tr><td class="l">Grades</td><td class="l">HG (high grown) and SHG (strictly high grown, higher altitude) are the export grades; HG is the benchmark washed arabica most often compared with the exchange (trade usage).</td></tr>
        <tr><td class="l">Differentials</td><td class="l">HG diffs move against futures: low in rallies, near tenderable parity when futures collapse, +10 to +37 since 2020 (<a href="https://sucafina.com/na/news/understanding-differentials-and-the-ny-market" target="_blank" rel="noopener">Sucafina</a>); about +22 in mid-Nov 2026 (<a href="https://www.cic.org.pg/category/weekly-market-report/" target="_blank" rel="noopener">CIC PNG</a>).</td></tr>
        <tr><td class="l">2026/27</td><td class="l">Central America and Mexico seen below 18m bags (−9.3%); Honduras among the biggest drops, with bean-filling problems at low altitude in the west. 20-ft containers are often short at peak in Honduras (<a href="https://sucafina.com/na/news/central-america-and-mexico-2026-27-harvest-update" target="_blank" rel="noopener">Sucafina</a>).</td></tr>
        <tr><td class="l" rowspan="4"><b>Colombia</b></td><td class="l">Regions</td><td class="l">South (Huila, Cauca, Nariño, south Tolima) is the largest by volume; Eje Cafetero (Caldas, Quindío, Risaralda) in the centre; the lower, warmer north (Santander, Magdalena) gives heavier cups; ~540,000 growers, most under 5 ha (<a href="https://sucafina.com/na/origins/colombia" target="_blank" rel="noopener">Sucafina</a>).</td></tr>
        <tr><td class="l">Grades</td><td class="l">Excelso (screen 14–16 range, e.g. EP), Supremo (screen 17+), UGQ (usual good quality, the benchmark); EP trades ~2¢ and Supremo ~5–6¢ over UGQ (<a href="https://sucafina.com/na/news/understanding-differentials-and-the-ny-market" target="_blank" rel="noopener">Sucafina</a>). Fully washed, mostly dried on the farm.</td></tr>
        <tr><td class="l">Weather</td><td class="l">Trees need some dry stress before flowering: heavy La Niña rain cuts the crop, a moderate El Niño can lift it (<a href="https://sucafina.com/na/news/impacts-of-el-nino-in-colombia" target="_blank" rel="noopener">Sucafina</a>). 2026/27 main crop no bigger than 2025/26 after wet Feb–Mar flowering and a dry mid-year (<a href="https://sucafina.com/na/news/colombia-2026-27-main-crop-update" target="_blank" rel="noopener">Sucafina</a>).</td></tr>
        <tr><td class="l">Differentials</td><td class="l">UGQ about +72 to +77 in Oct–Nov 2026 (<a href="https://www.cic.org.pg/category/weekly-market-report/" target="_blank" rel="noopener">CIC PNG</a>); Colombia also earns +10¢ on KC delivery from March 2026.</td></tr>
        <tr><td class="l" rowspan="4"><b>Brazil</b></td><td class="l">Qualities</td><td class="l">Santos 17/18 (fine, mild) and Rio Minas 17/18; Rio Minas has a sticky floor near 70¢ and at high prices trades against robusta rather than NY (<a href="https://sucafina.com/na/news/understanding-differentials-and-the-ny-market" target="_blank" rel="noopener">Sucafina</a>). Brazil 3/4 about −18 to −21 in Oct–Nov 2026 (CIC PNG).</td></tr>
        <tr><td class="l">Harvesting</td><td class="l">Flat Cerrado is machine-picked; hilly South Minas ~80% machine, the rest with hand-held vibrating rakes (<a href="https://sucafina.com/na/news/rethinking-brazil-potential" target="_blank" rel="noopener">Sucafina</a>). Conilon in Espírito Santo is almost all irrigated (<a href="https://sucafina.com/na/news/everything-you-need-to-know-about-brazil-s-robusta-harvest" target="_blank" rel="noopener">Sucafina</a>).</td></tr>
        <tr><td class="l">2026/27</td><td class="l">75.4m bags (arabica 49.4m); picking ran late (45% done on 26 June vs 51% average) with good bean size: ~25% of arabica on screen 17+ (<a href="https://sucafina.com/na/news/brazil-2026-27-late-harvest-update" target="_blank" rel="noopener">Sucafina</a>).</td></tr>
        <tr><td class="l">Frost</td><td class="l">The only big origin exposed to severe frost (historically every 5–6 years); a killing frost takes 3–4 years to come back into production (<a href="https://sucafina.com/na/origins/brazil?offerlistmode=0" target="_blank" rel="noopener">Sucafina</a>).</td></tr>
        </table></div></div>`;
    const kc = () => {
      const d = +$('#kcAge').value || 0, org = +$('#kcOrg').value, port = +$('#kcPort').value, imp = Math.max(0, +$('#kcImp').value || 0);
      const B = [[1800, 5325, 175], [1440, 3525, 150], [1080, 2025, 125], [720, 825, 100], [360, 225, 50], [150, 50, 25]];
      let age = 0;
      if (d > 120 && d <= 150) age = 50;
      else if (d > 150) { const [st, base, inc] = B.find(x => d > x[0]); age = base + Math.ceil((d - st) / 30) * inc; }
      if (d > 3600) { age = 18825 + Math.ceil((d - 3600) / 30) * 300; }
      else if (d > 1800) { const T = [[3240, 15525, 275], [2880, 12525, 250], [2520, 9825, 225], [2160, 7425, 200], [1800, 5325, 175]]; const [st, base, inc] = T.find(x => d > x[0]); age = base + Math.ceil((d - st) / 30) * inc; }
      const tot = org + port - 10 * imp - age;
      $('#kcAgeOut').innerHTML = `<div class="grid g4">${kpi('Age discount', '−' + fmt(age / 100, 2) + '¢', d + ' days since grading')}${kpi('Origin', (org >= 0 ? '+' : '') + fmt(org / 100, 2) + '¢', '')}${kpi('Port', fmt(port / 100, 2) + '¢', '')}
        ${kpi('Net to settlement', (tot >= 0 ? '+' : '') + fmt(tot / 100, 2) + '¢/lb', `≈ $${fmt(tot / 100 * 375, 0)} per contract (37,500 lb); grade ${fmt(-imp * 10 / 100, 2)}¢`)}</div>`;
    };
    ['#kcAge', '#kcOrg', '#kcPort', '#kcImp'].forEach(id => $(id).addEventListener('input', kc)); kc();
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

  // CEPEA/ESALQ long histories (data/coffee/brazil_physical_meta.json, pipelines/brazil_physical.py): Brazil conilon vs London,
  // and the CEPEA arabica basis once its history reaches well before 2018
  function BPh(BP) {
    const C = BP && BP.charts; if (!C || !C.robusta_vs_rc) return '';
    const R = C.robusta_vs_rc, A = C.cepea_basis_2nd3rd;
    return `<div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Brazil conilon vs London robusta</h2>${box('kcRob', 240)}
          <p class="note">CEPEA/ESALQ robusta (conilon) index minus the ICE London front, US$/t, weekly average. Latest (${R.now_date}) <b>${sgn(R.now, 0)} $/t</b>, ${ord(R.pct5y)} of 5 years; 5-yr median ${sgn(R.median5y, 0)}. CEPEA is a domestic Espírito Santo price, not FOB, so only the change against its own history matters. A deep Brazil discount makes conilon cheap for blends against arabica.</p></div>
        ${A ? `<div class="card"><h2>Brazil arabica basis since ${A.dates[0].slice(0, 4)} (CEPEA/ESALQ)</h2>${box('kcCep', 240)}
          <p class="note">CEPEA/ESALQ arabica index (tipo 6 bebida dura para melhor, delivered São Paulo) minus ICE KC, ¢/lb, monthly average; purple = vs the 2nd/3rd average, grey = vs the front. Latest week <b>${sgn(A.now, 1, '¢')}</b> vs 2nd/3rd, ${ord(A.pct5y)} of 5 years; median since ${A.dates[0].slice(0, 4)} ${sgn(A.median_all, 1, '¢')}. Red lines: ICE rule changes that matter for Brazil. A domestic naturals price, not semi-washed and not FOB, so read the change against its own history, not the level.</p></div>` : ''}</div>`;
  }
  function BPc(BP) {
    const C = BP && BP.charts; if (!C || !C.robusta_vs_rc) return;
    const line = (id, X, l, y) => chart(id, { type: 'line', data: { labels: X.dates, datasets: [{ label: l, data: X.v, borderColor: PAL[0], pointRadius: 0, borderWidth: 1.2 }] },
      options: { plugins: { legend: { display: false } }, scales: { y: { title: { display: true, text: y } } } } });
    line('kcRob', C.robusta_vs_rc, 'Conilon minus London, $/t', '$/t vs London');
    const M = C.cepea_basis_m;
    if (C.cepea_basis_2nd3rd && M) chart('kcCep', { type: 'line', data: { labels: M.months, datasets: [
        { label: 'vs KC 2nd/3rd', data: M.b23, borderColor: '#7d3c98', pointRadius: 0, borderWidth: 1.4 },
        { label: 'vs KC front', data: M.bfront, borderColor: '#95a5a6', pointRadius: 0, borderWidth: 1 }] }, plugins: [ruleLines(M.markers, M.months)],
      options: { scales: { y: { title: { display: true, text: '¢/lb vs KC' } } } } });
  }

  // Brazil tender parity (data/coffee/tender_parity.json, models/brazil_tender_parity.py): cost of a blended lot in the
  // Antwerp warehouse vs what the exchange pays; semi-washed vs fine/good cup differential history
  function TPh(T) {
    if (!T || !T.stack) return '';
    const N = T.now, W = [['w15', '15% semi-washed'], ['w30', '30% semi-washed']], keys = Object.keys(T.stack.w30.costs);
    const row = (l, f, b) => `<tr><td class="l">${b ? '<b>' + l + '</b>' : l}</td>${W.map(([k]) => `<td class="n">${b ? '<b>' + f(T.stack[k]) + '</b>' : f(T.stack[k])}</td>`).join('')}</tr>`;
    return `<div class="grid g2" style="margin-top:12px">
      <div class="card"><h2>Brazil tender parity</h2>
        <p class="note" style="margin-top:0">${T.reading.join(' ')}</p>${box('kcTP', 230)}
        <p class="note">Semi-washed (co-op cereja descascado) minus fine/good cup (CEPEA tipo 6), ¢/lb, with the tender margin of a 30% semi-washed blend. Dashed: the usual ~10¢ semi-washed premium. Prices at origin, treated as about FOB.</p></div>
      <div class="card"><h2>Cost to tender in Antwerp vs exchange value <span class="note">as of ${N.date}, ¢/lb</span></h2>${N.sw_frozen ? `<p class="note">The co-op semi-washed quote stopped on ${N.date} (source no longer reachable); this card stays at that date. CEPEA tipo 6 (Ma\'s weekly upload) remains the Brazil physical price on the other panels.</p>` : ''}
        <div class="tbl"><table><tr><th class="l">Item</th>${W.map(([, l]) => `<th>${l}</th>`).join('')}</tr>
        ${row('Blend at origin (semi-washed + CEPEA fine/good cup)', x => fmt(x.blend, 1))}
        ${keys.map(k => row(T.cost_labels[k] || k, x => fmt(x.costs[k], 2))).join('')}
        ${row('Cost in the Antwerp warehouse', x => fmt(x.cost_total, 1), 1)}
        ${row(`Exchange value: ${N.kc2_contract.replace(/^KC/, '')} ${fmt(N.kc2, 1)} − 6 Brazil − 1.25 Antwerp`, x => fmt(x.exchange_value, 1))}
        ${row('Tender margin', x => sgn(x.margin, 1, '¢'), 1)}
        ${row('Margin across the cost ranges', x => `${sgn(x.margin_high_cost, 0)} to ${sgn(x.margin_low_cost, 0)}`)}</table></div>
        <p class="note">Blend shares and the 8–10¢ all-in shipping are trading estimates; other items are listed with their source or as assumptions in the data file. Brazil pass rate ${T.pass_rate}% (ICE grading files). From 30 Dec 2026 new EU-port gradings need EUDR due-diligence data.</p></div></div>`;
  }
  function TPc(T) {
    if (!T || !T.history) return;
    const H = T.history;
    chart('kcTP', { type: 'line', data: { labels: H.dates, datasets: [
      { label: 'Semi-washed − fine/good cup', data: H.sw_minus_fc, borderColor: '#7d3c98', pointRadius: 0, borderWidth: 1.4, spanGaps: true },
      { label: 'Usual (~10¢)', data: H.dates.map(() => T.now.ma_normal), borderColor: '#95a5a6', borderDash: [5, 4], pointRadius: 0, borderWidth: 1 },
      { label: 'Tender margin, 30% semi-washed', data: H.margin_w30, borderColor: '#d68910', pointRadius: 0, borderWidth: 1.2, spanGaps: true }] },
      options: { scales: { y: { title: { display: true, text: '¢/lb' } } } } });
  }

  async function brazil() {
    await load();
    const BP = await getJSON('data/coffee/brazil_physical_meta.json').catch(() => null);
    const TP = await getJSON('data/coffee/tender_parity.json').catch(() => null);
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
      ${TPh(TP)}
      ${BPh(BP)}
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
    BPc(BP); TPc(TP);
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
    body().innerHTML = `<div class="grid g4">${T.map(([t, l]) => kpi(`${l}, ${mn(C.month)} to ${ordn(+C.asof.slice(8))}`, k(C.mtd[t]) + ' bags',
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
        ${kpi('Root-zone soil moisture', X.sm100_p == null ? '–' : ordn(X.sm100_p) + ' pct', '28–100 cm, vs same week 2011–25')}
        ${kpi('Frost watch', X.f16_tmin == null ? '–' : fmt(X.f16_tmin, 1) + ' °C', X.coldest_forecast ? `coldest forecast night, weighted; lowest point ${X.coldest_forecast[1].toFixed(1)} °C; ${pc(X.frost_risk_share)} of output ≤3 °C` : '')}</div>
      <div class="tbl" style="margin-top:8px"><table><tr><th class="l">Region (weather point)</th><th>Conab ${W.conab.season} output, k bags</th><th>Share</th><th>30d rain, mm</th><th>vs avg</th><th>Season rain</th><th>vs avg</th><th>Soil moisture pct</th><th>16-day rain</th><th>Coldest night ahead</th></tr>
        ${X.regions.map(r => `<tr><td class="l">${r.name}<br><span class="note">${r.conab_rows.join(', ')}</span></td><td class="n">${fmt(r.prod_k, 0)}</td><td class="n">${fmt(r.share, 1)}%</td>
          <td class="n">${r.has_weather ? fmt(r.r30, 0) : '<span class="note">pending</span>'}</td><td class="n">${r.r30_n ? sgn(100 * (r.r30 / r.r30_n - 1), 0, '%') : '–'}</td>
          <td class="n">${r.rstd != null ? fmt(r.rstd, 0) : '–'}</td><td class="n">${r.rstd_n ? sgn(100 * (r.rstd / r.rstd_n - 1), 0, '%') : '–'}</td>
          <td class="n">${r.sm100_p ?? '–'}</td><td class="n">${r.f16_rain != null ? fmt(r.f16_rain, 0) : '–'}</td><td class="n">${r.f16_tmin != null ? fmt(r.f16_tmin, 1) + ' °C' : '–'}</td></tr>`).join('')}</table></div>
      <p class="note">Covers ${pc(X.mapped_share)} of Brazil's ${t} output; weather available for ${pc(X.weather_share)} of that (missing points drop out and the rest are re-weighted).</p></div>`; };
    body().innerHTML = card('arabica', 'Arabica') + `<div style="margin-top:12px"></div>` + card('conilon', 'Conilon') +
      `<div class="grid g2" style="margin-top:12px">${['arabica', 'conilon'].map(t => { const c = (W.types[t] || {}).season_curve; if (!c) return '';
        const td = c.to_date; return `<div class="card"><h2>${t === 'arabica' ? 'Arabica' : 'Conilon'}: season rain since 1 September <span class="note">production-weighted, mm</span></h2>
        ${td ? `<p>${c.season} to date: <b>${fmt(td.mm, 0)} mm</b>, ${td.pct_mean != null ? td.pct_mean + '% of the ' + c.years + ' average' : ''}${td.last != null ? `; last season at the same point ${fmt(td.last, 0)} mm` : ''}${td.rank ? ` (ranks ${td.rank} of ${td.n + 1} seasons, 1 = driest)` : ''}.</p>` : `<p class="note">Current-season daily data loads with the next weather run.</p>`}
        <div style="position:relative;height:260px"><canvas id="kcSc_${t}"></canvas></div></div>`; }).join('')}</div>` +
      (H.length > 1 ? `<div class="card" style="margin-top:12px"><h2>Weighted rain index, daily readings</h2><div style="position:relative;height:200px"><canvas id="kcWh"></canvas></div><p class="note">Recorded from 1 Nov 2026, one point per run.</p></div>` : '') +
      `<p class="note">Weights: Conab survey ${W.conab.survey} of ${W.conab.season}, production by state and by Minas Gerais and Bahia region. Weather: Open-Meteo ERA5 and forecast at one point per region, against 2011–2025 (see Where it's grown for each point). Weather through ${W.weather_through || '–'}. For forecasts also check Somar Meteorologia and Climatempo.</p>`;
    ['arabica', 'conilon'].forEach(t => { const c = (W.types[t] || {}).season_curve; if (!c) return;
      chart('kcSc_' + t, { type: 'line', data: { labels: c.labels, datasets: [
        { label: '90th pct', data: c.p90, borderColor: 'rgba(127,140,141,.25)', backgroundColor: 'rgba(127,140,141,.15)', pointRadius: 0, fill: '+1' },
        { label: '10th pct', data: c.p10, borderColor: 'rgba(127,140,141,.25)', pointRadius: 0, fill: false },
        { label: 'Average ' + (c.years || ''), data: c.mean, borderColor: '#7f8c8d', borderDash: [5, 4], pointRadius: 0 },
        { label: c.last_season, data: c.last, borderColor: '#d68910', pointRadius: 0 },
        { label: c.season, data: c.current, borderColor: '#2c6fbb', borderWidth: 2.6, pointRadius: 0 }] }, options: { plugins: { legend: { labels: { filter: i => !/pct/.test(i.text) } } } } }); });
    if (H.length > 1) chart('kcWh', { type: 'line', data: { labels: H.map(r => r.date), datasets: [['arabica_r30_pct_normal', 'Arabica 30-day rain % of avg', '#7d3c98'], ['conilon_r30_pct_normal', 'Conilon 30-day rain % of avg', '#d68910'],
      ['arabica_rstd_pct_normal', 'Arabica season rain % of avg', '#2c6fbb']].map(([k, l, c]) => ({ label: l, data: H.map(r => r[k]), borderColor: c, pointRadius: 0 })) } });
  }

  // Certs profile and delivery economics: data/coffee/certs_profile.json (models/coffee_certs_profile.py).
  let CP = null;
  const loadCP = () => CP ? Promise.resolve(CP) : getJSON('data/coffee/certs_profile.json').then(d => (CP = d));
  const ruleLines = (marks, labels) => ({ id: 'ruleLines', afterDatasetsDraw(ch) {
    const { ctx, chartArea: a, scales: { x } } = ch; if (!a) return; ctx.save(); ctx.font = '10px system-ui,sans-serif';
    const by = {}; marks.forEach(m => { (by[m.date] ||= []).push(m.label); });
    Object.entries(by).forEach(([d, ls], k) => { const i = labels.indexOf(d); if (i < 0) return; const px = x.getPixelForValue(i);
      if (px < a.left || px > a.right) return;
      ctx.strokeStyle = 'rgba(192,57,43,.55)'; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = '#a93226'; ctx.save(); ctx.translate(px + 3, a.top + 4); ctx.rotate(Math.PI / 2); ctx.fillText(ls.join(' · '), 0, 0); ctx.restore(); });
    ctx.restore(); } });
  async function cprof() {
    await loadCP();
    const D = CP, H = D.history, A = D.age_hist, S = D.seasonal, Cu = D.current, E = D.economics, Ph = D.physical, R = D.rules, al = E.all;
    const c2 = v => sgn(v, 2, '¢'), kb = v => v == null ? '–' : f0(v / 1000) + 'k';
    const sh1 = A.share_over_1y.at(-1), shAvg = A.share_over_1y.slice(0, -1).filter(v => v != null), shMean = shAvg.reduce((a, b) => a + b, 0) / shAvg.length;
    const ctd100 = E.ctd_n.find(r => r.lots === 100), braA = E.by_origin_port.find(r => r.origin === 'Brazil' && r.port === 'Antwerp');
    const GP = D.gap, SG = Object.fromEntries(GP.signal.map(r => [r.key, r])), om = SG.oth, bm = SG.bra, sw = (Ph.brazil_ladder || []).find(l => /Semi-washed/.test(l.name));
    const dl = m => { const [y, mm] = m.split('-'); return MON[+mm - 1] + ' ' + y.slice(2); };
    const rel = r => r.adjusted > 3 ? 'cheaper than usual' : r.adjusted < -3 ? 'dearer than usual' : 'about normal';
    const spread = E.futures.settle - E.futures.next_settle;
    const top3 = E.ctd_top.slice(0, 3).map(r => `${r.origin} in ${r.port}`).join(', ');
    const brief = `<div class="card" style="margin:0 0 12px;border-left:4px solid var(--acc)"><h3 style="margin-top:0">Coffee certs: ${f0(Cu.total_lots)} lots on board; washed certs ${rel(om)} against physical, Brazil ${rel(bm)}</h3><ul style="margin:0;padding-left:18px">
      <li style="margin:4px 0"><b>Size and age.</b> ${f0(Cu.total_bags)} bags certified on ${Cu.daily_date} (about ${f0(Cu.total_lots)} lots), with ${f0(Cu.pending)} bags waiting for grading. The ${S.month} ${S.latest.slice(0, 4)} month-end (${kb(S.bags.at(-1))}) was the ${ordn(S.rank_low)} lowest ${S.month} of ${S.n} years, against a 10-year ${S.month} average of ${kb(S.avg10)}. ${f1(sh1)}% of the stock was over a year old at the ${A.delivery.at(-1)} delivery (2016–25 average ${f1(shMean)}%); the bag-weighted age is ${f0(al.avg_age)} days.</li>
      <li style="margin:4px 0"><b>Cost to stop everything.</b> Taking the whole stock on ${E.futures.contract} delivery would cost on average <b>${c2(al.total)}/lb against the futures</b> (origin ${c2(al.odiff)}, port ${c2(al.pdiff)}, age ${c2(al.age)}, weight allowance ${c2(al.weight)}, load-out and rent ${c2(al.oca_rca)}). Half the lots sit between ${c2(E.dist.p25)} and ${c2(E.dist.p75)}. On ${E.futures.next} the same coffee is ${c2(al.total_n1)} (older, and the EUDR transition discount starts).</li>
      <li style="margin:4px 0"><b>Cheapest to deliver.</b> Deliverers hand over the lowest-value lots first: the first 100 lots average ${c2(ctd100?.avg)}, mostly old washed coffee in Antwerp (${top3}). Fresh Brazil in Antwerp, the biggest block (${f0(braA?.lots)} lots), invoices at ${c2(braA?.total)}.</li>
      <li style="margin:4px 0"><b>Exchange against physical, against its own history.</b> ICO prices fresh export grades ex-dock, the certs are older warehouse coffee, so the raw gap is only read against its usual level at past deliveries. Other Milds: ${c2(om.now.gap)} for ${dl(GP.current)} (${dl(GP.previous)}: ${c2(om.prev?.gap)}) against a normal ${c2(om.normal.median)} (${om.basis === 'post' ? 'deliveries since the Dec 2023 re-grading ban' : 'all deliveries since 2016'}, ${om.normal.n} deliveries): <b>${sgn(om.adjusted, 1, '¢')}</b>, ${rel(om)}. Brazilian Naturals: ${c2(bm.now.gap)} (${dl(GP.previous)}: ${c2(bm.prev?.gap)}) against ${c2(bm.normal.median)}: <b>${sgn(bm.adjusted, 1, '¢')}</b>, ${rel(bm)}. Brazil semi-washed at origin is ${c2(sw?.basis)} (${sw?.date}), before freight.</li>
      <li style="margin:4px 0"><b>Rules now vs before.</b> Since 1 Dec 2023 a de-certified lot cannot be graded again, so the age discount and weight allowance stay with the coffee; before, old coffee could be re-graded as fresh, which kept the curve in carry and made stopping delivery risky.</li>
      <li style="margin:4px 0"><b>For the front spread.</b> ${E.futures.contract} first notice is ${Cu.first_notice || 'in late November'}; ${E.futures.contract} is ${sgn(spread, 2, '¢')} over ${E.futures.next}. The pile is small, and washed certs are ${rel(om)} against physical, which supports the nearby; but ${kb(Cu.pending)} bags pending grading (mostly Brazil in Antwerp) could add up to about ${f0(Cu.pending / 283.5)} lots if they pass, the main risk to the inversion.</li></ul>
      <p class="note" style="margin-bottom:0">Certs ${Cu.daily_date}; age split ${Cu.aging_date} rolled forward to ${Cu.daily_date} (estimate); futures ${E.futures.date}; ICO ${Ph.ico_month}.</p></div>`;
    const tAge = (rows, key) => `<table><tr><th class="l">${key === 'port' ? 'Port' : 'Origin'}</th>${Cu.port_age.groups.map(g => `<th>${g}</th>`).join('')}<th>Total</th><th>Over 1 yr</th></tr>
      ${rows.map(r => `<tr><td class="l">${r[key]}</td>${r.bags.map(v => `<td class="n">${v ? f0(v) : '–'}</td>`).join('')}<td class="n"><b>${f0(r.total)}</b></td><td class="n">${f0((r.bags[2] + r.bags[3] + r.bags[4]) / r.total * 100)}%</td></tr>`).join('')}</table>`;
    const ecoRows = E.by_origin_port.filter(r => r.lots >= 0.5).map(r => `<tr><td class="l">${r.origin}</td><td class="l">${r.port}</td><td class="n">${f0(r.bags)}</td><td class="n">${f0(r.lots)}</td><td class="n">${f0(r.avg_age)}</td>
      <td class="n">${f2(r.odiff)}</td><td class="n">${f2(r.pdiff)}</td><td class="n">${f2(r.age)}</td><td class="n">${f2(r.weight)}</td><td class="n">${f2(r.oca_rca)}</td><td class="n"><b>${c2(r.total)}</b></td><td class="n">${c2(r.total_n1)}</td></tr>`).join('');
    const ruleRows = R.changes.slice().reverse().map(r => `<tr><td class="l" style="white-space:nowrap">${r.effective_date}</td><td class="l">${r.first_contract}</td><td class="l">${r.rule_area}</td><td class="l">${r.plain_english}</td><td class="l"><a href="${r.source_url}" target="_blank" rel="noopener">source</a></td></tr>`).join('');
    const on = R.origin_now.pts, nx = R.origin_next.pts, pn = R.port_now.pts;
    const oList = Object.keys({ ...on, ...nx }).sort((a, b) => (on[b] ?? -9e9) - (on[a] ?? -9e9) || a.localeCompare(b));
    body().innerHTML = `${brief}
      <div class="grid g4">
        ${kpi('Certified now', f0(Cu.total_bags) + ' bags', `${Cu.daily_date}; ~${f0(Cu.total_lots)} lots; ${kb(Cu.pending)} pending grading`)}
        ${kpi(`${S.month} month-end vs history`, kb(S.bags.at(-1)), `${ordn(S.rank_low)} lowest of ${S.n}; 10-yr ${S.month} range ${kb(S.min10)}–${kb(S.max10)}`)}
        ${kpi('Cost to stop all certs', c2(al.total) + '/lb', `bag-weighted, vs ${E.futures.contract} ${f2(E.futures.settle)}; ${E.futures.next}: ${c2(al.total_n1)}`)}
        ${kpi('First 100 lots delivered', c2(ctd100?.avg) + '/lb', `cheapest to deliver; average age ${f0(al.avg_age)} days to delivery`)}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>ICE certified arabica since ${H.months[0].slice(0, 4)}</h2>
          <div style="display:flex;gap:10px;flex-wrap:wrap">${rngBar('cpH', ['10Y', 'All'], '10Y')}${rngBar('cpV', ['Total', 'By port'], 'Total')}</div>${box('cpH', 300)}
          <p class="note">Month-end certified bags (ICE). Red dashed lines mark the main rule changes (table below). Stock levels before and after each line are not like for like: until December 2023 old coffee could be de-certified and graded again as fresh.</p></div>
        <div class="card"><h2>Certified stock by age, all ports</h2>${box('cpA', 300)}
          <p class="note">Monthly ICE aging report, bags by days since grading measured to the next delivery month, all ports combined; line = share older than one year (right axis).</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>${S.month} month-end certs, every year</h2>${box('cpS', 240)}<p class="note">Same calendar month each year; dashed line = average of the previous 10 years.</p></div>
        <div class="card"><h2>Average invoice discount of the certified stock</h2>${box('cpV2', 240)}<p class="note">Bag-weighted, ¢/lb against the futures, from the monthly aging report with the port and age rules in force for each delivery month; the second line adds the weight allowance at the front-month price. Origin is not in the monthly file, so origin differentials are left out here.</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Current certs by port and age</h2><div class="tbl">${tAge(Cu.port_age.rows, 'port')}</div>
          <p class="note">Age split estimated to ${Cu.daily_date}: ICE's ${Cu.aging_date} aging report rolled forward with the daily reports (new passes go into the youngest bucket; other falls are taken out of each origin and port in proportion). Ages are days since grading at the ${Cu.delivery} delivery.</p></div>
        <div class="card"><h2>Current certs by origin and age <span class="note">(estimate)</span></h2><div class="tbl">${tAge(Cu.origin_age.rows, 'origin')}</div>
          <p class="note">Origin by port is reported daily by ICE; the age split by origin is not published and is <b>estimated</b> from grading results by origin and the port aging report.</p></div></div>
      <div class="card" style="margin-top:12px"><h2>Delivery economics by origin and port <span class="note">¢/lb against ${E.futures.contract} (${f2(E.futures.settle)}, ${E.futures.date}); negative = the receiver pays less than the futures</span></h2>
        <div class="tbl"><table><tr><th class="l">Origin</th><th class="l">Port</th><th>Bags</th><th>Lots</th><th>Avg age (d)</th><th>Origin</th><th>Port</th><th>Age</th><th>Weight</th><th>Load-out + rent</th><th>Invoice vs ${E.futures.contract}</th><th>Same on ${E.futures.next}</th></tr>
        ${ecoRows}<tr><td class="l"><b>All certs</b></td><td></td><td class="n"><b>${f0(al.bags)}</b></td><td class="n"><b>${f0(al.lots)}</b></td><td class="n">${f0(al.avg_age)}</td><td class="n">${f2(al.odiff)}</td><td class="n">${f2(al.pdiff)}</td><td class="n">${f2(al.age)}</td><td class="n">${f2(al.weight)}</td><td class="n">${f2(al.oca_rca)}</td><td class="n"><b>${c2(al.total)}</b></td><td class="n">${c2(al.total_n1)}</td></tr></table></div>
        <p class="note">Origin, port and age differentials, the weight allowance and the load-out (OCA) and rent (RCA) adjustments follow the ICE Coffee "C" rules for the delivery month (port averages of the posted warehouse rates). Grade (imperfection) differentials are not included: ICE does not publish them per lot. Lots ≈ bags × bag weight ÷ 37,500 lb. The comparison with physical prices is in the next card.</p></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Cheapest to deliver: the order lots would be tendered</h2>${box('cpC', 260)}
          <div class="tbl"><table><tr><th class="l">Lots delivered</th><th>Average ¢/lb</th><th>Range</th></tr>${E.ctd_n.map(r => `<tr><td class="l">${r.lots === 'all' ? `All (${f0(al.lots)})` : 'First ' + r.lots}</td><td class="n"><b>${c2(r.avg)}</b></td><td class="n">${f2(r.worst)} to ${f2(r.best)}</td></tr>`).join('')}</table></div>
          <p class="note">Every certified lot sorted by its invoice value against the futures, lowest first: the deliverer gives up the lots worth least on the invoice first. The whole stock is only about ${f0(al.lots)} lots, so the usual 1,000 / 2,500-lot steps are not reached.</p>
          <div class="tbl"><table><tr><th class="l">First 100 lots: origin</th><th class="l">Port</th><th>Lots</th><th>Days since grading</th><th>¢/lb</th></tr>${E.ctd_top.map(r => `<tr><td class="l">${r.origin}</td><td class="l">${r.port}</td><td class="n">${f1(r.lots)}</td><td class="n">${f0(r.age_from)}–${f0(r.age_to)}</td><td class="n">${f2(r.diff_from)} to ${f2(r.diff_to)}</td></tr>`).join('')}</table></div></div>
        <div class="card"><h2>Exchange vs ICO physical, against its own history</h2>
          <p class="note" style="margin-top:0"><b>What ICO prices:</b> fresh, current-crop export grades (e.g. Honduras HG, Guatemala HB, Santos 2/3 and 3/4) for prompt shipment, ex-dock in the USA and Europe (Germany, France), built as futures plus trade differentials, US ¢/lb. <b>What the certs are:</b> graded coffee of any age in exchange warehouses, invoiced with age, weight, port and origin adjustments. So only the change in the gap is read, not its level.</p>
          <div class="tbl"><table><tr><th class="l">ICO group</th><th>Now vs normal</th><th>${dl(GP.current)} gap</th><th>${dl(GP.previous)} gap</th><th>Normal (median)</th><th>10–90% range</th><th>Deliveries</th><th>Percentile</th></tr>
          ${GP.signal.map(r => `<tr><td class="l">${r.group}</td><td class="n"><b>${sgn(r.adjusted, 1, '¢')}</b></td><td class="n">${c2(r.now.gap)}</td><td class="n">${c2(r.prev?.gap)}</td><td class="n">${c2(r.normal.median)}</td><td class="n">${f1(r.normal.p10)} to ${f1(r.normal.p90)}</td><td class="n">${r.normal.n}${r.basis === 'post' ? ' (since Mar 24)' : ' (since Mar 16)'}</td><td class="n">${ordn(r.pctile)}</td></tr>`).join('')}</table></div>
          ${box('cpG', 230)}
          <p class="note">Gap = ICO group price minus the cert pool's invoice value, both against the KC contract being delivered, ¢/lb, one point per KC delivery from ${dl(GP.first)}: ICO month and pool from the aging report two months before delivery (the last data before first notice), ICO market (Europe / US) weighted by where the certs sit. Positive "now vs normal" = certs cheaper against physical than usual. Where the gap level moved after the December 2023 re-grading ban, the normal is taken from deliveries since March 2024 only (dashed line on the chart). Colombian Milds rest on a few hundred bags and are shown for completeness.</p>
          <h3>Brazil by export quality <span class="note">(at origin, before freight, ¢/lb vs KC front)</span></h3>
          <div class="tbl"><table>${(Ph.brazil_ladder || []).map(l => `<tr><td class="l">${l.name}</td><td class="n">${l.date}</td><td class="n"><b>${c2(l.basis)}</b></td></tr>`).join('')}</table></div>
          <p class="note">Brazil on the exchange (Antwerp, fresh) invoices at ${c2(braA?.fresh)}. The difference to the origin price has to cover freight, port and grading costs; it is what draws semi-washed Brazil to the exchange.</p></div></div>
      <div class="card" style="margin-top:12px"><h2>Rule changes: ICE Coffee "C"</h2><div class="tbl"><table><tr><th class="l">Effective</th><th class="l">First contract</th><th class="l">Area</th><th class="l">What changed</th><th class="l">Link</th></tr>${ruleRows}</table></div>
        <p class="note">From the ICE rulebook amendment notes, ICE filings and notices. Origin and port differentials apply by delivery month to every lot delivered, whenever it was graded; the age discount runs from each lot's grading certificate. The 10¢ premiums for Colombia, Costa Rica and Kenya and 5¢ for Guatemala apply from the March 2026 contract (ICE notice 16 Jan 2024; rulebook amendment note of 20 Dec 2023); May 2027 adds Vietnam. See the "KC contract: old vs new" tab.</p></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Differentials in force</h2><div class="tbl"><table><tr><th class="l">Origin</th><th>${Cu.delivery} delivery, ¢/lb</th><th>From May 2027</th></tr>${oList.map(o => `<tr><td class="l">${o}</td><td class="n">${on[o] == null ? 'not deliverable' : sgn(on[o] / 100, 2)}</td><td class="n">${nx[o] == null ? '–' : sgn(nx[o] / 100, 2)}</td></tr>`).join('')}</table></div>
          <p class="note">Ports: ${Object.entries(pn).map(([k, v]) => `${k.toLowerCase().replace(/(^|[\s/])\w/g, s => s.toUpperCase())} ${v ? sgn(v / 100, 2) : 'basis'}`).join(', ')}.</p></div>
        <div class="card"><h2>Age discount and other adjustments</h2><div class="tbl"><table><tr><th class="l">Days since grading</th><th>Discount</th></tr><tr><td class="l">0–120</td><td class="n">none</td></tr><tr><td class="l">121–150</td><td class="n">0.50¢</td></tr>
          ${R.age_bands.bands.map(([lo, hi, base, st]) => `<tr><td class="l">${lo + 1}–${hi > 9999 ? '' : hi}</td><td class="n">${f2(base / 100)}¢ + ${f2(st / 100)}¢ per 30 days</td></tr>`).join('')}</table></div>
          <p class="note">Weight allowance: 0.5% of the weight for the second month after weighing plus 0.125% a month after that, at the invoice price. Load-out (OCA) and rent (RCA) adjustments: the delivering warehouse's posted rates against the New York average (rent × 2 for Mar/May/Jul, × 3 for Sep/Dec). EUDR: transition stock in European ports loses 0.25¢ a month from January 2027 (from the March 2027 contract). Source: <a href="${R.source}" target="_blank" rel="noopener">ICE rulebook, Coffee "C"</a>, read ${R.read_on}.</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Front / second spread since ${D.spreads.first.slice(0, 4)} (% of price)</h2>${box('cpSp', 260)}<p class="note">Monthly average of front minus second (positive = inverted), front rolled at first notice; per-contract ICE settlements. Red lines: rule changes. Before Dec 2023 old coffee could be re-graded as fresh, so the earlier curve is not like for like.</p></div>
        <div class="card"><h2>${D.spreads.now.pair} at the same point, every year</h2>${box('cpSy', 260)}<p class="note">${D.spreads.now.pair} now ${sgn(D.spreads.now.s12, 2, '¢')} (${sgn(D.spreads.now.pct, 2, '%')} of price), ${D.spreads.now.bd_to_fnd} business days before first notice; bars = the same spread at the same distance in earlier years (red = now).</p></div></div>
      <p class="note">Variables used: ${D.variables.join('; ')}; KC calendar spreads from per-contract settlements (${D.spreads.first.slice(0, 4)} on). Built ${D.built}.</p>`;
    // charts
    const SPk = D.spreads;
    chart('cpSp', { type: 'line', data: { labels: SPk.months, datasets: [{ label: 'Front − second, % of price', data: SPk.s12_pct, borderColor: '#7d3c98', pointRadius: 0 }] }, plugins: [ruleLines(SPk.markers, SPk.months)] });
    chart('cpSy', { type: 'bar', data: { labels: SPk.same_point.map(r => r.year), datasets: [{ label: `${SPk.now.pair}, % of price`, data: SPk.same_point.map(r => r.pct), backgroundColor: SPk.same_point.map((r, i) => i === SPk.same_point.length - 1 ? '#c0392b' : '#7d3c98') }] } });
    const drawH = () => { const r = $('.rng[data-for=cpH] button.on').dataset.r, v = $('.rng[data-for=cpV] button.on').dataset.r;
      const a = r === 'All' ? 0 : Math.max(0, H.months.length - 121), lab = H.months.slice(a);
      const ds = v === 'Total' ? [{ label: 'Certified, bags', data: H.total.slice(a), borderColor: '#7d3c98', backgroundColor: 'rgba(125,60,152,.12)', fill: true, pointRadius: 0 }]
        : Object.entries(H.by_port).map(([p, s], i) => ({ label: p, data: s.slice(a), backgroundColor: PAL[i % PAL.length], borderColor: PAL[i % PAL.length], fill: true, pointRadius: 0, borderWidth: 0, stack: 's' }));
      chart('cpH', { type: 'line', data: { labels: lab, datasets: ds }, plugins: [ruleLines(H.markers, lab)],
        options: { scales: { y: { stacked: v !== 'Total', beginAtZero: true, ticks: { callback: x => f1(x / 1e6) + 'm' } } } } }); };
    drawH(); rngWire('cpH', drawH); rngWire('cpV', drawH);
    const ac = ['#2c6fbb', '#17a589', '#d68910', '#c0392b', '#7d3c98'];
    chart('cpA', { type: 'line', data: { labels: A.months, datasets: [...A.groups.map((g, i) => ({ label: g, data: A.bags[g], backgroundColor: ac[i], borderColor: ac[i], fill: true, pointRadius: 0, borderWidth: 0, stack: 's', yAxisID: 'y' })),
      { label: 'Over 1 yr, %', data: A.share_over_1y, borderColor: '#222', borderWidth: 1.5, pointRadius: 0, fill: false, yAxisID: 'y1' }] }, plugins: [ruleLines(H.markers.filter(m => m.date >= A.months[0]), A.months)],
      options: { scales: { y: { stacked: true, beginAtZero: true, ticks: { callback: x => f1(x / 1e6) + 'm' } }, y1: { position: 'right', min: 0, max: 100, grid: { display: false } } } } });
    chart('cpS', { type: 'bar', data: { labels: S.years, datasets: [{ label: `${S.month} month-end, bags`, data: S.bags, backgroundColor: S.years.map((y, i) => i === S.years.length - 1 ? '#c0392b' : '#7d3c98') },
      { type: 'line', label: '10-yr average', data: S.years.map((y, i) => i >= S.years.length - 11 ? S.avg10 : null), borderColor: '#333', borderDash: [4, 3], pointRadius: 0 }] },
      options: { scales: { y: { beginAtZero: true, ticks: { callback: x => f1(x / 1e6) + 'm' } } } } });
    chart('cpV2', { type: 'line', data: { labels: A.months, datasets: [{ label: 'Port + age, ¢/lb', data: A.port_age_disc, borderColor: '#2c6fbb', pointRadius: 0 },
      { label: 'Port + age + weight allowance', data: A.port_age_weight, borderColor: '#c0392b', pointRadius: 0 }] }, plugins: [ruleLines(H.markers.filter(m => m.date >= A.months[0]), A.months)] });
    const gl = GP.deliveries.map(h => dl(h.delivery)), gcol = { oth: '#2c6fbb', bra: '#d68910', col: '#17a589' };
    const regIdx = GP.deliveries.findIndex(h => h.regime === 'post');
    chart('cpG', { type: 'line', data: { labels: gl, datasets: GP.signal.map(r => ({ label: r.group, data: GP.deliveries.map(h => h.groups[r.key]?.gap ?? null), borderColor: gcol[r.key], pointRadius: 2, borderWidth: r.key === 'col' ? 1 : 2 })) },
      plugins: [ruleLines([{ date: gl[regIdx], label: 'Re-grading barred' }], gl)], options: { scales: { y: { title: { display: true, text: '¢/lb' } } } } });
    const cv = E.ctd_curve;
    chart('cpC', { type: 'line', data: { labels: cv.map(p => f0(p.cum_lots)), datasets: [{ label: 'Invoice vs futures, ¢/lb (lots sorted lowest first)', data: cv.map(p => Math.max(p.diff, -60)), borderColor: '#7d3c98', stepped: true, pointRadius: 0 }] },
      options: { plugins: { tooltip: { callbacks: { label: c => { const p = cv[c.dataIndex]; return `${f2(p.diff)}¢ ${p.origin || ''} ${p.port || ''} ${p.age ? p.age + ' d' : ''}`; } } } },
        scales: { x: { title: { display: true, text: 'cumulative lots' } }, y: { title: { display: true, text: '¢/lb (floored at −60)' } } } } });
  }
  // KC contract: old vs new. Rules from the ICE rulebook (Ch. 8 Coffee "C", Ch. 14 Coffee "C" Metric) and notices;
  // today's certified stock revalued under each rule set by models/coffee_certs_profile.py (contract_compare).
  async function kcnew() {
    await loadCP();
    const D = CP, X = D.contract_compare, R = D.rules, Cu = D.current, Ph = D.physical;
    const c2 = v => sgn(v, 2, '¢'), RS = ['kc_pre', 'kc_now', 'kc_may27', 'ac'], SD = X.same_day, P = X.path;
    const RB = 'https://www.ice.com/publicdocs/rulebooks/futures_us/8_Coffee.pdf', RB14 = X.ac.source_url, F157 = X.ac.filing_url;
    const N24 = 'https://www.ice.com/publicdocs/futures_us/exchange_notices/ICE_Futures_US_ExNotCoffeeFuturesAmendmentsJan20240116.pdf';
    const NVN = 'https://www.ice.com/publicdocs/futures_us/exchange_notices/Exchange_Notice_Vietnam_Deliverable_Origin_Coffee_20250401.pdf';
    const SPEC = 'https://www.ice.com/products/15/Coffee-C-Futures/specifications', R23 = 'https://www.ice.com/publicdocs/regulatory_filings/23-132_Amendments_to_Coffee_Rules.pdf';
    const a = l => `<a href="${l}" target="_blank" rel="noopener">`;
    const prem = ['Kenya', 'Colombia', 'Guatemala', 'Costa Rica'].map(o => [o, SD.kc_now.by_origin[o]]).filter(x => x[1]);
    const premBags = prem.reduce((t, [, v]) => t + v.bags, 0);
    const pth = Object.fromEntries(P.map(p => [p.delivery, p])), last = P.at(-2), first = P.at(-1), now = P[0];
    const cv = X.switch_quote.curve || [], h28 = cv.find(c => c.contract === 'KCH2028'), k28 = cv.find(c => c.contract === 'ACK2028');
    const steps = cv.slice(1).map((c, i) => ({ from: cv[i].contract, to: c.contract, d: c.clb - cv[i].clb }));
    const sw = steps.find(s => s.to === 'ACK2028'), others = steps.filter(s => s.to !== 'ACK2028' && s.from !== 'KCZ2026');
    const avgStep = others.length ? others.reduce((t, s) => t + s.d, 0) / others.length : null;
    const colM = (Ph.groups || []).filter(g => g.group === 'Colombian Milds').map(g => g.vs_delivery), othM = (Ph.groups || []).filter(g => g.group === 'Other Milds').map(g => g.vs_delivery);
    const rng = v => v.length ? `${sgn(Math.min(...v), 0, '¢')} to ${sgn(Math.max(...v), 0, '¢')}` : '–';
    const tr = X.transition_bags, trSh = tr / Cu.total_bags * 100;
    const brief = `<div class="card" style="margin:0 0 12px;border-left:4px solid var(--acc)"><h3 style="margin-top:0">The "new contract" is Coffee "C" Metric (AC) from May 2028; KC's own terms change first, in steps</h3><ul style="margin:0;padding-left:18px">
      <li style="margin:4px 0"><b>What changes, when.</b> March 2028 is the last KC delivery. From May 2028 arabica is delivered on ${a(F157)}Coffee "C" Metric</a> (AC): 10 tonnes in US$/t, big bags (FIBCs) allowed, Barcelona dropped; differentials are KC's converted to $/t. Before that KC changes in steps: the 10¢ premiums for Colombia, Costa Rica and Kenya and 5¢ for Guatemala <b>already apply from the March 2026 contract</b> (not May 2027); Vietnam joins at −6¢ from May 2027; EUDR transition stock in European ports takes a growing discount from March 2027.</li>
      <li style="margin:4px 0"><b>Same coffee, same day, different rules.</b> Today's ${f0(Cu.total_bags)} certified bags invoice at ${c2(SD.kc_pre.all.total)}/lb under the pre-March 2026 rules, ${c2(SD.kc_now.all.total)} under today's, and ${c2(SD.ac.all.total)} under AC (vs ${X.futures} ${f2(X.settle)}). The rule switch itself moves the whole stock by only ${sgn(SD.kc_now.all.total - SD.kc_pre.all.total, 2, '¢')}: the premium origins are ${f0(premBags)} bags (${prem.map(([o, v]) => `${o} ${sgn(v.total - SD.kc_pre.by_origin[o].total, 0, '¢')}`).join(', ')}). AC versus KC is rounding (${sgn(SD.ac.all.total - SD.kc_may27.all.total, 2, '¢')}).</li>
      <li style="margin:4px 0"><b>What really cuts value is time plus EUDR.</b> If the same stock waits, it invoices at ${c2(pth['2027-03']?.all.total)} on Mar 27, ${c2(pth['2027-05']?.all.total)} on May 27, ${c2(last.all.total)} on Mar 28 (last KC) and ${c2(first.all.total)} on May 28 (first AC), of which EUDR ${c2(first.all.eudr)}. ${f0(tr)} bags (${f0(trSh)}%) are EUDR transition stock in European ports: their owners gain by delivering them before March 2027.</li>
      <li style="margin:4px 0"><b>Deliverable supply.</b> More valuable on the invoice, but Colombian Milds still trade ${rng(colM)} over the delivery month physically and Other Milds ${rng(othM)} (ICO, ${Ph.ico_month}), far above +10¢ / par: the premiums do not bring Colombia, Kenya or Costa Rica to the exchange, they mainly make the few lots already graded dearer to receive. Vietnam from May 2027 adds a second cheap washed origin next to Brazil, and from 30 Dec 2026 new European gradings need EUDR due-diligence data, which slows new certs in Antwerp and Hamburg/Bremen.</li>
      <li style="margin:4px 0"><b>Spreads across the switch.</b> ${h28 && k28 ? `ACK28 trades ${f0(k28.usd_t)} $/t = ${f2(k28.clb)}¢, ${sgn(sw?.d, 2, '¢')} against KCH28 (${f2(h28.clb)}¢), in line with the curve's ${sgn(avgStep, 2, '¢')} average per step (thin: ${f0(k28.volume_10d)} AC lots in two weeks).` : 'AC prices not yet in the desk data.'} Two things could change that: (1) ICE has not said whether KC certificates can be delivered on AC; if they cannot, May 2028 starts with no certified stock and the old KC pile must be delivered on March 2028 or sold, which would weaken H28 against K28; (2) the EUDR transition discount steps up between the two. Watch for an ICE notice.</li></ul>
      <p class="note" style="margin-bottom:0">Certs ${Cu.daily_date}; futures ${X.switch_quote.kc_date}; AC ${X.switch_quote.ac_date || '–'}; rules read ${R.read_on}. Values hold the futures price at ${X.futures} ${f2(X.settle)}.</p></div>`;
    const row = (k, cells) => `<tr><td class="l"><b>${k}</b></td>${cells.map(c => `<td class="l">${c}</td>`).join('')}</tr>`;
    const side = `<div class="card"><h2>Main terms side by side</h2><div class="tbl"><table style="min-width:860px"><tr><th class="l" style="width:14%">Term</th><th class="l">KC before Mar 2026</th><th class="l">KC now (Mar 2026 – Mar 2027)</th><th class="l">KC May 2027 – Mar 2028 (last KC)</th><th class="l">AC Coffee "C" Metric (from May 2028)</th></tr>
      ${row('Unit / size', ['37,500 lb (17.01 t) washed arabica', 'same', 'same', '<b>10 metric tons</b> (22,046 lb)'])}
      ${row('Price quotation', ['¢/lb; 0.05¢ tick = $18.75/lot', 'same', 'same', '<b>US$ per tonne</b>; $1/t tick = $10/lot (1¢/lb = $22.05/t)'])}
      ${row('Months', ['Mar, May, Jul, Sep, Dec', 'same', 'same; <b>no KC listed after Mar 2028</b>', 'Mar, May, Jul, Sep, Dec; first expiry <b>May 2028</b>; listed since Sep 2025'])}
      ${row('Origins and differentials', ['Colombia +4¢; 12 origins at par (incl. Guatemala, Costa Rica, Kenya); Venezuela, Burundi, Rwanda, India −1¢; Dominican Rep., Ecuador −4¢; Brazil −6¢', '<b>Colombia, Costa Rica, Kenya +10¢; Guatemala +5¢</b>; rest unchanged', 'as now, <b>plus Vietnam −6¢</b>', 'same origins; $/t: +220 (Col, CR, Kenya), +110 (Guat), −22, −88, −132 (Brazil, Vietnam) = the KC values converted'])}
      ${row('Delivery ports', ['NY, Virginia par; New Orleans, Miami, Houston −0.50¢; Antwerp, Hamburg/Bremen, Barcelona −1.25¢', 'same', 'same', 'NY, Virginia par; Gulf/Miami −$11/t (−0.50¢); Antwerp, Hamburg/Bremen −$28/t (−1.27¢); <b>Barcelona removed</b>'])}
      ${row('Packaging', ['natural-fibre bags', 'same', 'same', 'bags <b>or FIBC big bags</b> up to 1 t (a lot is all one or the other); weight tolerance 2% bags, 3% FIBC'])}
      ${row('Grading / cup', ['8 full imperfections basis (Colombia 13), 0.10¢ per imperfection below basis, max 15 below (Colombia 10); ≥50% screen 15; clean cup, no aged taste', 'same', 'same (Vietnam on the 8-imperfection basis)', 'same standard; $2/t per imperfection'])}
      ${row('Age discount', ['none to 120 days; 0.50¢ at 121–150; then steps up to 18.25¢ at 3,600 days + 3¢ per 30 days', 'same', 'same', 'same schedule in $/t ($11 at 121 days … $4,150 at 3,600 + $66 per 30 days)'])}
      ${row('Weight allowance', ['0.5% for the 2nd month after weighing + 0.125% per month after', 'same', 'same', 'same'])}
      ${row('Rent / load-out', ['OCA (load-out vs NY average) and RCA (rent vs NY average × 2 or × 3)', 'same', 'same', 'same, worked out separately for bags and FIBCs'])}
      ${row('Customs', ['EU ports: non-cleared only (Apr 2024); US ports duty paid (Apr 2025)', 'same', 'same', 'same'])}
      ${row('EUDR', ['–', 'from 30 Dec 2026 new EU-port gradings need validated EUDR data; transition stock (B/L from 29 Jun 2023, no EUDR data) discounted <b>0.25¢ per month of 2027 from Mar 2027</b>', '2027 months 0.25¢/month; 2028 months 3¢ + 0.50¢/month (Mar 2028: 4.50¢)', 'transition stock: $121/t (5.49¢) on May 2028, + $11/t per month; Antwerp and Hamburg/Bremen'])}
      ${row('Re-grading', ['barred since 1 Dec 2023 (appeals only)', 'same', 'same', 'same (Rule 14.10a). <b>Not stated</b> whether KC certificates are deliverable on AC'])}
      ${row('Spot-month limit', ['500 lots (≈8,500 t)', 'same', 'same', '850 lots (8,500 t)'])}</table></div>
      <p class="note">Sources: ${a(RB)}ICE rulebook Ch. 8 Coffee "C"</a> (Appendix IV Schedules C-2/C-3, Appendix V, VII, VIII), ${a(RB14)}Ch. 14 Coffee "C" Metric</a>, ${a(F157)}ICE Submission 25-157</a>, ${a(N24)}ICE notice 16 Jan 2024</a>, ${a(NVN)}ICE notice 1 Apr 2025 (Vietnam)</a>, ${a(R23)}ICE Submission 23-132 (re-grading)</a>, ${a(SPEC)}ICE product specification</a>.</p>
      <p class="note"><b>March 2026 or May 2027?</b> ICE's 16 Jan 2024 notice set the premiums from the March 2026 expiry. The rulebook prints three Schedule C-2 tables, each "Effective with …" line sitting between two of them; its amendment notes tie the March 2026 schedule to the Board change of 20 Dec 2023 (the premiums) and the May 2027 schedule to 27 Mar 2025 (Vietnam, ICE notice 1 Apr 2025, which changes nothing else). ICE's product page lists the premiums as current and only Vietnam "commencing with the May 2027 expiry". So the premiums apply now, from March 2026; this page and the certs profile use that.</p></div>`;
    const dt = X.diff_table.slice().sort((p, q) => (q.kc_may27 ?? -99) - (p.kc_may27 ?? -99) || p.origin.localeCompare(q.origin));
    const nd = v => v == null ? '<span class="note">not deliverable</span>' : sgn(v, 2);
    const diffT = `<div class="card"><h2>Origin differentials by rule set <span class="note">¢/lb vs futures; AC in $/t</span></h2><div class="tbl"><table><tr><th class="l">Origin</th><th>Before Mar 26</th><th>Now</th><th>May 27 – Mar 28</th><th>AC $/t</th><th>AC in ¢/lb</th><th>Bags certified now</th></tr>
      ${dt.map(r => `<tr><td class="l">${r.origin}</td><td class="n">${nd(r.kc_pre)}</td><td class="n">${nd(r.kc_now)}</td><td class="n">${nd(r.kc_may27)}</td><td class="n">${r.ac_usd_t == null ? '–' : sgn(r.ac_usd_t, 0)}</td><td class="n">${nd(r.ac_clb)}</td><td class="n">${r.in_stock_bags ? f0(r.in_stock_bags) : '–'}</td></tr>`).join('')}</table></div></div>`;
    const spec = `<div class="card" style="border-left:4px solid #17a589"><h2>Full spec of the new contract — main points</h2><ul style="margin:0;padding-left:18px">
      <li><b>Name / symbol:</b> Coffee "C" Metric futures (AC), ICE Futures U.S.; options on it (monthly, weekly, calendar-spread).</li>
      <li><b>Size and price:</b> 10 t washed arabica; US$/t, minimum move $1/t ($10 a lot); option strikes every $25/t.</li>
      <li><b>Months:</b> Mar, May, Jul, Sep, Dec; first expiry May 2028 (KC's last is Mar 2028, so expiries never overlap). Last notice day 7 business days before the month's last business day; last trading day the business day before; notices from 7 business days before the first business day of the month; delivery 7 business days after notice.</li>
      <li><b>Origins:</b> the 21 KC growths incl. Vietnam. Par: Mexico, El Salvador, Nicaragua, PNG, Tanzania, Uganda, Panama, Peru, Honduras. +$220/t Colombia, Costa Rica, Kenya; +$110 Guatemala; −$22 Venezuela, Burundi, Rwanda, India; −$88 Dominican Rep., Ecuador; −$132 Brazil, Vietnam.</li>
      <li><b>Ports:</b> New York, Virginia par; New Orleans, Miami, Houston −$11/t; Antwerp, Hamburg/Bremen −$28/t. No Barcelona (no certified coffee there since Nov 2021).</li>
      <li><b>Packaging:</b> natural-fibre bags (KC-standard bags stay deliverable) or new polypropylene FIBCs up to 1 t, filled in the licensed warehouse from the original lined container; a lot is all bags or all FIBCs; one FIBC counts as 15 bags for load-out.</li>
      <li><b>Grade and age:</b> KC grading (8 imperfections basis, Colombia 13; $2/t per imperfection below basis; clean cup); age discount $11/t from 121 days rising to $4,150/t at 3,600 days + $66 per 30 days; weight allowance 0.5% + 0.125%/month; OCA and RCA as KC.</li>
      <li><b>EUDR:</b> EU ports need validated EUDR due-diligence data for gradings from 30 Dec 2026; transition stock $121/t from May 2028 + $11/t a month; legacy stock (B/L before 29 Jun 2023) exempt.</li>
      <li><b>Limits:</b> spot month 850 lots; positions aggregated with KC for accountability.</li>
      <li><b>Open point:</b> ${X.ac.certificates_note}</li></ul>
      <p class="note">${a(RB14)}ICE rulebook Chapter 14</a>; ${a(F157)}Submission 25-157 (21 Aug 2025)</a>; read ${X.ac.read_on}.</p></div>`;
    const ruleRows = R.changes.slice().reverse().map(r => `<tr><td class="l" style="white-space:nowrap">${r.effective_date}</td><td class="l">${r.first_contract}</td><td class="l">${r.rule_area}</td><td class="l">${r.plain_english}</td><td class="l"><a href="${r.source_url}" target="_blank" rel="noopener">source</a></td></tr>`).join('');
    const orgs = Object.keys(SD.kc_now.by_origin).sort((p, q) => SD.kc_now.by_origin[q].bags - SD.kc_now.by_origin[p].bags);
    const sdT = `<div class="tbl"><table><tr><th class="l">Origin</th><th>Bags</th>${RS.map(k => `<th>${X.rulesets[k]}</th>`).join('')}<th>Now vs before</th></tr>
      ${orgs.map(o => `<tr><td class="l">${o}</td><td class="n">${f0(SD.kc_now.by_origin[o].bags)}</td>${RS.map(k => `<td class="n">${f2(SD[k].by_origin[o]?.total)}</td>`).join('')}<td class="n">${sgn(SD.kc_now.by_origin[o].total - SD.kc_pre.by_origin[o].total, 2, '¢')}</td></tr>`).join('')}
      <tr><td class="l"><b>All certs</b></td><td class="n"><b>${f0(SD.kc_now.all.bags)}</b></td>${RS.map(k => `<td class="n"><b>${f2(SD[k].all.total)}</b></td>`).join('')}<td class="n"><b>${sgn(SD.kc_now.all.total - SD.kc_pre.all.total, 2, '¢')}</b></td></tr></table></div>`;
    const pT = `<div class="tbl"><table><tr><th class="l">Delivered on</th><th>Days older</th><th>All certs</th><th>EU ports</th><th>US ports</th><th>of which EUDR</th><th>of which age</th><th>Origin</th></tr>
      ${P.map(p => `<tr><td class="l">${p.label}</td><td class="n">${f0(p.add_days)}</td><td class="n"><b>${c2(p.all.total)}</b></td><td class="n">${c2(p.eu.total)}</td><td class="n">${c2(p.non_eu.total)}</td><td class="n">${f2(p.all.eudr)}</td><td class="n">${f2(p.all.age)}</td><td class="n">${f2(p.all.odiff)}</td></tr>`).join('')}</table></div>`;
    body().innerHTML = `${brief}${side}
      <div class="grid g2" style="margin-top:12px">${spec}${diffT}</div>
      <div class="card" style="margin-top:12px"><h2>What it means in ¢/lb: today's certified stock revalued</h2>
        <h3>Same day, same ages, each rule set <span class="note">bag-weighted invoice vs futures, ¢/lb; delivery ${X.delivery}</span></h3>${sdT}
        <p class="note">Each certified lot (origin, port, estimated age from the certs profile) is invoiced under each rule set with its ages and the futures price held at ${X.delivery}. Origin, port and age change by rule set; weight allowance and load-out/rent are the same in all. EUDR is left out here (it depends on the month; see below). AC $/t values are shown in ¢/lb (÷ 22.046).</p>
        <div class="grid g2" style="margin-top:8px"><div><h3>The same stock if it waits to each switch month</h3>${pT}
          <p class="note">Rules in force for each month; ages roll forward; EUDR transition discount applied to the transition share by origin and port. Mar 2028 is the last KC delivery; May 2028 the first AC.</p></div>
          <div><h3>KC and AC curve, ${X.switch_quote.kc_date}</h3>${box('kcnC', 260)}<p class="note">Settlements: KC in ¢/lb; AC in $/t shown in ¢/lb. AC trades thinly (${k28 ? f0(k28.volume_10d) : '–'} lots in two weeks).</p></div></div></div>
      <div class="card" style="margin-top:12px"><h2>Dated rule changes, KC to AC</h2><div class="tbl"><table><tr><th class="l">Effective</th><th class="l">First contract</th><th class="l">Rule</th><th class="l">What it means</th><th class="l">Source</th></tr>${ruleRows}</table></div></div>
      <p class="note">Variables used: ICE Coffee "C" and Coffee "C" Metric rulebook values (origin, port, age, weight, OCA/RCA, EUDR); certified stock by origin, port and estimated age (certs profile); EUDR transition bags (ICE daily report); KC and AC settlements; ICO group prices. Built ${D.built}.</p>`;
    chart('kcnC', { type: 'line', data: { labels: cv.map(c => c.contract.replace(/(\D+)(\D)(\d{2})(\d{2})/, '$1 $2$4')), datasets: [{ label: 'KC ¢/lb', data: cv.map(c => c.kind === 'KC' ? c.clb : null), borderColor: '#7d3c98', pointRadius: 3 },
      { label: 'AC (in ¢/lb)', data: cv.map(c => c.kind === 'AC' ? c.clb : null), borderColor: '#17a589', backgroundColor: '#17a589', pointRadius: 5, showLine: false }] },
      options: { scales: { y: { title: { display: true, text: '¢/lb' } } } } });
  }
  const REGC = { pre19: 'rgba(127,140,141,.45)', r19_23: 'rgba(44,111,187,.55)', post23: 'rgba(125,60,152,.7)' };
  function smBlock(M) {
    const N = M.now, f1s = v => v == null ? '–' : (v > 0 ? '+' : '') + f1(v);
    const kname = k => k === 1 ? 'day before notice' : `${k} days before notice`;
    const rows = M.upcoming.map(u => { const F = u.fair[String(u.compare_at)], Fp = (u.fair_pile || {})[String(u.compare_at)];
      return `<tr><td class="l">${u.pair}</td><td class="n">${u.first_notice}</td><td class="n">${u.bd_to_fnd}</td><td class="n">${sgn(u.spread_c, 2, '¢')}</td><td class="n">${sgn(u.spread_pct, 2, '%')}</td>
        <td class="n">${kname(u.compare_at)}</td><td class="n">${f1s(F.c.lo)} to ${f1s(F.c.hi)}¢</td><td class="n">${f1s(F.pct.lo)} to ${f1s(F.pct.hi)}%</td><td class="n">${Fp ? `${f1s(Fp.c.lo)} to ${f1s(Fp.c.hi)}¢` : '–'}</td>
        <td class="l"><b>${u.read === 'cheap' ? 'below fair' : u.read === 'rich' ? 'above fair' : 'in range'}</b></td></tr>`; }).join('');
    const sim = M.similar.map(r => `<tr><td class="l">${r.contract}</td><td class="n">${f1(r.cover)}%</td><td class="n">${f0(r.over1y)}%</td><td class="n">${sgn(r.c10, 2, '¢')} (${sgn(r.p10, 1, '%')})</td><td class="n">${sgn(r.c1, 2, '¢')} (${sgn(r.p1, 1, '%')})</td></tr>`).join('');
    return `<div class="card" style="margin-top:12px;border-left:4px solid var(--acc)"><h2>Spread model: fair front spread from certified stocks</h2>
        <ul style="margin:0 0 8px;padding-left:18px">${M.brief.map(t => `<li style="margin:4px 0">${t}</li>`).join('')}</ul>
        <div class="grid g4" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
          ${kpi('Certs cover', f2(N.cover) + '% of OI', `${f0(N.lots)} certified lots vs ${f0(N.oi)} lots open (CFTC); ${ordn(N.cover_pct_all)} pct of past deliveries since 2006 (median ${f1(N.cover_median_all)}%)${N.cover_front ? `; ${f1(N.cover_front)}% of ${N.front_contract} open interest (${N.front_oi_date})` : ''}`)}
          ${kpi('Certs to come', N.exp_pend ? f0(N.exp_pend / 1000) + 'k bags' : '–', `${f0(N.certs)} certified + ${f0(N.pending)} pending (${N.pending_date}) at a ${f0(N.pass_rate)}% pass rate (last 3 months of ICE gradings)`)}
          ${M.spot ? kpi('Certs ÷ 500-lot spot limit', f1(M.spot.now) + '×', `${f0(N.lots)} certified lots against the most one account can hold into the spot month${M.spot.with_pending ? `; ${f1(M.spot.with_pending)}× with pending bags` : ''}`) : ''}
          ${kpi('Physical washed premium', sgn(N.ico_oth, 0, '¢'), `ICO other milds ex-dock minus the ICE 2nd/3rd average, ${N.ico_month}; median since 2000 ${f0(N.ico_oth_median)}¢`)}</div>
        <div class="tbl" style="margin-top:10px"><table><tr><th class="l">Spread</th><th>First notice</th><th>Business days left</th><th>Market</th><th>% of price</th><th>Fair at</th><th>Fair range</th><th>Fair, % of price</th><th>On today's pile alone</th><th class="l">Reading</th></tr>${rows}</table></div>
        <p class="note">Fair range = the model's central 60% band (20th–80th percentile of its past errors) at the next fixed point before first notice, counting today's certified stocks, the bags pending grading at the recent pass rate, the age of the pile and the physical washed premium over the exchange. For contracts more than 30 business days out it is the fair value 30 days before notice if certs stayed where they are; it will move as certs change. Not a forecast of the path.</p>
        <div class="grid g2" style="margin-top:10px">
          <div class="card"><h3>Front spread against certs cover, by delivery</h3>${box('kcSc2', 280)}<p class="note">Each point is a past delivery: certified lots as % of all KC futures open interest (x, log scale) against the front spread at ${M.scatter.k_name} (y, % of the front price). The line is the model's fair spread at today's open interest, age and rules. Red: ${M.scatter.today.label}; hollow red: the same spread with the pending bags added at the recent pass rate.</p></div>
          <div class="card"><h3>Past deliveries with a similar pile</h3><div class="tbl"><table><tr><th class="l">Contract</th><th>Cover</th><th>Over 1 year</th><th>Spread 10 days before notice</th><th>Day before notice</th></tr>${sim}</table></div>
            <p class="note">Nearest past deliveries since 2016 on cover, age and the 3-month change in certs.</p></div></div>
        <p class="note"><b>Rule periods.</b> The spread history table above keeps its four periods (2012–18 re-grading allowed; 2019–20 first Brazil gradings; 2021–Nov 2023 Brazil in the pile, re-grading still allowed; Dec 2023 on re-grading barred) and the scatter above keeps its two (2020–Nov 2023 and Dec 2023 on). The model uses three, chosen on the per-delivery data back to 1997: before May 2019; May 2019 – Nov 2023 (new port and rent rules, then Brazil entering the pile); December 2023 on (re-grading barred). The colours in the delivery scatter follow the model's three periods.</p>

        <p class="note">Variables used: ${M.variables.join('; ')}. Built ${M.built}.</p></div>`;
  }
  function smCharts(M) {
    const S = M.scatter, R = S.regimes, ds = Object.keys(R).map(k => ({ label: R[k], data: S.points.filter(p => p.reg === k).map(p => ({ x: p.x, y: p.y, c: p.c })), backgroundColor: REGC[k] }));
    chart('kcSc2', { type: 'scatter', data: { datasets: [...ds,
      { type: 'line', label: S.line_label, data: S.line.map(p => ({ x: p.x, y: p.y })), borderColor: '#7d3c98', borderWidth: 1.5, pointRadius: 0 },
      { type: 'line', label: 'Fair band', data: S.line.map(p => ({ x: p.x, y: p.hi })), borderColor: 'rgba(125,60,152,.3)', borderDash: [3, 3], borderWidth: 1, pointRadius: 0 },
      { type: 'line', label: ' ', data: S.line.map(p => ({ x: p.x, y: p.lo })), borderColor: 'rgba(125,60,152,.3)', borderDash: [3, 3], borderWidth: 1, pointRadius: 0 },
      { label: S.today.label, data: [{ x: S.today.x, y: S.today.y, c: S.today.label }], backgroundColor: '#c0392b', pointRadius: 6 },
      ...(S.today_exp && S.today_exp.x ? [{ label: 'with pending at pass rate', data: [{ x: S.today_exp.x, y: S.today_exp.y, c: 'with pending bags' }], backgroundColor: 'rgba(0,0,0,0)', borderColor: '#c0392b', borderWidth: 2, pointRadius: 6 }] : [])] },
      options: { interaction: { mode: 'nearest', intersect: true }, plugins: { legend: { labels: { filter: i => i.text.trim() !== '' && i.text !== 'Fair band' } }, tooltip: { callbacks: { label: c => `${c.raw.c || ''}: cover ${f2(c.raw.x)}%, spread ${f2(c.raw.y)}%` } } },
        scales: { x: { type: 'logarithmic', title: { display: true, text: 'certified lots, % of KC futures open interest (log)' } }, y: { title: { display: true, text: 'front spread, % of price' } } } } });
  }
  async function certs() {
    await load();
    const SM = await getJSON('data/coffee/spread_model.json').catch(() => null);
    const St = K.structure, C = K.certs_ice, sn = St.now;
    if (!C) { body().innerHTML = '<div class="card"><p>ICE certified-stock history is loading; it fills on the next coffee data run.</p></div>'; return; }
    const c = C.now, kb = v => v == null ? '–' : f0(v / 1000) + 'k', sk = v => v == null ? '–' : (v >= 0 ? '+' : '−') + f0(Math.abs(v) / 1000) + 'k';
    const po = Object.entries(C.pending_by_origin), pp = Object.entries(C.pending_by_port), gr = c.passed_30d + c.failed_30d;
    const tbl = (o, h) => `<table><tr><th class="l">${h}</th><th>Bags</th><th>Share</th></tr>${Object.entries(o).map(([k, v]) => `<tr><td class="l">${k}</td><td class="n">${f0(v)}</td><td class="n">${f1(v / c.total * 100)}%</td></tr>`).join('')}</table>`;
    body().innerHTML = `<div class="grid g4">
        ${kpi('ICE certified arabica', f0(c.total) + ' bags', `${c.date}; ${sk(c.chg_1w)} on the week, ${sk(c.chg_1m)} on the month, ${sk(c.chg_1y)} on the year`)}
        ${kpi('Pending grading', f0(c.pending) + ' bags', po.length ? po.map(([k, v]) => `${k} ${kb(v)}`).join(', ') + (pp.length ? ' · at ' + pp.map(([k, v]) => `${k} ${kb(v)}`).join(', ') : '') : 'none waiting')}
        ${kpi('Grading, last 30 days', gr ? f0(c.passed_30d / gr * 100) + '% passed' : '–', `${f0(c.passed_30d)} bags passed, ${f0(c.failed_30d)} failed`)}
        ${kpi('KC front spread', sgn(sn.spread, 1, '¢'), `front minus second, ${sn.date}; ${ord(sn.pct_regime ?? sn.pct5y)} since Dec 2023; full carry ${f2(sn.carry)}¢`)}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Certified stocks and bags pending grading</h2>${rngBar('kcSt', ['1M', '3M', '6M', '1Y', 'All'], '3M')}${box('kcSt', 260)}<p class="note">ICE daily certified-stock report, bags of arabica in licensed warehouses that passed grading, and bags waiting to be graded. Of the certified total, ${f0(c.transition)} bags are EUDR transition stock (European ports, shipped from 29 June 2023 without EUDR due-diligence data; they take a discount from the March 2027 contract). Pending bags that pass will add to the total; they are the earliest public sign of new deliverable supply.</p></div>
        <div class="card"><h2>Front spread against certified stocks</h2>${box('kcSc', 280)}<p class="note">Each point is a month since 2020: certified stocks (x) against the KC front-month spread (y, ¢/lb, positive = inverted). The lines give the fair spread for each certs level, with a separate level since ICE barred re-grading of de-certified coffee in December 2023.${St.fair ? ` At ${f2(St.fair.certs)}m bags the fair spread is ${sgn(St.fair.fair, 1, '¢')}; today's ${sgn(sn.spread, 1, '¢')} is ${sgn(St.fair.resid, 1, '¢')} ${St.fair.resid >= 0 ? 'rich' : 'cheap'} to it (${ord(St.fair.resid_pct)} of gaps since Dec 2023). Certs explain about ${f0(St.fair.r2 * 100)}% of the monthly spread; the gap is a valuation, not a timing signal.` : ''} Certs before Sep 2026 are ICO monthly figures; from Sep 2026 ICE daily reports. Variables: ${(St.fair?.variables || []).join('; ')}.</p></div></div>
      <div class="card" style="margin-top:12px"><h2>Certification trigger: Brazil naturals against KC</h2>${rngBar('kcTp', ['2Y', '5Y', 'All'], '5Y')}${box('kcTp', 230)}<p class="note">ICO Brazilian naturals price minus the KC front month (monthly, ¢/lb, left) and certified stocks (million bags, right). Semi-washed Brazil to Antwerp is the cheapest coffee to certify, and it has come onto the exchange in size when Brazilian naturals traded about 5¢ or more under the futures: below that line certs have usually built over the following months, above it they have usually drawn. Latest (${K.ico.groups.month.at(-1)}): ${sgn(K.ico.groups.bra_d.at(-1), 1, '¢')}${K.ico.groups.bra_d.at(-1) <= -5 ? ', in the zone where new Brazil coffee tends to be certified' : ', above the level where new Brazil coffee is usually certified'}.</p></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Certified stocks by origin</h2><div class="tbl">${tbl(C.by_origin, 'Origin')}</div></div>
        <div class="card"><h2>Certified stocks by warehouse port</h2><div class="tbl">${tbl(C.by_port, 'Port')}</div><p class="note">ANT Antwerp, HA/BR Hamburg-Bremen, BAR Barcelona, HOU Houston, NOLA New Orleans, NY New York, VA Virginia. European ports deliver at a 1.25¢ discount; Gulf ports and Miami at 0.50¢ (see the primer).</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>KC front spread history</h2>${rngBar('kcSp', ['3M', '6M', '1Y', '2Y', '5Y', 'All'], '2Y')}${box('kcSp', 240)}
          <div class="tbl"><table><tr><th class="l">Period</th><th>Weeks inverted</th><th>Median ¢/lb</th><th>10th–90th pct</th></tr>${(St.regimes || []).map(g => `<tr><td class="l">${g.label}</td><td class="n">${f0(g.inverted_pct)}%</td><td class="n">${sgn(g.median, 2)}</td><td class="n">${f2(g.p10)} to ${f2(g.p90)}</td></tr>`).join('')}</table></div>
          <p class="note">The rules changed, so older history is a different market. Before 2019 the curve sat in carry: de-certified old coffee could be graded again and come back as fresh, wiping out the age discount, so a receiver risked getting stale coffee and nobody paid up for nearby delivery; position limits in the spot month (500 lots without an exemption) also capped how hard anyone could squeeze. Brazil semi-washed has been deliverable since the March 2013 contract, but it only entered the certified pile in size from late 2020. Since 1 December 2023 ICE bars re-grading coffee that was certified and then de-certified. Percentiles on this tab are measured from December 2023.</p></div>
        <div class="card"><h2>KC curve</h2><div class="tbl"><table><tr><th class="l">Contract</th><th>Price</th><th>1 week ago</th><th>Change</th><th>Volume</th></tr>
          ${K.curves.KC.map(r => `<tr><td class="l">${r.label}</td><td class="n">${f2(r.px)}</td><td class="n">${f2(r.px_1w)}</td><td class="n">${sgn(r.px - r.px_1w, 2)}</td><td class="n">${f0(r.vol)}</td></tr>`).join('')}</table></div></div></div>
      ${SM ? smBlock(SM) : ''}${asof()}`;
    const drawSt = r => { const a = rngFrom(C.dates, r), pr = r === '1M' || r === '3M' ? 2 : 0;
      chart('kcSt', { type: 'line', data: { labels: C.dates.slice(a), datasets: [{ label: 'Certified, bags', data: C.total.slice(a), borderColor: '#7d3c98', pointRadius: pr, yAxisID: 'y' }, { label: 'Pending grading', data: C.pending.slice(a), borderColor: '#d68910', pointRadius: pr, yAxisID: 'y1' }] },
        options: { scales: { y: { beginAtZero: false, title: { display: true, text: 'certified' } }, y1: { position: 'right', beginAtZero: true, grid: { display: false }, title: { display: true, text: 'pending' } } } } }); };
    drawSt('3M'); rngWire('kcSt', drawSt);
    const V = St.vs_certs || [], Fv = St.fair, pre = V.filter(p => !p.post), post = V.filter(p => p.post).slice(0, -1);
    if (V.length) chart('kcSc', { type: 'scatter', data: { datasets: [
      { label: '2020 – Nov 2023', data: pre.map(p => ({ x: p.x, y: p.y, m: p.m })), backgroundColor: 'rgba(127,140,141,.45)' },
      { label: 'Since Dec 2023', data: post.map(p => ({ x: p.x, y: p.y, m: p.m })), backgroundColor: 'rgba(125,60,152,.55)' },
      { label: 'Latest ' + V.at(-1).m, data: [{ x: V.at(-1).x, y: V.at(-1).y, m: V.at(-1).m }], backgroundColor: '#c0392b', pointRadius: 6 },
      ...(Fv ? [{ type: 'line', label: 'Fair spread, current rules', data: Fv.curve_post, borderColor: '#7d3c98', borderWidth: 1.5, pointRadius: 0 },
               { type: 'line', label: 'Fair spread, earlier rules', data: Fv.curve_pre, borderColor: '#95a5a6', borderDash: [4, 3], borderWidth: 1.2, pointRadius: 0 }] : [])] },
      options: { interaction: { mode: 'nearest', intersect: true }, plugins: { tooltip: { callbacks: { label: c => `${c.raw.m || ''} certs ${f2(c.raw.x)}m, spread ${f2(c.raw.y)}¢` } } },
        scales: { x: { type: 'logarithmic', title: { display: true, text: 'certified stocks, m bags (log scale)' } }, y: { title: { display: true, text: 'front spread ¢/lb' } } } } });
    if (SM) smCharts(SM);
    const drawSp = r => { const i0 = rngFrom(St.dates, r);
      chart('kcSp', { type: 'line', data: { labels: St.dates.slice(i0), datasets: [{ label: 'Front − second, ¢/lb', data: St.spread.slice(i0), borderColor: '#2c6fbb', pointRadius: 0 }, { label: 'Full carry (negative)', data: St.carry.slice(i0).map(x => -x), borderColor: '#7f8c8d', borderDash: [4, 3], pointRadius: 0 }] } }); };
    drawSp('2Y'); rngWire('kcSp', drawSp);
    const G = K.ico.groups, cm = Object.fromEntries((St.vs_certs || []).map(p => [p.m, p.x]));
    const drawTp = r => { const lab = G.month, a = r === 'All' ? Math.max(0, lab.indexOf('2015-01')) : rngFrom(lab.map(m => m + '-01'), r);
      chart('kcTp', { type: 'line', data: { labels: lab.slice(a), datasets: [{ label: 'Brazil naturals − KC, ¢/lb', data: G.bra_d.slice(a), borderColor: '#2f6b3a', pointRadius: 0, yAxisID: 'y' },
        { label: 'Certification line (−5¢)', data: lab.slice(a).map(() => -5), borderColor: '#c0392b', borderDash: [4, 3], pointRadius: 0, yAxisID: 'y' },
        { label: 'Certified stocks, m bags', data: lab.slice(a).map(m => cm[m] ?? null), borderColor: '#7d3c98', pointRadius: 0, spanGaps: true, yAxisID: 'y1' }] },
        options: { scales: { y1: { position: 'right', grid: { display: false } } } } }); };
    drawTp('5Y'); rngWire('kcTp', drawTp);
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

  // Coffee > Centrals & Col (data/coffee/colombia/colombia.json, pipelines/colombia_fnc.py; FNC public files)
  async function centrals() {
    const C = await getJSON('data/coffee/colombia/colombia.json'), P = C.production, E = C.exports, I = C.internal;
    const CYM = ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep'];
    const lab = m => new Date(m + '-15').toLocaleString('en', { month: 'short', year: 'numeric' });
    const cmp = X => `${f2(X.value / 1000)}m bags · ${sgn(X.vs_prev_pct, 0, '%')} y/y · ${sgn(X.vs_avg5_pct, 0, '%')} vs 5-yr avg`;
    const D = C.destinations, src = C.sources || {}, MR = C.monthly_report || {};
    body().innerHTML = `<div class="card"><h2>Colombia: what the FNC numbers say</h2><ul>${C.brief.map(b => `<li>${b}</li>`).join('')}</ul>
        <p class="note">Colombia is deliverable on KC at a premium; how Colombian lots rank against other origins is on <a href="#kc-cprof" onclick="document.querySelector('#kcTabs button[data-t=kc-cprof]').click();return false">Certs profile &amp; delivery economics</a>. Harvest months: main crop Oct–Jan, mitaca Apr–Jun/Jul (see <a href="#kc-geo" onclick="document.querySelector('#kcTabs button[data-t=kc-geo]').click();return false">Where it's grown</a>).</p></div>
      <div class="grid g4" style="margin-top:12px">
        ${kpi('Production ' + lab(P.latest.month), f2(P.latest.value / 1000) + 'm bags', `${sgn(P.latest.vs_prev_pct, 0, '%')} y/y; 12 months ${f2(P.roll12_now)}m`)}
        ${kpi('Exports ' + lab(E.latest.month), f2(E.latest.value / 1000) + 'm bags', `${sgn(E.latest.vs_prev_pct, 0, '%')} y/y; 12 months ${f2(E.roll12_now)}m`)}
        ${I ? kpi('Internal price, ¢/lb green', f1(I.now.c_lb) + '¢', `${f0(I.now.cop / 1000)}k COP/carga at ${f0(I.now.fx)} COP/US$ (${I.now.date})`) : ''}
        ${I ? kpi('Internal minus KC front', sgn(I.now.diff, 1, '¢'), `KC ${f1(I.now.kc)}¢${MR.differential_c_lb != null ? `; FNC differential ${f1(MR.differential_c_lb)}¢ (${lab(MR.month)})` : ''}`) : ''}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Production by month, coffee year Oct–Sep</h2>${box('coP', 260)}<p class="note">FNC registered production, thousand 60-kg bags. ${cmp(P.latest)}.</p></div>
        <div class="card"><h2>Exports by month, coffee year Oct–Sep</h2>${box('coE', 260)}<p class="note">All types, thousand 60-kg bags. ${cmp(E.latest)}.</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>12-month totals</h2>${box('coR', 260)}<p class="note">Rolling 12-month production and exports, million bags.</p></div>
        <div class="card"><h2>Internal price against KC front</h2>${box('coI', 260)}<p class="note">FNC internal reference price (COP per 125-kg carga of dry parchment) converted to ¢/lb of green (93.1 kg excelso per carga at yield factor 94) at the daily USD/COP rate (${I ? I.now.fx_source || '' : ''}); right axis: internal price minus KC front. The internal price is a farm-gate buying price, so it sits below the export differential.</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Exports by destination <span class="note">${D.period}</span></h2><div class="tbl"><table><tr><th class="l">Destination</th><th>k bags</th><th>Share</th><th>vs prior 12 m</th></tr>
          ${D.top.map(r => `<tr><td class="l">${r.country}</td><td class="n">${f0(r.k_bags)}</td><td class="n">${f1(r.share)}%</td><td class="n">${sgn(r.chg_pct, 0, '%')}</td></tr>`).join('')}
          <tr><td class="l">Others</td><td class="n">${f0(D.rest)}</td><td class="n">${f1(D.rest / D.total * 100)}%</td><td></td></tr><tr><td class="l"><b>Total</b></td><td class="n"><b>${f0(D.total)}</b></td><td></td><td></td></tr></table></div></div>
        <div class="card"><h2>Exports by type, last 12 months</h2><div class="tbl"><table><tr><th class="l">Type</th><th>k bags</th><th>vs prior 12 m</th></tr>
          ${Object.entries(E.by_type).map(([k, v]) => `<tr><td class="l">${k}</td><td class="n">${f0(v.last12)}</td><td class="n">${sgn(v.chg_pct, 0, '%')}</td></tr>`).join('')}</table></div>
          <p class="note">Honduras (ADECAFEH) is not shown: see the Data status tab.</p></div></div>
      <p class="note">Source: Federación Nacional de Cafeteros (FNC), <a href="https://federaciondecafeteros.org/estadisticas-cafeteras/" target="_blank" rel="noopener">estadísticas cafeteras</a>: ${Object.entries(src).map(([k, v]) => `${k.replace('_', ' ')} (${v.latest_data || 'read'}, read ${(v.read || '').slice(0, 10)})`).join('; ')}. Production history from ${P.history_from}, exports from ${E.history_from}. USD/COP: TRM (datos.gov.co), fallbacks Yahoo / TradingView. Built ${C.built}.</p>`;
    const seas = (id, S) => { const ks = Object.keys(S).filter(k => !k.startsWith('avg5')).slice(-3);
      chart(id, { type: 'bar', data: { labels: CYM, datasets: [...ks.map((k, q) => ({ type: q === ks.length - 1 ? 'bar' : 'line', label: k, data: S[k], backgroundColor: PAL[0], borderColor: PAL[q === ks.length - 1 ? 0 : q + 1], borderWidth: 1.5, pointRadius: 0 })),
        { type: 'line', label: '5-yr avg ' + S.avg5_years, data: S.avg5, borderColor: '#7f8c8d', borderDash: [4, 3], pointRadius: 0, borderWidth: 1.2 }] } }); };
    seas('coP', P.seasonal); seas('coE', E.seasonal);
    const r0 = P.roll12.month.findIndex(m => m >= '2012-01'), e0 = E.roll12.month.indexOf(P.roll12.month[r0]);
    chart('coR', { type: 'line', data: { labels: P.roll12.month.slice(r0), datasets: [{ label: 'Production', data: P.roll12.v.slice(r0), borderColor: PAL[0], pointRadius: 0 },
      { label: 'Exports', data: P.roll12.month.slice(r0).map(m => { const i = E.roll12.month.indexOf(m); return i < 0 ? null : E.roll12.v[i]; }), borderColor: PAL[2], pointRadius: 0 }] } });
    if (I) { const i0 = since(I.dates, 5);
      chart('coI', { type: 'line', data: { labels: I.dates.slice(i0), datasets: [{ label: 'Internal, ¢/lb', data: I.c_lb.slice(i0), borderColor: PAL[0], pointRadius: 0 }, { label: 'KC front', data: I.kc.slice(i0), borderColor: PAL[4], pointRadius: 0 },
        { label: 'Internal − KC', data: I.diff.slice(i0), borderColor: '#7f8c8d', borderDash: [4, 3], pointRadius: 0, yAxisID: 'y1' }] }, options: { scales: { y1: { position: 'right', grid: { display: false } } } } }); }
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
      ['Curve and certs', tilt(St.spread, 3), `Front spread ${sgn(St.spread, 1, '¢')} (${ord(St.pct_regime ?? St.pct5y)} since Dec 2023, when re-grading old certs was barred)${K.certs_ice ? `; ICE certs ${f0(K.certs_ice.now.total / 1000)}k bags, ${f0(K.certs_ice.now.pending / 1000)}k pending grading` : ''}: ${St.spread > 0 ? 'the market still pays for nearby coffee' : 'the curve is in carry, nearby supply is comfortable'}.`],
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
