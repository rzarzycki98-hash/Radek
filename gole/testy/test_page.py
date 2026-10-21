"""Page test: copy of gole/ with a simulated agent state (settled bets, a vetoed match), Chromium at 390 px.
Checks: no JS errors, no horizontal scroll on every tab, new skill cards render. Saves screenshots.
Usage (in the Claude cloud: PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers):
    python3 gole/testy/test_skills.py                  # leaves a simulated state in /tmp/lg-test-*/agent.json
    python3 gole/testy/test_page.py gole /tmp/lg-test-XXXX/agent.json /tmp/zrzuty
"""
import http.server, json, os, shutil, socketserver, sys, tempfile, threading
from playwright.sync_api import sync_playwright

GOLE, AGENT, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
site = tempfile.mkdtemp(prefix="lg-site-")
shutil.copytree(GOLE, os.path.join(site, "gole"), ignore=shutil.ignore_patterns(".cache"))
a = json.load(open(AGENT, encoding="utf-8"))
# one upcoming match vetoed by the critic, one with a switched-off warning (to see both on the page)
if a.get("upcoming"):
    v = a["upcoming"][0]
    v.update({"dec": "skip", "veto": ["rynek_przeciw", "rozjazd"],
              "why": "Krytyk zablokował zakład: rynek ruszył przeciwko; model i rynek mocno się różnią. Agent sprawdzi po meczu, czy blokada była słuszna. Zakład, który by postawił: Under 2.5 po 2.40 u Grosvenor."})
    if not v.get("best"):
        v["best"] = {"side": "Under", "odds": 2.4, "book": "Grosvenor", "bk": "grosvenor", "edge": 0.034, "q": 0.43}
# one league with old results (warning on the Agent tab), one fresh; ClubElo down with its reason
a.setdefault("status", {})["results"] = {"B1": {"last": "2026-10-11", "age_d": 10, "waiting": 9, "stale": True},
                                         "E0": {"last": "2026-10-19", "age_d": 2, "waiting": 0, "stale": False}}
a["status"].setdefault("sources", {})["clubelo"] = {"errors": ["ClubElo: http: HTTP 502 Bad Gateway"], "clubs": 0, "matched": {},
                                                    "tried": {"at": "2026-10-21 09:00", "why": "http: HTTP 502 Bad Gateway; https: URLError timed out"}}
a["status"]["sources"].setdefault("football_data", {"leagues": 38, "errors": []}).update({"n_stale": 1, "stale": ["E0-2627.csv: HTTP Error 503 – użyta kopia sprzed 5 godz."]})
json.dump(a, open(os.path.join(site, "gole", "agent.json"), "w", encoding="utf-8"), ensure_ascii=False)

handler = lambda *x, **k: http.server.SimpleHTTPRequestHandler(*x, directory=site, **k)
srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

errors, bad = [], []
with sync_playwright() as p:
    b = p.chromium.launch()
    for scheme in ("dark", "light"):
        pg = b.new_page(viewport={"width": 390, "height": 844}, color_scheme=scheme)
        pg.on("pageerror", lambda e: errors.append(str(e)))
        # web fonts may be unreachable from a test sandbox: that is not a page error
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "fonts.g" not in (m.location or {}).get("url", "")
              and "ERR_TUNNEL_CONNECTION_FAILED" not in m.text else None)
        pg.goto(f"http://127.0.0.1:{port}/gole/", wait_until="networkidle")
        for tab in ("agent", "mecze", "nauka", "wyniki", "ligi"):
            pg.click(f'.nav [data-tab="{tab}"]')
            pg.wait_for_timeout(250)
            sw, cw = pg.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
            if sw > cw + 1:
                bad.append(f"{scheme}/{tab}: horizontal scroll {sw} > {cw}")
            if tab == "nauka":
                pg.evaluate("document.querySelectorAll('details.skill').forEach((d,i)=>{ if(i===4) d.open=true; })")
                txt = pg.inner_text("#view")
                for need in ("Skille agenta", "Krytyk – druga opinia", "Szczęście czy umiejętność", "Kalibracja", "Wnioski agenta", "Krytyk: wyłączone blokady", "Over czy Under?"):
                    if need not in txt:
                        bad.append(f"{scheme}/nauka: missing '{need}'")
            if tab == "agent" and "Raport tygodnia" not in pg.inner_text("#view"):
                bad.append(f"{scheme}/agent: no weekly report card")
            if tab == "nauka" and "Zdrowie agenta" not in pg.inner_text("#view"):
                bad.append(f"{scheme}/nauka: no health card")
            if tab == "agent" and "Stare wyniki:" not in pg.inner_text("#view"):
                bad.append(f"{scheme}/agent: no warning about old results")
            if tab == "nauka" and "HTTP 502" not in pg.inner_text("#view"):
                bad.append(f"{scheme}/nauka: ClubElo error reason not shown")
            if tab == "wyniki":
                if "Pech." not in pg.inner_text("#view") and "Zasłużona wygrana." not in pg.inner_text("#view"):
                    bad.append(f"{scheme}/wyniki: no post-match lesson under settled bets")
            if tab == "mecze":
                if "krytyk blokuje" not in pg.inner_text("#view"):
                    bad.append(f"{scheme}/mecze: vetoed match not marked")
            if scheme == "dark" or tab == "nauka":
                pg.screenshot(path=os.path.join(OUT, f"{scheme}-{tab}.png"), full_page=True)
        pg.close()
    b.close()
srv.shutdown()
print("JS errors:", errors or "none")
print("Layout/content problems:", bad or "none")
sys.exit(1 if errors or bad else 0)
