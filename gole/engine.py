#!/usr/bin/env python3
"""Linia Goli v2: fetch results + odds from football-data.co.uk, rate teams, price
over/under 2.5, keep a paper-trading journal and an honest backtest.

Runs unattended in GitHub Actions. Writes gole/data.json and gole/journal.json.
Usage:
  python engine.py                       # live run (downloads from football-data.co.uk)
  python engine.py --local DIR --today YYYY-MM-DD [--fixtures-from-results]
      # offline test against a mirror laid out as DIR/data/<league>/season-XXYY.csv
"""
import argparse, csv, difflib, io, json, math, os, re, sys, unicodedata, urllib.request, datetime as dt
from zoneinfo import ZoneInfo

LEAGUES = [  # code, mirror folder, display name, country
    ("E0", "premier-league", "Premier League", "Anglia"),
    ("SP1", "la-liga", "LaLiga", "Hiszpania"),
    ("I1", "serie-a", "Serie A", "Włochy"),
    ("D1", "bundesliga", "Bundesliga", "Niemcy"),
    ("F1", "ligue-1", "Ligue 1", "Francja"),
]
BASE = "https://www.football-data.co.uk"

# Model parameters (chosen on the 2023/24-2025/26 backtest, see tune.py)
P = {
    "half_life": 250.0,   # days, time decay of old matches
    "prior": 20.0,        # pseudo-matches pulling each team to the league average
    "sot_w": 0.5,         # weight of shots-on-target-based expected goals vs real goals
    "rho": -0.08,         # Dixon-Coles low-score correction
    "promoted": (0.82, 1.18),
}
EDGE_MIN = 0.05           # model strategy: paper bet when model_prob * odds - 1 > 5%
MARKET_EDGE_MIN = 0.02    # market strategy: a bookmaker's price beats the fair market price by > 2%
MIN_BOOKS_FAIR = 3        # need this many UK bookmakers to build a fair price without Pinnacle
MAXG = 10


# ---------------------------------------------------------------- data

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
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


ODDS_KEYS = ["B365", "P", "Max", "Avg"]


def parse_rows(text, div=None):
    rows = []
    rdr = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    for r in rdr:
        if div and r.get("Div") and r["Div"] != div:
            continue
        if not r.get("HomeTeam") or not r.get("Date"):
            continue
        d = parse_date(r["Date"])
        if not d:
            continue
        def gi(k):
            try:
                return int(r.get(k, ""))
            except ValueError:
                return None
        rows.append({
            "div": r.get("Div", div), "d": d, "t": (r.get("Time") or "").strip(),
            "h": r["HomeTeam"].strip(), "a": r["AwayTeam"].strip(),
            "hg": gi("FTHG"), "ag": gi("FTAG"), "hst": gi("HST"), "ast": gi("AST"),
            "odds": {k: [fnum(r.get(k + ">2.5")), fnum(r.get(k + "<2.5"))] for k in ODDS_KEYS},
            "close": {k: [fnum(r.get(k + "C>2.5")), fnum(r.get(k + "C<2.5"))] for k in ODDS_KEYS},
        })
    return rows


class Source:
    def __init__(self, local=None):
        self.local = local
        self.errors = []

    def _get(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": "linia-goli/2 (+github actions)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8-sig", errors="replace")

    def season(self, code, folder, year):
        sc = season_code(year)
        try:
            if self.local:
                p = os.path.join(self.local, "data", folder, f"season-{sc}.csv")
                if not os.path.exists(p):
                    return []
                return parse_rows(open(p, encoding="utf-8-sig", errors="replace").read(), code)
            return parse_rows(self._get(f"{BASE}/mmz4281/{sc}/{code}.csv"), code)
        except Exception as e:
            self.errors.append(f"{code} {sc}: {e}")
            return []

    def fixtures(self):
        if self.local:
            return None
        try:
            return parse_rows(self._get(f"{BASE}/fixtures.csv"))
        except Exception as e:
            self.errors.append(f"fixtures: {e}")
            return []


# ---------------------------------------------------------------- model

def pois(k, lam):
    return math.exp(-lam) * lam ** k / math.factorial(k)


def score_matrix(lh, la, rho):
    ph = [pois(i, lh) for i in range(MAXG + 1)]
    pa = [pois(j, la) for j in range(MAXG + 1)]
    M = [[ph[i] * pa[j] for j in range(MAXG + 1)] for i in range(MAXG + 1)]
    if rho:
        M[0][0] *= max(0.0, 1 - lh * la * rho)
        M[0][1] *= max(0.0, 1 + lh * rho)
        M[1][0] *= max(0.0, 1 + la * rho)
        M[1][1] *= max(0.0, 1 - rho)
    s = sum(map(sum, M))
    return [[v / s for v in row] for row in M]


def markets(lh, la, rho):
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


class Model:
    """Team attack/defence ratings from matches strictly before `asof`."""

    def __init__(self, hist, asof, prev_teams, p=P):
        self.p = p
        rows, sw = [], 0.0
        sh = sa = sg = ss = 0.0
        for m in hist:
            if m["d"] >= asof or m["hg"] is None:
                continue
            w = 0.5 ** ((asof - m["d"]).days / p["half_life"])
            rows.append((m, w))
            sw += w
            sh += w * m["hg"]; sa += w * m["ag"]
            if m["hst"] is not None and m["ast"] is not None:
                sg += w * (m["hg"] + m["ag"]); ss += w * (m["hst"] + m["ast"])
        self.ok = sw > 20
        self.H = sh / sw if sw else 1.5
        self.A = sa / sw if sw else 1.2
        conv = sg / ss if ss else 0.3
        sw_ = p["sot_w"]
        acc = {}
        for m, w in rows:
            def g(goals, sot):
                return goals if sot is None else (1 - sw_) * goals + sw_ * sot * conv
            hg, ag = g(m["hg"], m["hst"]), g(m["ag"], m["ast"])
            for team, gf, ga, ef, ea in ((m["h"], hg, ag, self.H, self.A), (m["a"], ag, hg, self.A, self.H)):
                a = acc.setdefault(team, [0.0, 0.0, 0.0, 0.0])
                a[0] += w * gf; a[1] += w * ef; a[2] += w * ga; a[3] += w * ea
        self.prev_teams = prev_teams
        k = p["prior"] * (self.H + self.A) / 2
        self.att, self.dfn = {}, {}
        for team, (gf, ef, ga, ea) in acc.items():
            pa, pd = self._prior(team)
            self.att[team] = (gf + k * pa) / (ef + k)
            self.dfn[team] = (ga + k * pd) / (ea + k)

    def _prior(self, team):
        if self.prev_teams is not None and team not in self.prev_teams:
            return self.p["promoted"]
        return (1.0, 1.0)

    def rating(self, team):
        if team in self.att:
            return self.att[team], self.dfn[team]
        return self._prior(team)

    def lambdas(self, h, a):
        ah, dh = self.rating(h)
        aa, da = self.rating(a)
        return self.H * ah * da, self.A * aa * dh

    def over25(self, h, a):
        lh, la = self.lambdas(h, a)
        return markets(lh, la, self.p["rho"])["over"]["2.5"]


def teams_of(rows):
    return {m["h"] for m in rows} | {m["a"] for m in rows}


# ---------------------------------------------------------------- betting maths

def best_bet(p_over, odds):
    """Return (side, prob, odds, edge) for the better side, using one odds pair."""
    o, u = odds
    cands = []
    if o:
        cands.append(("Over", p_over, o, p_over * o - 1))
    if u:
        cands.append(("Under", 1 - p_over, u, (1 - p_over) * u - 1))
    return max(cands, key=lambda c: c[3]) if cands else None


def market_prob(odds):
    o, u = odds
    if not o or not u:
        return None
    return (1 / o) / (1 / o + 1 / u)


def backtest(seasons_rows, test_from_idx, p=P, books=("B365", "Max")):
    """seasons_rows: list of season row-lists, oldest first. Predict every match in
    seasons[test_from_idx:] using only earlier data, bet when edge > EDGE_MIN."""
    allm = [m for rows in seasons_rows for m in rows if m["hg"] is not None]
    res = {b: {"n": 0, "profit": 0.0} for b in books}
    mkt = {k: {"n": 0, "profit": 0.0} for k in ("best", "one")}
    mkt_seasons = []
    ll_mod = ll_mkt = n_ll = 0
    cache = {}
    per_season = []
    for si in range(test_from_idx, len(seasons_rows)):
        prev = teams_of(seasons_rows[si - 1]) if si > 0 else None
        s = {b: {"n": 0, "profit": 0.0} for b in books}
        ms = {k: {"n": 0, "profit": 0.0} for k in mkt}
        for m in seasons_rows[si]:
            if m["hg"] is None:
                continue
            q0 = market_prob(m["odds"]["P"])
            if q0:
                y0 = m["hg"] + m["ag"] > 2
                for k, b in (("best", "Max"), ("one", "B365")):
                    bb = best_bet(q0, m["odds"][b])
                    if bb and bb[3] > MARKET_EDGE_MIN:
                        pr = bb[2] - 1 if (bb[0] == "Over") == y0 else -1.0
                        for acc in (mkt[k], ms[k]):
                            acc["n"] += 1; acc["profit"] += pr
            if m["d"] not in cache:
                cache[m["d"]] = Model(allm, m["d"], prev, p)
            mod = cache[m["d"]]
            if not mod.ok:
                continue
            po = mod.over25(m["h"], m["a"])
            y = m["hg"] + m["ag"] > 2
            q = market_prob(m["close"]["P"]) or market_prob(m["close"]["Avg"])
            if q:
                n_ll += 1
                ll_mkt -= math.log(q if y else 1 - q)
                ll_mod -= math.log(po if y else 1 - po)
            for b in books:
                bb = best_bet(po, m["odds"][b])
                if bb and bb[3] > EDGE_MIN:
                    win = (bb[0] == "Over") == y
                    pr = bb[2] - 1 if win else -1.0
                    for acc in (res[b], s[b]):
                        acc["n"] += 1; acc["profit"] += pr
        per_season.append(s)
        mkt_seasons.append(ms)
    out = {"matches": n_ll,
           "logloss_model": round(ll_mod / n_ll, 4) if n_ll else None,
           "logloss_market": round(ll_mkt / n_ll, 4) if n_ll else None, "books": {}}
    for b in books:
        r = res[b]
        out["books"][b] = {"bets": r["n"], "roi": round(r["profit"] / r["n"], 4) if r["n"] else None,
                           "seasons": [round(x[b]["profit"] / x[b]["n"], 4) if x[b]["n"] else None for x in per_season]}
    out["market"] = {k: {"bets": r["n"], "roi": round(r["profit"] / r["n"], 4) if r["n"] else None,
                         "seasons": [round(x[k]["profit"] / x[k]["n"], 4) if x[k]["n"] else None for x in mkt_seasons]}
                     for k, r in mkt.items()}
    return out


# ---------------------------------------------------------------- team stats for the UI

def team_stats(played, team, mod):
    ms = sorted((m for m in played if m["h"] == team or m["a"] == team), key=lambda m: m["d"])
    def side(m):
        home = m["h"] == team
        return home, (m["hg"] if home else m["ag"]), (m["ag"] if home else m["hg"])
    homes = [m for m in ms if m["h"] == team]
    aways = [m for m in ms if m["a"] == team]
    form = []
    for m in ms[-6:]:
        home, f, a = side(m)
        form.append({"date": m["d"].isoformat(), "opp": m["a"] if home else m["h"], "home": home,
                     "gf": f, "ga": a, "res": "W" if f > a else ("D" if f == a else "L")})
    att, dfn = mod.rating(team)
    return {
        "gp": len(ms), "gf": sum(side(m)[1] for m in ms), "ga": sum(side(m)[2] for m in ms),
        "o25": sum(1 for m in ms if m["hg"] + m["ag"] > 2), "btts": sum(1 for m in ms if m["hg"] and m["ag"]),
        "o25h": [sum(1 for m in homes if m["hg"] + m["ag"] > 2), len(homes)],
        "o25a": [sum(1 for m in aways if m["hg"] + m["ag"] > 2), len(aways)],
        "att": round(att, 2), "def": round(dfn, 2), "form": form,
    }


# ---------------------------------------------------------------- journal

def match_id(code, m):
    return f"{code}|{m['d'].isoformat()}|{m['h']}|{m['a']}"


def update_journal(journal, code, name, fixtures_priced, results, now_iso, today=None):
    """Add new paper bets for priced fixtures, settle open ones from results."""
    entries = journal.setdefault("entries", [])
    known = {e["id"] for e in entries}
    for f in fixtures_priced:
        for strategy, b in (("model", f.get("bet")), ("market", f.get("mbet"))):
            eid = f["id"] + "|" + strategy
            if not b or eid in known:
                continue
            entries.append({"id": eid, "match": f["id"], "strategy": strategy, "league": code, "league_name": name,
                            "date": f["date"], "time": f["time"], "home": f["home"], "away": f["away"],
                            "side": b["side"], "prob": b["prob"], "odds": b["odds"], "book": b["book"],
                            "edge": b["edge"], "added": now_iso, "status": "open"})
            known.add(eid)
    res_by_id = {match_id(code, m): m for m in results if m["hg"] is not None}
    for e in entries:
        if e["league"] != code or e["status"] != "open":
            continue
        m = res_by_id.get(e.get("match", e["id"]))
        if not m:
            # postponed or never reported: void after three weeks, stake returned
            if today and dt.date.fromisoformat(e["date"]) < today - dt.timedelta(days=21):
                e.update({"status": "void", "profit": 0.0})
            continue
        over = m["hg"] + m["ag"] > 2
        won = (e["side"] == "Over") == over
        e.update({"status": "won" if won else "lost", "score": f"{m['hg']}:{m['ag']}",
                  "profit": round(e["odds"] - 1, 3) if won else -1.0})
        close = m["close"]["B365"] if e["book"] == "B365" else m["close"]["Avg"]
        ci = 0 if e["side"] == "Over" else 1
        if close and close[ci]:
            e["close_odds"] = close[ci]


def journal_summary(journal):
    out = {}
    for strategy in ("model", "market"):
        es = [e for e in journal.get("entries", []) if e.get("strategy", "model") == strategy]
        settled = [e for e in es if e["status"] in ("won", "lost")]
        n = len(settled)
        profit = sum(e["profit"] for e in settled)
        clv = [e["odds"] / e["close_odds"] - 1 for e in settled if e.get("close_odds")]
        out[strategy] = {"settled": n, "won": sum(1 for e in settled if e["status"] == "won"),
                         "open": sum(1 for e in es if e["status"] == "open"),
                         "profit": round(profit, 2), "roi": round(profit / n, 4) if n else None,
                         "clv": round(sum(clv) / len(clv), 4) if clv else None}
    return out


# ---------------------------------------------------------------- The Odds API (Ladbrokes, BetVictor)

ODDS_API = "https://api.the-odds-api.com/v4/sports/{sport}/odds"
ODDS_SPORTS = {"E0": "soccer_epl", "SP1": "soccer_spain_la_liga", "I1": "soccer_italy_serie_a",
               "D1": "soccer_germany_bundesliga", "F1": "soccer_france_ligue_one"}
USER_BOOKS = {"ladbrokes_uk": "LB", "betvictor": "BV"}   # the user's bookmakers (all UK books are fetched)
ODDS_REFRESH_H = 11      # free plan budget: ~5 calls x 2-3 times a day
LONDON = ZoneInfo("Europe/London")

STOP = {"fc", "cf", "afc", "sc", "ac", "as", "ssc", "us", "rc", "cd", "ud", "sd", "vfb", "vfl", "tsg", "fsv", "sv",
        "1", "05", "04", "club", "de", "calcio", "and", "the", "hotspur", "albion", "wanderers", "town", "city", "united"}
ALIASES = {  # normalised Odds-API name -> football-data name
    "manchester united": "Man United", "manchester city": "Man City", "man utd": "Man United",
    "brighton hove": "Brighton", "wolverhampton": "Wolves", "nottingham forest": "Nott'm Forest",
    "atletico madrid": "Ath Madrid", "atletico": "Ath Madrid", "athletic bilbao": "Ath Bilbao", "athletic": "Ath Bilbao",
    "real betis": "Betis", "celta vigo": "Celta", "rayo vallecano": "Vallecano", "real sociedad": "Sociedad",
    "espanyol": "Espanol", "deportivo la coruna": "La Coruna", "racing santander": "Santander",
    "real oviedo": "Oviedo", "real valladolid": "Valladolid", "sporting gijon": "Sp Gijon", "deportivo alaves": "Alaves",
    "inter milan": "Inter", "internazionale": "Inter", "milan": "Milan", "roma": "Roma", "hellas verona": "Verona",
    "bayern munchen": "Bayern Munich", "borussia dortmund": "Dortmund", "borussia monchengladbach": "M'gladbach",
    "monchengladbach": "M'gladbach", "bayer leverkusen": "Leverkusen", "eintracht frankfurt": "Ein Frankfurt",
    "koln": "FC Koln", "cologne": "FC Koln", "mainz": "Mainz", "hamburger": "Hamburg", "schalke": "Schalke 04",
    "st pauli": "St Pauli", "sankt pauli": "St Pauli", "heidenheim": "Heidenheim", "sv elversberg": "Elversberg",
    "paris saint germain": "Paris SG", "psg": "Paris SG", "olympique marseille": "Marseille", "olympique lyonnais": "Lyon",
    "stade rennais": "Rennes", "stade brestois 29": "Brest", "stade brestois": "Brest", "saint etienne": "St Etienne",
    "as saint etienne": "St Etienne", "le havre": "Le Havre", "le mans": "Le Mans", "estac troyes": "Troyes",
}


def norm_name(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().replace("'", "")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(t for t in s.split() if t not in STOP)


def match_team(raw, known):
    """Map a bookmaker-feed team name onto the football-data name used by the model."""
    if raw in known:
        return raw
    n = norm_name(raw)
    full = re.sub(r"[^a-z0-9 ]", " ", unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode().lower())
    full = " ".join(full.split())
    for key in (full, n):
        if key in ALIASES and ALIASES[key] in known:
            return ALIASES[key]
    by_norm = {norm_name(k): k for k in known}
    if n in by_norm:
        return by_norm[n]
    nt = set(n.split())
    subs = [k for kn, k in by_norm.items() if kn and (set(kn.split()) <= nt or (nt and nt <= set(kn.split())))]
    if len(subs) == 1:
        return subs[0]
    close = difflib.get_close_matches(n, list(by_norm), n=1, cutoff=0.75)
    return by_norm[close[0]] if close else None


class OddsAPI:
    """Fetches over/under 2.5 prices from the user's bookmakers, cached to stay inside the free plan."""

    def __init__(self, key, outdir, now):
        self.key, self.now = key, now
        self.path = os.path.join(outdir, "odds_cache.json")
        self.status = {"enabled": bool(key)}

    def load(self):
        try:
            cache = json.load(open(self.path, encoding="utf-8"))
        except Exception:
            cache = {}
        fetched = cache.get("fetched_at")
        fresh = fetched and (self.now - dt.datetime.fromisoformat(fetched)).total_seconds() < ODDS_REFRESH_H * 3600
        if self.key and not fresh:
            new, errors, remaining = {}, [], None
            for div, sport in ODDS_SPORTS.items():
                url = ODDS_API.format(sport=sport) + "?" + "&".join([
                    "apiKey=" + self.key, "markets=totals", "oddsFormat=decimal", "dateFormat=iso",
                    "regions=uk"])
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "linia-goli/2"})
                    with urllib.request.urlopen(req, timeout=60) as r:
                        remaining = r.headers.get("x-requests-remaining", remaining)
                        new[div] = json.loads(r.read().decode("utf-8"))
                except Exception as e:
                    msg = str(e).replace(self.key, "***")
                    errors.append(f"{div}: {msg}")
            if new:
                cache = {"fetched_at": self.now.isoformat(timespec="minutes"), "remaining": remaining, "events": new}
                json.dump(cache, open(self.path, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
            self.status["errors"] = errors
        self.status.update({"fetched_at": cache.get("fetched_at"), "remaining": cache.get("remaining")})
        return self.parse(cache.get("events") or {})

    @staticmethod
    def parse(events_by_div):
        out = {}
        for div, events in events_by_div.items():
            rows = []
            for ev in events if isinstance(events, list) else []:
                try:
                    ko = dt.datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")).astimezone(LONDON)
                except Exception:
                    continue
                odds, books = {}, {}
                for bm in ev.get("bookmakers", []):
                    code = USER_BOOKS.get(bm.get("key"))
                    for mk in bm.get("markets", []):
                        if mk.get("key") != "totals":
                            continue
                        o = u = None
                        for oc in mk.get("outcomes", []):
                            if abs(float(oc.get("point", 0)) - 2.5) > 1e-9:
                                continue
                            if oc.get("name") == "Over":
                                o = fnum(oc.get("price"))
                            elif oc.get("name") == "Under":
                                u = fnum(oc.get("price"))
                        if o or u:
                            books[bm.get("key")] = {"t": bm.get("title") or bm.get("key"), "o": o, "u": u}
                            if code:
                                odds[code] = [o, u]
                rows.append({"d": ko.date(), "t": ko.strftime("%H:%M"), "home": ev.get("home_team", ""),
                             "away": ev.get("away_team", ""), "odds": odds, "books": books})
            out[div] = rows
        return out


def merge_bookmaker_odds(fx, events, known, today, unmatched):
    """Attach the user's bookmaker prices to fixtures; add matches missing from fixtures.csv."""
    idx = {(m["h"], m["a"]): m for m in fx}
    for ev in events:
        if ev["d"] < today:
            continue
        h, a = match_team(ev["home"], known), match_team(ev["away"], known)
        if not h or not a:
            unmatched.extend(n for n, x in ((ev["home"], h), (ev["away"], a)) if not x)
            continue
        m = idx.get((h, a))
        if m and abs((m["d"] - ev["d"]).days) <= 1:
            m["odds"] = dict(m["odds"], **ev["odds"])
            m["books"] = ev["books"]
        elif ev["odds"] or ev["books"] or not m:
            new = {"div": None, "d": ev["d"], "t": ev["t"], "h": h, "a": a, "hg": None, "ag": None,
                   "hst": None, "ast": None, "odds": dict(ev["odds"]), "books": ev["books"], "close": {}}
            fx.append(new); idx[(h, a)] = new
    return fx


def fair_price(odds, books):
    """Fair P(over 2.5): de-margined Pinnacle when available, else median of UK bookmakers."""
    q = market_prob(odds.get("P", [None, None]))
    if q:
        return q, "Pinnacle", 1
    qs = sorted(x for x in (market_prob([b["o"], b["u"]]) for b in (books or {}).values()) if x)
    if len(qs) >= MIN_BOOKS_FAIR:
        mid = len(qs) // 2
        return (qs[mid] if len(qs) % 2 else (qs[mid - 1] + qs[mid]) / 2), "UK", len(qs)
    return None, None, 0


def market_bet(q, odds, books=None):
    """A bookmaker price that beats the fair market price: the user's bookmakers first,
    otherwise any UK bookmaker in the feed (Ladbrokes/BetVictor do not publish totals there)."""
    if not q:
        return None
    cands = []
    for b in ("LB", "BV"):
        if b in odds:
            bb = best_bet(q, odds[b])
            if bb:
                cands.append((bb, b))
    if not cands:
        for b in (books or {}).values():
            bb = best_bet(q, [b["o"], b["u"]])
            if bb:
                cands.append((bb, b["t"]))
    if not cands:
        return None
    bb, b = max(cands, key=lambda c: c[0][3])
    if bb[3] > MARKET_EDGE_MIN:
        return {"side": bb[0], "prob": round(bb[1], 4), "odds": bb[2], "edge": round(bb[3], 4), "book": b}
    return None


def choose_bet(po, odds):
    """Paper bet at the user's bookmakers when they have a price, else Bet365, else market average."""
    for books in (("LB", "BV"), ("B365",), ("Avg",)):
        cands = []
        for b in books:
            if b in odds:
                bb = best_bet(po, odds[b])
                if bb:
                    cands.append((bb, b))
        if cands:
            bb, b = max(cands, key=lambda c: c[0][3])
            if bb[3] > EDGE_MIN:
                return {"side": bb[0], "prob": round(bb[1], 4), "odds": bb[2], "edge": round(bb[3], 4), "book": b}
            return None
    return None


# ---------------------------------------------------------------- main

def run(today, src, outdir, fixtures_from_results=False, n_seasons=5):
    years = season_years(today, n_seasons)          # current first
    fixtures_all = src.fixtures()
    jpath = os.path.join(outdir, "journal.json")
    try:
        journal = json.load(open(jpath, encoding="utf-8"))
    except Exception:
        journal = {"entries": []}
    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat(timespec="minutes")
    oa = OddsAPI(os.environ.get("ODDS_API_KEY", "").strip() or None, outdir, now)
    book_events = oa.load() if not fixtures_from_results else {}
    unmatched = []
    out = {"generated": now_iso, "today": today.isoformat(), "source": "football-data.co.uk",
           "edge_min": EDGE_MIN, "market_edge_min": MARKET_EDGE_MIN, "params": {k: v for k, v in P.items() if k != "promoted"}, "leagues": []}
    for code, folder, name, country in LEAGUES:
        seasons = [src.season(code, folder, y) for y in reversed(years)]  # oldest first
        cur = seasons[-1]
        if not cur and not any(seasons):
            continue
        if fixtures_from_results:  # offline test: matches on/after today become fixtures with their pre-match odds
            fx = [dict(m, hg=None, ag=None) for m in cur if m["d"] >= today]
            seasons[-1] = cur = [m for m in cur if m["d"] < today]
        else:
            fx = [m for m in (fixtures_all or []) if m["div"] == code and m["d"] >= today]
        known = set().union(*(teams_of(r) for r in seasons if r)) | teams_of(fx)
        fx = merge_bookmaker_odds(fx, book_events.get(code, []), known, today, unmatched)
        hist = [m for rows in seasons for m in rows]
        prev_teams = teams_of(seasons[-2]) if len(seasons) > 1 and seasons[-2] else None
        mod = Model(hist, today + dt.timedelta(days=1), prev_teams)
        played = [m for m in cur if m["hg"] is not None]
        priced = []
        for m in sorted(fx, key=lambda m: (m["d"], m["t"])):
            lh, la = mod.lambdas(m["h"], m["a"])
            mk = markets(lh, la, P["rho"])
            po = mk["over"]["2.5"]
            odds = {k: v for k, v in m["odds"].items() if v[0] or v[1]}
            bet = choose_bet(po, odds)
            books = m.get("books") or {}
            q, qsrc, qn = fair_price(odds, books)
            mbet = market_bet(q, odds, books)
            min_odds = {"over": round((1 + MARKET_EDGE_MIN) / q, 2), "under": round((1 + MARKET_EDGE_MIN) / (1 - q), 2)} if q else None
            best = {}
            for i, side in ((0, "over"), (1, "under")):
                pr = [((b["o"], b["u"])[i], b["t"]) for b in books.values() if (b["o"], b["u"])[i]]
                pr += [(odds[k][i], {"B365": "Bet365", "P": "Pinnacle"}[k]) for k in ("B365", "P") if k in odds and odds[k][i]]
                if pr:
                    best[side] = max(pr)
            mp = market_prob(odds.get("P", [None, None])) or market_prob(odds.get("Avg", [None, None]))
            priced.append({"id": match_id(code, m), "date": m["d"].isoformat(), "time": m["t"],
                           "home": m["h"], "away": m["a"], "xg": [round(lh, 2), round(la, 2)],
                           "odds": odds, "market_over": round(mp, 4) if mp else None, "bet": bet,
                           "fair_over": round(q, 4) if q else None, "fair_src": qsrc, "fair_n": qn, "mbet": mbet,
                           "min_odds": min_odds,
                           "best": best, "books": {k: [b["t"], b["o"], b["u"]] for k, b in sorted(books.items())}, **mk})
        update_journal(journal, code, name, priced, cur, now_iso, today)
        bt = backtest(seasons[:-1], 2) if len(seasons) >= 4 else None  # completed seasons only
        last = max((m["d"] for m in played), default=None)
        out["leagues"].append({
            "code": code, "name": name, "country": country, "season": season_code(years[0]),
            "played": len(played), "last_result": last.isoformat() if last else None,
            "goals_pg": round(sum(m["hg"] + m["ag"] for m in played) / len(played), 2) if played else None,
            "o25_rate": round(sum(1 for m in played if m["hg"] + m["ag"] > 2) / len(played), 3) if played else None,
            "avg": [round(mod.H, 2), round(mod.A, 2)],
            "teams": {t: team_stats(played, t, mod) for t in sorted(teams_of(cur) | teams_of(fx))},
            "fixtures": priced, "backtest": bt,
        })
    if fixtures_all is not None:  # diagnostics: what the upcoming-fixtures file contained
        diag = {}
        for m in fixtures_all:
            x = diag.setdefault(m["div"] or "?", {"rows": 0, "first": None, "last": None})
            x["rows"] += 1
            ds = m["d"].isoformat()
            x["first"] = min(x["first"] or ds, ds); x["last"] = max(x["last"] or ds, ds)
        out["fixtures_file"] = {k: diag[k] for k in sorted(diag) if k in {c for c, *_ in LEAGUES}}
        out["fixtures_file_rows"] = len(fixtures_all)
    oa.status["unmatched"] = sorted(set(unmatched))
    out["bookmakers"] = oa.status
    journal["summary"] = journal_summary(journal)
    journal["updated"] = now_iso
    out["journal_summary"] = journal["summary"]
    out["errors"] = src.errors
    if not out["leagues"]:  # source down: keep the last good data instead of publishing an empty page
        raise SystemExit("no leagues built: " + "; ".join(src.errors[:3]))
    os.makedirs(outdir, exist_ok=True)
    dpath = os.path.join(outdir, "data.json")
    # keep old timestamps when nothing else changed, so unchanged runs make no commit
    try:
        old = json.load(open(dpath, encoding="utf-8"))
        if {k: v for k, v in old.items() if k != "generated"} == {k: v for k, v in out.items() if k != "generated"}:
            out["generated"] = old["generated"]
    except Exception:
        pass
    try:
        oldj = json.load(open(jpath, encoding="utf-8"))
        if oldj.get("entries") == journal.get("entries"):
            journal["updated"] = oldj.get("updated", journal["updated"])
    except Exception:
        pass
    json.dump(out, open(dpath, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(journal, open(jpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--local")
    ap.add_argument("--today")
    ap.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--fixtures-from-results", action="store_true")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(dt.timezone.utc).date()
    o = run(today, Source(a.local), a.out, a.fixtures_from_results)
    for L in o["leagues"]:
        bt = L["backtest"] or {}
        print(f"{L['name']:15} played {L['played']:3} last {L['last_result']} fixtures {len(L['fixtures']):3} "
              f"bets {sum(1 for f in L['fixtures'] if f['bet'])} bt {bt.get('books', {}).get('B365')}")
    print("journal", o["journal_summary"])
    if o["errors"]:
        print("errors:", *o["errors"], sep="\n  ")
    if not o["leagues"]:
        sys.exit("no leagues built")
