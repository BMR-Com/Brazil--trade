"""Parse the UNICA 'Acompanhamento da safra na região Centro-Sul' PDF (tables 1, 2 and 8)."""
import re

REG = ["CS", "SP", "OTHER"]
METRICS = [("Cana-de-açúcar", "cane_kt"), ("Açúcar", "sugar_kt"), ("Etanol anidro", "anhydrous_ml"),
           ("Etanol hidratado", "hydrous_ml"), ("Etanol total", "ethanol_ml"), ("ATR/ tonelada de cana", "atr_kg_t"),
           ("ATR", "atr_kt"), ("Litros etanol/ tonelada de cana", "ethanol_l_t"), ("Kg açúcar/ tonelada de cana", "sugar_kg_t")]
MES = {"janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
       "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12}


def _n(s):
    s = s.strip().replace("%", "")
    return float(s.replace(".", "").replace(",", "."))


def _nums(line):
    return re.findall(r"-?[\d\.]+,\d+%?|-?\d{1,3}(?:\.\d{3})+|-?\d+%?", line)


def parse_text(pages):
    txt = "\n".join(pages)
    m = re.search(r"Posição até\s*(\d{2}/\d{2}/\d{4})", txt)
    if not m:
        return []
    d, mo, y = m.group(1).split("/")
    position = f"{y}-{mo}-{d}"
    seasons = re.findall(r"(\d{4}/\d{4})\s+(\d{4}/\d{4})\s+Var", txt)
    prev, cur = seasons[0] if seasons else (None, None)
    rows = []

    def table(block, name, month=None):
        lines = block.splitlines()
        mixmode = None
        for ln in lines:
            s = ln.strip()
            low = s.lower()
            if low.startswith("açúcar ") and "%" in s and not re.match(r"Açúcar\s+¹", s):
                mixmode = "mix_sugar"
            elif low.startswith("etanol ") and "%" in s and s.count("%") <= 6 and not re.search(r"[²¹]", s):
                mixmode = "mix_ethanol"
            else:
                mixmode = None
            if mixmode:
                v = [x for x in _nums(s) if "%" in x]
                for i, r in enumerate(REG):
                    if len(v) >= 2 * i + 2:
                        rows.extend([dict(position=position, table=name, month=month, metric=mixmode, region=r, season=prev, value=_n(v[2 * i])),
                                 dict(position=position, table=name, month=month, metric=mixmode, region=r, season=cur, value=_n(v[2 * i + 1]))])
                continue
            for lab, key in METRICS:
                if s.startswith(lab) and not (key == "atr_kt" and s.startswith("ATR/")):
                    rest = s[len(lab):]
                    v = [x for x in _nums(rest) if "%" not in x]
                    v = [x for x in v if x not in ("1", "2", "3")] if len(v) > 6 else v
                    for i, r in enumerate(REG):
                        if len(v) >= 2 * i + 2:
                            rows.extend([dict(position=position, table=name, month=month, metric=key, region=r, season=prev, value=_n(v[2 * i])),
                                     dict(position=position, table=name, month=month, metric=key, region=r, season=cur, value=_n(v[2 * i + 1]))])
                    break

    t1 = re.search(r"Tabela 1\.(.*?)Tabela 2\.", txt, re.S)
    t2 = re.search(r"Tabela 2\.(.*?)Fonte", txt, re.S)
    if t1:
        table(t1.group(1), "accumulated")
    if t2:
        mm = re.search(r"referente a (\w+) de (\d{4})", t2.group(1))
        month = f"{mm.group(2)}-{MES.get(mm.group(1).lower(), 0):02d}" if mm else None
        table(t2.group(1), "monthly", month)

    t8 = re.search(r"Tabela 8\. Hist(.*?)Fonte", txt, re.S)
    if t8:
        for ln in t8.group(1).splitlines():
            mm = re.match(r"\s*(\d{2})/(\d{2})\s+(.*)", ln)
            if not mm:
                continue
            v = _nums(mm.group(3))
            if len(v) < 6:
                continue
            dd, mo = int(mm.group(1)), int(mm.group(2))
            yr = int(cur[:4]) if mo >= 4 else int(cur[5:])
            fort = f"{yr}-{mo:02d}-{dd:02d}"
            for k, key in enumerate(["corn_anh_fn", "corn_hyd_fn", "corn_total_fn", "corn_anh_acc", "corn_hyd_acc", "corn_total_acc"]):
                rows.append(dict(position=position, table="corn", month=fort, metric=key, region="CS", season=cur, value=_n(v[k]) / 1000.0))
    return rows


def parse_pdf(fobj):
    import pdfplumber
    with pdfplumber.open(fobj) as pdf:
        pages = [(p.extract_text() or "") for p in pdf.pages]
    return parse_text(pages)
