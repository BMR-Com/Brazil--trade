// Sugar section: same tab layout as cotton. Brazil Centre-South crush (MAPA/UNICA), ethanol parity, white premium,
// Brazil exports (SECEX) and the world balance come from sugar/data/sugar.json (built by sugar/scripts/build.py);
// COT, spreads/vol, seasonality and technicals use the desk modules with SB.
const Sugar = (() => {
  let built = false, tab = 'su-primer', S = null;
  const TABS = [['su-primer', 'Primer'], ['su-geo', "Where it's grown, trade &amp; weather"], ['su-bal', 'World balance'], ['su-cs', 'Brazil Centre-South crush'],
    ['su-eth', 'Ethanol parity &amp; mix'], ['su-white', 'White premium'], ['su-exp', 'Brazil exports'], ['su-asia', 'India &amp; Thailand'],
    ['su-flows', 'Futures, options &amp; COT'], ['su-rv', 'Spreads &amp; vol'], ['su-outlook', 'Outlook'], ['su-seas', 'Seasonality &amp; technicals']];
  const body = () => $('#suBody');
  const f1 = v => fmt(v, 1), f2 = v => fmt(v, 2);
  const load = () => S ? Promise.resolve(S) : getJSON('sugar/data/sugar.json').then(d => (S = d));
  function shell() {
    $('#sugar').innerHTML = `<nav class="tabs" id="suTabs">${TABS.map(([k, l], i) => `<button data-t="${k}" class="${k === tab ? 'on' : ''}">${i + 1} · ${l}</button>`).join('')}</nav><main><div id="suBody"></div></main>`;
    $$('#suTabs button').forEach(b => b.onclick = () => { tab = b.dataset.t; $$('#suTabs button').forEach(x => x.classList.toggle('on', x === b)); render(); });
  }
  function show() {
    if (!built) { shell(); built = true; }
    const h = location.hash.slice(1); if (TABS.some(t => t[0] === h)) { tab = h; $$('#suTabs button').forEach(x => x.classList.toggle('on', x.dataset.t === tab)); }
    render();
  }
  const guard = fn => async () => { try { await fn(); } catch (e) { console.error(e); body().innerHTML = '<div class="card"><p class="note">This tab failed to load.</p></div>'; } };
  function render() {
    history.replaceState(null, '', '#' + tab);
    body().innerHTML = '<div class="card"><p class="note">Loading…</p></div>';
    ({ 'su-primer': primer, 'su-geo': () => Geo.mount(body(), 'sugar'), 'su-bal': guard(balance), 'su-cs': guard(crush), 'su-eth': guard(ethanol),
      'su-white': guard(white), 'su-exp': guard(exportsTab), 'su-asia': guard(asia), 'su-flows': flows, 'su-rv': () => RVView.mount(body(), 'SB'),
      'su-outlook': guard(outlook), 'su-seas': () => MktStudy.mount(body(), ['SB']) })[tab]();
  }
  const kpi = (lab, v, sub) => `<div class="kpi card" style="padding:10px"><div class="lbl">${lab}</div><div class="val" style="font-size:19px">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
  const asof = () => `<p class="note">Sugar data built ${S.built}. Sources: MAPA (fortnightly Centre-South production), UNICA (monthly reports), ANP (pump prices), B3 ethanol and ICE futures (TradingView), MDIC/SECEX (exports), USDA FAS PSD.</p>`;

  function primer() {
    const row = (a, b) => `<tr><td class="l"><b>${a}</b></td><td class="l">${b}</td></tr>`;
    const SPR = [
      ['Mar/May (H/K)', 'Q1 → Q2: Brazil off-season into the new crush', 'Usually a premium (Mar over May): Centre-South stocks are lowest in March and the new crop starts filling May.',
        'Old-crop Brazilian sugar delivered into March; Central American surplus when March pays above its carry; whether India/Thailand ship in Q1; the start date of the new crush (stood-over cane and a dry late March bring it forward, rain and immature cane delay it).',
        'When ethanol pays better than sugar, Brazil makes less sugar and the Q1/Q2 supply gap narrows: the spread drifts toward flat.'],
      ['May/Jul (K/N)', 'Early crush → peak crush', 'Usually a premium: even an early start leaves less sugar for May than for July, when Brazil runs at full speed.',
        'Stood-over cane, rain interrupting early field work, the opening sugar/ethanol mix, and any unusually large Q2 supply from India or Thailand.',
        'A heavy Q2 from other exporters, weak import demand or a weak white premium (refiners stop bidding for raws) can push May to a discount; longs avoiding delivery can weaken it into expiry.'],
      ['Jul/Oct (N/V)', 'Peak crush, port bottleneck', 'No fixed pattern: mills make sugar faster than Santos can load it, so stocks build inland toward an October peak.',
        'Vessel queues and their timing, terminal capacity shared with soybeans (Q2) and corn (from July), the expected October stock level, and the mix.',
        'A queue peaking before July weighs on July; big expected October stocks weigh on October.'],
      ['Oct/Mar (V/H)', 'Stock peak → off-season low', 'Usually a discount (Oct under Mar): October sits on the year’s largest Brazilian stocks, March on the smallest.',
        'Centre-South production and stocks, sugar vs ethanol pay, whether exports flow or back up at the ports, the quality and size of Thai/Indian/Australian supply, and the cost of carrying sugar to March.',
        'The discount is roughly capped by carry (financing, storage, insurance). Low Brazilian stocks, port jams, strong Q3 demand and export bans elsewhere can flip it to a premium.']];
    const LSPR = [
      ['Mar/May', 'Refined supply from the northern-hemisphere campaign vs re-export refiners running on Brazilian raws.'],
      ['May/Aug', 'August is London-only: the bridge from Q2 to the main Brazilian white (crystal) and refined-from-Brazil-raws season.'],
      ['Aug/Oct', 'Peak availability of Brazilian crystal sugar and refinery output; freight and container availability matter more than in raws.'],
      ['Oct/Dec', 'EU beet campaign starts; December often sees deliveries of fresh beet and Brazilian sugar.'],
      ['Dec/Mar', 'Asian white supply (Thai/Indian) and destination demand in Q1, against what refiners can make from the raw curve.']];
    body().innerHTML = Specs.slot('sugar') + `<div class="grid g2">
      <div class="card"><h2>Two benchmarks: raw (New York) and white (London)</h2><div class="tbl"><table>
        <tr><th class="l"></th><th class="l">ICE Sugar No. 11 (raw)</th><th class="l">ICE London No. 5 (white)</th></tr>
        <tr><td class="l">What</td><td class="l">Raw cane sugar, an industrial input that must be refined before people eat it</td><td class="l">Refined, food-grade white sugar</td></tr>
        <tr><td class="l">Size / quote</td><td class="l">112,000 lb (50.8 t); ¢/lb, tick 0.01¢ = $11.20</td><td class="l">50 t; $/t, tick $0.10 = $5</td></tr>
        <tr><td class="l">Months</td><td class="l">Mar, May, Jul, Oct</td><td class="l">Mar, May, Aug, Oct, Dec</td></tr>
        <tr><td class="l">Last trade</td><td class="l">Last business day before the delivery month</td><td class="l">16 calendar days before the delivery month (mid-February for March)</td></tr>
        <tr><td class="l">Quality</td><td class="l">Basis 96° polarization; higher pol earns a premium (Brazilian VHP at ~99° gets one), lower pol a penalty</td><td class="l">Minimum 99.8° pol, colour 45 ICUMSA or lower</td></tr>
        <tr><td class="l">Delivery</td><td class="l">FOB bulk, receiver's vessel at a port in an approved origin; the delivery window runs into the contract month</td><td class="l">FOB in bags (bulk by agreement) at an approved port; window starts in the contract month</td></tr>
        <tr><td class="l">Who uses it</td><td class="l">Cane mills (Brazil above all), raw importers and refiners, trade houses, funds</td><td class="l">Refiners, beet and cane white-sugar producers, food and drink buyers in deficit regions</td></tr></table></div>
        <h3>Calendar</h3><p>Brazil Centre-South (≈90% of Brazil's sugar) crushes April to November and ships most of the world's raw sugar from June to January; its October–March rains grow the next crop. India crushes November–April and Thailand December–April, so Asian supply arrives in the first quarter. The ISO crop year runs October–September.</p></div>
      <div class="card"><h2>The white premium: the link between the two</h2>
        <p>White premium = London No. 5 ($/t) − New York No. 11 (¢/lb × 22.0462). It is the futures margin a toll refiner earns by buying raws in New York and selling whites in London.</p>
        <div class="tbl"><table>
          ${row('Horizontal vs diagonal', 'Horizontal pairs the same (or nearest) months: Mar/Mar, May/May, Aug/Jul, Oct/Oct. Refiners hedge on the diagonal, raws one month earlier than whites, because raw sugar has to be shipped and melted first.')}
          ${row('When it is wide', 'Refining pays: refiners buy more raws (supports No. 11 and the front raw spreads) and white supply rises with a lag, which in time pulls the premium back.')}
          ${row('When it is narrow', 'Refiners run at minimum rates rather than shut (restarting is costly), raws lose a buyer, and mills that can choose (crystal vs VHP in Brazil, remelt in Asia) shift toward raws.')}
          ${row('What sets the cost line', 'Energy (gas, fuel oil, coal), the raw-to-white conversion loss, bags and handling, freight to the destination, and financing. A premium below that line squeezes stand-alone refiners first.')}
          ${row('Why it moves on its own', 'Raws and whites have different seasons and supply chains: EU beet and Indian/Thai whites in Q4–Q1, Brazilian crystal and refined-from-raws in Q2–Q3. A white-specific shortage (an export ban, a refinery outage, a squeeze into a London expiry) moves the premium while raws stand still.')}</table></div>
        <p class="note">Desk: the <a href="#" onclick="document.querySelector('#suTabs button[data-t=su-white]').click();return false">White premium</a> tab shows the front and forward premium against past years.</p></div></div>

      <div class="card" style="margin-top:12px"><h2>New York raw spreads: what each one measures</h2>
        <p>A spread is the nearer contract minus the later one. A <b>premium</b> (inverse) says sugar is scarcer now than later; a <b>discount</b> (carry) says the near month is well supplied and someone has to be paid to store. Each No. 11 month is the early leg of one spread and the late leg of another, so a shock in one quarter ripples along the curve.</p>
        <div class="tbl"><table><tr><th class="l">Spread</th><th class="l">Window</th><th class="l">Normal shape and why</th><th class="l">What moves it</th><th class="l">When it breaks the pattern</th></tr>
        ${SPR.map(r => `<tr>${r.map((x, i) => `<td class="l">${i ? x : '<b>' + x + '</b>'}</td>`).join('')}</tr>`).join('')}</table></div></div>

      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>London white spreads</h2><div class="tbl"><table><tr><th class="l">Spread</th><th class="l">What it reflects</th></tr>
          ${LSPR.map(r => `<tr><td class="l"><b>${r[0]}</b></td><td class="l">${r[1]}</td></tr>`).join('')}</table></div>
          <p class="note">London spreads respond to refinery runs, destination demand (Middle East, North and East Africa, South Asia) and who is willing to deliver into an expiry. Packaging and freight make whites slower to move than raws, so local shortages show up in the front London spread before the premium.</p></div>
        <div class="card"><h2>Rules that hold across all spreads</h2><div class="tbl"><table>
          ${row('Carry caps the discount', 'A discount wide enough to pay financing, storage and insurance pays someone to hold sugar, so carry limits how far a spread can fall. Higher interest rates widen that limit; each exporter’s own costs differ.')}
          ${row('Liquidity decides who sets it', 'Front spreads move on fundamentals and deliveries; spreads further out move on order flow and can drift away from fundamentals.')}
          ${row('Expiry and rolls', 'Physical settlement forces futures onto the physical value, so front spreads swing hardest in the last weeks. Index funds roll out of the front month on a fixed schedule, pressing the front leg down and the next one up.')}
          ${row('Reading open interest', 'Speculators usually drive the daily move, so price and open interest together tell who is trading: price up with OI up means new longs; price down with OI up, new shorts; price up with OI down, short covering; price down with OI down, long liquidation. Moves on falling OI tend to run out once the covering is done.')}
          ${row('Annual index rebalance', 'BCOM and S&amp;P GSCI reset their weights once a year in early January, over about the 6th–10th business day: they buy what lagged and sell what outperformed. After a big down year sugar can see tens of thousands of lots of index buying in that window (estimates for January 2026 were near 67k lots after a 23% fall), enough to lift the front month for a few days; the size can be estimated from CFTC index-trader positions.')}
          ${row('Who delivers', 'October and May deliveries are almost all Centre-South Brazil (a clean expiry); March can bring several origins, which makes receivers more cautious.')}
          ${row('Curve shape', 'A curve mostly at premiums (backwardation) says the market wants sugar now; mostly at discounts (contango) says it is oversupplied and pays storage. A shift from one to the other matters more than the level.')}
          ${row('Physical premiums', 'Regional premiums and discounts to the futures (FOB Santos VHP, delivered whites in destinations) do the same job as carry: they move sugar between months and regions.')}</table></div></div></div>

      <div class="card" style="margin-top:12px"><h2>Delivery, laytime and demurrage</h2>
        <p>Both contracts settle by physical delivery FOB the receiver's ship at an origin port. The seller (deliverer) puts sugar alongside and loads it; the buyer (receiver) brings and pays for the ship. Loading speed is guaranteed, and the side that holds up the ship pays for the delay: that is demurrage. Who delivers, from which port, and how fast that port loads all show up in the expiring spread.</p>
        <div class="tbl"><table><tr><th class="l">Step</th><th class="l">New York No. 11 (raw, bulk)</th><th class="l">London No. 5 (white, bags)</th></tr>
        <tr><td class="l"><b>1. Expiry and tender</b></td><td class="l">After the last trading day, deliverers name the growth (origin) and the port; each port must carry a minimum block of contracts. The clearing house matches deliverers with receivers at the expiry settlement price.</td><td class="l">The day after expiry is tender day: sellers name the port (minimum block per port, or the clearing house steps in), and buyers and sellers are matched. Buyers may swap tenders the next day.</td></tr>
        <tr><td class="l"><b>2. Ship nomination</b></td><td class="l">The receiver nominates a vessel in writing at least 7 days before it is expected ready, with size, ETA, quantity and its demurrage and despatch rates. A substitute vessel is allowed within a few days of the original's date.</td><td class="l">The buyer names the vessel 14 days before the delivery day; the seller names who receives the notice of readiness 7 days before.</td></tr>
        <tr><td class="l"><b>3. Delivery window</b></td><td class="l">The ship can present from the 1st of the delivery month to the 15th of the second month after (March: 1 March – 15 May).</td><td class="l">Runs through the delivery month and the following one.</td></tr>
        <tr><td class="l"><b>4. Notice of readiness and laytime</b></td><td class="l">The master tenders notice of readiness (NOR) once the ship is at the port and ready. Laytime (the free loading time) starts at the next local working period, or after the 7-day nomination period if NOR comes early. Berthing is in NOR order unless local custom differs.</td><td class="l">Laytime starts in the afternoon if NOR is given in the morning, otherwise next working morning; weekends and holidays are excluded. In congestion NOR can be tendered at the usual waiting place.</td></tr>
        <tr><td class="l"><b>5. Guaranteed loading rate</b></td><td class="l">4,000 t per weather working day for a ship with four or more workable hatches, pro rata for fewer.</td><td class="l">1,500 t per weather working day (bags are slower), on four or more hatches.</td></tr>
        <tr><td class="l"><b>6. Demurrage and despatch</b></td><td class="l">If loading takes longer than laytime, the deliverer pays the receiver demurrage at the charter-party rate (which must match the market rate for that ship). If it is faster, the receiver pays the deliverer despatch at half that rate. On top, the deliverer pays the receiver a daily fee while the ship stays on demurrage: 0% of the demurrage rate for the first 15 days, 50% for days 16–30 and 100% after that (from the March 2028 delivery: 0% days 1–10, 50% days 11–20, 100% days 21–30, 150% after). No cap. Settled within 60 days of the bill of lading.</td><td class="l">Same idea: the seller pays demurrage beyond laytime, the buyer pays despatch at half the rate, and the seller adds a daily fee while on demurrage: 0% of the demurrage rate for days 1–21, 25% for days 22–35, 50% for days 36–49, 100% after. Settled in dollars within 60 days of the bill of lading.</td></tr>
        <tr><td class="l"><b>7. Weight and quality</b></td><td class="l">Shipper's weights and tests at loading, under an independent supervisor; samples split and sealed. Price is adjusted for polarization (premium above 96°, discount below).</td><td class="l">Supervisor's certificate of weight, packing and quality (pol, colour, moisture); disputes go to an exchange-approved chemist.</td></tr>
        <tr><td class="l"><b>8. Documents and payment</b></td><td class="l">Clean on-board bills of lading, invoice at the actual polarization, weight and quality certificates, certificate of origin; the receiver pays on presentation. Risk passes when the sugar crosses the ship's rail, title on payment.</td><td class="l">Seller lodges documents on settlement day and is paid through the clearing house unless the buyer rejects them that afternoon.</td></tr>
        <tr><td class="l"><b>9. Default</b></td><td class="l">Failure to load or to take delivery goes to expedited arbitration and cash settlement against the expiry price; force majeure gives limited extra time.</td><td class="l">Insufficient-seller rules and arbitration; quality, weight and packing claims go to arbitration.</td></tr></table></div>
        <div class="tbl" style="margin-top:8px"><table>
          ${row('Why demurrage matters to the price', 'A port with long queues (Santos in a peak crush) means the deliverer risks paying demurrage on every exchange tender. Deliverers then prefer to sell physical sugar directly, or want a bigger discount to deliver, so congestion weakens the expiring month against the next. When ports are clear, delivery is cheap and the expiring month holds better.')}
          ${row('Why the receiver matters', 'A single large receiver (a refiner or trade house that needs the sugar) means the delivery is absorbed and the front spread firms after expiry; a large delivery with no natural receiver means the sugar has to be re-sold, which weighs on the next month and on physical premiums.')}
          ${row('Off-exchange alternatives', 'Most physical sugar is not delivered through the exchange: buyers and sellers swap futures for physical sugar (exchange for physical) and price off the futures with a premium or discount. Exchange delivery is the backstop that keeps futures tied to physical value.')}</table></div>
        <p class="note">Summary of the ICE Sugar No. 11 rules and ICE Futures Europe White Sugar delivery procedures; rule details change (some No. 11 polarization and delay-fee terms change from the March 2028 delivery), so check the current rulebook before acting.</p></div>
      <div class="card" style="margin-top:12px"><h2>What a delay costs: demurrage and the daily fee in ¢/lb</h2>
        <div class="grid g4" id="dmIn">
          <label>Contract<br><select id="dmK"><option value="n11">No. 11, to Oct 2027 deliveries</option><option value="n11b">No. 11, from Mar 2028</option><option value="n5">No. 5 (white)</option></select></label>
          <label>Cargo, tonnes<br><input id="dmQ" type="number" value="50000" step="5000"></label>
          <label>Demurrage rate, $/day<br><input id="dmR" type="number" value="20000" step="1000"></label>
          <label>Wait for a berth, days<br><input id="dmW" type="number" value="20" step="1"></label></div>
        <div id="dmOut" style="margin-top:8px"></div>
        <p class="note">Laytime = cargo ÷ the contract loading rate (No. 11: 4,000 t a day, No. 5: 1,500 t a day). Time on demurrage = waiting for a berth + loading time − laytime; here loading is assumed to run at exactly the contract rate, so only the queue puts the ship on demurrage. The deliverer pays demurrage for every day on demurrage plus the daily fee on top; 1 ¢/lb = $22.05/t. Demurrage rates follow the freight market for the ship's size (roughly $10–30k a day for the Handysize-to-Panamax ships that load sugar), so set the rate to today's market. Despatch (half the demurrage rate) is paid the other way when a ship loads faster than laytime.</p></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Reading a sugar balance: trade flows by quarter</h2><div class="tbl"><table>
          ${row('Annual balance', 'Production minus consumption by crop year (Oct/Sep or Apr/Mar). It tells you whether stocks grow or shrink, but not when sugar is short.')}
          ${row('Quarterly trade flow', 'For each quarter, exportable raw and white sugar by origin (Centre-South Brazil, India, Thailand, Central America, Australia, EU) against import needs by destination (China, Indonesia, Middle East refiners, Africa, US). Raws and whites are kept apart, with refiners converting one into the other.')}
          ${row('Inputs', 'Crop and mix, port logistics and queues, importer stocks, government stocks and trade policy (export quotas, bans, import duties and licences), freight and energy, and the white premium (which sets refiners’ appetite for raws).')}
          ${row('How to read it', 'A deficit quarter is where stress builds; a surplus quarter needs a cheaper price or a wider carry to clear. Revisions to a balance matter more than its level, because each provider’s level differs.')}
          ${row('Limits', 'Trade flows describe where pressure sits, not when price turns: they react to the market as much as they lead it.')}</table></div></div>
        <div class="card"><h2>What moves sugar</h2><div class="tbl"><table><tr><th class="l">Driver</th><th class="l">Mechanism</th><th class="l">Where on this desk</th></tr>
        <tr><td class="l">Brazil cane and ATR</td><td class="l">Cane crushed × sugar per tonne (ATR) sets how much sugar the mills can make. Rain Oct–Mar, frost and fires Jun–Sep.</td><td class="l">Centre-South crush, weather</td></tr>
        <tr><td class="l">Sugar/ethanol mix</td><td class="l">Brazilian mills switch cane between sugar and ethanol. When hydrous ethanol pays more than sugar, mills cut the sugar mix; the swing is about 4–5 mt of sugar.</td><td class="l">Ethanol parity &amp; mix</td></tr>
        <tr><td class="l">Brazil fuel prices</td><td class="l">Petrobras gasoline pricing, the real and crude set what ethanol is worth at the pump. Drivers fill with hydrous when it costs under ~70% of gasoline.</td><td class="l">Ethanol parity &amp; mix</td></tr>
        <tr><td class="l">Corn ethanol</td><td class="l">Corn ethanol plants in Mato Grosso, Goiás and Mato Grosso do Sul supply a fast-growing share of Brazil's ethanol. Each litre made from corn is a litre the cane mills need not make, so they can hold a higher sugar mix even when ethanol parity is close to sugar; it weakens the old rule that cheap sugar pushes mills back to ethanol.</td><td class="l">Ethanol parity &amp; mix</td></tr>
        <tr><td class="l">Brazil ethanol blend</td><td class="l">The gasoline blend rose from E27 to E30 in 2025 (Combustível do Futuro law), adding about 1.3 bn litres of ethanol demand, the cane equivalent of 1–2 mt of sugar; the law allows up to E35, which would add roughly 3.3 bn litres, around 5.5 mt of sugar-equivalent cane (at about 75 litres of ethanol or 125 kg of sugar per tonne of cane), part of it met by corn ethanol.</td><td class="l">Ethanol parity &amp; mix</td></tr>
        <tr><td class="l">India and Thailand</td><td class="l">India's crop, ethanol diversion and export quotas decide whether India sells to the world. Thailand is the second-largest exporter and the main supplier to Asia.</td><td class="l">India &amp; Thailand</td></tr>
        <tr><td class="l">Refining margin</td><td class="l">A wide white premium pulls raw sugar into refineries (Middle East, North Africa, Asia) and supports No. 11; a narrow one leaves raws unsold.</td><td class="l">White premium</td></tr>
        <tr><td class="l">The real (BRL)</td><td class="l">Brazilian mills earn dollars but pay costs in reais. A weaker real raises the reais a mill gets for each cent of No. 11, so mills hedge and sell more at the same dollar price, which presses the raw futures down; a stronger real does the reverse. Political shocks in Brazil reach sugar mostly through this channel.</td><td class="l">Ethanol parity &amp; mix</td></tr>
        <tr><td class="l">US domestic market (No. 16)</td><td class="l">US sugar is walled off from the world by import quotas and tariffs, so the domestic No. 16 price is set mainly by the US beet and cane crops, harvest pace and refining capacity. It can stay firm while No. 11 falls; a long slide in world prices only feeds through slowly. No. 16 is thinly traded.</td><td class="l">—</td></tr>
        <tr><td class="l">Long-run demand</td><td class="l">Consumption grows with population and income in Asia and Africa and is flat to falling in rich markets. Weight-loss drugs and sugar taxes cut demand first in soft drinks, snacks and alcohol; what matters for sugar is which products and countries lose volume, since makers can protect sales value while using less sugar.</td><td class="l">World balance</td></tr>
        <tr><td class="l">Funds</td><td class="l">Managed money swings are large in sugar; crowded positions, together with index-fund rolls, drive moves around expiry.</td><td class="l">Futures, options &amp; COT</td></tr></table></div></div></div>
      <p class="note">Primer written for this desk from public exchange rules and industry explanations (ICE contract rules; Czapp/Czarnikow explainers on the sugar contracts and spreads). Live readings sit on the other tabs.</p>`;
    const BANDS = { n11: [[15, 0], [15, 0.5], [1e9, 1]], n11b: [[10, 0], [10, 0.5], [10, 1], [1e9, 1.5]], n5: [[21, 0], [14, 0.25], [14, 0.5], [1e9, 1]] };
    const RATE = { n11: 4000, n11b: 4000, n5: 1500 };
    const dm = () => {
      const k = $('#dmK').value, q = +$('#dmQ').value || 0, r = +$('#dmR').value || 0, w = +$('#dmW').value || 0;
      const lay = q / RATE[k], dd = Math.max(0, w), rows = [];
      let left = dd, start = 0, tot = 0, fee = 0;
      for (const [len, pct] of BANDS[k]) {
        const d = Math.min(left, len); if (d <= 0) break;
        const c = d * r, f = d * r * pct; tot += c; fee += f;
        rows.push([`days ${start + 1}–${start + d}`, d, pct, c + f]);
        left -= d; start += len;
      }
      const all = tot + fee, pt = q ? all / q : 0, clb = pt / 22.0462, unit = k === 'n5' ? '$/t' : '¢/lb';
      const per = (x) => k === 'n5' ? '$' + fmt(x / q, 2) + '/t' : fmt(x / q / 22.0462, 3) + ' ¢/lb';
      $('#dmOut').innerHTML = `<div class="grid g4">${kpi('Laytime', fmt(lay, 1) + ' days', `${fmt(q, 0)} t at ${fmt(RATE[k], 0)} t a day`)}
        ${kpi('Days on demurrage', fmt(dd, 0), 'berth wait beyond laytime (loading at contract rate)')}
        ${kpi('Total cost to the deliverer', '$' + fmt(all / 1000, 0) + 'k', `demurrage $${fmt(tot / 1000, 0)}k + daily fee $${fmt(fee / 1000, 0)}k`)}
        ${kpi('In the price', k === 'n5' ? '$' + fmt(pt, 2) + '/t' : fmt(clb, 2) + ' ¢/lb', k === 'n5' ? `${fmt(clb, 2)} ¢/lb equivalent` : `$${fmt(pt, 2)}/t`)}</div>
        <div class="tbl"><table><tr><th class="l">Period on demurrage</th><th>Days</th><th>Daily fee (% of demurrage)</th><th>Cost incl. fee</th><th>Per unit</th><th>Per extra day</th></tr>
        ${rows.map(x => `<tr><td class="l">${x[0]}</td><td class="n">${fmt(x[1], 0)}</td><td class="n">${fmt(100 * x[2], 0)}%</td><td class="n">$${fmt(x[3] / 1000, 0)}k</td><td class="n">${per(x[3])}</td><td class="n">${per(x[3] / x[1])}</td></tr>`).join('')}</table></div>`;
    };
    ['#dmK', '#dmQ', '#dmR', '#dmW'].forEach(id => $(id).addEventListener('input', dm)); dm();
  }

  // ---------- world balance ----------
  async function balance() {
    await load();
    const P = S.psd, W = P.World, n = W.years.length, yl = y => `${y}/${String(y + 1).slice(2)}`;
    const ctry = ['Brazil', 'India', 'Thailand', 'China', 'EU'];
    const i = n - 1, j = n - 2;
    const row = (c, k) => { const d = P[c]; return `<td class="n">${f1(d[k][i])}</td><td class="n">${sgn(d[k][i] - d[k][j], 1)}</td>`; };
    const est = (S.estimates || []).slice().sort((a, b) => (a.country + a.season + a.item).localeCompare(b.country + b.season + b.item) || b.date.localeCompare(a.date));
    body().innerHTML = `<div class="grid g4">${kpi(`World production ${yl(W.years[i])}`, f1(W.prod[i]) + ' mt', `${sgn(W.prod[i] - W.prod[j], 1)} mt on the year`)}
        ${kpi('World consumption', f1(W.cons[i]) + ' mt', `${sgn(W.cons[i] - W.cons[j], 1)} mt`)}
        ${kpi('Surplus (prod − cons)', sgn(W.prod[i] - W.cons[i], 1) + ' mt', `last year ${sgn(W.prod[j] - W.cons[j], 1)}`)}
        ${kpi('Stocks / use', f1(W.stu[i]) + '%', `last year ${f1(W.stu[j])}%`)}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>World production, consumption and stocks/use</h2><div style="position:relative;height:300px"><canvas id="suW"></canvas></div>
          <p class="note">USDA PSD, centrifugal sugar, raw value, million tonnes; marketing years as USDA reports them (mostly Oct–Sep).</p></div>
        <div class="card"><h2>Main countries, ${yl(W.years[i])}</h2><div class="tbl"><table><tr><th class="l">Country</th><th>Production</th><th>±</th><th>Consumption</th><th>±</th><th>Exports</th><th>±</th><th>Imports</th><th>±</th><th>Ending stocks</th><th>±</th></tr>
          ${ctry.map(c => `<tr><td class="l">${c}</td>${row(c, 'prod')}${row(c, 'cons')}${row(c, 'exp')}${row(c, 'imp')}${row(c, 'end')}</tr>`).join('')}</table></div>
          <div style="position:relative;height:220px;margin-top:8px"><canvas id="suX"></canvas></div><p class="note">Exports by country, mt. Brazil supplies about half of world exports.</p></div></div>
      <div class="card" style="margin-top:12px"><h2>Latest estimates from the trade and agencies</h2><div class="tbl"><table><tr><th class="l">Country</th><th class="l">Scope</th><th>Season</th><th class="l">Item</th><th>Value</th><th class="l">Source</th><th>Date</th></tr>
        ${est.map(e => `<tr><td class="l">${e.country}</td><td class="l">${e.scope}</td><td>${e.season}</td><td class="l">${e.item}</td><td class="n"><b>${f2(e.value)}</b> ${e.unit}</td><td class="l">${e.url ? `<a href="${e.url}" target="_blank" rel="noopener">${e.source}</a>` : e.source}</td><td>${e.date}</td></tr>`).join('')}</table></div></div>${asof()}`;
    const lab = W.years.map(yl);
    chart('suW', { type: 'bar', data: { labels: lab, datasets: [
      { label: 'Production', data: W.prod, backgroundColor: '#2f6b3a', yAxisID: 'y' }, { label: 'Consumption', data: W.cons, backgroundColor: '#d68910', yAxisID: 'y' },
      { type: 'line', label: 'Stocks/use %', data: W.stu, borderColor: '#2c6fbb', pointRadius: 2, yAxisID: 'y1' }] },
      options: { scales: { y: { min: 130 }, y1: { position: 'right', grid: { display: false } } } } });
    chart('suX', { type: 'line', data: { labels: lab, datasets: ctry.map((c, k) => ({ label: c, data: P[c].exp, borderColor: PAL[k], pointRadius: 0, borderWidth: 1.6 })) } });
  }

  // ---------- Centre-South crush ----------
  async function crush() {
    await load();
    const C = S.crush, cur = C.current, sz = C.seasons[cur], Pj = C.projection, U = S.unica, n = sz.fn.length - 1;
    const prevK = Object.keys(C.seasons).sort().filter(k => k < cur).pop(), pv = C.seasons[prevK];
    const at = (s, k) => s[k][Math.min(n, s[k].length - 1)];
    const rng = x => `${f1(x.lo)}–${f1(x.hi)}`;
    const mixNow = U.implied_mix?.at(-1);
    const uv = (k, t = 'accumulated') => U[t][k];
    body().innerHTML = `<div class="grid g4">
        ${kpi(`Cane crushed to ${sz.end[n]}`, f1(at(sz, 'cane')) + ' mt', `${sgn(100 * (at(sz, 'cane') / at(pv, 'cane') - 1), 1, '%')} vs ${prevK} at the same fortnight`)}
        ${kpi('Sugar made', f2(at(sz, 'sugar')) + ' mt', `${sgn(100 * (at(sz, 'sugar') / at(pv, 'sugar') - 1), 1, '%')} on the year`)}
        ${kpi('Ethanol made', f2(at(sz, 'ethanol')) + ' bn L', `${sgn(100 * (at(sz, 'ethanol') / at(pv, 'ethanol') - 1), 1, '%')} on the year`)}
        ${kpi('Sugar mix (latest fortnight)', mixNow ? f1(mixNow.mix) + '%' : '–', mixNow ? `fortnight to ${mixNow.end}${mixNow.corn_est ? '; corn ethanol estimated out' : ''}` : '')}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Season to date: sugar made by fortnight</h2><div style="position:relative;height:300px"><canvas id="suCane"></canvas></div>
          <p class="note">Cumulative from April 1. MAPA fortnightly Centre-South production (all mills), million tonnes.</p></div>
        <div class="card"><h2>Where the season ends</h2><p>At the pace of past seasons from this fortnight on, Centre-South ${cur} ends at:</p>
          <div class="tbl"><table><tr><th class="l"></th><th>So far</th><th>Central</th><th>Middle range</th><th>Past-season range</th></tr>
          <tr><td class="l">Cane, mt</td><td class="n">${f1(Pj.cane.now)}</td><td class="n"><b>${f1(Pj.cane.mid)}</b></td><td class="n">${rng(Pj.cane)}</td><td class="n">${f1(Pj.cane.min)}–${f1(Pj.cane.max)}</td></tr>
          <tr><td class="l">Sugar, mt</td><td class="n">${f2(Pj.sugar.now)}</td><td class="n"><b>${f2(Pj.sugar.mid)}</b></td><td class="n">${rng(Pj.sugar)}</td><td class="n">${f1(Pj.sugar.min)}–${f1(Pj.sugar.max)}</td></tr>
          <tr><td class="l">Ethanol, bn L</td><td class="n">${f2(Pj.ethanol.now)}</td><td class="n"><b>${f2(Pj.ethanol.mid)}</b></td><td class="n">${rng(Pj.ethanol)}</td><td class="n">${f1(Pj.ethanol.min)}–${f1(Pj.ethanol.max)}</td></tr></table></div>
          <details style="margin-top:8px"><summary>Each past season's finish applied to this year</summary><div class="tbl"><table><tr><th class="l">Pattern of</th><th>Pace ratio</th><th>Cane</th><th>Sugar</th><th>Ethanol</th></tr>
            ${Pj.by_season.map(r => `<tr><td class="l">${r.safra}</td><td class="n">${f2(r.pace_ratio)}</td><td class="n">${f1(r.cane)}</td><td class="n">${f2(r.sugar)}</td><td class="n">${f2(r.ethanol)}</td></tr>`).join('')}</table></div></details>
          <h3>Same date in past seasons</h3><div class="tbl"><table><tr><th class="l">Season</th><th>Cane</th><th>Sugar</th><th>Ethanol</th><th>Sugar kg/t cane</th><th>Hydrous stocks</th></tr>
            ${C.same_date.map(r => `<tr><td class="l">${r.safra}</td><td class="n">${f1(r.cane)}</td><td class="n">${f2(r.sugar)}</td><td class="n">${f2(r.ethanol)}</td><td class="n">${f1(r.kgt)}</td><td class="n">${f2(r.hyd_stock)}</td></tr>`).join('')}</table></div></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>UNICA, accumulated to ${U.position}</h2><div class="tbl"><table><tr><th class="l"></th>${U.seasons.map(s => `<th>${s}</th>`).join('')}<th>Change</th></tr>
          ${[['cane_kt', 'Cane, kt', 0], ['sugar_kt', 'Sugar, kt', 0], ['ethanol_ml', 'Ethanol, m L', 0], ['hydrous_ml', 'of which hydrous', 0], ['anhydrous_ml', 'of which anhydrous', 0], ['atr_kg_t', 'ATR, kg/t', 2], ['sugar_kg_t', 'Sugar, kg/t cane', 2], ['mix_sugar', 'Sugar mix, %', 2]]
            .map(([k, l, d]) => { const v = uv(k); return v ? `<tr><td class="l">${l}</td>${v.map(x => `<td class="n">${fmt(x, d)}</td>`).join('')}<td class="n">${k.includes('mix') || k.includes('kg_t') ? sgn(v[1] - v[0], 2) : sgn(100 * (v[1] / v[0] - 1), 1, '%')}</td></tr>` : ''; }).join('')}</table></div>
          ${U.corn?.total_fn?.length ? `<p class="note">Corn ethanol (UNICA members), latest fortnight ${U.corn.fortnight.at(-1)}: ${f1(U.corn.total_fn.at(-1))} m L. Corn ethanol is why total ethanol can rise while the cane mix still favours sugar.</p>` : ''}</div>
        <div class="card"><h2>Cane by state, season to date</h2><div class="tbl"><table><tr><th class="l">State</th><th>Cane, mt</th><th>vs last year</th><th>Sugar, mt</th><th>vs last year</th></tr>
          ${C.states.map(r => `<tr><td class="l">${r.uf}</td><td class="n">${f1(r.cane)}</td><td class="n">${sgn(100 * (r.cane / r.cane_prev - 1), 1, '%')}</td><td class="n">${f2(r.sugar)}</td><td class="n">${sgn(100 * (r.sugar / r.sugar_prev - 1), 1, '%')}</td></tr>`).join('')}</table></div>
          <div style="position:relative;height:220px;margin-top:8px"><canvas id="suKgt"></canvas></div><p class="note">Sugar kg per tonne of cane, by fortnight (MAPA). Falls when mills favour ethanol or ATR drops.</p></div></div>${asof()}`;
    const ks = Object.keys(C.seasons).sort().slice(-5);
    const L = Array.from({ length: 24 }, (_, k) => 'F' + (k + 1));
    chart('suCane', { type: 'line', data: { labels: L, datasets: ks.flatMap((k, q) => [
      { label: k + ' sugar', data: C.seasons[k].sugar, borderColor: PAL[q], borderWidth: k === cur ? 2.6 : 1.2, pointRadius: k === cur ? 2 : 0, yAxisID: 'y' }]) },
      options: { scales: { y: { title: { display: true, text: 'sugar, mt' } } } } });
    chart('suKgt', { type: 'line', data: { labels: L, datasets: ks.map((k, q) => ({ label: k, data: C.seasons[k].cane.map((c, t) => { const dc = c - (C.seasons[k].cane[t - 1] || 0), ds = C.seasons[k].sugar[t] - (C.seasons[k].sugar[t - 1] || 0); return dc > 1 ? +(1000 * ds / dc).toFixed(1) : null; }),
      borderColor: PAL[q], borderWidth: k === cur ? 2.4 : 1.1, pointRadius: 0 })) } });
  }

  // ---------- ethanol ----------
  async function ethanol() {
    await load();
    const Pa = S.parity, nw = Pa.now, Pu = S.pump, m = Pu.ratio.length - 1;
    const yrs = 5, cut = new Date(); cut.setFullYear(cut.getFullYear() - yrs); const c0 = cut.toISOString().slice(0, 10);
    const k0 = Pa.dates.findIndex(d => d >= c0);
    body().innerHTML = `<div class="grid g4">
        ${kpi('Hydrous ethanol parity', f2(nw.parity) + ' ¢/lb', `B3 ethanol R$${fmt(nw.eth, 0)}/m³ at R$${fmt(nw.fx, 4)}/US$ (${nw.date})`)}
        ${kpi('Sugar No. 11 front', f2(nw.sb) + ' ¢/lb', `ethanol − sugar ${sgn(nw.eth_minus_sugar, 2)} ¢/lb`)}
        ${kpi('Parity vs last 5 years', fmt(nw.pct_rank_5y, 0) + 'th percentile', nw.eth_minus_sugar < 0 ? 'sugar pays more than ethanol: mills max sugar' : 'ethanol pays more: mills shift cane to ethanol')}
        ${kpi('Pump ratio hydrous/gasoline', f1(Pu.ratio[m]) + '%', `São Paulo, week to ${Pu.dates[m]}; under ~70% drivers choose ethanol`)}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Sugar against hydrous ethanol parity</h2><div style="position:relative;height:300px"><canvas id="suPar"></canvas></div>
          <p class="note">Ethanol parity = the B3 hydrous ethanol price converted to the raw-sugar ¢/lb a mill would need to be indifferent, after ATR conversion, the real and FOB logistics. When No. 11 trades well above parity, mills make as much sugar as their equipment allows (the mix runs near its maximum); below it, the mix falls and Brazil exports less.</p></div>
        <div class="card"><h2>Pump prices, São Paulo</h2><div style="position:relative;height:300px"><canvas id="suPump"></canvas></div>
          <p class="note">ANP weekly retail prices, R$/litre. Hydrous demand rises when the ratio is below ~70% (ethanol has ~70% of gasoline's energy).</p></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Sugar mix by fortnight</h2><div style="position:relative;height:240px"><canvas id="suMix"></canvas></div>
          <p class="note">Share of cane ATR made into sugar, implied from MAPA fortnightly sugar and ethanol (corn ethanol removed where estimated).</p></div>
        <div class="card"><h2>Brent in reais</h2><div style="position:relative;height:240px"><canvas id="suBrl"></canvas></div>
          <p class="note">Brent × USD/BRL: what Petrobras' import parity for gasoline follows. Higher gasoline lets ethanol price higher and pulls cane away from sugar.</p></div></div>${asof()}`;
    const sl = a => a.slice(k0);
    chart('suPar', { type: 'line', data: { labels: sl(Pa.dates), datasets: [
      { label: 'Sugar No. 11 front', data: sl(Pa.sb), borderColor: '#2f6b3a', pointRadius: 0, borderWidth: 1.6 },
      { label: 'Hydrous ethanol parity', data: sl(Pa.par), borderColor: '#d68910', pointRadius: 0, borderWidth: 1.6 }] } });
    chart('suPump', { type: 'line', data: { labels: Pu.dates, datasets: [
      { label: 'Hydrous', data: Pu.hydrous, borderColor: '#2f6b3a', pointRadius: 0, yAxisID: 'y' }, { label: 'Gasoline', data: Pu.gasoline, borderColor: '#c0392b', pointRadius: 0, yAxisID: 'y' },
      { label: 'Ratio %', data: Pu.ratio, borderColor: '#2c6fbb', borderDash: [4, 3], pointRadius: 0, yAxisID: 'y1' }] },
      options: { scales: { y1: { position: 'right', grid: { display: false } } } } });
    const IM = S.unica.implied_mix || [];
    chart('suMix', { type: 'bar', data: { labels: IM.map(x => x.end), datasets: [{ label: 'Sugar mix %', data: IM.map(x => x.mix), backgroundColor: IM.map(x => x.corn_est ? '#9cb89f' : '#2f6b3a') }] }, options: { scales: { y: { min: 30 } } } });
    const B = Pa.brent_brl || { dates: [], v: [] };
    chart('suBrl', { type: 'line', data: { labels: B.dates, datasets: [{ label: 'Brent, R$/bbl', data: B.v, borderColor: '#7d3c98', pointRadius: 0 }] } });
  }

  // ---------- white premium ----------
  async function white() {
    await load();
    const W = S.white, F = W.front, cut = new Date(); cut.setFullYear(cut.getFullYear() - 6); const c0 = cut.toISOString().slice(0, 10), k0 = Math.max(0, F.dates.findIndex(d => d >= c0));
    const MON = { H: 'March', K: 'May', Q: 'August', V: 'October', Z: 'December' };
    body().innerHTML = `<div class="grid g2">
        <div class="card"><h2>White premium curve (${W.curve[0]?.date || ''})</h2><div class="tbl"><table><tr><th class="l">London / NY pair</th><th>White $/t</th><th>Raw ¢/lb</th><th>Premium $/t</th><th>1 week ago</th><th>Rank vs history</th></tr>
          ${W.curve.map(r => `<tr><td class="l">${r.pair}</td><td class="n">${f1(r.white)}</td><td class="n">${f2(r.raw)}</td><td class="n"><b>${f1(r.prem)}</b></td><td class="n">${f1(r.prem_1w)}</td><td class="n">${r.pct_vs_hist != null ? fmt(r.pct_vs_hist, 0) + 'th pct' : '–'}</td></tr>`).join('')}</table></div>
          <p class="note">Premium = London No. 5 white ($/t) − New York No. 11 raw (¢/lb × 22.046). A stand-alone refinery needs roughly $80–100/t to cover melting, energy and freight; above that, refiners bid for raws (supports No. 11); below it, raws back up at origin.</p></div>
        <div class="card"><h2>Front white premium</h2><div style="position:relative;height:300px"><canvas id="suWp"></canvas></div></div></div>
      <div class="card" style="margin-top:12px"><h2>Same pair in past years: average premium in the 30 days before expiry</h2><div class="grid g3">
        ${Object.entries(W.history).map(([m, a]) => `<div><h3>${MON[m] || m} whites</h3><div class="tbl"><table><tr><th>Year</th><th>$/t</th></tr>${a.slice(-10).reverse().map(r => `<tr><td>${r.year}</td><td class="n">${f1(r.avg30)}</td></tr>`).join('')}</table></div></div>`).join('')}</div></div>${asof()}`;
    chart('suWp', { type: 'line', data: { labels: F.dates.slice(k0), datasets: [{ label: 'White premium, $/t', data: F.prem.slice(k0), borderColor: '#2c6fbb', pointRadius: 0, borderWidth: 1.4 }] } });
  }

  // ---------- exports ----------
  async function exportsTab() {
    await load();
    const E = S.exports, M = E.monthly, last = E.pace.at(-1), prev = E.pace.at(-2);
    body().innerHTML = `<div class="grid g4">
        ${kpi(`Brazil exports ${last.my}, to ${E.last}`, f2(last.to_date) + ' mt', `${sgn(100 * (last.to_date / prev.to_date - 1), 1, '%')} vs ${prev.my} at the same month`)}
        ${kpi(`Last month (${E.last})`, f2(M.raw.at(-1) + M.white.at(-1)) + ' mt', `raw ${f2(M.raw.at(-1))} · white ${f2(M.white.at(-1))}`)}
        ${kpi('Average price', fmt(M.usd_t.at(-1), 0) + ' $/t', 'FOB, SECEX unit value')}
        ${kpi(`${prev.my} total`, f2(prev.total) + ' mt', 'Apr–Mar marketing year')}</div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Monthly exports, raw and white</h2><div style="position:relative;height:300px"><canvas id="suEm"></canvas></div><p class="note">MDIC/SECEX, HS 1701, million tonnes. Unit value on the right axis.</p></div>
        <div class="card"><h2>Cumulative by marketing year (Apr–Mar)</h2><div style="position:relative;height:300px"><canvas id="suEc"></canvas></div></div></div>
      <div class="grid g2" style="margin-top:12px">
        <div class="card"><h2>Pace</h2><div class="tbl"><table><tr><th class="l">Marketing year</th><th>To date</th><th>Full year</th><th>Share shipped</th></tr>
          ${E.pace.map(r => `<tr><td class="l">${r.my}</td><td class="n">${f2(r.to_date)}</td><td class="n">${r.total ? f2(r.total) : '–'}</td><td class="n">${r.total ? fmt(100 * r.to_date / r.total, 0) + '%' : '–'}</td></tr>`).join('')}</table></div></div>
        <div class="card"><h2>Top destinations this marketing year</h2><div class="tbl"><table><tr><th class="l">Country</th><th>mt</th><th>Same time last year</th><th>Change</th></tr>
          ${E.dest.map(r => `<tr><td class="l">${r.country}</td><td class="n">${f2(r.t)}</td><td class="n">${f2(r.prev)}</td><td class="n">${sgn(r.t - r.prev, 2)}</td></tr>`).join('')}</table></div></div></div>
      <div id="suFlow" style="margin-top:12px"></div>
      <p class="note">Full Brazil export detail for every product: <a href="#brexp">Brazil exports tab</a>.</p>${asof()}`;
    getJSON('data/sugar/flows.json').then(F => {
      if (!$('#suFlow')) return;
      const fc = F.forecast, B = F.balance, Su = F.surprise;
      $('#suFlow').innerHTML = `<div class="card"><h2>Brazil export flow forecast <span class="note">data to ${F.last_month}</span></h2>
        <div class="grid g4">${kpi('Next month (' + fc.next_month + ')', f2(fc.next_month_mt) + ' mt', `same month last year ${f2(fc.next_month_ly)} mt`)}
        ${kpi('Next three months', f2(fc.next3_mt) + ' mt', `${fc.next3}; last year ${f2(fc.next3_ly)} mt (${sgn(100 * (fc.next3_mt / fc.next3_ly - 1), 0, '%')})`)}
        ${kpi('Last month vs forecast', sgn(Su.mt.at(-1), 2) + ' mt', `${Su.months.at(-1)}: ${Su.mt.at(-1) < 0 ? 'Brazil shipped less than its production and pace implied' : 'Brazil shipped more than its production and pace implied'}`)}
        ${kpi('Season stock build', f2(B.season_build.at(-1)) + ' mt', 'production − consumption − exports since April')}</div>
        ${F.weekly ? `<div class="grid g4" style="margin-top:8px">${kpi('Mid-month read (' + F.weekly.month + ')', f2(F.weekly.projected_mt) + ' mt', `SECEX weekly: ${f2(F.weekly.mtd_mt)} mt in ${F.weekly.days} of ${F.weekly.workdays} working days (${fmt(F.weekly.avg_t_day / 1000, 0)}k t/day vs ${fmt(F.weekly.ly_avg_t_day / 1000, 0)}k last year)`)}
          ${kpi('Mid-month vs forecast', F.weekly.surprise_mt == null ? '–' : sgn(F.weekly.surprise_mt, 2) + ' mt', F.weekly.forecast_mt == null ? '' : `forecast ${f2(F.weekly.forecast_mt)} mt; data to ${F.weekly.asof}`)}
          ${F.china ? kpi('Brazil → China, last 2 months', fmt(F.china.last2_kt, 0) + ' kt', `same months last year ${fmt(F.china.last2_ly_kt, 0)} kt; Brazil supplies about 85% of China's imports`) : ''}
          ${F.china ? kpi('Brazil → China, year to date', fmt(F.china.ytd_kt, 0) + ' kt', `to ${F.china.last}; last year ${fmt(F.china.ytd_ly_kt, 0)} kt`) : ''}</div>` : ''}
        <div class="grid g2" style="margin-top:8px"><div style="position:relative;height:240px"><canvas id="suFlB"></canvas></div><div style="position:relative;height:240px"><canvas id="suFlS"></canvas></div></div>
        ${F.china ? '<div style="position:relative;height:200px;margin-top:8px"><canvas id="suFlC"></canvas></div>' : ''}
        <p class="note">Left: monthly Brazil sugar production, exports and domestic use, mt. Right: actual exports minus the forecast made a month earlier, mt. Variables used: ${F.variables.join('; ')}. Mid-month read = SECEX weekly month-to-date daily average × working days. Sources: MAPA, MDIC/SECEX (monthly and weekly), USDA PSD, China customs via UN Comtrade.</p></div>`;
      chart('suFlB', { type: 'bar', data: { labels: B.months, datasets: [{ label: 'Production', data: B.prod, backgroundColor: '#2f6b3a' }, { label: 'Exports', data: B.exports, backgroundColor: '#d68910' },
        { type: 'line', label: 'Domestic use', data: B.cons, borderColor: '#7f8c8d', pointRadius: 0 }] } });
      if (F.china) chart('suFlC', { type: 'bar', data: { labels: F.china.months, datasets: [{ label: 'Brazil sugar exports to China, kt (leads China customs imports by 1–2 months)', data: F.china.brazil_to_china_kt, backgroundColor: '#c0392b' }] } });
      chart('suFlS', { type: 'bar', data: { labels: Su.months, datasets: [{ label: 'Exports vs forecast, mt', data: Su.mt, backgroundColor: Su.mt.map(v => v < 0 ? '#c0392b' : '#2c6fbb') }] } });
    }).catch(() => { $('#suFlow').innerHTML = ''; });
    chart('suEm', { type: 'bar', data: { labels: M.ym, datasets: [{ label: 'Raw', data: M.raw, backgroundColor: '#d68910', stack: 's' }, { label: 'White', data: M.white, backgroundColor: '#2c6fbb', stack: 's' },
      { type: 'line', label: '$/t', data: M.usd_t, borderColor: '#7f8c8d', pointRadius: 0, yAxisID: 'y1' }] }, options: { scales: { x: { stacked: true }, y: { stacked: true }, y1: { position: 'right', grid: { display: false } } } } });
    const ys = Object.keys(E.my).sort().slice(-6), ML = ['Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar'];
    chart('suEc', { type: 'line', data: { labels: ML, datasets: ys.map((y, q) => ({ label: `${y}/${String(+y + 1).slice(2)}`, data: E.my[y].cum, borderColor: PAL[q], borderWidth: q === ys.length - 1 ? 2.6 : 1.2, pointRadius: 0 })) } });
  }

  // ---------- India & Thailand ----------
  async function asia() {
    await load();
    const P = S.psd, yl = y => `${y}/${String(y + 1).slice(2)}`;
    const est = c => (S.estimates || []).filter(e => e.country === c).sort((a, b) => b.season.localeCompare(a.season) || b.date.localeCompare(a.date));
    const card = (c, id, txt) => { const d = P[c], n = d.years.length - 1; return `<div class="card"><h2>${c}</h2><p>${txt}</p>
      <div style="position:relative;height:240px"><canvas id="${id}"></canvas></div>
      <div class="tbl"><table><tr><th class="l">${yl(d.years[n])} (USDA)</th><th>Production</th><th>Consumption</th><th>Exports</th><th>Ending stocks</th></tr>
      <tr><td class="l">mt</td><td class="n">${f1(d.prod[n])}</td><td class="n">${f1(d.cons[n])}</td><td class="n">${f1(d.exp[n])}</td><td class="n">${f1(d.end[n])}</td></tr>
      <tr><td class="l">vs last year</td><td class="n">${sgn(d.prod[n] - d.prod[n - 1], 1)}</td><td class="n">${sgn(d.cons[n] - d.cons[n - 1], 1)}</td><td class="n">${sgn(d.exp[n] - d.exp[n - 1], 1)}</td><td class="n">${sgn(d.end[n] - d.end[n - 1], 1)}</td></tr></table></div>
      <h3>Latest estimates</h3><div class="tbl"><table>${est(c).map(e => `<tr><td>${e.season}</td><td class="l">${e.item}</td><td class="n"><b>${f2(e.value)}</b></td><td class="l">${e.url ? `<a href="${e.url}" target="_blank" rel="noopener">${e.source}</a>` : e.source}</td><td>${e.date}</td></tr>`).join('') || '<tr><td class="note">None recorded.</td></tr>'}</table></div></div>`; };
    body().innerHTML = `<div class="grid g2">
      ${card('India', 'suIn', 'The second-largest producer and the largest consumer. Exports only when the government allows (quotas set each season after domestic needs and ethanol diversion); a monsoon shortfall or more cane diverted to ethanol removes India from the world market. Crush runs November to April, mostly Maharashtra, Uttar Pradesh and Karnataka.')}
      ${card('Thailand', 'suTh', 'The second-largest exporter and the main supplier to Asian refiners (Indonesia, China, Korea, Japan). Rain-fed cane: the May–October monsoon sets the next crop, crushed December to April. Thai sugar competes with Brazilian raws on freight into Asia.')}</div>
      <div class="card" style="margin-top:12px"><h2>Weather in the cane belts</h2><p class="note">Monsoon rain against history for Uttar Pradesh, Maharashtra and central Thailand is on the <a href="#su-geo" onclick="document.querySelector('#suTabs button[data-t=su-geo]').click();return false">Where it's grown, trade &amp; weather</a> tab.</p></div>${asof()}`;
    const ch = (id, d) => chart(id, { type: 'bar', data: { labels: d.years.map(yl), datasets: [{ label: 'Production', data: d.prod, backgroundColor: '#2f6b3a' }, { label: 'Consumption', data: d.cons, backgroundColor: '#d68910' }, { type: 'line', label: 'Exports', data: d.exp, borderColor: '#2c6fbb', pointRadius: 0 }] } });
    ch('suIn', P.India); ch('suTh', P.Thailand);
  }

  function flows() {
    body().innerHTML = `<div id="suCot"></div><div class="card" style="margin-top:12px"><h2>Index traders and the full COT read</h2>
      <p class="note">Index-trader (CIT) positions, trader concentration and all report categories: <a href="#cot" onclick="document.querySelector('nav.comm button[data-c=cotfull]').click();return false">COT (full) tab</a>. Sugar has the largest index-fund weight in the softs, so the GSCI/BCOM roll (5th–9th business day of the month before expiry) moves the front spread.</p></div>`;
    CotDesk.mount($('#suCot'), ['SB']);
  }

  async function outlook() {
    await load();
    const Pj = S.crush.projection, Pa = S.parity.now, wp = S.white.curve[0], W = S.psd.World, n = W.years.length - 1, B = S.balance;
    const tilt = (v, t) => v > t ? '<span class="up">supportive</span>' : v < -t ? '<span class="dn">bearish</span>' : 'neutral';
    const F = [
      ['World balance', tilt(-(W.prod[n] - W.cons[n]), 1.5), `USDA has world production ${f1(W.prod[n])} mt against consumption ${f1(W.cons[n])} mt, a ${W.prod[n] >= W.cons[n] ? 'surplus' : 'deficit'} of ${f1(Math.abs(W.prod[n] - W.cons[n]))} mt; stocks/use ${f1(W.stu[n])}%.`],
      ['Centre-South crop', tilt(34.5 - Pj.sugar.mid, 0.5), `At past-season pace the Centre-South makes ${f2(Pj.sugar.mid)} mt of sugar this season (middle range ${f1(Pj.sugar.lo)}–${f1(Pj.sugar.hi)}), from ${f1(Pj.cane.mid)} mt of cane.`],
      ['Ethanol parity', tilt(-Pa.eth_minus_sugar, 1), `Sugar ${f2(Pa.sb)} ¢/lb against hydrous parity ${f2(Pa.parity)} ¢/lb: ${Pa.eth_minus_sugar < 0 ? 'sugar still pays more, so mills keep the mix high. Below parity mills shift cane to ethanol, but that changes the mix over a season, not the price week to week' : 'ethanol pays more, so mills cut the sugar mix'}.`],
      ['Refining demand', tilt((wp?.prem || 90) - 90, 10), wp ? `Front white premium $${f1(wp.prem)}/t (${wp.pair}), ${fmt(wp.pct_vs_hist, 0)}th percentile of past years.` : 'No white premium data.'],
    ];
    body().innerHTML = `<div class="card"><h2>Sugar outlook factors</h2><div class="tbl"><table>${F.map(([a, t, x]) => `<tr><td class="l"><b>${a}</b></td><td>${t}</td><td class="l sv-w">${x}</td></tr>`).join('')}</table></div>
        <p class="note">Rule-of-thumb read of the data on these tabs; not a forecast.</p></div>
      <div id="suSig" style="margin-top:12px"></div>
      <div id="suCz" style="margin-top:12px"></div>
      <div id="suTech" style="margin-top:12px"></div>
      <div class="grid g2" style="margin-top:12px"><div class="card"><h2>Next events</h2><div id="suCal"></div></div>
        <div class="card"><h2>Sugar headlines</h2><div id="suNews"></div></div></div>
      <div id="suSzUp" style="margin-top:12px"></div>`;
    getJSON('data/sugar/signals.json').then(G => {
      const N = G.now, H = G.history, k = v => v == null ? '–' : fmt(v, 0);
      $('#suSig').innerHTML = `<div class="card"><h2>Positioning, reais and parity <span class="note">CFTC ${G.cot_date}</span></h2>
        <div class="grid g4">${kpi('Managed money net', sgn(N.mm_net, 0) + ' lots', `${f1(N.mm_pct_oi)}% of open interest; ${k(N.mm_pctile_3y)}th percentile of 3 years; ${sgn(N.mm_chg_1w, 0)} on the week`)}
        ${kpi('Sugar in reais', 'R$ ' + k(N.brl_t) + '/t', `${k(N.brl_t_pctile_5y)}th percentile of 5 years: the price mills see when they fix`)}
        ${kpi('Over hydrous parity', sgn(N.parity_premium, 2) + ' ¢/lb', N.parity_premium > 0 ? 'sugar pays more than ethanol: mix stays at maximum sugar' : 'ethanol pays more: mills shift cane to ethanol')}
        ${kpi('Market depth', k(N.lots_per_point_last) + ' lots/pt', `fund lots per point of price last week; median ${k(N.lots_per_point_median)} since 2021`)}</div>
        <div style="position:relative;height:220px;margin-top:8px"><canvas id="suSigC"></canvas></div>
        <p class="note">Managed money net as % of open interest (left) and sugar in R$ per tonne (right), weekly. Sources: CFTC, ICE, USD/BRL, B3 ethanol.</p></div>`;
      chart('suSigC', { type: 'line', data: { labels: H.dates, datasets: [{ label: 'Managed money net, % OI', data: H.mm_pct_oi, borderColor: '#2c6fbb', pointRadius: 0, spanGaps: true, yAxisID: 'y' },
        { label: 'R$/t', data: H.brl_t, borderColor: '#d68910', pointRadius: 0, spanGaps: true, yAxisID: 'y1' }] }, options: { scales: { y1: { position: 'right', grid: { display: false } } } } });
    }).catch(() => { $('#suSig').innerHTML = ''; });
    getJSON('data/sugar/czapp_digest.json').then(Z => {
      if (!Z || !(Z.items || []).length || !$('#suCz')) return;
      $('#suCz').innerHTML = `<div class="card"><h2>Industry reading this week <span class="note">Czapp (Czarnikow) free insights, week to ${Z.week_ending}</span></h2>
        ${Z.themes && Z.themes.length ? `<ul>${Z.themes.map(t => `<li>${t}</li>`).join('')}</ul>` : ''}
        <div class="tbl"><table><tr><th class="l">Date</th><th class="l">Article</th><th class="l">What it says for sugar</th></tr>
        ${Z.items.map(i => `<tr><td class="l">${i.date}</td><td class="l"><a href="${i.url}" target="_blank" rel="noopener">${i.title}</a></td><td class="l">${i.takeaway}</td></tr>`).join('')}</table></div>
        <p class="note">Our own one-line reading of each free article; follow the link for the original. Updated weekly.</p></div>`;
    }).catch(() => {});
    Tech.mount($('#suTech'), ['SB']);
    try { MktStudy.upcoming($('#suSzUp'), ['SB'], () => $('#suTabs button[data-t="su-seas"]').click()); } catch (e) { /* no seasonal data yet */ }
    try { Intel.calendar($('#suCal'), { markets: ['SB'], days: 30, minImp: 1 }); } catch (e) { $('#suCal').innerHTML = '<p class="note">Calendar not available.</p>'; }
    try { Intel.news($('#suNews'), { tags: ['sugar'], n: 20, chips: false }); } catch (e) { $('#suNews').innerHTML = '<p class="note">No headlines.</p>'; }
  }
  return { show };
})();
