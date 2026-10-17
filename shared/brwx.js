/* Brazil weather, ENSO and USDA-report panel shared by the coffee, sugar and cotton pages.
   Usage: <div id="brwx" data-crop="coffee"></div><script src=".../shared/brwx.js"></script>
   Data: weather/data/br_weather.json (daily, Open-Meteo + NOAA CPC) and usda/reports.json (updated weekly). */
(function () {
  var BASE = 'https://bmr-com.github.io/Brazil--trade/';
  var el = document.getElementById('brwx');
  if (!el) return;
  var crop = el.getAttribute('data-crop') || 'coffee';
  var C = { s1: '#a8892a', s2: '#3a9cc0', s3: '#e0605a', hist: '#8a8d9e' };
  var css = document.createElement('style');
  css.textContent = '#brwx .bx-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}' +
    '#brwx .bx-card{border:1px solid rgba(128,128,128,.28);border-radius:10px;padding:16px;overflow:auto}' +
    '#brwx .bx-t{font-size:13px;font-weight:700;margin-bottom:3px}#brwx .bx-s{font-size:11px;opacity:.7;margin-bottom:12px;line-height:1.45}' +
    '#brwx table{width:100%;border-collapse:collapse;font-size:12px}#brwx th{font-size:10px;text-transform:uppercase;letter-spacing:.8px;opacity:.7;text-align:left;padding:6px 8px;border-bottom:1px solid rgba(128,128,128,.3);white-space:nowrap}' +
    '#brwx td{padding:6px 8px;border-bottom:1px solid rgba(128,128,128,.15)}#brwx td.r,#brwx th.r{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}' +
    '#brwx .dry{color:#e0605a;font-weight:600}#brwx .wet{color:#3a9cc0;font-weight:600}#brwx .hot{color:#e0605a}' +
    '#brwx .bx-enso{display:flex;flex-wrap:wrap;gap:18px;font-size:12.5px;margin-bottom:14px}#brwx .bx-enso b{font-size:18px}' +
    '#brwx .bx-rep{border-left:3px solid #a8892a;padding:8px 12px;margin:10px 0;font-size:12.5px;line-height:1.5}#brwx .bx-rep a{color:inherit}' +
    '#brwx .bx-wrap{position:relative;height:280px}@media(max-width:900px){#brwx .bx-grid{grid-template-columns:1fr}}';
  document.head.appendChild(css);
  var f = function (v, d) { return v == null || isNaN(v) ? '—' : (+v).toLocaleString('en-US', { minimumFractionDigits: d || 0, maximumFractionDigits: d || 0 }); };
  var pc = function (p) { if (p == null) return '—'; var cls = p < 75 ? 'dry' : p > 125 ? 'wet' : ''; return '<span class="' + cls + '">' + f(p) + '%</span>'; };
  var TITLES = { coffee: 'Brazil coffee belt — rainfall, heat and El Niño', sugar: 'Brazil Centre-South cane — rainfall, heat and El Niño', cotton: 'Brazil cotton (Mato Grosso, Bahia, Goiás) — rainfall, heat and El Niño' };
  var NOTES = {
    coffee: 'Flowering runs from September to November: arabica needs a dry spell then steady rain to set an even bloom; irregular rain or heat above ~34°C causes uneven flowering and flower abortion (USDA BR2026-0040).',
    sugar: 'The Centre-South crush runs April–November; rain in the dry winter slows crushing and lowers ATR, while summer dryness and heat cut cane growth for next season (USDA BR2026-0040).',
    cotton: 'Most Brazilian cotton is a second crop planted after soybeans from January; late soybean planting from irregular spring rain shortens the cotton window, and heat with low soil moisture cuts yields (USDA BR2026-0040).'
  };
  Promise.all([fetch(BASE + 'weather/data/br_weather.json?' + Date.now()).then(function (r) { return r.json(); }).catch(function () { return null; }),
               fetch(BASE + 'usda/reports.json?' + Date.now()).then(function (r) { return r.json(); }).catch(function () { return []; })])
    .then(function (res) { render(res[0], res[1] || []); });

  function render(W, R) {
    var h = '<div class="bx-card" style="margin-bottom:16px"><div class="bx-t">' + TITLES[crop] + '</div><div class="bx-s">' + NOTES[crop] + '</div>';
    if (W && W.enso) {
      var wk = (W.enso.weekly || []).slice(-1)[0], oni = (W.enso.oni || []).slice(-1)[0];
      h += '<div class="bx-enso">' + (wk ? '<div>Niño 3.4 weekly anomaly<br><b>' + (wk.nino34 > 0 ? '+' : '') + f(wk.nino34, 1) + '°C</b> <span style="opacity:.7">week of ' + wk.week + '</span></div>' : '') +
        (oni ? '<div>ONI (' + oni.season + ' ' + oni.year + ')<br><b>' + (oni.anom > 0 ? '+' : '') + f(oni.anom, 1) + '°C</b> <span style="opacity:.7">' + (oni.anom >= 1.5 ? 'strong El Niño' : oni.anom >= 0.5 ? 'El Niño' : oni.anom <= -0.5 ? 'La Niña' : 'neutral') + '</span></div>' : '') +
        (W.mg_index && crop === 'coffee' ? '<div>Minas Gerais coffee belt, last 30 days<br><b>' + f(W.mg_index.d30.rain) + ' mm</b> <span style="opacity:.7">' + f(W.mg_index.d30.pct_normal) + '% of normal · next 16 days ' + f(W.mg_index.fc16.rain) + ' mm vs ' + f(W.mg_index.fc16.normal) + ' normal</span></div>' : '') +
        '</div>';
    }
    h += '</div>';
    if (W) {
      var rows = W.regions.filter(function (r) { return r.crop === crop; });
      h += '<div class="bx-grid"><div class="bx-card"><div class="bx-t">Rainfall vs 1991–2020 normal, by region</div><div class="bx-s">ERA5 reanalysis and 16-day model forecast via Open-Meteo, as of ' + (rows[0] ? rows[0].asof : '') + '. Red under 75% of normal, blue over 125%. Hot days = max ≥34°C. Not station data — Somar and INMET station readings can differ locally.</div><table><thead><tr><th>Region · town</th><th class="r">7d mm</th><th class="r">30d % norm</th><th class="r">90d % norm</th><th class="r">Hot days 30d</th><th class="r">Next 16d mm</th><th class="r">vs norm</th></tr></thead><tbody>' +
        rows.map(function (r) {
          var fc = r.fc16 || {};
          return '<tr><td>' + r.region + ' · ' + r.town + '</td><td class="r">' + f(r.d7.rain) + '</td><td class="r">' + pc(r.d30.pct_normal) + '</td><td class="r">' + pc(r.d90.pct_normal) +
            '</td><td class="r ' + (r.d30.hot_days >= 5 ? 'hot' : '') + '">' + r.d30.hot_days + '</td><td class="r">' + f(fc.rain) + '</td><td class="r">' + pc(fc.normal ? fc.rain / fc.normal * 100 : null) + '</td></tr>';
        }).join('') + '</tbody></table></div>';
      h += '<div class="bx-card"><div class="bx-t">Cumulative rain since 1 September</div><div class="bx-s">' + (crop === 'coffee' ? 'Minas Gerais coffee belt, regions weighted by approximate Conab output shares (Sul de Minas 50%, Cerrado 25%, Matas 22%, Norte 3%)' : 'Average of the regions in the table') + ', mm</div><div class="bx-wrap"><canvas id="bxSeason"></canvas></div></div></div>';
    }
    var reps = R.filter(function (r) { return (r.commodities || []).indexOf(crop) >= 0; }).sort(function (a, b) { return b.date.localeCompare(a.date); }).slice(0, 6);
    if (reps.length) {
      h += '<div class="bx-card"><div class="bx-t">USDA reports — what they mean for ' + crop + '</div><div class="bx-s">FAS attaché (GAIN) reports and USDA outlooks, checked every Friday</div>' +
        reps.map(function (r) {
          return '<div class="bx-rep"><b><a href="' + r.url + '" target="_blank" rel="noopener">' + r.title + '</a></b> <span style="opacity:.7">· ' + (r.post ? r.post + ' · ' : '') + r.date + '</span><br>' +
            (r.impact && r.impact[crop] ? '<b>Impact:</b> ' + r.impact[crop] + '<br>' : '') + '<span style="opacity:.8">' + (r.summary || '') + '</span></div>';
        }).join('') + '</div>';
    }
    el.innerHTML = h;
    if (W && window.Chart) {
      var S;
      if (crop === 'coffee' && W.mg_index) S = W.mg_index.season;
      else {
        var rs = W.regions.filter(function (r) { return r.crop === crop; });
        var avg = function (k) { var n = Math.min.apply(null, rs.map(function (r) { return r.season[k].length || 0; })); var o = []; for (var i = 0; i < n; i++) { var s = 0; rs.forEach(function (r) { s += r.season[k][i]; }); o.push(+(s / rs.length).toFixed(1)); } return o; };
        S = { start: rs[0].season.start, cur: avg('cur'), prev: avg('prev'), normal: avg('normal') };
      }
      var n = Math.max(S.normal.length, S.prev.length), start = new Date(S.start + 'T00:00:00'), lab = [];
      for (var i = 0; i < n; i++) { var d = new Date(start.getTime() + i * 864e5); lab.push(d.toISOString().slice(5, 10)); }
      var L = function (l, d, c, o) { var x = { label: l, data: d, borderColor: c, backgroundColor: c, borderWidth: 2, pointRadius: 0, tension: 0 }; for (var k in o) x[k] = o[k]; return x; };
      new Chart(document.getElementById('bxSeason'), { type: 'line', data: { labels: lab, datasets: [L('This season', S.cur, C.s1, { borderWidth: 2.5 }), L('Last season', S.prev, C.s2, {}), L('1991–2020 normal', S.normal, C.hist, { borderDash: [5, 4] })] },
        options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { display: true, labels: { boxWidth: 14, boxHeight: 2 } } }, scales: { x: { ticks: { maxTicksLimit: 8 } }, y: { title: { display: true, text: 'mm' } } } } });
    }
  }
})();
