"""SAFRAS & Mercado coffee quotes for the Coffee > Differentials tab (Brazil by quality).

SAFRAS publishes free market notes on its WordPress site; this reads them through the public WordPress REST API
(robots.txt allows it) and keeps only the numbers:
  English site (safras.com.br/eng, ~monthly): FOB Santos differentials against ICE KC by quality - good cup MTGB
    14/16, fine cup 17/18, semi-washed (cherry), Rio, conillon - plus domestic R$/bag quotes for good cup (south of
    Minas) and fine cup (Cerrado/Mogiana) in the 2020-22 notes.
  Portuguese site (safras.com.br, 2-3 times a week): the previous session's buying prices, R$/60-kg bag, for
    sul de Minas bebida boa 15% catação, cerrado mineiro bebida dura 15%, Zona da Mata "rio" tipo 7 20%, conilon
    tipo 7 Vitória and conilon 7/8.
Output: data/coffee/diffs/safras_quotes.csv (one row per quote: quote_date, post_date, site, series, region, basis,
low, high, unit, shipment, ambiguous, url) and data/coffee/diffs/safras_read.json (latest post date read per site;
each run asks only for newer posts, --backfill re-reads everything). No article text is stored.
A quote whose sentence carries more than one number is kept with ambiguous=1 and the current-sounding number.
"""
import argparse, csv, html, json, re, sys, time
from datetime import date, datetime, timedelta
from pathlib import Path
import urllib.robotparser
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "coffee" / "diffs"
CSV = OUT / "safras_quotes.csv"
STATE = OUT / "safras_read.json"
AGENT = "BMR-Com research desk (github.com/BMR-Com)"
H = {"User-Agent": AGENT}
SITES = {"en": ("https://safras.com.br/eng/wp-json/wp/v2/posts", ["coffee"]),
         "pt": ("https://safras.com.br/wp-json/wp/v2/posts", ["bebida boa", "conilon tipo 7"])}
FIELDS = ["quote_date", "post_date", "site", "series", "region", "basis", "low", "high", "unit", "shipment", "ambiguous", "url"]


def robots_ok(url):
    rp = urllib.robotparser.RobotFileParser()
    try:
        r = requests.get("https://safras.com.br/robots.txt", headers=H, timeout=60)
        rp.parse(r.text.splitlines() if r.status_code == 200 else [])
    except Exception:
        return True
    return rp.can_fetch(AGENT, url)


def http(url, params, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, headers=H, params=params, timeout=240)
            if r.status_code == 400 and params.get("page", 1) > 1:
                return None                                   # past the last page
            r.raise_for_status()
            return r
        except Exception as e:
            print(f"  retry {i + 1}: {str(e)[:160]}"); time.sleep(15 * (i + 1))
    raise SystemExit(f"SAFRAS not reachable: {url}")


def txt(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).replace("​", "")


def brl(s):
    return float(s.replace(".", "").replace(",", "."))


# ---------- Portuguese daily notes ----------
PT = [("sul_minas_boa", "Sul de Minas", r"sul de Minas[^.]{0,90}?bebida boa"),
      ("cerrado_dura", "Cerrado mineiro", r"cerrado(?: mineiro)?[^.]{0,60}?bebida dura"),
      ("mogiana_boa", "Mogiana", r"Mogiana[^.]{0,80}?bebida (?:boa|dura)"),
      ("zona_mata_rio", "Zona da Mata", r"[“\"]?rio[”\"]? tipo 7"),
      ("conilon_t78", "Vitória ES", r"conilon tipo 7/8"),
      ("conilon_t7", "Vitória ES", r"conilon tipo 7(?!/)[^.]{0,40}?Vit[óo]ria")]
NUM = r"R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})(?:\s?/\s?(\d{1,3}(?:\.\d{3})*,\d{2}))?"
WD = {"segunda": 0, "terça": 1, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4}


def session_date(t, post):
    """The daily note reports the previous session: 'Na terça-feira (17), ...'."""
    m = re.search(r"N[ao]s? (segunda|terça|terca|quarta|quinta|sexta)-feira \((\d{1,2})\)", t, re.I)
    if not m:
        return post
    d = int(m.group(2))
    y, mo = post.year, post.month
    if d > post.day:
        mo -= 1
        if mo == 0:
            y, mo = y - 1, 12
    try:
        return date(y, mo, d)
    except ValueError:
        return post


def parse_pt(t, post, url):
    rows = []
    qd = session_date(t, post)
    # cut each quality's clause at the next "R$ .../..." pair; skip weekly/monthly balance sentences ("subiu de X para Y")
    for series, region, pat in PT:
        for m in re.finditer(pat + r"[^$]{0,140}?" + NUM, t, re.I):
            seg = t[max(0, m.start() - 60):m.end()]
            if re.search(r"balan[çc]o", seg, re.I):
                continue
            g = [x for x in m.groups() if x]
            lo = brl(g[0]); hi = brl(g[1]) if len(g) > 1 else lo
            rows.append({"quote_date": qd.isoformat(), "post_date": post.isoformat(), "site": "pt", "series": series, "region": region,
                         "basis": "domestic", "low": lo, "high": hi, "unit": "R$/60kg", "shipment": "spot", "ambiguous": 0, "url": url})
            break
    return rows


# ---------- English notes ----------
QUAL = [("fine_cup_1718", r"fine(?:r)? cups?|17/18 FC|FC 17/18"), ("good_cup_mtgb", r"MTGB|good cups?"),
        ("semi_washed", r"semi-?washed|cherry"), ("rio", r"\bRio\b"), ("conillon", r"conill?on")]
HIST = r"(last year|a year ago|in 20\d\d|deflated|5-year|average)"
CUR_LAST = r"(which (?:had |has )?(?:exchanged|changed|was|traded)|ended up|from (?:BRL )?[-+]?\s?\d)"
FWD = r"(new[- ]crop|for (?:[A-Z][a-z]{2,8}|H[12]|first half|second half)[^.]{0,20}shipment|for shipment in [^.,]+|Sep/\d\d|forward)"
NC = r"(?<![\w/])([+\-\u2212\u2013]\s?\d{1,3}(?:[.,]\d)?)(?:\s*(?:to|/)\s*([+\-\u2212\u2013]?\s?\d{1,3}(?:[.,]\d)?))?\s*(?:US\s?)?(?:cents|c/lb|\u00a2)"
NB = r"BRL\s?(\d[\d,]*)(?:\s*(?:/|to|and)\s*(?:BRL\s?)?(\d[\d,]*))?"


def _f(x):
    return float(x.replace("\u2212", "-").replace("\u2013", "-").replace(" ", "").replace(",", "."))


def cents(s):
    out = []
    for m in re.finditer(NC, s):
        a = _f(m.group(1)); b = m.group(2)
        b = _f(("-" if a < 0 and b.strip()[0].isdigit() else "") + b) if b else a
        out.append((m.start(), min(a, b), max(a, b)))
    for m in re.finditer(r"\b(\d{1,3})\s*cents?\s*(over|above|premium|under|below|discount)", s):
        v = float(m.group(1)) * (1 if m.group(2) in ("over", "above", "premium") else -1)
        out.append((m.start(), v, v))
    for m in re.finditer(r"\bat par\b", s):
        out.append((m.start(), 0.0, 0.0))
    return sorted(out)


def mentions(s):
    M = []
    for k, p in QUAL:
        for m in re.finditer(p, s, re.I):
            if not any(a <= m.start() < b for a, b, _ in M):
                M.append((m.start(), m.end(), k))
    return sorted(M)


def pick(vals, s):
    amb = int(len(vals) > 1)
    return (vals[-1] if amb and re.search(CUR_LAST, s, re.I) else vals[0]), amb


def parse_en(t, post, url):
    rows = []
    fob_doc = bool(re.search(r"FOB|against ICE|differential", t, re.I))
    for s in re.split(r"(?<=[a-z0-9%\)])\.\s+(?=[A-Z(])", t):
        M = mentions(s)
        if not M:
            continue
        hist = bool(re.search(HIST, s, re.I))
        cv = cents(s) if (fob_doc and re.search(r"cents|\u00a2", s)) else []
        bv = [(m.start(), brl2(m.group(1)), brl2(m.group(2)) if m.group(2) else brl2(m.group(1))) for m in re.finditer(NB, s)] if re.search(r"bag", s) else []
        bv = [x for x in bv if 200 <= x[1] <= 5000]
        for i, (a, b, k) in enumerate(M):
            nxt = M[i + 1][0] if i + 1 < len(M) else len(s)
            seg = s[a:nxt]
            c = [v for v in cv if a <= v[0] < nxt]
            if c and not (hist and len(c) == 1):
                (pos, lo, hi), amb = pick(c, seg)
                after = [v[0] for v in cv if v[0] > pos] + [nxt]
                fw = re.search(FWD, s[pos:min(after)], re.I)
                ship = "prompt" if not fw or re.search(r"near|prompt|spot", fw.group(0), re.I) else fw.group(0)[:40]
                rows.append({"quote_date": post.isoformat(), "post_date": post.isoformat(), "site": "en", "series": k, "region": "FOB Santos",
                             "basis": "FOB vs ICE London" if k == "conillon" and re.search(r"London|LIFFE", seg) else "FOB vs ICE KC", "low": lo, "high": hi, "unit": "c/lb", "shipment": ship,
                             "ambiguous": amb, "url": url})
            bb = [v for v in bv if a <= v[0] < nxt]
            if bb and k in ("fine_cup_1718", "good_cup_mtgb") and not re.search(HIST + r"|Sep/\d\d|September 20\d\d|for delivery|future|forward|commitment|certified|extra fine", seg, re.I):
                (pos, lo, hi), amb = pick(bb, seg)
                region = "Cerrado" if re.search(r"Cerrado", seg) else "Mogiana" if re.search(r"Mogiana", seg) else "Sul de Minas" if re.search(r"south(?:ern)? (?:of )?Minas", seg, re.I) else ""
                rows.append({"quote_date": post.isoformat(), "post_date": post.isoformat(), "site": "en", "series": ("fine_cup" if k.startswith("fine") else "good_cup") + "_domestic",
                             "region": region, "basis": "domestic", "low": lo, "high": hi, "unit": "R$/60kg", "shipment": "spot", "ambiguous": amb, "url": url})
    return rows


def brl2(s):
    s = s.replace(",", "")
    return float(s) if s else float("nan")


def save(old, new, state):
    key = lambda r: (r["quote_date"], r["site"], r["series"], r["region"], str(r["shipment"]), r["url"])
    allr = {key(r): r for r in old}
    for r in new:
        allr[key(r)] = {k: r.get(k, "") for k in FIELDS}
    rows = sorted(allr.values(), key=lambda r: (r["quote_date"], r["site"], r["series"]))
    with open(CSV, "w", newline="") as f:
        w = csv.DictWriter(f, FIELDS); w.writeheader(); w.writerows(rows)
    STATE.write_text(json.dumps(state, indent=1))
    return rows


def main():
    """Posts are read oldest first after the last post date read for each search, and the file and state are saved
    after every page, so a run that hits the time budget (--minutes) resumes where it stopped on the next run."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--minutes", type=float, default=18)
    a = ap.parse_args()
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text()) if STATE.exists() and not a.backfill else {}
    old = []
    if CSV.exists() and not a.backfill:
        with open(CSV) as f:
            old = list(csv.DictReader(f))
    new, read, partial = [], 0, False
    for site, (api, searches) in SITES.items():
        if not robots_ok(api):
            print(f"robots.txt does not allow {api}; skipped"); continue
        for q in searches:
            sk = f"{site}:{q}"
            after = state.get(sk) or state.get(site)
            page = 1
            while True:
                if time.time() - t0 > a.minutes * 60:
                    partial = True; break
                p = {"search": q, "per_page": 100, "page": page, "_fields": "id,date,link,title,content", "orderby": "date", "order": "asc"}
                if after:
                    p["after"] = after
                r = http(api, p)
                if r is None:
                    break
                posts = r.json()
                for x in posts:
                    t = txt(x["content"]["rendered"])
                    pd_ = date.fromisoformat(x["date"][:10])
                    new += (parse_pt if site == "pt" else parse_en)(t, pd_, x["link"])
                    read += 1
                    state[sk] = max(filter(None, [state.get(sk), x["date"]]))
                tp = int(r.headers.get("X-WP-TotalPages", "1") or 1)
                print(f"  {site} '{q}' page {page}/{tp}: {len(posts)} posts, to {state.get(sk, '-')[:10]}", flush=True)
                save(old, new, state)
                if page >= tp or not posts:
                    break
                page += 1
                time.sleep(2)
            state.pop(site, None)
    rows = save(old, new, state)
    print(f"SAFRAS: {read} posts read, {len(new)} quotes found, {len(rows)} in file, latest {rows[-1]['quote_date'] if rows else '-'}"
          + (" (time budget reached; the next run carries on)" if partial else ""))


if __name__ == "__main__":
    main()
