"""Source check from GitHub Actions (the Claude cloud cannot reach these sites): ClubElo, football-data fixtures and
the newest results of the agent's leagues. Read-only, prints a report; never writes into gole/.
Usage: python3 gole/testy/diagnoza_zrodel.py
"""
import csv, datetime as dt, io, os, socket, sys, urllib.error, urllib.request

GOLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GOLE)
import agent as AG  # noqa: E402
import engine as E  # noqa: E402

UAS = {"agent": "linia-goli-agent/1 (+github actions)", "browser": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def probe(url, ua="agent", n=160):
    req = urllib.request.Request(url, headers={"User-Agent": UAS[ua], "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read()
            h = {k: r.headers.get(k) for k in ("Server", "Content-Type", "Last-Modified", "CF-RAY") if r.headers.get(k)}
            return f"{r.status} {len(body)} B {h} | {body[:n].decode('utf-8', 'replace')!r}"
    except urllib.error.HTTPError as e:
        body = e.read()[:n].decode("utf-8", "replace") if hasattr(e, "read") else ""
        h = {k: e.headers.get(k) for k in ("Server", "Content-Type", "CF-RAY", "Via") if e.headers and e.headers.get(k)}
        return f"HTTP {e.code} {e.reason} {h} | {body!r}"
    except Exception as e:
        return f"{type(e).__name__}: {e}"


today = dt.date.today()
print("=== ClubElo")
for host in ("api.clubelo.com", "clubelo.com", "www.clubelo.com"):
    try:
        print(f"  DNS {host}: {sorted({a[4][0] for a in socket.getaddrinfo(host, 80)})}")
    except Exception as e:
        print(f"  DNS {host}: {e}")
for day in (today,):
    for scheme in ("http", "https"):
        for ua in UAS:
            print(f"  {scheme}://api.clubelo.com/{day} [{ua}]: {probe(f'{scheme}://api.clubelo.com/{day}', ua)}")
for path in ("Fixtures", "Arsenal", ""):
    print(f"  http://api.clubelo.com/{path}: {probe('http://api.clubelo.com/' + path, 'browser')}")
print(f"  http://clubelo.com/: {probe('http://clubelo.com/', 'browser')}")
print(f"  http://www.clubelo.com/: {probe('http://www.clubelo.com/', 'browser')}")
try:  # does the website itself carry the ratings (a possible way around the broken API)?
    req = urllib.request.Request("http://clubelo.com/", headers={"User-Agent": UAS["browser"]})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    for word in ("Arsenal", "Bayern", "Elo", ".csv", "api"):
        i = html.find(word)
        print(f"  clubelo.com '{word}': {html.count(word)} razy" + (f", np. {html[max(0, i - 120):i + 160]!r}" if i >= 0 else ""))
except Exception as e:
    print("  clubelo.com:", e)

print("\n=== football-data.co.uk")
print("  fixtures.csv:", probe(f"{E.BASE}/fixtures.csv", n=0))
try:
    req = urllib.request.Request(f"{E.BASE}/fixtures.csv", headers={"User-Agent": "linia-goli/3 (+github actions)"})
    text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8-sig", "replace")
    rd = list(csv.DictReader(io.StringIO(text)))
    cols = list(rd[0].keys()) if rd else []
    print(f"  kolumny ({len(cols)}): {[c for c in cols if '2.5' in c or c in ('Div', 'Date', 'Time', 'PSH', 'B365H')]}")
    for code in AG.LEAGUES:
        rs = [r for r in rd if r.get("Div") == code]
        withp = sum(1 for r in rs if E.fnum(r.get("P>2.5")) and E.fnum(r.get("P<2.5")))
        withb = sum(1 for r in rs if E.fnum(r.get("B365>2.5")))
        dates = sorted({r.get("Date") for r in rs})
        print(f"  {code:4} meczów {len(rs):3}, z Pinnacle o/u 2.5: {withp:3}, z Bet365 o/u 2.5: {withb:3}, daty {dates[:1]}–{dates[-1:]}")
except Exception as e:
    print("  fixtures.csv: błąd", e)

print("\n=== najnowsze wyniki lig agenta (pliki sezonu 26/27)")
sc = E.season_code(E.season_years(today, 1)[0])
for code in AG.LEAGUES:
    url = f"{E.BASE}/mmz4281/{sc}/{code}.csv"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "linia-goli/3 (+github actions)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            lm = r.headers.get("Last-Modified")
            rows = E.parse_rows(r.read().decode("utf-8-sig", "replace"), code)
        last = max((m["d"] for m in rows if m["hg"] is not None), default=None)
        cnt = {b: sum(1 for m in rows if m["ou"].get(b)) for b in ("P", "BFE", "B365", "Avg")}
        cntc = {b: sum(1 for m in rows if m["ouc"].get(b)) for b in ("P", "BFE", "B365", "Avg")}
        print(f"       kursy o/u 2.5 przed meczem {cnt}, na zamknięcie {cntc}")
        print(f"  {code:4} wyników {sum(1 for m in rows if m['hg'] is not None):3}, ostatni {last}, Last-Modified: {lm}")
    except Exception as e:
        print(f"  {code:4} błąd: {e}")

print("\n=== ESPN – wyniki piłkarskie (zapasowe źródło)")
import tempfile  # noqa: E402
import zrodla as ZR  # noqa: E402
es = ZR.ESPNScores(tempfile.mkdtemp(), dt.datetime.now(dt.timezone.utc))
for code in ("B1", "E0", "G1"):
    try:
        rows = es._day(code, dt.date(2026, 10, 18))
        print(f"  {code} 18.10: {len(rows)} meczów, np. {rows[:3]}")
    except Exception as e:
        print(f"  {code}: błąd {e}")

print("\n=== The Odds API – czy Pinnacle i giełdy podają linię goli (1 zapytanie, 1 kredyt)")
key = os.environ.get("ODDS_API_KEY", "").strip()
if not os.environ.get("DIAG_ODDS"):  # costs 1 credit of the monthly 500: only when asked for (DIAG_ODDS=1)
    print("  pominięte (ustaw DIAG_ODDS=1, żeby sprawdzić)")
elif key:
    import json  # noqa: E402
    url = (f"https://api.the-odds-api.com/v4/sports/soccer_epl/odds?apiKey={key}&dateFormat=iso&oddsFormat=decimal&markets=totals"
           f"&bookmakers={','.join(E.FOOT_BOOKMAKERS)}")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "linia-goli/3"}), timeout=60) as r:
            evs = json.loads(r.read().decode("utf-8"))
            print(f"  zużyte w zapytaniu: {r.headers.get('x-requests-last')}, zostało: {r.headers.get('x-requests-remaining')}")
        cnt = {}
        for ev in evs:
            for bm in ev.get("bookmakers", []):
                pts = sorted({o.get("point") for mk in bm.get("markets", []) for o in mk.get("outcomes", [])})
                cnt.setdefault(bm["key"], []).append(pts)
        for k, v in sorted(cnt.items()):
            print(f"  {k:15} meczów {len(v):2}, z linią 2.5: {sum(1 for p in v if 2.5 in p):2}, linie np. {v[:4]}")
        ce = E.compact_event(evs[0]) if evs else None
        if ce:
            print("  przykład:", ce["home"], "–", ce["away"], json.dumps(ce["books"])[:400])
            print("  uczciwa cena:", E.fair_prices({"books": ce["books"], "ou": {}, "x": {}}))
    except Exception as e:
        print("  błąd:", str(e).replace(key, "***"))
else:
    print("  brak klucza")
