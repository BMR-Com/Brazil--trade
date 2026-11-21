"""CEPEA/ESALQ arabica and robusta (conilon) coffee indices -> data/coffee/ (scheduled GitHub Actions job only).

One request to the CEPEA coffee indicator page per run (max twice a day, weekdays), honest User-Agent, and only if
cepea.org.br/robots.txt allows that agent (checked every run with urllib.robotparser; if not allowed the run skips
quietly). The page carries both indices as HTML tables ('Data | À vista R$ | ... | À vista US$'); each table is read
with brazil_physical.cepea_rows (same parser as Ma's manual inbox files), new dates are added to the raw store
(dates already held from CEPEA's own data are never overwritten; it replaces only the Noticias Agricolas copy) and
brazil_physical.build() rewrites cepea_arabica_history.csv / cepea_robusta_history.csv (c_lb = usd_bag/132.277*100).
Rows with only R$ get US$ from the PTAX series already in the desk (build() handles the conversion).
Fails (exit 1) if the page was fetched but no dated rows for both indices could be parsed. Ma's inbox uploads stay as backup.
"""
import re
from datetime import date
import sys
import urllib.robotparser
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brazil_physical as bp  # noqa: E402

AGENT = "BMR-Com research desk (github.com/BMR-Com)"
ROBOTS = "https://www.cepea.org.br/robots.txt"
PAGES = ["https://www.cepea.org.br/br/indicador/cafe.aspx", "https://www.cepea.org.br/en/indicator/coffee.aspx"]
SOURCE = "CEPEA indicator page (scheduled fetch)"


def allowed(url):
    rp = urllib.robotparser.RobotFileParser()
    try:
        r = requests.get(ROBOTS, headers={"User-Agent": AGENT}, timeout=30)
    except Exception as e:
        print(f"robots.txt could not be read ({e}); skipped")
        return False
    if r.status_code >= 500 or r.status_code in (401, 403):
        print(f"robots.txt HTTP {r.status_code}; skipped")
        return False
    rp.parse(r.text.splitlines() if r.status_code == 200 else [])
    return rp.can_fetch(AGENT, url)


def tables(html):
    """Each <table> with the ~1500 characters of text before it as its title (that is where the index name sits)."""
    out, pos = [], 0
    for m in re.finditer(r"(?is)<table.*?</table>", html):
        before = " ".join(re.sub(r"(?s)<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html[max(pos, m.start() - 6000):m.start()]).split())[-1500:]
        rows = [[" ".join(re.sub(r"(?s)<[^>]+>", " ", c).split()) for c in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", tr)]
                for tr in re.findall(r"(?is)<tr.*?</tr>", m.group(0))]
        out.append((before, rows))
        pos = m.end()
    return out


def _br(x):
    x = x.replace("R$", "").replace("US$", "").strip()
    if not re.fullmatch(r"[\d.]+,\d+|\d+(\.\d+)?", x):
        return None
    return float(x.replace(".", "").replace(",", ".")) if "," in x else float(x)


def loose_rows(rows):
    """Header-free reading: rows starting with a dd/mm/yyyy date; BRL = first plain number, USD = last (percent cells skipped)."""
    out = []
    for r in rows:
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})$", (r[0] if r else "").strip())
        if not m:
            continue
        nums = [v for v in (_br(c) for c in r[1:] if "%" not in c) if v is not None]
        if len(nums) < 2:
            continue
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        out.append((d.isoformat(), "", nums[0], nums[-1]))
    return out


def parse(html):
    got, unlabeled = {}, []
    for title, rows in tables(html):
        low = title.lower()
        tail = low[-400:]
        if "robusta" in tail or "conilon" in tail or "conillon" in tail:
            name = "robusta"
        elif "arábica" in tail or "arabica" in tail:
            name = "arabica"
        else:
            unlabeled.append(rows)
            continue
        rr = bp.cepea_rows([[name]] + rows)
        if rr and ("cepea_" + name) not in got:
            got["cepea_" + name] = [(d, "cepea_" + name, b, u) for d, _, b, u in rr]
    if len(got) < 2:
        # Titles not found near the tables: fall back on price level (arabica always trades well above robusta per bag).
        cands = []
        for rows in (unlabeled or [r for _, r in tables(html)]):
            rr = bp.cepea_rows([["arabica"]] + rows) or loose_rows(rows)
            if rr:
                last = [b or u for _, _, b, u in rr if (b or u)]
                if last:
                    cands.append((float(last[-1]), rr))
        cands.sort(key=lambda x: -x[0])
        for name, (_, rr) in zip([n for n in ("arabica", "robusta") if "cepea_" + n not in got], cands):
            got["cepea_" + name] = [(d, "cepea_" + name, b, u) for d, _, b, u in rr]
            print(f"CEPEA {name}: table matched by price level (no title found)")
    return got


def main():
    for url in PAGES:
        if not allowed(url):
            print(f"robots.txt does not allow {AGENT!r} on {url}; skipped")
            continue
        r = requests.get(url, headers={"User-Agent": AGENT, "Accept-Language": "pt-BR,en;q=0.8"}, timeout=60)
        print(f"{url}: HTTP {r.status_code}, {len(r.content)} bytes")
        if r.status_code != 200:
            continue
        r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
        got = parse(r.text)
        print("parsed:", {k: (len(v), v[0][0] if v else None, v[-1][0] if v else None) for k, v in got.items()})
        if set(got) != {"cepea_arabica", "cepea_robusta"}:
            print(f"::error::CEPEA page {url} fetched but the arabica and robusta tables could not both be parsed "
                  f"(found {sorted(got)}; {len(tables(r.text))} tables on page) - page layout changed?")
            sys.exit(1)
        rows = [x for v in got.values() for x in v]
        new = pd.DataFrame([{"date": d, "series": s, "place": "CEPEA/ESALQ", "brl_60kg": b, "usd_60kg": u, "source": SOURCE}
                            for d, s, b, u in rows])
        old = bp.read_raw()
        own = old[old.source.isin(["CEPEA file uploaded to inbox", "CEPEA series download", SOURCE])]
        have = set(zip(own.date, own.series))
        new = new[[(d, s) not in have for d, s in zip(new.date, new.series)]]   # add new dates only, never overwrite
        print(f"new rows: {len(new)}", new[["date", "series", "usd_60kg"]].to_string(index=False) if len(new) else "")
        if len(new):
            bp.save_raw(new)
        bp.build()
        return
    print("no CEPEA page fetched this run (robots or HTTP); nothing changed")


if __name__ == "__main__":
    main()
