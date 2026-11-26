#!/usr/bin/env python3
"""Capture delivery figures for Coffee C (KC), Cotton No. 2 (CT) and London White Sugar No. 5 (WS) from free news
pages during each delivery window. Standard library only; runs in .github/workflows/softs_deliveries.yml.

ICE publishes no free per-firm delivery file for these contracts. What reaches the public:
  CT, KC  The PRICE Futures Group's daily Softs Report (blog.pricegroup.com, robots.txt allows all): in its Cotton and
      Coffee sections, "ICE said that N notices were posted for delivery against <Month> futures and that total
      deliveries for the month are now N contracts". Posts are found from the blog's date archive pages
      (/YYYY/MM/DD/), because a post's slug can carry the previous day's date. Counts only, no firm names.
  CT  Fibre2Fashion's daily ICE cotton report: notices issued per day, running totals, sometimes the issuing firm.
  KC  StoneX's Daily Coffee Report: notices per day and running totals, counts of issuers/stoppers (no names).
      (Both refuse the job's requests from GitHub's runners as of Nov 2026: 405 and 403. Kept in case that changes.)
  WS  Reuters tender stories mirrored by NovaCana / ChiniMandi / Business Recorder: total tonnes, origins, and the
      deliverers and receivers named by traders (preliminary) or in the exchange data (clearing members).
The spot-month open interest that brackets each delivery comes from the desk's own daily ICE data and is added by
models/softs_deliveries.py, so it does not depend on these pages.

Windows (ICE US business days): CT first notice day - 1 .. last trading day + 3; KC first notice day .. LTD + 2;
WS LTD .. LTD + 6. Outside every window the script exits at once. robots.txt is read first for each host.
Writes <dir>/auto/<p>_auto_sources.csv and <p>_auto_firms.csv (entry=auto; hand-entered rows win in the builder) and
<dir>/auto/capture_status.json (repo only).

  python pipelines/softs_deliveries.py              # due check, then capture every market in its window
  python pipelines/softs_deliveries.py --due        # print window state only
  python pipelines/softs_deliveries.py --contract CTH27 --force
  python pipelines/softs_deliveries.py --contract CTZ26,KCZ26,CTN26 --force   # several, e.g. a backfill
  python pipelines/softs_deliveries.py --selftest
"""
import html
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
import importlib.util  # noqa: E402


def _mod(name, path):  # load by path: the builder and this script share a file name
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


_sb = _mod("sb_capture", "pipelines/sugar_deliveries.py")
_bd = _mod("softs_deliveries_model", "models/softs_deliveries.py")
get, text_of, pub_date, number, sentences, load, save, fmt = _sb.get, _sb.text_of, _sb.pub_date, _sb.number, _sb.sentences, _sb.load, _sb.save, _sb.fmt
SRC_COLS, FIRM_COLS = _sb.SRC_COLS, _sb.FIRM_COLS
MARKETS, MON, dates, next_bd, prev_bd, norm = _bd.MARKETS, _bd.MON, _bd.dates, _bd.next_bd, _bd.prev_bd, _bd.norm

SRC = SRC_COLS[:3] + ["kind"] + SRC_COLS[3:]
EN = {3: "march", 5: "may", 7: "july", 8: "august", 9: "september", 10: "october", 12: "december"}
PT = {3: "mar[cç]o", 5: "maio", 8: "agosto", 10: "outubro", 12: "dezembro"}
CLEARING = r"BNP|Marex|Macquarie|ADM Investor|StoneX|FCStone|Sucden Financial|Capital Markets|Wells Fargo|RJO|R\.J\. O|Société Générale|Newedge|Goldman|J\.?P\.? ?Morgan|Morgan Stanley|ABN|Rabo|Wedbush|Advantage|Phillip"
PAGES = {
    "CT": ["https://www.fibre2fashion.com/news/cotton-news/", "https://www.fibre2fashion.com/news/textile-news"],
    "KC": ["https://www.stonex.com/en/insights/", "https://www.stonex.com/en-us/insights/"],
    "WS": ["https://www.novacana.com/n/acucar/exportacao", "https://www.novacana.com/n/acucar/mercado", "https://www.novacana.com/n/acucar"],
}
FEEDS = {"WS": ["https://www.chinimandi.com/feed/", "https://www.brecorder.com/feeds/markets"]}
LINK = {"CT": r"cotton[^\"']*-\d+-newsdetails\.htm", "KC": r"daily-coffee-report", "WS": r"a[cç]ucar[^\"']*(branco|londres|refinado)"}
TITLE = {"WS": r"white sugar|refined sugar|London sugar"}


# ---------------------------------------------------------------- windows
def window(sym, c, today):
    fnd, ltd, _ = dates(sym, c[-3], int(c[-2:]))
    if sym == "CT":
        return prev_bd(fnd, 1), next_bd(ltd, 3), ltd
    if sym == "KC":
        return fnd, next_bd(ltd, 2), ltd
    return ltd, next_bd(ltd, 6), ltd


def due(today):
    out = []
    for sym, M in MARKETS.items():
        for yy in (today.year % 100 - 1, today.year % 100, today.year % 100 + 1):
            for code in M["months"]:
                c = f"{'W' if sym == 'WS' else sym}{code}{yy:02d}"
                a, b, l = window(sym, c, today)
                if a <= today <= b:
                    out.append((sym, c, l))
    return out


# ---------------------------------------------------------------- parsers (return rows of {kind, lots, tonnes, figure, note} and firms)
def n(s):
    return number(s, False)


def parse_ct(t, month):
    low = t.lower()
    if "cotton" not in low or not re.search(EN[month], low) or "notice" not in low:
        return None
    figs, firms = [], []
    for s in sentences(t):
        sl = s.lower()
        if not re.search(EN[month][:3], sl) and "notice" not in sl:
            continue
        m = re.search(r"total (?:delivery )?notices (?:now )?(?:stand|stood) at (\d[\d,]*)", s, re.I) or \
            re.search(r"bringing the total[^.]*? to (\d[\d,]*)", s, re.I)
        if m:
            figs.append({"kind": "running", "lots": n(m.group(1)), "note": s[:240]})
            continue
        m = re.search(r"(\d[\d,]*) (?:delivery )?notices (?:were |have been )?(?:issued|tendered|posted)", s, re.I) or \
            re.search(r"notices for (?:just )?(\d[\d,]*) (?:lots|contracts)", s, re.I)
        if m:
            k = "fnd" if re.search(r"first notice day|first day", sl) else "partial"
            if re.search(r"expected|will be", sl):
                k = "fnd" if k == "fnd" else "context"
            figs.append({"kind": k, "lots": n(m.group(1)), "note": s[:240]})
            mi = re.search(r"issued by ([A-Z][A-Za-z&.' ]{2,40}?)(?=[,.;]| and | reportedly| on |$)", s)
            if mi:
                f = mi.group(1).strip()
                firms.append({"firm": f, "side": "deliverer", "type": "clearing" if re.search(CLEARING, f) else "other",
                              "lots": n(m.group(1)), "rank_text": "issuer named in the daily report"})
            ms = re.search(r"stopped by ([A-Z][A-Za-z&.' ]{2,40}?)(?=[,.;]| and |$)", s)
            if ms:
                f = ms.group(1).strip()
                firms.append({"firm": f, "side": "receiver", "type": "clearing" if re.search(CLEARING, f) else "other",
                              "lots": None, "rank_text": "stopper named in the daily report"})
    return {"figs": figs, "firms": firms, "official": False} if figs or firms else None


def parse_kc(t, month):
    low = t.lower()
    if not re.search(r"arabica|coffee", low) or "notice" not in low and "tender" not in low:
        return None
    figs = []
    for s in sentences(t):
        sl = s.lower()
        m = re.search(r"(?:expired|concluded)[^.]*? with (?:a total of )?(\d[\d,]*) lots", s, re.I)
        if m and re.search(EN[month], sl):
            figs.append({"kind": "total", "lots": n(m.group(1)), "note": s[:240]})
            continue
        m = re.search(r"bringing the total[^.]*? to (\d[\d,]*)", s, re.I)
        if m:
            figs.append({"kind": "running", "lots": n(m.group(1)), "note": s[:240]})
            continue
        m = re.search(r"(\d[\d,]*) (?:delivery )?notices (?:were )?(?:issued|reported|posted) today", s, re.I) or \
            re.search(r"(\d[\d,]*) lots of arabica were (?:tendered|issued)", s, re.I)
        if m:
            figs.append({"kind": "daily", "lots": n(m.group(1)), "note": s[:240]})
    return {"figs": figs, "firms": [], "official": False} if figs else None


T_RE = r"(\d[\d.,]*\s*(?:million|mil)?)\s*(?:de\s+)?(?:metric\s+)?(?:tons|tonnes|toneladas|mt)\b"


def parse_ws(t, month):
    low = t.lower()
    pt = bool(re.search(r"\b(açúcar|toneladas|entregues?)\b", low))
    if not re.search(r"white sugar|refined sugar|açúcar branco|london|londres", low) or not re.search(PT.get(month, "x") if pt else EN[month], low):
        return None
    official = bool(re.search(r"exchange data|said the exchange|informou a bolsa|dados (oficiais|da bolsa)|official exchange data", low))
    figs, firms = [], []
    for s in sentences(t):
        sl = s.lower()
        if not figs:
            m = re.search(r"(\d[\d,]*)\s+(?:lots|lotes)", s, re.I)
            mt = re.search(T_RE, s, re.I)
            if re.search(r"tender|deliver|entreg|expir|vencimento", sl) and (m or mt) and not re.search(r"largest|main|sole|maior|principal", sl):
                figs.append({"kind": "total", "lots": n(m.group(1)) if m else None, "tonnes": number(mt.group(1), pt) if mt else None, "note": s[:240]})
        for side, pat in (("deliverer", r"deliverers?|sellers?"), ("receiver", r"receivers?|takers?|buyers?")):
            for m in re.finditer(r"([A-Z][\w&.' ]{2,40}?)(?:,? and ([A-Z][\w&.' ]{2,40}?))? (?:was|were) (?:said to be |seen as |considered )?the (sole|main|largest|biggest|only|principal) (?:" + pat + r")", s):
                for f in filter(None, (m.group(1), m.group(2))):
                    firms.append({"firm": f.strip(), "side": side, "type": "merchant", "lots": None,
                                  "rank_text": {"only": "sole", "biggest": "largest", "principal": "main"}.get(m.group(3), m.group(3)), "figure": "preliminary"})
        for side, key in (("receiver", "Buyers"), ("deliverer", "Sellers")):
            m = re.search(key + r":\s*(.+?)(?=(?:Buyers|Sellers):|$)", s)
            if m:
                for f, v in re.findall(r"([A-Z][A-Za-z&.' ]{2,40}?)\s+(\d{1,3}(?:,\d{3})+|\d+)", m.group(1)):
                    firms.append({"firm": f.strip(), "side": side, "type": "clearing", "lots": None, "tonnes": n(v),
                                  "rank_text": "exchange data", "figure": "official"})
    return {"figs": figs, "firms": firms, "official": official} if figs or firms else None


# ---------------------------------------------------------------- PRICE Futures Group Softs Report (CT and KC)
PG = "https://blog.pricegroup.com"
PG_SEC = {"CT": "COTTON", "KC": "COFFEE"}
_pg_cache = {}


def _pg_get(u):
    if u not in _pg_cache:
        time.sleep(0.4)  # a backfill walks hundreds of pages: keep the pace gentle
        try:
            _pg_cache[u] = (get(u), None)
        except Exception as e:
            _pg_cache[u] = (None, f"{u}: {e}")
    return _pg_cache[u]


def full_text(page):
    """Every text node of the page, headings included (text_of keeps only <p>, and the section names may not be in one)."""
    page = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?is)<(br|/p|/h\d|/div|/li|/strong|/b)\b[^>]*>", " \n ", page)
    return re.sub(r"[ \t\r\f\v]+", " ", html.unescape(re.sub(r"(?s)<[^>]+>", " ", page))).strip()


def pg_sections(t):
    """Split a Softs Report into {COTTON: text, FCOJ: ..., COFFEE: ..., SUGAR: ..., COCOA: ...}."""
    pat = r"\b(COTTON|FCOJ|COFFEE|SUGAR|COCOA)\s+General Comments"
    hits = list(re.finditer(pat, t))
    if len(hits) < 2:
        hits = list(re.finditer(r"\b(Cotton|FCOJ|Coffee|Sugar|Cocoa)\W{0,20}General Comments", t, re.I))
    out = {}
    for i, h in enumerate(hits):
        k = h.group(1).upper()
        out.setdefault(k, t[h.start(): hits[i + 1].start() if i + 1 < len(hits) else len(t)])
    return out


def parse_pg(sec, month):
    """Daily notices and the running total for the month, from one Softs Report section."""
    figs = []
    mon = EN[month]
    for s in sentences(re.sub(r"\s+", " ", sec)):
        if re.search(r"London|ICE Europe|Robusta", s, re.I):
            continue
        d = re.search(r"(\d[\d,]*) (?:delivery )?(?:notices|contracts|lots) (?:were|was) (?:posted|tendered|issued) for delivery against (\w+) (?:futures|contracts?)", s, re.I)
        if not d or d.group(2).lower() != mon:
            continue
        r = re.search(r"deliveries for the month (?:are|is|were) now (\d[\d,]*)", s, re.I)  # "total" is sometimes mistyped
        daily, run = n(d.group(1)), n(r.group(1)) if r else None
        k = "fnd" if run is not None and daily == run and daily else "daily"
        figs.append({"kind": k, "lots": daily, "note": s[:240]})
        if run is not None:
            figs.append({"kind": "running", "lots": run, "note": s[:240]})
    return {"figs": figs, "firms": [], "official": False} if figs else None


def pg_reports(a, b):
    """(date, url, page) for each Softs Report posted from a to b, found through the date archive pages."""
    out, errs, d = [], [], a
    while d <= b:
        if d.weekday() < 5:
            arch, e = _pg_get(f"{PG}/{d:%Y/%m/%d}/")
            if e:
                if "404" not in e:
                    errs.append(e)
            else:
                for h in dict.fromkeys(re.findall(rf'href="({re.escape(PG)}/{d:%Y/%m/%d}/softs-report-[\d-]+/?)"', arch)):
                    page, e = _pg_get(h)
                    if e:
                        errs.append(e)
                    else:
                        out.append((d, h, page))
        d += timedelta(days=1)
    return out, errs


PARSE = {"CT": parse_ct, "KC": parse_kc, "WS": parse_ws}

SAMPLES = [
    ("CT", 7, "July 2026 cotton: Total delivery notices now stand at 617 contracts, all of which could be original notices. Another 56 notices were issued on the eighth notice day.",
     ("running", 617)),
    ("CT", 5, "On the May cotton contract, 123 delivery notices were issued by BNP Paribas, reportedly associated with Olam Group activity.", ("partial", 123)),
    ("KC", 12, "December Arabica expired today with 815 lots tendered to at least 6 stoppers. Largest deliveries came from Peru (200).", ("total", 815)),
    ("KC", 3, "There were 41 delivery notices reported today, bringing the total to 962 for the March arabica contract.", ("running", 962)),
    ("WS", 3, "A total of 411,200 metric tons of mostly Guatemalan white sugar has been tendered against the March contract on ICE Futures Europe, exchange data showed on Friday.",
     ("total", None)),
    ("WS", 12, "Deliveries of refined sugar against the expiry of the December contract at ICE London exchange were seen at 7,190 lots, or 359,500 tonnes, according to preliminary information from sugar traders. Louis Dreyfus and Wilmar International were said to be the main deliverers. ED&F Man was said to be the largest receiver.",
     ("total", 7190)),
]


PG_SAMPLE = ("COTTON General Comments: Cotton was higher again yesterday. Overnight News: ICE said that 24 notices were posted for delivery "
             "against December futures and that total deliveries for the month are now 262 contracts. Chart Trends: Trends in Cotton are up. "
             "FCOJ General Comments: FCOJ was lower. Overnight News: ICE said that 0 contracts were posted for delivery against January futures. "
             "COFFEE General Comments: New York and London were lower. Overnight News: ICE NY said that 0 notices were tendered for delivery against "
             "December futures and that total deliveries for the month are now 10 contracts. "
             "SUGAR General Comments: New York and London were higher. COCOA General Comments: Cocoa was lower. Overnight News: ICE NY said that 182 "
             "notices were posted for delivery against December contracts and that total deliveries for the month are now 567 contracts.")


def selftest():
    bad = 0
    secs = pg_sections(PG_SAMPLE)
    for sym, want in (("CT", [("daily", 24), ("running", 262)]), ("KC", [("daily", 0), ("running", 10)])):
        r = parse_pg(secs.get(PG_SEC[sym], ""), 12)
        got = [(f["kind"], f["lots"]) for f in (r or {}).get("figs", [])]
        ok = got == want and parse_pg(secs.get(PG_SEC[sym], ""), 3) is None
        bad += not ok
        print("ok " if ok else "BAD", sym, "pricegroup", got)
    r = parse_pg("COTTON General Comments: x. ICE said that 35 notices were posted for delivery against March futures and that total deliveries for the month are now 35 contracts.", 3)
    ok = r and [(f["kind"], f["lots"]) for f in r["figs"]] == [("fnd", 35), ("running", 35)]
    bad += not ok
    print("ok " if ok else "BAD", "CT", "pricegroup first day", r and r["figs"])
    r = parse_pg("ICE said that 10 contracts were posted for delivery against July futures and that tzotal deliveries for the month are now 225 contracts.", 7)
    ok = r and [(f["kind"], f["lots"]) for f in r["figs"]] == [("daily", 10), ("running", 225)]
    bad += not ok
    print("ok " if ok else "BAD", "CT", "pricegroup 2025 wording", r and [(f["kind"], f["lots"]) for f in r["figs"]])
    for sym, m, t, (k, lots) in SAMPLES:
        r = PARSE[sym](t, m)
        f = r["figs"][0] if r and r["figs"] else {}
        ok = f.get("kind") == k and (lots is None or f.get("lots") == lots)
        bad += not ok
        print("ok " if ok else "BAD", sym, m, f.get("kind"), f.get("lots"), f.get("tonnes"), [(x["firm"], x["side"]) for x in (r or {}).get("firms", [])])
    if bad:
        sys.exit(1)


# ---------------------------------------------------------------- discovery and capture
def candidates(sym):
    urls, errs = [], []
    for L in PAGES.get(sym, []):
        try:
            page = get(L)
            for h in re.findall(r'href="([^"#?]+)"', page):
                u = urljoin(L, h)
                if re.search(LINK[sym], u, re.I) and u not in urls:
                    urls.append(u)
        except Exception as e:
            errs.append(f"{L}: {e}")
    for F in FEEDS.get(sym, []):
        try:
            x = get(F)
            for it in re.findall(r"(?is)<item>(.*?)</item>", x):
                title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(r"(?is)<title>(.*?)</title>", it) or [None, ""])[1]))
                link = (re.search(r"(?is)<link>(.*?)</link>", it) or [None, ""])[1].strip()
                if link and re.search(TITLE[sym], title, re.I) and re.search(r"deliver|tender|expir", title, re.I) and link not in urls:
                    urls.append(link)
        except Exception as e:
            errs.append(f"{F}: {e}")
    return urls[:40], errs


def capture(sym, c, l, since, until=None):
    M = MARKETS[sym]
    A = ROOT / M["dir"] / "auto"
    p = M["p"]
    S, F = load(A / f"{p}_auto_sources.csv"), load(A / f"{p}_auto_firms.csv")
    seen = {r["url"] for r in S} | {r["url"] for r in F}
    st = {"contract": c, "ltd": str(l), "checked": [], "found": [], "errors": []}
    added = str(date.today())

    def add(r, u, src, sdate, fig):
        for f in r["figs"]:
            S.append({"contract": c, "expiry_date": str(l), "figure": fig, "kind": f["kind"], "lots": fmt(f.get("lots")), "tonnes": fmt(f.get("tonnes")),
                      "lots_derived": "", "origins": "", "ports": "", "expiry_settle_cents": "",
                      "notes": "parsed by the capture job; check against the article: " + f["note"], "source": src,
                      "source_date": sdate, "url": u, "entry": "auto", "added": added})
        for f in r["firms"]:
            F.append({"contract": c, "expiry_date": str(l), "side": f["side"], "firm": norm(f["firm"], f["type"]), "firm_type": f["type"],
                      "lots": fmt(f.get("lots")), "tonnes": fmt(f.get("tonnes")), "share_pct": "", "rank_text": f["rank_text"],
                      "figure": f.get("figure", fig), "source": src, "source_date": sdate, "url": u, "entry": "auto", "added": added})
        st["found"].append({"url": u, "figs": [(f["kind"], f.get("lots"), f.get("tonnes")) for f in r["figs"]], "firms": [(f["firm"], f["side"]) for f in r["firms"]]})

    if sym in PG_SEC:
        reps, errs = pg_reports(since, min(until or date.today(), date.today()))
        st["errors"] += errs
        for d, u, page in reps:
            st["checked"].append(u)
            if u in seen:
                continue
            secs = pg_sections(full_text(page))
            if PG_SEC[sym] not in secs:
                st["errors"].append(f"{u}: no {PG_SEC[sym].title()} section found")
                continue
            r = parse_pg(secs[PG_SEC[sym]], MON[c[-3]])
            if r:
                add(r, u, "pricegroup.com Softs Report", str(d), "approximate")
    urls, e2 = candidates(sym)
    st["errors"] += e2
    for u in urls:
        if u in seen:
            continue
        try:
            page = get(u)
        except Exception as e:
            st["errors"].append(f"{u}: {e}")
            continue
        st["checked"].append(u)
        pdte = pub_date(page)
        if pdte and pdte < str(since):
            continue
        r = PARSE[sym](text_of(page), MON[c[-3]])
        if not r:
            continue
        src = urlparse(u).netloc.replace("www.", "")
        fig = "official" if r["official"] else "approximate" if sym != "WS" else "preliminary"
        add(r, u, src, pdte or added, fig)
    save(A / f"{p}_auto_sources.csv", S, SRC)
    save(A / f"{p}_auto_firms.csv", F, FIRM_COLS)
    return st


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    today = date.today()
    if "--contract" in sys.argv:
        todo = []
        for c in sys.argv[sys.argv.index("--contract") + 1].upper().replace(" ", "").split(","):
            sym = "WS" if c.startswith("W") else c[:2]
            todo.append((sym, c, window(sym, c, today)[2]))
    else:
        todo = due(today)
    if "--due" in sys.argv or not todo:
        print("due=" + ("yes " + " ".join(c for _, c, _ in todo) if todo else "no"))
        return
    for sym, c, l in todo:
        a, b, _ = window(sym, c, today)
        try:
            # the archive walk runs to the delivery month's last business day, so a forced run after the month gets late notices too
            end = max(b, _bd.month_bds(2000 + int(c[-2:]), MON[c[-3]])[-1])
            st = capture(sym, c, l, a - timedelta(days=1), next_bd(end, 1))
        except Exception as e:  # one market's failure must not stop the others
            st = {"contract": c, "errors": [f"capture failed: {e}"]}
        st["run_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        A = ROOT / MARKETS[sym]["dir"] / "auto"
        A.mkdir(parents=True, exist_ok=True)
        (A / f"{MARKETS[sym]['p']}_capture_status.json").write_text(json.dumps(st, indent=1, ensure_ascii=False))
        print(json.dumps(st, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main()
