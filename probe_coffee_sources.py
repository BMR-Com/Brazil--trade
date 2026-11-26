"""One-off probe #6 (deleted after): dry run of the new coffee pipelines, nothing committed."""
import subprocess, csv, collections
for cmd in (["python", "pipelines/safras_quotes.py", "--backfill"], ["python", "pipelines/brazil_stocks.py"], ["python", "pipelines/vietnam_exports.py"]):
    print("==", " ".join(cmd)); r = subprocess.run(cmd, capture_output=True, text=True, timeout=1500); print(r.stdout[-6000:]); print("ERR", r.stderr[-3000:], "rc", r.returncode)
def show(p, n=40):
    try:
        rows = list(csv.DictReader(open(p)))
    except Exception as e:
        print(p, e); return []
    print("==", p, len(rows))
    for r in rows[:5] + rows[-n:]: print("  ", {k: v for k, v in r.items() if k != "url"})
    return rows
q = show("data/coffee/diffs/safras_quotes.csv", 60)
c = collections.Counter((r["site"], r["series"], r["unit"]) for r in q); print(c)
print("ambiguous", [ (r["quote_date"], r["series"], r["low"], r["high"], r["url"][-70:]) for r in q if r.get("ambiguous") == "1"][:40])
for s in ("good_cup_mtgb", "fine_cup_1718", "semi_washed", "conillon", "rio"):
    v = [float(r["low"]) for r in q if r["series"] == s and r["unit"] == "c/lb" and r["low"]]
    if v: print(s, "n", len(v), "min", min(v), "max", max(v), "outliers", [(r["quote_date"], r["low"], r["url"][-60:]) for r in q if r["series"] == s and r["unit"] == "c/lb" and r["low"] and abs(float(r["low"])) > 120])
for s in set(r["series"] for r in q if r["unit"].startswith("R$")):
    v = sorted(float(r["low"]) for r in q if r["series"] == s and r["unit"].startswith("R$") and r["low"])
    print(s, "n", len(v), "min", v[0], "med", v[len(v)//2], "max", v[-1])
show("data/coffee/diffs/brazil_stocks.csv", 30)
show("data/coffee/diffs/vietnam_exports.csv", 70)
