#!/usr/bin/env python3
"""Stan agenta Linii Goli w kilku linijkach – dla Radka i dla Claude na początku nowej rozmowy.

Czyta gole/agent.json (zapisywany przez GitHub Actions co 4 godziny) i niczego nie zmienia.
Użycie:
    git pull && python3 gole/stan.py          # stan z repozytorium
    python3 gole/stan.py inny/agent.json      # inny plik (np. z testu)
"""
import datetime as dt, json, os, sys
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
HERE = os.path.dirname(os.path.abspath(__file__))
SPORT = {"pilka": "Piłka", "nba": "NBA", "all": "agent"}
STATUS = {"won": "wygrany", "lost": "przegrany", "push": "zwrot (równo z linią)", "void": "zwrot (mecz się nie odbył)"}


def gbp(x, sign=False):
    if x is None:
        return "—"
    s = f"£{abs(x):,.2f}"
    if x < -0.004:
        return "−" + s
    return "+" + s if sign and x > 0.004 else s


def pct(x, sign=True):
    if x is None:
        return "—"
    return f"{x * 100:+.1f}%" if sign else f"{x * 100:.0f}%"


def when(iso):
    try:
        return dt.datetime.fromisoformat(iso).astimezone(LONDON).strftime("%d.%m %H:%M")
    except (TypeError, ValueError):
        return iso or "—"


def bet_txt(b):
    return f"{b.get('side')} {b.get('line', 2.5)} @ {b.get('odds') or 0:.2f} ({b.get('book', '?')})"


def main(path):
    try:
        a = json.load(open(path, encoding="utf-8"))
    except FileNotFoundError:
        print(f"Brak pliku {path} – agent jeszcze nie ruszył albo najpierw zrób git pull.")
        return 1
    S, st = a.get("summary") or {}, a.get("status") or {}
    now = dt.datetime.now(dt.timezone.utc)
    start = a.get("start")
    days = (now.date() - dt.date.fromisoformat(start)).days if start else None
    print(f"AGENT LINII GOLI – ostatnia zmiana stanu {when(a.get('updated'))} (czas Londyn)"
          + (f", gra od {start} (dzień {days + 1})" if start else ""))

    # wallet and results
    print(f"\nPortfel: {gbp(S.get('equity'))} ({gbp(S.get('profit'), True)} od startu £{a.get('start_balance', 1000):.0f}); "
          f"wolne {gbp(S.get('cash'))}, w grze {gbp(S.get('open'))} (otwarte zakłady: {S.get('n_open', 0)})")
    stats = S.get("stats") or {}
    for k, label in (("all", "Razem"), ("pilka", "Piłka"), ("nba", "NBA")):
        b = stats.get(k) or {}
        if k != "all" and not b.get("bets"):
            continue
        dec = (b.get("won") or 0) + (b.get("lost") or 0)
        print(f"  {label}: rozliczone {b.get('bets', 0)}, trafione {pct(b['won'] / dec, False) if dec else '—'}, "
              f"zysk {gbp(b.get('profit'), True)}, wynik na stawkę {pct(b.get('roi'))}, vs zamknięcie {pct(b.get('clv'))}")

    # bets
    bets = a.get("bets") or []
    open_ = sorted((b for b in bets if b.get("status") == "open"), key=lambda b: b.get("ko") or "")
    if open_:
        print(f"\nOtwarte zakłady ({len(open_)}):")
        for b in open_:
            started = bool(b.get("ko")) and dt.datetime.fromisoformat(b["ko"]) <= now
            print(f"  {when(b.get('ko'))}  {b.get('home')} – {b.get('away')}: {bet_txt(b)}, stawka {gbp(b.get('stake'))}"
                  + ("  [mecz rozegrany, czeka na wynik]" if started else ""))
    done = sorted((b for b in bets if b.get("status") in STATUS), key=lambda b: b.get("settled") or b.get("ko") or "", reverse=True)
    if done:
        print(f"\nOstatnio rozliczone (z {len(done)}):")
        for b in done[:5]:
            print(f"  {when(b.get('ko'))}  {b.get('home')} – {b.get('away')}: {bet_txt(b)} → {STATUS[b['status']]}"
                  f"{', wynik ' + b['score'] if b.get('score') else ''}, {gbp(b.get('profit'), True)}")
    an = S.get("analysed") or {}
    print(f"\nOceny agenta: najbliższe mecze {an.get('upcoming', 0)}, z tego obstawione {an.get('upcoming_bets', 0)}; "
          f"rozliczone oceny (dane do nauki): {an.get('settled', 0)}")

    # tactics, learning, rules, change log
    T = S.get("tactics") or {}
    names = {sp: {t.get("key"): t.get("name") for t in ts} for sp, ts in T.items()}
    for sp in ("pilka", "nba"):
        ts = T.get(sp) or []
        if not ts:
            continue
        act = next((t for t in ts if t.get("active")), {})
        tested = sorted((t for t in ts if t.get("n")), key=lambda t: -(t.get("roi") if t.get("roi") is not None else -9))
        best = ", ".join(f"{t['name']} (typy: {t['n']}, wynik {pct(t.get('roi'))})" for t in tested[:3]) or "jeszcze nic rozliczonego"
        print(f"Taktyki – {SPORT[sp]}: pieniędzmi gra „{act.get('name', '?')}”; na sucho najlepiej: {best}")
    sides = S.get("sides") or {}
    for sp in ("pilka", "nba"):
        x = sides.get(sp) or {}
        if x:
            print(f"Over/Under – {SPORT[sp]}: " + "; ".join(
                f"{n} dni: oceny {x[n]['an'][0]}/{x[n]['an'][1]}, zakłady {x[n]['bets'][0]}/{x[n]['bets'][1]}" for n in ("7", "30") if n in x))
    L = S.get("learning") or {}
    learn = []
    for sp in ("pilka", "nba"):
        x = L.get(sp) or {}
        n, need = x.get("settled", 0), x.get("need", 30)
        learn.append(f"{SPORT[sp]} {'– sam zmienia zasady' if n >= need else f'– rozliczone zakłady {n}/{need} do pierwszych zmian'}")
    print("Nauka: " + ", ".join(learn))
    R = a.get("rules") or {}
    rp, rn = R.get("pilka") or {}, R.get("nba") or {}
    if rp:
        print(f"Zasady piłka: „{names.get('pilka', {}).get(rp.get('tactic'), rp.get('tactic'))}”, przewaga od "
              f"{pct((rp.get('edges') or {}).get(rp.get('tactic')))}, kursy {rp.get('odds_min')}–{rp.get('odds_max')}"
              + (f", wyłączone ligi: {', '.join(rp['off_leagues'])}" if rp.get("off_leagues") else "")
              + (f", wyłączone strony: {', '.join(rp['off_sides'])}" if rp.get("off_sides") else ""))
    if rn:
        print(f"Zasady NBA: „{names.get('nba', {}).get(rn.get('tactic'), rn.get('tactic'))}”, przewaga od "
              f"{pct((rn.get('edges') or {}).get(rn.get('tactic')))}, kursy {rn.get('odds_min')}–{rn.get('odds_max')}, "
              f"zaufanie do własnego modelu {pct(rn.get('w_model'), False)}, gra od {rn.get('min_games')}. meczu drużyny"
              + (f", wyłączone strony: {', '.join(rn['off_sides'])}" if rn.get("off_sides") else ""))
    # skills added 18.10.2026: critic, post-match verdicts, calibration, conclusions
    cr = S.get("critic") or {}
    if cr:
        print("\nKrytyk (blokuje podejrzane zakłady; wynik = co by było, gdyby agent zagrał):")
        for sp in ("pilka", "nba"):
            for r in cr.get(sp) or []:
                if r.get("n") or r.get("open") or not r.get("on"):
                    print(f"  {SPORT[sp]}: {r['name']} – {'blokuje' if r.get('on') else 'WYŁĄCZONA (tylko ostrzega)'}, "
                          f"zablokowane rozliczone {r.get('n', 0)} (wynik {pct(r.get('roi'))}), czeka {r.get('open', 0)}")
        if not any(r.get("n") or r.get("open") for rows in cr.values() for r in rows):
            print("  na razie niczego nie zablokował")
    lk = S.get("luck") or {}
    if lk.get("n"):
        cat_names = {"zasluzona": "zasłużone wygrane", "szczescie": "szczęście", "pech": "pech", "zla_cena": "błąd ceny",
                     "bez_porownania": "bez porównania"}
        cats = ", ".join(f"{cat_names.get(k, k)}: {v}" for k, v in (lk.get("cats") or {}).items())
        print(f"Analiza po meczu: {cats or '—'}; zysk {gbp(lk.get('profit_clv'), True)} przy „uczciwym” wg zamknięcia "
              f"{gbp(lk.get('exp_close'), True)} (na {lk.get('n_clv', 0)} zakładach z kursem zamknięcia)")
    for sp, c in (S.get("calib") or {}).items():
        print(f"Kalibracja {SPORT[sp]}: {c.get('n')} rozliczonych ocen, błąd agenta {c.get('ll_agent')} vs rynek {c.get('ll_market')}"
              f" (mniej = lepiej), agent {'zawyża' if (c.get('bias') or 0) > 0 else 'zaniża'} over o {abs(c.get('bias') or 0) * 100:.0f} pkt proc.")
    for t in S.get("insights") or []:
        print(f"  Wniosek: {t}")
    ch = a.get("changes") or []
    print(f"\nDziennik zmian (wpisy: {len(ch)}), ostatnie:")
    for c in ch[-3:][::-1]:
        print(f"  {when(c.get('at'))} {SPORT.get(c.get('sport'), 'agent')}: {c.get('text')}")

    # data sources
    src = st.get("sources") or {}
    err = lambda d: f" – błędy: {'; '.join(d['errors'])}" if d.get("errors") else ""
    print("\nŹródła danych (ostatnia aktualizacja):")
    fd = src.get("football_data") or {}
    print(f"  football-data.co.uk: {fd.get('leagues', '?')} lig"
          + (f", udanych pobrań {fd['downloads']}" if fd.get("downloads") is not None else "") + err(fd))
    for x in fd.get("stale") or []:
        print(f"    nie pobrało się, użyta starsza kopia: {x}")
    res = st.get("results") or {}
    old_res = [(c, r) for c, r in sorted(res.items()) if r.get("stale")]
    if res:
        newest = max((r["last"] for r in res.values() if r.get("last")), default=None)
        print(f"    wyniki lig agenta: najnowszy {newest or '—'}"
              + ("; STARE (3+ dni, a mecze czekają): " + ", ".join(f"{c} ostatni {r['last']}, czeka {r['waiting']}" + (f", z ESPN {r['espn']}" if r.get("espn") else "") for c, r in old_res)
                 if old_res else "; wszystkie świeże"))
    od = src.get("odds") or {}
    print(f"  The Odds API: zapytania do końca miesiąca: {od.get('remaining', '?')}; ligi agenta z kursami: "
          f"{', '.join(od.get('leagues') or []) or 'brak'}{err(od)}")
    ce = src.get("clubelo") or {}
    n_ce = sum(len(m) for m in (ce.get("matched") or {}).values())
    used = sorted({v for v in (a.get("elo_src") or {}).values() if v})
    print(f"  ClubElo: {f'działa, dopasowane drużyny: {n_ce}' if n_ce else 'nie działa'}{err(ce)}"
          + (f"; siła drużyn liczona z: {', '.join(used)}" if used else ""))
    fp = src.get("fpl") or {}
    print(f"  Fantasy Premier League: zawodnicy z kontuzją lub zawieszeniem: {fp.get('players', 0)}")
    es = src.get("espn") or {}
    print(f"  ESPN (NBA): mecze w bazie {es.get('games', 0)}, kontuzje w raporcie {es.get('injuries', 0)}{err(es)}"
          + (f"; starsze kopie zamiast pobrania: {len(es['stale'])}" if es.get("stale") else ""))
    ep = src.get("espn_pilka")
    if ep is not None:
        print(f"  ESPN (zapasowe wyniki piłki): rozliczone z ESPN w tej aktualizacji {ep.get('used', 0)}{err(ep)}")
    nb = st.get("nba") or {}
    if nb:
        nx = nb.get("next")
        print(f"NBA: mecze w tym sezonie {nb.get('season_games', 0)}"
              + (f", najbliższy {nx['home']} – {nx['away']} {when(nx['ko'])}" if nx else "")
              + f"; mecze w ciągu 48 h: {nb.get('upcoming', 0)}, z kursami: {nb.get('with_odds', 0)}"
              + (f"; błąd prognozy sumy ±{nb['rmse']} pkt" if nb.get("rmse") else ""))

    # readiness and errors
    Rd = S.get("ready") or {}
    dd, bb = Rd.get("days") or [0, 90], Rd.get("bets") or [0, 200]
    print(f"\nGotowość na prawdziwe pieniądze: {'TAK' if Rd.get('ok') else 'jeszcze nie'} – dni {dd[0]}/{dd[1]}, zakłady {bb[0]}/{bb[1]}, "
          f"portfel na plusie: {'tak' if Rd.get('profit') else 'nie'}, kursy lepsze niż zamknięcie: {'tak' if Rd.get('clv') else 'nie'}")
    errs = st.get("errors") or []
    print("Błędy agenta przy ostatniej aktualizacji: " + ("; ".join(errs) if errs else "brak"))
    runs = a.get("runs") or []
    if runs:
        last = runs[-42:]   # about a week
        bad = [r for r in last if r["err"] or not all(v for k, v in r["ok"].items() if k != "elo")]
        fails = sorted({k for r in last for k, v in r["ok"].items() if v is False and k != "elo"})
        print(f"Zdrowie agenta (ostatnie {len(last)} aktualizacji): z problemami {len(bad)}"
              + (f" (źródła: {', '.join(fails)})" if fails else "") + f", z błędem agenta {sum(1 for r in last if r['err'])}")
    wk = (a.get("weekly") or [None])[-1]
    if wk:
        print(f"\nRaport tygodnia {wk['from']} – {wk['to']}:")
        for t in wk["lines"]:
            print("  " + t)
    print("\nCzy automatyczne aktualizacje przechodzą: gh run list -R rzarzycki98-hash/Radek -L 5")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    try:
        sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "agent.json")))
    except BrokenPipeError:  # output cut short (e.g. piped to head): not an error
        sys.stderr.close()
