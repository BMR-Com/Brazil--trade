#!/usr/bin/env python3
"""Capture each new ICE Sugar No. 11 expiry delivery (total lots and tonnes, named deliverers and receivers) from free
news mirrors of the Reuters tender story. Standard library only; runs in .github/workflows/sugar_deliveries.yml.

ICE publishes no public per-firm delivery file for Sugar No. 11 (its notice goes to members); the firm names reach the
public through trade reports on expiry day (preliminary, from traders) and the exchange total a day or two later.

Runs only from the last trading day (LTD) to LTD + 6 ICE business days; any other day it exits at once.
Sources, in order: NovaCana sugar news lists (Portuguese Reuters translations, full text), ChiniMandi RSS, Business
Recorder markets RSS. robots.txt is read first for each host.
Writes data/sugar/deliveries/auto/sb_auto_sources.csv and sb_auto_firms.csv (entry=auto; a hand-entered row in
sb_sources.csv / sb_firms.csv for the same expiry and firm always wins in models/sugar_deliveries.py) and
auto/capture_status.json (repo only).

  python pipelines/sugar_deliveries.py              # due check, then capture
  python pipelines/sugar_deliveries.py --due        # print the window state only
  python pipelines/sugar_deliveries.py --contract SBV26 --force
  python pipelines/sugar_deliveries.py --selftest   # parser checks on stored sample sentences
"""
import csv
import html
import json
import re
import sys
import urllib.request
import urllib.robotparser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "data/sugar/deliveries"
A = D / "auto"
UA = "Mozilla/5.0 (compatible; softs-desk-bot/1.0)"
WINDOW_BD = 6
MONTHS = {"H": 3, "K": 5, "N": 7, "V": 10}
EN = {3: "march", 5: "may", 7: "july", 10: "october"}
PT = {3: "mar[cç]o", 5: "maio", 7: "julho", 10: "outubro"}
LISTS = ["https://www.novacana.com/n/acucar/exportacao", "https://www.novacana.com/n/acucar/mercado", "https://www.novacana.com/n/acucar"]
FEEDS = ["https://www.chinimandi.com/feed/", "https://www.brecorder.com/feeds/markets"]
ALIASES = [  # (pattern, firm name used in the dataset)
    (r"Louis Dreyfus|\bLDC\b|Term Commodities", "Louis Dreyfus"), (r"\bWilmar\b", "Wilmar"), (r"\bAlvean\b", "Alvean"),
    (r"\bSucden\b|Sucres et Denr", "Sucden"), (r"\bCOFCO\b|\bCofco\b", "COFCO International"), (r"\bBTG\b", "BTG Pactual"),
    (r"\bViterra\b|Glencore", "Viterra"), (r"\bCargill\b", "Cargill"), (r"ED&F Man|ED&amp;F Man|\bEDF Man\b|Volcafe", "ED&F Man"),
    (r"\bCzarnikow\b", "Czarnikow"), (r"\bBunge\b", "Bunge"), (r"\bRa[ií]zen\b", "Raizen"), (r"\bOlam\b|\bOFI\b", "Olam"),
    (r"\bTate (&|and) Lyle\b", "Tate & Lyle"), (r"\bCopersucar\b", "Copersucar"), (r"\bMacquarie\b", "Macquarie"),
    (r"\bEnerfo\b", "Enerfo"), (r"\bCSC Commodities\b", "CSC Commodities"), (r"\bAmaggi\b", "Amaggi"), (r"\bMarex\b", "Marex"),
    (r"\bTereos\b", "Tereos"), (r"\bSodrugestvo\b", "Sodrugestvo"), (r"\bHedgepoint\b|\bStoneX\b", "StoneX"),
]
DELIV = r"deliver|seller|tender|entreg|fornecedor|vendedor"
RECV = r"receiv|taker|buyer|took|stopper|receb|destinat|compradora|receptor|tomador"
OFFICIAL = r"said the exchange|exchange said|exchange data|by the exchange|in a notice|informou a bolsa|segundo a bolsa|dados (oficiais|da bolsa)|a bolsa informou"
SRC_COLS = ["contract", "expiry_date", "figure", "lots", "tonnes", "lots_derived", "origins", "ports", "expiry_settle_cents", "notes", "source", "source_date", "url", "entry", "added"]
FIRM_COLS = ["contract", "expiry_date", "side", "firm", "firm_type", "lots", "tonnes", "share_pct", "rank_text", "figure", "source", "source_date", "url", "entry", "added"]


# ---------------------------------------------------------------- calendar
def holidays():
    try:
        return set(json.loads((ROOT / "data/release_calendar.json").read_text())["holidays"]["ice_us_softs"])
    except Exception:
        return set()


def is_bd(d, H):
    return d.weekday() < 5 and str(d) not in H


def ltd(code, yy, H):
    """LTD = last business day of the month before the delivery month."""
    m, y = MONTHS[code], 2000 + yy
    d = date(y, m, 1) - timedelta(days=1)
    while not is_bd(d, H):
        d -= timedelta(days=1)
    return d


def add_bd(d, n, H):
    while n > 0:
        d += timedelta(days=1)
        n -= is_bd(d, H)
    return d


def window(today, H):
    """Contract whose capture window (LTD .. LTD + WINDOW_BD business days) contains today."""
    for yy in (today.year % 100 - 1, today.year % 100, today.year % 100 + 1):
        for code in MONTHS:
            l = ltd(code, yy, H)
            if l <= today <= add_bd(l, WINDOW_BD, H):
                return f"SB{code}{yy:02d}", l
    return None, None


# ---------------------------------------------------------------- fetching
_robots = {}


def allowed(url):
    host = "{0.scheme}://{0.netloc}".format(urlparse(url))
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser(host + "/robots.txt")
        try:
            req = urllib.request.Request(host + "/robots.txt", headers={"User-Agent": UA})
            rp.parse(urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace").splitlines())
        except Exception:
            rp = None  # no robots file reachable: treat as allowed
        _robots[host] = rp
    rp = _robots[host]
    return rp is None or rp.can_fetch(UA, url)


def get(url):
    if not allowed(url):
        raise PermissionError(f"robots.txt disallows {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en,pt;q=0.8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def text_of(page):
    page = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", page)
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", page) or [page]
    t = " ".join(re.sub(r"(?s)<[^>]+>", " ", p) for p in paras)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def pub_date(page):
    m = re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', page) or re.search(r'article:published_time"\s+content="(\d{4}-\d{2}-\d{2})', page) \
        or re.search(r'<time[^>]+datetime="(\d{4}-\d{2}-\d{2})', page)
    return m.group(1) if m else ""


# ---------------------------------------------------------------- parsing
def n_en(s):
    return float(s.replace(",", ""))


def n_pt(s, mil=False):
    s = s.strip()
    v = float(s.replace(".", "").replace(",", ".")) if "," in s else float(s.replace(".", "")) if re.fullmatch(r"\d{1,3}(\.\d{3})+", s) else float(s)
    return v * 1000 if mil else v


def number(s, pt):
    """'13,27 mil' (pt) -> 13270; '9.267' (pt) -> 9267; '30,032' (en) -> 30032; '1.52 million' (en) -> 1.52e6."""
    s = s.strip()
    m = re.match(r"([\d.,]+)\s*(million|milh[ãa]o|milh[õo]es|mln|mn|mil)?", s, re.I)
    if not m:
        return None
    v, u = m.group(1).rstrip(".,"), (m.group(2) or "").lower()
    try:
        x = n_pt(v) if pt else n_en(v)
    except ValueError:
        return None
    if u == "mil":
        x *= 1e3
    elif u:
        x *= 1e6
    return x


def sentences(t):
    return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-ZÀ-Ú\"“])", t) if s.strip()]


def parse(t, month):
    """Totals and firms from one article's text. Returns None if it is not about this month's Sugar No. 11 tender."""
    low = t.lower()
    pt = bool(re.search(r"\b(açúcar|lotes|toneladas|entregas?)\b", low))
    mon = PT[month] if pt else EN[month]
    if not re.search(mon, low) or not re.search(r"sugar|açúcar|acucar", low) or not re.search(r"deliver|entreg|tender", low):
        return None
    if re.search(r"white sugar|açúcar branco|london|londres", low) and not re.search(r"raw sugar|açúcar bruto|demerara|vhp", low):
        return None
    lot_re = r"([\d][\d.,]*\s*(?:mil)?)\s+(?:lotes|lots|contracts|contratos)"
    t_re = r"([\d][\d.,]*\s*(?:million|milh[ãa]o|milh[õo]es|mn|mil)?)\s*(?:de\s+)?(?:metric\s+)?(?:tons|tonnes|toneladas|t)\b"
    out = {"lots": None, "tonnes": None, "official": bool(re.search(OFFICIAL, low)), "firms": [], "pt": pt}
    for s in sentences(t):
        sl = s.lower()
        if out["lots"] is None and re.search(r"total|reach|amount|seen at|estimad|atingi|somar|foram|chegou|ficaram|deliveries|entregas", sl) and not re.search(r"largest|maior|principal|sole|única", sl):
            m = re.search(lot_re, s, re.I)
            if m:
                out["lots"] = number(m.group(1), pt)
                m2 = re.search(t_re, s[m.end():], re.I)
                if m2:
                    out["tonnes"] = number(m2.group(1), pt)
        hits = [(mm.start(), name) for pat, name in ALIASES for mm in re.finditer(pat, s)]
        for pos, name in sorted(hits):
            if any(f["firm"] == name for f in out["firms"]):
                continue
            after = s[pos:]
            dpos = [m.start() for m in re.finditer(DELIV, after, re.I)]
            rpos = [m.start() for m in re.finditer(RECV, after, re.I)]
            if not dpos and not rpos:
                continue
            side = "deliverer" if dpos and (not rpos or dpos[0] < rpos[0]) else "receiver"
            seg = after[:160]
            nxt = [m.start() for _, nm in ALIASES if nm != name for m in re.finditer(_, seg)]
            if nxt:
                seg = seg[:min(nxt)]
            ml = re.search(lot_re, seg, re.I)
            mt = re.search(t_re, seg, re.I)
            rank = next((w for w in ("sole", "única", "only", "largest", "biggest", "maior", "main", "principal") if w in seg.lower()), "")
            out["firms"].append({"firm": name, "side": side, "lots": number(ml.group(1), pt) if ml else None,
                                 "tonnes": number(mt.group(1), pt) if (mt and not ml) else None,
                                 "rank_text": {"única": "sole", "only": "sole", "biggest": "largest", "maior": "largest", "principal": "main"}.get(rank, rank)})
    if out["lots"] is None and not out["firms"]:
        return None
    return out


SAMPLES = [  # (text, month, expect lots, expect firm checks)
    ("Raw sugar deliveries on expiry of the October contract on ICE totalled 30,032 lots, or around 1.52 million metric tons, according to preliminary information from two sugar traders. Louis Dreyfus was the largest deliverer with 10,321 lots. COFCO International was the largest receiver with 13,977 contracts.",
     10, 30032, {("Louis Dreyfus", "deliverer"): 10321, ("COFCO International", "receiver"): 13977}),
    ("As entregas de açúcar bruto contra o vencimento do contrato de julho na ICE foram estimadas em cerca de 21,2 mil lotes, ou quase 1,1 milhão de toneladas, de acordo com informações preliminares de três tradings. A Wilmar foi considerada a maior fornecedora do açúcar, com 13,27 mil lotes, enquanto a Alvean seria a principal recebedora, com 15,74 mil lotes.",
     7, 21200, {("Wilmar", "deliverer"): 13270, ("Alvean", "receiver"): 15740}),
    ("A entrega física de açúcar contra o vencimento do contrato de março na ICE atingiu 17.582 lotes, ou 893.216 toneladas, informou a bolsa.",
     3, 17582, {}),
    ("Deliveries of raw sugar on the expiration of the May contract on ICE exchange totalled 9,520 lots, or 483,643 metric tons, said the exchange in a notice. Sucden was the biggest deliverer, with 285,400 tonnes, while Alvean was seen as the sole receiver.",
     5, 9520, {("Sucden", "deliverer"): None, ("Alvean", "receiver"): None}),
]


def selftest():
    bad = 0
    for t, m, lots, firms in SAMPLES:
        r = parse(t, m)
        got = {(f["firm"], f["side"]): f["lots"] for f in (r or {}).get("firms", [])}
        ok = r is not None and r["lots"] == lots and all(k in got and (v is None or got[k] == v) for k, v in firms.items())
        bad += not ok
        print("ok " if ok else "BAD", m, r and r["lots"], r and r["tonnes"], r and r["official"], got)
    print("pt tonnes check:", parse(SAMPLES[1][0], 7)["tonnes"], parse(SAMPLES[2][0], 3)["tonnes"])
    sys.exit(1 if bad else 0)


# ---------------------------------------------------------------- discovery
def candidates(since):
    urls, errs = [], []
    for L in LISTS:
        try:
            page = get(L)
            for h in re.findall(r'href="([^"]+/noticias/[^"#?]+)"', page):
                u = urljoin(L, h)
                s = u.lower()
                if re.search(r"acucar", s) and re.search(r"entreg|vencimento|expira|contrato", s) and u not in urls:
                    urls.append(u)
        except Exception as e:
            errs.append(f"{L}: {e}")
    for F in FEEDS:
        try:
            x = get(F)
            for it in re.findall(r"(?is)<item>(.*?)</item>", x):
                title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(r"(?is)<title>(.*?)</title>", it) or [None, ""])[1]))
                link = (re.search(r"(?is)<link>(.*?)</link>", it) or [None, ""])[1].strip()
                pd_ = (re.search(r"(?is)<pubDate>(.*?)</pubDate>", it) or [None, ""])[1]
                try:
                    d = datetime.strptime(pd_.strip()[:25], "%a, %d %b %Y %H:%M:%S").date()
                except ValueError:
                    d = None
                if link and re.search(r"sugar", title, re.I) and re.search(r"deliver|tender|expir", title, re.I) and (d is None or d >= since) and link not in urls:
                    urls.append(link)
        except Exception as e:
            errs.append(f"{F}: {e}")
    return urls, errs


# ---------------------------------------------------------------- store
def load(p):
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


def save(p, rows, cols):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows(rows)


def fmt(v):
    return "" if v is None else str(int(round(v)))


def capture(contract, l, force=False):
    today = date.today()
    st = {"run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "contract": contract, "ltd": str(l), "checked": [], "found": [], "errors": []}
    man = [r for r in load(D / "sb_sources.csv") if r["contract"] == contract]
    if not force and any(r["figure"] == "official" for r in man) and any(r["contract"] == contract for r in load(D / "sb_firms.csv")):
        st["skipped"] = "hand-entered official total and firms already present"
        return st
    S, F = load(A / "sb_auto_sources.csv"), load(A / "sb_auto_firms.csv")
    seen = {r["url"] for r in S} | {r["url"] for r in F}
    urls, st["errors"] = candidates(l - timedelta(days=1))
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
        if pdte and pdte < str(l):
            continue
        r = parse(text_of(page), MONTHS[contract[2]])
        if not r:
            continue
        src = urlparse(u).netloc.replace("www.", "")
        fig = "official" if r["official"] else "preliminary"
        added = str(today)
        if r["lots"] or r["tonnes"]:
            S.append({"contract": contract, "expiry_date": str(l), "figure": fig, "lots": fmt(r["lots"]), "tonnes": fmt(r["tonnes"]), "lots_derived": "",
                      "origins": "", "ports": "", "expiry_settle_cents": "", "notes": "parsed by the capture job; check against the article",
                      "source": src, "source_date": pdte or added, "url": u, "entry": "auto", "added": added})
        for f in r["firms"]:
            F.append({"contract": contract, "expiry_date": str(l), "side": f["side"], "firm": f["firm"], "firm_type": "merchant", "lots": fmt(f["lots"]),
                      "tonnes": fmt(f["tonnes"]), "share_pct": "", "rank_text": f["rank_text"], "figure": "preliminary", "source": src,
                      "source_date": pdte or added, "url": u, "entry": "auto", "added": added})
        st["found"].append({"url": u, "lots": r["lots"], "tonnes": r["tonnes"], "figure": fig, "firms": [(f["firm"], f["side"], f["lots"]) for f in r["firms"]]})
    save(A / "sb_auto_sources.csv", S, SRC_COLS)
    save(A / "sb_auto_firms.csv", F, FIRM_COLS)
    return st


def main():
    if "--selftest" in sys.argv:
        selftest()
    H = holidays()
    today = date.today()
    if "--contract" in sys.argv:
        c = sys.argv[sys.argv.index("--contract") + 1].upper()
        contract, l = c, ltd(c[2], int(c[3:5]), H)
    else:
        contract, l = window(today, H)
    if "--due" in sys.argv or contract is None:
        print(f"due={'yes' if contract else 'no'} {contract or ''} {l or ''}")
        return
    if today < l and "--force" not in sys.argv:
        print("before the last trading day; nothing to do")
        return
    st = capture(contract, l, force="--force" in sys.argv)
    A.mkdir(parents=True, exist_ok=True)
    (A / "capture_status.json").write_text(json.dumps(st, indent=1, ensure_ascii=False))
    print(json.dumps(st, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    main()
