"""Test of the Timesheet view and the English page (Chromium, light and dark).
Checks: no Polish text left anywhere, the Timesheet shows all 7 days (Start, Finish, Break, Hours), the name, totals,
a night shift marked +1, no money on the Timesheet, the whole sheet fits on one phone screen (390 x 700 CSS px,
the part of a 6.6" phone screen left by Chrome's bars) and no sideways scroll at 360 px. Saves screenshots.
Usage (Claude cloud: PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers):
    python3 godziny/testy/test_timesheet.py godziny /tmp/zrzuty-godziny
"""
import http.server, json, os, re, shutil, socketserver, sys, tempfile, threading
from playwright.sync_api import sync_playwright

SRC, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
site = tempfile.mkdtemp(prefix="godziny-ts-")
shutil.copytree(SRC, os.path.join(site, "godziny"), ignore=shutil.ignore_patterns("testy"))

# Week 47 (16-22.11.2026): Mon 03:30-18:30 (like Radek's screenshot), Tue only a start, Wed night shift 22:00-06:00,
# Sat 06:00-14:00 with a 30 min break kept from the time of entry. Made-up rate: the Timesheet must not show money.
STATE = {"brk": 45, "rate": 15.0, "name": "Test Driver", "days": {
    "2026-11-16": {"s": "03:30", "e": "18:30", "b": 45},
    "2026-11-17": {"s": "07:00", "e": "", "b": 45},
    "2026-11-18": {"s": "22:00", "e": "06:00", "b": 45},
    "2026-11-21": {"s": "06:00", "e": "14:00", "b": 30},
}}
EXPECT_ROWS = [
    ["Monday", "16/11", "03:30", "18:30", "45m", "14h 15m"],
    ["Tuesday", "17/11", "07:00", "—", "—", "—"],
    ["Wednesday", "18/11", "22:00", "06:00+1", "45m", "7h 15m"],
    ["Thursday", "19/11", "—", "—", "—", "Day off"],
    ["Friday", "20/11", "—", "—", "—", "Day off"],
    ["Saturday", "21/11", "06:00", "14:00", "30m", "7h 30m"],
    ["Sunday", "22/11", "—", "—", "—", "Day off"],
]
POLISH = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]|\b(Tydzień|wolne|dziś|przerwa|godziny|Godziny|Ustawienia|Zapisz|Wyślij|stawka|Stawka|brutto|podatek|kopię)\b")

handler = lambda *x, **k: http.server.SimpleHTTPRequestHandler(*x, directory=site, **k)
srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()

errors, bad = [], []
with sync_playwright() as p:
    b = p.chromium.launch()
    for scheme in ("light", "dark"):
        ctx = b.new_context(viewport={"width": 390, "height": 700}, color_scheme=scheme, device_scale_factor=2)
        ctx.add_init_script(f"if (!localStorage.getItem('godziny-v1')) localStorage.setItem('godziny-v1', {json.dumps(json.dumps(STATE))})")
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"http://127.0.0.1:{port}/godziny/index.html")
        pg.clock.set_fixed_time("2026-11-17T04:00:00")
        pg.reload()
        # the whole page in English (also the picker and the empty-day placeholders)
        pg.locator('.day[data-key="2026-11-19"] [data-field="s"]').click()
        text = pg.inner_text("body") + " " + " ".join(pg.eval_on_selector_all("[aria-label],[placeholder]",
            "els => els.map(e => (e.getAttribute('aria-label') || '') + ' ' + (e.getAttribute('placeholder') || ''))"))
        text += " " + pg.evaluate("summaryText()") + " " + pg.title()
        found = sorted(set(m.group(0) for m in POLISH.finditer(text)))
        if found:
            bad.append(f"{scheme}: Polish text left on the page: {found}")
        pg.locator('.picker button', has_text="Cancel").click()
        if pg.input_value("#name") != "Test Driver":
            bad.append(f"{scheme}: name not shown in Settings")
        # Timesheet
        pg.click("#ts-open")
        if not pg.is_visible("#ts") or pg.is_visible("main"):
            bad.append(f"{scheme}: Timesheet did not open on its own screen")
        rows = pg.eval_on_selector_all("#ts-body tr", "trs => trs.map(tr => [...tr.cells].map(td => td.innerText.replace(/\\s+/g, '')))")
        want = [[c.replace(" ", "") for c in r] for r in EXPECT_ROWS]
        if rows != want:
            bad.append(f"{scheme}: Timesheet rows {rows}, expected {want}")
        head = pg.inner_text("#ts .ts-top") + " " + pg.inner_text("#ts-week")
        for part in ("Timesheet", "Test Driver", "Week 47", "16–22 November 2026"):
            if part not in head:
                bad.append(f"{scheme}: Timesheet header lacks {part!r}: {head!r}")
        tot = pg.inner_text("#ts-total") + " " + pg.inner_text("#ts-dec") + " " + pg.inner_text("#ts-sub")
        for part in ("29 h", "(29.00 h)", "Days worked: 3", "Time on site: 31 h", "Breaks: 2 h"):
            if part not in tot:
                bad.append(f"{scheme}: Timesheet totals lack {part!r}: {tot!r}")
        if "£" in pg.inner_text("#ts"):
            bad.append(f"{scheme}: money shown on the Timesheet")
        if "finish − start" in pg.inner_text("#ts") or pg.locator("#ts-note").count():
            bad.append(f"{scheme}: the explanation line under the totals is back (Radek asked to remove it)")
        bottom = pg.evaluate("document.querySelector('.ts-sheet').getBoundingClientRect().bottom")
        if bottom > 700:
            bad.append(f"{scheme}: Timesheet does not fit on one screen (bottom at {bottom:.0f} px of 700)")
        pg.screenshot(path=os.path.join(OUT, f"timesheet-{scheme}.png"))
        for width in (390, 360):
            pg.set_viewport_size({"width": width, "height": 700})
            if pg.evaluate("document.documentElement.scrollWidth") > width:
                bad.append(f"{scheme}: sideways scroll on the Timesheet at {width} px")
            # the table must stay inside the card's padding (no column touching or crossing the edge)
            gap = pg.evaluate("""(() => { const s = document.querySelector('.ts-sheet'), t = document.querySelector('.ts-table');
                const pad = parseFloat(getComputedStyle(s).paddingRight);
                return s.getBoundingClientRect().right - pad - t.getBoundingClientRect().right; })()""")
            if gap < -0.5:
                bad.append(f"{scheme}: table sticks out of the card by {-gap:.1f} px at {width} px")
        pg.set_viewport_size({"width": 390, "height": 700})
        # week arrows on the Timesheet, then back to the normal page on the same week
        pg.click("#ts-next")
        if "Week 48" not in pg.inner_text("#ts-week") or pg.inner_text("#ts-total") != "0 h":
            bad.append(f"{scheme}: next week on the Timesheet: {pg.inner_text('#ts-week')!r} {pg.inner_text('#ts-total')!r}")
        pg.click("#ts-prev")
        pg.click("#ts-back")
        if pg.is_visible("#ts") or "Week 47" not in pg.inner_text("#week-title"):
            bad.append(f"{scheme}: Back did not return to the page on week 47")
        # changing the name updates the Timesheet
        pg.fill("#name", "  Other   Name ")
        pg.dispatch_event("#name", "change")
        pg.click("#ts-open")
        if pg.inner_text("#ts-name") != "Other Name":
            bad.append(f"{scheme}: new name not on the Timesheet: {pg.inner_text('#ts-name')!r}")
        pg.reload()
        if pg.input_value("#name") != "Other Name":
            bad.append(f"{scheme}: name not kept after reopening")
        ctx.close()
    b.close()
srv.shutdown()

problems = [f"JS error: {e}" for e in errors] + bad
print("\n".join(problems) if problems else "OK – Timesheet: 7 dni, po angielsku, bez pieniędzy, mieści się na 1 ekranie")
sys.exit(1 if problems else 0)
