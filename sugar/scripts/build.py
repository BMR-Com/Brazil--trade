"""Build sugar/data/sugar.json for the Sugar tab from the fetched data files."""
import os, json, math
from datetime import date, timedelta
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.environ.get("SUGAR_DATA", os.path.join(ROOT, "data"))
REPO = os.path.abspath(os.path.join(ROOT, ".."))
TRADE = os.environ.get("TRADE_DATA", os.path.join(REPO, "data"))

LB_T = 22.0462                      # lb per tonne / 100
ATR = {"sugar": 1.0495, "anh": 1.7651, "hyd": 1.6913}   # kg ATR per kg sugar / per litre ethanol (CONSECANA)
POL = 0.0405                        # VHP polarisation premium over the 96° NY11 basis
LOGISTICS_BRL = 190.0               # mill -> FOB Santos (freight + elevation), R$/t — default, editable on the page


def rd(x, n=2):
    if x is None:
        return None
    try:
        if isinstance(x, (float, np.floating)) and (math.isnan(x) or math.isinf(x)):
            return None
    except Exception:
        pass
    return round(float(x), n)


def ser(s, n=2):
    return [[str(k)[:10], rd(v, n)] for k, v in s.items() if v is not None and not (isinstance(v, float) and math.isnan(v))]


def read(name, **kw):
    p = os.path.join(DATA, name)
    return pd.read_csv(p, **kw) if os.path.exists(p) else None


# ---------------------------------------------------------------- crush (MAPA)
def crush():
    d = read("mapa_fortnight.csv", parse_dates=["start", "end"])
    if d is None:
        return None
    cs = d[(d.region == "Centro-Sul") & (d.uf == "TOTAL")].copy()
    cs = cs.drop_duplicates(["safra", "end"], keep="last").sort_values("end")
    cs["y0"] = cs.safra.str[:4].astype(int)
    cs["day"] = (cs["end"] - pd.to_datetime(cs.y0.astype(str) + "-04-01")).dt.days + 1
    # fortnight index 1..24: ends on the 15th or month-end
    cs["fn"] = ((cs["end"].dt.month - 4) % 12) * 2 + np.where(cs["end"].dt.day <= 16, 1, 2)
    cs = cs[(cs.day > 0) & (cs.day <= 366)]
    cs = cs.drop_duplicates(["safra", "fn"], keep="last")
    seasons = sorted(cs.safra.unique())
    cur = seasons[-1]
    out = {"seasons": {}, "current": cur}
    finals = {}
    for s in seasons:
        g = cs[cs.safra == s].set_index("fn").sort_index()
        inc = g[["cane_t", "sugar_t", "ethanol_m3", "anh_prod", "hyd_prod"]].diff()
        inc.iloc[0] = g[["cane_t", "sugar_t", "ethanol_m3", "anh_prod", "hyd_prod"]].iloc[0]
        rec = {"fn": g.index.tolist(), "end": [str(x)[:10] for x in g["end"]],
               "cane": [rd(x / 1e6, 3) for x in g.cane_t], "sugar": [rd(x / 1e6, 3) for x in g.sugar_t],
               "ethanol": [rd(x / 1e6, 3) for x in g.ethanol_m3],
               "hyd_stock": [rd(x / 1e6, 3) for x in g.hyd_stock], "anh_stock": [rd(x / 1e6, 3) for x in g.anh_stock],
               "cane_fn": [rd(x / 1e6, 3) for x in inc.cane_t], "sugar_fn": [rd(x / 1e6, 3) for x in inc.sugar_t],
               "ethanol_fn": [rd(x / 1e6, 3) for x in inc.ethanol_m3],
               "kgt": [rd(a / b * 1000, 2) if b else None for a, b in zip(g.sugar_t, g.cane_t)],
               "kgt_fn": [rd(a / b * 1000, 2) if b and b > 2e6 else None for a, b in zip(inc.sugar_t, inc.cane_t)],
               "lt_fn": [rd(a / b * 1000, 2) if b and b > 2e6 else None for a, b in zip(inc.ethanol_m3 * 1000, inc.cane_t)]}
        out["seasons"][s] = rec
        if 24 in g.index and s != cur:
            finals[s] = g.loc[24, ["cane_t", "sugar_t", "ethanol_m3"]].to_dict()
    # Season projection. For each finished season s: remaining_s = final_s - cum_s(n), scaled by the ratio of the
    # current season's last-4-fortnight crush to season s over the same fortnights; sugar uses the season's
    # rest-of-season kg/t relative to the same 4-fortnight window, applied to the current kg/t.
    g = cs[cs.safra == cur].set_index("fn").sort_index()
    n = int(g.index.max())
    proj = {"fn": n, "end": str(g["end"].iloc[-1])[:10], "history": [], "by_season": []}
    hist = [s for s in finals if s >= "2015/2016"]
    w0 = max(n - 4, 0)
    def win(gg, col):
        a_ = gg[col].get(n, np.nan); b_ = gg[col].get(w0, 0.0) if w0 else 0.0
        return a_ - b_
    cane_w, sug_w, eth_w = win(g, "cane_t"), win(g, "sugar_t"), win(g, "ethanol_m3")
    kgt_now = sug_w / cane_w
    lt_now = eth_w / cane_w
    pc, ps, pe = [], [], []
    for s in hist:
        h = cs[cs.safra == s].set_index("fn").sort_index()
        if n not in h.index or (w0 and w0 not in h.index):
            continue
        r = cane_w / win(h, "cane_t")
        rem_c = finals[s]["cane_t"] - h.loc[n, "cane_t"]
        rem_s = finals[s]["sugar_t"] - h.loc[n, "sugar_t"]
        rem_e = finals[s]["ethanol_m3"] - h.loc[n, "ethanol_m3"]
        kgt_rest = rem_s / rem_c if rem_c > 1e6 else np.nan
        kgt_win = win(h, "sugar_t") / win(h, "cane_t")
        lt_rest = rem_e / rem_c if rem_c > 1e6 else np.nan
        lt_win = win(h, "ethanol_m3") / win(h, "cane_t")
        c_ = g.loc[n, "cane_t"] + r * rem_c
        s_ = g.loc[n, "sugar_t"] + r * rem_c * kgt_now * (kgt_rest / kgt_win if kgt_win and not np.isnan(kgt_rest) else 1.0)
        e_ = g.loc[n, "ethanol_m3"] + r * rem_c * lt_now * (lt_rest / lt_win if lt_win and not np.isnan(lt_rest) else 1.0)
        pc.append(c_); ps.append(s_); pe.append(e_)
        proj["by_season"].append({"safra": s, "pace_ratio": rd(r, 2), "cane": rd(c_ / 1e6, 1), "sugar": rd(s_ / 1e6, 2), "ethanol": rd(e_ / 1e6, 2)})
    for key, arr, col in [("cane", pc, "cane_t"), ("sugar", ps, "sugar_t"), ("ethanol", pe, "ethanol_m3")]:
        if not arr:
            continue
        a_ = np.array(arr) / 1e6
        proj[key] = {"now": rd(g.loc[n, col] / 1e6, 2), "mid": rd(np.median(a_), 2), "lo": rd(np.percentile(a_, 25), 2),
                     "hi": rd(np.percentile(a_, 75), 2), "min": rd(a_.min(), 2), "max": rd(a_.max(), 2), "n": len(a_)}
    proj["kgt_window"] = rd(kgt_now * 1000, 1)
    for s in hist:
        proj["history"].append({"safra": s, "cane": rd(finals[s]["cane_t"] / 1e6, 1), "sugar": rd(finals[s]["sugar_t"] / 1e6, 2),
                                "ethanol": rd(finals[s]["ethanol_m3"] / 1e6, 2)})
    out["projection"] = proj
    # same-date comparison table
    comp = []
    for s in seasons[-6:]:
        h = cs[(cs.safra == s) & (cs.fn == n)]
        if len(h):
            r = h.iloc[0]
            comp.append({"safra": s, "cane": rd(r.cane_t / 1e6, 1), "sugar": rd(r.sugar_t / 1e6, 2), "ethanol": rd(r.ethanol_m3 / 1e6, 2),
                         "kgt": rd(r.sugar_t / r.cane_t * 1000, 1), "hyd_stock": rd(r.hyd_stock / 1e6, 2)})
    out["same_date"] = comp
    # states: current season cumulative by UF vs last season same date
    st = d[(d.region == "Centro-Sul") & (d.uf != "TOTAL")]
    a = st[(st.safra == cur) & (st["end"] == g["end"].iloc[-1])]
    prev = seasons[-2] if len(seasons) > 1 else None
    pe = cs[(cs.safra == prev) & (cs.fn == n)]["end"]
    b = st[(st.safra == prev) & (st["end"] == pe.iloc[0])] if prev and len(pe) else st.iloc[0:0]
    out["states"] = []
    for uf in a.sort_values("cane_t", ascending=False).uf:
        x = a[a.uf == uf].iloc[0]
        y = b[b.uf == uf].iloc[0] if (b.uf == uf).any() else None
        out["states"].append({"uf": uf, "cane": rd(x.cane_t / 1e6, 2), "sugar": rd(x.sugar_t / 1e6, 3),
                              "cane_prev": rd(y.cane_t / 1e6, 2) if y is not None else None,
                              "sugar_prev": rd(y.sugar_t / 1e6, 3) if y is not None else None})
    return out, cs


# ---------------------------------------------------------------- UNICA (official mix, ATR, corn ethanol)
def unica_block(cs):
    u = read("unica_reports.csv")
    if u is None or u.empty:
        return None
    pos = u.position.max()
    u = u[u.position == pos]
    acc = u[(u.table == "accumulated") & (u.region == "CS")].pivot_table(index="metric", columns="season", values="value")
    mon = u[(u.table == "monthly") & (u.region == "CS")]
    month = mon.month.dropna().iloc[0] if len(mon) else None
    mon = mon.pivot_table(index="metric", columns="season", values="value")
    corn = u[u.table == "corn"].pivot_table(index="month", columns="metric", values="value").sort_index()
    blk = {"position": pos, "month": month, "seasons": list(acc.columns),
           "accumulated": {m: [rd(v, 2) for v in acc.loc[m].tolist()] for m in acc.index},
           "monthly": {m: [rd(v, 2) for v in mon.loc[m].tolist()] for m in mon.index},
           "corn": {"fortnight": corn.index.tolist(), "total_fn": [rd(v, 1) for v in corn.get("corn_total_fn", [])],
                    "anh_fn": [rd(v, 1) for v in corn.get("corn_anh_fn", [])], "hyd_fn": [rd(v, 1) for v in corn.get("corn_hyd_fn", [])]}}
    # implied fortnightly mix for the current MAPA season (cane ethanol = MAPA ethanol − UNICA corn ethanol)
    cur = cs.safra.max()
    g = cs[cs.safra == cur].sort_values("fn")
    inc = g[["sugar_t", "anh_prod", "hyd_prod"]].diff(); inc.iloc[0] = g[["sugar_t", "anh_prod", "hyd_prod"]].iloc[0]
    ca = {}
    if len(corn):
        for k, r in corn.iterrows():
            e = (pd.to_datetime(k) - timedelta(days=1)).date()
            ca[str(e)] = (r.get("corn_anh_fn", np.nan), r.get("corn_hyd_fn", np.nan))
    last = list(ca.values())[-4:] if ca else []
    avg = (np.nanmean([x[0] for x in last]), np.nanmean([x[1] for x in last])) if last else (0.0, 0.0)
    mix = []
    for (_, r), (_, i) in zip(g.iterrows(), inc.iterrows()):
        e = str(r["end"])[:10]
        c = ca.get(e)
        est = c is None
        c = c or avg
        anh = max(i.anh_prod - c[0] * 1000, 0) if not np.isnan(c[0]) else i.anh_prod
        hyd = max(i.hyd_prod - c[1] * 1000, 0) if not np.isnan(c[1]) else i.hyd_prod
        s_atr = i.sugar_t * ATR["sugar"]
        e_atr = anh * ATR["anh"] + hyd * ATR["hyd"]          # m3 * kg/L = t
        mix.append({"end": e, "mix": rd(100 * s_atr / (s_atr + e_atr), 1) if s_atr + e_atr > 0 else None, "corn_est": est})
    blk["implied_mix"] = mix
    return blk


# ---------------------------------------------------------------- prices, parity, white premium
def prices():
    p = read("prices_cont.csv")
    if p is None:
        return None, None
    p["date"] = pd.to_datetime(p["date"])
    w = p.pivot_table(index="date", columns="symbol", values="close").sort_index()
    w.columns = [c.split(":")[1] for c in w.columns]
    w = w.ffill(limit=5)
    snap = {}
    last = w.index.max()
    for c in w.columns:
        s = w[c].dropna()
        if s.empty:
            continue
        v = s.iloc[-1]
        def chg(days):
            t = s[s.index <= s.index[-1] - timedelta(days=days)]
            return rd((v / t.iloc[-1] - 1) * 100, 1) if len(t) else None
        ytd = s[s.index < pd.Timestamp(s.index[-1].year, 1, 1)]
        snap[c] = {"last": rd(v, 4), "date": str(s.index[-1])[:10], "w1": chg(7), "m1": chg(30),
                   "ytd": rd((v / ytd.iloc[-1] - 1) * 100, 1) if len(ytd) else None}
    # daily parity inputs (page recomputes with editable constants)
    q = w[["ETH1!", "USDBRL", "SB1!", "W1!"]].dropna()
    q = q[q.index >= "2012-01-01"]
    par = (q["ETH1!"] * ATR["sugar"] * 1000 / (ATR["hyd"] * 1000) + LOGISTICS_BRL) / q["USDBRL"] / LB_T / (1 + POL)
    parity = {"dates": [str(x)[:10] for x in q.index], "eth": [rd(x, 1) for x in q["ETH1!"]], "fx": [rd(x, 4) for x in q["USDBRL"]],
              "sb": [rd(x, 2) for x in q["SB1!"]], "par": [rd(x, 2) for x in par]}
    prem = (par - q["SB1!"])
    parity["now"] = {"date": str(q.index[-1])[:10], "eth": rd(q["ETH1!"].iloc[-1], 1), "fx": rd(q["USDBRL"].iloc[-1], 4),
                     "sb": rd(q["SB1!"].iloc[-1], 2), "parity": rd(par.iloc[-1], 2), "eth_minus_sugar": rd(prem.iloc[-1], 2),
                     "pct_rank_5y": rd((prem[prem.index >= prem.index[-1] - timedelta(days=5 * 365)] <= prem.iloc[-1]).mean() * 100, 0)}
    # Brent / gasoline context for the ethanol side
    ctx = w[["BRN1!", "USDBRL"]].dropna()
    ctx = ctx[ctx.index >= "2018-01-01"].resample("W-FRI").last()
    parity["brent_brl"] = {"dates": [str(x)[:10] for x in ctx.index], "v": [rd(a * b, 1) for a, b in zip(ctx["BRN1!"], ctx["USDBRL"])]}
    return snap, parity


MON = {"H": 3, "K": 5, "N": 7, "Q": 8, "V": 10, "Z": 12}


def white_premium():
    c = read("prices_contracts.csv")
    if c is None or c.empty:
        return None
    c["date"] = pd.to_datetime(c["date"])
    px = {s: g.set_index("date").close.sort_index() for s, g in c.groupby("symbol")}
    pairs = []
    for s in px:
        if not s.startswith("W") or s.startswith("WZ") is None:
            continue
        m, y = s[1], int(s[2:])
        raw = {"H": f"SBH{y}", "K": f"SBK{y}", "Q": f"SBN{y}", "V": f"SBV{y}", "Z": f"SBH{y + 1}"}.get(m)
        if raw not in px:
            continue
        a, b = px[s], px[raw]
        j = pd.concat([a, b], axis=1, keys=["w", "r"], sort=True).dropna()
        if len(j) < 20:
            continue
        j["prem"] = j.w - j.r * LB_T
        nominal = pd.Timestamp(y, {"H": 2, "K": 4, "Q": 7, "V": 9, "Z": 11}[m], 16)
        pairs.append({"white": s, "raw": raw, "mon": m, "year": y, "expiry": min(j.index.max(), nominal), "nominal": nominal, "s": j})
    if not pairs:
        return None
    today = max(p["expiry"] for p in pairs)
    pairs.sort(key=lambda p: p["nominal"])
    # front pair series: on each date use the pair whose white contract expires next
    front = []
    for k, p in enumerate(pairs):
        prev_exp = pairs[k - 1]["expiry"] if k else pd.Timestamp("1900-01-01")
        seg = p["s"][(p["s"].index > prev_exp) & (p["s"].index <= p["expiry"])]
        front.append(seg.assign(pair=f'{p["white"]}/{p["raw"]}'))
    f = pd.concat(front)
    f = f[f.index >= "2010-01-01"]
    live = [p for p in pairs if p["s"].index.max() >= today - timedelta(days=3) and p["nominal"] >= today - timedelta(days=3)]
    # history by pair type: average premium in the 30 days before expiry, last 15 years
    hist = {}
    for p in pairs:
        if p in live or p["year"] < 2010:
            continue
        s = p["s"][p["s"].index > p["expiry"] - timedelta(days=30)].prem
        hist.setdefault(p["mon"], []).append({"pair": f'{p["white"]}/{p["raw"]}', "year": p["year"], "avg30": rd(s.mean(), 1)})
    curve = []
    for p in live:
        s = p["s"]
        curve.append({"pair": f'{p["white"]}/{p["raw"]}', "white": rd(s.w.iloc[-1], 1), "raw": rd(s.r.iloc[-1], 2),
                      "prem": rd(s.prem.iloc[-1], 1), "date": str(s.index[-1])[:10], "mon": p["mon"],
                      "prem_1w": rd(s.prem.iloc[-6], 1) if len(s) > 6 else None,
                      "pct_vs_hist": rd(np.mean([h["avg30"] <= s.prem.iloc[-1] for h in hist.get(p["mon"], []) if h["avg30"] is not None]) * 100, 0) if hist.get(p["mon"]) else None})
    return {"front": {"dates": [str(x)[:10] for x in f.index], "prem": [rd(x, 1) for x in f.prem], "pair": f.pair.tolist()},
            "curve": curve, "history": hist}


# ---------------------------------------------------------------- Brazil exports (Comex Stat, from the trade tab's data)
def exports():
    frames = []
    for fn in ["exports_pre2015.csv", "exports_2015on.csv"]:
        p = os.path.join(TRADE, fn)
        if os.path.exists(p):
            x = pd.read_csv(p, dtype={"ncm": str, "country_code": str}, usecols=["year", "month", "ncm", "country_name", "kg_net", "fob_usd"])
            frames.append(x[x.ncm.str[:4] == "1701"])
    if not frames:
        return None
    d = pd.concat(frames)
    d["type"] = np.where(d.ncm.str[4:6].isin(["13", "14"]), "raw", np.where(d.ncm.str[4:6] == "12", "beet", "white"))
    d = d[d.type != "beet"]
    d["t"] = d.kg_net / 1000
    m = d.groupby(["year", "month", "type"]).agg(t=("t", "sum"), fob=("fob_usd", "sum")).reset_index()
    pv = m.pivot_table(index=["year", "month"], columns="type", values="t").fillna(0)
    fob = m.groupby(["year", "month"]).fob.sum()
    pv["usd_t"] = fob / (pv.raw + pv.white)
    pv = pv.reset_index()
    pv = pv[pv.year >= 2010]
    pv["my"] = np.where(pv.month >= 4, pv.year, pv.year - 1)
    pv["mi"] = (pv.month - 4) % 12          # 0 = April
    my = {}
    for y, g in pv.groupby("my"):
        g = g.sort_values("mi")
        my[str(y)] = {"mi": g.mi.tolist(), "cum": [rd(v / 1e6, 3) for v in (g.raw + g.white).cumsum()],
                      "total": rd((g.raw + g.white).sum() / 1e6, 2), "n": len(g)}
    last_y, last_m = int(pv.year.iloc[-1]), int(pv.month.iloc[-1])
    cur_my = last_y if last_m >= 4 else last_y - 1
    k = (last_m - 4) % 12
    pace = []
    for y in sorted(my, key=int)[-6:]:
        e = my[y]
        if k < len(e["cum"]):
            pace.append({"my": f"{y}/{int(y) + 1 - 2000:02d}", "to_date": e["cum"][k], "total": e["total"] if e["n"] == 12 else None})
    # destinations, current MY vs prior MY same months
    d["my"] = np.where(d.month >= 4, d.year, d.year - 1); d["mi"] = (d.month - 4) % 12
    cur = d[(d.my == cur_my) & (d.mi <= k)].groupby("country_name").t.sum()
    prv = d[(d.my == cur_my - 1) & (d.mi <= k)].groupby("country_name").t.sum()
    top = cur.sort_values(ascending=False).head(12)
    dest = [{"country": c, "t": rd(v / 1e6, 3), "prev": rd(prv.get(c, 0) / 1e6, 3)} for c, v in top.items()]
    mon = pv.tail(36)
    return {"last": f"{last_y}-{last_m:02d}", "cur_my": cur_my, "k": k,
            "monthly": {"ym": [f"{a}-{b:02d}" for a, b in zip(mon.year, mon.month)], "raw": [rd(v / 1e6, 3) for v in mon.raw],
                        "white": [rd(v / 1e6, 3) for v in mon.white], "usd_t": [rd(v, 0) for v in mon.usd_t]},
            "my": my, "pace": pace, "dest": dest}


# ---------------------------------------------------------------- USDA PSD
def psd():
    d = read("psd_sugar.csv")
    if d is None:
        return None
    d = d[d.Market_Year >= 2005]
    attrs = {"Production": "prod", "Human Dom. Consumption": "cons", "Exports": "exp", "Imports": "imp", "Ending Stocks": "end"}
    out = {}
    for cc, name in [("BR", "Brazil"), ("IN", "India"), ("TH", "Thailand"), ("CH", "China"), ("E4", "EU")]:
        g = d[d.Country_Code == cc]
        if g.empty and cc == "E4":
            g = d[d.Country_Name.str.contains("European Union", na=False)]
        p = g.pivot_table(index="Market_Year", columns="Attribute_Description", values="Value")
        out[name] = {"years": p.index.tolist(), **{k: [rd(v / 1000, 2) for v in p.get(a, pd.Series(index=p.index, dtype=float))] for a, k in attrs.items()}}
    w = d.groupby(["Market_Year", "Attribute_Description"]).Value.sum().unstack()
    use = w.get("Total Disappearance", w["Human Dom. Consumption"])
    out["World"] = {"years": w.index.tolist(), "prod": [rd(v / 1000, 2) for v in w["Production"]],
                    "cons": [rd(v / 1000, 2) for v in w["Human Dom. Consumption"]], "exp": [rd(v / 1000, 2) for v in w["Exports"]],
                    "end": [rd(v / 1000, 2) for v in w["Ending Stocks"]], "stu": [rd(a / b * 100, 1) for a, b in zip(w["Ending Stocks"], use)]}
    return out


def main():
    res = {"built": str(date.today()), "constants": {"atr": ATR, "pol": POL, "logistics_brl": LOGISTICS_BRL, "lb_t": LB_T}}
    c = crush()
    if c:
        res["crush"], cs = c
        res["unica"] = unica_block(cs)
    res["snapshot"], res["parity"] = prices()
    res["white"] = white_premium()
    a = read("anp_sp.csv")
    if a is not None and {"hydrous", "gasoline"} <= set(a.columns):
        a = a.dropna().tail(260)
        res["pump"] = {"dates": a.iloc[:, 0].astype(str).str[:10].tolist(), "hydrous": [rd(v, 2) for v in a.hydrous],
                       "gasoline": [rd(v, 2) for v in a.gasoline], "ratio": [rd(h / g * 100, 1) for h, g in zip(a.hydrous, a.gasoline)]}
    res["exports"] = exports()
    res["psd"] = psd()
    est = os.path.join(DATA, "estimates.json")
    res["estimates"] = json.load(open(est)) if os.path.exists(est) else []
    # exportable surplus cross-check: projected CS sugar + N/NE (last season) − domestic use (USDA)
    try:
        pj = res["crush"]["projection"]["sugar"]
        br = res["psd"]["Brazil"]
        cons = br["cons"][-1]
        res["balance"] = {"cs_sugar_mid": pj["mid"], "cs_sugar_lo": pj["lo"], "cs_sugar_hi": pj["hi"], "br_cons": cons}
    except Exception:
        pass
    with open(os.path.join(DATA, "sugar.json"), "w") as fh:
        json.dump(res, fh, separators=(",", ":"))
    print("built", os.path.join(DATA, "sugar.json"), os.path.getsize(os.path.join(DATA, "sugar.json")) // 1024, "KB")


if __name__ == "__main__":
    main()
