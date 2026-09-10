"""Write Central Bank (TCMB) daily rates as static JSON files the app can read from any device.

    python tools/build_rates.py                 # last 400 days that are missing, plus today
    python tools/build_rates.py 2026-01-01 2026-03-31

Output: app/rates/YYYY-MM-DD.json per published day, e.g.
    {"date": "2026-08-28", "TRY_per_unit": true,
     "rates": {"USD": {"unit": 1, "ForexBuying": 48.0732, "ForexSelling": 48.1598, ...}, ...}}
Days with no TCMB file (weekends, holidays) get {"date": ..., "none": true} so the app can step back
to the previous published day. app/rates/index.json lists the days that exist.
The GitHub Actions workflow in the published repo runs this daily.
"""
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "rates"
FIELDS = ("ForexBuying", "ForexSelling", "BanknoteBuying", "BanknoteSelling")


def fetch_day(d: dt.date):
    today = dt.date.today()
    url = "https://www.tcmb.gov.tr/kurlar/today.xml" if d >= today else f"https://www.tcmb.gov.tr/kurlar/{d:%Y%m}/{d:%d%m%Y}.xml"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 IFSBridge/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            root = ET.fromstring(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    # today.xml carries its own date; make sure it is really today's file
    stamp = root.get("Tarih") or ""
    if d >= today and stamp and stamp != d.strftime("%d.%m.%Y"):
        return None
    rates = {}
    for c in root.findall("Currency"):
        code = c.get("CurrencyCode")
        unit = float((c.findtext("Unit") or "1").replace(",", "."))
        entry = {"unit": unit}
        for f in FIELDS:
            v = (c.findtext(f) or "").strip()
            entry[f] = round(float(v.replace(",", ".")) / unit, 6) if v else None
        rates[code] = entry
    return {"date": d.isoformat(), "TRY_per_unit": True, "rates": rates}


def main(argv):
    OUT.mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    if len(argv) >= 3:
        start, end = dt.date.fromisoformat(argv[1]), dt.date.fromisoformat(argv[2])
    else:
        start, end = today - dt.timedelta(days=400), today
    written = 0
    d = start
    while d <= end:
        path = OUT / f"{d.isoformat()}.json"
        # re-fetch today (the file appears at 15:30) and any 'none' day younger than 3 days
        stale = False
        if path.exists():
            try:
                cur = json.loads(path.read_text("utf-8"))
                stale = cur.get("none") and (today - d).days <= 3
            except Exception:  # noqa: BLE001
                stale = True
        if not path.exists() or stale or d == today:
            try:
                data = fetch_day(d)
            except Exception as e:  # noqa: BLE001
                print("skip", d, e)
                d += dt.timedelta(days=1)
                continue
            if data is None:
                if d == today and path.exists():
                    d += dt.timedelta(days=1)
                    continue
                data = {"date": d.isoformat(), "none": True}
            path.write_text(json.dumps(data, separators=(",", ":")), "utf-8")
            written += 1
        d += dt.timedelta(days=1)
    days = sorted(p.stem for p in OUT.glob("????-??-??.json"))
    (OUT / "index.json").write_text(json.dumps({"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "first": days[0] if days else None, "last": days[-1] if days else None, "count": len(days)}), "utf-8")
    print(f"{written} files written, {len(days)} days available in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
