"""Test of the take-home pay on the Godziny page (Chromium, 390 px, light and dark).
Checks: take-home pay matches values worked out by hand with the payslip's method (rates below are made up –
public repo; the method was checked on 9.11.2026 against a real payslip to the penny), saved data without pay settings still loads, no JS errors,
no horizontal scroll. Saves screenshots.
Usage (Claude cloud: PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers):
    python3 godziny/testy/test_zarobek.py godziny /tmp/zrzuty-godziny
"""
import http.server, json, os, shutil, socketserver, sys, tempfile, threading
from playwright.sync_api import sync_playwright

SRC, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
site = tempfile.mkdtemp(prefix="godziny-site-")
shutil.copytree(SRC, os.path.join(site, "godziny"), ignore=shutil.ignore_patterns("testy"))

# Test week: Mon-Fri 07:00-16:27 = 9 h 27 min - 45 min break = 8 h 42 min = 8.7 h; 5 days = 43.5 h.
# OLD_STATE has no "rate"/"hol" keys, like data saved by version 3 on Radek's phone: the page must ask for the rate.
# PAY_STATE adds made-up rates (real ones are typed in on the phone only) in the version 4-5 format:
# rate 15.00 + holiday pay 2.00 must become one rate of 17.00 (holiday pay is now part of the rate).
OLD_STATE = {"brk": 45, "days": {f"2026-10-{d}": {"s": "07:00", "e": "16:27", "b": 45} for d in range(19, 24)}}
PAY_STATE = dict(OLD_STATE, rate=15.00, hol=2.00)

# Hand-checked (and payslip) results: minutes after breaks -> (gross, tax, NI, net)
EXPECT = {
    2610: (739.50, 99.40, 39.80, 600.30),    # 43.5 h
    3000: (850.00, 121.60, 48.64, 679.76),   # 50 h
    3582: (1014.90, 163.80, 58.96, 792.14),  # 59.7 h - NI above the upper limit (2%)
    4200: (1190.00, 234.20, 62.46, 893.34),  # 70 h - part of the week taxed at 40%
    0: (0.0, 0.0, 0.0, 0.0),
}

handler = lambda *x, **k: http.server.SimpleHTTPRequestHandler(*x, directory=site, **k)
srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

errors, bad = [], []
with sync_playwright() as p:
    b = p.chromium.launch()
    for scheme in ("light", "dark"):
        ctx = b.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme)
        ctx.add_init_script(f"if (!localStorage.getItem('godziny-v1')) localStorage.setItem('godziny-v1', {json.dumps(json.dumps(OLD_STATE))})")
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}/godziny/index.html")
        # old data without a rate: hint instead of a wrong £0.00
        pg.locator("#weeks button", has_text="19.10").click()
        if pg.inner_text("#pay-net") != "—" or "Wpisz stawkę" not in pg.inner_text("#pay-when"):
            bad.append(f"{scheme}: no rate -> expected a hint, got {pg.inner_text('#pay-when')!r}")
        if "£" in pg.inner_text("#weeks") or "Na rękę" in pg.evaluate("summaryText()"):
            bad.append(f"{scheme}: no rate -> money shown anyway")
        pg.evaluate(f"localStorage.setItem('godziny-v1', {json.dumps(json.dumps(PAY_STATE))})")
        pg.reload()
        for mins, (g, t, n, net) in EXPECT.items():
            r = pg.evaluate(f"payFor({{net: {mins}, sat: 0}})")
            got = (r["gross"], r["tax"], r["ni"], r["net"])
            if got != (g, t, n, net):
                bad.append(f"{scheme}: payFor({mins}) = {got}, expected {(g, t, n, net)}")
        # open the payslip week from the weeks list
        pg.locator("#weeks button", has_text="19.10").click()
        net_txt = pg.inner_text("#pay-net")
        sub_txt = pg.inner_text("#pay-sub")
        if net_txt != "£600.30":
            bad.append(f"{scheme}: week 19-25.10 shows {net_txt!r}, expected '£600.30'")
        sub_txt = pg.inner_text("#pay-when") + " " + pg.evaluate("$('pay-sub').textContent")
        for part in ("£739.50", "£99.40", "£39.80", "pt 30.10"):
            if part not in sub_txt:
                bad.append(f"{scheme}: summary line lacks {part!r}: {sub_txt!r}")
        if "£600.30" not in pg.inner_text("#weeks"):
            bad.append(f"{scheme}: weeks list lacks £600.30")
        if "£600.30" not in pg.inner_text("#month"):
            bad.append(f"{scheme}: October total lacks £600.30: {pg.inner_text('#month')!r}")
        if pg.evaluate("summaryText()").find("Na rękę ok. £600.30") < 0:
            bad.append(f"{scheme}: shared summary lacks the take-home line")
        before = pg.inner_text("#pay-net")
        pg.locator('.day[data-key="2026-10-24"] [data-field="s"]').click()
        pg.locator('.picker button', has_text="Zapisz").click()   # start: suggested from the last entry
        pg.locator('.picker button', has_text="Zapisz").click()   # end: suggested from the last entry
        if pg.inner_text("#pay-net") == before:
            bad.append(f"{scheme}: adding Saturday did not update the amount at once")
        pg.locator('.day[data-key="2026-10-24"] .clear').click()
        if pg.inner_text("#pay-net") != before:
            bad.append(f"{scheme}: clearing Saturday did not bring back {before}")
        if pg.input_value("#rate") != "17.00" or pg.input_value("#sat") != "" or pg.locator("#hol").count():
            bad.append(f"{scheme}: default pay settings not shown")
        # changing the rate recalculates and is remembered
        pg.fill("#rate", "18.00")
        pg.dispatch_event("#rate", "change")
        if pg.inner_text("#pay-net") == "£600.30":
            bad.append(f"{scheme}: changing the rate did not change take-home pay")
        if json.loads(pg.evaluate("localStorage.getItem('godziny-v1')")).get("rate") != 18:
            bad.append(f"{scheme}: new rate not saved")
        if pg.evaluate("document.documentElement.scrollWidth") > 390:
            bad.append(f"{scheme}: horizontal scroll")
        pg.fill("#rate", "17.00")
        pg.dispatch_event("#rate", "change")
        # Saturday 07:00-16:27 (8.7 h): without a Saturday rate it is paid like any day,
        # with a Saturday rate of 20.00: 43.5 h x 17 + 8.7 h x 20 = 913.50 gross
        pg.evaluate("state.days['2026-10-24'] = {s: '07:00', e: '16:27', b: 45}; save(); render()")
        if pg.inner_text("#pay-net") != "£706.77":
            bad.append(f"{scheme}: Saturday without own rate shows {pg.inner_text('#pay-net')!r}, expected '£706.77'")
        pg.fill("#sat", "20.00")
        pg.dispatch_event("#sat", "change")
        if pg.inner_text("#pay-net") != "£725.58":
            bad.append(f"{scheme}: Saturday at 20.00 shows {pg.inner_text('#pay-net')!r}, expected '£725.58'")
        if "sobota 8.70 h × £20.00" not in pg.evaluate("$('pay-sub').textContent"):
            bad.append(f"{scheme}: Saturday line missing in 'Jak to wyszło'")
        if json.loads(pg.evaluate("localStorage.getItem('godziny-v1')")).get("sat") != 20:
            bad.append(f"{scheme}: Saturday rate not saved")
        # typing a rate and then tapping a week straight away must open that week (no lost tap)
        pg.click("#today")
        pg.fill("#sat", "20.00")
        pg.dispatch_event("#sat", "change")   # first "change" (keyboard Done); the tap's blur fires a second one
        pg.locator("#weeks button", has_text="19.10").click()
        if "19–25" not in pg.inner_text("#week-title"):
            bad.append(f"{scheme}: tap on a week right after typing a rate was lost")
        pg.reload()
        if pg.input_value("#sat") != "20.00" or pg.input_value("#rate") != "17.00":
            bad.append(f"{scheme}: rates not kept after reopening the page")
        pg.locator("#weeks button", has_text="19.10").click()
        pg.locator('.day[data-key="2026-10-24"] .clear').click()
        pg.screenshot(path=os.path.join(OUT, f"godziny-{scheme}.png"), full_page=True)
        # empty week: no pay box
        pg.click("#next")
        if pg.is_visible("#week-pay"):
            bad.append(f"{scheme}: pay box visible in an empty week")
        ctx.close()
    b.close()
srv.shutdown()

problems = [f"JS error: {e}" for e in errors] + bad
print("\n".join(problems) if problems else "OK – zarobek zgodny z wyliczeniem ręcznym, bez błędów, bez przewijania w bok")
sys.exit(1 if problems else 0)
