"""Charts for the BMR-Com Sugar Research weekly, from repo data only.

Usage: python models/sugar_weekly_charts.py <out_dir>   (run models/sugar_world.py and models/sugar_weekly.py first)
Writes six PNGs (light chart background, 150 dpi) to <out_dir>:
  c1_parity.png    No. 11 front vs hydrous ethanol parity, 12 months
  c2_white.png     white premium, front pair, 2 years
  c3_rain.png      cumulative rain this month, Centre-South weighted, vs 2011-2025 average and last year
  c4_stoppage.png  estimated stoppage days by state, month to date and since 1 April, vs normal
  c5_range.png     cane by fortnight after the last MAPA fortnight: last season vs normal / wet / dry cases
  c6_cot.png       CFTC managed money net, 3 years
Titles are generic; the weekly's captions carry the week's reading.
"""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

R = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
BLUE, AMBER, PURPLE, GREEN, GRAY, INK, MUTED, BG = "#2160c4", "#c47a14", "#8b3f9e", "#4f8f2a", "#8a8f98", "#2a211b", "#6b625a", "#fcfaf6"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "axes.edgecolor": "#cfc8bf", "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": "#ebe6df", "grid.linewidth": 0.8,
                     "axes.spines.top": False, "axes.axisbelow": True, "axes.spines.right": False, "figure.facecolor": BG, "axes.facecolor": BG,
                     "savefig.facecolor": BG, "legend.frameon": False})
S = json.loads((R / "sugar/data/sugar.json").read_text())
W = json.loads((R / "data/sugar/world.json").read_text())
FRI = pd.Timestamp(json.loads((R / "data/sugar/weekly_inputs.json").read_text())["week_ending"])


def finish(fig, ax, title, sub, src, name):
    fig.text(0.012, 0.975, title, fontsize=13.5, fontweight="bold", color=INK, va="top")
    fig.text(0.012, 0.915, sub, fontsize=10, color=MUTED, va="top")
    fig.text(0.012, 0.015, src, fontsize=8.5, color=MUTED, va="bottom")
    fig.subplots_adjust(top=0.80, bottom=0.14, left=0.08, right=0.97)
    fig.savefig(OUT / name, dpi=150)
    plt.close(fig)


# 1. Raw sugar vs hydrous ethanol parity, 12 months
P = S["parity"]
df = pd.DataFrame({"d": pd.to_datetime(P["dates"]), "sb": P["sb"], "par": P["par"]}).set_index("d")
df = df.loc["2025-11-01":FRI]
fig, ax = plt.subplots(figsize=(10, 4.6))
ax.plot(df.index, df.sb, color=BLUE, lw=2, label="No. 11 front")
ax.plot(df.index, df.par, color=AMBER, lw=2, label="Hydrous ethanol parity")
ax.fill_between(df.index, df.par, df.sb, where=df.sb >= df.par, color=BLUE, alpha=0.08, lw=0)
ax.annotate(f"No. 11 {df.sb.iloc[-1]:.2f}", (df.index[-1], df.sb.iloc[-1]), xytext=(6, 4), textcoords="offset points", color=INK, fontsize=9)
ax.annotate(f"parity {df.par.iloc[-1]:.2f}", (df.index[-1], df.par.iloc[-1]), xytext=(6, -10), textcoords="offset points", color=INK, fontsize=9)
ax.set_ylabel("US cents per lb")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
ax.legend(loc="upper left", ncol=2)
ax.set_xlim(df.index[0], df.index[-1] + pd.Timedelta(days=40))
finish(fig, ax, "Raw sugar vs hydrous ethanol parity", f"ICE No. 11 front month and the sugar-equivalent price of hydrous ethanol at the mill, ¢/lb, to {FRI:%d %b %Y}",
       "Sources: ICE and B3 hydrous ethanol futures via TradingView; USD/BRL; BMR-Com softs desk parity (CONSECANA ATR factors, R$190/t to FOB, VHP pol premium).", "c1_parity.png")

# 2. White premium, front pair, 2 years
F = S["white"]["front"]
wp = pd.DataFrame({"d": pd.to_datetime(F["dates"]), "p": F["prem"]}).set_index("d").loc["2024-11-01":FRI]
fig, ax = plt.subplots(figsize=(10, 4.4))
ax.plot(wp.index, wp.p, color=PURPLE, lw=1.8)
ax.axhline(wp.p.mean(), color=GRAY, lw=1, ls="--")
ax.text(wp.index[5], wp.p.mean() + 2, f"2-year average ${wp.p.mean():.0f}", color=MUTED, fontsize=9)
ax.annotate(f"${wp.p.iloc[-1]:.0f}/t", (wp.index[-1], wp.p.iloc[-1]), xytext=(6, 0), textcoords="offset points", color=INK, fontsize=9)
ax.set_ylabel("US$ per tonne")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
ax.set_xlim(wp.index[0], wp.index[-1] + pd.Timedelta(days=45))
finish(fig, ax, "London white premium over New York raws", "London No. 5 front minus New York No. 11 front (×22.0462), US$/t; Dec 26 whites against Mar 27 raws at the week's close",
       "Sources: ICE Futures Europe and ICE Futures US settlements via TradingView; BMR-Com softs desk.", "c2_white.png")

# 3. Cumulative November rain, CS weighted
C = W["cane_weather"]["chart"]
days = [d[8:] for d in C["days"]]
fig, ax = plt.subplots(figsize=(10, 4.4))
x = np.arange(len(days))
ax.plot(x, C["avg"], color=GRAY, lw=2, ls="--", label="2011–2025 average")
if C.get("ly"):
    ax.plot(x, C["ly"], color=AMBER, lw=1.6, label="2025")
ax.plot(x, C["cur"], color=BLUE, lw=2.4, label="2026")
for ser, col in ((C["cur"], BLUE), (C["avg"], GRAY)):
    ax.annotate(f"{ser[-1]:.0f} mm", (x[-1], ser[-1]), xytext=(6, -3), textcoords="offset points", color=INK, fontsize=9)
ax.set_xticks(x[::2]); ax.set_xticklabels([f"{d}/{C['days'][0][5:7]}" for d in days[::2]])
ax.set_ylabel("mm since the 1st")
ax.set_xlim(-0.3, len(x) + 1.2)
ax.legend(loc="upper left")
finish(fig, ax, f"Cane-belt rain this month vs normal", f"Cumulative rain, Centre-South weighted by each state's cane crushed this season, {C['days'][0]} to {C['days'][-1]}",
       "Sources: ERA5 via Open-Meteo at seven cane points (SP x3, GO, MG, MS, PR); weights from MAPA cane crushed this season; BMR-Com.", "c3_rain.png")

# 4. Stoppage days by state, month to date and since April vs normal
rows = [r for r in W["cane_weather"]["rows"]]
lab = [r["id"] if r["id"] != "CS" else "Centre-South" for r in rows]
fig, axs = plt.subplots(1, 2, figsize=(10, 4.4), sharey=True)
for ax, key, ttl in ((axs[0], "stop_mtd", "This month"), (axs[1], "stop_atd", "Since 1 April")):
    y = np.arange(len(rows))
    now = [r[key]["now"] for r in rows]; nor = [r[key]["avg"] for r in rows]
    ax.barh(y + 0.2, nor, height=0.36, color="#c9c3bb", label="2011–2025 normal")
    ax.barh(y - 0.2, now, height=0.36, color=BLUE, label="2026")
    for yi, v in zip(y, now):
        ax.text(v + 0.3, yi - 0.2, f"{v:.0f}", va="center", fontsize=8.5, color=INK)
    ax.set_title(ttl, fontsize=10.5, color=INK, loc="left")
    ax.set_yticks(y); ax.set_yticklabels(lab); ax.invert_yaxis(); ax.set_xlabel("estimated stoppage days")
    ax.grid(axis="y", visible=False)
axs[1].legend(loc="lower right", fontsize=8.5)
fig.text(0.012, 0.975, "Estimated harvest-stoppage days by state", fontsize=13.5, fontweight="bold", color=INK, va="top")
fig.text(0.012, 0.915, "Days when rain would stop cutting (≥5 mm, or the day after ≥10 mm, or two days after ≥20 mm), estimated from daily rainfall", fontsize=10, color=MUTED, va="top")
fig.text(0.012, 0.015, "Sources: ERA5 via Open-Meteo; BMR-Com estimate from rainfall, not reported mill downtime.", fontsize=8.5, color=MUTED)
fig.subplots_adjust(top=0.78, bottom=0.17, left=0.14, right=0.98, wspace=0.08)
fig.savefig(OUT / "c4_stoppage.png", dpi=150); plt.close(fig)

# 5. Remaining crush by fortnight: cases vs last season
Rg = W["range"]
m = pd.read_csv(R / "sugar/data/mapa_fortnight.csv", parse_dates=["end"])
cur_sf = sorted(m.safra.unique())[-1]; prev_sf = sorted(m.safra.unique())[-2]
t = m[(m.region == "Centro-Sul") & (m.uf == "TOTAL") & (m.safra == prev_sf)].sort_values("end")
t["fn"] = t.cane_t.diff()
E0 = pd.Timestamp(Rg["from_fortnight"]); E1 = E0 - pd.DateOffset(years=1)
ly = t[t.end > E1].head(len(Rg["cases"]["base"]["fortnights"]))
labs = [f["to"][5:] for f in Rg["cases"]["base"]["fortnights"]]
fig, ax = plt.subplots(figsize=(10, 4.4))
x = np.arange(len(labs))
lyv = list(ly.fn / 1e6)[:len(labs)]
ax.bar(x - 0.27, lyv, width=0.26, color="#c9c3bb", label=f"{prev_sf} actual")
ax.bar(x, [f["cane_mt"] for f in Rg["cases"]["base"]["fortnights"]], width=0.26, color=BLUE, label=f"{cur_sf}, normal rain")
lo = [f["cane_mt"] for f in Rg["cases"]["wet"]["fortnights"]]; hi = [f["cane_mt"] for f in Rg["cases"]["dry"]["fortnights"]]
base = [f["cane_mt"] for f in Rg["cases"]["base"]["fortnights"]]
ax.errorbar(x, base, yerr=[np.array(base) - np.array(lo), np.array(hi) - np.array(base)], fmt="none", ecolor=INK, elinewidth=1.2, capsize=4, label="wet to dry case")
MN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ax.set_xticks(x); ax.set_xticklabels([("1H " if l[3:] == "15" else "2H ") + MN[int(l[:2]) - 1] for l in labs])
for xi, v in zip(x, base):
    ax.text(xi + 0.15, v + 0.3, f"{v:.1f}", ha="left", fontsize=8.5, color=INK)
ax.set_ylabel("cane crushed, million t")
ax.legend(loc="upper right")
finish(fig, ax, "Centre-South cane still to crush, by fortnight", "Centre-South cane by fortnight after the latest MAPA fortnight: last season's actuals and this season's path under normal, wet and dry rain",
       "Sources: MAPA fortnightly production; ERA5, ensembles and climatology via Open-Meteo; BMR-Com public-data scenario.", "c5_range.png")

# 6. Managed money net, 3 years
C6 = json.loads((R / "data/cot_desk/SB.json").read_text())["series"]
cot = pd.DataFrame({"d": pd.to_datetime(C6["date"]), "mm": C6["mm_n"], "px": C6["price"]}).set_index("d").loc["2023-11-01":]
fig, ax = plt.subplots(figsize=(10, 4.4))
ax.bar(cot.index, cot.mm / 1000, width=5, color=np.where(cot.mm >= 0, BLUE, AMBER))
ax.axhline(0, color="#a9a29a", lw=0.8)
ax.annotate(f"{cot.mm.iloc[-1] / 1000:.0f}k, {cot.index[-1]:%d %b}", (cot.index[-1], cot.mm.iloc[-1] / 1000), xytext=(-110, 10), textcoords="offset points", color=INK, fontsize=9,
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
ax.set_ylabel("thousand contracts (net)")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
finish(fig, ax, "Managed money in sugar No. 11", "CFTC managed money net position in sugar No. 11, futures and options combined, weekly",
       "Source: CFTC disaggregated Commitments of Traders (positions as of Tuesday); BMR-Com softs desk.", "c6_cot.png")
print("ok", sorted(p.name for p in OUT.glob("*.png")))
