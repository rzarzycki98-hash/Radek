#!/usr/bin/env python3
"""Linia Goli v3: 38 leagues, over/under 2.5 and 1X2.

Every run (GitHub Actions, every 4 hours):
  1. downloads results and odds from football-data.co.uk (completed seasons are cached),
     upcoming fixtures and UK bookmaker prices from The Odds API (inside the free budget),
  2. re-tunes every league on its newest results (walk-forward, so it learns from its errors),
  3. blends the model with the betting market, prices the fixtures, writes paper bets,
  4. settles bets and every prediction after the match, and grades each league
     (a league only counts as "checked" when it beat the closing line in the test).

Writes gole/data.json, gole/journal.json, gole/predictions.json (last 120 days),
gole/archiwum/<YYYY-MM>.json (older settled predictions, kept for good), gole/odds_cache.json.
Usage:
  python engine.py --out gole                     # live run
  python engine.py --local DIR --today YYYY-MM-DD --out OUT --fixtures-from-results
      # offline test against DIR/data/<code>/season-XXYY.csv and DIR/new/<CODE>.csv
"""
import argparse, csv, difflib, io, json, math, os, re, sys, time, unicodedata, urllib.request, datetime as dt
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agent as AG   # the betting agent: virtual money, learns from its own bets
import nba as NBA    # NBA total points for the agent
import zrodla as ZR  # extra free data for the agent (ClubElo team strength)

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
TOP = AG.LEAGUES                              # the agent's 11 leagues are first in line for the odds budget
BASE = "https://www.football-data.co.uk"
N_SEASONS = 6

RHO = -0.08                                   # Dixon-Coles low-score correction
SOT_W = 0.5                                   # weight of shots-on-target expected goals (leagues with shots)
PROMOTED = (0.82, 1.18)                       # prior attack/defence of a newly promoted team
GRID = [(h, k) for h in (180.0, 360.0, 720.0, 1200.0) for k in (3.0, 6.0, 12.0, 25.0)]   # half-life days x prior matches
W_GRID = [i / 10 for i in range(11)]          # model weight in the blend with the market (0 = market only)
DEFAULT = {"half_life": 360.0, "prior": 12.0, "w_ou": 0.3, "w_x": 0.3}
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

OU_PRE = {"B365": ("B365>2.5", "B365<2.5"), "P": ("P>2.5", "P<2.5"), "Max": ("Max>2.5", "Max<2.5"), "Avg": ("Avg>2.5", "Avg<2.5"),
          "BFE": ("BFE>2.5", "BFE<2.5")}   # BFE = Betfair Exchange (football-data has no Pinnacle since 2025/26)
OU_CLOSE = {"B365": ("B365C>2.5", "B365C<2.5"), "P": ("PC>2.5", "PC<2.5"), "Max": ("MaxC>2.5", "MaxC<2.5"), "Avg": ("AvgC>2.5", "AvgC<2.5"),
            "BFE": ("BFEC>2.5", "BFEC<2.5")}
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
        self.stale = []  # files that failed to download, replaced by an older copy from the cache
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
        except Exception as e:
            if path and os.path.exists(path):  # source down: use the stale copy, and say so in the status
                age = (time.time() - os.path.getmtime(path)) / 3600
                self.stale.append(f"{name}: {str(e)[:80]} – użyta kopia sprzed {age:.0f} godz.")
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

    def fpl(self):
        """Fantasy Premier League player list: injuries, suspensions, chance of playing (Premier League only)."""
        try:
            if self.local:
                p = os.path.join(self.local, "fpl.json")
                return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
            path = os.path.join(self.cache_dir, "fpl.json") if self.cache_dir else None
            if path and os.path.exists(path) and (time.time() - os.path.getmtime(path)) / 3600 < 3.5:
                return json.load(open(path, encoding="utf-8"))
            req = urllib.request.Request(FPL_URL, headers={"User-Agent": "Mozilla/5.0 (linia-goli; +github actions)", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                text = r.read().decode("utf-8")
            self.downloads += 1
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            return json.loads(text)
        except Exception as e:
            self.errors.append(f"FPL: {str(e)[:120]}")
            return None

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

    def __init__(self, half_life, prior, sot_w, base_half_life=None):
        self.lam = 0.5 ** (1 / half_life)
        self.lam_g = 0.5 ** (1 / base_half_life) if base_half_life else self.lam   # league scoring level
        self.prior, self.sot_w = prior, sot_w
        self.ref = None
        self.g = [0.0] * 5  # SW, SH, SA, SG(sot matches), SS
        self.t = {}         # team -> [ref_date, Wh, Wa, GF, GFs, SF, GA, GAs, SA]

    def _decay_global(self, d):
        if self.ref is None:
            self.ref = d
        elif d > self.ref:
            f = self.lam_g ** (d - self.ref).days
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
        wg = self.lam_g ** (d - m["d"]).days
        hg, ag = m["hg"], m["ag"]
        sot = self.sot_w and m["hst"] is not None and m["ast"] is not None
        g = self.g
        g[0] += wg; g[1] += wg * hg; g[2] += wg * ag
        if sot:
            g[3] += wg * (hg + ag); g[4] += wg * (m["hst"] + m["ast"])
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


def run_rater(seasons, half_life, prior, sot_w, upto=None, base_half_life=None):
    """One chronological pass. Returns (predictions per match id(m), rater at `upto`)."""
    r = Rater(half_life, prior, sot_w, base_half_life)
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


def acc_bet(acc, won, odds, q_close):
    """q_close: fair closing probability of the side (Pinnacle without margin) -> beat-the-close value."""
    acc["n"] += 1
    acc["profit"] += odds - 1 if won else -1.0
    if q_close:
        acc["clv"] += odds * q_close - 1
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
    roi_pos, clv_pos = roi is not None and roi > 0, clv is not None and clv > 0
    if extra:  # bets at closing prices only: no closing-line check possible
        return "watch" if roi_pos and n >= 150 else "no"
    if n >= 80 and roi_pos and clv_pos:
        return "ok"
    # beating the fair closing price is the reliable signal; profit alone needs a big sample
    if clv_pos or (roi_pos and n >= 150):
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
                        acc_bet(accs[key], (b[1] == 0) == over, b[2], qc[b[1]] if qc else None)
                b = best_side([qo, 1 - qo], m["ou"], ["Max"])
                if b and b[0] > MARKET_EDGE_MIN:
                    acc_bet(accs["mk_ou"], (b[1] == 0) == over, b[2], qc[b[1]] if qc else None)
            # 1X2
            if qx is not None:
                px = pool(p[1], qx, prm["w_x"])
                qc = qx if extra else demargin(m["xc"].get("P") or m["xc"].get("Avg"))
                if qc:
                    ll["x_model"] += ll_x(p[1], res); ll["x_blend"] += ll_x(px, res)
                    ll["x_close"] += ll_x(qc, res); ll["n_x"] += 1
                src = "xc" if extra else "x"
                one = "B365" if m[src].get("B365") else "Avg"
                # extra leagues bet at closing prices, so a closing-line check would be circular
                qcl = None if extra else qc
                for key, book in (("x_one", one), ("x_best", "Max")):
                    b = best_side(px, m[src], [book])
                    if b and b[0] > EDGE_MIN:
                        acc_bet(accs[key], b[1] == res, b[2], qcl[b[1]] if qcl else None)
                if not extra:
                    b = best_side(qx, m["x"], ["Max"])
                    if b and b[0] > MARKET_EDGE_MIN:
                        acc_bet(accs["mk_x"], b[1] == res, b[2], qcl[b[1]] if qcl else None)
    res_ = {k: fin_acc(a) for k, a in accs.items()}
    out["ou"] = None if extra else {
        "one": res_["ou_one"], "best": res_["ou_best"], "market": res_["mk_ou"],
        "ll": {k: r4(ll["ou_" + k] / ll["n_ou"]) for k in ("model", "blend", "close")} if ll["n_ou"] else None}
    out["x"] = {"one": res_["x_one"], "best": res_["x_best"], "market": None if extra else res_["mk_x"],
                "ll": {k: r4(ll["x_" + k] / ll["n_x"]) for k in ("model", "blend", "close")} if ll["n_x"] else None}
    out["grade"] = {"ou": None if extra else grade(res_["ou_one"], False), "x": grade(res_["x_one"], extra)}
    combo = live["combo"] if live else GRID.index((DEFAULT["half_life"], DEFAULT["prior"]))
    out["_preds"] = preds_by_combo[combo]
    return out


# ---------------------------------------------------------------- statistics verdict (no bookmaker input)
#
# For every match the app weighs several plain statistics: the model of goals and shots, the league
# table, recent form, home/away form, goal difference and head-to-head meetings (for 1X2), and goal
# rates, recent overs, both-teams-score and head-to-head goals (for over/under 2.5). A match is
# "worth attention" when the model is confident and most statistics point the same way.

class TeamRec:
    __slots__ = ("gp", "pts", "gf", "ga", "h_gp", "h_pts", "a_gp", "a_pts", "h_o25", "a_o25", "btts", "last")

    def __init__(self):
        self.gp = self.pts = self.gf = self.ga = self.h_gp = self.h_pts = self.a_gp = self.a_pts = 0
        self.h_o25 = self.a_o25 = self.btts = 0
        self.last = []  # (points, over 2.5) of recent matches


class SeasonState:
    def __init__(self):
        self.t = {}

    def rec(self, name):
        r = self.t.get(name)
        if r is None:
            r = self.t[name] = TeamRec()
        return r

    def add(self, m):
        hg, ag = m["hg"], m["ag"]
        over, btts = hg + ag > 2, hg > 0 and ag > 0
        for team, home, gf, ga in ((m["h"], True, hg, ag), (m["a"], False, ag, hg)):
            r = self.rec(team)
            pts = 3 if gf > ga else (1 if gf == ga else 0)
            r.gp += 1; r.pts += pts; r.gf += gf; r.ga += ga; r.btts += btts
            if home:
                r.h_gp += 1; r.h_pts += pts; r.h_o25 += over
            else:
                r.a_gp += 1; r.a_pts += pts; r.a_o25 += over
            r.last.append((pts, over))
            if len(r.last) > 5:
                r.last.pop(0)

    def ranks(self, teams=()):
        names = set(self.t) | set(teams)
        order = sorted(names, key=lambda n: (-(self.t[n].pts if n in self.t else 0),
                                             -((self.t[n].gf - self.t[n].ga) if n in self.t else 0),
                                             -(self.t[n].gf if n in self.t else 0), n))
        return {n: i + 1 for i, n in enumerate(order)}, len(order)


def h2h_key(a, b):
    return (a, b) if a < b else (b, a)


def stats_verdict(h, a, S, meetings, px, pover):
    """Factors and verdicts for one match. px = model [home, draw, away], pover = model P(over 2.5)."""
    th, ta = S.t.get(h), S.t.get(a)
    meet = [x for x in meetings[-6:]]
    fx, fo = [], []
    # --- 1X2
    fx.append({"k": "model", "v": [r4(px[0]), r4(px[1]), r4(px[2])],
               "l": "h" if px[0] - px[2] >= 0.15 else "a" if px[2] - px[0] >= 0.15 else None})
    if th and ta and th.gp >= 4 and ta.gp >= 4:
        rk, n = S.ranks((h, a))
        gap = max(3, round(n / 4))
        fx.append({"k": "table", "v": [rk[h], rk[a], n, th.pts, ta.pts],
                   "l": "h" if rk[a] - rk[h] >= gap else "a" if rk[h] - rk[a] >= gap else None})
        gdh, gda = (th.gf - th.ga) / th.gp, (ta.gf - ta.ga) / ta.gp
        fx.append({"k": "gd", "v": [round(gdh, 2), round(gda, 2)],
                   "l": "h" if gdh - gda >= 0.6 else "a" if gda - gdh >= 0.6 else None})
    if th and ta and len(th.last) >= 3 and len(ta.last) >= 3:
        fh = sum(p for p, _ in th.last) / len(th.last) * 5
        fa = sum(p for p, _ in ta.last) / len(ta.last) * 5
        fx.append({"k": "form", "v": [sum(p for p, _ in th.last), len(th.last), sum(p for p, _ in ta.last), len(ta.last)],
                   "l": "h" if fh - fa >= 4 else "a" if fa - fh >= 4 else None})
    if th and ta and th.h_gp >= 2 and ta.a_gp >= 2:
        hp, ap = th.h_pts / th.h_gp, ta.a_pts / ta.a_gp
        fx.append({"k": "venue", "v": [round(hp, 2), round(ap, 2), th.h_gp, ta.a_gp],
                   "l": "h" if hp - ap >= 0.6 else "a" if ap - hp >= 0.6 else None})
    if len(meet) >= 3:
        wh = sum(1 for m in meet if (m["h"] == h and m["hg"] > m["ag"]) or (m["a"] == h and m["ag"] > m["hg"]))
        wa = sum(1 for m in meet if (m["h"] == a and m["hg"] > m["ag"]) or (m["a"] == a and m["ag"] > m["hg"]))
        fx.append({"k": "h2h", "v": [wh, len(meet) - wh - wa, wa, len(meet)],
                   "l": "h" if wh - wa >= 2 else "a" if wa - wh >= 2 else None})
    # --- over/under 2.5
    fo.append({"k": "model", "v": [r4(pover)], "l": "o" if pover >= 0.58 else "u" if pover <= 0.42 else None})
    if th and ta and th.h_gp >= 2 and ta.a_gp >= 2:
        rh, ra = th.h_o25 / th.h_gp, ta.a_o25 / ta.a_gp
        avg = (rh + ra) / 2
        fo.append({"k": "venue", "v": [round(rh, 2), round(ra, 2)], "l": "o" if avg >= 0.6 else "u" if avg <= 0.4 else None})
    if th and ta and th.gp >= 4 and ta.gp >= 4:
        gh, ga_ = (th.gf + th.ga) / th.gp, (ta.gf + ta.ga) / ta.gp
        avg = (gh + ga_) / 2
        fo.append({"k": "gpg", "v": [round(gh, 2), round(ga_, 2)], "l": "o" if avg >= 3.0 else "u" if avg <= 2.2 else None})
        bh, ba = th.btts / th.gp, ta.btts / ta.gp
        fo.append({"k": "btts", "v": [round(bh, 2), round(ba, 2)],
                   "l": "o" if bh >= 0.6 and ba >= 0.6 else "u" if bh <= 0.35 and ba <= 0.35 else None})
    if th and ta and len(th.last) + len(ta.last) >= 6:
        oh, oa = sum(o for _, o in th.last), sum(o for _, o in ta.last)
        ratio = (oh + oa) / (len(th.last) + len(ta.last))
        fo.append({"k": "last5", "v": [oh, len(th.last), oa, len(ta.last)], "l": "o" if ratio >= 0.7 else "u" if ratio <= 0.3 else None})
    if len(meet) >= 3:
        g = sum(m["hg"] + m["ag"] for m in meet) / len(meet)
        fo.append({"k": "h2h", "v": [round(g, 2), len(meet)], "l": "o" if g >= 3.0 else "u" if g <= 2.0 else None})

    def verdict(F, side, lean, other, p, hi, lo):
        agree = sum(1 for f in F if f["l"] == lean)
        against = sum(1 for f in F if f["l"] == other)
        level = 2 if p >= hi and agree >= 4 and against == 0 else (1 if p >= lo and agree >= 3 and against <= 1 else 0)
        return {"side": side, "level": level, "agree": agree, "against": against, "n": len(F), "f": F}

    def best(a, b):  # the side the statistics back more strongly
        return max((a, b), key=lambda v: (v["level"], v["agree"] - v["against"], v["p"]))

    vh = verdict(fx, 0, "h", "a", px[0], 0.55, 0.45); vh["p"] = px[0]
    va = verdict(fx, 2, "a", "h", px[2], 0.55, 0.45); va["p"] = px[2]
    vov = verdict(fo, 0, "o", "u", pover, 0.60, 0.53); vov["p"] = pover
    vun = verdict(fo, 1, "u", "o", 1 - pover, 0.60, 0.53); vun["p"] = 1 - pover
    vx, vo = best(vh, va), best(vov, vun)
    for v in (vx, vo):
        del v["p"]
    return {"x": vx, "ou": vo}


# ---------------------------------------------------------------- learned weights for the statistics
#
# Not every statistic matters equally. On the history of all leagues the app learns how much each
# one really predicts (logistic regression), then adjusts the weights to each league. The test is
# walk-forward: a season is always judged by weights learned only on the seasons before it.

import numpy as np

LEARN_T = {"x": (0.62, 0.52), "ou": (0.62, 0.56)}   # probability for "worth attention" / "possible"
X_KEYS = ["model", "table", "gd", "form", "venue", "h2h"]
O_KEYS = ["model", "venue", "gpg", "last5", "btts", "h2h"]


def feat_x(h, a, S, meet, px):
    th, ta = S.t.get(h), S.t.get(a)
    x = [math.log(max(px[0], 1e-4) / max(px[2], 1e-4)), 0.0, 0.0, 0.0, 0.0, 0.0]
    if th and ta and th.gp >= 4 and ta.gp >= 4:
        rk, n = S.ranks((h, a))
        x[1] = (rk[a] - rk[h]) / max(n, 2)
        x[2] = max(-3.0, min(3.0, (th.gf - th.ga) / th.gp - (ta.gf - ta.ga) / ta.gp))
    if th and ta and len(th.last) >= 3 and len(ta.last) >= 3:
        x[3] = (sum(p for p, _ in th.last) / len(th.last) - sum(p for p, _ in ta.last) / len(ta.last)) / 3
    if th and ta and th.h_gp >= 2 and ta.a_gp >= 2:
        x[4] = (th.h_pts / th.h_gp - ta.a_pts / ta.a_gp) / 3
    if len(meet) >= 3:
        wh = sum(1 for m in meet if (m["h"] == h and m["hg"] > m["ag"]) or (m["a"] == h and m["ag"] > m["hg"]))
        wa = sum(1 for m in meet if (m["h"] == a and m["hg"] > m["ag"]) or (m["a"] == a and m["ag"] > m["hg"]))
        x[5] = (wh - wa) / len(meet)
    return x


def feat_ou(h, a, S, meet, pover):
    th, ta = S.t.get(h), S.t.get(a)
    x = [logit(pover), 0.0, 0.0, 0.0, 0.0, 0.0]
    if th and ta and th.h_gp >= 2 and ta.a_gp >= 2:
        x[1] = (th.h_o25 / th.h_gp + ta.a_o25 / ta.a_gp) / 2 - 0.5
    if th and ta and th.gp >= 4 and ta.gp >= 4:
        x[2] = ((th.gf + th.ga) / th.gp + (ta.gf + ta.ga) / ta.gp) / 2 - 2.7
        x[4] = (th.btts / th.gp + ta.btts / ta.gp) / 2 - 0.5
    if th and ta and len(th.last) + len(ta.last) >= 6:
        x[3] = (sum(o for _, o in th.last) + sum(o for _, o in ta.last)) / (len(th.last) + len(ta.last)) - 0.5
    if len(meet) >= 3:
        x[5] = (sum(m["hg"] + m["ag"] for m in meet) / len(meet) - 2.7) / 1.5
    return x


def build_rows(seasons, preds):
    """Feature rows for every finished match that had a model prediction, seen as of its kick-off."""
    rows, meetings = [], {}
    S_ = len(seasons)
    for si, srows in enumerate(seasons):
        S = SeasonState()
        played = [m for m in srows if m["hg"] is not None]
        i = 0
        while i < len(played):
            day = [m for m in played[i:] if m["d"] == played[i]["d"]]
            for m in day:
                p = preds.get(id(m))
                if p is None:
                    continue
                meet = meetings.get(h2h_key(m["h"], m["a"]), [])[-6:]
                res = result_idx(m)
                rows.append({"off": S_ - 1 - si, "fx": feat_x(m["h"], m["a"], S, meet, p[1]), "fo": feat_ou(m["h"], m["a"], S, meet, p[0]),
                             "res": res, "over": m["hg"] + m["ag"] > 2, "px": p[1], "po": p[0],
                             "qx": demargin(m["xc"].get("P") or m["xc"].get("Avg")),
                             "qo": demargin(m["ouc"].get("P") or m["ouc"].get("Avg"))})
            for m in day:
                S.add(m)
                meetings.setdefault(h2h_key(m["h"], m["a"]), []).append(m)
            i += len(day)
    return rows


def fit_logit(X, y, prior=None, lam=1.0, iters=30):
    X = np.column_stack([np.ones(len(X)), np.asarray(X, float)])
    y = np.asarray(y, float)
    d = X.shape[1]
    w0 = np.zeros(d) if prior is None else np.asarray(prior, float)
    w = w0.copy()
    P = lam * np.eye(d)
    if prior is None:
        P[0, 0] = 1e-6
    for _ in range(iters):
        z = np.clip(X @ w, -30, 30)
        p = 1 / (1 + np.exp(-z))
        g = X.T @ (p - y) + P @ (w - w0)
        H = (X.T * (p * (1 - p))) @ X + P
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-7:
            break
    return w


CAL_MIN = 300      # settled matches before the model's over 2.5 chance gets a calibration
CAL_LAM = 20.0     # pull of the calibration towards "no change" (a=0, b=1)


def fit_platt(x, y, lam=CAL_LAM):
    """(a, b) of logit p' = a + b * logit p, fitted by logistic regression, pulled towards (0, 1)."""
    w = fit_logit(list(x), list(y), prior=[0.0, 1.0], lam=lam)
    return float(w[0]), float(w[1])


def calib_params(x, y):
    """Calibration of the model's over 2.5 chance from earlier matches (x = logit of the model's chance, y = over)."""
    if len(x) < CAL_MIN:
        return None
    a, b = fit_platt(x, y)
    return {"a": round(a, 4), "b": round(b, 4), "n": len(x)}


def apply_calib(p, c):
    if not c:
        return p
    z = c["a"] + c["b"] * logit(p)
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))


def sig(w, x):
    z = w[0] + sum(wi * xi for wi, xi in zip(w[1:], x))
    return 1 / (1 + math.exp(-max(-30, min(30, z))))


def learned_probs(W, fx, fo):
    ph, pa, po = sig(W["xh"], fx), sig(W["xa"], fx), sig(W["ou"], fo)
    tot = ph + pa
    if tot > 0.97:
        ph, pa = ph * 0.97 / tot, pa * 0.97 / tot
    return [ph, 1 - ph - pa, pa], po


def fit_set(rows, prior=None, lam=1.0):
    if len(rows) < 150:
        return prior
    X = [r["fx"] for r in rows]
    return {"xh": fit_logit(X, [r["res"] == 0 for r in rows], prior and prior["xh"], lam),
            "xa": fit_logit(X, [r["res"] == 2 for r in rows], prior and prior["xa"], lam),
            "ou": fit_logit([r["fo"] for r in rows], [r["over"] for r in rows], prior and prior["ou"], lam)}


def learned_verdict(px3, po):
    """side and level for 1X2 and over/under 2.5 from the learned probabilities."""
    side_x = 0 if px3[0] >= px3[2] else 2
    p = px3[side_x]
    lx = 2 if p >= LEARN_T["x"][0] else (1 if p >= LEARN_T["x"][1] else 0)
    side_o = 0 if po >= 0.5 else 1
    q = po if side_o == 0 else 1 - po
    lo = 2 if q >= LEARN_T["ou"][0] else (1 if q >= LEARN_T["ou"][1] else 0)
    return (side_x, lx, p), (side_o, lo, q)


def learn_all(ctx):
    """Pooled weights per test season and for live use, then league-tuned weights and the honest test."""
    all_rows = {code: c["rows"] for code, c in ctx.items()}
    offs = (2, 1, 0)
    pooled = {t: fit_set([r for rs in all_rows.values() for r in rs if r["off"] > t]) for t in offs}
    pooled["live"] = fit_set([r for rs in all_rows.values() for r in rs])
    out = {}
    for code, rows in all_rows.items():
        acc = {mk: {lv: [0, 0, 0.0, 0] for lv in ("2", "1")} for mk in ("x", "ou")}
        ll = {k: [0.0, 0] for k in ("x_model", "x_learn", "x_close", "ou_model", "ou_learn", "ou_close")}
        for t in offs:
            if not pooled[t]:
                continue
            W = fit_set([r for r in rows if r["off"] > t], pooled[t], lam=40.0) or pooled[t]
            for r in rows:
                if r["off"] != t:
                    continue
                px3, po = learned_probs(W, r["fx"], r["fo"])
                (sx, lx, _), (so, lo, _) = learned_verdict(px3, po)
                for mk, side, lv, hit, q in (("x", sx, lx, sx == r["res"], r["qx"]), ("ou", so, lo, (so == 0) == r["over"], r["qo"])):
                    if lv:
                        a = acc[mk][str(lv)]
                        a[0] += 1; a[1] += hit
                        if q:
                            a[2] += q[side]; a[3] += 1
                if r["qx"]:
                    ll["x_model"][0] += ll_x(r["px"], r["res"]); ll["x_learn"][0] += ll_x(px3, r["res"]); ll["x_close"][0] += ll_x(r["qx"], r["res"])
                    for k in ("x_model", "x_learn", "x_close"):
                        ll[k][1] += 1
                if r["qo"]:
                    ll["ou_model"][0] += ll_ou(r["po"], r["over"]); ll["ou_learn"][0] += ll_ou(po, r["over"]); ll["ou_close"][0] += ll_ou(r["qo"][0], r["over"])
                    for k in ("ou_model", "ou_learn", "ou_close"):
                        ll[k][1] += 1
        live = fit_set(rows, pooled["live"], lam=40.0) or pooled["live"]
        out[code] = {
            "w": live,
            "test": {mk: {lv: {"n": a[0], "hit": r4(a[1] / a[0]) if a[0] else None, "mkt": r4(a[2] / a[3]) if a[3] else None}
                          for lv, a in d.items()} for mk, d in acc.items()},
            "ll": {k: r4(v[0] / v[1]) if v[1] else None for k, v in ll.items()},
        }
    return out, pooled["live"]


def apply_learned(stats, W, fx, fo):
    """Replace the vote-based verdict with the learned one; keep the factor list as the explanation."""
    px3, po = learned_probs(W, fx, fo)
    (sx, lx, p_x), (so, lo, p_o) = learned_verdict(px3, po)
    keys = {"x": X_KEYS, "ou": O_KEYS}
    for mk, side, lv, p, feats in (("x", sx, lx, p_x, fx), ("ou", so, lo, p_o, fo)):
        v = stats[mk]
        w = W["xh"] if (mk == "x" and side == 0) else W["xa"] if mk == "x" else W["ou"]
        sign = -1 if (mk == "ou" and side == 1) else 1
        contrib = {k: sign * float(w[i + 1]) * feats[i] for i, k in enumerate(keys[mk])}
        lean = ("h" if side == 0 else "a") if mk == "x" else ("o" if side == 0 else "u")
        other = {"h": "a", "a": "h", "o": "u", "u": "o"}[lean]
        for f in v["f"]:
            f["c"] = round(contrib.get(f["k"], 0.0), 3)
        v.update({"side": side, "level": lv, "p": r4(p),
                  "agree": sum(1 for f in v["f"] if f["l"] == lean), "against": sum(1 for f in v["f"] if f["l"] == other)})
    stats["px"] = [r4(x) for x in px3]
    stats["po"] = r4(po)
    return stats


# ---------------------------------------------------------------- injuries and suspensions (Premier League, Fantasy Premier League)

FPL_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_POS = {1: "BR", 2: "OBR", 3: "POM", 4: "NAP"}


def fpl_absences(fpl, known):
    """Per football-data team name: players who are injured, doubtful or suspended, with how much they matter."""
    if not fpl or not fpl.get("elements"):
        return {}
    teams = {}
    for t in fpl.get("teams", []):
        fd = best_team(t.get("name", ""), known) or best_team(t.get("short_name", ""), known)
        if fd:
            teams[t["id"]] = fd
    by_team = {}
    for p in fpl["elements"]:
        by_team.setdefault(p.get("team"), []).append(p)
    out = {}
    for tid, players in by_team.items():
        fd = teams.get(tid)
        if not fd:
            continue
        games = max((p.get("starts") or 0) for p in players) or 0
        fx = lambda p: float(p.get("expected_goal_involvements") or 0)
        team_xgi = sum(fx(p) for p in players) or 0.0
        rows = []
        for p in players:
            stt, ch = p.get("status"), p.get("chance_of_playing_next_round")
            if stt in ("u", "n"):  # left the club or not eligible
                continue
            if stt == "a" and (ch is None or ch >= 100):
                continue
            starts, minutes = p.get("starts") or 0, p.get("minutes") or 0
            if starts == 0 and minutes < 180:  # fringe players do not change a match
                continue
            share = starts / games if games else 0.0
            xgi = fx(p) / team_xgi if team_xgi else 0.0
            rows.append({"n": p.get("web_name"), "pos": FPL_POS.get(p.get("element_type"), ""), "st": stt, "ch": ch,
                         "news": (p.get("news") or "")[:120], "starts": starts, "of": games, "xgi": round(xgi, 3),
                         "key": share >= 0.6 or xgi >= 0.15})
        rows.sort(key=lambda r: (not r["key"], -r["starts"]))
        out[fd] = rows
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
    "manchester united": "Man United", "manchester city": "Man City", "man utd": "Man United", "spurs": "Tottenham",
    "tottenham hotspur": "Tottenham", "nottm forest": "Nott'm Forest",
    "brighton hove": "Brighton", "wolverhampton": "Wolves", "nottingham forest": "Nott'm Forest",
    "sheffield wednesday": "Sheffield Weds", "sheffield united": "Sheffield United", "queens park rangers": "QPR",
    "west bromwich": "West Brom", "west bromwich albion": "West Brom", "peterborough united": "Peterboro",
    "peterborough": "Peterboro", "dundee fc": "Dundee", "dundee": "Dundee", "dundee united": "Dundee United",
    "stade lavallois": "Laval", "vitoria sc": "Guimaraes", "basaksehir": "Buyuksehyr", "istanbul basaksehir": "Buyuksehyr",
    "erzurum bb": "Erzurumspor", "estudiantes": "Estudiantes L.P.", "estudiantes la plata": "Estudiantes L.P.",
    "gimnasia la plata": "Gimnasia L.P.", "independiente rivadavia": "Ind. Rivadavia", "austria lustenau": "A. Lustenau",
    "austria wien": "Austria Vienna", "atletico mineiro": "Atletico-MG", "atletico paranaense": "Athletico-PR",
    "athletico paranaense": "Athletico-PR", "henan fc": "Henan Songshan Longmen", "henan": "Henan Songshan Longmen",
    "shanghai sipg": "Shanghai Port", "shanghai sipg fc": "Shanghai Port", "shenzhen peng city": "Shenzhen Xinpengcheng",
    "shenzhen peng city fc": "Shenzhen Xinpengcheng", "tokyo verdy": "Verdy", "zaglebie lubin": "Zaglebie",
    "akron tolyatti": "Akron Togliatti", "fc akron tolyatti": "Akron Togliatti", "dinamo moscow": "Dynamo Moscow",
    "d c united": "DC United", "dc united": "DC United", "la galaxy": "Los Angeles Galaxy",
    "atletico madrid": "Ath Madrid", "atletico": "Ath Madrid", "athletic bilbao": "Ath Bilbao", "athletic": "Ath Bilbao",
    "real betis": "Betis", "celta vigo": "Celta", "rayo vallecano": "Vallecano", "real sociedad": "Sociedad",
    "espanyol": "Espanol", "deportivo la coruna": "La Coruna", "racing santander": "Santander",
    "real oviedo": "Oviedo", "celta fortuna": "Celta B", "real valladolid": "Valladolid", "sporting gijon": "Sp Gijon", "deportivo alaves": "Alaves",
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
    "sint truiden": "St Truiden", "sint truidense": "St Truiden", "sint truidense vv": "St Truiden", "stvv": "St Truiden",
    "olympiacos": "Olympiakos", "olympiacos piraeus": "Olympiakos", "paok": "PAOK", "aek athens": "AEK",
    "fenerbahce": "Fenerbahce", "galatasaray": "Galatasaray", "besiktas": "Besiktas",
}


SPECIAL = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "ß": "ss", "đ": "d", "Đ": "D", "ı": "i"})


def ascii_low(s):
    s = unicodedata.normalize("NFKD", s.translate(SPECIAL)).encode("ascii", "ignore").decode().lower().replace("'", "")
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
    exact = [k for k in known if ascii_low(k) == ascii_low(raw)]
    if len(exact) == 1:
        return exact[0]
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

    def refresh(self, sports_by_div, kickoffs_by_div, reserve=0):
        """kickoffs_by_div: known upcoming kick-off datetimes (UTC) per league, to aim the paid calls.
        reserve: credits kept for the NBA odds for the rest of the month."""
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
        allowance = 12 if remaining is None else max(0, int((remaining - 10 - reserve) / days_left))
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


def light_fixture(f):
    """What the match list needs; prices, factors and score grids stay in the league detail file."""
    st = f.get("stats") or {}
    lite = {mk: {k: st[mk][k] for k in ("side", "level", "p", "agree", "against", "n") if k in st[mk]} for mk in ("x", "ou") if mk in st}
    if "px" in st:
        lite["px"], lite["po"] = st["px"], st["po"]
    extra = {}
    if f.get("absences") is not None:
        extra["abs"] = [sum(1 for r in f["absences"][side] if r["key"] and (r["ch"] is None or r["ch"] <= 50)) for side in ("home", "away")]
    return {k: f[k] for k in ("id", "date", "time", "ko", "home", "away", "xg", "x12", "over", "final", "tips", "best")} | {"stats": lite} | extra


def merge_events(fx, events, known, unmatched, names=None):
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
            if names is not None:
                names[m["h"]], names[m["a"]] = ev["home"], ev["away"]
            continue
        h, a = best_team(ev["home"], known), best_team(ev["away"], known)
        if not h or not a or h == a:
            unmatched.extend(n for n, x in ((ev["home"], h), (ev["away"], a)) if not x)
            continue
        if names is not None:
            names[h], names[a] = ev["home"], ev["away"]
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
            e["close_odds"] = close_rows[bk][i]
        elif e.get("last_odds"):
            e["close_odds"] = e["last_odds"]
        elif close_rows.get("Avg"):
            e["close_odds"] = close_rows["Avg"][i]
        fair_close = demargin(close_rows.get("P") or close_rows.get("Avg"))
        if fair_close:  # beat the close: our price against the fair closing price (Pinnacle without margin)
            e["clv"] = round(e["odds"] * fair_close[i] - 1, 4)


def summarize(entries):
    settled = [e for e in entries if e["status"] in ("won", "lost")]
    n = len(settled)
    profit = sum(e["profit"] for e in settled)
    clv = [e["clv"] if "clv" in e else e["odds"] / e["close_odds"] - 1 for e in settled if "clv" in e or e.get("close_odds")]
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
                      "xg": f["xg"], "sv": [f["stats"]["x"]["side"], f["stats"]["x"]["level"], f["stats"]["ou"]["side"], f["stats"]["ou"]["level"]]}
    today = now.date()
    for mid, p in list(P.items()):
        if p["l"] != code or "score" in p:
            continue
        m = find_result(results, p["date"], p["home"], p["away"])
        if m:
            p["score"] = [m["hg"], m["ag"]]
        elif dt.date.fromisoformat(p["date"]) < today - dt.timedelta(days=21):
            del P[mid]  # never settled (postponed or result missing): nothing to score


RECENT_DAYS = 120  # predictions.json keeps this many days; older settled ones go to the archive
ARCHIVE_DIR = "archiwum"


def load_archive(outdir):
    """All archived predictions (gole/archiwum/<YYYY-MM>.json), one dict keyed by match id."""
    allp, adir = {}, os.path.join(outdir, ARCHIVE_DIR)
    if os.path.isdir(adir):
        for fn in sorted(os.listdir(adir)):
            if re.fullmatch(r"\d{4}-\d{2}\.json", fn):
                allp.update(load_json(os.path.join(adir, fn), {}).get("matches", {}))
    return allp


def archive_predictions(preds, outdir, today):
    """Settled predictions older than RECENT_DAYS move to the month's archive file, which is kept for good.
    The page loads only the light recent file; the archive feeds the season-by-season report."""
    cutoff = (today - dt.timedelta(days=RECENT_DAYS)).isoformat()
    P = preds.get("matches", {})
    by_month = {}
    for mid in [k for k, p in P.items() if p["date"] < cutoff]:
        p = P.pop(mid)
        if "score" in p:
            by_month.setdefault(p["date"][:7], {})[mid] = p
    if not by_month:
        return 0
    adir = os.path.join(outdir, ARCHIVE_DIR)
    os.makedirs(adir, exist_ok=True)
    for month, rows in by_month.items():
        path = os.path.join(adir, f"{month}.json")
        A = load_json(path, {})
        A.setdefault("matches", {}).update(rows)
        A["matches"] = dict(sorted(A["matches"].items()))
        json.dump(A, open(path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return sum(len(r) for r in by_month.values())


def season_label(day):
    """'2026/27' for July 2026 to June 2027 (European calendar, also used for summer leagues)."""
    y, m = int(day[:4]), int(day[5:7])
    s = y if m >= 7 else y - 1
    return f"{s}/{(s + 1) % 100:02d}"


def prediction_report(matches, codes):
    """Scores of every finished prediction since logging began (recent + archive): model vs market vs final,
    how the statistics' ratings hit, calibration of over 2.5, and the same split season by season."""
    out = {}
    done = [p for p in matches.values() if "score" in p]
    for code in codes + ["ALL"]:
        rows = [p for p in done if code == "ALL" or p["l"] == code]
        acc = score_predictions(rows)
        if rows:
            acc["since"] = min(p["date"] for p in rows)
            seasons = {}
            for p in rows:
                seasons.setdefault(season_label(p["date"]), []).append(p)
            acc["seasons"] = {}
            for lab, rs in sorted(seasons.items(), reverse=True):
                a = score_predictions(rs)
                acc["seasons"][lab] = {"n": a["n"], "x": [a["x"]["n"], a["x"]["won"]], "ou": [a["ou"]["n"], a["ou"]["won"]], "sv": a["sv"]}
        if code == "ALL":
            bins = [[0, 0] for _ in range(10)]
            for p in rows:
                q = p["f_ou"] if p["f_ou"] is not None else p["m_ou"]
                b = min(9, int(q * 10))
                bins[b][0] += 1; bins[b][1] += sum(p["score"]) > 2
            acc["calib_ou"] = bins
        out[code] = acc
    return out


def score_predictions(rows):
    """Log-loss and hit rate of model, market and final blend, plus hits of the statistics' ratings."""
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
                   "ll_final": r4(sc["f"] / n) if n else None, "hit": r4(sc["hit"] / n) if n else None, "won": sc["hit"]}
    sv = {mk: {"2": [0, 0], "1": [0, 0]} for mk in ("x", "ou")}
    for p in rows:
        if not p.get("sv"):
            continue
        hg, ag = p["score"]
        xs, xl, os_, ol = p["sv"]
        if xl:
            sv["x"][str(xl)][0] += 1; sv["x"][str(xl)][1] += xs == (0 if hg > ag else (1 if hg == ag else 2))
        if ol:
            sv["ou"][str(ol)][0] += 1; sv["ou"][str(ol)][1] += (os_ == 0) == (hg + ag > 2)
    acc["sv"] = sv
    return acc


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
    # the agent and its NBA data (results from ESPN, prices from the same odds budget)
    ag, nba_ctx = None, None
    try:
        ag = AG.Agent(outdir, now)
    except Exception as e:
        print("agent: start failed:", e)
    if ag and not fixtures_from_results and not src.local and not only:
        ag.elo = ZR.ClubElo(src.cache_dir or os.path.join(outdir, ".cache"), now)
        try:
            nba_ctx = NBA.prepare(src.cache_dir or os.path.join(outdir, ".cache"), now, oa)
        except Exception as e:
            ag.errors.append(f"NBA: {str(e)[:160]}")
    oa.refresh(sports, kickoffs, reserve=NBA.reserve(now) if nba_ctx else 0)

    out = {"version": VERSION, "generated": now_iso, "today": today.isoformat(), "edge_min": EDGE_MIN,
           "market_edge_min": MARKET_EDGE_MIN, "leagues": []}
    unmatched = []
    names = load_json(os.path.join(outdir, "names.json"), {})
    # 3) per league: merge bookmaker events, walk-forward test, current table and form, rows for learning
    ctx = {}
    for code, name, country, sport, extra, cname in leagues:
        if code not in data:
            continue
        seasons, fx = data[code]["seasons"], data[code]["fx"]
        cur = seasons[-1]
        played = [m for m in cur if m["hg"] is not None]
        use_sot = not extra and sum(1 for m in played[-60:] if m["hst"] is not None) > 20
        known = set().union(*(teams_of(s) for s in seasons[-2:] if s)) | teams_of(fx)
        if sport and not fixtures_from_results:
            fx = merge_events(fx, oa.events(code), known, unmatched, names.setdefault(code, {}))
        ev = evaluate_league(seasons, extra, use_sot)
        prm = ev["params"]
        _, r = run_rater(seasons, prm["half_life"], prm["prior"], SOT_W if use_sot else 0.0, upto=today)
        S = SeasonState()
        for m in sorted(played, key=lambda m: m["d"]):
            S.add(m)
        meetings = {}
        for srows in seasons:
            for m in srows:
                if m["hg"] is not None:
                    meetings.setdefault(h2h_key(m["h"], m["a"]), []).append(m)
        ctx[code] = {"seasons": seasons, "fx": fx, "played": played, "use_sot": use_sot, "ev": ev, "r": r, "S": S,
                     "meetings": meetings, "rows": build_rows(seasons, ev.pop("_preds"))}
    # injuries and suspensions for the Premier League (information only, not part of the tested verdict)
    absences = {}
    if "E0" in ctx:
        known_e0 = teams_of(ctx["E0"]["seasons"][-1]) | teams_of(ctx["E0"]["fx"])
        absences = fpl_absences(src.fpl(), known_e0)
    # 4) learn how much each statistic matters, on all leagues together and then per league
    learned, pooled_w = learn_all(ctx) if ctx else ({}, None)
    details = {}
    for code, name, country, sport, extra, cname in leagues:
        if code not in ctx:
            continue
        c = ctx[code]
        seasons, fx, played, ev, r, S, meetings = c["seasons"], c["fx"], c["played"], c["ev"], c["r"], c["S"], c["meetings"]
        cur = seasons[-1]
        prm = ev["params"]
        prev = teams_of(seasons[-2]) if len(seasons) > 1 else None
        live = live_grade(journal, code)
        grades = {"ou": final_grade(ev["grade"]["ou"], live["ou"]), "x": final_grade(ev["grade"]["x"], live["x"])}
        W = (learned.get(code) or {}).get("w") or pooled_w
        # 5) price the fixtures and judge them with the learned statistics
        priced = []
        for m in sorted(fx, key=lambda m: (m["d"], m.get("t") or "")):
            if m["h"] == m["a"]:
                continue
            f = price_fixture(m, r, prev, prm, extra, code, now)
            if dt.datetime.fromisoformat(f["ko"]) > now - dt.timedelta(hours=2):  # hide matches already played
                meet = meetings.get(h2h_key(m["h"], m["a"]), [])
                f["stats"] = stats_verdict(m["h"], m["a"], S, meet, f["x12"], f["over"]["2.5"])
                if W:
                    apply_learned(f["stats"], W, feat_x(m["h"], m["a"], S, meet[-6:], f["x12"]), feat_ou(m["h"], m["a"], S, meet[-6:], f["over"]["2.5"]))
                if code == "E0" and absences:
                    f["absences"] = {"home": absences.get(m["h"], []), "away": absences.get(m["a"], [])}
                priced.append(f)
        update_journal(journal, code, f"{country} · {name}", priced, played, now, grades)
        if ag and code in AG.LEAGUES:
            try:
                ag.football(code, f"{country} · {name}", priced, played, teams=sorted(teams_of(cur) | teams_of(fx)),
                            elo_backup=ZR.results_elo(seasons))
            except Exception as e:  # the agent must never stop the app
                ag.errors.append(f"{code}: {str(e)[:160]}")
        update_predictions(preds_log, code, priced, played, now)
        last = max((m["d"] for m in played), default=None)
        H, A, _ = r.base()
        lt = learned.get(code) or {}
        details[code] = {"teams": {t: team_stats(played, t, r, today, prev) for t in sorted(teams_of(cur) | teams_of(fx))},
                         "fixtures": {f["id"]: f for f in priced}}
        out["leagues"].append({
            "code": code, "name": name, "country": country, "extra": extra, "odds_feed": bool(sport),
            "played": len(played), "last_result": last.isoformat() if last else None,
            "goals_pg": round(sum(m["hg"] + m["ag"] for m in played) / len(played), 2) if played else None,
            "o25_rate": round(sum(1 for m in played if m["hg"] + m["ag"] > 2) / len(played), 3) if played else None,
            "home_rate": round(sum(1 for m in played if m["hg"] > m["ag"]) / len(played), 3) if played else None,
            "avg": [round(H, 2), round(A, 2)], "shots": use_sot,
            "params": prm, "test": {k: ev[k] for k in ("tested_seasons", "matches", "ou", "x")},
            "stats_test": lt.get("test"), "learn_ll": lt.get("ll"),
            "weights": {k: [round(float(x), 3) for x in v] for k, v in W.items()} if W else None,
            "grade_test": ev["grade"], "grade": grades, "live": live,
            "names": {k: v for k, v in names.get(code, {}).items() if k in details[code]["teams"]},
            "fixtures": [light_fixture(f) for f in priced],
        })
    agent_summary = None
    if ag:
        try:
            if nba_ctx:
                ag.nba(nba_ctx)
        except Exception as e:
            ag.errors.append(f"NBA agent: {str(e)[:160]}")
        try:
            sources = {
                "football_data": {"errors": src.errors[:5], "leagues": len(data), "downloads": src.downloads,
                                  "stale": src.stale[:8], "n_stale": len(src.stale)},
                "odds": {"remaining": oa.c.get("remaining"), "leagues": sorted(d for d, s in oa.c["sports"].items() if s.get("odds") and d in AG.LEAGUES),
                         "errors": (oa.status.get("errors") or [])[:3]},
                "fpl": {"teams": len(absences), "players": sum(len(v) for v in absences.values())},
                "clubelo": ag.elo.status() if ag.elo is not None else None,
                "espn": {k: nba_ctx["status"].get(k) for k in ("games", "injuries", "errors", "stale")} if nba_ctx else None,
            }
            agent_summary = ag.finish({"nba": nba_ctx["status"] if nba_ctx else None, "odds_remaining": oa.c.get("remaining"),
                                       "sources": sources})
        except Exception as e:
            print("agent: save failed:", e)
    oa.save()
    out["bookmakers"] = dict(oa.status, remaining=oa.c.get("remaining"),
                             leagues_with_prices=sorted(d for d, s in oa.c["sports"].items() if s.get("odds")),
                             unmatched=sorted(set(unmatched))[:40])
    journal["summary"] = journal_summary(journal)
    journal["updated"] = now_iso
    out["journal_summary"] = journal["summary"]
    archived = load_archive(outdir)
    out["report"] = prediction_report({**archived, **preds_log.get("matches", {})}, [L["code"] for L in out["leagues"]])
    out["errors"] = src.errors
    out["runtime_s"] = round(time.time() - t0, 1)
    out["downloads"] = src.downloads
    out["_agent"] = agent_summary
    if not out["leagues"]:  # source down: keep the last good data instead of publishing an empty page
        raise SystemExit("no leagues built: " + "; ".join(src.errors[:3]))
    os.makedirs(outdir, exist_ok=True)
    dpath = os.path.join(outdir, "data.json")
    old = load_json(dpath, None)
    agent_summary = out.pop("_agent", None)
    strip = lambda o: {k: v for k, v in o.items() if k not in ("generated", "runtime_s", "downloads")}
    if old and strip(old) == strip(out):  # nothing changed: keep the timestamp, so no commit is made
        out["generated"] = old.get("generated", out["generated"])
    oldj = load_json(os.path.join(outdir, "journal.json"), {})
    if oldj.get("entries") == journal.get("entries"):
        journal["updated"] = oldj.get("updated", journal["updated"])
    json.dump(out, open(dpath, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    os.makedirs(os.path.join(outdir, "liga"), exist_ok=True)
    for code, det in details.items():  # details load only when a match or a league is opened
        json.dump(det, open(os.path.join(outdir, "liga", f"{code}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(names, open(os.path.join(outdir, "names.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)
    json.dump(journal, open(os.path.join(outdir, "journal.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    archive_predictions(preds_log, outdir, today)  # older settled predictions are kept for good in gole/archiwum
    json.dump(preds_log, open(os.path.join(outdir, "predictions.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    out["agent"] = agent_summary
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
    a = o.get("agent")
    if a:
        print("agent: portfel", a["equity"], "otwarte", a["n_open"], "rozliczone", a["stats"]["all"]["bets"],
              "przeanalizowane", a["analysed"])
    print("runtime", o["runtime_s"], "s, downloads", o["downloads"])
    if o["errors"]:
        print("errors:", *o["errors"][:30], sep="\n  ")
