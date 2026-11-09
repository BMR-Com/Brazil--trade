"""Rebuild data/cotton/ice/latest.json from the ICE certs files in data/cotton/ice (newest of each kind, the previous
warehouse report, and the full warehouse history used for certification-month cohorts)."""
import json, re
from pathlib import Path
D = Path(__file__).resolve().parent.parent / "data" / "cotton" / "ice"
K = {"stock": "stock", "grade": "grade_staple", "warehouse": "warehouse", "strength": "strength", "year_of_growth": "year_of_growth"}
out = json.loads((D / "latest.json").read_text()) if (D / "latest.json").exists() else {}
for k, pre in K.items():
    fs = sorted(f for f in D.glob(pre + "_*.csv") if re.search(r"_(\d{4}-\d{2}-\d{2})\.csv$", f.name) and (k != "grade" or True))
    if k == "stock":
        fs = [f for f in fs if not f.name.startswith("stock_by")]
    if not fs:
        continue
    d = lambda f: re.search(r"(\d{4}-\d{2}-\d{2})", f.name).group(1)
    out[k], out[k + "_date"] = f"data/cotton/ice/{fs[-1].name}", d(fs[-1])
    if k == "warehouse":
        out["warehouse_history"] = [{"date": d(f), "path": f"data/cotton/ice/{f.name}"} for f in fs]
        if len(fs) > 1:
            out["warehouse_prev"], out["warehouse_prev_date"] = f"data/cotton/ice/{fs[-2].name}", d(fs[-2])
(D / "latest.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
