"""Sucden Financial coffee outlook -> headline numbers and revisions (public summary).

Usage
  python models/sucden_coffee.py --url  <report page URL>            # fetch and parse (may be blocked on runners)
  python models/sucden_coffee.py --html <saved page.html> [--url U]  # parse a saved copy (browser / WebFetch)
  python models/sucden_coffee.py --text <plain text file> --date YYYY-MM-DD --url U --title T
  add --dry-run to print without writing; add --lab PATH to also write the matched evidence (private, keep outside repo)

What it does
  1. Pulls the report date (article:published_time), title and the plain text.
  2. Finds headline numbers by season: world production, world consumption, world balance (surplus +/deficit -),
     Brazil crop (total / arabica / robusta-conilon), Vietnam, Colombia. Each match must name a season (e.g. 2026/27
     or 26/27) in the same sentence; values are million 60-kg bags.
  3. Compares with the previous headline in data/coffee/reports/sucden.json and appends revisions
     (metric, season, previous -> new, report date) to that file. Unchanged numbers are recorded as "maintained".

The public file keeps only the latest headline figures and the revisions list; the full table by report date lives in
the private Lab. The automatic match is a first pass: review the printed table before committing, and fix a figure with
--set metric:season=value (repeatable) when the wording defeats the patterns.
"""
import argparse
import html as htmlmod
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "coffee", "reports", "sucden.json")   # shared with models/reports_store.py (key points)

SEASON = re.compile(r"\b(?:20)?(\d{2})\s?[/-]\s?(?:20)?(\d{2})\b")
LABEL = {"world_production": "World production", "world_consumption": "World consumption", "world_balance": "World balance (+ surplus / − deficit)",
         "brazil_total": "Brazil crop", "brazil_arabica": "Brazil arabica", "brazil_robusta": "Brazil conilon (robusta)",
         "vietnam": "Vietnam crop", "colombia": "Colombia crop", "brazil_carryover": "Brazil carryover, end-June"}


def season_of(s):
    m = SEASON.search(s)
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if (a + 1) % 100 != b:
        return None
    return f"20{a:02d}/{b:02d}"


def page_text(raw):
    raw = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)
    m = re.search(r"(?is)<main[^>]*>(.*?)</main>", raw)
    body = m.group(1) if m else raw
    t = re.sub(r"(?s)<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", htmlmod.unescape(t)).strip()


def meta(raw, prop):
    m = re.search(r'<meta[^>]+(?:property|name)="%s"[^>]+content="([^"]+)"' % re.escape(prop), raw) or \
        re.search(r'<meta[^>]+content="([^"]+)"[^>]+(?:property|name)="%s"' % re.escape(prop), raw)
    return m.group(1) if m else None


RANGE = re.compile(r"(\d{1,3}(?:\.\d{1,3})?)(?:\s?(?:–|-|to)\s?(\d{1,3}(?:\.\d{1,3})?))?\s?(?:m|M|mn|mln|million|mill)\.?\s?(?:x\s?60\s?kg\s)?bags?")
COUNTRY = [("brazil", r"brazil"), ("vietnam", r"vietnam"), ("colombia", r"colombia"), ("other", r"indonesia|honduras|central america|ethiopia|uganda|india\b|peru|guatemala|nicaragua|mexico")]


def extract(text):
    """Return {metric: {season: (value, sentence)}} - first confident match per metric/season.

    Each 'NN m bags' figure (or range, taken at its midpoint) is tied to the nearest season written before it in the
    sentence and to the country last named in the text (section headings count), then classified by the words around it.
    """
    found = {}
    ctx, last_season = None, None
    for s in re.split(r"(?<=[.!?])\s+", text):
        low = s.lower()
        named = [(low.rfind(k) if re.search(rx, low) else -1, k) for k, rx in COUNTRY]
        named = [x for x in named if x[0] >= 0]
        first_ctx = ctx
        if named:
            ctx = max(named)[1]
        if len(s) > 450 or "bag" not in low:
            continue
        seasons = [(m.start(), season_of(m.group(0))) for m in SEASON.finditer(s)]
        seasons = [x for x in seasons if x[1]]
        inherited = False
        if seasons:
            last_season = seasons[-1][1]
        elif last_season and re.search(r"global|world|total production", low):
            seasons, inherited = [(-1, last_season)], True       # world totals often omit the season; take the last one named
        else:
            continue
        for m in RANGE.finditer(s):
            a, b = float(m.group(1)), m.group(2)
            v = (a + float(b)) / 2 if b else a
            before = [x for x in seasons if x[0] < m.start()]
            se = (before[-1] if before else seasons[0])[1]
            w0, w1 = low[max(0, m.start() - 70):m.start()], low[m.end():m.end() + 45]
            win = w0[-60:] + " # " + w1[:20]          # classify on the words just before the figure
            c = ctx if ctx else first_ctx
            near_c = [k for k, rx in COUNTRY if re.search(rx, w0 + w1)]
            if near_c:
                c = near_c[0]
            key = None
            if re.search(r"deficit|surplus", w1[:25] + w0[-30:]):
                if "brazil alone" in low or "in brazil" in low or not re.search(r"global|world|balance|cycle|season|market|our", low):
                    continue
                word = "deficit" if "deficit" in (w1[:25] + w0[-30:]) else "surplus"
                if "deficit" in w1[:25] and "surplus" in w1[:25]:
                    word = "deficit" if w1.find("deficit") < w1.find("surplus") else "surplus"
                key, v = "world_balance", (-v if word == "deficit" else v)
            elif v >= 140 and re.search(r"consumption|demand", win) and not re.search(r"production|supply", w0[-40:]):
                key = "world_consumption"
            elif v >= 140 and re.search(r"production|supply|crop|output", win):
                key = "world_production"
            elif c == "brazil" and re.match(r"\s?(of |for )?arabica", w1) and 20 <= v <= 60:
                key = "brazil_arabica"
            elif c == "brazil" and re.match(r"\s?(of |for )?(conil+on|robusta)", w1) and 8 <= v <= 30:
                key = "brazil_robusta"
            elif c == "brazil" and re.search(r"conil+on|robusta", w0[-60:]) and re.search(r"crop|estimate", w0) and 8 <= v <= 30:
                key = "brazil_robusta"
            elif c == "brazil" and 40 <= v <= 95 and re.search(r"crop|production|produce|projection|estimate|expectation", win) \
                    and not re.search(r"export|consum|ship|carry|stock|demand|availab|disappear|need", w0[-60:]):
                key = "brazil_total"
            elif c == "vietnam" and 18 <= v <= 36 and re.search(r"crop|production|estimate", win) and not re.search(r"export|consum|ship|sold", w0[-60:]):
                key = "vietnam"
            elif c == "colombia" and 8 <= v <= 16 and re.search(r"crop|production|outlook|estimate", win) and not re.search(r"export|consum|ship", w0[-60:]):
                key = "colombia"
            if inherited and not key.startswith("world"):
                key = None
            if key:
                found.setdefault(key, {}).setdefault(se, (round(v, 3), s))
    return found


def load_prev():
    if os.path.exists(OUT):
        with open(OUT) as f:
            return json.load(f)
    return {"source": "Sucden Financial", "name": "Sucden Financial: Coffee Market Outlook / Coffee Crop Update",
            "home": "https://www.sucdenfinancial.com/en/market-insights/soft-commodities-outlook/coffee-market-outlook/",
            "cadence": "about three outlooks a year plus crop updates", "entries": [], "reports_seen": [], "revisions": [], "latest": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url"); ap.add_argument("--html"); ap.add_argument("--text"); ap.add_argument("--date"); ap.add_argument("--title")
    ap.add_argument("--set", action="append", default=[]); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--lab")
    ap.add_argument("--summary", help="JSON file with own-words key points: {production, consumption, stocks, price_drivers: [..]}")
    a = ap.parse_args()
    raw = None
    if a.html:
        raw = open(a.html, encoding="utf-8", errors="ignore").read()
    elif a.url and not a.text:
        import requests
        r = requests.get(a.url, timeout=40, headers={"User-Agent": "Mozilla/5.0 (research desk)"})
        r.raise_for_status()
        raw = r.text
    if raw is not None:
        text = page_text(raw)
        date = a.date or (meta(raw, "article:published_time") or "")[:10]
        title = a.title or (meta(raw, "og:title") or "").split("|")[0].strip()
    elif a.text:
        text = open(a.text, encoding="utf-8").read()
        date, title = a.date, a.title
    else:
        raise SystemExit("give --url, --html or --text")
    if not date:
        raise SystemExit("report date not found; pass --date")
    found = extract(text)
    head = {k: {s: v for s, (v, _) in d.items()} for k, d in found.items()}
    for kv in a.set:
        k, rest = kv.split(":", 1); s, v = rest.split("=")
        head.setdefault(k, {})[s] = float(v)
    if not head:
        raise SystemExit("no headline numbers recognised; check the text or use --set")
    P = load_prev()
    prev = (P.get("latest") or {}).get("headline", {})
    revs = []
    for k, d in head.items():
        for s, v in d.items():
            pv = prev.get(k, {}).get(s)
            if pv is None:
                revs.append({"report_date": date, "metric": k, "label": LABEL[k], "season": s, "previous": None, "new": v, "change": None, "kind": "new"})
            elif abs(pv - v) > 1e-9:
                revs.append({"report_date": date, "metric": k, "label": LABEL[k], "season": s, "previous": pv, "new": v, "change": round(v - pv, 3), "kind": "revised"})
            else:
                revs.append({"report_date": date, "metric": k, "label": LABEL[k], "season": s, "previous": pv, "new": v, "change": 0.0, "kind": "maintained"})
    print(f"{date}  {title}")
    for r_ in revs:
        print(f"  {r_['label']:<40} {r_['season']}  {r_['previous']} -> {r_['new']}  ({r_['kind']})")
    if a.lab:
        with open(a.lab, "w") as f:
            json.dump({"date": date, "url": a.url, "evidence": {k: {s: e for s, (_, e) in d.items()} for k, d in found.items()}}, f, indent=1)
    if a.dry_run:
        return 0
    if date in P.get("reports_seen", []):
        P["revisions"] = [x for x in P["revisions"] if x["report_date"] != date]
    else:
        P.setdefault("reports_seen", []).append(date)
    merged = {k: dict(v) for k, v in prev.items()}
    for k, d in head.items():
        merged.setdefault(k, {}).update(d)
    summ = json.load(open(a.summary)) if a.summary else (P.get("latest") or {}).get("summary") if (P.get("latest") or {}).get("date") == date else None
    old = P.get("latest") or {}
    lines = old.get("balance_lines") if old.get("date") == date else [
        {"line": LABEL[k], "season": s_, "value": f"{v:+g}m bags" if k == "world_balance" else f"{v:g}m bags"}
        for k in LABEL if k in head for s_, v in sorted(head[k].items())]
    P["latest"] = {"date": date, "title": title, "url": a.url, "headline": merged, "this_report": head, "summary": summ, "balance_lines": lines}
    P["revisions"] = sorted(P["revisions"] + revs, key=lambda x: (x["report_date"], x["metric"], x["season"]), reverse=True)
    P["built"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(P, f, indent=1, ensure_ascii=False)
    print("wrote", OUT)


if __name__ == "__main__":
    sys.exit(main())
