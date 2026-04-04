"""
Brazil Trade Scraper — Incremental Updater
==========================================
Called by GitHub Actions every Monday to fetch new MDIC data.
The full historical CSV was built by the Colab notebook.
This script adds only new/incomplete years to exports.csv.

Usage:
  python scraper.py                    # fetch incomplete/missing years
  python scraper.py --years 2025 2026  # force specific years
"""

import io, time, logging, argparse
import requests, urllib3, pandas as pd
from pathlib import Path
from datetime import date

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-8s %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger(__name__)

BASE_DIR    = Path(__file__).parent
DATA_DIR    = BASE_DIR / "data"
# Data is split — scraper only updates the 2015+ file
EXPORT_CSV  = DATA_DIR / "exports_2015on.csv"
COUNTRY_CSV = DATA_DIR / "countries.csv"
DATA_DIR.mkdir(exist_ok=True)

BASE_URL          = "https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm"
TARGET_CHAPTERS   = {"09","21","52","17","12","23","15","10"}

# ── Commodity classification ───────────────────────────────────────────────
def classify(ncm):
    p4  = ncm[:4]
    p56 = ncm[4:6]
    if p4 == "0901":
        if p56 in ("11","12","21","22","90"): return ("coffee","arabica_green")
        if p56 == "19":                        return ("coffee","conillon_robusta")
        return ("coffee","arabica_green")
    if p4 == "2101": return ("coffee","soluble")
    if ncm[:2] in ("09","21"): return None
    if p4 in ("5201","5202","5203"): return ("cotton","raw_cotton")
    if ncm[:2] == "52": return None
    if p4 == "1701":
        return ("sugar","raw_cane" if p56 in ("11","13") else
                "raw_beet"  if p56 == "14" else "refined")
    if p4 == "1702": return ("sugar","refined")
    if ncm[:2] == "17": return None
    if p4 == "1201": return ("soybeans","raw_soybeans")
    if p4 == "2304": return ("soybeans","soybean_meal")
    if p4 == "1507": return ("soybeans","soybean_oil")
    if ncm[:2] in ("12","23","15"): return None
    if p4 in ("1005","1007"): return ("corn","yellow_corn")
    return None

# ── Country lookup (from official MDIC PAIS.csv) ───────────────────────────
COUNTRIES = {
    "000":"Not Defined","013":"Afghanistan","015":"Aland Islands",
    "017":"Albania","020":"Alboran-Perejil Islands","023":"Germany",
    "025":"East Germany","031":"Burkina Faso","037":"Andorra","040":"Angola",
    "041":"Anguilla","042":"Antarctica","043":"Antigua And Barbuda",
    "047":"Netherlands Antilles","053":"Saudi Arabia","059":"Algeria",
    "063":"Argentina","064":"Armenia","065":"Aruba","069":"Australia",
    "072":"Austria","073":"Azerbaijan","077":"Bahamas","080":"Bahrain",
    "081":"Bangladesh","083":"Barbados","085":"Belarus","087":"Belgium",
    "088":"Belize","090":"Bermuda","093":"Myanmar","097":"Bolivia",
    "098":"Bosnia And Herzegovina","099":"Bonaire Saint Eustatius And Saba",
    "101":"Botswana","105":"Brazil","108":"Brunei","111":"Bulgaria",
    "115":"Burundi","119":"Bhutan","127":"Cape Verde","137":"Cayman Islands",
    "141":"Cambodia","145":"Cameroon","149":"Canada","151":"Canary Islands",
    "153":"Kazakhstan","154":"Qatar","158":"Chile","160":"China",
    "161":"Taiwan","163":"Cyprus","169":"Colombia","173":"Comoros",
    "177":"Congo","183":"Cook Islands","187":"North Korea","190":"South Korea",
    "193":"Cote D Ivoire","195":"Croatia","196":"Costa Rica","198":"Kuwait",
    "199":"Cuba","200":"Curacao","229":"Benin","232":"Denmark",
    "235":"Dominica","237":"Dubai","239":"Ecuador","240":"Egypt",
    "243":"Eritrea","244":"United Arab Emirates","245":"Spain",
    "246":"Slovenia","247":"Slovakia","249":"United States","251":"Estonia",
    "253":"Ethiopia","255":"Falkland Islands","259":"Faroe Islands",
    "267":"Philippines","271":"Finland","275":"France","281":"Gabon",
    "285":"Gambia","289":"Ghana","291":"Georgia","293":"Gibraltar",
    "297":"Grenada","301":"Greece","305":"Greenland","309":"Guadeloupe",
    "313":"Guam","317":"Guatemala","325":"French Guyana","329":"Guinea",
    "331":"Equatorial Guinea","334":"Guinea-Bissau","337":"Guyana",
    "341":"Haiti","345":"Honduras","351":"Hong Kong","355":"Hungary",
    "357":"Yemen","361":"India","365":"Indonesia","367":"England",
    "369":"Iraq","372":"Iran","375":"Ireland","379":"Iceland","383":"Israel",
    "386":"Italy","391":"Jamaica","399":"Japan","403":"Jordan",
    "411":"Kiribati","420":"Laos","426":"Lesotho","427":"Latvia",
    "431":"Lebanon","434":"Liberia","438":"Libya","440":"Liechtenstein",
    "442":"Lithuania","445":"Luxembourg","447":"Macao","449":"Macedonia",
    "450":"Madagascar","455":"Malaysia","458":"Malawi","461":"Maldives",
    "464":"Mali","467":"Malta","474":"Morocco","476":"Marshall Islands",
    "477":"Martinique","485":"Mauritius","488":"Mauritania","489":"Mayotte",
    "493":"Mexico","494":"Moldova","495":"Monaco","497":"Mongolia",
    "498":"Montenegro","499":"Micronesia","501":"Montserrat",
    "505":"Mozambique","507":"Namibia","511":"Christmas Island",
    "517":"Nepal","521":"Nicaragua","525":"Niger","528":"Nigeria",
    "538":"Norway","542":"New Caledonia","545":"Papua New Guinea",
    "548":"New Zealand","551":"Vanuatu","556":"Oman","573":"Netherlands",
    "575":"Palau","576":"Pakistan","578":"Palestine","580":"Panama",
    "586":"Paraguay","589":"Peru","599":"French Polynesia","603":"Poland",
    "607":"Portugal","611":"Puerto Rico","623":"Kenya","625":"Kyrgyzstan",
    "628":"United Kingdom","640":"Central African Republic",
    "647":"Dominican Republic","660":"Reunion","665":"Zimbabwe",
    "670":"Romania","675":"Rwanda","676":"Russia","677":"Solomon Islands",
    "678":"St. Kitts And Nevis","685":"Western Sahara","687":"El Salvador",
    "690":"Samoa","697":"San Marino","699":"Sint Maarten",
    "700":"Saint Pierre And Miquelon",
    "705":"Saint Vincent And The Grenadines","710":"Saint Helena",
    "715":"Saint Lucia","720":"Sao Tome And Principe","728":"Senegal",
    "731":"Seychelles","735":"Sierra Leone","737":"Serbia","741":"Singapore",
    "744":"Syria","748":"Somalia","750":"Sri Lanka","754":"Swaziland",
    "756":"South Africa","759":"Sudan","760":"South Sudan","764":"Sweden",
    "767":"Switzerland","770":"Suriname","772":"Tajikistan","776":"Thailand",
    "780":"Tanzania","783":"Djibouti","788":"Chad","791":"Czech Republic",
    "795":"East Timor","800":"Togo","810":"Tonga",
    "815":"Trinidad And Tobago","820":"Tunisia",
    "823":"Turks And Caicos Islands","824":"Turkmenistan","827":"Turkey",
    "831":"Ukraine","833":"Uganda","845":"Uruguay","847":"Uzbekistan",
    "850":"Venezuela","858":"Vietnam","863":"Virgin Islands Uk",
    "866":"Virgin Islands Usa","870":"Fiji","875":"Wallis And Futuna",
    "888":"DR Congo","890":"Zambia","990":"Planes And Ships Provisions",
    "999":"Not Declared",
}

OUT_COLS = [
    "year","month","ncm","co_unid","commodity","subtype",
    "country_code","country_name","qt_estat","kg_net","fob_usd",
]

def load_countries() -> dict:
    if COUNTRY_CSV.exists():
        df = pd.read_csv(COUNTRY_CSV, dtype=str)
        return dict(zip(df["country_code"], df["country_name"]))
    pd.DataFrame([{"country_code":k,"country_name":v}
                  for k,v in COUNTRIES.items()]).to_csv(COUNTRY_CSV, index=False)
    return COUNTRIES

def download_year(year: int) -> pd.DataFrame | None:
    url = f"{BASE_URL}/EXP_{year}.csv"
    log.info("Fetching %s", url)
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=300, verify=False)
            resp.raise_for_status()
            break
        except Exception as e:
            log.warning("  attempt %d: %s", attempt+1, e)
            if attempt == 2:
                log.error("  all retries failed for %d", year)
                return None
            time.sleep(5*(attempt+1))

    raw = resp.content.decode("latin-1")
    df  = pd.read_csv(io.StringIO(raw), sep=";", dtype=str, on_bad_lines="skip")
    df.columns = [c.strip().strip('"').upper() for c in df.columns]
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip().str.strip('"')

    df["CO_NCM"]  = df["CO_NCM"].str.zfill(8)
    df["CO_PAIS"] = df["CO_PAIS"].str.zfill(3)

    df = df[df["CO_NCM"].str[:2].isin(TARGET_CHAPTERS)].copy()
    if df.empty: return None

    classified = df["CO_NCM"].map(classify)
    df = df[classified.notna()].copy()
    if df.empty: return None

    df["commodity"] = classified[classified.notna()].map(lambda x: x[0])
    df["subtype"]   = classified[classified.notna()].map(lambda x: x[1])

    for col in ("QT_ESTAT","KG_LIQUIDO","VL_FOB","CO_ANO","CO_MES"):
        df[col] = pd.to_numeric(
            df[col].str.strip().str.strip('"')
                   .str.replace(".","",regex=False)
                   .str.replace(",",".",regex=False),
            errors="coerce"
        ).fillna(0)

    df["CO_ANO"] = df["CO_ANO"].astype(int)
    df["CO_MES"] = df["CO_MES"].astype(int)
    df["CO_UNID"] = df.get("CO_UNID", pd.Series("", index=df.index)).astype(str).str.strip().str.strip('"')
    df["country_name"] = df["CO_PAIS"].map(COUNTRIES).fillna("Unknown")

    df = df.rename(columns={
        "CO_ANO":"year","CO_MES":"month","CO_NCM":"ncm","CO_UNID":"co_unid",
        "CO_PAIS":"country_code","QT_ESTAT":"qt_estat",
        "KG_LIQUIDO":"kg_net","VL_FOB":"fob_usd",
    })

    months = sorted(df["month"].unique())
    log.info("  %d rows | months %02d-%02d | cof=%.2fBkg cot=%.2fBkg sug=%.1fBkg soy=%.1fBkg cor=%.1fBkg",
             len(df), months[0], months[-1],
             df[df.commodity=="coffee"]["kg_net"].sum()/1e9,
             df[df.commodity=="cotton"]["kg_net"].sum()/1e9,
             df[df.commodity=="sugar"]["kg_net"].sum()/1e9,
             df[df.commodity=="soybeans"]["kg_net"].sum()/1e9,
             df[df.commodity=="corn"]["kg_net"].sum()/1e9)
    return df[OUT_COLS]

def load_existing() -> pd.DataFrame:
    if EXPORT_CSV.exists():
        df = pd.read_csv(EXPORT_CSV, dtype={"ncm":str,"country_code":str,"co_unid":str})
        log.info("Loaded %d existing rows from %s", len(df), EXPORT_CSV)
        return df
    return pd.DataFrame(columns=OUT_COLS)

def complete_years(df: pd.DataFrame) -> set:
    if df.empty: return set()
    cur = date.today().year
    counts = df.groupby("year")["month"].nunique()
    return {int(y) for y in counts[counts >= 12].index if int(y) < cur}

PRE2015_YEARS = set(range(1997, 2015))  # handled by exports_pre2015.csv — never touch

def save(df: pd.DataFrame):
    df = df.sort_values(["year","month","commodity","country_code"]).reset_index(drop=True)
    df.to_csv(EXPORT_CSV, index=False)
    log.info("Saved %d rows → %s (%.0f MB)", len(df), EXPORT_CSV,
             EXPORT_CSV.stat().st_size/1e6)

def run(years_override=None):
    countries = load_countries()
    existing  = load_existing()
    done      = complete_years(existing)
    cur_year  = date.today().year

    to_fetch = years_override if years_override else [
        y for y in range(2015, cur_year+1) if y not in done
    ]
    if not to_fetch:
        log.info("All years complete — nothing to fetch.")
        return

    log.info("Years to fetch: %s", to_fetch)
    new_frames = []
    for year in to_fetch:
        raw = download_year(year)
        if raw is not None:
            new_frames.append(raw)

    if not new_frames:
        log.info("No new data.")
        return

    if not existing.empty:
        existing = existing[~existing["year"].isin(to_fetch)]
    combined = pd.concat([existing]+new_frames, ignore_index=True)
    save(combined)
    log.info("Done. Total rows: %d", len(combined))

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", nargs="+", type=int)
    args = ap.parse_args()
    run(years_override=args.years)
