"""USDA reports for the cotton, coffee and sugar "Reports" tabs.

Sources (all public US government data):
  - FAS GAIN attaché reports (gain.fas.usda.gov; anonymous token on apps.fas.usda.gov/newgainapi), categories
    Cotton and Products (25), Coffee (24), Sugar (31), key countries only. Standard types (Cotton and Products
    Annual/Update, Coffee Annual/Semi-annual, Sugar Annual/Semi-annual/Update); other reports only when the title or
    highlights are about the commodity.
  - FAS "World Markets and Trade" circulars (apps.fas.usda.gov/psdonline/circulars/{cotton,coffee,sugar}.pdf;
    the URL always holds the latest issue, so each issue is kept when first seen).
  - ERS "Cotton and Wool Outlook" and "Sugar and Sweeteners Outlook" (www.ers.usda.gov/publications/<id>; new ids
    found in the ERS sitemap).

Commands
  python models/usda_reports.py fetch     # list new reports since data/research/usda_reports_state.json, download,
                                          # pdftotext -layout, keep text in data/research/usda_text/<key>.txt.gz,
                                          # parse the PSD tables (USDA Official vs New Post) into the state
  python models/usda_reports.py build     # write data/{cotton,coffee,sugar}/reports/usda.json via reports_store
  python models/usda_reports.py all       # fetch + build (the workflow)

Key points: numbers come from the reports' own tables (Post vs USDA official, and Post's change from its previous
report). Short own-words notes written on reading a report go in data/research/usda_reports_notes.json
({key: [point, ...]}) and are shown first. Entries without a note are marked auto.
fetch exits non-zero when a source cannot be listed at all (token, search, sitemap), so the run shows as failed.
"""
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "models"))
import reports_store  # noqa: E402

STATE = os.path.join(ROOT, "data", "research", "usda_reports_state.json")
NOTES = os.path.join(ROOT, "data", "research", "usda_reports_notes.json")
TEXT = os.path.join(ROOT, "data", "research", "usda_text")
H = {"User-Agent": "Mozilla/5.0 (research desk; github actions)", "Accept": "application/json, text/plain, */*"}
GAIN = "https://apps.fas.usda.gov/newgainapi/"
ANON = "00000000-0000-0000-0000-00000000000000000000-0000-0000-0000-000000000000"   # GAIN's public (anonymous) client
GAIN_HOME = "https://gain.fas.usda.gov/"

WEST_AFRICA = ["Senegal", "Cote d'Ivoire", "Benin", "Burkina Faso", "Mali", "Cameroon", "Chad", "Togo", "Ghana", "Nigeria", "Guinea"]
CENTRAL_AMERICA = ["Honduras", "Guatemala", "Mexico", "Nicaragua", "Costa Rica", "El Salvador"]
MARKETS = {
    "cotton": {"cat": 25, "word": r"cotton", "label": "Cotton",
               "countries": ["China", "India", "Pakistan", "Bangladesh", "Vietnam", "Turkey", "Brazil", "Australia", "Uzbekistan",
                             "Indonesia", "Egypt", "Mexico"] + WEST_AFRICA,
               "types": r"^Cotton and Products (Annual|Update)", "table": r"^\s*Cotton\b",
               "lines": [("Production", r"^Production"), ("Exports", r"^Exports"), ("Imports", r"^Imports"),
                         ("Mill use", r"^Domestic Use(?! and)"), ("Ending stocks", r"^Ending Stocks")],
               "unit": ("bales", 1000), "wmt": "cotton", "ers": ("Cotton and Wool Outlook", "cws")},
    "coffee": {"cat": 24, "word": r"coffee", "label": "Coffee",
               "countries": ["Brazil", "Vietnam", "Colombia", "Indonesia", "Ethiopia", "Uganda", "Kenya", "India", "Peru",
                             "European Union"] + CENTRAL_AMERICA,
               "types": r"^Coffee (Annual|Semi-annual|Semi-Annual|.*Update)", "table": r"^\s*Coffee, Green",
               "lines": [("Production", r"^Total Production"), ("Arabica", r"^Arabica Production"), ("Robusta", r"^Robusta Production"),
                         ("Exports", r"^Total Exports"), ("Consumption", r"^Domestic Consumption"), ("Ending stocks", r"^Ending Stocks")],
               "unit": ("bags", 1000), "wmt": "coffee", "ers": None},
    "sugar": {"cat": 31, "word": r"sugar", "label": "Sugar",
              "countries": ["Brazil", "India", "Thailand", "European Union", "China", "Mexico", "Russia", "Pakistan", "Indonesia",
                            "Australia", "Philippines"],
              "types": r"^Sugar (Annual|Semi-annual|Semi-Annual|.*Update)", "table": r"^\s*Sugar, Centrifugal",
              "lines": [("Production", r"^Total Sugar Production"), ("Exports", r"^Total Exports"), ("Imports", r"^Total Imports"),
                        ("Consumption", r"^Human Dom\. Consumption"), ("Ending stocks", r"^Ending Stocks")],
              "unit": ("t", 1000), "wmt": "sugar", "ers": ("Sugar and Sweeteners Outlook", "sss")},
}
CNAME = {"China - People's Republic of": "China", "Turkiye": "Turkey", "Uzbekistan - Republic of": "Uzbekistan",
         "Korea - Republic of": "South Korea", "South Africa - Republic of": "South Africa"}
MON = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September",
                                   "October", "November", "December"], 1)}


def window_start(market):
    return reports_store.window_start(market)


def load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def save_state(S):
    S["updated"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ")
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(S, f, indent=1, ensure_ascii=False, sort_keys=True)


def get(url, **kw):
    for i in range(3):
        try:
            r = requests.get(url, headers=kw.pop("headers", H), timeout=120, **kw)
            if r.status_code == 200:
                return r
            print("  http", r.status_code, url)
        except Exception as e:
            print("  err", e, url)
        time.sleep(4 * (i + 1))
    return None


def pdf_text(content):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(content)
        f.flush()
        return subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True, timeout=180).stdout


def put_text(key, text):
    os.makedirs(TEXT, exist_ok=True)
    with gzip.open(os.path.join(TEXT, key + ".txt.gz"), "wt", encoding="utf-8") as f:
        f.write(text)


def read_text(key):
    p = os.path.join(TEXT, key + ".txt.gz")
    return gzip.open(p, "rt", encoding="utf-8").read() if os.path.exists(p) else None


# ---------------------------------------------------------------- PSD tables in GAIN reports (USDA Official | New Post)
NUM = r"-?\(?[\d,]+(?:\.\d+)?\)?"


def num(s):
    s = s.replace(",", "")
    neg = s.startswith("(") or s.startswith("-")
    v = float(s.strip("()-"))
    return -v if neg else v


def parse_tables(text):
    """Every 'USDA Official / New Post' table: {title, years, rows: {label: [[official, post], ...]}}."""
    L = text.splitlines()
    out = []
    for i, l in enumerate(L):
        if not re.search(r"Market Year Begin", l):
            continue
        head = None
        for j in range(i - 1, max(-1, i - 4), -1):
            ys = re.findall(r"\b(?:MY\s*)?(\d{4}/\d{2,4})\b", L[j])
            if len(ys) >= 1:
                head = (j, ys)
                break
        if not head:
            continue
        k = len(head[1])
        title = re.split(r"\s{2,}", L[head[0]].strip())[0]
        win = "\n".join(L[i:i + 6])
        if not re.search(r"Official", win) or not re.search(r"Post", win):
            continue
        rows, blank = {}, 0
        for l2 in L[i + 1:i + 60]:
            if not l2.strip():
                blank += 1
                if blank >= 4 and rows:
                    break
                continue
            blank = 0
            if re.search(r"Market Year Begin", l2) or (rows and re.search(r"\b\d{4}/\d{2,4}\b.*\b\d{4}/\d{2,4}\b", l2)):
                break
            m = re.match(r"^\s*(.*?[A-Za-z.)%])\s+((?:" + NUM + r"\s+)*" + NUM + r")\s*$", l2)
            if not m:
                continue
            label, vals = m.group(1).strip(), re.split(r"\s+", m.group(2).strip())
            if len(vals) == 2 * k + 1:          # label ending in a number ("Domestic Use and Loss 1000")
                label, vals = label + " " + vals[0], vals[1:]
            if len(vals) != 2 * k:
                continue
            try:
                v = [num(x) for x in vals]
            except ValueError:
                continue
            rows.setdefault(label, [[v[2 * n], v[2 * n + 1]] for n in range(k)])
        if rows:
            out.append({"title": title, "years": [y if len(y) == 7 else y[:5] + y[-2:] for y in head[1]], "rows": rows})
    return out


def pick_table(tables, market):
    pat = MARKETS[market]["table"]
    for t in tables:
        if re.search(pat, t["title"], re.I):
            return t
    return None


def line_vals(t, market):
    """{line: [[official, post] per year]} for the market's key lines."""
    out = {}
    for name, pat in MARKETS[market]["lines"]:
        for lab, v in t["rows"].items():
            if re.search(pat, lab, re.I):
                out[name] = v
                break
    return out


# ---------------------------------------------------------------- fetch
def gain_token():
    r = requests.post(GAIN + "token", data=f"client_id=eAuthClient&client_secret={ANON}&grant_type=client_credentials",
                      headers={**H, "Content-Type": "application/x-www-form-urlencoded"}, timeout=60)
    r.raise_for_status()
    return r.json()["access_token"]


def gain_wanted(e, market):
    M = MARKETS[market]
    c = CNAME.get(e["countryName"], e["countryName"])
    if c not in M["countries"]:
        return None
    name = e["reportName"].strip()
    if re.search(M["types"], name, re.I):
        return c
    if re.search(M["word"], name, re.I) or len(re.findall(M["word"], e.get("reportHighlights") or "", re.I)) >= 1:
        return c
    return None


def fetch_gain(S):
    tok = gain_token()
    A = {**H, "Authorization": "Bearer " + tok}
    G = S.setdefault("gain", {})
    today = date.today().isoformat()
    new = 0
    for market, M in MARKETS.items():
        ws = window_start(market)
        r = requests.post(GAIN + "api/Search/GetSearchResults", json={"categoryIds": [M["cat"]], "fromDate": ws, "toDate": today + "T23:59:59"},
                          headers=A, timeout=180)
        r.raise_for_status()
        res = r.json()
        print(f"GAIN {market}: {len(res)} reports since {ws}")
        for e in sorted(res, key=lambda e: e["publishDate"]):
            c = gain_wanted(e, market)
            if not c:
                continue
            key = e.get("reportNumber") or hashlib.md5(e["fileName"].encode()).hexdigest()[:10]
            rec = G.get(key)
            if rec and market not in rec["markets"]:
                rec["markets"].append(market)
            if rec and rec.get("text"):
                continue
            url = GAIN + "api/Report/DownloadReportByFileName?fileName=" + requests.utils.quote(e["fileName"] + ".pdf")
            rec = rec or {"key": key, "markets": [market], "country": c, "name": e["reportName"].strip(), "post": e.get("postName"),
                          "date": e["publishDate"][:10], "file": e["fileName"], "url": url, "highlights": (e.get("reportHighlights") or "").strip()}
            G[key] = rec
            x = get(url)
            if not x or x.content[:4] != b"%PDF":
                print("  no pdf", key, rec["name"], c)
                continue
            t = pdf_text(x.content)
            put_text(key, t)
            rec["text"] = True
            rec["tables"] = parse_tables(t)
            new += 1
            print(f"  + {rec['date']} {c}: {rec['name']} ({key}), {len(rec['tables'])} tables")
            time.sleep(1)
    return new


def fetch_wmt(S):
    W = S.setdefault("wmt", {})
    new = 0
    for market, M in MARKETS.items():
        u = f"https://apps.fas.usda.gov/psdonline/circulars/{M['wmt']}.pdf"
        x = get(u)
        if not x or x.content[:4] != b"%PDF":
            print("WMT", market, "not available")
            continue
        t = pdf_text(x.content)
        m = re.search(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d\d)\b", t[:3000])
        if not m:
            print("WMT", market, "no issue date found")
            continue
        ym = f"{m.group(2)}-{MON[m.group(1)]:02d}"
        key = f"wmt-{market}-{ym}"
        if key in W:
            continue
        put_text(key, t)
        W[key] = {"key": key, "market": market, "month": ym, "url": u, "first_seen": date.today().isoformat(),
                  "sha": hashlib.sha1(x.content).hexdigest()[:12], "headline": wmt_headline(t)}
        new += 1
        print(f"WMT + {key}: {W[key]['headline']}")
    return new


def wmt_headline(t):
    L = [l.strip() for l in t.splitlines()[:30] if l.strip()]
    for i, l in enumerate(L):
        if re.search(r"World Markets and Trade", l):
            for n in L[i + 1:i + 4]:
                if len(n) > 15 and not re.match(r"^[\d.\s]+$", n) and not re.search(r"Million|Percent|^\d", n):
                    return re.sub(r"\s{2,}.*", "", n)
    return None


def fetch_ers(S):
    E = S.setdefault("ers", {"checked_max": 0, "items": {}})
    sm = get("https://www.ers.usda.gov/sitemap.xml")
    if not sm:
        raise SystemExit("ERS sitemap not reachable")
    ids = set()
    for u in re.findall(r"<loc>([^<]+)</loc>", sm.text):
        y = get(u)
        if y:
            ids |= {int(i) for i in re.findall(r"/publications/(\d+)</loc>", y.text)}
    if not ids:
        raise SystemExit("ERS sitemap: no publication ids")
    ids = sorted(ids)
    todo = [i for i in ids if i > E["checked_max"]]
    if not E["checked_max"]:
        todo = ids[-300:]                     # first run: the last ~300 publications cover well over a year
    want = {M["ers"][0]: m for m, M in MARKETS.items() if M["ers"]}
    new = 0
    for i in todo:
        r = get(f"https://www.ers.usda.gov/publications/{i}")
        if not r:
            continue
        tt = re.search(r"<title>([^<|]+)", r.text)
        title = tt.group(1).strip() if tt else ""
        m = re.match(r"^(Cotton and Wool Outlook|Sugar and Sweeteners Outlook):\s+(\w+)\s+(\d{4})", title)
        E["checked_max"] = max(E["checked_max"], i)
        if not m:
            continue
        market = want[m.group(1)]
        ym = f"{m.group(3)}-{MON.get(m.group(2), 0):02d}"
        if ym < window_start(market)[:7]:
            continue
        pdfs = [p for p in re.findall(r'href="(/media/\d+/[^"]+\.pdf)[^"]*"', r.text) if re.search(MARKETS[market]["ers"][1], p, re.I)]
        if not pdfs:
            print("  ERS no pdf", i, title)
            continue
        x = get("https://www.ers.usda.gov" + pdfs[0])
        if not x or x.content[:4] != b"%PDF":
            continue
        t = pdf_text(x.content)
        code = re.search(r"\b((?:CWS|SSS-M?)-?\d{2,3}[a-z]?)\b", t[:600])
        key = f"ers-{market}-{ym}"
        put_text(key, t)
        rd = re.search(r"\|\s*(\w+ \d{1,2}, \d{4})", t[:800])
        E["items"][key] = {"key": key, "market": market, "month": ym, "id": i, "title": title, "code": code.group(1) if code else None,
                           "url": f"https://www.ers.usda.gov/publications/{i}", "pdf": "https://www.ers.usda.gov" + pdfs[0].split("?")[0],
                           "date": datetime.strptime(rd.group(1), "%B %d, %Y").date().isoformat() if rd else f"{ym}-15",
                           "headline": ers_headline(t)}
        new += 1
        print(f"ERS + {key}: {E['items'][key]['headline']}")
        time.sleep(0.5)
    return new


def ers_headline(t):
    L = [l.strip() for l in t.splitlines()[:40]]
    for i, l in enumerate(L):
        if re.match(r"^(Cotton and Wool|Sugar and Sweeteners) Outlook:", l):
            body = [x for x in L[i + 1:i + 8] if x]
            if body and not re.search(r"\d{4}", body[0]) and "," in body[0] or " and " in (body[0] if body else ""):
                body = body[1:]                 # authors line
            h = []
            for x in body:
                if len(x) > 110 or re.search(r"\bThe (latest|U\.S\.)\b|USDA", x):
                    break
                h.append(x)
            return " ".join(h)[:160] or None
    return None


def fetch():
    S = load(STATE, {})
    errs = []
    n = {}
    for name, fn in (("gain", fetch_gain), ("wmt", fetch_wmt), ("ers", fetch_ers)):
        try:
            n[name] = fn(S)
        except SystemExit as e:
            errs.append(f"{name}: {e}")
        except Exception as e:
            errs.append(f"{name}: {type(e).__name__}: {e}")
        save_state(S)
    print("new:", n)
    if errs:
        print("::error::" + "; ".join(errs))
        return 1
    return 0


# ---------------------------------------------------------------- build entries
def fmt(v, market, diff=False):
    """Thousand units -> readable: bales/bags in millions, sugar in Mt / kt."""
    unit = MARKETS[market]["unit"][0]
    if v is None:
        return "–"
    sgn = ("+" if v > 0 else "−" if v < 0 else "±") if diff else ("−" if v < 0 else "")
    a = abs(v)
    if unit == "t":
        return f"{sgn}{a / 1000:.2f} Mt" if a >= 1000 else f"{sgn}{a:,.0f} kt"
    u = "bales" if unit == "bales" else "bags"
    return f"{sgn}{a / 1000:.2f}m {u}" if a >= 1000 else f"{sgn}{a:,.0f}k {u}"


def pct(a, b):
    return "" if not b else f" ({(a / b - 1) * 100:+.1f}%)".replace("-", "−")


def gain_points(rec, market, prev):
    t = pick_table(rec.get("tables") or [], market)
    if not t:
        return [], None
    V = line_vals(t, market)
    if not V:
        return [], None
    ys = t["years"]
    pts, comp = [], {"my": ys[-1], "rows": []}
    k = len(ys) - 1
    for name, v in V.items():
        o, p = v[k]
        comp["rows"].append({"line": name, "usda": o, "post": p, "diff": p - o})
    diffs = [r for r in comp["rows"] if r["diff"] and r["usda"] and abs(r["diff"]) >= 0.005 * abs(r["usda"])]   # ignore <0.5% gaps
    if all(r["usda"] == 0 for r in comp["rows"]):
        pts.append(f"MY {ys[-1]}: Post's first forecast (no USDA official number yet): " +
                   "; ".join(f"{r['line'].lower()} {fmt(r['post'], market)}" for r in comp["rows"] if r["post"]) + ".")
    elif diffs:
        pts.append(f"MY {ys[-1]}, Post vs USDA official: " + "; ".join(
            f"{r['line'].lower()} {fmt(r['post'], market)} vs {fmt(r['usda'], market)} ({fmt(r['diff'], market, True)})" for r in diffs) + ".")
    else:
        pts.append(f"MY {ys[-1]}: Post in line with USDA official (production {fmt(V.get('Production', [[0, 0]] * len(ys))[k][1], market)}).")
    if k >= 1:
        d1 = [(name, v[k - 1]) for name, v in V.items() if v[k - 1][0] and v[k - 1][1] != v[k - 1][0] and name in ("Production", "Exports", "Ending stocks")]
        if d1:
            pts.append(f"MY {ys[k - 1]}, Post vs USDA: " + "; ".join(f"{n.lower()} {fmt(b, market)} vs {fmt(a, market)}" for n, (a, b) in d1) + ".")
    if prev:
        pt = pick_table(prev.get("tables") or [], market)
        PV = line_vals(pt, market) if pt else {}
        if PV and ys[-1] in pt["years"]:
            j = pt["years"].index(ys[-1])
            ch = [(n, PV[n][j][1], V[n][k][1]) for n in V if n in PV and PV[n][j][1] and PV[n][j][1] != V[n][k][1]
                  and n in ("Production", "Exports", "Imports", "Consumption", "Mill use", "Ending stocks")]
            when = datetime.fromisoformat(prev["date"]).strftime("%b %Y")
            if ch:
                pts.append(f"Post's own revision since its {prev['name']} ({when}), MY {ys[-1]}: " + "; ".join(
                    f"{n.lower()} {fmt(b, market)} from {fmt(a, market)}{pct(b, a)}" for n, a, b in ch) + ".")
            else:
                pts.append(f"No change to Post's MY {ys[-1]} key numbers since its {prev['name']} ({when}).")
    return pts, comp


def build():
    S = load(STATE, {})
    NT = load(NOTES, {})
    for market, M in MARKETS.items():
        path = os.path.join(ROOT, "data", market, "reports", "usda.json")
        D = load(path, {})
        D.update({"source": "usda", "name": "USDA: attaché (GAIN) reports, World Markets and Trade, ERS outlook",
                  "home": "https://gain.fas.usda.gov/", "cadence": "on release (checked every weekday afternoon)",
                  "access": "public: GAIN API and PDFs, FAS PSD circulars, ERS publications",
                  "note": "GAIN reports are written by USDA's overseas posts and are not official USDA estimates; the official number is the "
                          "one in the report's own table (USDA Official). Following the desk's rule, the points show how far Post is from "
                          "USDA and how Post changed its own numbers, not the levels alone."})
        ws = window_start(market)
        entries, summary = [], {}
        recs = sorted([r for r in S.get("gain", {}).values() if market in r["markets"] and r["date"] >= ws], key=lambda r: r["date"])
        last_by_country = {}
        for r in recs:
            prev = last_by_country.get(r["country"])
            pts, comp = gain_points(r, market, prev)
            note = NT.get(r["key"], [])
            e = {"date": r["date"], "title": f"{r['country']}: {r['name']}", "url": r["url"], "kind": "gain", "country": r["country"],
                 "tag": "FAS attaché", "key_points": note + pts, "auto": not note}
            if comp:
                e["post_vs_usda"] = comp
                last_by_country[r["country"]] = r
                summary[r["country"]] = {"date": r["date"], "report": r["name"], "url": r["url"], **comp}
            entries.append(e)
        for w in S.get("wmt", {}).values():
            if w["market"] != market or w["month"] < ws[:7]:
                continue
            note = NT.get(w["key"], [])
            d = w["month"] + "-15" if w["first_seen"][:7] != w["month"] else w["first_seen"]
            entries.append({"date": d, "title": f"FAS {M['label']}: World Markets and Trade, {datetime.strptime(w['month'], '%Y-%m').strftime('%B %Y')}"
                            + (f" — {w['headline']}" if w.get("headline") else ""), "url": w["url"], "kind": "wmt", "tag": "FAS WMT",
                            "key_points": note or auto_text_points(w["key"]), "auto": not note})
        for x in S.get("ers", {}).get("items", {}).values():
            if x["market"] != market or x["date"] < ws:
                continue
            note = NT.get(x["key"], [])
            entries.append({"date": x["date"], "title": f"ERS {x['title'].split(' | ')[0]}" + (f" — {x['headline']}" if x.get("headline") else ""),
                            "url": x["url"], "kind": "ers", "tag": "ERS outlook", "key_points": note or auto_text_points(x["key"]), "auto": not note})
        entries.sort(key=lambda e: (e["date"], e["title"]), reverse=True)
        D["entries"] = entries
        D["window_start"] = ws
        D["summary"] = {"unit": {"cotton": "thousand 480-lb bales", "coffee": "thousand 60-kg bags", "sugar": "thousand t, raw value"}[market],
                        "rows": [dict(country=c, **v) for c, v in sorted(summary.items(), key=lambda kv: kv[1]["date"], reverse=True)]}
        D["built"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        reports_store.save(path, D)
        print(f"{os.path.relpath(path, ROOT)}: {len(entries)} entries ({sum(1 for e in entries if e['kind'] == 'gain')} GAIN), from {ws}")
    return 0


REV = re.compile(r"\b(raised|lowered|reduced|increased|decreased|cut|up|down|unchanged|revised|forecast|projected|estimated)\b", re.I)


def auto_text_points(key, n=3):
    """Fallback for a WMT / ERS issue nobody has summarised yet: the first sentences that carry a number and a change,
    clipped to the clause with the number (marked auto on the page)."""
    t = read_text(key)
    if not t:
        return []
    body = re.sub(r"[ \t]+", " ", t[:9000])
    body = re.sub(r"\n(?=[a-z(0-9])", " ", body)
    sents = re.split(r"(?<=[.])\s+(?=[A-Z])", body.replace("\n", " "))
    out = []
    for s in sents:
        s = s.strip()
        if 40 < len(s) < 320 and REV.search(s) and re.search(r"\d", s) and not re.search(r"Figure|Table|Source:|http|click", s):
            s = re.split(r";|, (?:but|while|as|which|with)\b", s)[0].strip().rstrip(",") + ("" if s.endswith(".") else ".")
            out.append(s)
        if len(out) >= n:
            break
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "fetch":
        return fetch()
    if cmd == "build":
        return build()
    if cmd == "all":
        rc = fetch()
        build()
        return rc
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
