"""Test of night outs on the Work Hours page (Chromium, light and dark).
Checks: the 🌙 button on a day marks a night out (also on a day without hours) and unmarks it, the mark survives
a reload and editing the day's times, the week card and the shared summary count night outs, the Timesheet shows
🌙 next to the day and "Night outs: N" (no money), still fits the card at 390 and 360 px, the backup file keeps them.
Usage (Claude cloud: PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers):
    python3 godziny/testy/test_nightout.py godziny /tmp/zrzuty-godziny
"""
import http.server, json, os, shutil, socketserver, sys, tempfile, threading
from playwright.sync_api import sync_playwright

SRC, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
site = tempfile.mkdtemp(prefix="godziny-night-")
shutil.copytree(SRC, os.path.join(site, "godziny"), ignore=shutil.ignore_patterns("testy"))

# Week 47 (16-22.11.2026): Mon 05:00-19:00, Wed 06:00-18:00, Thu 06:00-17:00; made-up rate (no money on the Timesheet).
STATE = {"brk": 45, "rate": 15.0, "name": "Test Driver", "days": {
    "2026-11-16": {"s": "05:00", "e": "19:00", "b": 45},
    "2026-11-18": {"s": "06:00", "e": "18:00", "b": 45},
    "2026-11-19": {"s": "06:00", "e": "17:00", "b": 45},
}}

handler = lambda *x, **k: http.server.SimpleHTTPRequestHandler(*x, directory=site, **k)
srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{port}/godziny/index.html"

errors, bad = [], []
with sync_playwright() as p:
    b = p.chromium.launch()
    for scheme in ("light", "dark"):
        ctx = b.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme, accept_downloads=True)
        ctx.add_init_script(f"if (!localStorage.getItem('godziny-v1')) localStorage.setItem('godziny-v1', {json.dumps(json.dumps(STATE))})")
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(URL)
        pg.evaluate("monday = fromKey('2026-11-16'); render()")
        moon = lambda d: pg.locator(f'.day[data-key="2026-11-{d}"] .moon')
        # Monday (worked), Tuesday (no hours, e.g. stuck away) and Wednesday (longest day name) get a night out
        for d in ("16", "17", "18"):
            moon(d).click()
        if [moon(d).get_attribute("aria-pressed") for d in ("16", "17", "18", "19")] != ["true", "true", "true", "false"]:
            bad.append(f"{scheme}: moon buttons not pressed as expected")
        if "night out" not in pg.inner_text('.day[data-key="2026-11-16"] .day-gross'):
            bad.append(f"{scheme}: Monday row does not say night out")
        tue = pg.inner_text('.day[data-key="2026-11-17"]')
        if "day off" not in tue or "night out" not in tue:
            bad.append(f"{scheme}: Tuesday (no hours) row wrong: {tue!r}")
        if "3 night outs" not in pg.inner_text("#week-sub"):
            bad.append(f"{scheme}: week card lacks '3 night outs': {pg.inner_text('#week-sub')!r}")
        # editing Monday's start keeps the night out
        pg.locator('.day[data-key="2026-11-16"] [data-field="s"]').click()
        pg.locator('.picker button', has_text="Save").click()
        if not pg.evaluate("state.days['2026-11-16'].n"):
            bad.append(f"{scheme}: editing the time removed the night out")
        # survives a reload
        pg.reload()
        pg.evaluate("monday = fromKey('2026-11-16'); render()")
        if pg.evaluate("[16,17,18,19].map(d => Boolean((state.days['2026-11-' + d] || {}).n))") != [True, True, True, False]:
            bad.append(f"{scheme}: night outs lost after reopening")
        summary = pg.evaluate("summaryText()")
        if "Mon 16/11: 05:00–19:00 → 13 h 15 min + night out" not in summary or "Tue 17/11: night out" not in summary \
                or "night outs: 3" not in summary:
            bad.append(f"{scheme}: shared summary lacks night outs: {summary!r}")
        # Timesheet
        pg.click("#ts-open")
        days = pg.eval_on_selector_all("#ts-body tr td:first-child", "tds => tds.map(td => td.innerText.trim())")
        want = ["Monday🌙", "Tuesday🌙", "Wednesday🌙", "Thursday", "Friday", "Saturday", "Sunday"]
        if [d.replace(" ", "") for d in days] != want:
            bad.append(f"{scheme}: Timesheet day cells {days}, expected {want}")
        if "Day off" not in pg.inner_text("#ts-body tr:nth-child(2)"):
            bad.append(f"{scheme}: Tuesday without hours not 'Day off' on the Timesheet")
        if "Night outs: 3" not in pg.inner_text("#ts-sub") or "£" in pg.inner_text("#ts"):
            bad.append(f"{scheme}: Timesheet bottom line wrong or money shown: {pg.inner_text('#ts-sub')!r}")
        for width in (390, 360):
            pg.set_viewport_size({"width": width, "height": 700})
            gap = pg.evaluate("""(() => { const s = document.querySelector('.ts-sheet'), t = document.querySelector('.ts-table');
                return s.getBoundingClientRect().right - parseFloat(getComputedStyle(s).paddingRight) - t.getBoundingClientRect().right; })()""")
            if gap < -0.5 or pg.evaluate("document.documentElement.scrollWidth") > width:
                bad.append(f"{scheme}: Timesheet too wide with night outs at {width} px ({gap:.1f})")
            bottom = pg.evaluate("document.querySelector('.ts-sheet').getBoundingClientRect().bottom")
            if bottom > 700:
                bad.append(f"{scheme}: Timesheet does not fit one screen at {width} px (bottom {bottom:.0f})")
        pg.set_viewport_size({"width": 390, "height": 700})
        pg.screenshot(path=os.path.join(OUT, f"nightout-timesheet-{scheme}.png"))
        pg.click("#ts-back")
        pg.set_viewport_size({"width": 390, "height": 844})
        pg.evaluate("monday = fromKey('2026-11-16'); render(); window.scrollTo(0, 0)")
        pg.screenshot(path=os.path.join(OUT, f"nightout-days-{scheme}.png"))
        # backup keeps them (also the day without hours)
        with pg.expect_download() as dl:
            pg.click("#export")
        path = os.path.join(OUT, f"night-backup-{scheme}.json")
        dl.value.save_as(path)
        ctx2 = b.new_context()
        pg2 = ctx2.new_page()
        pg2.goto(URL)
        pg2.set_input_files("#import-file", path)
        pg2.wait_for_function("Object.keys(state.days).length >= 4")
        if pg2.evaluate("[16,17,18,19].map(d => Boolean((state.days['2026-11-' + d] || {}).n))") != [True, True, True, False]:
            bad.append(f"{scheme}: backup lost night outs")
        ctx2.close()
        # unmarking Tuesday (no hours) removes the day completely
        moon("17").click()
        if pg.evaluate("'2026-11-17' in state.days") or moon("17").get_attribute("aria-pressed") != "false":
            bad.append(f"{scheme}: unmarking an empty day left it saved")
        ctx.close()
    b.close()
srv.shutdown()

problems = [f"JS error: {e}" for e in errors] + bad
print("\n".join(problems) if problems else "OK – night outy: zaznaczanie, zapis, Timesheet, podsumowanie, kopia")
sys.exit(1 if problems else 0)
