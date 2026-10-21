"""Walk-forward check of the goals model on history: the agent's 11 leagues, 6 seasons (football-data.co.uk).

Answers three questions without looking into the future:
  1) how far the model's chance of over 2.5 is from what happened, per league and season (bias, calibration slope),
  2) does a calibration of the model (fitted only on earlier matches) help: log loss vs the market,
  3) paper bets like the agent's "Model + rynek": how many Over/Under, profit and value vs the closing price (CLV),
     before and after the calibration, with the market taken from Pinnacle or from the average of bookmakers.

Never writes into gole/. Needs the internet (GitHub Actions) or --local DIR with data/<code>/season-XXYY.csv files.
Usage: python3 gole/testy/historia.py [--local DIR] [--cache DIR] [--today 2026-10-21] [--only E0,SP1]
"""
import argparse, datetime as dt, json, math, os, sys

GOLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GOLE)
import engine as E  # noqa: E402
import agent as AG  # noqa: E402

GAINS = (0.0, 0.0005, 0.001, 0.002)   # tested minimum gains for the model's weight in the blend
BASE_HL = (60.0, 120.0, 240.0)   # tested half-lives (days) of the league scoring level
EDGE = 0.03            # the agent's "Model + rynek" threshold
ODDS = (1.5, 3.2)      # the agent's odds range


def mean_goals(p_over):
    """Poisson mean of total goals that gives this chance of over 2.5 (the model's expected goals, approximately)."""
    lo, hi = 0.2, 8.0
    for _ in range(50):
        m = (lo + hi) / 2
        if 1 - math.exp(-m) * (1 + m + m * m / 2) < p_over:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


def ll(p, y):
    return -math.log(max(p if y else 1 - p, 1e-9))


def summ(rows, key):
    """Log loss, mean probability, bias and calibration slope of rows[key] against the result."""
    rs = [r for r in rows if r.get(key) is not None]
    if not rs:
        return None
    n = len(rs)
    rate = sum(r["y"] for r in rs) / n
    mp = sum(r[key] for r in rs) / n
    a, b = E.fit_platt([E.logit(r[key]) for r in rs], [r["y"] for r in rs], lam=0.0) if n >= 50 else (None, None)
    return {"n": n, "ll": sum(ll(r[key], r["y"]) for r in rs) / n, "mean": mp, "rate": rate, "bias": mp - rate, "slope": b}


def bets(rows, pkey, book, fair_key="qc"):
    """Paper bets at one bookmaker: the side with the biggest edge over pkey, if above EDGE."""
    acc = {"n": 0, "over": 0, "under": 0, "profit": 0.0, "clv": 0.0, "nc": 0}
    for r in rows:
        p, odds = r.get(pkey), r["odds"].get(book)
        if p is None or not odds:
            continue
        best = None
        for i, (q, o) in enumerate(zip([p, 1 - p], odds)):
            e = q * o - 1
            if best is None or e > best[0]:
                best = (e, i, o)
        e, i, o = best
        if e < EDGE or not ODDS[0] <= o <= ODDS[1]:
            continue
        won = (i == 0) == bool(r["y"])
        acc["n"] += 1
        acc["over" if i == 0 else "under"] += 1
        acc["profit"] += o - 1 if won else -1
        if r.get(fair_key):
            q = r[fair_key] if i == 0 else 1 - r[fair_key]
            acc["clv"] += o * q - 1
            acc["nc"] += 1
    n = acc["n"]
    return {"n": n, "over": acc["over"], "under": acc["under"], "roi": acc["profit"] / n if n else None,
            "clv": acc["clv"] / acc["nc"] if acc["nc"] else None}


def pct(x, sign=True):
    return "   –  " if x is None else (f"{x * 100:+5.1f}%" if sign else f"{x * 100:5.1f}%")


def league_rows(src, code, years):
    ys = list(reversed(years))  # oldest first
    seasons = [sorted(src.season(code, y, y == years[0]), key=lambda m: m["d"]) for y in ys]
    while seasons and not seasons[0]:
        seasons.pop(0)
        ys.pop(0)
    if len(seasons) < 3:
        return [], None
    played = [[m for m in s if m["hg"] is not None] for s in seasons]
    use_sot = sum(1 for m in played[-1][-60:] + played[-2][-60:] if m["hst"] is not None) > 20
    preds_by_combo = [E.run_rater(seasons, h, k, E.SOT_W if use_sot else 0.0)[0] for h, k in E.GRID]
    out = []
    base_preds = {bh: {} for bh in BASE_HL}
    for i in range(2, len(seasons)):
        if len(played[i]) < 30:
            continue
        prm = E.choose_params([m for s in played[max(0, i - E.TUNE_SEASONS):i] for m in s], preds_by_combo, False)
        if not prm:
            continue
        # weight variants: how the engine picked it before 21.10.2026 (1 season, any gain) and with other minimum gains
        variants = {"przed (1 sezon, bez progu)": E.choose_params(played[i - 1], preds_by_combo, False, min_gain=0.0)}
        for g in GAINS:
            variants[f"2 sezony, próg {g}"] = E.choose_params([m for s in played[max(0, i - E.TUNE_SEASONS):i] for m in s],
                                                             preds_by_combo, False, min_gain=g)
        preds = preds_by_combo[prm["combo"]]
        for bh in BASE_HL:  # variant: the league's scoring level follows recent matches faster than team strengths
            if prm["combo"] not in base_preds[bh]:
                h, k = E.GRID[prm["combo"]]
                base_preds[bh][prm["combo"]] = E.run_rater(seasons, h, k, E.SOT_W if use_sot else 0.0, base_half_life=bh)[0]
        # every earlier match with this season's model settings, for the calibration (fitted on the past only)
        hist = [(m["d"], E.logit(preds[id(m)][0]), int(m["hg"] + m["ag"] > 2)) for s in played[1:i + 1] for m in s if id(m) in preds]
        for m in played[i]:
            p = preds.get(id(m))
            if p is None:
                continue
            qo = E.demargin(m["ou"].get("P"))
            qa = E.demargin(m["ou"].get("Avg"))
            qc = E.demargin(m["ouc"].get("P") or m["ouc"].get("Avg"))
            qb, qbc = E.demargin(m["ou"].get("BFE")), E.demargin(m["ouc"].get("BFE"))
            qac = E.demargin(m["ouc"].get("Avg"))
            out.append({"lg": code, "si": E.season_code(ys[i]), "d": m["d"], "pm": p[0], "y": int(m["hg"] + m["ag"] > 2), "qo": qo[0] if qo else None,
                        "qa": qa[0] if qa else None, "qc": qc[0] if qc else None, "qb": qb[0] if qb else None,
                        "qbc": qbc[0] if qbc else None, "qac": qac[0] if qac else None, "hasP": bool(m["ou"].get("P")),
                        "pv": {bh: base_preds[bh][prm["combo"]].get(id(m), (None,))[0] for bh in BASE_HL},
                        "qs": (AG.fair_ou(m["ou"])[0] or [None])[0], "qsc": (AG.fair_ou(m["ouc"])[0] or [None])[0],
                        "var": {k: (preds_by_combo[v["combo"]].get(id(m), (None,))[0], v["w_ou"]) for k, v in variants.items() if v},
                        "odds": {b: m["ou"].get(b) for b in ("B365", "Max", "Avg", "P")}, "_hist": hist, "_w": prm["w_ou"]})
    return out, seasons


def calibrate(rows):
    """Adds pmc: the model's chance after a calibration fitted on matches before the first day of the row's month."""
    cache = {}
    for r in rows:
        month = r["d"].replace(day=1)
        key = (r["lg"], r["si"], month)
        if key not in cache:
            past = [(x, y) for d, x, y in r["_hist"] if d < month]
            cache[key] = E.calib_params([x for x, _ in past], [y for _, y in past])
        r["pmc"] = E.apply_calib(r["pm"], cache[key])


def blends(rows, all_rows):
    """Walk-forward model weight per league and season: chosen on the previous season, as the engine does."""
    by = {}
    for r in all_rows:
        by.setdefault((r["lg"], r["si"]), []).append(r)

    def best_w(prev, pkey, mkey):
        sc = []
        for w in E.W_GRID:
            s = n = 0
            for r in prev:
                if r.get(mkey) is None:
                    continue
                s += ll(E.pool([r[pkey], 1 - r[pkey]], [r[mkey], 1 - r[mkey]], w)[0], r["y"]); n += 1
            if n >= 40:
                sc.append((s / n, w))
        return min(sc)[1] if sc else prev[0]["_w"]

    for (lg, si), rs in by.items():
        prev = by.get((lg, E.season_code(int("20" + si[:2]) - 1)), [])
        for pkey, mkey, out in (("pm", "qo", "b_raw"), ("pmc", "qo", "b_cal"), ("pm", "qa", "a_raw"), ("pmc", "qa", "a_cal")):
            w = best_w(prev, pkey, mkey) if prev else rs[0]["_w"]   # first test season: the engine's own choice
            for r in rs:
                r[out] = E.pool([r[pkey], 1 - r[pkey]], [r[mkey], 1 - r[mkey]], w)[0] if r.get(mkey) is not None else None
                r["w_" + out] = w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local")
    ap.add_argument("--cache", default=os.path.join(GOLE, ".cache"))
    ap.add_argument("--today")
    ap.add_argument("--only")
    ap.add_argument("--json", help="also write the numbers to this file")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    src = E.Source(a.local, a.cache)
    years = E.season_years(today, E.N_SEASONS)
    codes = a.only.split(",") if a.only else AG.LEAGUES
    rows, n_season = [], {}
    for code in codes:
        rs, seasons = league_rows(src, code, years)
        rows += rs
        if seasons:
            n_season[code] = [len([m for m in s if m["hg"] is not None]) for s in seasons]
    if src.errors:
        print("błędy pobierania:", src.errors[:10])
    if not rows:
        raise SystemExit("brak danych")
    calibrate(rows)
    blends(rows, rows)
    seasons_ = sorted({r["si"] for r in rows})

    print(f"\nTEST NA HISTORII – {len(rows)} meczów, ligi {', '.join(codes)}; sezony testowe = 3.–6. z 6 pobranych "
          f"(model i waga dobierane na {E.TUNE_SEASONS} poprzednich sezonach, kalibracja na meczach sprzed danego miesiąca)\n")
    print("1) SKRZYWIENIE MODELU: średnia szansa over 2.5 z modelu minus to, co się stało (pkt proc.), i nachylenie kalibracji")
    print("   (nachylenie 1.0 = szanse dobrze rozłożone; powyżej 1 = model za ostrożny, ściska szanse w stronę 50%)")
    hdr = "   liga  " + "".join(f"{s[:2] + '/' + s[2:]:>16}" for s in seasons_) + f"{'razem':>16}{'rynek(Pinn.)':>14}"
    print(hdr)
    for code in codes + ["RAZEM"]:
        rs = rows if code == "RAZEM" else [r for r in rows if r["lg"] == code]
        if not rs:
            continue
        cells = []
        for s in seasons_ + [None]:
            x = summ([r for r in rs if s is None or r["si"] == s], "pm")
            cells.append(f"{x['bias'] * 100:+6.1f} / {x['slope']:.2f}".rjust(16) if x and x["slope"] else (f"{x['bias'] * 100:+6.1f}".rjust(16) if x else " " * 16))
        mk = summ(rs, "qo")
        cells.append(f"{mk['bias'] * 100:+6.1f} / {mk['slope']:.2f}".rjust(14) if mk and mk["slope"] else "")
        print(f"   {code:6}" + "".join(cells))
    print("\n   Skrzywienie w zależności od tego, co mówi rynek (Pinnacle przed meczem), wszystkie ligi:")
    for lo, hi in ((0, 0.45), (0.45, 0.52), (0.52, 0.58), (0.58, 0.65), (0.65, 1.01)):
        rs = [r for r in rows if r["qo"] is not None and lo <= r["qo"] < hi]
        if rs:
            n = len(rs)
            print(f"     rynek {lo * 100:3.0f}–{min(hi, 1) * 100:3.0f}%: meczów {n:5}, weszło {sum(r['y'] for r in rs) / n * 100:5.1f}%, "
                  f"rynek {sum(r['qo'] for r in rs) / n * 100:5.1f}%, model {sum(r['pm'] for r in rs) / n * 100:5.1f}%, "
                  f"model po kalibracji {sum(r['pmc'] for r in rs) / n * 100:5.1f}%")
    print("\n   Skrzywienie wg miesiąca sezonu (model − wynik, pkt proc.), wszystkie ligi:")
    for mon in (8, 9, 10, 11, 12, 1, 2, 3, 4, 5):
        rs = [r for r in rows if r["d"].month == mon]
        if len(rs) >= 50:
            x, y = summ(rs, "pm"), summ(rs, "pmc")
            print(f"     miesiąc {mon:2}: meczów {len(rs):5}, model {x['bias'] * 100:+5.1f}, po kalibracji {y['bias'] * 100:+5.1f}, "
                  f"nachylenie {x['slope'] or 0:.2f} → {y['slope'] or 0:.2f}")

    print("\n   Czy rynek też się mylił? Średnia szansa minus wynik (pkt proc.) – model / Pinnacle / średnia bukm. / giełda Betfair:")
    for s_ in seasons_:
        rs = [r for r in rows if r["si"] == s_]
        cells = []
        for k in ("pm", "qo", "qa", "qb"):
            x = summ(rs, k)
            cells.append(f"{x['bias'] * 100:+5.1f} (n {x['n']})" if x else "   –      ")
        print(f"     {s_[:2]}/{s_[2:]}: " + " / ".join(cells) + f"; mecze z Pinnacle: {sum(r['hasP'] for r in rs)}/{len(rs)}, over weszło {sum(r['y'] for r in rs) / len(rs) * 100:.1f}%")
    print("\n   Wariant modelu: średnia goli w lidze liczona z krótszej pamięci (pół-okres w dniach) – skrzywienie i log loss")
    for bh in (None,) + BASE_HL:
        key = "pm" if bh is None else f"pv{int(bh)}"
        if bh is not None:
            for r in rows:
                r[key] = r["pv"][bh]
        line = f"     {'obecny model' if bh is None else f'pół-okres {int(bh):3} dni':18}"
        for s_ in seasons_ + [None]:
            x = summ([r for r in rows if (s_ is None or r["si"] == s_) and r.get(key) is not None], key)
            line += f" | {('razem' if s_ is None else s_[:2] + '/' + s_[2:])} {x['bias'] * 100:+5.1f} ll {x['ll']:.4f}" if x else ""
        print(line)
    print("\n2) LOG LOSS (mniej = lepiej) na meczach z kursami Pinnacle przed meczem i na zamknięcie")
    print("   liga     meczów   model  model+kal  blend(P)  blend+kal(P)  blend(śr.)  blend+kal(śr.)  Pinnacle  zamknięcie   waga przed→po")
    res = {}
    for code in codes + ["RAZEM"]:
        rs = rows if code == "RAZEM" else [r for r in rows if r["lg"] == code]
        rs = [r for r in rs if r["qo"] is not None and r["qc"] is not None and r["qa"] is not None]
        if not rs:
            continue
        n = len(rs)
        L = {k: sum(ll(r[k], r["y"]) for r in rs) / n for k in ("pm", "pmc", "b_raw", "b_cal", "a_raw", "a_cal", "qo", "qc")}
        w0 = sum(r["w_b_raw"] for r in rs) / n
        w1 = sum(r["w_b_cal"] for r in rs) / n
        res[code] = {"n": n, "ll": L, "w": [w0, w1]}
        print(f"   {code:6} {n:7}  {L['pm']:.4f}   {L['pmc']:.4f}    {L['b_raw']:.4f}     {L['b_cal']:.4f}       {L['a_raw']:.4f}       "
              f"{L['a_cal']:.4f}       {L['qo']:.4f}    {L['qc']:.4f}      {w0:.2f}→{w1:.2f}")

    print("\n3) ZAKŁADY NA SUCHO jak „Model + rynek” (przewaga 3%+, kursy 1.50–3.20), CLV = vs zamknięcie Pinnacle")
    print("   (Bet365 ≈ jeden bukmacher z UK; Max = najlepszy kurs na rynku, zawyżony przez pojedyncze stare ceny)")
    out3 = {}
    for label, key in (("rynek = Pinnacle, bez kalibracji", "b_raw"), ("rynek = Pinnacle, z kalibracją", "b_cal"),
                       ("rynek = średnia bukm., bez kalibracji", "a_raw"), ("rynek = średnia bukm., z kalibracją", "a_cal"),
                       ("sam model, bez kalibracji", "pm"), ("sam model, z kalibracją", "pmc"),
                       ("bez modelu: Pinnacle jako uczciwa cena", "qo"), ("bez modelu: średnia jako uczciwa cena", "qa"),
                       ("bez modelu: giełda Betfair jako uczciwa cena", "qb")):
        line = f"   {label:40}"
        for book in ("B365", "Max"):
            b = bets(rows, key, book)
            out3[f"{key}|{book}"] = b
            line += f" | {book:4} typów {b['n']:5} (Over {b['over']:4}, Under {b['under']:4}) wynik {pct(b['roi'])} CLV {pct(b['clv'])}"
        print(line)
    print("\n   „Kurs ponad rynek” z giełdą Betfair (przed meczem) jako uczciwą ceną, przy różnych progach przewagi; CLV vs zamknięcie giełdy / średniej:")
    global EDGE
    for e in (0.0, 0.01, 0.02, 0.03):
        EDGE = e
        line = f"     próg {e * 100:3.0f}%:"
        for book in ("B365", "Avg", "Max"):
            b, b2 = bets(rows, "qb", book, "qbc"), bets(rows, "qb", book, "qac")
            line += f" | {book:4} typów {b['n']:4} (O {b['over']:3}/U {b['under']:3}) wynik {pct(b['roi'])} CLV {pct(b['clv'])} / {pct(b2['clv'])}"
        print(line)
    EDGE = 0.03
    print("\n   Na ligę (Bet365, rynek = Pinnacle): bez kalibracji → z kalibracją")
    for code in codes:
        rs = [r for r in rows if r["lg"] == code]
        b0, b1 = bets(rs, "b_raw", "B365"), bets(rs, "b_cal", "B365")
        print(f"     {code:5} typów {b0['n']:4} (O {b0['over']:3}/U {b0['under']:3}) wynik {pct(b0['roi'])} CLV {pct(b0['clv'])}"
              f"  →  typów {b1['n']:4} (O {b1['over']:3}/U {b1['under']:3}) wynik {pct(b1['roi'])} CLV {pct(b1['clv'])}")
    print("\n4) WAGA MODELU: jak silnik dobierał ją przed 21.10 i warianty nowego doboru")
    print("   (rynek = Pinnacle, a gdy go brak – giełda Betfair, potem średnia; zakłady jak „Model + rynek” przy Bet365 i przy najlepszym kursie)")
    for name in list(rows[0]["var"]):
        for r in rows:
            v = r["var"].get(name)
            r["vb"] = E.pool([v[0], 1 - v[0]], [r["qs"], 1 - r["qs"]], v[1])[0] if v and v[0] is not None and r["qs"] is not None else None
        ok = [r for r in rows if r["vb"] is not None]
        lls = sum(ll(r["vb"], r["y"]) for r in ok) / len(ok)
        llm = sum(ll(r["qs"], r["y"]) for r in ok) / len(ok)
        ws = [r["var"][name][1] for r in ok]
        line = f"   {name:28} log loss {lls:.4f} (sam rynek {llm:.4f}), średnia waga {sum(ws) / len(ws):.2f}, ligo-sezony z wagą 0: {sum(1 for w in ws if w == 0) / len(ws) * 100:3.0f}%"
        for book in ("B365", "Max"):
            b = bets(ok, "vb", book, "qsc")
            line += f" | {book:4} typów {b['n']:4} (O {b['over']:3}/U {b['under']:3}) wynik {pct(b['roi'])} CLV {pct(b['clv'])}"
        print(line)
    print("\n5) REGUŁA „OVER, GDY MODEL SPODZIEWA SIĘ CO NAJMNIEJ X GOLI” (Over zawsze, bez patrzenia na przewagę; kursy 1.50–3.20)")
    print("   (oczekiwane gole odtworzone z szansy modelu na over: 2.5 gola = 46%, 2.6 = 48%, 2.7 = 51%, 3.0 = 58%)")
    for r in rows:
        r["mu"] = mean_goals(r["pm"])
    for lo, hi in ((2.5, 2.6), (2.6, 2.7), (2.7, 2.8), (2.8, 3.0), (3.0, 9.0), (2.6, 9.0)):
        rs = [r for r in rows if lo <= r["mu"] < hi]
        line = f"   model {lo:.1f}–{hi:.1f} goli: meczów {len(rs):5}, over weszło {sum(r['y'] for r in rs) / max(1, len(rs)) * 100:5.1f}%" if hi < 9 else \
               f"   model {lo:.1f}+ goli:     meczów {len(rs):5}, over weszło {sum(r['y'] for r in rs) / max(1, len(rs)) * 100:5.1f}%"
        for book in ("B365", "Max"):
            n = won = 0
            profit = clv = nc = 0.0
            for r in rs:
                o = (r["odds"].get(book) or [None])[0]
                if not o or not 1.5 <= o <= 3.2:
                    continue
                n += 1
                won += r["y"]
                profit += o - 1 if r["y"] else -1
                if r.get("qsc") is not None:
                    clv += o * r["qsc"] - 1
                    nc += 1
            line += f" | {book:4} zakładów {n:5}, wynik {pct(profit / n if n else None)}, CLV {pct(clv / nc if nc else None)}"
        print(line)
    if a.json:
        json.dump({"ll": res, "bets": out3, "seasons": n_season}, open(a.json, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
