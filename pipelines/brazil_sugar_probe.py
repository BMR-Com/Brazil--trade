"""One-off probe (manual workflow only): can the GitHub runner read Brazil sugar price indicators?
Checks robots.txt for each URL with the desk's honest User-Agent, fetches only what robots allows, prints status,
table titles and the first rows, and saves the raw pages under probe_out/ for the run artifact (never committed)."""
import re, sys, urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse
import requests

AGENT = "BMR-Com research desk (github.com/BMR-Com)"
URLS = [
    "https://www.cepea.org.br/br/indicador/acucar.aspx",
    "https://www.cepea.org.br/en/indicator/sugar.aspx",
    "https://www.cepea.org.br/br/indicador/series/acucar.aspx?id=53",
    "https://www.cepea.org.br/br/indicador/series/acucar.aspx?id=151",
    "https://www.noticiasagricolas.com.br/cotacoes/sucroenergetico",
    "https://www.noticiasagricolas.com.br/cotacoes/sucroenergetico/acucar-cristal-cepea",
    "https://www.novacana.com/cotacoes",
]
out = Path("probe_out"); out.mkdir(exist_ok=True)
robots = {}

def ok(url):
    host = urlparse(url).scheme + "://" + urlparse(url).netloc
    if host not in robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(host + "/robots.txt", headers={"User-Agent": AGENT}, timeout=30)
            print(f"\n== {host}/robots.txt HTTP {r.status_code}\n" + r.text[:1500])
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            robots[host] = None if r.status_code in (401, 403) or r.status_code >= 500 else rp
        except Exception as e:
            print(f"robots error {host}: {e}"); robots[host] = None
    rp = robots[host]
    return rp is not None and rp.can_fetch(AGENT, url)

for i, u in enumerate(URLS):
    if not ok(u):
        print(f"\n## {u}: robots does not allow (or robots unreadable); not fetched"); continue
    try:
        r = requests.get(u, headers={"User-Agent": AGENT, "Accept-Language": "pt-BR,en;q=0.8"}, timeout=60)
    except Exception as e:
        print(f"\n## {u}: error {e}"); continue
    ct = r.headers.get("content-type", "")
    print(f"\n## {u}: HTTP {r.status_code}, {len(r.content)} bytes, {ct}")
    (out / f"p{i}.bin").write_bytes(r.content)
    if r.status_code != 200 or "html" not in ct:
        continue
    r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
    html = r.text
    pos = 0
    for m in re.finditer(r"(?is)<table.*?</table>", html):
        before = " ".join(re.sub(r"(?s)<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html[max(pos, m.start()-3000):m.start()]).split())[-250:]
        rows = [[" ".join(re.sub(r"(?s)<[^>]+>", " ", c).split()) for c in re.findall(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", tr)]
                for tr in re.findall(r"(?is)<tr.*?</tr>", m.group(0))]
        print("  TABLE after:", before[-200:]); [print("   ", r_) for r_ in rows[:4]]
        pos = m.end()
    for a in sorted(set(re.findall(r'href="([^"]*(?:xls|serie|series|download)[^"]*)"', html, re.I)))[:20]:
        print("  link:", a)
