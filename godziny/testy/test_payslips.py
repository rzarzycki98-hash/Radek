"""Test of learning from payslips on the Work Hours page (Chromium 390 px, light and dark).
Numbers are made up (public repository). Checks: PAYSLIP lines pasted (two at once) are read, rates are learned
as paid money / paid hours and the net adjustment as payslip net minus the page's tax+NI sum (e.g. a pension),
only the last 4 payslips count, a week with a payslip shows the payslip amount (✓ in Weeks), a warning when the
payslip paid other hours than logged, wrong lines are refused, the same week is replaced, removing re-learns,
everything survives a reload and a backup file. Saves screenshots.
Usage (Claude cloud: PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers):
    python3 godziny/testy/test_payslips.py godziny /tmp/zrzuty-godziny
"""
import http.server, json, math, os, shutil, socketserver, sys, tempfile, threading
from playwright.sync_api import sync_playwright

SRC, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
site = tempfile.mkdtemp(prefix="godziny-slip-")
shutil.copytree(SRC, os.path.join(site, "godziny"), ignore=shutil.ignore_patterns("testy"))


def r2(x):
    return math.floor(x * 100 + 0.5 + 1e-9) / 100


def tax_ni(g):  # same rules as the page (1257L w1m1, NI category A), worked out by hand here
    taxable = max(0, math.floor(g - 12579 / 52 + 1e-9))
    tax = r2(min(taxable, 37700 / 52) * 0.2 + max(0, min(taxable, (125140 - 12570) / 52) - 37700 / 52) * 0.4)
    ni = r2(max(0, min(g, 967) - 242) * 0.08 + max(0, g - 967) * 0.02)
    return tax, ni


def line(wc, bh, bp, sh, sp, other=5.00):
    g = r2(bp + sp)
    t, n = tax_ni(g)
    net = r2(g - t - n - other)
    return f"PAYSLIP w/c {wc} | basic {bh:.2f} h £{bp:.2f} | sat {sh:.2f} h £{sp:.2f} | gross £{g:,.2f} | tax £{t:.2f} | NI £{n:.2f} | net £{net:.2f}", net


# Log: week 43 (19-25.10) Mon-Fri 07:00-16:27 = 43.5 h; week 44 (26.10-1.11) the same + Saturday 07:00-15:45 = 8 h;
# week 45 (2-8.11) Monday only (8.7 h, no payslip). Payslips: 5 pounds "other" (a pension) each week;
# week 44 paid only 42.75 basic hours (0.75 h missing).
DAYS = {f"2026-10-{d}": {"s": "07:00", "e": "16:27", "b": 45} for d in (19, 20, 21, 22, 23, 26, 27, 28, 29, 30)}
DAYS["2026-10-31"] = {"s": "07:00", "e": "15:45", "b": 45}
DAYS["2026-11-02"] = {"s": "07:00", "e": "16:27", "b": 45}
STATE = {"brk": 45, "rate": 0, "sat": 0, "days": DAYS}
L43, NET43 = line("19/10/2026", 43.5, 652.50, 0, 0)
L44, NET44 = line("26/10/2026", 42.75, 641.25, 8.0, 160.00)


def expected_estimate(basic_h, sat_h, corr):
    g = r2(r2(basic_h * 15) + r2(sat_h * 20))
    t, n = tax_ni(g)
    return r2(g - t - n + corr)


handler = lambda *x, **k: http.server.SimpleHTTPRequestHandler(*x, directory=site, **k)
srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{port}/godziny/index.html"


def money(x):
    return f"£{x:,.2f}"


errors, bad = [], []
with sync_playwright() as p:
    b = p.chromium.launch()
    for scheme in ("light", "dark"):
        ctx = b.new_context(viewport={"width": 390, "height": 844}, color_scheme=scheme, accept_downloads=True)
        ctx.add_init_script(f"if (!localStorage.getItem('godziny-v1')) localStorage.setItem('godziny-v1', {json.dumps(json.dumps(STATE))})")
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(URL)
        # a wrong line is refused and nothing changes
        pg.fill("#slip-in", "PAYSLIP w/c 19/10/2026 | basic 43.50 h £652.50 | gross £999.00 | tax £1 | NI £1 | net £1")
        pg.click("#slip-add")
        if "Not added" not in pg.inner_text("#toast") or pg.evaluate("Object.keys(state.slips || {}).length"):
            bad.append(f"{scheme}: a wrong payslip line was not refused: {pg.inner_text('#toast')!r}")
        # two payslips pasted at once
        pg.fill("#slip-in", L43 + "\n" + L44)
        pg.click("#slip-add")
        if pg.evaluate("Object.keys(state.slips || {}).length") != 2 or pg.input_value("#slip-in"):
            bad.append(f"{scheme}: two pasted payslips not added: {pg.inner_text('#toast')!r}")
        learned = pg.evaluate("[state.rate, state.sat, state.corr]")
        if learned != [15, 20, -5]:
            bad.append(f"{scheme}: learned rate/Saturday/adjustment {learned}, expected [15, 20, -5]")
        if pg.input_value("#rate") != "15.00" or pg.input_value("#sat") != "20.00":
            bad.append(f"{scheme}: rate fields not filled in from the payslips")
        txt = pg.inner_text("#slip-learned")
        if "rate £15.00" not in txt or "Saturday £20.00" not in txt or "−£5.00" not in txt:
            bad.append(f"{scheme}: learned line wrong: {txt!r}")
        # week 44: payslip amount on the card, page estimate and the missing 0.75 h warning
        pg.locator("#weeks button", has_text="26/10").click()
        est44 = expected_estimate(43.5, 8, -5)
        if pg.inner_text("#pay-net") != money(NET44):
            bad.append(f"{scheme}: week 44 card shows {pg.inner_text('#pay-net')!r}, expected payslip {money(NET44)}")
        if f"page estimate {money(est44)}" not in pg.inner_text("#pay-when"):
            bad.append(f"{scheme}: week 44 page estimate wrong: {pg.inner_text('#pay-when')!r} (expected {money(est44)})")
        warn = pg.inner_text("#pay-warn") if pg.is_visible("#pay-warn") else ""
        if "50.75 h" not in warn or "51.50 h" not in warn or "0.75 h not paid" not in warn:
            bad.append(f"{scheme}: missing-hours warning wrong: {warn!r}")
        if "other £5.00" not in pg.evaluate("$('pay-sub').textContent"):
            bad.append(f"{scheme}: payslip breakdown lacks the 'other' deduction")
        if money(NET44) + " ✓" not in pg.inner_text("#weeks"):
            bad.append(f"{scheme}: weeks list does not show the payslip amount with ✓")
        pg.screenshot(path=os.path.join(OUT, f"payslip-week-{scheme}.png"))
        # week 43: hours match, so no warning
        pg.locator("#weeks button", has_text="19/10").click()
        if pg.is_visible("#pay-warn"):
            bad.append(f"{scheme}: warning shown for a week whose hours match")
        # week 45 without a payslip: estimate with the learned rate and adjustment
        pg.locator("#weeks button", has_text="2/11").click()
        if pg.inner_text("#pay-net") != money(expected_estimate(8.7, 0, -5)):
            bad.append(f"{scheme}: week 45 estimate {pg.inner_text('#pay-net')!r}, expected {money(expected_estimate(8.7, 0, -5))}")
        if "payslip adjustment £5.00" not in pg.evaluate("$('pay-sub').textContent"):
            bad.append(f"{scheme}: estimate breakdown lacks the payslip adjustment")
        # October total adds the payslips of weeks ending in October (week 43); week 44 ends on 1.11
        pg.locator("#weeks button", has_text="19/10").click()
        if money(NET43) not in pg.inner_text("#month"):
            bad.append(f"{scheme}: October total does not use the payslip: {pg.inner_text('#month')!r}")
        pg.locator("#slips").scroll_into_view_if_needed()
        pg.screenshot(path=os.path.join(OUT, f"payslips-{scheme}.png"), full_page=True)
        # the same week again replaces it (now no pension): adjustment moves to -2.50
        l44b, _ = line("26/10/2026", 42.75, 641.25, 8.0, 160.00, other=0)
        pg.fill("#slip-in", l44b)
        pg.click("#slip-add")
        if pg.evaluate("[Object.keys(state.slips).length, state.corr]") != [2, -2.5]:
            bad.append(f"{scheme}: replacing week 44 gave {pg.evaluate('[Object.keys(state.slips).length, state.corr]')}")
        # only the last 4 payslips count: 3 older weeks at £10/h do not move the rate while 4 newer exist
        old = [line(wc, 40, 400.00, 0, 0)[0] for wc in ("28/09/2026", "05/10/2026", "12/10/2026")]
        new = [line(wc, 40, 600.00, 0, 0)[0] for wc in ("02/11/2026", "09/11/2026")]
        pg.fill("#slip-in", "\n".join(old + new))
        pg.click("#slip-add")
        rate = pg.evaluate("state.rate")
        # last 4: w/c 9.11, 2.11 (40 h £600 each), 26.10 (42.75 h £641.25), 19.10 (43.5 h £652.50)
        want = r2((600 + 600 + 641.25 + 652.50) / (40 + 40 + 42.75 + 43.5))
        if rate != want:
            bad.append(f"{scheme}: rate from the last 4 payslips {rate}, expected {want}")
        # removing a payslip re-learns
        pg.locator('#slips button[aria-label="Remove payslip for week 46"]').click()
        want = r2((600 + 641.25 + 652.50 + 400) / (40 + 42.75 + 43.5 + 40))
        if pg.evaluate("state.rate") != want or pg.evaluate("Object.keys(state.slips).length") != 6:
            bad.append(f"{scheme}: after removing, rate {pg.evaluate('state.rate')}, expected {want}")
        # kept after reopening, and the Timesheet still shows no money
        pg.reload()
        if pg.evaluate("Object.keys(state.slips).length") != 6 or pg.input_value("#rate") != f"{want:.2f}":
            bad.append(f"{scheme}: payslips or learned rate lost after reopening")
        pg.click("#ts-open")
        if "£" in pg.inner_text("#ts"):
            bad.append(f"{scheme}: money on the Timesheet")
        pg.click("#ts-back")
        # backup file carries the payslips to another phone
        with pg.expect_download() as dl:
            pg.click("#export")
        path = os.path.join(OUT, f"backup-{scheme}.json")
        dl.value.save_as(path)
        ctx2 = b.new_context(viewport={"width": 390, "height": 844})
        pg2 = ctx2.new_page()
        pg2.on("pageerror", lambda e: errors.append(str(e)))
        pg2.goto(URL)
        pg2.set_input_files("#import-file", path)
        pg2.wait_for_function("Object.keys(state.slips || {}).length === 6")
        if pg2.evaluate("state.rate") != want or "6 payslips" not in pg2.inner_text("#toast"):
            bad.append(f"{scheme}: backup did not bring the payslips back: {pg2.inner_text('#toast')!r}")
        ctx2.close()
        ctx.close()
    b.close()
srv.shutdown()

problems = [f"JS error: {e}" for e in errors] + bad
print("\n".join(problems) if problems else "OK – payslipy: nauka stawek i poprawki, ostatnie 4, ostrzeżenie o godzinach, kopia")
sys.exit(1 if problems else 0)
