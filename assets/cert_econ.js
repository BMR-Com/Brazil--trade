// Cost to put up certs and the front spread into first notice: data/derived/cert_economics.json (models/cert_economics.py).
// certEcon('CT' | 'KC' | 'CC', element) fills the element; used by the cotton, coffee and cocoa certs tabs.
async function certEcon(sym, el) {
  if (!el) return;
  let J; try { J = await getJSON('data/derived/cert_economics.json'); } catch (e) { el.innerHTML = ''; return; }
  const M = J.markets[sym]; if (!M) { el.innerHTML = ''; return; }
  const C = M.cost, F = M.fnd, f0 = v => fmt(v, 0), f2 = v => fmt(v, 2);
  const kp = (lab, v, sub) => `<div class="kpi card" style="padding:10px"><div class="lbl">${lab}</div><div class="val" style="font-size:19px">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;
  const src = `<p class="note" style="margin-bottom:0"><b>Sources:</b> ${J.sources[sym].join('; ')}.</p>`;
  let cost = '';
  if (sym === 'CT' && C) {
    const S = C.spread, mc = C.median_components_c_bale;
    const rep = S ? (() => { const carry = -S.spread, gap = carry - C.stock_c_lb;
      return `<p class="read"><b>Replacement cost:</b> making a new cert costs about <b>${f2(C.stock_c_lb)}¢/lb</b> (${f2(C.stock_ex_loadout_c_lb)}¢ before the prepaid load-out) against ${S.pair} at <b>${sgn(S.spread, 2, '¢')}</b> on ${S.date}: the spread pays ${gap >= 0 ? f2(gap) + '¢ more than' : f2(-gap) + '¢ less than'} the cost of a new cert${S.spread > 0 ? ' (front at a premium)' : ''}. A receiver who stops certs and redelivers does not pay this cost again.</p>`; })() : '';
    cost = `<div class="card" style="margin-top:12px"><h2>Cost to put up certs <span class="note">ICE warehouse tariffs 2026-27, by warehouse</span></h2>
      <div class="grid g4">${kp('New certs, report of ' + C.report, f0(C.new_bales) + ' bales', `vs ${C.prev_report || '–'}; $${f0(C.new_usd)} to put up`)}
        ${kp('Weighted cost, new certs', f2(C.new_c_lb) + '¢/lb', '500 lb per bale')}
        ${kp('Whole stock', f0(C.stock_bales) + ' bales', `$${f0(C.stock_usd)}; ${f2(C.stock_c_lb)}¢/lb`)}
        ${kp('Range across warehouses', `${f2(C.range_c_lb[0])}–${f2(C.range_c_lb[1])}¢/lb`, `${f0(C.range_c_bale[0])}–${f0(C.range_c_bale[1])}¢ per bale`)}</div>
      ${rep}
      <div class="tbl"><table><tr><th class="l">Warehouse</th><th class="l">Point</th><th>Certs now</th><th>Change</th><th>New</th><th>¢/bale</th><th>¢/lb</th><th>$ spent on new</th></tr>
        ${C.rows.map(r => `<tr><td class="l">${r.warehouse}</td><td class="l">${r.point}</td><td class="n">${f0(r.bales)}</td><td class="n">${sgn(r.change, 0)}</td><td class="n">${r.new ? f0(r.new) : '–'}</td><td class="n">${f0(r.cost_c_bale)}</td><td class="n">${f2(r.cost_c_lb)}</td><td class="n">${r.new_usd ? f0(r.new_usd) : '–'}</td></tr>`).join('')}</table></div>
      <p class="note">Cost per bale (median warehouse): receiving, weighing and sampling ${f0(mc.receiving_weighing_sampling_c)}¢, ICE inspection ${f0(mc.exchange_inspection_c)}¢, USDA futures classing ${f0(mc.usda_classing_c)}¢ (on top of the grower classing every bale already pays), load-out ${f0(mc.load_out_c)}¢ (prepaid at certification): ${f0(mc.total_to_certificate_c)}¢. A Smith-Doxey request costs the same $2.00 as the ICE inspection: faster, not cheaper. Storage is extra (not included). New certs are the rise in each warehouse's certs since the previous report.</p>${src}</div>`;
  }
  if (sym === 'KC' && C) {
    const T = C.total, T3 = C.total_30d, tb = R => `<table><tr><th class="l">Port</th><th>Graded</th><th>Passed</th><th>Failed</th><th>Fee $</th><th>¢/lb graded</th><th>¢/lb per cert</th></tr>${R.map(r => `<tr><td class="l">${r.port}</td><td class="n">${f0(r.graded)}</td><td class="n">${f0(r.passed)}</td><td class="n">${f0(r.failed)}</td><td class="n">${f0(r.fee_usd)}</td><td class="n">${f2(r.c_lb_graded)}</td><td class="n">${f2(r.c_lb_passed)}</td></tr>`).join('')}</table>`;
    cost = `<div class="card" style="margin-top:12px"><h2>Cost to put up certs <span class="note">ICE grading fee, by port</span></h2>
      <div class="grid g4">${kp('ICE grading fee', '$' + f2(C.fee_usd_bag) + '/bag', `${f2(C.c_lb_60kg)}¢/lb on a 60-kg bag; min $${f0(C.min_usd_receipt)} per receipt`)}
        ${kp('Graded on ' + C.date, f0(T.graded) + ' bags', `$${f0(T.fee_usd)}; ${f0(T.passed)} passed`)}
        ${kp('Cost per new cert, ' + C.date, f2(T.c_lb_passed) + '¢/lb', 'fees on passed and failed bags, per bag that passed')}
        ${kp('Last 30 days', f0(T3.graded) + ' bags graded', `$${f0(T3.fee_usd)}; ${f2(T3.c_lb_passed)}¢/lb per new cert`)}</div>
      <div class="grid g2" style="margin-top:8px"><div class="tbl"><h3>Report of ${C.date}</h3>${tb(C.rows)}</div><div class="tbl"><h3>Since ${C.d30_from}</h3>${tb(C.rows_30d)}</div></div>
      <p class="note">Failed bags pay the fee too, so the cost per bag that becomes a cert rises as the pass rate falls. The $${f0(C.min_usd_receipt)} minimum only matters for receipts under ${C.min_binds_below_bags} bags. Refunds: $0.70/bag if cancelled before grading, $0.50/bag if an appeal changes the result. ICE's published coffee storage and handling rates list storage, load-out and rebagging only; warehouse in-charges (receiving, sampling) are not published, so the cost shown is the grading fee alone. Grading results are reported by port, not by warehouse.</p>${src}</div>`;
  }
  if (sym === 'CC' && C) {
    const T = C.total, T12 = C.total_12m, ML = m => MON[+m.slice(5) - 1] + ' ' + m.slice(0, 4);
    const tb = R => `<table><tr><th class="l">Port</th><th class="l">Grading</th><th>Lots</th><th>Tonnes</th><th>Fee per lot $</th><th>Fee $</th><th>$/t</th></tr>${R.map(r => `<tr><td class="l">${r.port}</td><td class="l">${r.type}</td><td class="n">${f0(r.lots)}</td><td class="n">${f0(r.tonnes)}</td><td class="n">${f0(r.fee_per_lot)}</td><td class="n">${f0(r.fee_usd)}</td><td class="n">${f2(r.usd_t)}</td></tr>`).join('')}</table>`;
    cost = `<div class="card" style="margin-top:12px"><h2>Cost to put up certs <span class="note">ICE grading fee, by port</span></h2>
      <div class="grid g4">${kp('ICE grading fee', '$' + C.fee_table.map(x => f0(x.usd_per_sample)).join(' / '), C.fee_table.map(x => (x.chops_min === x.chops_max ? x.chops_min : x.chops_min + '–' + x.chops_max)).join(' / ') + ' chops per sample; one sample per 10-t lot')}
        ${kp('Graded in ' + ML(C.month), f0(T.tonnes) + ' t', `${f0(T.lots)} lots; $${f0(T.fee_usd)}`)}
        ${kp('Cost per tonne', '$' + f2(T.usd_t) + '/t', 'first gradings and regrades')}
        ${kp('Last 12 months', f0(T12.tonnes) + ' t', `$${f0(T12.fee_usd)}; $${f2(T12.usd_t)}/t (from ${ML(C.from_12m)})`)}</div>
      <div class="grid g2" style="margin-top:8px"><div class="tbl"><h3>${ML(C.month)}</h3>${tb(C.rows)}</div><div class="tbl"><h3>Last 12 months</h3>${tb(C.rows_12m)}</div></div>
      <p class="note">A grade covers one or two delivery periods (Rule 9.18), so a cert held longer pays the fee again at each regrade (about $${f0(C.min_usd_t)}/t a time). No ICE cocoa warehouse handling-rate sheet was found, so the cost shown is the grading fee alone.</p>${src}</div>`;
  }
  const u = F.unit, dp = u === '$/t' ? 0 : 2, cu = F.cert_unit, gcol = sym === 'CC';
  const cur = F.current;
  let read = '';
  if (cur) read = cur.opened
    ? `<b>${cur.pair}</b> (first notice ${cur.fnd}): ${sgn(cur.spread, dp, u === '$/t' ? ' $/t' : '¢')} on ${cur.date}, ${sgn(cur.chg, dp, u === '$/t' ? ' $/t' : '¢')} since ${cur.start} (${cur.chg < 0 ? 'toward wider carry' : cur.chg > 0 ? 'toward the front' : 'unchanged'})${cur.cert_chg != null ? `; certs ${sgn(cur.cert_chg, 0)} ${cu} ${cur.cert_from ? 'from ' + cur.cert_from : 'since ' + cur.start} to ${cur.cert_to}` : ''}.`
    : `<b>${cur.pair}</b>: first notice ${cur.fnd}; the month before it starts ${cur.start}. Spread now ${sgn(cur.spread, dp, u === '$/t' ? ' $/t' : '¢')} (${cur.date}).`;
  const fnd = `<div class="card" style="margin-top:12px"><h2>Front spread into first notice <span class="note">front minus next, ${u}; negative = carry</span></h2>
    <p class="read">${read}</p>
    <div class="tbl"><table><tr><th class="l">Spread</th><th class="l">First notice</th><th>1 month before</th><th>At first notice</th><th>Change</th><th>Certs change, ${cu}</th>${gcol ? '<th>First gradings, t</th>' : ''}</tr>
      ${F.rows.map(r => `<tr><td class="l">${r.pair}</td><td class="l">${r.fnd}</td><td class="n">${fmt(r.s_start, dp)}</td><td class="n">${fmt(r.s_fnd, dp)}</td><td class="n">${sgn(r.chg, dp)}</td><td class="n">${r.cert_chg == null ? '–' : sgn(r.cert_chg, 0)}</td>${gcol ? `<td class="n">${r.gradings == null ? '–' : f0(r.gradings)}</td>` : ''}</tr>`).join('')}</table></div>
    <p class="note">"1 month before" is ${F.window_days} trading days before first notice.${sym === 'CT' ? ' Old-crop months only (Dec, Mar, May, Jul; October skipped).' : ''} – = no certs data for that window on the desk. Built ${J.built}.</p></div>`;
  el.innerHTML = cost + fnd;
}
