"""India crush collector: season-to-date sugar production releases for the Sugar > India detail tracker.

Sources, in order (every URL is checked against the site's robots.txt first; honest User-Agent; no login, no captcha):
  1. ISMA (indiansugar.com) and the Maharashtra Sugar Commissionerate (sugar.maharashtra.gov.in): reachability is
     checked and logged each run; ISMA press-release pages linked from the home page are parsed when reachable.
  2. News of the releases on ChiniMandi (WordPress search API, then the RSS feed as fallback): ISMA fortnightly
     updates ("... updates by ISMA till <date>") and Sugar Commissionerate reports for Maharashtra ("... lakh quintals").
Only the numbers, the date and the source URL are stored (no article text), in data/sugar/india_crush_auto.csv.
Hand-entered rows (data/sugar/manual/india_crush_history.csv, india.csv) always win over these.
Runs at most once a day (inside the sugar_world workflow); status in data/sugar/india_crush_status.json.
"""
import csv, html as htmlmod, json, re, sys, time
import urllib.robotparser
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sugar" / "india_crush_auto.csv"
STATUS = ROOT / "data" / "sugar" / "india_crush_status.json"
HIST = ROOT / "data" / "sugar" / "manual" / "india_crush_history.csv"
UA = {"User-Agent": "Mozilla/5.0 (compatible; BMR-Com research desk; github.com/BMR-Com)"}
FIELDS = ["season", "as_of", "region", "sugar_lakh_t", "mills", "cane_lakh_t", "recovery_pct", "source", "url", "note", "parsed_at"]
MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september",
                                       "october", "november", "december"], 1)}
MON_RE = "(january|february|march|april|may|june|july|august|september|october|november|december)"
STATES = {"Maharashtra": "MH", "Uttar Pradesh": "UP", "Karnataka": "KA"}
_robots = {}


def robots_ok(url):
    host = "{0.scheme}://{0.netloc}".format(urlparse(url))
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(host + "/robots.txt", headers=UA, timeout=25)
            if r.status_code == 404:
                rp.parse([])
            elif r.status_code >= 400:
                rp = None
            else:
                rp.parse(r.text.splitlines())
        except Exception:
            rp = None
        _robots[host] = rp
    rp = _robots[host]
    return None if rp is None else rp.can_fetch(UA["User-Agent"], url)


def get(url, log, **kw):
    ok = robots_ok(url)
    if ok is False:
        log.append({"url": url, "result": "disallowed by robots.txt"})
        return None
    try:
        r = requests.get(url, headers=UA, timeout=30, **kw)
        log.append({"url": url, "result": r.status_code, "robots": "read" if ok else "unreadable"})
        return r if r.status_code == 200 else None
    except Exception as e:
        log.append({"url": url, "result": type(e).__name__})
        return None


def text_of(html):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", htmlmod.unescape(t)).strip()


def season_of(d):
    y = d.year if d.month >= 10 else d.year - 1
    return f"{y}/{(y + 1) % 100:02d}"


def parse_date(t, ref):
    """'till December 15', 'up to 15th December 2025', 'as of Nov 30' -> date in the season of ref."""
    t = t.lower()
    m = re.search(r"(?:till|until|up ?to|as on|as of|by|ending)\s+(\d{1,2})(?:st|nd|rd|th)?\s+" + MON_RE + r"(?:,?\s+(\d{4}))?", t) or \
        re.search(r"(?:till|until|up ?to|as on|as of|by|ending)\s+" + MON_RE + r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?", t)
    if not m:
        return None
    g = m.groups()
    if g[0].isdigit():
        dd, mm, yy = int(g[0]), MONTHS[g[1]], g[2]
    else:
        mm, dd, yy = MONTHS[g[0]], int(g[1]), g[2]
    y = int(yy) if yy else (ref.year if mm <= ref.month else ref.year - 1)
    try:
        d = date(y, mm, dd)
    except ValueError:
        return None
    return d if d <= ref and (ref - d).days < 60 else None


NUM = r"(\d{1,3}(?:\.\d{1,2})?)"


def parse_isma(t, ref):
    """All-India and state season-to-date sugar (lakh t) and mills from a news report of an ISMA release."""
    d = parse_date(t, ref)
    if not d:
        return []
    rows = []
    m = re.search(r"(?:sugar )?production[^.]{0,120}?" + NUM + r"\s*lakh\s*(?:metric\s*)?ton", t, re.I)
    if m:
        mills = re.search(r"(\d{2,3})\s+(?:sugar\s+)?(?:mills|factories)", t[max(0, m.start() - 300): m.end() + 300], re.I)
        rows.append({"region": "IN", "sugar_lakh_t": float(m.group(1)), "mills": int(mills.group(1)) if mills else ""})
    for name, code in STATES.items():
        for sm in re.finditer(name, t):
            seg = t[sm.end(): sm.end() + 220]
            cut = [seg.find(o) for o in STATES if o != name and seg.find(o) > 0]
            seg = seg[:min(cut)] if cut else seg
            n = re.search(NUM + r"\s*lakh\s*(?:metric\s*)?ton", seg, re.I)
            if n:
                mills = re.search(r"(\d{2,3})\s+(?:sugar\s+)?(?:mills|factories)", seg, re.I)
                rows.append({"region": code, "sugar_lakh_t": float(n.group(1)), "mills": int(mills.group(1)) if mills else ""})
                break
    for r in rows:
        r.update({"season": season_of(d), "as_of": str(d)})
    return rows


def parse_mh(t, ref):
    """Maharashtra Sugar Commissionerate report as reported: cane crushed (lakh t), sugar (lakh quintals), recovery, mills."""
    d = parse_date(t, ref)
    q = re.search(NUM + r"\s*lakh\s*quintals?", t, re.I)
    if not d or not q:
        return []
    cane = re.search(NUM + r"\s*lakh\s*(?:metric\s*)?ton\w*\s*(?:of\s*)?(?:sugar)?cane", t, re.I) or \
        re.search(r"crush\w*\s*" + NUM + r"\s*lakh\s*(?:metric\s*)?ton", t, re.I)
    rec = re.search(r"recovery[^.]{0,60}?" + NUM + r"\s*(?:%|per\s*cent|percent)", t, re.I)
    mills = re.search(r"(\d{2,3})\s+(?:sugar\s+)?(?:mills|factories)", t, re.I)
    if not cane:
        return []
    return [{"season": season_of(d), "as_of": str(d), "region": "MH", "sugar_lakh_t": round(float(q.group(1)) / 10, 3),
             "cane_lakh_t": float(cane.group(1)), "recovery_pct": float(rec.group(1)) if rec else "", "mills": int(mills.group(1)) if mills else "",
             "note": f"{q.group(1)} lakh quintals"}]


def sane(rows, known):
    """Drop parses that cannot be right: values outside 0-400 lakh t, states above all-India, all-India below an
    earlier release of the same season."""
    out = []
    ind = {(r["season"], r["as_of"]): r["sugar_lakh_t"] for r in rows if r["region"] == "IN"}
    for r in rows:
        v = r["sugar_lakh_t"]
        if not (0 < v < 400):
            continue
        a = ind.get((r["season"], r["as_of"]))
        if r["region"] != "IN" and a is not None and v > a:
            continue
        if r["region"] == "IN" and not r.get("cane_lakh_t"):
            earlier = [kv for (s, d, reg), kv in known.items() if s == r["season"] and reg == "IN" and d < r["as_of"]]
            if earlier and v < max(earlier) - 0.5:
                continue
        if r.get("cane_lakh_t") and not (0 < r["cane_lakh_t"] < 2000 and (r.get("recovery_pct") in ("", None) or 5 < r["recovery_pct"] < 14)):
            continue
        out.append(r)
    return out


def chinimandi_posts(log, since):
    """(title, link, date, html) for recent ChiniMandi posts about ISMA or Maharashtra production."""
    posts = []
    for q in ("ISMA sugar production", "Maharashtra sugar production"):
        url = "https://www.chinimandi.com/wp-json/wp/v2/posts"
        r = get(url, log, params={"search": q, "after": since.isoformat() + "T00:00:00", "per_page": 20, "_fields": "title,link,date,content"})
        if r is None:
            posts = []
            break
        try:
            for p in r.json():
                posts.append((htmlmod.unescape(re.sub("<[^>]+>", "", p["title"]["rendered"])), p["link"], p["date"][:10], p["content"]["rendered"]))
        except Exception:
            posts = []
            break
        time.sleep(1)
    if posts:
        return posts, "wp-json"
    # fallback: RSS feed pages (full content in content:encoded when the site provides it)
    for page in range(1, 8):
        r = get("https://www.chinimandi.com/feed/" + (f"?paged={page}" if page > 1 else ""), log)
        if r is None:
            break
        items = re.findall(r"(?s)<item>(.*?)</item>", r.text)
        if not items:
            break
        old = False
        for it in items:
            ti = htmlmod.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(r"(?s)<title>(.*?)</title>", it) or [None, ""])[1]))
            ln = (re.search(r"<link>(.*?)</link>", it) or [None, ""])[1].strip()
            pd_ = (re.search(r"<pubDate>(.*?)</pubDate>", it) or [None, ""])[1]
            try:
                dt = datetime.strptime(pd_[:16], "%a, %d %b %Y").date()
            except Exception:
                dt = date.today()
            if dt < since:
                old = True
                continue
            body = (re.search(r"(?s)<content:encoded>(.*?)</content:encoded>", it) or [None, ""])[1]
            posts.append((ti, ln, str(dt), re.sub(r"<!\[CDATA\[|\]\]>", "", body)))
        if old:
            break
        time.sleep(1)
    return posts, "rss"


def main():
    st = json.loads(STATUS.read_text()) if STATUS.exists() else {}
    today = date.today()
    if st.get("last_run_date") == str(today) and "--force" not in sys.argv:
        print("india crush collector already ran today")
        return 0
    log, rows = [], []
    known = {}
    for f in (HIST, OUT):
        if f.exists():
            for r in csv.DictReader(f.open()):
                if not r.get("cane_lakh_t"):
                    known[(r["season"], r["as_of"], r["region"])] = float(r["sugar_lakh_t"])
    seen = set(st.get("seen_urls", []))

    # 1. primary sources: reachability, and ISMA press releases if the site answers
    direct = {}
    for name, url in (("ISMA", "https://www.indiansugar.com/"), ("Maharashtra Sugar Commissionerate", "https://sugar.maharashtra.gov.in/")):
        n0 = len(log)
        r = get(url, log)
        direct[name] = log[n0]["result"] if len(log) > n0 else "not tried"
        if r is not None and name == "ISMA":
            links = sorted(set(re.findall(r"EventDetails\.aspx\?Nid=(\d+)", r.text)), key=int)[-6:]
            for nid in links:
                u = f"https://www.indiansugar.com/EventDetails.aspx?Nid={nid}"
                if u in seen:
                    continue
                p = get(u, log)
                seen.add(u)
                if p is None:
                    continue
                t = text_of(p.text)
                for x in parse_isma(t, today):
                    x.update({"source": "ISMA press release (auto)", "url": u})
                    rows.append(x)
                time.sleep(1)

    # 2. news of the releases
    since = today - timedelta(days=21)
    posts, via = chinimandi_posts(log, since)
    for title, link, pdate, body in posts:
        if link in seen:
            continue
        ref = datetime.strptime(pdate, "%Y-%m-%d").date()
        t = text_of(body) if body else ""
        tl = title.lower()
        if not t:
            p = get(link, log)
            t = text_of(p.text) if p is not None else ""
            time.sleep(1)
        if not t:
            continue
        got = []
        if "isma" in tl and ("production" in tl or "output" in tl):
            got = parse_isma(title + ". " + t, ref)
            src = "ISMA via ChiniMandi (auto)"
        elif "maharashtra" in tl and ("quintal" in tl or "sugar production" in tl or "crush" in tl):
            got = parse_mh(title + ". " + t, ref)
            src = "Maharashtra Sugar Commissionerate via ChiniMandi (auto)"
        for x in got:
            x.update({"source": src, "url": link})
            rows.append(x)
        seen.add(link)

    rows = sane(rows, known)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    have = []
    if OUT.exists():
        have = list(csv.DictReader(OUT.open()))
    keys = {(r["season"], r["as_of"], r["region"], bool(r.get("cane_lakh_t"))) for r in have}
    new = 0
    for r in rows:
        k = (r["season"], r["as_of"], r["region"], bool(r.get("cane_lakh_t")))
        if k in keys:
            continue
        keys.add(k)
        r["parsed_at"] = stamp
        have.append({f: r.get(f, "") for f in FIELDS})
        new += 1
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in sorted(have, key=lambda r: (r["as_of"], r["region"])):
            w.writerow(r)
    codes = {}
    for e in log:
        codes[str(e["result"])] = codes.get(str(e["result"]), 0) + 1
    st.update({"run": stamp, "last_run_date": str(today), "direct_sources": direct, "news_via": via, "news_posts_checked": len(posts),
               "rows_parsed": len(rows), "rows_added": new, "rows_total": len(have), "http": codes,
               "disallowed": sum(1 for e in log if e["result"] == "disallowed by robots.txt"),
               "seen_urls": sorted(seen)[-400:], "log_tail": log[-12:]})
    STATUS.write_text(json.dumps(st, indent=1))
    print(json.dumps({k: v for k, v in st.items() if k not in ("seen_urls", "log_tail")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
