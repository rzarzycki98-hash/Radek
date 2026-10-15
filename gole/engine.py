#!/usr/bin/env python3
"""Linia Goli v2: fetch results + odds from football-data.co.uk, rate teams, price
over/under 2.5, keep a paper-trading journal and an honest backtest.

Runs unattended in GitHub Actions. Writes gole/data.json and gole/journal.json.
Usage:
  python engine.py                       # live run (downloads from football-data.co.uk)
  python engine.py --local DIR --today YYYY-MM-DD [--fixtures-from-results]
      # offline test against a mirror laid out as DIR/data/<league>/season-XXYY.csv
"""
import argparse, csv, io, json, math, os, sys, urllib.request, datetime as dt

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
EDGE_MIN = 0.05           # paper bet when model_prob * odds - 1 > 5%
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
    ll_mod = ll_mkt = n_ll = 0
    cache = {}
    per_season = []
    for si in range(test_from_idx, len(seasons_rows)):
        prev = teams_of(seasons_rows[si - 1]) if si > 0 else None
        s = {b: {"n": 0, "profit": 0.0} for b in books}
        for m in seasons_rows[si]:
            if m["hg"] is None:
                continue
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
    out = {"matches": n_ll,
           "logloss_model": round(ll_mod / n_ll, 4) if n_ll else None,
           "logloss_market": round(ll_mkt / n_ll, 4) if n_ll else None, "books": {}}
    for b in books:
        r = res[b]
        out["books"][b] = {"bets": r["n"], "roi": round(r["profit"] / r["n"], 4) if r["n"] else None,
                           "seasons": [round(x[b]["profit"] / x[b]["n"], 4) if x[b]["n"] else None for x in per_season]}
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
        if f["id"] in known or not f.get("bet"):
            continue
        b = f["bet"]
        entries.append({"id": f["id"], "league": code, "league_name": name, "date": f["date"], "time": f["time"],
                        "home": f["home"], "away": f["away"], "side": b["side"], "prob": b["prob"],
                        "odds": b["odds"], "book": b["book"], "edge": b["edge"], "added": now_iso,
                        "status": "open"})
    res_by_id = {match_id(code, m): m for m in results if m["hg"] is not None}
    for e in entries:
        if e["league"] != code or e["status"] != "open":
            continue
        m = res_by_id.get(e["id"])
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
    settled = [e for e in journal.get("entries", []) if e["status"] in ("won", "lost")]
    n = len(settled)
    profit = sum(e["profit"] for e in settled)
    clv = [e["odds"] / e["close_odds"] - 1 for e in settled if e.get("close_odds")]
    return {"settled": n, "won": sum(1 for e in settled if e["status"] == "won"),
            "open": sum(1 for e in journal.get("entries", []) if e["status"] == "open"),
            "profit": round(profit, 2), "roi": round(profit / n, 4) if n else None,
            "clv": round(sum(clv) / len(clv), 4) if clv else None}


# ---------------------------------------------------------------- main

def run(today, src, outdir, fixtures_from_results=False, n_seasons=5):
    years = season_years(today, n_seasons)          # current first
    fixtures_all = src.fixtures()
    jpath = os.path.join(outdir, "journal.json")
    try:
        journal = json.load(open(jpath, encoding="utf-8"))
    except Exception:
        journal = {"entries": []}
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    out = {"generated": now_iso, "today": today.isoformat(), "source": "football-data.co.uk",
           "edge_min": EDGE_MIN, "params": {k: v for k, v in P.items() if k != "promoted"}, "leagues": []}
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
            bet = None
            book = "B365" if "B365" in odds else ("Avg" if "Avg" in odds else None)
            if book:
                bb = best_bet(po, odds[book])
                if bb and bb[3] > EDGE_MIN:
                    bet = {"side": bb[0], "prob": round(bb[1], 4), "odds": bb[2], "edge": round(bb[3], 4), "book": book}
            mp = market_prob(odds.get("P", [None, None])) or market_prob(odds.get("Avg", [None, None]))
            priced.append({"id": match_id(code, m), "date": m["d"].isoformat(), "time": m["t"],
                           "home": m["h"], "away": m["a"], "xg": [round(lh, 2), round(la, 2)],
                           "odds": odds, "market_over": round(mp, 4) if mp else None, "bet": bet, **mk})
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
    journal["summary"] = journal_summary(journal)
    journal["updated"] = now_iso
    out["journal_summary"] = journal["summary"]
    out["errors"] = src.errors
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
