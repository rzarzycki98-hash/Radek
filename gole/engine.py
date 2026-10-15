#!/usr/bin/env python3
"""Linia Goli v3: 38 leagues, over/under 2.5 and 1X2.

Every run (GitHub Actions, every 4 hours):
  1. downloads results and odds from football-data.co.uk (completed seasons are cached),
     upcoming fixtures and UK bookmaker prices from The Odds API (inside the free budget),
  2. re-tunes every league on its newest results (walk-forward, so it learns from its errors),
  3. blends the model with the betting market, prices the fixtures, writes paper bets,
  4. settles bets and every prediction after the match, and grades each league
     (a league only counts as "checked" when it beat the closing line in the test).

Writes gole/data.json, gole/journal.json, gole/predictions.json, gole/odds_cache.json.
Usage:
  python engine.py --out gole                     # live run
  python engine.py --local DIR --today YYYY-MM-DD --out OUT --fixtures-from-results
      # offline test against DIR/data/<code>/season-XXYY.csv and DIR/new/<CODE>.csv
"""
import argparse, csv, difflib, io, json, math, os, re, sys, time, unicodedata, urllib.request, datetime as dt
from zoneinfo import ZoneInfo

# code, name, country, The Odds API sport key (None = not covered)
MAIN = [
    ("E0", "Premier League", "Anglia", "soccer_epl"),
    ("E1", "Championship", "Anglia", "soccer_efl_champ"),
    ("E2", "League One", "Anglia", "soccer_england_league1"),
    ("E3", "League Two", "Anglia", "soccer_england_league2"),
    ("EC", "National League", "Anglia", None),
    ("SC0", "Premiership", "Szkocja", "soccer_spl"),
    ("SC1", "Championship", "Szkocja", None),
    ("SC2", "League One", "Szkocja", None),
    ("SC3", "League Two", "Szkocja", None),
    ("D1", "Bundesliga", "Niemcy", "soccer_germany_bundesliga"),
    ("D2", "2. Bundesliga", "Niemcy", "soccer_germany_bundesliga2"),
    ("I1", "Serie A", "Włochy", "soccer_italy_serie_a"),
    ("I2", "Serie B", "Włochy", "soccer_italy_serie_b"),
    ("SP1", "LaLiga", "Hiszpania", "soccer_spain_la_liga"),
    ("SP2", "LaLiga 2", "Hiszpania", "soccer_spain_segunda_division"),
    ("F1", "Ligue 1", "Francja", "soccer_france_ligue_one"),
    ("F2", "Ligue 2", "Francja", "soccer_france_ligue_two"),
    ("N1", "Eredivisie", "Holandia", "soccer_netherlands_eredivisie"),
    ("B1", "Pro League", "Belgia", "soccer_belgium_first_div"),
    ("P1", "Liga Portugal", "Portugalia", "soccer_portugal_primeira_liga"),
    ("T1", "Süper Lig", "Turcja", "soccer_turkey_super_league"),
    ("G1", "Super League", "Grecja", "soccer_greece_super_league"),
]
EXTRA = [  # one file per league with all seasons, 1X2 closing odds only, no shots
    ("ARG", "Liga Profesional", "Argentyna", "soccer_argentina_primera_division", "Argentina"),
    ("AUT", "Bundesliga", "Austria", "soccer_austria_bundesliga", "Austria"),
    ("BRA", "Serie A", "Brazylia", "soccer_brazil_campeonato", "Brazil"),
    ("CHN", "Super League", "Chiny", "soccer_china_superleague", "China"),
    ("DNK", "Superliga", "Dania", "soccer_denmark_superliga", "Denmark"),
    ("FIN", "Veikkausliiga", "Finlandia", "soccer_finland_veikkausliiga", "Finland"),
    ("IRL", "Premier Division", "Irlandia", "soccer_league_of_ireland", "Ireland"),
    ("JPN", "J1 League", "Japonia", "soccer_japan_j_league", "Japan"),
    ("MEX", "Liga MX", "Meksyk", "soccer_mexico_ligamx", "Mexico"),
    ("NOR", "Eliteserien", "Norwegia", "soccer_norway_eliteserien", "Norway"),
    ("POL", "Ekstraklasa", "Polska", "soccer_poland_ekstraklasa", "Poland"),
    ("ROU", "Liga I", "Rumunia", None, "Romania"),
    ("RUS", "Premier Liga", "Rosja", "soccer_russia_premier_league", "Russia"),
    ("SWE", "Allsvenskan", "Szwecja", "soccer_sweden_allsvenskan", "Sweden"),
    ("SWZ", "Super League", "Szwajcaria", "soccer_switzerland_superleague", "Switzerland"),
    ("USA", "MLS", "USA", "soccer_usa_mls", "USA"),
]
TOP = ["E0", "SP1", "I1", "D1", "F1"]          # first in line for the odds budget
BASE = "https://www.football-data.co.uk"
N_SEASONS = 6

RHO = -0.08                                   # Dixon-Coles low-score correction
SOT_W = 0.5                                   # weight of shots-on-target expected goals (leagues with shots)
PROMOTED = (0.82, 1.18)                       # prior attack/defence of a newly promoted team
GRID = [(h, k) for h in (120.0, 240.0, 480.0) for k in (8.0, 20.0, 50.0)]   # half-life days x prior matches
W_GRID = [i / 10 for i in range(11)]          # model weight in the blend with the market (0 = market only)
DEFAULT = {"half_life": 240.0, "prior": 20.0, "w_ou": 0.3, "w_x": 0.3}
EDGE_MIN = 0.03                               # model+market tip: probability x odds - 1 above 3%
MARKET_EDGE_MIN = 0.02                        # market tip: a bookmaker beats the fair price by 2%
MIN_BOOKS_FAIR = 3
MAXG = 10
LONDON = ZoneInfo("Europe/London")
VERSION = 3


# ---------------------------------------------------------------- small helpers

def season_code(year):  # 2026 -> "2627"
    return f"{year % 100:02d}{(year + 1) % 100:02d}"


def season_years(today, n):
    y = today.year if today.month >= 7 else today.year - 1
    return [y - i for i in range(n)]  # current first


def fnum(x):
    try:
        v = float(x)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def r4(x):
    return None if x is None else round(x, 4)


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def demargin(odds):
    """Fair probabilities from one bookmaker's prices (proportional margin removal)."""
    if not odds or any(not o for o in odds):
        return None
    inv = [1 / o for o in odds]
    s = sum(inv)
    return [x / s for x in inv]


def pool(pm, pk, w):
    """Log-linear pooling of model and market probabilities (w = model weight)."""
    if pk is None:
        return list(pm)
    v = [max(a, 1e-9) ** w * max(b, 1e-9) ** (1 - w) for a, b in zip(pm, pk)]
    s = sum(v)
    return [x / s for x in v]


# ---------------------------------------------------------------- data

OU_PRE = {"B365": ("B365>2.5", "B365<2.5"), "P": ("P>2.5", "P<2.5"), "Max": ("Max>2.5", "Max<2.5"), "Avg": ("Avg>2.5", "Avg<2.5")}
OU_CLOSE = {"B365": ("B365C>2.5", "B365C<2.5"), "P": ("PC>2.5", "PC<2.5"), "Max": ("MaxC>2.5", "MaxC<2.5"), "Avg": ("AvgC>2.5", "AvgC<2.5")}
X_PRE = {"B365": "B365", "P": "PS", "Max": "Max", "Avg": "Avg"}
X_CLOSE = {"B365": "B365C", "P": "PSC", "Max": "MaxC", "Avg": "AvgC"}


def parse_rows(text, div=None, code=None):
    """Rows from a football-data CSV: main-league files, fixtures.csv and the 'new' league files."""
    rows = []
    for r in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        if div and r.get("Div") and r["Div"] != div:
            continue
        home = (r.get("HomeTeam") or r.get("Home") or "").strip()
        away = (r.get("AwayTeam") or r.get("Away") or "").strip()
        d = parse_date(r.get("Date"))
        if not home or not away or not d:
            continue

        def gi(*keys):
            for k in keys:
                try:
                    return int(float(r.get(k, "")))
                except ValueError:
                    pass
            return None

        def pair(keys):
            return [fnum(r.get(keys[0])), fnum(r.get(keys[1]))]

        def trio(prefix):
            return [fnum(r.get(prefix + s)) for s in "HDA"]

        ou = {b: pair(k) for b, k in OU_PRE.items()}
        ouc = {b: pair(k) for b, k in OU_CLOSE.items()}
        xp = {b: trio(k) for b, k in X_PRE.items()}
        xc = {b: trio(k) for b, k in X_CLOSE.items()}
        rows.append({
            "div": code or r.get("Div") or div, "d": d, "t": (r.get("Time") or "").strip()[:5],
            "h": home, "a": away, "hg": gi("FTHG", "HG"), "ag": gi("FTAG", "AG"),
            "hst": gi("HST"), "ast": gi("AST"), "season": (r.get("Season") or "").strip() or None,
            "country": (r.get("Country") or "").strip() or None,
            "ou": {b: v for b, v in ou.items() if v[0] and v[1]},
            "ouc": {b: v for b, v in ouc.items() if v[0] and v[1]},
            "x": {b: v for b, v in xp.items() if all(v)},
            "xc": {b: v for b, v in xc.items() if all(v)},
        })
    return rows


class Source:
    """football-data.co.uk with a disk cache: completed seasons are downloaded once."""

    def __init__(self, local=None, cache_dir=None):
        self.local, self.cache_dir = local, cache_dir
        self.errors, self.downloads = [], 0
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    def _get(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "linia-goli/3 (+github actions)"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    self.downloads += 1
                    time.sleep(0.3)  # be gentle with a small free site
                    return r.read().decode("utf-8-sig", errors="replace")
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(3)

    def _cached(self, name, url, max_age_h):
        """Text of url, from the disk cache when younger than max_age_h (None = forever)."""
        path = os.path.join(self.cache_dir, name) if self.cache_dir else None
        if path and os.path.exists(path):
            age = (time.time() - os.path.getmtime(path)) / 3600
            if max_age_h is None or age < max_age_h:
                return open(path, encoding="utf-8").read()
        try:
            text = self._get(url)
        except Exception:
            if path and os.path.exists(path):  # source down: use the stale copy
                return open(path, encoding="utf-8").read()
            raise
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        return text

    def season(self, code, year, current):
        sc = season_code(year)
        try:
            if self.local:
                p = os.path.join(self.local, "data", code, f"season-{sc}.csv")
                return parse_rows(open(p, encoding="utf-8-sig").read(), code) if os.path.exists(p) else []
            text = self._cached(f"{code}-{sc}.csv", f"{BASE}/mmz4281/{sc}/{code}.csv", 3.5 if current else None)
            return parse_rows(text, code)
        except Exception as e:
            if current or year >= dt.date.today().year - 5:
                self.errors.append(f"{code} {sc}: {e}")
            return []

    def extra(self, code):
        try:
            if self.local:
                p = os.path.join(self.local, "new", f"{code}.csv")
                return parse_rows(open(p, encoding="utf-8-sig").read(), code=code) if os.path.exists(p) else []
            return parse_rows(self._cached(f"new-{code}.csv", f"{BASE}/new/{code}.csv", 11), code=code)
        except Exception as e:
            self.errors.append(f"{code}: {e}")
            return []

    def fixtures(self):
        if self.local:
            return None
        try:
            return parse_rows(self._cached("fixtures.csv", f"{BASE}/fixtures.csv", 3.5))
        except Exception as e:
            self.errors.append(f"fixtures: {e}")
            return []

    def extra_fixtures(self):
        """Upcoming matches of the 'new' leagues (optional file; the Odds API fills gaps)."""
        if self.local:
            return []
        try:
            return parse_rows(self._cached("new_league_fixtures.csv", f"{BASE}/new_league_fixtures.csv", 3.5))
        except Exception:
            return []


def split_extra_seasons(rows, n):
    by = {}
    for m in rows:
        by.setdefault(m["season"] or str(m["d"].year), []).append(m)
    seasons = sorted(by.values(), key=lambda rs: min(m["d"] for m in rs))
    return [sorted(s, key=lambda m: m["d"]) for s in seasons[-n:]]


def teams_of(rows):
    return {m["h"] for m in rows} | {m["a"] for m in rows}


# ---------------------------------------------------------------- model

class Rater:
    """Team attack/defence ratings with exponential time decay, updated match by match.

    Equivalent to re-fitting on all matches strictly before the query date, but O(1) per match,
    which makes tuning every league on every run cheap."""

    def __init__(self, half_life, prior, sot_w):
        self.lam = 0.5 ** (1 / half_life)
        self.prior, self.sot_w = prior, sot_w
        self.ref = None
        self.g = [0.0] * 5  # SW, SH, SA, SG(sot matches), SS
        self.t = {}         # team -> [ref_date, Wh, Wa, GF, GFs, SF, GA, GAs, SA]

    def _decay_global(self, d):
        if self.ref is None:
            self.ref = d
        elif d > self.ref:
            f = self.lam ** (d - self.ref).days
            self.g = [x * f for x in self.g]
            self.ref = d

    def _team(self, name, d):
        a = self.t.get(name)
        if a is None:
            a = self.t[name] = [d, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        elif d > a[0]:
            f = self.lam ** (d - a[0]).days
            for i in range(1, 9):
                a[i] *= f
            a[0] = d
        return a

    def add(self, m, d):
        """Add a finished match as seen from date d (d > match date)."""
        self._decay_global(d)
        w = self.lam ** (d - m["d"]).days
        hg, ag = m["hg"], m["ag"]
        sot = self.sot_w and m["hst"] is not None and m["ast"] is not None
        g = self.g
        g[0] += w; g[1] += w * hg; g[2] += w * ag
        if sot:
            g[3] += w * (hg + ag); g[4] += w * (m["hst"] + m["ast"])
        for team, home, gf, ga, sf, sa in ((m["h"], True, hg, ag, m["hst"], m["ast"]), (m["a"], False, ag, hg, m["ast"], m["hst"])):
            a = self._team(team, d)
            a[1 if home else 2] += w
            a[3] += w * gf; a[6] += w * ga
            if sot:
                a[4] += w * gf; a[5] += w * sf; a[7] += w * ga; a[8] += w * sa

    def ok(self):
        return self.g[0] > 20

    def base(self):
        SW, SH, SA, SG, SS = self.g
        H = SH / SW if SW else 1.45
        A = SA / SW if SW else 1.15
        conv = SG / SS if SS else 0.3
        return H, A, conv

    def rating(self, team, d, prev_teams, H, A, conv):
        pa, pd = PROMOTED if prev_teams is not None and team not in prev_teams else (1.0, 1.0)
        a = self.t.get(team)
        if a is None:
            return pa, pd
        a = self._team(team, d)
        s = self.sot_w
        gf = a[3] - s * a[4] + s * conv * a[5]
        ga = a[6] - s * a[7] + s * conv * a[8]
        ef = H * a[1] + A * a[2]
        ea = A * a[1] + H * a[2]
        k = self.prior * (H + A) / 2
        return (gf + k * pa) / (ef + k), (ga + k * pd) / (ea + k)

    def lambdas(self, h, a, d, prev_teams):
        self._decay_global(d)
        H, A, conv = self.base()
        ah, dh = self.rating(h, d, prev_teams, H, A, conv)
        aa, da = self.rating(a, d, prev_teams, H, A, conv)
        return H * ah * da, A * aa * dh


def pois_list(lam):
    p = [math.exp(-lam)]
    for k in range(1, MAXG + 1):
        p.append(p[-1] * lam / k)
    return p


def fast_probs(lh, la, rho=RHO):
    """(P over 2.5, [P home, P draw, P away]) with the Dixon-Coles correction, no full matrix."""
    ph, pa = pois_list(lh), pois_list(la)
    t00 = max(0.0, 1 - lh * la * rho); t01 = max(0.0, 1 + lh * rho)
    t10 = max(0.0, 1 + la * rho); t11 = max(0.0, 1 - rho)
    p00, p01, p10, p11 = ph[0] * pa[0] * t00, ph[0] * pa[1] * t01, ph[1] * pa[0] * t10, ph[1] * pa[1] * t11
    under = p00 + p01 + p10 + p11 + ph[2] * pa[0] + ph[0] * pa[2]
    draw = sum(ph[i] * pa[i] for i in range(2, MAXG + 1)) + p00 + p11
    cum, home = 0.0, 0.0
    for i in range(MAXG + 1):
        home += ph[i] * cum
        cum += pa[i]
    home += p10 - ph[1] * pa[0]
    away = 1.0 - home - draw  # mass outside the truncated grid is negligible
    tot = home + draw + away
    return 1 - under, [home / tot, draw / tot, away / tot]


def score_matrix(lh, la, rho=RHO):
    ph, pa = pois_list(lh), pois_list(la)
    M = [[ph[i] * pa[j] for j in range(MAXG + 1)] for i in range(MAXG + 1)]
    M[0][0] *= max(0.0, 1 - lh * la * rho)
    M[0][1] *= max(0.0, 1 + lh * rho)
    M[1][0] *= max(0.0, 1 + la * rho)
    M[1][1] *= max(0.0, 1 - rho)
    s = sum(map(sum, M))
    return [[v / s for v in row] for row in M]


def markets(lh, la, rho=RHO):
    M = score_matrix(lh, la, rho)
    tot, x12, btts = {}, [0.0, 0.0, 0.0], 0.0
    for i in range(MAXG + 1):
        for j in range(MAXG + 1):
            p = M[i][j]
            tot[i + j] = tot.get(i + j, 0) + p
            x12[0 if i > j else (1 if i == j else 2)] += p
            if i and j:
                btts += p
    over = {str(l): round(sum(p for g, p in tot.items() if g > l), 4) for l in (0.5, 1.5, 2.5, 3.5, 4.5)}
    dist = [round(tot.get(g, 0), 4) for g in range(7)]
    dist.append(round(max(0.0, 1 - sum(dist)), 4))
    scores = sorted(((M[i][j], f"{i}:{j}") for i in range(6) for j in range(6)), reverse=True)[:5]
    return {"over": over, "btts": round(btts, 4), "x12": [round(v, 4) for v in x12],
            "dist": dist, "scores": [[s, round(p, 4)] for p, s in scores]}


def run_rater(seasons, half_life, prior, sot_w, upto=None):
    """One chronological pass. Returns (predictions per match id(m), rater at `upto`)."""
    r = Rater(half_life, prior, sot_w)
    preds = {}
    pending, cur = [], None
    for si, rows in enumerate(seasons):
        prev = teams_of(seasons[si - 1]) if si > 0 and seasons[si - 1] else None
        for m in rows:
            if m["hg"] is None:
                continue
            if m["d"] != cur:  # matches of earlier days become known
                for x in pending:
                    r.add(x, m["d"])
                pending, cur = [], m["d"]
            if si > 0 and r.ok():
                lh, la = r.lambdas(m["h"], m["a"], m["d"], prev)
                preds[id(m)] = fast_probs(lh, la)
            pending.append(m)
    if upto is not None:
        for x in pending:
            if x["d"] < upto:
                r.add(x, upto)
        r._decay_global(upto)
    return preds, r


# ---------------------------------------------------------------- tuning and the honest test

def ll_ou(p, over):
    return -math.log(max(p if over else 1 - p, 1e-9))


def ll_x(px, res):
    return -math.log(max(px[res], 1e-9))


def result_idx(m):
    return 0 if m["hg"] > m["ag"] else (1 if m["hg"] == m["ag"] else 2)


def mkt_ref(m, extra):
    """Market probabilities used for the blend: pre-match Pinnacle (main) or closing Pinnacle (extra)."""
    if extra:
        x = demargin(m["xc"].get("P") or m["xc"].get("Avg"))
        return None, x
    o = demargin(m["ou"].get("P") or m["ou"].get("Avg"))
    x = demargin(m["x"].get("P") or m["x"].get("Avg"))
    return (o[0] if o else None), x


def choose_params(sample, preds_by_combo, extra):
    """Pick (half_life, prior) by model log-loss, then the blend weights by blended log-loss."""
    best, best_ll = None, None
    for ci, preds in enumerate(preds_by_combo):
        ll = n = 0
        for m in sample:
            p = preds.get(id(m))
            if p is None:
                continue
            if not extra:
                ll += ll_ou(p[0], m["hg"] + m["ag"] > 2)
            ll += ll_x(p[1], result_idx(m)); n += 1
        if n >= 40 and (best_ll is None or ll / n < best_ll):
            best, best_ll = ci, ll / n
    if best is None:
        return None
    preds = preds_by_combo[best]
    out = {"half_life": GRID[best][0], "prior": GRID[best][1], "w_ou": DEFAULT["w_ou"], "w_x": DEFAULT["w_x"], "combo": best}
    for key in ("w_ou", "w_x"):
        if key == "w_ou" and extra:
            continue
        scores = []
        for w in W_GRID:
            ll = n = 0
            for m in sample:
                p = preds.get(id(m))
                if p is None:
                    continue
                qo, qx = mkt_ref(m, extra)
                if key == "w_ou" and qo is not None:
                    q = pool([p[0], 1 - p[0]], [qo, 1 - qo], w)[0]
                    ll += ll_ou(q, m["hg"] + m["ag"] > 2); n += 1
                elif key == "w_x" and qx is not None:
                    ll += ll_x(pool(p[1], qx, w), result_idx(m)); n += 1
            if n >= 40:
                scores.append((ll / n, w))
        if scores:
            out[key] = min(scores)[1]
    return out


def best_side(probs, odds_by_book, books):
    """Best (edge, side index, odds, book) over the given books."""
    best = None
    for b in books:
        odds = odds_by_book.get(b)
        if not odds:
            continue
        for i, (p, o) in enumerate(zip(probs, odds)):
            if o and p:
                e = p * o - 1
                if best is None or e > best[0]:
                    best = (e, i, o, b)
    return best


def acc_bet(acc, won, odds, close):
    acc["n"] += 1
    acc["profit"] += odds - 1 if won else -1.0
    if close:
        acc["clv"] += odds / close - 1
        acc["nc"] += 1


def new_acc():
    return {"n": 0, "profit": 0.0, "clv": 0.0, "nc": 0}


def fin_acc(a):
    return {"bets": a["n"], "roi": r4(a["profit"] / a["n"]) if a["n"] else None,
            "clv": r4(a["clv"] / a["nc"]) if a["nc"] else None}


def grade(a, extra):
    """Safety switch: when may a league's tips be trusted?"""
    n, roi, clv = a["bets"], a["roi"], a["clv"]
    if n < 30:
        return "few"
    if extra:  # bets at closing prices only: no closing-line check possible
        return "watch" if roi is not None and roi > 0 and n >= 150 else "no"
    if n >= 80 and roi is not None and roi > 0 and clv is not None and clv > 0:
        return "ok"
    if (roi is not None and roi > 0) or (clv is not None and clv > 0):
        return "watch"
    return "no"


def evaluate_league(seasons, extra, use_sot):
    """Walk-forward test and live parameters for one league.

    For each tested season the parameters are picked on the season before it only, so the
    reported numbers are what the self-tuning model would really have done."""
    preds_by_combo = [run_rater(seasons, h, k, SOT_W if use_sot else 0.0)[0] for h, k in GRID]
    played = [[m for m in s if m["hg"] is not None] for s in seasons]
    S = len(seasons)
    out = {"tested_seasons": 0, "matches": 0}
    # live parameters: tuned on the last completed season plus the current one so far
    recent = (played[-2] if S >= 2 else []) + played[-1]
    live = choose_params(recent, preds_by_combo, extra) if S >= 2 else None
    out["params"] = {k: v for k, v in (live or DEFAULT).items() if k != "combo"}
    out["live_combo"] = live["combo"] if live else None
    test_idx = [i for i in range(2, S) if len(played[i]) >= (30 if i == S - 1 else 100)][-3:]
    accs = {k: new_acc() for k in ("ou_one", "ou_best", "x_one", "x_best", "mk_ou", "mk_x")}
    ll = {"ou_model": 0.0, "ou_blend": 0.0, "ou_close": 0.0, "n_ou": 0, "x_model": 0.0, "x_blend": 0.0, "x_close": 0.0, "n_x": 0}
    for i in test_idx:
        prm = choose_params(played[i - 1], preds_by_combo, extra)
        if not prm:
            continue
        preds = preds_by_combo[prm["combo"]]
        out["tested_seasons"] += 1
        for m in played[i]:
            p = preds.get(id(m))
            if p is None:
                continue
            out["matches"] += 1
            over, res = m["hg"] + m["ag"] > 2, result_idx(m)
            qo, qx = mkt_ref(m, extra)
            # over/under 2.5 (main leagues have the odds)
            if not extra and qo is not None:
                po = pool([p[0], 1 - p[0]], [qo, 1 - qo], prm["w_ou"])
                qc = demargin(m["ouc"].get("P") or m["ouc"].get("Avg"))
                if qc:
                    ll["ou_model"] += ll_ou(p[0], over); ll["ou_blend"] += ll_ou(po[0], over)
                    ll["ou_close"] += ll_ou(qc[0], over); ll["n_ou"] += 1
                for key, book in (("ou_one", "B365"), ("ou_best", "Max")):
                    b = best_side(po, m["ou"], [book])
                    if b and b[0] > EDGE_MIN:
                        c = m["ouc"].get(book)
                        acc_bet(accs[key], (b[1] == 0) == over, b[2], c[b[1]] if c else None)
                fair = [qo, 1 - qo]
                for book in ("Max",):
                    b = best_side(fair, m["ou"], [book])
                    if b and b[0] > MARKET_EDGE_MIN:
                        c = m["ouc"].get(book)
                        acc_bet(accs["mk_ou"], (b[1] == 0) == over, b[2], c[b[1]] if c else None)
            # 1X2
            if qx is not None:
                px = pool(p[1], qx, prm["w_x"])
                qc = qx if extra else demargin(m["xc"].get("P") or m["xc"].get("Avg"))
                if qc:
                    ll["x_model"] += ll_x(p[1], res); ll["x_blend"] += ll_x(px, res)
                    ll["x_close"] += ll_x(qc, res); ll["n_x"] += 1
                src, csrc = ("xc", None) if extra else ("x", "xc")
                one = "B365" if m[src].get("B365") else "Avg"
                for key, book in (("x_one", one), ("x_best", "Max")):
                    b = best_side(px, m[src], [book])
                    if b and b[0] > EDGE_MIN:
                        c = m[csrc].get(book) if csrc else None
                        acc_bet(accs[key], b[1] == res, b[2], c[b[1]] if c else None)
                if not extra:
                    b = best_side(qx, m["x"], ["Max"])
                    if b and b[0] > MARKET_EDGE_MIN:
                        c = m["xc"].get("Max")
                        acc_bet(accs["mk_x"], b[1] == res, b[2], c[b[1]] if c else None)
    res_ = {k: fin_acc(a) for k, a in accs.items()}
    out["ou"] = None if extra else {
        "one": res_["ou_one"], "best": res_["ou_best"], "market": res_["mk_ou"],
        "ll": {k: r4(ll["ou_" + k] / ll["n_ou"]) for k in ("model", "blend", "close")} if ll["n_ou"] else None}
    out["x"] = {"one": res_["x_one"], "best": res_["x_best"], "market": None if extra else res_["mk_x"],
                "ll": {k: r4(ll["x_" + k] / ll["n_x"]) for k in ("model", "blend", "close")} if ll["n_x"] else None}
    out["grade"] = {"ou": None if extra else grade(res_["ou_one"], False), "x": grade(res_["x_one"], extra)}
    return out


# ---------------------------------------------------------------- team stats for the UI

def team_stats(played, team, r, d, prev):
    ms = sorted((m for m in played if m["h"] == team or m["a"] == team), key=lambda m: m["d"])

    def side(m):
        home = m["h"] == team
        return home, (m["hg"] if home else m["ag"]), (m["ag"] if home else m["hg"])
    homes = [m for m in ms if m["h"] == team]
    aways = [m for m in ms if m["a"] == team]
    form = []
    for m in ms[-5:]:
        home, f, a = side(m)
        form.append({"date": m["d"].isoformat(), "opp": m["a"] if home else m["h"], "home": home,
                     "gf": f, "ga": a, "res": "W" if f > a else ("D" if f == a else "L")})
    H, A, conv = r.base()
    att, dfn = r.rating(team, d, prev, H, A, conv)
    pts = sum(3 if side(m)[1] > side(m)[2] else (1 if side(m)[1] == side(m)[2] else 0) for m in ms)
    return {
        "gp": len(ms), "gf": sum(side(m)[1] for m in ms), "ga": sum(side(m)[2] for m in ms), "pts": pts,
        "w": sum(1 for m in ms if side(m)[1] > side(m)[2]), "dr": sum(1 for m in ms if side(m)[1] == side(m)[2]),
        "o25": sum(1 for m in ms if m["hg"] + m["ag"] > 2), "btts": sum(1 for m in ms if m["hg"] and m["ag"]),
        "o25h": [sum(1 for m in homes if m["hg"] + m["ag"] > 2), len(homes)],
        "o25a": [sum(1 for m in aways if m["hg"] + m["ag"] > 2), len(aways)],
        "att": round(att, 2), "def": round(dfn, 2), "form": form,
    }


# ---------------------------------------------------------------- The Odds API (UK bookmakers)

ODDS_URL = "https://api.the-odds-api.com/v4/sports/{sport}/{what}"
USER_BOOKS = {"ladbrokes_uk": "Ladbrokes", "betvictor": "BetVictor"}
EXCHANGES = {"betfair_ex_uk", "betfair_ex_eu", "matchbook", "smarkets", "betdaq"}  # commission eats small edges
EVENTS_REFRESH_H = 11
ODDS_REFRESH_H = 10
ODDS_WINDOW_H = 54        # only buy odds for leagues with a kick-off in this window

STOP = {"fc", "cf", "afc", "sc", "ac", "as", "ssc", "us", "rc", "cd", "ud", "sd", "vfb", "vfl", "tsg", "fsv", "sv",
        "1", "05", "04", "club", "de", "calcio", "and", "the", "hotspur", "albion", "wanderers", "town", "city", "united",
        "cf", "fk", "if", "bk", "ik", "sk", "aik", "kv", "krc", "rsc", "nk", "cd", "ca", "club", "sport", "esporte", "clube"}
ALIASES = {  # normalised feed name -> football-data name
    "manchester united": "Man United", "manchester city": "Man City", "man utd": "Man United",
    "brighton hove": "Brighton", "wolverhampton": "Wolves", "nottingham forest": "Nott'm Forest",
    "sheffield wednesday": "Sheffield Weds", "sheffield united": "Sheffield United", "queens park rangers": "QPR",
    "west bromwich": "West Brom", "west bromwich albion": "West Brom", "peterborough united": "Peterborough",
    "atletico madrid": "Ath Madrid", "atletico": "Ath Madrid", "athletic bilbao": "Ath Bilbao", "athletic": "Ath Bilbao",
    "real betis": "Betis", "celta vigo": "Celta", "rayo vallecano": "Vallecano", "real sociedad": "Sociedad",
    "espanyol": "Espanol", "deportivo la coruna": "La Coruna", "racing santander": "Santander",
    "real oviedo": "Oviedo", "real valladolid": "Valladolid", "sporting gijon": "Sp Gijon", "deportivo alaves": "Alaves",
    "inter milan": "Inter", "internazionale": "Inter", "hellas verona": "Verona",
    "bayern munchen": "Bayern Munich", "borussia dortmund": "Dortmund", "borussia monchengladbach": "M'gladbach",
    "monchengladbach": "M'gladbach", "bayer leverkusen": "Leverkusen", "eintracht frankfurt": "Ein Frankfurt",
    "koln": "FC Koln", "cologne": "FC Koln", "hamburger": "Hamburg", "schalke": "Schalke 04",
    "st pauli": "St Pauli", "sankt pauli": "St Pauli", "sv elversberg": "Elversberg",
    "paris saint germain": "Paris SG", "psg": "Paris SG", "olympique marseille": "Marseille", "olympique lyonnais": "Lyon",
    "stade rennais": "Rennes", "stade brestois 29": "Brest", "stade brestois": "Brest", "saint etienne": "St Etienne",
    "as saint etienne": "St Etienne", "estac troyes": "Troyes",
    "psv eindhoven": "PSV Eindhoven", "az alkmaar": "AZ Alkmaar", "sporting lisbon": "Sp Lisbon", "sporting cp": "Sp Lisbon",
    "sporting braga": "Sp Braga", "braga": "Sp Braga", "vitoria guimaraes": "Guimaraes", "fc porto": "Porto",
    "royal antwerp": "Antwerp", "club brugge": "Club Brugge", "union saint gilloise": "St. Gilloise",
    "olympiacos": "Olympiakos", "olympiacos piraeus": "Olympiakos", "paok": "PAOK", "aek athens": "AEK",
    "fenerbahce": "Fenerbahce", "galatasaray": "Galatasaray", "besiktas": "Besiktas",
}


def ascii_low(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().replace("'", "")
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def norm_tokens(s):
    return [t for t in ascii_low(s).split() if t not in STOP]


def tok_match(a, b):
    """1 for the same word, 0.7 for a prefix or abbreviation (weds ~ wednesday), 0.8 for a near spelling."""
    if a == b:
        return 1.0
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) >= 3 and long_.startswith(short):
        return 0.7
    if len(short) >= 3 and short[0] == long_[0]:
        it = iter(long_)
        if all(c in it for c in short):
            return 0.7
    return 0.8 if difflib.SequenceMatcher(None, a, b).ratio() >= 0.85 else 0.0


def team_sim(raw, known):
    full = ascii_low(raw)
    for key in (full, " ".join(norm_tokens(raw))):
        if key in ALIASES:
            return 1.0 if ALIASES[key] == known else 0.0
    if full == ascii_low(known):
        return 1.0
    a, b = norm_tokens(raw), norm_tokens(known)
    if not a or not b:
        a, b = full.split(), ascii_low(known).split()
    sa = sum(max(tok_match(x, y) for y in b) for x in a) / len(a)
    sb = sum(max(tok_match(x, y) for x in a) for y in b) / len(b)
    score = 0.6 * max(sa, sb) + 0.4 * min(sa, sb)
    return 0.75 * score + 0.25 * difflib.SequenceMatcher(None, full, ascii_low(known)).ratio()


def best_team(raw, known):
    sc = sorted(((team_sim(raw, k), k) for k in known), reverse=True)
    if sc and sc[0][0] >= 0.65 and (len(sc) == 1 or sc[0][0] - sc[1][0] >= 0.1):
        return sc[0][1]
    return None


class OddsAPI:
    """Fixtures (free endpoint) and UK bookmaker prices, spent carefully inside the free plan."""

    def __init__(self, key, outdir, now):
        self.key, self.now = key, now
        self.path = os.path.join(outdir, "odds_cache.json")
        self.status = {"enabled": bool(key), "calls": 0}
        try:
            c = json.load(open(self.path, encoding="utf-8"))
        except Exception:
            c = {}
        if c.get("v") != 3:  # older cache layout: start fresh (prices are refreshed within hours)
            c = {"v": 3, "sports": {}, "remaining": c.get("remaining")}
        self.c = c

    def _get(self, sport, what, params):
        q = "&".join([f"apiKey={self.key}", "dateFormat=iso"] + params)
        url = ODDS_URL.format(sport=sport, what=what) + "?" + q
        req = urllib.request.Request(url, headers={"User-Agent": "linia-goli/3"})
        with urllib.request.urlopen(req, timeout=60) as r:
            rem = r.headers.get("x-requests-remaining")
            if rem is not None:
                try:
                    self.c["remaining"] = int(float(rem))
                except ValueError:
                    pass
            return json.loads(r.read().decode("utf-8"))

    def _age_h(self, iso):
        if not iso:
            return 1e9
        return (self.now - dt.datetime.fromisoformat(iso)).total_seconds() / 3600

    def refresh(self, sports_by_div, kickoffs_by_div):
        """kickoffs_by_div: known upcoming kick-off datetimes (UTC) per league, to aim the paid calls."""
        if not self.key:
            return
        errors = []
        S = self.c["sports"]
        # 1) free: upcoming events for every covered league
        for div, sport in sports_by_div.items():
            s = S.setdefault(div, {})
            if self._age_h(s.get("events_at")) < EVENTS_REFRESH_H:
                continue
            try:
                evs = self._get(sport, "events", [])
                s["events"] = [compact_event(e) for e in evs]
                s["events_at"] = self.now.isoformat(timespec="minutes")
            except Exception as e:
                errors.append(f"{div} events: {str(e).replace(self.key, '***')}")
        # 2) paid: prices, only for leagues playing soon, within a daily allowance
        today = self.now.date().isoformat()
        led = self.c.setdefault("ledger", {})
        if led.get("day") != today:
            led.update({"day": today, "spent": 0})
        month_end = (self.now.date().replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
        days_left = (month_end - self.now.date()).days + 1
        remaining = self.c.get("remaining")
        allowance = 12 if remaining is None else max(0, int((remaining - 10) / days_left))
        horizon = self.now + dt.timedelta(hours=ODDS_WINDOW_H)
        cands = []
        for div, sport in sports_by_div.items():
            s = S.setdefault(div, {})
            kos = list(kickoffs_by_div.get(div, []))
            for e in s.get("events", []):
                try:
                    kos.append(dt.datetime.fromisoformat(e["ko"]))
                except Exception:
                    pass
            soon = [k for k in kos if self.now < k <= horizon]
            if not soon or self._age_h(s.get("odds_at")) < ODDS_REFRESH_H:
                continue
            cands.append((0 if div in TOP else 1, min(soon), div, sport))
        cands.sort()
        for _, _, div, sport in cands:
            if led["spent"] + 2 > allowance:
                break
            try:
                evs = self._get(sport, "odds", ["regions=uk", "markets=h2h,totals", "oddsFormat=decimal"])
                S[div]["odds"] = [compact_event(e) for e in evs]
                S[div]["odds_at"] = self.now.isoformat(timespec="minutes")
                led["spent"] += 2
                self.status["calls"] += 1
            except Exception as e:
                errors.append(f"{div} odds: {str(e).replace(self.key, '***')}")
        self.status["errors"] = errors
        self.status["allowance_today"] = allowance

    def save(self):
        json.dump(self.c, open(self.path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    def events(self, div):
        """Upcoming events with any prices we hold, as dicts with London date/time."""
        s = self.c["sports"].get(div, {})
        by_id = {e["id"]: dict(e) for e in s.get("events", [])}
        for e in s.get("odds", []):
            by_id.setdefault(e["id"], dict(e))["books"] = e.get("books", {})
        out = []
        for e in by_id.values():
            try:
                ko = dt.datetime.fromisoformat(e["ko"])
            except Exception:
                continue
            if ko < self.now:
                continue
            loc = ko.astimezone(LONDON)
            out.append({"d": loc.date(), "t": loc.strftime("%H:%M"), "ko": ko, "home": e["home"], "away": e["away"],
                        "books": e.get("books", {}), "odds_at": s.get("odds_at")})
        return out


def compact_event(ev):
    books = {}
    home, away = ev.get("home_team", ""), ev.get("away_team", "")
    for bm in ev.get("bookmakers", []) or []:
        ou = x = None
        for mk in bm.get("markets", []):
            if mk.get("key") == "totals":
                o = u = None
                for oc in mk.get("outcomes", []):
                    try:
                        pt = float(oc.get("point", 0))
                    except (TypeError, ValueError):
                        continue
                    if abs(pt - 2.5) > 1e-9:
                        continue
                    if oc.get("name") == "Over":
                        o = fnum(oc.get("price"))
                    elif oc.get("name") == "Under":
                        u = fnum(oc.get("price"))
                if o and u:
                    ou = [o, u]
            elif mk.get("key") == "h2h":
                p = {oc.get("name"): fnum(oc.get("price")) for oc in mk.get("outcomes", [])}
                v = [p.get(home), p.get("Draw"), p.get(away)]
                if all(v):
                    x = v
        if ou or x:
            books[bm.get("key")] = {"t": bm.get("title") or bm.get("key"), "ou": ou, "x": x}
    ko = ev.get("commence_time", "").replace("Z", "+00:00")
    return {"id": ev.get("id"), "ko": ko, "home": home, "away": away, "books": books}


def merge_events(fx, events, known, unmatched):
    """Attach bookmaker prices to fixtures (matching by date and both teams); add missing fixtures."""
    for ev in events:
        cands = [m for m in fx if abs((m["d"] - ev["d"]).days) <= 1]
        best, second = None, 0.0
        for m in cands:
            sh, sa = team_sim(ev["home"], m["h"]), team_sim(ev["away"], m["a"])
            if sh < 0.5 or sa < 0.5:
                continue
            s = sh + sa
            if best is None or s > best[0]:
                second = best[0] if best else second
                best = (s, m)
            elif s > second:
                second = s
        if best and best[0] >= 1.3 and best[0] - second >= 0.15:
            m = best[1]
            m["books"] = ev["books"]
            m["odds_at"] = ev.get("odds_at")
            if not m.get("t") and ev["t"]:
                m["t"] = ev["t"]
            continue
        h, a = best_team(ev["home"], known), best_team(ev["away"], known)
        if not h or not a or h == a:
            unmatched.extend(n for n, x in ((ev["home"], h), (ev["away"], a)) if not x)
            continue
        fx.append({"div": None, "d": ev["d"], "t": ev["t"], "h": h, "a": a, "hg": None, "ag": None,
                   "hst": None, "ast": None, "ou": {}, "ouc": {}, "x": {}, "xc": {},
                   "books": ev["books"], "odds_at": ev.get("odds_at")})
    return fx


# ---------------------------------------------------------------- pricing one fixture

def fair_prices(m):
    """Fair (margin-free) market probabilities: Pinnacle, else median of UK bookmakers, else average."""
    books = {k: b for k, b in (m.get("books") or {}).items() if k not in EXCHANGES}
    out = {}
    for mk, fd, key in (("ou", "ou", "ou"), ("x", "x", "x")):
        q = demargin(m[fd].get("P"))
        if q:
            out[mk] = (q, "Pinnacle", 1)
            continue
        qs = [demargin(b[key]) for b in books.values() if b.get(key)]
        qs = [q for q in qs if q]
        if len(qs) >= MIN_BOOKS_FAIR:
            med = [sorted(q[i] for q in qs)[len(qs) // 2] if len(qs) % 2 else
                   sum(sorted(q[i] for q in qs)[len(qs) // 2 - 1:len(qs) // 2 + 1]) / 2 for i in range(len(qs[0]))]
            s = sum(med)
            out[mk] = ([v / s for v in med], "UK", len(qs))
            continue
        q = demargin(m[fd].get("Avg"))
        if q:
            out[mk] = (q, "Średnia", 0)
    return out


def price_table(m, mk):
    """{book_key: (title, odds list)} for one market: UK bookmakers from the feed plus Bet365 from football-data."""
    t = {}
    for k, b in (m.get("books") or {}).items():
        if k in EXCHANGES:
            continue
        v = b.get("ou" if mk == "ou" else "x")
        if v:
            t[k] = (b["t"], v)
    v = m["ou" if mk == "ou" else "x"].get("B365")
    if v and "bet365" not in t:
        t["B365"] = ("Bet365", v)
    return t


SIDES = {"ou": ["Over", "Under"], "x": ["1", "X", "2"]}


def pick_bet(probs, table, edge_min):
    best = None
    for k, (title, odds) in table.items():
        for i, (p, o) in enumerate(zip(probs, odds)):
            if p and o:
                e = p * o - 1
                # the user's bookmakers win ties and near-ties
                score = e + (0.005 if k in USER_BOOKS else 0)
                if best is None or score > best[0]:
                    best = (score, e, i, o, k, title)
    if best and best[1] > edge_min:
        _, e, i, o, k, title = best
        return {"side": i, "prob": round(probs[i], 4), "odds": o, "edge": round(e, 4), "book": title, "book_key": k,
                "user_book": k in USER_BOOKS}
    return None


def price_fixture(m, r, prev, prm, extra, code, now):
    lh, la = r.lambdas(m["h"], m["a"], m["d"], prev)
    mk = markets(lh, la)
    po_model = mk["over"]["2.5"]
    x_model = mk["x12"]
    fair = fair_prices(m)
    fo, fx_ = fair.get("ou"), fair.get("x")
    final_ou = pool([po_model, 1 - po_model], fo[0], prm["w_ou"]) if fo else None
    final_x = pool(x_model, fx_[0], prm["w_x"]) if fx_ else None
    tab_ou, tab_x = price_table(m, "ou"), price_table(m, "x")
    tips = {}
    if final_ou:
        tips["model_ou"] = pick_bet(final_ou, tab_ou, EDGE_MIN)
        tips["market_ou"] = pick_bet(fo[0], tab_ou, MARKET_EDGE_MIN)
    if final_x:
        tips["model_x"] = pick_bet(final_x, tab_x, EDGE_MIN)
        tips["market_x"] = pick_bet(fx_[0], tab_x, MARKET_EDGE_MIN)
    best = {}
    for name, tab, n in (("ou", tab_ou, 2), ("x", tab_x, 3)):
        b = []
        for i in range(n):
            pr = [(odds[i], title) for title, odds in tab.values() if odds[i]]
            b.append(max(pr) if pr else None)
        best[name] = b
    ko = None
    try:
        hh, mm = (m.get("t") or "12:00").split(":")[:2]
        ko = dt.datetime.combine(m["d"], dt.time(int(hh), int(mm)), LONDON)
    except Exception:
        ko = dt.datetime.combine(m["d"], dt.time(12, 0), LONDON)
    return {
        "id": f"{code}|{m['d'].isoformat()}|{m['h']}|{m['a']}", "date": m["d"].isoformat(), "time": m.get("t") or "",
        "ko": ko.astimezone(dt.timezone.utc).isoformat(timespec="minutes"),
        "home": m["h"], "away": m["a"], "xg": [round(lh, 2), round(la, 2)], **mk,
        "fair": {"ou": [r4(v) for v in fo[0]] if fo else None, "ou_src": fo[1] if fo else None,
                 "x": [r4(v) for v in fx_[0]] if fx_ else None, "x_src": fx_[1] if fx_ else None},
        "final": {"ou": [r4(v) for v in final_ou] if final_ou else None, "x": [r4(v) for v in final_x] if final_x else None},
        "tips": {k: v for k, v in tips.items() if v},
        "prices": {"ou": {k: [t, v] for k, (t, v) in sorted(tab_ou.items())},
                   "x": {k: [t, v] for k, (t, v) in sorted(tab_x.items())}},
        "best": best, "odds_at": m.get("odds_at"),
    }


# ---------------------------------------------------------------- journal (paper bets) and predictions log

def find_result(results, e_date, home, away, days=2):
    d0 = dt.date.fromisoformat(e_date)
    for m in results:
        if m["h"] == home and m["a"] == away and m["hg"] is not None and abs((m["d"] - d0).days) <= days:
            return m
    return None


def update_journal(journal, code, name, priced, results, now, grade_now):
    entries = journal.setdefault("entries", [])
    by_id = {e["id"]: e for e in entries}
    now_iso = now.isoformat(timespec="minutes")
    for f in priced:
        started = dt.datetime.fromisoformat(f["ko"]) <= now
        for key, b in f["tips"].items():
            strategy, mk = key.split("_")
            eid = f["id"] + "|" + strategy + ("" if mk == "ou" else "|1x2")
            if eid in by_id or started:
                continue
            e = {"id": eid, "match": f["id"], "strategy": strategy, "mkt": mk, "league": code, "league_name": name,
                 "date": f["date"], "time": f["time"], "ko": f["ko"], "home": f["home"], "away": f["away"],
                 "side": SIDES[mk][b["side"]], "prob": b["prob"], "odds": b["odds"], "book": b["book"],
                 "book_key": b["book_key"], "user_book": b["user_book"], "edge": b["edge"],
                 "grade": grade_now.get(mk), "added": now_iso, "status": "open"}
            entries.append(e); by_id[eid] = e
        # follow the price until kick-off: the last price seen is the closing price for CLV
        for e in [by_id.get(f["id"] + "|" + s + sfx) for s in ("model", "market") for sfx in ("", "|1x2")]:
            if not e or e["status"] != "open" or started:
                continue
            mk = e.get("mkt", "ou")
            row = f["prices"][mk].get(e.get("book_key") or "")
            if row:
                e["last_odds"] = row[1][SIDES[mk].index(e["side"])]
    today = now.date()
    for e in entries:
        if e["league"] != code or e["status"] != "open":
            continue
        m = find_result(results, e["date"], e["home"], e["away"])
        if not m:
            if dt.date.fromisoformat(e["date"]) < today - dt.timedelta(days=21):
                e.update({"status": "void", "profit": 0.0})
            continue
        mk = e.get("mkt", "ou")
        if mk == "ou":
            won = (e["side"] == "Over") == (m["hg"] + m["ag"] > 2)
            close_rows, i = m["ouc"], ["Over", "Under"].index(e["side"])
        else:
            won = ["1", "X", "2"].index(e["side"]) == result_idx(m)
            close_rows, i = m["xc"], ["1", "X", "2"].index(e["side"])
        e.update({"status": "won" if won else "lost", "score": f"{m['hg']}:{m['ag']}",
                  "profit": round(e["odds"] - 1, 3) if won else -1.0})
        bk = e.get("book_key") or e.get("book")
        if bk in ("B365", "P") and close_rows.get(bk):
            e["close_odds"], e["close_src"] = close_rows[bk][i], "fd"
        elif e.get("last_odds"):
            e["close_odds"], e["close_src"] = e["last_odds"], "last"
        elif close_rows.get("Avg"):
            e["close_odds"], e["close_src"] = close_rows["Avg"][i], "avg"


def summarize(entries):
    settled = [e for e in entries if e["status"] in ("won", "lost")]
    n = len(settled)
    profit = sum(e["profit"] for e in settled)
    clv = [e["odds"] / e["close_odds"] - 1 for e in settled if e.get("close_odds")]
    return {"settled": n, "won": sum(1 for e in settled if e["status"] == "won"),
            "open": sum(1 for e in entries if e["status"] == "open"),
            "profit": round(profit, 2), "roi": r4(profit / n) if n else None,
            "clv": r4(sum(clv) / len(clv)) if clv else None}


def journal_summary(journal):
    es = journal.get("entries", [])
    out = {}
    for strategy in ("model", "market"):
        for mk in ("ou", "x"):
            out[f"{strategy}_{mk}"] = summarize([e for e in es if e.get("strategy", "model") == strategy and e.get("mkt", "ou") == mk])
    return out


def live_grade(journal, code):
    """Journal evidence per market for one league (model tips)."""
    out = {}
    for mk in ("ou", "x"):
        out[mk] = summarize([e for e in journal.get("entries", []) if e["league"] == code and
                             e.get("strategy", "model") == "model" and e.get("mkt", "ou") == mk])
    return out


def final_grade(test_grade, live):
    """The test grade, switched off automatically when the paper journal disagrees."""
    if test_grade is None:
        return None
    if live["settled"] >= 40 and (live["clv"] is not None and live["clv"] < 0) and (live["roi"] or 0) < 0:
        return "off"
    return test_grade


def update_predictions(preds, code, priced, results, now):
    """Every priced match is logged, settled after the match, and scored: the app's report card."""
    P = preds.setdefault("matches", {})
    for f in priced:
        if dt.datetime.fromisoformat(f["ko"]) <= now:
            continue
        P[f["id"]] = {"l": code, "date": f["date"], "time": f["time"], "home": f["home"], "away": f["away"],
                      "m_ou": f["over"]["2.5"], "m_x": f["x12"],
                      "k_ou": f["fair"]["ou"][0] if f["fair"]["ou"] else None, "k_x": f["fair"]["x"],
                      "f_ou": f["final"]["ou"][0] if f["final"]["ou"] else None, "f_x": f["final"]["x"],
                      "xg": f["xg"]}
    today = now.date()
    for mid, p in list(P.items()):
        if p["l"] != code or "score" in p:
            continue
        m = find_result(results, p["date"], p["home"], p["away"])
        if m:
            p["score"] = [m["hg"], m["ag"]]
        elif dt.date.fromisoformat(p["date"]) < today - dt.timedelta(days=21):
            del P[mid]
    cutoff = (today - dt.timedelta(days=120)).isoformat()
    for mid in [k for k, p in P.items() if p["date"] < cutoff]:
        del P[mid]


def prediction_report(preds, codes):
    """Rolling scores of finished predictions: model vs market vs final, calibration of over 2.5."""
    out = {}
    for code in codes + ["ALL"]:
        rows = [p for p in preds.get("matches", {}).values() if "score" in p and (code == "ALL" or p["l"] == code)]
        acc = {"n": len(rows)}
        for mk in ("ou", "x"):
            sc = {"m": 0.0, "k": 0.0, "f": 0.0, "n": 0, "hit": 0}
            for p in rows:
                hg, ag = p["score"]
                if mk == "ou":
                    if p["k_ou"] is None:
                        continue
                    y = hg + ag > 2
                    sc["m"] += ll_ou(p["m_ou"], y); sc["k"] += ll_ou(p["k_ou"], y); sc["f"] += ll_ou(p["f_ou"] or p["m_ou"], y)
                    sc["hit"] += ((p["f_ou"] or p["m_ou"]) >= 0.5) == y
                else:
                    if p["k_x"] is None:
                        continue
                    res = 0 if hg > ag else (1 if hg == ag else 2)
                    fx = p["f_x"] or p["m_x"]
                    sc["m"] += ll_x(p["m_x"], res); sc["k"] += ll_x(p["k_x"], res); sc["f"] += ll_x(fx, res)
                    sc["hit"] += max(range(3), key=lambda i: fx[i]) == res
                sc["n"] += 1
            n = sc["n"]
            acc[mk] = {"n": n, "ll_model": r4(sc["m"] / n) if n else None, "ll_market": r4(sc["k"] / n) if n else None,
                       "ll_final": r4(sc["f"] / n) if n else None, "hit": r4(sc["hit"] / n) if n else None}
        if code == "ALL":
            bins = [[0, 0] for _ in range(10)]
            for p in rows:
                q = p["f_ou"] if p["f_ou"] is not None else p["m_ou"]
                b = min(9, int(q * 10))
                bins[b][0] += 1; bins[b][1] += sum(p["score"]) > 2
            acc["calib_ou"] = bins
        out[code] = acc
    return out


# ---------------------------------------------------------------- main

def load_json(path, default):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return default


def run(today, src, outdir, fixtures_from_results=False, now=None, only=None):
    t0 = time.time()
    now = now or dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="minutes")
    years = season_years(today, N_SEASONS)
    journal = load_json(os.path.join(outdir, "journal.json"), {"entries": []})
    preds_log = load_json(os.path.join(outdir, "predictions.json"), {"matches": {}})
    fixtures_main = src.fixtures() or []
    fixtures_extra = src.extra_fixtures()

    leagues = [(c, n, co, sp, False, None) for c, n, co, sp in MAIN] + [(c, n, co, sp, True, cn) for c, n, co, sp, cn in EXTRA]
    if only:
        leagues = [L for L in leagues if L[0] in only]

    # 1) results
    data = {}
    for code, name, country, sport, extra, cname in leagues:
        if extra:
            seasons = split_extra_seasons(src.extra(code), N_SEASONS)
        else:
            seasons = [src.season(code, y, i == 0) for i, y in reversed(list(enumerate(years)))]  # oldest first
            seasons = [sorted(s, key=lambda m: m["d"]) for s in seasons]
            while seasons and not seasons[0]:
                seasons.pop(0)
        if not seasons or not any(seasons):
            continue
        cur = seasons[-1]
        if fixtures_from_results:  # offline test: matches from today on become fixtures
            fx = [dict(m, hg=None, ag=None) for m in cur if m["d"] >= today]
            seasons[-1] = cur = [m for m in cur if m["d"] < today]
        elif extra:
            fx = [dict(m) for m in fixtures_extra if (m["country"] or "").lower() == cname.lower() and m["d"] >= today]
        else:
            fx = [dict(m) for m in fixtures_main if m["div"] == code and m["d"] >= today]
        data[code] = {"seasons": seasons, "fx": fx}

    # 2) bookmaker prices (aimed at leagues that play soon)
    oa = OddsAPI(None if fixtures_from_results else (os.environ.get("ODDS_API_KEY", "").strip() or None), outdir, now)
    sports = {c: sp for c, _, _, sp, _, _ in leagues if sp and c in data}
    kickoffs = {}
    for code, d in data.items():
        for m in d["fx"]:
            try:
                hh, mm = (m["t"] or "15:00").split(":")[:2]
                kickoffs.setdefault(code, []).append(dt.datetime.combine(m["d"], dt.time(int(hh), int(mm)), LONDON).astimezone(dt.timezone.utc))
            except Exception:
                pass
    oa.refresh(sports, kickoffs)

    out = {"version": VERSION, "generated": now_iso, "today": today.isoformat(), "edge_min": EDGE_MIN,
           "market_edge_min": MARKET_EDGE_MIN, "leagues": []}
    unmatched = []
    for code, name, country, sport, extra, cname in leagues:
        if code not in data:
            continue
        seasons, fx = data[code]["seasons"], data[code]["fx"]
        cur = seasons[-1]
        played = [m for m in cur if m["hg"] is not None]
        use_sot = not extra and sum(1 for m in played[-60:] if m["hst"] is not None) > 20
        known = set().union(*(teams_of(s) for s in seasons[-2:] if s)) | teams_of(fx)
        if sport and not fixtures_from_results:
            fx = merge_events(fx, oa.events(code), known, unmatched)
        # 3) learn: walk-forward test and fresh parameters
        ev = evaluate_league(seasons, extra, use_sot)
        prm = ev["params"]
        prev = teams_of(seasons[-2]) if len(seasons) > 1 else None
        hist_seasons = seasons
        _, r = run_rater(hist_seasons, prm["half_life"], prm["prior"], SOT_W if use_sot else 0.0, upto=today)
        live = live_grade(journal, code)
        grades = {"ou": final_grade(ev["grade"]["ou"], live["ou"]), "x": final_grade(ev["grade"]["x"], live["x"])}
        # 4) price the fixtures
        priced = []
        for m in sorted(fx, key=lambda m: (m["d"], m.get("t") or "")):
            if m["h"] == m["a"]:
                continue
            priced.append(price_fixture(m, r, prev, prm, extra, code, now))
        update_journal(journal, code, f"{country} · {name}", priced, played, now, grades)
        update_predictions(preds_log, code, priced, played, now)
        last = max((m["d"] for m in played), default=None)
        H, A, _ = r.base()
        out["leagues"].append({
            "code": code, "name": name, "country": country, "extra": extra, "odds_feed": bool(sport),
            "played": len(played), "last_result": last.isoformat() if last else None,
            "goals_pg": round(sum(m["hg"] + m["ag"] for m in played) / len(played), 2) if played else None,
            "o25_rate": round(sum(1 for m in played if m["hg"] + m["ag"] > 2) / len(played), 3) if played else None,
            "home_rate": round(sum(1 for m in played if m["hg"] > m["ag"]) / len(played), 3) if played else None,
            "avg": [round(H, 2), round(A, 2)], "shots": use_sot,
            "params": prm, "test": {k: ev[k] for k in ("tested_seasons", "matches", "ou", "x")},
            "grade_test": ev["grade"], "grade": grades, "live": live,
            "teams": {t: team_stats(played, t, r, today, prev) for t in sorted(teams_of(cur) | teams_of(fx))},
            "fixtures": priced,
        })
    oa.save()
    out["bookmakers"] = dict(oa.status, remaining=oa.c.get("remaining"),
                             leagues_with_prices=sorted(d for d, s in oa.c["sports"].items() if s.get("odds")),
                             unmatched=sorted(set(unmatched))[:40])
    journal["summary"] = journal_summary(journal)
    journal["updated"] = now_iso
    out["journal_summary"] = journal["summary"]
    out["report"] = prediction_report(preds_log, [L["code"] for L in out["leagues"]])
    out["errors"] = src.errors
    out["runtime_s"] = round(time.time() - t0, 1)
    out["downloads"] = src.downloads
    if not out["leagues"]:  # source down: keep the last good data instead of publishing an empty page
        raise SystemExit("no leagues built: " + "; ".join(src.errors[:3]))
    os.makedirs(outdir, exist_ok=True)
    dpath = os.path.join(outdir, "data.json")
    old = load_json(dpath, None)
    strip = lambda o: {k: v for k, v in o.items() if k not in ("generated", "runtime_s", "downloads")}
    if old and strip(old) == strip(out):  # nothing changed: keep the timestamp, so no commit is made
        out["generated"] = old.get("generated", out["generated"])
    oldj = load_json(os.path.join(outdir, "journal.json"), {})
    if oldj.get("entries") == journal.get("entries"):
        journal["updated"] = oldj.get("updated", journal["updated"])
    json.dump(out, open(dpath, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(journal, open(os.path.join(outdir, "journal.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(preds_log, open(os.path.join(outdir, "predictions.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local")
    ap.add_argument("--today")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--cache", default=None, help="folder for downloaded CSV files")
    ap.add_argument("--only", default=None, help="comma-separated league codes (testing)")
    ap.add_argument("--fixtures-from-results", action="store_true")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(dt.timezone.utc).date()
    now = dt.datetime.combine(today, dt.time(9, 0), dt.timezone.utc) if a.today else None
    cache = a.cache or os.path.join(a.out, ".cache")
    o = run(today, Source(a.local, cache), a.out, a.fixtures_from_results, now=now,
            only=set(a.only.split(",")) if a.only else None)
    for L in o["leagues"]:
        t = L["test"]
        print(f"{L['country']:10} {L['name']:17} played {L['played']:3} fx {len(L['fixtures']):3} "
              f"tips {sum(len(f['tips']) for f in L['fixtures']):3} grade {L['grade']} "
              f"x1 {t['x']['one']} ou1 {t['ou']['one'] if t['ou'] else None} prm {L['params']}")
    print("journal", o["journal_summary"])
    print("bookmakers", {k: v for k, v in o["bookmakers"].items() if k != "unmatched"})
    print("runtime", o["runtime_s"], "s, downloads", o["downloads"])
    if o["errors"]:
        print("errors:", *o["errors"][:30], sep="\n  ")
