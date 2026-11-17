#!/usr/bin/env python3
"""Alert engine, evaluated after each daily data refresh.

Rules (levels are stated in advance on the page):
  - cotton front spread at or above 80%, 90% and 100% of full carry (data/cotton/carry_history.csv)
  - certified stocks moving more than a set amount in a week (cotton 10,000 bales, coffee 40,000 bags)
  - a new 55-day closing high or low in the front contract (levels from the previous 55 settlements)
  - managed-money net beyond its 3-year 10th or 90th percentile (weekly COT)
  - coffee: ICO Brazilian naturals minus KC front at or below −5¢/lb (monthly, the certs tab's tenderable-parity line)
  - sugar: No. 11 front below hydrous ethanol parity
  - weather: ECMWF ensemble read turning dry or wet in a main crop region; odds of ≤3 °C over 30% in a Brazil coffee or cane region
  - data: a source on the Data status tab going late or missing

Writes data/alerts/state.json (what is on now and the next levels) and appends events to data/alerts/log.csv.
With --email it sends one email per day, only for alerts that newly triggered, through SMTP settings taken from
environment variables (repository secrets); without them it skips the email and says so.
"""
import csv, json, os, smtplib, ssl, sys
from datetime import datetime, timezone
from email.mime.text import MIMEText

import numpy as np
import pandas as pd

from watch_common import (ROOT, D, MK, ORDER, WX_MAIN, FROST_REGIONS, J, rd, fmt, label, last_settled, load_px, front_series,
                          wx_label, write_json, now_et)

STATE = D / "alerts" / "state.json"
LOG = D / "alerts" / "log.csv"
CARRY_LEVELS = [80, 90, 100]
CERT_WEEK = {"CT": (10000, "bales"), "KC": (40000, "bags")}


def A(aid, market, text, on, level=None, date=None):
    return {"id": aid, "market": market, "text": text, "on": bool(on), "level": level, "date": date}


def carry_rules(asof):
    out, watch = [], []
    p = D / "cotton" / "carry_history.csv"
    if not p.exists():
        return out, watch
    h = pd.read_csv(p, parse_dates=["date"])
    h = h[h.date <= asof]
    L = h.iloc[-1]
    pair = f"{label(L.front)}/{label(L['next'])}"
    for lv in CARRY_LEVELS:
        need = L.full_carry * lv / 100
        on = L.pct_of_full_carry >= lv
        out.append(A(f"CT_carry_{lv}", "Cotton", f"{pair} at {L.pct_of_full_carry:.1f}% of full carry ({L.spread:+.2f}¢ vs {L.full_carry:.2f}¢): at or above {lv}%",
                     on, f"{need:.2f}¢ {label(L['next'])} over {label(L.front)}", str(L.date.date())))
        if not on:
            watch.append({"market": "Cotton", "text": f"{pair} {lv}% of full carry at {need:.2f}¢ {label(L['next'])} over {label(L.front)} (now {L.spread:+.2f}¢, {L.date.date()})"})
    return out, watch[:1]


def cert_rules(asof):
    out, watch = [], []
    wc = J("data/overview/what_changed.json", {})
    for m in wc.get("markets", []):
        if m["sym"] not in CERT_WEEK:
            continue
        it = next((i for i in m["items"] if i["item"].startswith("ICE cert")), None)
        if not it or it["d5"] is None:
            continue
        thr, u = CERT_WEEK[m["sym"]]
        on = abs(it["d5"]) > thr
        out.append(A(f"{m['sym']}_certs_week", m["name"], f"{it['item']} {fmt(it['d5'], 0, True)} {u} in a week to {it['date']} (threshold ±{thr:,} {u})", on, f"±{thr:,} {u}", it["date"]))
        watch.append({"market": m["name"], "text": f"Certs weekly change beyond ±{thr:,} {u} (latest {fmt(it['d5'], 0, True)}, {it['date']})"})
    return out, watch


def breakout_rules(asof):
    out, watch = [], []
    for sym in ORDER:
        name, unit, dp, _, _ = MK[sym]
        w = load_px(sym, asof)
        fs = front_series(sym, w)
        f = fs.front.iloc[-1]
        s = w[f].dropna()
        s = s[s.index <= asof]
        if len(s) < 57:
            continue
        prior = s.iloc[-56:-1]
        hi, lo, px = prior.max(), prior.min(), s.iloc[-1]
        d = str(s.index[-1].date())
        out.append(A(f"{sym}_55hi", name, f"{label(f)} settled {fmt(px, dp)} {unit}, a new 55-day high (above {fmt(hi, dp)})", px > hi, f"{fmt(hi, dp)}", d))
        out.append(A(f"{sym}_55lo", name, f"{label(f)} settled {fmt(px, dp)} {unit}, a new 55-day low (below {fmt(lo, dp)})", px < lo, f"{fmt(lo, dp)}", d))
        # levels for the next session: the 55 settlements ending today
        nxt = s.iloc[-55:]
        watch.append({"market": name, "text": f"{label(f)}: 55-day high {fmt(nxt.max(), dp)}, 55-day low {fmt(nxt.min(), dp)} {unit} (settle {fmt(px, dp)} on {d})"})
    return out, watch


def cot_rules(asof):
    out, watch = [], []
    for sym in ORDER:
        C = J(f"data/cot_desk/{sym}.json")
        if not C:
            continue
        s = pd.Series(C["series"]["mm_n"], index=pd.to_datetime(C["series"]["date"])).sort_index()
        s = s[s.index <= asof]
        win = s[s.index > s.index[-1] - pd.Timedelta(days=3 * 365)]
        p10, p90, v = win.quantile(.1), win.quantile(.9), s.iloc[-1]
        d = str(s.index[-1].date())
        name = MK[sym][0]
        out.append(A(f"{sym}_mm_hi", name, f"Managed money net {v:+,.0f} lots ({d}) above its 3-year 90th percentile ({p90:+,.0f})", v > p90, f"{p90:+,.0f}", d))
        out.append(A(f"{sym}_mm_lo", name, f"Managed money net {v:+,.0f} lots ({d}) below its 3-year 10th percentile ({p10:+,.0f})", v < p10, f"{p10:+,.0f}", d))
        watch.append({"market": name, "text": f"Managed money net {v:+,.0f} lots ({d}); 3-year band {p10:+,.0f} to {p90:+,.0f}"})
    return out, watch


def coffee_rule():
    K = J("coffee/data/coffee.json")
    try:
        g = K["ico"]["groups"]
        v, m = g["bra_d"][-1], g["month"][-1]
    except Exception:
        return [], []
    return ([A("KC_bra_tender", "Coffee C", f"ICO Brazilian naturals {v:+.1f}¢/lb against KC ({m}): at or below −5¢, where semi-washed Brazil has come onto the exchange", v <= -5, "−5.0¢", m)],
            [{"market": "Coffee C", "text": f"Brazil naturals vs KC −5.0¢/lb (latest {v:+.1f}¢, {m})"}])


def sugar_rule():
    P = J("data/sugar/parity_read.json") or {}
    n = P.get("now") or {}
    if n.get("parity") is None or n.get("sb") is None:
        return [], []
    on = n["sb"] < n["parity"]
    return ([A("SB_below_parity", "Sugar No. 11", f"No. 11 {n['contract_label']} {n['sb']:.2f}¢ below hydrous ethanol parity {n['parity']:.2f}¢ ({n['date']})", on, f"{n['parity']:.2f}¢", n["date"])],
            [{"market": "Sugar No. 11", "text": f"Ethanol parity {n['parity']:.2f}¢/lb: No. 11 {n['contract_label']} now {n['sb']:.2f}¢ ({n['date']})"}])


def weather_rules(was=frozenset()):
    W = J("data/geo/wx_ensemble.json", {"regions": {}})
    wc = J("data/overview/what_changed.json", {})
    out = []
    flips = {(m["sym"], r["region"]): r for m in wc.get("markets", []) for r in m.get("weather", [])}
    for sym in ORDER:
        for rid in WX_MAIN[sym]:
            r = flips.get((sym, rid))
            if not r:
                continue
            for lab in ("dry", "wet"):
                out.append(A(f"wx_{rid}_{lab}", MK[sym][0], f"{r['name']}: next-15-day ensemble read {lab} ({r['window']}; {r['src']})",
                             r["read"] == lab and (r["flip"] or f"wx_{rid}_{lab}" in was), None, (W.get("generated") or "")[:10]))
    for rid in FROST_REGIONS:
        r = W["regions"].get(rid)
        if not r or r.get("p_frost3_max") is None:
            continue
        mk = "Coffee C" if "coffee" in r["crops"] else "Sugar No. 11"
        out.append(A(f"frost_{rid}", mk, f"{r['name']}: {r['p_frost3_max'] * 100:.0f}% of ensemble members at or below 3 °C in the next 15 days", r["p_frost3_max"] > .3, "30%", (W.get("generated") or "")[:10]))
    return out, []


def data_rules():
    S = J("data/status.json", {})
    out = []
    for r in S.get("sources", []):
        aid = "data_" + "".join(ch if ch.isalnum() else "_" for ch in r["source"])[:60]
        out.append(A(aid, "Data", f"{r['source']}: {r['state']} (latest {r['latest'] or '–'}, limit {r['limit']} {r['age_unit']})", r["state"] != "ok", None, S.get("today")))
    return out, []


def send(new, today):
    host, user, pw = os.environ.get("SMTP_HOST"), os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS")
    to = os.environ.get("ALERT_TO") or os.environ.get("EMAIL_TO")
    frm = os.environ.get("EMAIL_FROM") or user
    if not all([host, user, pw, to]):
        print("email: SMTP_HOST/SMTP_USER/SMTP_PASS/EMAIL_TO secrets not set; email skipped")
        return False
    port = int(os.environ.get("SMTP_PORT") or 465)
    body = "New alerts on the Softs Desk (" + today + "):\n\n" + "\n".join(f"- [{a['market']}] {a['text']}" for a in new)
    body += "\n\nhttps://bmr-com.github.io/Brazil--trade/#overview\nResearch use only."
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"Softs Desk alerts {today}: {len(new)} new"
    msg["From"], msg["To"] = frm, to
    rcpt = [x.strip() for x in to.split(",") if x.strip()]
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
            s.login(user, pw); s.sendmail(frm, rcpt, msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls(context=ctx); s.login(user, pw); s.sendmail(frm, rcpt, msg.as_string())
    print(f"email: sent {len(new)} new alerts")
    return True


def main():
    asof = last_settled()
    today = str(now_et().date())
    prev = J("data/alerts/state.json", {}) or {}
    was = {a["id"] for a in prev.get("active", [])}
    rules, watch, errors = [], [], []
    for fn in (carry_rules, cert_rules, breakout_rules, cot_rules, coffee_rule, sugar_rule, weather_rules, data_rules):
        try:
            r, w = fn(asof) if fn in (carry_rules, cert_rules, breakout_rules, cot_rules) else fn(was) if fn is weather_rules else fn()
            rules += r; watch += w
        except Exception as e:
            errors.append(f"{fn.__name__}: {str(e)[:120]}")
    active = [a for a in rules if a["on"]]
    since = {a["id"]: a.get("since") for a in prev.get("active", [])}
    for a in active:
        a["new"] = a["id"] not in was
        a["since"] = today if a["new"] else (since.get(a["id"]) or today)
    cleared = [a for a in prev.get("active", []) if a["id"] not in {x["id"] for x in active}]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    newlog = not LOG.exists()
    with open(LOG, "a", newline="") as f:
        wr = csv.writer(f)
        if newlog:
            wr.writerow(["date", "id", "market", "event", "text"])
        for a in active:
            if a["new"]:
                wr.writerow([today, a["id"], a["market"], "triggered", a["text"]])
        for a in cleared:
            wr.writerow([today, a["id"], a["market"], "cleared", a["text"]])
    pending = [p for p in prev.get("pending_email", []) if p["id"] in {a["id"] for a in active}]
    pending += [a for a in active if a["new"] and a["id"] not in {p["id"] for p in pending}]
    emailed = prev.get("last_email")
    if "--email" in sys.argv and pending and emailed != today:
        try:
            if send(pending, today):
                emailed, pending = today, []
        except Exception as e:
            errors.append(f"email failed: {str(e)[:150]}")
    state = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "asof": str(asof.date()), "today": today,
             "active": active, "watch": watch, "rules_checked": len(rules), "pending_email": pending, "last_email": emailed, "errors": errors,
             "rules": ["Cotton front spread at 80%, 90% and 100% of full carry", "Certified stocks: weekly change beyond ±10,000 bales (cotton) or ±40,000 bags (coffee)",
                       "New 55-day closing high or low in the front contract", "Managed-money net beyond its 3-year 10th or 90th percentile",
                       "ICO Brazilian naturals vs KC at or below −5¢/lb", "No. 11 front below hydrous ethanol parity",
                       "Ensemble weather read turning dry or wet (stays on while the read holds) in a main crop region; frost odds (≤3 °C) above 30% in a Brazil coffee or cane region",
                       "A data source on the Data status tab late or missing"]}
    write_json("data/alerts/state.json", state)
    print(f"alerts: {len(active)} on ({sum(a['new'] for a in active)} new), {len(cleared)} cleared, {len(rules)} checked; errors {errors}")
    for a in active:
        print(("  NEW " if a["new"] else "      ") + f"[{a['market']}] {a['text']}")
    for w in watch:
        print("  watch:", w["text"])
    if errors and any(e.startswith("email failed") for e in errors):
        sys.exit(1)   # a failed send shows as a failed run


if __name__ == "__main__":
    main()
