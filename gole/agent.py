"""Agent Linii Goli: obstawia wirtualnymi pieniędzmi, sam ocenia swoje typy i uczy się, która taktyka działa.

Decyzje Radka (17.10.2026):
  - portfel £1000 wspólny dla piłki i NBA, stawka 1% aktualnego portfela,
  - piłka: gole over/under 2.5 w ligach Top 5 + Holandia, Portugalia, Belgia, Turcja, Szkocja, Grecja,
    kursy William Hill, Grosvenor, Casumo i LeoVegas (tylko oni podają O/U w darmowych danych),
  - NBA: suma punktów over/under, kursy Ladbrokes i BetVictor, a gdy ich nie ma, inny bukmacher z UK,
  - agent analizuje każdy mecz tych lig, a stawia tylko tam, gdzie kurs jest wyższy, niż wynika z szansy,
  - kilka taktyk gra równolegle na sucho; agent stawia pieniądze taktyką, która najlepiej się sprawdza,
  - po 30+ rozliczonych zakładach sam, ostrożnie zmienia swoje zasady (najwyżej jedna zmiana na tydzień),
  - gotowość na prawdziwe pieniądze: 3+ miesiące, 200+ zakładów, zysk i kursy lepsze niż zamknięcie.

Pliki: gole/agent.json (portfel, zakłady, taktyki, zasady, zmiany - czyta je strona),
       gole/agent_analizy.json (ocena każdego meczu, typ każdej taktyki i wynik - do nauki).
"""
import datetime as dt, json, math, os

START_BALANCE = 1000.0
STAKE_PCT = 0.01           # 1% aktualnego portfela
MAX_OPEN_PCT = 0.30        # w otwartych zakładach najwyżej 30% portfela
MAX_ODDS_AGE_H = 12        # starszych kursów agent nie używa
LEARN_MIN = 30             # zmiany zasad dopiero po tylu rozliczonych zakładach
CHANGE_GAP_DAYS = 7        # najwyżej jedna zmiana zasad na tydzień (osobno piłka i NBA)
READY = {"days": 90, "bets": 200}
KEEP_ANALYSES_DAYS = 400

LEAGUES = ["E0", "SP1", "I1", "D1", "F1", "N1", "P1", "B1", "T1", "SC0", "G1"]
FOOT_BOOKS = {"williamhill": "William Hill", "grosvenor": "Grosvenor", "casumo": "Casumo", "leovegas": "LeoVegas"}
NBA_PREF = {"ladbrokes_uk": "Ladbrokes", "betvictor": "BetVictor"}
EXCHANGES = {"betfair_ex_uk", "betfair_ex_eu", "matchbook", "smarkets", "betdaq"}
SIDES = ["Over", "Under"]

# Taktyki: każda typuje na sucho każdy mecz. Pieniądze idą na taktykę aktywną ("tactic" w zasadach).
TACTICS = {
    "pilka": {
        "blend": {"name": "Model + rynek", "desc": "Szansa z modelu goli i strzałów połączona z kursami rynku (waga dobrana osobno dla każdej ligi). Gra, gdy kurs daje przewagę."},
        "market": {"name": "Kurs ponad rynek", "desc": "Bez modelu: gra, gdy jeden bukmacher płaci więcej niż uczciwa cena wszystkich bukmacherów razem."},
        "stats": {"name": "Statystyki potwierdzają", "desc": "Model + rynek z mniejszą przewagą, ale tylko gdy tabela, forma, mecze u siebie/na wyjeździe i H2H wskazują tę samą stronę."},
        "model": {"name": "Sam model", "desc": "Tylko model goli i strzałów celnych, bez patrzenia na rynek. Wymaga dużej przewagi."},
        "big": {"name": "Duża przewaga", "desc": "Model + rynek, ale tylko przy przewadze 6% i więcej. Mniej zakładów, bardziej pewne okazje."},
        "elo": {"name": "Siła drużyn (Elo)", "desc": "Ranking siły klubów ClubElo: przy dużej różnicy sił (150+ pkt) gra Over, przy wyrównanym meczu (do 40 pkt) Under – gdy model + rynek daje choć 1% przewagi."},
        "inj": {"name": "Kontuzje", "desc": "Szansa na gole poprawiona o brakujących zawodników (Premier League, dane Fantasy Premier League): bez kluczowych strzelców mniej goli, bez obrońców i bramkarza więcej."},
        "move": {"name": "Za ruchem rynku", "desc": "Gra stronę, w którą przesunęły się kursy od pierwszego odczytu (o 3+ punkty procentowe), gdy cena wciąż nie jest gorsza od uczciwej."},
    },
    "nba": {
        "blend": {"name": "Model + rynek", "desc": "Prognoza sumy punktów z ataku i obrony drużyn połączona z linią bukmacherów."},
        "model": {"name": "Sam model", "desc": "Tylko prognoza punktów, bez patrzenia na rynek. Wymaga dużej przewagi."},
        "big": {"name": "Duża przewaga", "desc": "Model + rynek, ale tylko przy przewadze 6% i więcej."},
        "b2b": {"name": "Zmęczenie (mecz dzień po dniu)", "desc": "Under, gdy choć jedna drużyna grała dzień wcześniej, a model + rynek daje choć 1% przewagi."},
        "inj": {"name": "Kontuzje gwiazd", "desc": "Prognoza punktów poprawiona o brak najlepszych strzelców (raport kontuzji ESPN): około 3 punkty mniej za każdą gwiazdę."},
        "move": {"name": "Za ruchem linii", "desc": "Gra w kierunku, w którym linia punktów przesunęła się od pierwszego odczytu (o 1.5+ pkt)."},
    },
}
EDGES0 = {"pilka": {"blend": 0.03, "market": 0.02, "stats": 0.02, "model": 0.05, "big": 0.06, "elo": 0.01, "inj": 0.02, "move": 0.0},
          "nba": {"blend": 0.03, "model": 0.05, "big": 0.06, "b2b": 0.01, "inj": 0.02, "move": 0.0}}
ELO_BIG, ELO_CLOSE = 150, 40     # ClubElo gap: a mismatch / an even match
MOVE_MIN = 0.03                  # market moved by 3+ percentage points since the first look
LINE_MOVE_MIN = 1.5              # NBA line moved by 1.5+ points
RULES0 = {
    "pilka": {"tactic": "blend", "edges": EDGES0["pilka"], "odds_min": 1.5, "odds_max": 3.2, "stats_filter": True,
              "off_leagues": [], "off_sides": []},
    "nba": {"tactic": "blend", "edges": EDGES0["nba"], "odds_min": 1.6, "odds_max": 2.4, "w_model": 0.3, "min_games": 5,
            "off_sides": []},
}
EDGE_LIMITS = (0.01, 0.10)
ODDS_MAX_LIMITS = {"pilka": (2.2, 3.2), "nba": (2.0, 2.4)}
SWITCH_MIN = {"pilka": 50, "nba": 80}   # tactic needs this many settled paper picks before the agent switches to it


# ---------------------------------------------------------------- helpers

def r2(x):
    return None if x is None else round(x, 2)


def r4(x):
    return None if x is None else round(x, 4)


def demargin(odds):
    if not odds or any(not o for o in odds):
        return None
    inv = [1 / o for o in odds]
    s = sum(inv)
    return [x / s for x in inv]


def pool(pm, pk, w):
    """Log-linear pooling of model and market probabilities (w = model weight)."""
    v = [max(a, 1e-9) ** w * max(b, 1e-9) ** (1 - w) for a, b in zip(pm, pk)]
    s = sum(v)
    return [x / s for x in v]


def pctf(x, sign=False):
    if x is None:
        return "—"
    return f"{x * 100:+.1f}%" if sign else f"{x * 100:.0f}%"


def oddf(o):
    return f"{o:.2f}"


def numf(x):
    return str(x)


def stats_of(rows):
    """rows: dicts with 'u' (profit per £1 staked) and optional 'clv'."""
    n = len(rows)
    clv = [r["clv"] for r in rows if r.get("clv") is not None]
    return {"n": n, "roi": sum(r["u"] for r in rows) / n if n else None,
            "won": sum(1 for r in rows if r["u"] > 0), "clv": sum(clv) / len(clv) if clv else None, "nclv": len(clv)}


def pub(s):
    return {"n": s["n"], "won": s["won"], "roi": r4(s["roi"]), "clv": r4(s["clv"])}


def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def p_over25(lh, la):
    m = lh + la
    return 1 - math.exp(-m) * (1 + m + m * m / 2)


def injury_effect(f):
    """Premier League: expected goals corrected for missing players (Fantasy Premier League data).
    Missing attackers take away 40% of their share of the team's goals and assists (someone replaces them),
    missing key defenders or the goalkeeper give the opponent a few percent more."""
    a = f.get("absences")
    if not a or not f.get("xg"):
        return None

    def miss(r):
        if r.get("ch") is not None:
            return max(0.0, 1 - r["ch"] / 100)
        return 1.0 if r.get("st") in ("i", "s", "n") else 0.5

    def side(rows):
        att = min(0.6, sum((r.get("xgi") or 0) * miss(r) for r in rows))
        dfn = min(0.2, sum((0.06 if r.get("pos") == "BR" else 0.03) * miss(r) for r in rows if r.get("key") and r.get("pos") in ("BR", "OBR")))
        names = [[r["n"], r.get("pos"), round(miss(r), 2), r.get("xgi")] for r in rows if r.get("key") and miss(r) >= 0.5]
        return att, dfn, names

    ah, dh, nh = side(a.get("home") or [])
    aa, da, na = side(a.get("away") or [])
    lh, la = f["xg"]
    lh2, la2 = lh * (1 - 0.4 * ah) * (1 + da), la * (1 - 0.4 * aa) * (1 + dh)
    d = p_over25(lh2, la2) - p_over25(lh, la)
    return {"d": round(d, 4), "h": nh, "a": na, "xg": [round(lh2, 2), round(la2, 2)]}


def odds_bucket(o):
    return "do 1.80" if o < 1.8 else "1.80–2.19" if o < 2.2 else "2.20–2.79" if o < 2.8 else "2.80 i więcej"


def edge_bucket(e):
    return "do 3%" if e < 0.03 else "3–6%" if e < 0.06 else "6–10%" if e < 0.10 else "10% i więcej"


# ---------------------------------------------------------------- the agent

class Agent:
    def __init__(self, outdir, now):
        self.outdir, self.now = outdir, now
        self.path = os.path.join(outdir, "agent.json")
        self.apath = os.path.join(outdir, "agent_analizy.json")
        s = load_json(self.path, None)
        if not s or s.get("v") != 1:
            s = {"v": 1, "start": now.date().isoformat(), "start_balance": START_BALANCE, "cash": START_BALANCE,
                 "bets": [], "rules": json.loads(json.dumps(RULES0)), "changes": [], "history": [], "last_change": {}}
            s["changes"].append({"at": now.isoformat(timespec="minutes"), "sport": "all",
                                 "text": "Start agenta: portfel £1000, stawka 1% portfela, taktyka „Model + rynek”.",
                                 "why": "Piłka: over/under 2.5 w 11 dużych ligach Europy, kursy William Hill, Grosvenor, Casumo, LeoVegas. "
                                        "NBA: suma punktów, kursy Ladbrokes i BetVictor (gdy ich brak: inny bukmacher z UK). "
                                        "Wszystkie taktyki typują na sucho każdy mecz; po 30 rozliczonych zakładach agent sam zmienia zasady i taktykę."})
        for sp, r0 in RULES0.items():  # rule keys added in later versions
            R = s["rules"].setdefault(sp, {})
            for k, v in r0.items():
                R.setdefault(k, json.loads(json.dumps(v)))
            for t, e in EDGES0[sp].items():
                R["edges"].setdefault(t, e)
        self.s = s
        self.A = load_json(self.apath, {}).get("rows", {}) if os.path.exists(self.apath) else {}
        self.cands = []
        self.errors = []
        self.elo = None   # zrodla.ClubElo, set by the engine
        self.by_id = {b["id"]: b for b in s["bets"]}

    # ------------------------------------------------ money
    def open_stakes(self):
        return round(sum(b["stake"] for b in self.s["bets"] if b["status"] == "open"), 2)

    def equity(self):
        return round(self.s["cash"] + self.open_stakes(), 2)

    def settle(self, b, outcome, extra):
        """outcome: won / lost / push / void."""
        payout = b["stake"] * b["odds"] if outcome == "won" else (b["stake"] if outcome in ("push", "void") else 0.0)
        self.s["cash"] = round(self.s["cash"] + payout, 2)
        b.update(extra)
        b.update({"status": outcome, "payout": r2(payout), "profit": r2(payout - b["stake"]),
                  "settled": self.now.isoformat(timespec="minutes")})

    # ------------------------------------------------ football
    def football(self, code, league_name, priced, results, teams=None):
        rules = self.s["rules"]["pilka"]
        elo = {}
        if self.elo is not None:
            try:
                names = set(teams or []) | {f["home"] for f in priced} | {f["away"] for f in priced}
                elo = self.elo.match(code, sorted(names))
            except Exception as e:
                self.errors.append(f"ClubElo {code}: {str(e)[:80]}")
        for f in priced:
            if dt.datetime.fromisoformat(f["ko"]) <= self.now:
                continue
            b = self.by_id.get(f"pilka|{f['id']}|ou")
            if b and b["status"] == "open":  # follow the price until kick-off (closing price at the same bookmaker)
                row = (f.get("prices") or {}).get("ou", {}).get(b["book_key"])
                if row:
                    b["last_odds"] = row[1][SIDES.index(b["side"])]
            an = self.analyze_football(f, code, league_name, rules, elo)
            old = self.A.get(an["id"])
            if old and old.get("fresh") and not an["fresh"] and not old.get("res"):
                an = old  # prices went stale: the last view with fresh prices stays the agent's judgement of this match
            if b:  # already placed: keep the reason it was placed for
                an["dec"], an["why"], an["stake"] = "bet", b["why"], b["stake"]
            self.A[an["id"]] = an
            if an["dec"] == "cand" and not b:
                self.cands.append((an["best"]["edge"], an))
        self.settle_football(code, results)

    def analyze_football(self, f, code, league_name, rules, elo=None):
        pm = f["over"]["2.5"]
        pk = f["fair"]["ou"][0] if (f.get("fair") or {}).get("ou") else None
        p = f["final"]["ou"][0] if (f.get("final") or {}).get("ou") else None
        st = (f.get("stats") or {}).get("ou") or {}
        an = {"id": f"pilka|{f['id']}", "sp": "pilka", "lg": code, "lgn": league_name, "date": f["date"], "ko": f["ko"],
              "home": f["home"], "away": f["away"], "line": 2.5, "pm": r4(pm), "pk": r4(pk), "p": r4(p), "xg": f.get("xg"),
              "st": [st.get("side"), st.get("level"), st.get("agree"), st.get("against")] if st else None,
              "at": self.now.isoformat(timespec="minutes")}
        # extra data: team strength (ClubElo), injuries (Premier League), how the market moved since the first look
        elo = elo or {}
        eh, ea = (elo.get(f["home"]) or (None, None))[1], (elo.get(f["away"]) or (None, None))[1]
        an["elo"] = [round(eh), round(ea)] if eh and ea else None
        inj = injury_effect(f)
        an["inj"] = inj
        old = self.A.get(an["id"])
        pk0 = old["pk0"] if old and old.get("pk0") is not None else pk
        mv = pk - pk0 if pk is not None and pk0 is not None else None
        an["pk0"], an["mv"] = r4(pk0), r4(mv)
        prices = {k: v for k, v in ((f.get("prices") or {}).get("ou") or {}).items() if k in FOOT_BOOKS}
        age = (self.now - dt.datetime.fromisoformat(f["odds_at"])).total_seconds() / 3600 if f.get("odds_at") else None
        an["odds_age_h"] = r2(age)
        fresh = bool(prices) and age is not None and age <= MAX_ODDS_AGE_H
        an["fresh"] = fresh

        def pick(q, side=None):
            best = None
            if q is None:
                return None
            for k, (title, odds) in prices.items():
                for i in (0, 1):
                    if odds[i] and (side is None or side == i):
                        e = q[i] * odds[i] - 1
                        if best is None or e > best["edge"]:
                            best = {"side": SIDES[i], "odds": odds[i], "book": FOOT_BOOKS[k], "bk": k, "edge": r4(e), "q": r4(q[i])}
            return best

        qs = {"blend": [p, 1 - p] if p is not None else None, "market": [pk, 1 - pk] if pk is not None else None,
              "model": [pm, 1 - pm]}
        qs["stats"] = qs["big"] = qs["blend"]
        p_inj = min(0.98, max(0.02, p + inj["d"])) if inj and p is not None and abs(inj["d"]) >= 0.01 else None
        qs["inj"] = [p_inj, 1 - p_inj] if p_inj is not None else None
        an["p_inj"] = r4(p_inj)
        stats_side = SIDES[st["side"]] if st and st.get("side") is not None else None
        elo_side = None
        if an["elo"]:
            dif = abs(eh - ea)
            elo_side = 0 if dif >= ELO_BIG else 1 if dif <= ELO_CLOSE else None
        move_side = (0 if mv > 0 else 1) if mv is not None and abs(mv) >= MOVE_MIN else None
        tpick = {}
        for t in TACTICS["pilka"]:
            if t == "elo":
                tpick[t] = pick(qs["blend"], elo_side) if elo_side is not None else None
            elif t == "move":
                tpick[t] = pick(qs["blend"], move_side) if move_side is not None else None
            else:
                tpick[t] = pick(qs.get(t))

        def ok(t, b):
            if not b or not fresh or b["edge"] < rules["edges"][t] or not rules["odds_min"] <= b["odds"] <= rules["odds_max"]:
                return False
            if t == "stats" and not (st and (st.get("level") or 0) >= 1 and stats_side == b["side"]):
                return False
            return True

        an["tx"] = {t: [SIDES.index(b["side"]), b["odds"], b["bk"], b["edge"]] if ok(t, b) else None for t, b in tpick.items()}
        act = rules["tactic"]
        best = tpick.get(act)
        an["best"], an["tactic"] = best, act
        against = bool(best and stats_side and st.get("level") == 2 and stats_side != best["side"])
        tname = TACTICS["pilka"][act]["name"]
        dec, why = "skip", None
        if code in rules["off_leagues"]:
            why = "Liga wyłączona przez agenta (tu przegrywał z rynkiem)."
        elif not prices:
            why = "Brak kursu over/under 2.5 u William Hill, Grosvenor, Casumo i LeoVegas."
        elif qs["blend"] is None and act != "model":
            why = "Za mało bukmacherów, żeby ustalić uczciwą cenę rynku – bez tego agent nie ryzykuje."
        elif not fresh:
            why = f"Kursy sprzed {age:.0f} godz. – za stare na zakład." if age else "Nieznany wiek kursów."
        elif best is None:
            why = {"elo": (f"Taktyka „{tname}” gra tylko przy dużej różnicy sił (150+ pkt Elo) albo wyrównanym meczu (do 40 pkt); "
                           f"tu różnica {abs(eh - ea):.0f} pkt.") if an["elo"] else f"Brak rankingu ClubElo dla tych drużyn – taktyka „{tname}” nie typuje.",
                   "inj": f"Brak ważnych braków kadrowych – taktyka „{tname}” nie typuje (dane o kontuzjach są tylko dla Premier League).",
                   "move": f"Kursy prawie się nie ruszyły od pierwszego odczytu – taktyka „{tname}” nie typuje."}.get(act, "Za mało danych.")
        elif best["edge"] < rules["edges"][act]:
            why = (f"Brak przewagi: najlepiej {best['side']} 2.5 po {oddf(best['odds'])} u {best['book']} "
                   f"({pctf(best['edge'], True)}, taktyka „{tname}” wymaga {pctf(rules['edges'][act], True)}).")
        elif not rules["odds_min"] <= best["odds"] <= rules["odds_max"]:
            why = f"Kurs {oddf(best['odds'])} poza zakresem agenta {oddf(rules['odds_min'])}–{oddf(rules['odds_max'])}."
        elif best["side"] in rules["off_sides"]:
            why = f"Agent nie gra teraz na {best['side']} (tu przegrywał)."
        elif act == "stats" and not an["tx"]["stats"]:
            why = f"Przewaga na {best['side']}, ale statystyki jej nie potwierdzają."
        elif rules["stats_filter"] and against:
            why = f"Przewaga na {best['side']}, ale statystyki mocno wskazują {stats_side} – agent odpuszcza."
            an["stats_block"] = True
        else:
            dec = "cand"
            why = self.football_reason(an, best, f, st, act)
            if against:
                an["stats_against"] = True
        an["dec"], an["why"] = dec, why
        return an

    @staticmethod
    def football_reason(an, best, f, st, act):
        i = SIDES.index(best["side"])
        pm = an["pm"] if i == 0 else 1 - an["pm"]
        parts = [f"{best['side']} 2.5 po {oddf(best['odds'])} u {best['book']}: agent daje {pctf(best['q'])}, kurs zakłada "
                 f"{pctf(1 / best['odds'])} → przewaga {pctf(best['edge'], True)} (taktyka „{TACTICS['pilka'][act]['name']}”)."]
        mk = f"Model goli i strzałów: {pctf(pm)}"
        if an["pk"] is not None:
            mk += f", rynek bez marży: {pctf(an['pk'] if i == 0 else 1 - an['pk'])}"
        parts.append(mk + ".")
        if f.get("xg"):
            parts.append(f"Oczekiwane gole {numf(f['xg'][0])} – {numf(f['xg'][1])}.")
        if st and st.get("n"):
            same = SIDES[st["side"]] == best["side"]
            pro, con = (st.get("agree", 0), st.get("against", 0)) if same else (st.get("against", 0), st.get("agree", 0))
            parts.append(f"Statystyki (tabela, forma, u siebie/na wyjeździe, H2H): {pro} za {best['side']}, {con} przeciw"
                         + (" – agent idzie tu pod prąd statystyk, bo kurs daje przewagę; po meczu sprawdzi, czy słusznie." if con > pro else "."))
        if an.get("elo"):
            parts.append(f"Siła drużyn (ClubElo): {an['elo'][0]} i {an['elo'][1]}.")
        inj = an.get("inj")
        if inj and (inj["h"] or inj["a"]):
            who = [n[0] for n in inj["h"] + inj["a"]][:4]
            parts.append(f"Braki kluczowych: {', '.join(who)} – szansa na over po ich uwzględnieniu {pctf(an.get('p_inj') or ((an['p'] or 0) + inj['d']))}.")
        if an.get("mv") is not None and abs(an["mv"]) >= 0.01:
            parts.append(f"Rynek od pierwszego odczytu: over {pctf(an['pk0'])} → {pctf(an['pk'])}.")
        return " ".join(parts)

    def settle_football(self, code, results):
        today = self.now.date()

        def find(date, home, away):
            d0 = dt.date.fromisoformat(date)
            for m in results:
                if m["h"] == home and m["a"] == away and m["hg"] is not None and abs((m["d"] - d0).days) <= 2:
                    return m
            return None

        for b in self.s["bets"]:
            if b["sp"] != "pilka" or b["lg"] != code or b["status"] != "open":
                continue
            m = find(b["date"], b["home"], b["away"])
            if not m:
                if dt.date.fromisoformat(b["date"]) < today - dt.timedelta(days=21):
                    self.settle(b, "void", {"note": "Brak wyniku po 21 dniach – zwrot stawki."})
                continue
            i = SIDES.index(b["side"])
            won = (m["hg"] + m["ag"] > 2.5) == (i == 0)
            extra = {"score": f"{m['hg']}:{m['ag']}"}
            fair = demargin(m["ouc"].get("P") or m["ouc"].get("Avg"))
            if fair:
                extra["clv"] = r4(b["odds"] * fair[i] - 1)
                extra["clv_src"] = "Pinnacle" if m["ouc"].get("P") else "średnia rynku"
            if b.get("last_odds"):
                extra["close_odds"] = b["last_odds"]
            self.settle(b, "won" if won else "lost", extra)
        for a in self.A.values():
            if a["sp"] != "pilka" or a["lg"] != code or "res" in a:
                continue
            m = find(a["date"], a["home"], a["away"])
            if not m:
                continue
            over = m["hg"] + m["ag"] > 2.5
            a["res"] = [m["hg"], m["ag"]]
            fair = demargin(m["ouc"].get("P") or m["ouc"].get("Avg"))
            if fair:
                a["close"] = r4(fair[0])

            def outcome(i, odds):
                won = over == (i == 0)
                return [r4(odds - 1 if won else -1.0), r4(odds * fair[i] - 1) if fair else None]

            if a.get("best"):
                a["cf"] = dict(zip(("u", "clv"), outcome(SIDES.index(a["best"]["side"]), a["best"]["odds"])))
            a["txr"] = {t: outcome(v[0], v[1]) if v else None for t, v in (a.get("tx") or {}).items()}

    # ------------------------------------------------ NBA
    def nba(self, ctx):
        """ctx from nba.prepare(): upcoming games with model numbers, all games, odds events."""
        rules = self.s["rules"]["nba"]
        done = {g["id"]: g for g in ctx["games"] if g["done"]}
        for g in ctx["upcoming"]:
            if dt.datetime.fromisoformat(g["ko"]) <= self.now:
                continue
            b = self.by_id.get(f"nba|{g['id']}|tot")
            ev = g.get("odds")
            if b and b["status"] == "open" and ev:
                bk = ev["books"].get(b["book_key"])
                if bk and bk.get("tot") and abs(bk["tot"][0] - b["line"]) < 1e-9:
                    b["last_odds"] = bk["tot"][1 if b["side"] == "Over" else 2]
                    b["last_line"] = bk["tot"][0]
            an = self.analyze_nba(g, rules, ctx)
            old = self.A.get(an["id"])
            if old and old.get("fresh") and not an["fresh"] and not old.get("res"):
                an = old
            if b:
                an["dec"], an["why"], an["stake"] = "bet", b["why"], b["stake"]
            self.A[an["id"]] = an
            if an["dec"] == "cand" and not b:
                self.cands.append((an["best"]["edge"], an))
        today = self.now.date()
        for b in self.s["bets"]:
            if b["sp"] != "nba" or b["status"] != "open":
                continue
            g = done.get(b["eid"])
            if not g:
                if dt.date.fromisoformat(b["date"]) < today - dt.timedelta(days=10):
                    self.settle(b, "void", {"note": "Mecz nie rozegrany – zwrot stawki."})
                continue
            total = g["hs"] + g["as"]
            extra = {"score": f"{g['hs']}:{g['as']}", "total": total}
            if b.get("last_odds") and b.get("last_line") == b["line"]:
                extra["clv"] = r4(b["odds"] / b["last_odds"] - 1)
                extra["clv_src"] = "ostatni kurs u bukmachera"
                extra["close_odds"] = b["last_odds"]
            if abs(total - b["line"]) < 1e-9:
                self.settle(b, "push", extra)
            else:
                self.settle(b, "won" if (total > b["line"]) == (b["side"] == "Over") else "lost", extra)
        for a in self.A.values():
            if a["sp"] != "nba" or "res" in a:
                continue
            g = done.get(a.get("eid"))
            if not g:
                continue
            total = g["hs"] + g["as"]
            a["res"] = [g["hs"], g["as"]]

            def outcome(i, odds, line):
                if abs(total - line) < 1e-9:
                    return [0.0, None]
                return [r4(odds - 1 if (total > line) == (i == 0) else -1.0), None]

            if a.get("best"):
                a["cf"] = dict(zip(("u", "clv"), outcome(SIDES.index(a["best"]["side"]), a["best"]["odds"], a["best"]["line"])))
            a["txr"] = {t: outcome(v[0], v[1], v[4]) if v else None for t, v in (a.get("tx") or {}).items()}

    def analyze_nba(self, g, rules, ctx):
        import nba as N
        an = {"id": f"nba|{g['id']}", "eid": g["id"], "sp": "nba", "lg": "NBA", "lgn": "NBA", "date": g["day"], "ko": g["ko"],
              "home": g["hn"], "away": g["an"], "mu": r2(g.get("mu")), "sd": r2(g.get("sd")), "gp": [g.get("gp_h"), g.get("gp_a")],
              "b2b": [g.get("b2b_h", False), g.get("b2b_a", False)], "inj": g.get("inj"), "mu_inj": r2(g.get("mu_inj")),
              "at": self.now.isoformat(timespec="minutes")}
        ev = g.get("odds")
        books, tot = {}, {}
        if ev:
            tot = {k: b for k, b in ev["books"].items() if b.get("tot") and k not in EXCHANGES}
            pref = {k: b for k, b in tot.items() if k in NBA_PREF}
            books = pref or tot
        lines = sorted(b["tot"][0] for b in tot.values())
        lmed = (lines[len(lines) // 2] if len(lines) % 2 else (lines[len(lines) // 2 - 1] + lines[len(lines) // 2]) / 2) if lines else None
        old = self.A.get(an["id"])
        line0 = old["line0"] if old and old.get("line0") is not None else lmed
        lmv = lmed - line0 if lmed is not None and line0 is not None else None
        an["lmed"], an["line0"] = lmed, line0
        age = (self.now - dt.datetime.fromisoformat(ctx["odds_at"])).total_seconds() / 3600 if ev and ctx.get("odds_at") else None
        an["odds_age_h"] = r2(age)
        fresh = bool(books) and age is not None and age <= MAX_ODDS_AGE_H
        an["fresh"] = fresh

        def price(mu, side=None, model_only=False):
            best = None
            if mu is None:
                return None
            for k, bk in books.items():
                L, o, u = bk["tot"]
                p_over, p_under, p_push = N.prob_total(mu, g["sd"], L)
                pm = p_over / max(p_over + p_under, 1e-9)
                q = demargin([o, u])
                pr = [pm, 1 - pm] if model_only else pool([pm, 1 - pm], q, rules["w_model"])
                for i, odds in enumerate((o, u)):
                    if side is not None and side != i:
                        continue
                    e = pr[i] * (1 - p_push) * odds + p_push - 1
                    if best is None or e > best["edge"]:
                        best = {"side": SIDES[i], "line": L, "odds": odds, "book": bk.get("t") or k, "bk": k, "edge": r4(e),
                                "q": r4(pr[i]), "pm": r4(pm if i == 0 else 1 - pm), "pk": r4(q[i]), "pref": k in NBA_PREF}
            return best

        mu = g.get("mu")
        tired = bool(g.get("b2b_h") or g.get("b2b_a"))
        hurt = bool(g.get("inj") and g["inj"].get("adj"))
        picks = {"blend": price(mu), "model": price(mu, model_only=True), "big": price(mu),
                 "b2b": price(mu, side=1) if tired else None,
                 "inj": price(g.get("mu_inj")) if hurt else None,
                 "move": price(mu, side=0 if lmv > 0 else 1) if lmv is not None and abs(lmv) >= LINE_MOVE_MIN else None}
        gp_ok = min(g.get("gp_h") or 0, g.get("gp_a") or 0) >= rules["min_games"]

        def ok(t, b):
            return bool(b and fresh and gp_ok and b["edge"] >= rules["edges"][t] and rules["odds_min"] <= b["odds"] <= rules["odds_max"])

        an["tx"] = {t: [SIDES.index(b["side"]), b["odds"], b["bk"], b["edge"], b["line"]] if ok(t, b) else None for t, b in picks.items()}
        act = rules["tactic"]
        best = picks.get(act)
        an["best"], an["tactic"] = best, act
        if best:
            o = best["side"] == "Over"
            an["line"] = best["line"]
            an["pm"] = r4(best["pm"] if o else 1 - best["pm"])
            an["pk"] = r4(best["pk"] if o else 1 - best["pk"])
            an["p"] = r4(best["q"] if o else 1 - best["q"])
        tname = TACTICS["nba"][act]["name"]
        dec, why = "skip", None
        if not ev:
            why = "Brak kursów na sumę punktów dla tego meczu (jeszcze nie pobrane albo brak w ofercie)."
        elif not books:
            why = "Żaden bukmacher z UK nie podaje sumy punktów dla tego meczu."
        elif mu is None:
            why = "Model nie ma jeszcze danych o tych drużynach."
        elif not gp_ok:
            why = (f"Za mało meczów w tym sezonie ({g.get('gp_h') or 0} i {g.get('gp_a') or 0}, potrzeba {rules['min_games']}) – "
                   f"agent czeka, aż forma drużyn się ustali.")
        elif not fresh:
            why = f"Kursy sprzed {age:.0f} godz. – za stare na zakład." if age else "Nieznany wiek kursów."
        elif not best:
            why = {"b2b": f"Żadna drużyna nie grała dzień wcześniej – taktyka „{tname}” tu nie gra.",
                   "inj": f"Gwiazdy obu drużyn grają – taktyka „{tname}” tu nie gra.",
                   "move": f"Linia prawie się nie ruszyła od pierwszego odczytu – taktyka „{tname}” tu nie gra."}.get(act, "Brak przewagi.")
        elif best["edge"] < rules["edges"][act]:
            why = (f"Brak przewagi: najlepiej {best['side']} {numf(best['line'])} po {oddf(best['odds'])} u {best['book']} "
                   f"({pctf(best['edge'], True)}, taktyka „{tname}” wymaga {pctf(rules['edges'][act], True)}).")
        elif not rules["odds_min"] <= best["odds"] <= rules["odds_max"]:
            why = f"Kurs {oddf(best['odds'])} poza zakresem agenta {oddf(rules['odds_min'])}–{oddf(rules['odds_max'])}."
        elif best["side"] in rules["off_sides"]:
            why = f"Agent nie gra teraz na {best['side']} (tu przegrywał)."
        else:
            dec = "cand"
            parts = [f"{best['side']} {numf(best['line'])} pkt po {oddf(best['odds'])} u {best['book']}"
                     f"{'' if best['pref'] else ' (Ladbrokes i BetVictor nie mają tej linii)'}: agent daje {pctf(best['q'])}, "
                     f"kurs zakłada {pctf(1 / best['odds'])} → przewaga {pctf(best['edge'], True)} (taktyka „{tname}”).",
                     f"Prognoza sumy {numf(round(mu, 1))} pkt (± {g['sd']:.0f}) z formy ataku i obrony obu drużyn, "
                     f"model {pctf(best['pm'])}, rynek {pctf(best['pk'])}."]
            if tired:
                parts.append("Zmęczenie: " + " i ".join(n for n, t in ((g["hn"], g.get("b2b_h")), (g["an"], g.get("b2b_a"))) if t) + " grali wczoraj.")
            if hurt:
                who = [f"{r[0]} ({r[1]})" for r in g["inj"]["h"] + g["inj"]["a"]]
                parts.append(f"Kontuzje gwiazd: {', '.join(who)} → prognoza {numf(g['inj']['adj'])} pkt.")
            if lmv:
                parts.append(f"Linia od pierwszego odczytu: {numf(line0)} → {numf(lmed)}.")
            why = " ".join(parts)
        an["dec"], an["why"] = dec, why
        return an

    # ------------------------------------------------ placing the bets
    def place(self):
        self.cands.sort(key=lambda c: -c[0])
        for edge, an in self.cands:
            eq = self.equity()
            stake = round(eq * STAKE_PCT, 2)
            if stake < 0.5:
                an["dec"], an["why"] = "skip", "Portfel za mały na zakład."
                continue
            if self.open_stakes() + stake > MAX_OPEN_PCT * eq + 1e-9:
                an["dec"] = "skip"
                an["why"] = f"Limit bezpieczeństwa: w otwartych zakładach jest już {pctf(self.open_stakes() / eq)} portfela (max 30%). " + an["why"]
                continue
            best, sp = an["best"], an["sp"]
            bid = f"{an['id']}|{'ou' if sp == 'pilka' else 'tot'}"
            b = {"id": bid, "sp": sp, "lg": an["lg"], "lgn": an["lgn"], "date": an["date"], "ko": an["ko"],
                 "home": an["home"], "away": an["away"], "side": best["side"], "line": best.get("line", 2.5),
                 "odds": best["odds"], "book": best["book"], "book_key": best["bk"], "prob": best["q"], "edge": best["edge"],
                 "tactic": an["tactic"], "stake": stake, "placed": self.now.isoformat(timespec="minutes"),
                 "odds_age_h": an.get("odds_age_h"), "status": "open", "why": an["why"]}
            if sp == "nba":
                b["eid"] = an["eid"]
                b["mu"] = an.get("mu")
            if an.get("stats_against"):
                b["stats_against"] = True
            self.s["cash"] = round(self.s["cash"] - stake, 2)
            self.s["bets"].append(b)
            self.by_id[bid] = b
            an["dec"], an["stake"] = "bet", stake

    # ------------------------------------------------ learning: the agent adjusts its own rules
    def bet_rows(self, sp):
        return [{"u": b["profit"] / b["stake"], "clv": b.get("clv"), "b": b} for b in self.s["bets"]
                if b["sp"] == sp and b["status"] in ("won", "lost", "push")]

    def paper_rows(self, sp, tactic=None):
        """Settled picks: tactic=None -> the active tactic's best price on every analysed match (also below the bar)."""
        out = []
        for a in self.A.values():
            if a["sp"] != sp or "res" not in a:
                continue
            if tactic is None:
                if a.get("cf") and a.get("best"):
                    out.append({"u": a["cf"]["u"], "clv": a["cf"].get("clv"), "a": a})
            else:
                r = (a.get("txr") or {}).get(tactic)
                if r:
                    out.append({"u": r[0], "clv": r[1], "a": a, "t": a["tx"][tactic]})
        return out

    def tactic_stats(self, sp):
        return {t: stats_of(self.paper_rows(sp, t)) for t in TACTICS[sp]}

    def change(self, sp, text, why):
        self.s["changes"].append({"at": self.now.isoformat(timespec="minutes"), "sport": sp, "text": text, "why": why})
        self.s["last_change"][sp] = self.now.date().isoformat()

    def adapt(self):
        for sp in ("pilka", "nba"):
            bets = self.bet_rows(sp)
            if len(bets) < LEARN_MIN:
                continue
            last = self.s["last_change"].get(sp)
            if last and (self.now.date() - dt.date.fromisoformat(last)).days < CHANGE_GAP_DAYS:
                continue
            for step in (self.step_tactic, self.step_league_off, self.step_league_on, self.step_side, self.step_edge_up,
                         self.step_edge_down, self.step_odds_max, self.step_stats, self.step_weight):
                if step(sp, bets):
                    break

    @staticmethod
    def bad(s, n_min, roi_max):
        """Clearly losing: enough bets, losing money and not beating the closing price."""
        return s["n"] >= n_min and s["roi"] is not None and s["roi"] < roi_max and (s["clv"] is None or s["clv"] < 0)

    def step_tactic(self, sp, bets):
        """Move the money to the tactic that proved best on paper."""
        R = self.s["rules"][sp]
        act = R["tactic"]
        T = self.tactic_stats(sp)
        a = T[act]
        a_roi = a["roi"] if a["n"] >= 30 else 0.0
        good = [(t, s) for t, s in T.items() if t != act and s["n"] >= SWITCH_MIN[sp] and s["roi"] > 0
                and (s["clv"] is None or s["clv"] > 0) and s["roi"] >= a_roi + 0.03]
        if not good:
            return False
        t, s = max(good, key=lambda c: c[1]["roi"])
        R["tactic"] = t
        names = TACTICS[sp]
        self.change(sp, f"Zmieniam taktykę z „{names[act]['name']}” na „{names[t]['name']}”.",
                    f"„{names[t]['name']}”: {s['n']} typów na sucho, wynik {pctf(s['roi'], True)}"
                    + (f", kurs vs zamknięcie {pctf(s['clv'], True)}" if s["clv"] is not None else "")
                    + f". „{names[act]['name']}”: {a['n']} typów, wynik {pctf(a['roi'], True)}.")
        return True

    def step_league_off(self, sp, bets):
        if sp != "pilka":
            return False
        R = self.s["rules"][sp]
        for lg in sorted({r["b"]["lg"] for r in bets}):
            if lg in R["off_leagues"]:
                continue
            s = stats_of([r for r in bets if r["b"]["lg"] == lg])
            if self.bad(s, 15, -0.10):
                R["off_leagues"].append(lg)
                R.setdefault("off_since", {})[lg] = self.now.date().isoformat()
                name = next(r["b"]["lgn"] for r in bets if r["b"]["lg"] == lg)
                self.change(sp, f"Wyłączam ligę {name}.",
                            f"{s['n']} zakładów, wynik {pctf(s['roi'], True)}, kurs vs zamknięcie {pctf(s['clv'], True)} – tu rynek jest lepszy od agenta. "
                            f"Dalej ocenia jej mecze na sucho i włączy ją, gdy typy zaczną wygrywać.")
                return True
        return False

    def step_league_on(self, sp, bets):
        if sp != "pilka":
            return False
        R = self.s["rules"][sp]
        act = R["tactic"]
        for lg in list(R["off_leagues"]):
            since = R.get("off_since", {}).get(lg, "")
            rows = [r for r in self.paper_rows(sp, act) if r["a"]["lg"] == lg and r["a"]["date"] > since]
            s = stats_of(rows)
            if s["n"] >= 20 and s["roi"] > 0 and (s["clv"] is None or s["clv"] > 0):
                R["off_leagues"].remove(lg)
                R.get("off_since", {}).pop(lg, None)
                name = next((r["a"]["lgn"] for r in rows), lg)
                self.change(sp, f"Włączam z powrotem ligę {name}.",
                            f"Od wyłączenia {s['n']} typów na sucho: wynik {pctf(s['roi'], True)}"
                            + (f", kurs vs zamknięcie {pctf(s['clv'], True)}." if s["clv"] is not None else "."))
                return True
        return False

    def step_side(self, sp, bets):
        R = self.s["rules"][sp]
        if R["off_sides"]:
            return False
        for side in SIDES:
            s = stats_of([r for r in bets if r["b"]["side"] == side])
            if self.bad(s, 20, -0.15):
                R["off_sides"].append(side)
                self.change(sp, f"Przestaję grać {side}.", f"{s['n']} zakładów na {side}: wynik {pctf(s['roi'], True)}"
                            + (f", kurs vs zamknięcie {pctf(s['clv'], True)}." if s["clv"] is not None else "."))
                return True
        return False

    def step_edge_up(self, sp, bets):
        R = self.s["rules"][sp]
        act = R["tactic"]
        s = stats_of([r for r in bets if r["b"].get("tactic", "blend") == act][-50:])
        if s["n"] >= LEARN_MIN and R["edges"][act] < EDGE_LIMITS[1] - 1e-9 and s["roi"] < 0 and (s["clv"] is None or s["clv"] < 0):
            old = R["edges"][act]
            R["edges"][act] = round(min(EDGE_LIMITS[1], old + 0.01), 3)
            self.change(sp, f"Podnoszę wymaganą przewagę z {pctf(old, True)} do {pctf(R['edges'][act], True)}.",
                        f"Ostatnie {s['n']} zakładów: wynik {pctf(s['roi'], True)}"
                        + (f", kurs vs zamknięcie {pctf(s['clv'], True)}" if s["clv"] is not None else "") + ". Agent będzie bardziej wybredny.")
            return True
        return False

    def step_edge_down(self, sp, bets):
        R = self.s["rules"][sp]
        act = R["tactic"]
        s = stats_of([r for r in bets if r["b"].get("tactic", "blend") == act])
        thr = R["edges"][act]
        if thr <= EDGE_LIMITS[0] + 1e-9 or s["n"] < 50 or s["roi"] <= 0 or (s["clv"] is not None and s["clv"] <= 0):
            return False
        cf = stats_of([r for r in self.paper_rows(sp) if r["a"].get("tactic") == act and thr - 0.01 <= r["a"]["best"]["edge"] < thr])
        if cf["n"] >= 30 and cf["roi"] > 0 and (cf["clv"] is None or cf["clv"] > 0):
            R["edges"][act] = round(max(EDGE_LIMITS[0], thr - 0.005), 3)
            self.change(sp, f"Obniżam wymaganą przewagę z {pctf(thr, True)} do {pctf(R['edges'][act], True)}.",
                        f"Zakłady zarabiają ({pctf(s['roi'], True)}), a {cf['n']} pominiętych meczów z nieco mniejszą przewagą też dałoby zysk ({pctf(cf['roi'], True)}).")
            return True
        return False

    def step_odds_max(self, sp, bets):
        R = self.s["rules"][sp]
        lo, _ = ODDS_MAX_LIMITS[sp]
        cut = 2.5 if sp == "pilka" else 2.05
        s = stats_of([r for r in bets if r["b"]["odds"] > cut])
        if R["odds_max"] > lo + 1e-9 and self.bad(s, 20, -0.20):
            old = R["odds_max"]
            R["odds_max"] = round(max(lo, old - (0.2 if sp == "pilka" else 0.1)), 2)
            self.change(sp, f"Obniżam najwyższy kurs z {oddf(old)} do {oddf(R['odds_max'])}.",
                        f"{s['n']} zakładów po kursie powyżej {oddf(cut)}: wynik {pctf(s['roi'], True)}"
                        + (f", kurs vs zamknięcie {pctf(s['clv'], True)}." if s["clv"] is not None else "."))
            return True
        return False

    def step_stats(self, sp, bets):
        if sp != "pilka":
            return False
        R = self.s["rules"][sp]
        if R["stats_filter"]:
            cf = stats_of([r for r in self.paper_rows(sp) if r["a"].get("stats_block")])
            if cf["n"] >= 20 and cf["roi"] > 0 and (cf["clv"] is None or cf["clv"] > 0):
                R["stats_filter"] = False
                self.change(sp, "Przestaję odrzucać zakłady, gdy statystyki wskazują drugą stronę.",
                            f"{cf['n']} odrzuconych w ten sposób meczów dałoby zysk {pctf(cf['roi'], True)} – filtr przeszkadzał.")
                return True
        else:
            s = stats_of([r for r in bets if r["b"].get("stats_against")])
            if self.bad(s, 15, -0.15):
                R["stats_filter"] = True
                self.change(sp, "Znów odrzucam zakłady, gdy statystyki mocno wskazują drugą stronę.",
                            f"{s['n']} takich zakładów: wynik {pctf(s['roi'], True)}.")
                return True
        return False

    def step_weight(self, sp, bets):
        """NBA: how much the agent trusts its own model against the bookmakers (log-loss on all analysed games)."""
        if sp != "nba":
            return False
        R = self.s["rules"][sp]
        rows = [a for a in self.A.values() if a["sp"] == "nba" and a.get("res") and a.get("line") is not None
                and a.get("pm") is not None and a.get("pk") is not None and abs(sum(a["res"]) - a["line"]) > 1e-9]
        if len(rows) < 100:
            return False

        def ll(w):
            t = 0.0
            for a in rows:
                p = pool([a["pm"], 1 - a["pm"]], [a["pk"], 1 - a["pk"]], w)[0]
                y = sum(a["res"]) > a["line"]
                t -= math.log(max(p if y else 1 - p, 1e-9))
            return t / len(rows)

        best = min([i / 10 for i in range(11)], key=ll)
        cur = R["w_model"]
        if abs(best - cur) >= 0.1 - 1e-9 and ll(cur) - ll(best) > 0.002:
            new = round(cur + (0.1 if best > cur else -0.1), 1)
            R["w_model"] = new
            self.change(sp, f"Zmieniam zaufanie do własnego modelu z {pctf(cur)} do {pctf(new)}.",
                        f"Na {len(rows)} rozliczonych meczach NBA lepiej sprawdzało się {pctf(best)} modelu, a resztę dają kursy bukmacherów.")
            return True
        return False

    # ------------------------------------------------ summary for the page (what the agent learned so far)
    def summary(self):
        S = self.s
        settled = [b for b in S["bets"] if b["status"] in ("won", "lost", "push")]

        def block(bs):
            staked = sum(b["stake"] for b in bs)
            profit = sum(b["profit"] for b in bs)
            clv = [b["clv"] for b in bs if b.get("clv") is not None]
            return {"bets": len(bs), "won": sum(1 for b in bs if b["status"] == "won"),
                    "lost": sum(1 for b in bs if b["status"] == "lost"), "staked": r2(staked), "profit": r2(profit),
                    "roi": r4(profit / staked) if staked else None, "clv": r4(sum(clv) / len(clv)) if clv else None}

        out = {"all": block(settled)}
        for sp in ("pilka", "nba"):
            out[sp] = block([b for b in settled if b["sp"] == sp])

        def split(key):
            groups = {}
            for b in settled:
                groups.setdefault(key(b), []).append(b)
            return [dict(block(v), name=k) for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))]

        out["by_code"] = {lg: block([b for b in settled if b["lg"] == lg]) for lg in sorted({b["lg"] for b in settled})}
        out["by"] = {
            "league": split(lambda b: b["lgn"]),
            "side": split(lambda b: f"{SPORT_LABEL[b['sp']]}: {b['side']}"),
            "odds": split(lambda b: odds_bucket(b["odds"])),
            "edge": split(lambda b: edge_bucket(b["edge"])),
            "book": split(lambda b: b["book"]),
        }
        tact = {}
        for sp in ("pilka", "nba"):
            T = self.tactic_stats(sp)
            open_n = {t: sum(1 for a in self.A.values() if a["sp"] == sp and "res" not in a and (a.get("tx") or {}).get(t)) for t in TACTICS[sp]}
            tact[sp] = [{"key": t, "name": v["name"], "desc": v["desc"], "edge": S["rules"][sp]["edges"][t],
                         "active": S["rules"][sp]["tactic"] == t, "open": open_n[t], **pub(T[t])} for t, v in TACTICS[sp].items()]
        eq = self.equity()
        days = (self.now.date() - dt.date.fromisoformat(S["start"])).days
        a = out["all"]
        ready = {"days": [days, READY["days"]], "bets": [len(settled), READY["bets"]],
                 "profit": eq > S["start_balance"], "clv": a["clv"] is not None and a["clv"] > 0}
        ready["ok"] = days >= READY["days"] and len(settled) >= READY["bets"] and ready["profit"] and ready["clv"]
        up = [x for x in self.A.values() if dt.datetime.fromisoformat(x["ko"]) > self.now]
        return {"equity": r2(eq), "cash": r2(S["cash"]), "open": self.open_stakes(),
                "n_open": sum(1 for b in S["bets"] if b["status"] == "open"),
                "profit": r2(eq - S["start_balance"]), "stats": out, "tactics": tact, "ready": ready,
                "analysed": {"upcoming": len(up), "upcoming_bets": sum(1 for x in up if x["dec"] == "bet"),
                             "settled": sum(1 for x in self.A.values() if "res" in x), "total": len(self.A),
                             "pilka": sum(1 for x in self.A.values() if x["sp"] == "pilka"),
                             "nba": sum(1 for x in self.A.values() if x["sp"] == "nba")},
                "learning": {sp: {"settled": len(self.bet_rows(sp)), "need": LEARN_MIN} for sp in ("pilka", "nba")}}

    def finish(self, extra_status=None):
        self.place()
        try:
            self.adapt()
        except Exception as e:  # learning must never break the run
            self.errors.append(f"nauka: {e}")
        S = self.s
        eq = self.equity()
        today = self.now.date().isoformat()
        if S["history"] and S["history"][-1][0] == today:
            S["history"][-1][1] = r2(eq)
        else:
            S["history"].append([today, r2(eq)])
        cutoff = (self.now.date() - dt.timedelta(days=KEEP_ANALYSES_DAYS)).isoformat()
        stale = (self.now.date() - dt.timedelta(days=21)).isoformat()
        for k in [k for k, a in self.A.items() if a["date"] < cutoff or ("res" not in a and a["date"] < stale)]:
            del self.A[k]  # too old, or never settled (postponed): nothing to learn from
        horizon = self.now + dt.timedelta(days=7)
        upcoming = sorted((a for a in self.A.values() if self.now < dt.datetime.fromisoformat(a["ko"]) <= horizon),
                          key=lambda a: (a["ko"], a["lg"], a["home"]))
        S["summary"] = self.summary()
        S["upcoming"] = [{k: a.get(k) for k in ("id", "sp", "lg", "lgn", "ko", "home", "away", "line", "p", "pm", "pk", "mu", "mu_inj",
                                                 "best", "dec", "why", "stake", "tx", "b2b", "elo", "inj", "p_inj", "pk0", "mv",
                                                 "lmed", "line0", "xg", "tactic", "odds_age_h", "gp")}
                         for a in upcoming]
        S["status"] = dict(extra_status or {}, errors=self.errors)
        S["leagues"] = LEAGUES
        S["books"] = {"pilka": list(FOOT_BOOKS.values()), "nba": list(NBA_PREF.values())}
        S["updated"] = self.now.isoformat(timespec="minutes")
        S["bets"].sort(key=lambda b: (b["ko"], b["id"]))
        old = load_json(self.path, {})
        strip = lambda o: {k: v for k, v in o.items() if k != "updated"}
        if old and strip(old) == strip(S):
            S["updated"] = old.get("updated", S["updated"])
        json.dump(S, open(self.path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        json.dump({"rows": dict(sorted(self.A.items()))}, open(self.apath, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        return S["summary"]


SPORT_LABEL = {"pilka": "Piłka", "nba": "NBA"}
