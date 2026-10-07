#!/usr/bin/env python3
"""Abiskript portfelli liikujate selgitamiseks (kasutab ajastatud Claude'i ülesanne).

  python3 scripts/movers.py symbols            -> prindib FMP sümbolid JSON-massiivina (tükkideks max 80)
  python3 scripts/movers.py movers QUOTES.json -> prindib tänased >=5% liikujad JSON-ina

QUOTES.json = FMP batch-quote vastuste liidetud massiiv (väljad symbol, price, changePercentage, timestamp).
Sümbolite teisendus ja "täna kaubeldud" kontroll on samad mis äpis (index.html).
"""
import csv, json, sys, os, datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUF = {"se": ".ST", "no": ".OL", "par": ".PA", "fr": ".PA", "ch": ".SW", "swx": ".SW", "mil": ".MI", "it": ".MI",
       "lon": ".L", "gb": ".L", "etr": ".DE", "de": ".DE", "be": ".BR", "bru": ".BR", "dk": ".CO", "ams": ".AS",
       "lis": ".LS", "pl": ".WA", "es": ".MC", "mce": ".MC", "hel": ".HE", "ca": ".TO", "hk": ".HK", "hkg": ".HK",
       "kls": ".KL", "au": ".AX", "aus": ".AX"}
OVERRIDE = {"envi-ams": "ENVIP.OL", "nyxh-be": "NYXH"}
SUFTZ = {".L": "Europe/London", ".LS": "Europe/Lisbon", ".HE": "Europe/Helsinki", ".HK": "Asia/Hong_Kong",
         ".KL": "Asia/Kuala_Lumpur", ".AX": "Australia/Sydney", ".TO": "America/New_York", "": "America/New_York"}
THRESHOLD = 5.0
CHUNK = 80


def to_fmp(sym):
    s = sym.strip().lower()
    if s in OVERRIDE:
        return OVERRIDE[s]
    if "-" not in s:
        return s.upper().replace(".", "-")
    base, ex = s.rsplit("-", 1)
    suf = SUF.get(ex)
    if not suf:
        return None
    if suf == ".HK":
        base = base.zfill(4)
    return base.upper().replace(".", "-") + suf


def suffix(fmp):
    i = fmp.rfind(".")
    return fmp[i:] if i > 0 else ""


def positions():
    out = {}
    with open(os.path.join(ROOT, "positions.csv"), newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            book = (r.get("Book") or "").strip().upper()
            sym = (r.get("Symbol") or "").strip()
            name = (r.get("Name") or "").strip()
            if book == "BONDS" or not sym or name.startswith("#"):
                continue
            fmp = to_fmp(sym)
            if fmp:
                out[fmp] = {"sym": sym, "name": name, "book": book, "country": (r.get("Country_or_Parent") or "").strip()}
    return out


def traded_today(fmp, ts):
    if not ts:
        return True
    # kauplemispäev börsi ajavööndis peab olema sama mis tänane kuupäev Tallinnas
    tz = ZoneInfo(SUFTZ.get(suffix(fmp), "Europe/Paris"))
    return datetime.datetime.fromtimestamp(ts, tz).date() == datetime.datetime.now(ZoneInfo("Europe/Tallinn")).date()


def main():
    pos = positions()
    if sys.argv[1:2] == ["symbols"]:
        syms = sorted(pos)
        print(json.dumps([syms[i:i + CHUNK] for i in range(0, len(syms), CHUNK)]))
        return
    if sys.argv[1:2] == ["movers"] and len(sys.argv) > 2:
        quotes = json.load(open(sys.argv[2]))
        res = []
        for q in quotes:
            p = pos.get(q.get("symbol"))
            pct = q.get("changePercentage")
            if not p or pct is None or abs(pct) < THRESHOLD or not traded_today(q["symbol"], q.get("timestamp")):
                continue
            res.append({**p, "fmp": q["symbol"], "pct": round(pct, 2), "price": q.get("price"),
                        "quoteTime": datetime.datetime.fromtimestamp(q["timestamp"], datetime.timezone.utc).isoformat() if q.get("timestamp") else None})
        res.sort(key=lambda x: -abs(x["pct"]))
        print(json.dumps(res, ensure_ascii=False, indent=1))
        return
    print(__doc__)
    sys.exit(2)


if __name__ == "__main__":
    main()
