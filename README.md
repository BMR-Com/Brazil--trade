# 🇧🇷 Brazil Agricultural Trade Analytics

Auto-updating dashboard for Brazilian agricultural exports.  
**Data:** MDIC/SECEX Dados Abertos · **Updates:** Every Monday via GitHub Actions

---

## Commodities & NCM codes

| Commodity | Sub-type | Key NCM codes | Volume unit |
|-----------|----------|---------------|-------------|
| ☕ Coffee | Arabica green | 09011100, 09011200, 09012100 | 60 kg bags |
| ☕ Coffee | Conillon / Robusta | 09011900 | 60 kg bags |
| ☕ Coffee | Soluble / Instant | 21011110, 21011190, 21011200 | 60 kg bags |
| 🌾 Cotton | Raw / carded | 52010010, 52010090, 52030000 | MT or 480 lb bales |
| 🍬 Sugar | Raw cane / beet / refined | 17011310–17019990 | Metric tonnes |
| 🫘 Soybeans | Raw beans | 12010090, 12010010 | Metric tonnes |
| 🫘 Soybeans | Meal / cake | 23040010, 23040090 | Metric tonnes |
| 🫘 Soybeans | Oil | 15071000, 15079011, 15079019 | Metric tonnes |
| 🌽 Corn | Yellow dent / other | 10059010, 10059090 | Metric tonnes |

---

## Repo structure

```
brazil-trade/
├── scraper.py              ← downloads & filters MDIC CSV, updates exports.csv
├── scheduler.py            ← called by GitHub Actions; decides what to fetch
├── requirements.txt
├── index.html              ← analytics dashboard (reads data/exports.csv)
├── data/
│   ├── exports.csv         ← main dataset  ← YOU UPLOAD THIS FROM COLAB
│   └── countries.csv       ← country lookup ← YOU UPLOAD THIS FROM COLAB
└── .github/workflows/
    └── update_data.yml     ← runs every Monday, commits new data automatically
```

---

## Setup — you already have the CSV files from Colab

### Step 1 — Create the GitHub repo
1. Go to [github.com](https://github.com) → **New repository**
2. Name it `brazil-trade`, set to **Public**, click **Create repository**

### Step 2 — Upload ALL project files
On the new empty repo page click **uploading an existing file** and drag in:

```
scraper.py
scheduler.py
requirements.txt
index.html
README.md
.gitignore
.github/           ← the whole folder (includes workflows/update_data.yml)
data/exports.csv   ← from your Colab Google Drive download
data/countries.csv ← from your Colab Google Drive download
```

> **Tip:** GitHub's web uploader doesn't handle nested folders well.  
> Upload everything except `.github/` first, then create the workflow file:  
> Click **Add file → Create new file**, type the path  
> `.github/workflows/update_data.yml` and paste the file contents.

### Step 3 — Enable GitHub Actions
- Click the **Actions** tab → **I understand my workflows, go ahead and enable them**

### Step 4 — Test it
- Actions tab → **Brazil Trade — Monthly Data Update** → **Run workflow**
- Leave all inputs blank → **Run workflow** (green button)
- It will check if new data is available and update if so (~3 min)

**That's it.** Every Monday from now on the Action runs automatically.

---

## Viewing the dashboard

**Option A — GitHub Pages (recommended, no local server needed)**
1. Settings → Pages → Source: **Deploy from a branch** → Branch: `main`, folder: `/ (root)`
2. Your dashboard is live at `https://YOUR_USERNAME.github.io/brazil-trade/`

**Option B — Local**
```bash
cd brazil-trade
python -m http.server 8080
# open http://localhost:8080
```

> ⚠️ You must use a server (Option A or B). Double-clicking `index.html`
> won't work because browsers block local file reads for security reasons.

---

## Manual operations

```bash
# Install dependencies
pip install requests pandas urllib3

# Check what's in the CSV
python -c "import pandas as pd; df=pd.read_csv('data/exports.csv'); print(df.groupby('commodity')[['fob_usd','mt']].sum())"

# Force-fetch a specific year (e.g. if you want to refresh 2024)
python scraper.py --years 2024

# Force-fetch current + previous year (same as what the Action does)
python scheduler.py --force
```

---

## How the auto-update works

```
Every Monday 08:00 UTC
        │
        ▼
  scheduler.py
  "What's the latest month in exports.csv?"
  "What period should MDIC have by now?"
        │
  Already up to date? ──YES──▶ Exit cleanly (no commit)
        │
        NO
        ▼
  scraper.py --years [current_year, prev_year]
  Downloads EXP_{year}.csv from balanca.economia.gov.br
  Streams in 300k-row chunks
  Keeps ONLY rows matching our 29 target NCM codes
  Discards everything else
        │
        ▼
  Merges new rows into data/exports.csv
  Commits & pushes: "data: update through Mar 2026 [bot]"
        │
        ▼
  Dashboard auto-refreshes next time someone opens it
  (index.html fetches exports.csv fresh on every page load)
```

---

## Data notes

- **Source:** `https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm/EXP_{YEAR}.csv`
- **Coffee volume:** `qt_estat` = 60 kg bags (MDIC statistical unit for NCM 0901)
- **Cotton volume:** `mt` = metric tonnes · `bales_480lb` = 480 lb bales (kg ÷ 217.724)
- **Sugar/Soy/Corn:** `mt` = metric tonnes
- **FOB:** `fob_usd` in USD
- **SSL note:** MDIC's CDN has certificate chain issues — `verify=False` is set in scraper.py (safe because we're only reading public open data, not sending credentials)
