"""NBA for the Linia Goli agent: total points over/under.

  - results and schedule: ESPN scoreboard (free, no key), one request per game day, finished days cached for good,
  - model: every team's attack and defence in points against the league average, older games weigh less;
    memory length and prior are tuned on the games so far (walk-forward), spread from the model's own errors,
  - prices: The Odds API, market "totals", UK bookmakers (1 request = 1 credit, at most 2 a day).
"""
import datetime as dt, json, math, os, time, urllib.request
from zoneinfo import ZoneInfo

ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_INJ = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
STAR_SHARE = 0.25           # a player who was his team's top scorer in 25%+ of its recent games is a star
STAR_POINTS = 3.0           # a missing star takes about 3 points off the expected total (tested on paper by the agent)
INJ_W = {"out": 1.0, "doubtful": 0.75, "questionable": 0.4, "day-to-day": 0.4, "probable": 0.1}
ET = ZoneInfo("America/New_York")
TEAMS = {"hawks", "celtics", "nets", "hornets", "bulls", "cavaliers", "mavericks", "nuggets", "pistons", "warriors",
         "rockets", "pacers", "clippers", "lakers", "grizzlies", "heat", "bucks", "timberwolves", "pelicans", "knicks",
         "thunder", "magic", "76ers", "suns", "blazers", "kings", "spurs", "raptors", "jazz", "wizards"}
REAL = (2, 3, 5)            # ESPN season types: regular season, play-offs, play-in (1 = pre-season)
GRID = [(h, k) for h in (15.0, 30.0, 60.0, 120.0) for k in (2.0, 5.0, 10.0)]
WARMUP = 200                # games before the tuning starts counting errors
ODDS_EVERY_H = 8
ODDS_PER_DAY = 2
SEASON_MONTHS = {10, 11, 12, 1, 2, 3, 4, 5, 6}
SD_RANGE = (14.0, 26.0)


def team_key(name):
    w = (name or "").strip().lower().split()
    return w[-1] if w else ""


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def prob_total(mu, sd, line):
    """(P over, P under, P push) for a total-points line; whole lines can push."""
    if abs(line - round(line)) < 1e-9:
        po = 1 - ncdf((line + 0.5 - mu) / sd)
        pu = ncdf((line - 0.5 - mu) / sd)
    else:
        po = 1 - ncdf((line - mu) / sd)
        pu = 1 - po
    return po, pu, max(0.0, 1 - po - pu)


# ---------------------------------------------------------------- ESPN

def as_int(v):
    """ESPN gives some fields as numbers and some as objects ({"id": "2", "type": 2, ...})."""
    for _ in range(2):
        if isinstance(v, dict):
            v = next((v[k] for k in ("type", "value", "id", "displayValue") if k in v), None)
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def parse(js):
    games = []
    default_type = 0
    for L in (js or {}).get("leagues", []) or []:
        default_type = as_int((L.get("season") or {}).get("type"))
        break
    for ev in (js or {}).get("events", []) or []:
        try:
            comp = ev["competitions"][0]
            cs = {c.get("homeAway"): c for c in comp.get("competitors", [])}
            h, a = cs["home"], cs["away"]
            hn, an = h["team"].get("displayName", ""), a["team"].get("displayName", "")
            hk, ak = team_key(hn), team_key(an)
            if hk not in TEAMS or ak not in TEAMS or hk == ak:
                continue
            stt = ((ev.get("status") or comp.get("status") or {}).get("type") or {})
            hs, as_ = as_int(h.get("score")), as_int(a.get("score"))
            done = bool(stt.get("completed")) and hs + as_ > 0
            games.append({"id": str(ev["id"]), "ko": ev["date"].replace("Z", "+00:00"), "h": hk, "a": ak, "hn": hn, "an": an,
                          "hs": hs if done else None, "as": as_ if done else None, "done": done,
                          "lh": top_scorer(h), "la": top_scorer(a),
                          "type": as_int((ev.get("season") or {}).get("type")) or default_type, "st": stt.get("name")})
        except Exception:
            continue
    return games


def top_scorer(comp):
    """[name, points] of a team's top scorer: in the game (finished) or per game this season (upcoming)."""
    try:
        for L in comp.get("leaders", []) or []:
            if L.get("name") in ("points", "pointsPerGame"):
                x = (L.get("leaders") or [])[0]
                a = x.get("athlete") or {}
                return [a.get("displayName") or a.get("fullName") or a.get("shortName"), as_int(x.get("value")),
                        "g" if L.get("name") == "points" else "s"]
    except Exception:
        pass
    return None


def calendar(js):
    out = []
    for L in (js or {}).get("leagues", []) or []:
        for c in L.get("calendar", []) or []:
            v = c if isinstance(c, str) else (c.get("startDate") if isinstance(c, dict) else None)
            if v and len(v) >= 10:
                out.append(v[:10].replace("-", ""))
        season = as_int((L.get("season") or {}).get("year")) or None
        return sorted(set(out)), season
    return [], None


class ESPNSource:
    def __init__(self, cache_dir, now):
        self.dir = os.path.join(cache_dir, "nba")
        os.makedirs(self.dir, exist_ok=True)
        self.now = now
        self.errors, self.downloads = [], 0

    def _get(self, params, base=ESPN):
        url = base + ("?" + params if params else "")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (linia-goli; +github actions)", "Accept": "application/json"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    self.downloads += 1
                    time.sleep(0.15)
                    return json.loads(r.read().decode("utf-8"))
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)

    def _cache(self, name, params, fresh, build, base=ESPN):
        """fresh(data, age_h) -> True when the cached copy can be used."""
        path = os.path.join(self.dir, name)
        old = None
        if os.path.exists(path):
            try:
                old = json.load(open(path, encoding="utf-8"))
                if fresh(old, (time.time() - os.path.getmtime(path)) / 3600):
                    return old
            except Exception:
                old = None
        try:
            data = build(self._get(params, base))
        except Exception as e:
            if old is not None:
                return old
            raise e
        json.dump(data, open(path, "w", encoding="utf-8"), separators=(",", ":"))
        return data

    def season_calendar(self, params, name, max_age_h):
        def build(js):
            cal, season = calendar(js)
            return {"cal": cal, "season": season, "games": parse(js)}
        return self._cache(name, params, lambda d, age: max_age_h is None or age < max_age_h, build)

    def day(self, ymd, past):
        def fresh(d, age):
            if past and all(g["done"] or g.get("st") in ("STATUS_POSTPONED", "STATUS_CANCELED") for g in d["games"]):
                return True
            return age < 3.0
        return self._cache(f"e{ymd}.json", f"dates={ymd}", fresh, lambda js: {"games": parse(js)})["games"]

    def injuries(self):
        """{team key: [[player, status, comment]]} from ESPN's injury report (refreshed every 3 hours)."""
        def build(js):
            out = {}
            for t in (js or {}).get("injuries", []) or []:
                k = team_key(t.get("displayName", ""))
                if k not in TEAMS:
                    continue
                rows = []
                for i in t.get("injuries", []) or []:
                    a = i.get("athlete") or {}
                    stt = i.get("status") or ((i.get("type") or {}).get("description")) or ""
                    rows.append([a.get("displayName") or "", str(stt), (i.get("shortComment") or "")[:140]])
                out[k] = rows
            return {"teams": out}
        return self._cache("injuries.json", "", lambda d, age: age < 3.0, build, base=ESPN_INJ)["teams"]


def load_games(cache_dir, now):
    src = ESPNSource(cache_dir, now)
    today = now.astimezone(ET).date()
    for fn in os.listdir(src.dir):  # older cache layout without top scorers
        if fn.startswith("d") and fn.endswith(".json"):
            try:
                os.remove(os.path.join(src.dir, fn))
            except OSError:
                pass
    top = src.season_calendar(f"dates={today:%Y%m%d}", "cal_now.json", 12)   # the season that contains today
    cal_now, y = top["cal"], top["season"]
    if not y:
        raise RuntimeError("ESPN: brak kalendarza sezonu")
    prev = src.season_calendar(f"dates={y - 1}0115", f"cal_{y - 1}.json", None)
    days = sorted(set(prev["cal"]) | set(cal_now))
    games = {}
    for ymd in days:
        try:
            d = dt.date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:]))
        except ValueError:
            continue
        if d > today + dt.timedelta(days=7) or d < today - dt.timedelta(days=500):   # a week ahead: the next game shows early
            continue
        try:
            for g in src.day(ymd, d < today - dt.timedelta(days=1)):
                g["day"] = d.isoformat()
                games[g["id"]] = g
        except Exception as e:
            src.errors.append(f"ESPN {ymd}: {str(e)[:80]}")
    season_start = min(cal_now) if cal_now else None
    return sorted(games.values(), key=lambda g: g["ko"]), season_start, src


# ---------------------------------------------------------------- model

class PtsRater:
    """Points scored and allowed against the league average, decayed by days, shrunk towards average."""

    def __init__(self, half_life, prior):
        self.lam = 0.5 ** (1 / half_life)
        self.k = prior
        self.ref = None
        self.g = [0.0, 0.0, 0.0]   # weight, home points, away points
        self.t = {}                # team -> [ref_date, weight, points above expected, points allowed above expected]

    def _decay(self, d):
        if self.ref is None:
            self.ref = d
        elif d > self.ref:
            f = self.lam ** (d - self.ref).days
            self.g = [x * f for x in self.g]
            self.ref = d

    def _team(self, n, d):
        x = self.t.get(n)
        if x is None:
            x = self.t[n] = [d, 0.0, 0.0, 0.0]
        elif d > x[0]:
            f = self.lam ** (d - x[0]).days
            x[1] *= f; x[2] *= f; x[3] *= f
            x[0] = d
        return x

    def base(self):
        W, H, A = self.g
        return (H / W, A / W) if W > 5 else (115.0, 112.0)

    def rating(self, n, d):
        if n not in self.t:
            return 0.0, 0.0
        x = self._team(n, d)
        return x[2] / (x[1] + self.k), x[3] / (x[1] + self.k)

    def predict(self, h, a, d):
        self._decay(d)
        Lh, La = self.base()
        oh, dh = self.rating(h, d)
        oa, da = self.rating(a, d)
        return Lh + oh + da, La + oa + dh

    def add(self, g, d):
        self._decay(d)
        Lh, La = self.base()
        th, ta = self._team(g["h"], d), self._team(g["a"], d)
        th[1] += 1; th[2] += g["hs"] - Lh; th[3] += g["as"] - La
        ta[1] += 1; ta[2] += g["as"] - La; ta[3] += g["hs"] - Lh
        self.g[0] += 1; self.g[1] += g["hs"]; self.g[2] += g["as"]


def tune(played):
    best = None
    for hl, k in GRID:
        r = PtsRater(hl, k)
        se, n = 0.0, 0
        for i, g in enumerate(played):
            d = dt.date.fromisoformat(g["day"])
            mh, ma = r.predict(g["h"], g["a"], d)
            if i >= WARMUP:
                e = g["hs"] + g["as"] - mh - ma
                se += e * e; n += 1
            r.add(g, d)
        if n and (best is None or se / n < best[0]):
            best = (se / n, hl, k, r, n)
    return best


def team_stars(played, upcoming):
    """{team key: {player: share of games as top scorer}} from the last 30 games, plus this season's leader."""
    by_team = {}
    for g in reversed(played):
        for k, top in ((g["h"], g.get("lh")), (g["a"], g.get("la"))):
            lst = by_team.setdefault(k, [])
            if len(lst) < 30 and top and top[0]:
                lst.append(top[0])
    out = {}
    for k, names in by_team.items():
        n = len(names)
        if n < 5:
            continue
        cnt = {}
        for x in names:
            cnt[x] = cnt.get(x, 0) + 1
        out[k] = {x: round(c / n, 2) for x, c in cnt.items() if c / n >= STAR_SHARE}
    for g in upcoming:  # the season's points-per-game leader counts as a star too
        for k, top in ((g["h"], g.get("lh")), (g["a"], g.get("la"))):
            if top and top[0] and top[2] == "s":
                out.setdefault(k, {}).setdefault(top[0], 0.5)
    return out


# ---------------------------------------------------------------- prices

def compact(ev):
    books = {}
    for bm in ev.get("bookmakers", []) or []:
        for mk in bm.get("markets", []) or []:
            if mk.get("key") != "totals":
                continue
            o = u = None
            pt = None
            for oc in mk.get("outcomes", []) or []:
                try:
                    p = float(oc.get("point"))
                    price = float(oc.get("price"))
                except (TypeError, ValueError):
                    continue
                if price <= 1.0:
                    continue
                if oc.get("name") == "Over" and o is None:
                    o, pt = price, p if pt is None else pt
                elif oc.get("name") == "Under" and u is None:
                    u = price
                    pt = p if pt is None else pt
            if o and u and pt:
                books[bm.get("key")] = {"t": bm.get("title") or bm.get("key"), "tot": [pt, o, u]}
    return {"id": ev.get("id"), "ko": (ev.get("commence_time") or "").replace("Z", "+00:00"),
            "home": ev.get("home_team", ""), "away": ev.get("away_team", ""), "books": books}


def fetch_odds(oa, now, upcoming, errors):
    """At most ODDS_PER_DAY paid requests a day, only when a real game starts within 30 hours."""
    S = oa.c["sports"].setdefault("NBA", {})
    if not oa.key:
        return S
    led = oa.c.setdefault("nba_ledger", {})
    if led.get("day") != now.date().isoformat():
        led.update({"day": now.date().isoformat(), "spent": 0})
    soon = [g for g in upcoming if now < dt.datetime.fromisoformat(g["ko"]) <= now + dt.timedelta(hours=30)]
    age = 1e9 if not S.get("odds_at") else (now - dt.datetime.fromisoformat(S["odds_at"])).total_seconds() / 3600
    remaining = oa.c.get("remaining")
    if soon and age >= ODDS_EVERY_H and led["spent"] < ODDS_PER_DAY and (remaining is None or remaining > 15):
        try:
            evs = oa._get("basketball_nba", "odds", ["regions=uk", "markets=totals", "oddsFormat=decimal"])
            S["odds"] = [compact(e) for e in evs]
            S["odds_at"] = now.isoformat(timespec="minutes")
            led["spent"] += 1
        except Exception as e:
            errors.append(f"NBA kursy: {str(e).replace(oa.key, '***')[:120]}")
    return S


def reserve(now):
    """Credits kept aside for NBA for the rest of the month, so football does not spend them."""
    if now.month not in SEASON_MONTHS:
        return 0
    month_end = (now.date().replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    return ODDS_PER_DAY * ((month_end - now.date()).days + 1)


# ---------------------------------------------------------------- everything the agent needs

def prepare(cache_dir, now, oa):
    status = {"errors": []}
    games, season_start, src = load_games(cache_dir, now)
    status["errors"] += src.errors[:20]
    status["downloads"] = src.downloads
    played = [g for g in games if g["done"] and g["type"] in REAL]
    status["games"] = len(played)
    best = tune(played) if len(played) > WARMUP + 50 else None
    upcoming = [g for g in games if not g["done"] and g["type"] in REAL and dt.datetime.fromisoformat(g["ko"]) > now - dt.timedelta(hours=3)
                and dt.datetime.fromisoformat(g["ko"]) <= now + dt.timedelta(hours=48)]
    nxt = min((g for g in games if not g["done"] and g["type"] in REAL and dt.datetime.fromisoformat(g["ko"]) > now), key=lambda g: g["ko"], default=None)
    status["next"] = {"ko": nxt["ko"], "home": nxt["hn"], "away": nxt["an"]} if nxt else None
    gp = {}
    for g in played:
        if season_start and g["day"].replace("-", "") >= season_start:
            gp[g["h"]] = gp.get(g["h"], 0) + 1
            gp[g["a"]] = gp.get(g["a"], 0) + 1
    status["season_games"] = sum(gp.values()) // 2
    status["season_start"] = season_start
    if best:
        mse, hl, k, r, n = best
        sd = min(max(math.sqrt(mse), SD_RANGE[0]), SD_RANGE[1])
        status.update({"half_life": hl, "prior": k, "rmse": round(math.sqrt(mse), 1), "tested": n, "sd": round(sd, 1)})
        for g in upcoming:
            d = dt.date.fromisoformat(g["day"])
            mh, ma = r.predict(g["h"], g["a"], d)
            g.update({"mu": mh + ma, "mu_h": round(mh, 1), "mu_a": round(ma, 1), "sd": sd})
    days_by_team = {}
    for g in games:
        if g["type"] in REAL and g.get("st") not in ("STATUS_POSTPONED", "STATUS_CANCELED"):
            days_by_team.setdefault(g["h"], set()).add(g["day"])
            days_by_team.setdefault(g["a"], set()).add(g["day"])
    for g in upcoming:
        g["gp_h"], g["gp_a"] = gp.get(g["h"], 0), gp.get(g["a"], 0)
        yday = (dt.date.fromisoformat(g["day"]) - dt.timedelta(days=1)).isoformat()
        g["b2b_h"] = yday in days_by_team.get(g["h"], set())   # second night of a back-to-back
        g["b2b_a"] = yday in days_by_team.get(g["a"], set())
    # stars and the injury report: a missing top scorer usually means fewer points
    stars = team_stars(played, upcoming)
    try:
        inj = src.injuries()
    except Exception as e:
        inj = {}
        status["errors"].append(f"ESPN kontuzje: {str(e)[:80]}")
    status["injuries"] = sum(len(v) for v in inj.values())
    for g in upcoming:
        out = {}
        for side, k in (("h", g["h"]), ("a", g["a"])):
            rows = []
            for name, stt, comment in inj.get(k, []):
                w = INJ_W.get(stt.strip().lower(), 0.0)
                if name in stars.get(k, {}) and w > 0:
                    rows.append([name, stt, w, stars[k][name]])
            out[side] = rows
        adj = -STAR_POINTS * sum(r[2] for r in out["h"] + out["a"])
        g["inj"] = {"h": out["h"], "a": out["a"], "adj": round(adj, 1)}
        if g.get("mu") is not None:
            g["mu_inj"] = g["mu"] + adj
    if best:
        names = {}
        for g in games:
            names[g["h"]], names[g["a"]] = g["hn"], g["an"]
        today = now.astimezone(ET).date()
        Lh, La = r.base()
        status["teams"] = sorted(([names.get(t, t), round(r.rating(t, today)[0], 1), round(r.rating(t, today)[1], 1), gp.get(t, 0),
                                   sorted(stars.get(t, {}), key=lambda n: -stars[t][n])[:2]] for t in TEAMS if t in r.t),
                                 key=lambda x: -(x[1] - x[2]))
        status["league_pts"] = round((Lh + La) / 2, 1)
    S = fetch_odds(oa, now, upcoming, status["errors"]) if oa is not None else {}
    evs = S.get("odds", []) if S else []
    for g in upcoming:
        ko = dt.datetime.fromisoformat(g["ko"])
        for ev in evs:
            try:
                eko = dt.datetime.fromisoformat(ev["ko"])
            except Exception:
                continue
            if team_key(ev["home"]) == g["h"] and team_key(ev["away"]) == g["a"] and abs((eko - ko).total_seconds()) <= 6 * 3600:
                g["odds"] = ev
                break
    status["odds_at"] = S.get("odds_at") if S else None
    status["with_odds"] = sum(1 for g in upcoming if g.get("odds"))
    status["upcoming"] = len(upcoming)
    return {"games": games, "upcoming": upcoming, "odds_at": status["odds_at"], "status": status}
