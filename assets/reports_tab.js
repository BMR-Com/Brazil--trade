// Reports tab (coffee, sugar) and the Spreads & arbs table.
// Reports: data/{coffee,sugar}/reports/*.json, short own-words key points per source (current crop / marketing year only).
// Spreads & arbs: data/markets/spread_tables.json built daily by models/softs_spread_tables.py from the desk's settlements.
const ReportsView = (() => {
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const lk = (u, t) => u ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t)}</a>` : esc(t);
  const dt = d => d ? new Date(d + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '–';
  const sg = (v, d = 1) => v == null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d);
  const SRC = { coffee: ['sucden', 'sucafina', 'stonex', 'cic_png', 'rabobank'], sugar: ['edfman', 'sucden_technicals'] };
  const get = (m, s) => getJSON(`data/${m}/reports/${s}.json`).catch(() => null);
  const entries = (E, n) => (E || []).slice(0, n).map(e => `<div style="margin:8px 0 10px"><div><b>${lk(e.url, e.title)}</b> <span class="note">· ${dt(e.date)}${e.tag ? ' · ' + esc(e.tag) : ''}</span></div>
      ${(e.key_points || []).length ? `<ul style="margin:4px 0 0 18px;padding:0">${e.key_points.map(p => `<li>${esc(p)}</li>`).join('')}</ul>` : ''}</div>`).join('');
  const head = (D, extra = '') => `<h2>${lk(D.home, D.name)}</h2><p class="note">Read ${esc(D.cadence)}. Showing ${D.window_start ? 'items from ' + dt(D.window_start) + ' (current crop / marketing year)' : 'latest items'}.${extra}</p>`;

  function sucden(D) {
    const L = D.latest || {};
    const order = ['world_production', 'world_consumption', 'world_balance', 'brazil_total', 'brazil_arabica', 'brazil_robusta', 'brazil_carryover', 'vietnam', 'colombia'];
    const dates = [...new Set((D.revisions || []).map(r => r.report_date))].sort().slice(-3);
    const keys = [...new Set((D.revisions || []).filter(r => dates.includes(r.report_date)).map(r => r.metric + '|' + r.season))]
      .sort((a, b) => order.indexOf(a.split('|')[0]) - order.indexOf(b.split('|')[0]) || a.localeCompare(b));
    const cell = (k, d) => { const r = D.revisions.find(x => x.metric + '|' + x.season === k && x.report_date === d); if (!r) return '<td class="n note">–</td>';
      const t = r.kind === 'revised' ? `<b>${r.new}</b> <span class="note">(${sg(r.change)})</span>` : r.kind === 'maintained' ? `${r.new} <span class="note">(held)</span>` : `${r.new} <span class="note">(first)</span>`;
      return `<td class="n" title="${esc(r.note || '')}">${t}${r.note ? ' *' : ''}</td>`; };
    return `<div class="card">${head(D)}
      <h3>Latest balance sheet: ${lk(L.url, L.title)} (${dt(L.date)})</h3>
      <div class="tbl"><table><tr><th class="l">Line</th><th class="l">Season / date</th><th class="l">Sucden figure</th></tr>
        ${(L.balance_lines || []).map(b => `<tr><td class="l">${esc(b.line)}</td><td class="l">${esc(b.season)}</td><td class="l">${esc(b.value)}</td></tr>`).join('')}</table></div>
      <p class="note">Headline figures as published by Sucden Financial (million 60-kg bags), with link; the balance line is implied from their production and consumption figures.</p>
      <h3>What they revised: last ${dates.length} reports</h3>
      <div class="tbl"><table><tr><th class="l">Line</th><th class="l">Season</th>${dates.map(d => `<th>${dt(d)}</th>`).join('')}</tr>
        ${keys.map(k => { const [m, s] = k.split('|'); const r = D.revisions.find(x => x.metric === m); return `<tr><td class="l">${esc(r.label)}</td><td class="l">${s}</td>${dates.map(d => cell(k, d)).join('')}</tr>`; }).join('')}</table></div>
      <p class="note">Change is against the same line in their previous report. * hover for the wording (ranges shown at the midpoint). Agencies' levels differ a lot; the desk follows each one's revisions.</p>
      <h3>Reports this crop year</h3>${entries(D.entries, 6)}</div>`;
  }

  function cic(D) {
    const E = D.entries || [], last = E.slice(0, 6);
    const grades = ['Brazil 3/4', 'Honduras HG', 'Colombia UGQ', 'Kenya AB FAQ', 'PNG Y1'];
    return `<div class="card">${head(D)}
      <h3>Differential indications, ¢/lb vs ICE NY (last ${last.length} reports)</h3>
      <div class="tbl"><table><tr><th class="l">Report</th>${grades.map(g => `<th>${g}</th>`).join('')}<th>KC 2nd pos. close</th></tr>
        ${last.map(e => `<tr><td class="l">${lk(e.url, dt(e.date))}</td>${grades.map(g => `<td class="n">${sg(e.diffs?.[g], 0)}</td>`).join('')}<td class="n">${e.kc_second ?? '–'}</td></tr>`).join('')}</table></div>
      <p class="note">${esc(D.caveat)} Ranges (Kenya) at the midpoint. Full history since Jan 2021: data/coffee/manual/png_diffs.csv.</p>
      <h3>Key points</h3>${entries(E.filter(e => (e.key_points || []).length), 4)}</div>`;
  }

  async function mount(el, market) {
    const L = await Promise.all(SRC[market].map(s => get(market, s)));
    const parts = SRC[market].map((s, i) => { const D = L[i]; if (!D) return '';
      if (s === 'sucden') return sucden(D);
      if (s === 'cic_png') return cic(D);
      return `<div class="card">${head(D, D.sugar_line ? ' Sugar: ' + esc(D.sugar_line) : '')}${D.note ? `<p class="note">${esc(D.note)}</p>` : ''}${entries(D.entries, 16) || '<p class="note">No items in the current window.</p>'}</div>`; });
    el.innerHTML = `<div class="card"><p class="note" style="margin:0">Short summaries in the desk's own words of free research from each source, current ${market === 'coffee' ? 'coffee crop year' : 'Centre-South season'} only, with links to the originals. Numbers are the publishers' and are attributed; nothing here is a recommendation.</p></div>`
      + parts.filter(Boolean).map(p => `<div style="margin-top:12px">${p}</div>`).join('');
  }
  return { mount };
})();

const SpreadTables = (() => {
  const sg = (v, d) => v == null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d);
  const pc = p => p == null ? '–' : `${ordn(p)}`;
  async function mount(el, market) {
    const S = await getJSON('data/markets/spread_tables.json').catch(() => null);
    const R = S?.[market];
    if (!R) { el.innerHTML = '<div class="card"><p class="note">Spreads &amp; arbs table not built yet.</p></div>'; return; }
    const groups = [...new Set(R.map(r => r.group))];
    const dp = r => r.unit === '$/t' ? 1 : 2;
    el.innerHTML = `<div class="card"><h2>Spreads &amp; arbs (settlement ${S.asof})</h2><div class="tbl"><table class="sa">
      <tr><th class="l">Line</th><th>Value</th><th>Unit</th><th>Day chg</th><th>% of deferred</th><th>1-yr pct</th><th>Ratio</th></tr>
      ${groups.map(g => `<tr><td class="l" colspan="7" style="background:#f4f6f8;font-weight:600">${g}</td></tr>` + R.filter(r => r.group === g).map(r => `<tr>
        <td class="l">${r.label}${r.date !== S.asof ? ` <span class="note">(${r.date})</span>` : ''}</td><td class="n"><b>${sg(r.value, dp(r)).replace(/^\+/, r.group.startsWith('Settle') ? '' : '+')}</b></td><td class="n">${r.unit}</td>
        <td class="n">${sg(r.chg, dp(r))}</td><td class="n">${r.pct_of_deferred == null ? '' : sg(r.pct_of_deferred, 2) + '%'}</td><td class="n">${r.pctile_1y == null ? '' : pc(r.pctile_1y)}</td>
        <td class="n">${r.ratio == null ? '' : r.ratio.toFixed(3) + (r.ratio_pctile_1y != null ? ` <span class="note">(${pc(r.ratio_pctile_1y)})</span>` : '')}</td></tr>`).join('')).join('')}
      </table></div><p class="note">${(S.notes || []).join(' ')}</p></div>`;
  }
  return { mount };
})();
