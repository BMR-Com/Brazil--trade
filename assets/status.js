// Data status: each source the desk uses, its latest data date, cadence and a late flag (data/status.json, pipelines/data_status.py).
const Status = (() => {
  let S = null;
  const load = async () => S || (S = await getJSON('data/status.json?' + Date.now()).catch(() => null));
  async function show() {
    const el = $('#status'), D = await load();
    if (!D) { el.innerHTML = '<main><div class="card"><p class="note">Data status loads after the first status run.</p></div></main>'; return; }
    const late = D.sources.filter(r => r.state !== 'ok'), grp = [...new Set(D.sources.map(r => r.group))];
    const chip = r => r.state === 'ok' ? '<b class="up">OK</b>' : r.state === 'late' ? '<b class="dn">LATE</b>' : r.state === 'check' ? '<b class="dn">CHECK</b>' : '<b class="dn">MISSING</b>';
    const esc = x => String(x == null ? '' : x).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
    el.innerHTML = `<main><div class="card"><h2>Data status <span class="note">checked ${D.generated}</span></h2>
      <p class="read">${late.length ? `<b class="dn">${late.length} of ${D.sources.length} sources are late:</b> ${late.map(r => r.source).join('; ')}. Numbers built on them may be out of date.` : `<b class="up">All ${D.sources.length} sources are current.</b>`}</p>
      <div class="tbl"><table><tr><th class="l">Source</th><th>Latest data</th><th>Age</th><th class="l">Cadence</th><th>Late after</th><th>Status</th><th class="l">Feed</th><th class="l">Used in</th></tr>
      ${grp.map(g => `<tr><td class="l" colspan="8"><b>${g}</b></td></tr>` + D.sources.filter(r => r.group === g).map(r => `<tr style="${r.state !== 'ok' ? 'background:rgba(192,57,43,.08)' : ''}"><td class="l">${r.source}</td><td class="n">${r.latest || '–'}</td><td class="n">${r.age == null ? '–' : r.age + ' ' + (r.age_unit === 'days' ? 'd' : 'bd')}</td><td class="l">${r.cadence}</td><td class="n">${r.limit} ${r.age_unit === 'days' ? 'd' : 'bd'}</td><td>${chip(r)}</td><td class="l note">${r.manual ? 'manual upload' : 'automatic'}</td><td class="l note">${r.used_in}</td></tr>`).join('')).join('')}</table></div>
      <p class="note">Age in business days (bd) for daily sources, calendar days (d) for the rest. Weekly reports carry their own reference date: COT is Tuesday's positions, on-call Friday's, export sales the week ending Thursday, so their limits are longer. Manual uploads go in via the repo (ICE certs, EWR, CFR quotes, ICE options files).</p></div></main>`;
    history.replaceState(null, '', '#status');
  }
  // one-line strip for the footer of every page
  async function strip(el) {
    const D = await load(); if (!D || !el) return;
    const late = D.sources.filter(r => r.state !== 'ok');
    el.innerHTML = late.length ? `<a href="#status" class="dn" data-status>Data status: ${late.length} source${late.length > 1 ? 's' : ''} late (${late.slice(0, 3).map(r => r.source.replace(/ \(.*\)$/, '')).join(', ')}${late.length > 3 ? ', …' : ''})</a>` : `<a href="#status" data-status>Data status: all sources current</a>`;
    el.querySelector('[data-status]').onclick = e => { e.preventDefault(); $('nav.comm button[data-c="status"]').click(); };
  }
  return { show, strip };
})();
