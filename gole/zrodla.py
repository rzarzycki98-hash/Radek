"""Extra free data for the agent: team strength from ClubElo (api.clubelo.com, one CSV a day).

ClubElo rates every European club after each match (like chess Elo). The agent uses it as an
independent opinion on how strong the two teams are; the tactic built on it is tested on paper first.
"""
import csv, datetime as dt, difflib, io, json, os, time, unicodedata, urllib.error, urllib.request
from zoneinfo import ZoneInfo

ELO_URLS = ["https://api.clubelo.com/{day}", "http://api.clubelo.com/{day}"]
RETRY_H = 6   # after a failed download, try again after this many hours (meanwhile: Elo from league results)
COUNTRY = {"E0": "ENG", "SP1": "ESP", "I1": "ITA", "D1": "GER", "F1": "FRA", "N1": "NED", "P1": "POR",
           "B1": "BEL", "T1": "TUR", "SC0": "SCO", "G1": "GRE"}
# football-data name -> how ClubElo usually writes it (a hint for the matcher, not a hard rule)
HINT = {"nott'm forest": "forest", "ath bilbao": "bilbao", "ath madrid": "atletico", "espanol": "espanyol",
        "la coruna": "depor", "santander": "racing", "vallecano": "rayo vallecano", "bayern munich": "bayern",
        "ein frankfurt": "frankfurt", "fc koln": "koeln", "m'gladbach": "gladbach", "werder bremen": "werder",
        "schalke 04": "schalke", "az alkmaar": "az", "for sittard": "sittard", "psv eindhoven": "psv",
        "sp braga": "braga", "sp lisbon": "sporting", "academico viseu": "viseu", "club brugge": "brugge",
        "oud-heverlee leuven": "leuven", "raal la louviere": "louviere", "st. gilloise": "union", "lommel sk": "lommel",
        "buyuksehyr": "basaksehir", "goztep": "goztepe", "asteras tripolis": "asteras", "ofi crete": "ofi",
        "volos nfc": "volos", "levadeiakos": "levadiakos", "paris sg": "paris sg", "st truiden": "sint truiden"}
STOP = {"fc", "cf", "afc", "sc", "ac", "as", "ssc", "us", "rc", "cd", "ud", "sd", "sk", "fk", "nfc", "bk", "if", "04", "1899", "1846"}
SPECIAL = str.maketrans({"ł": "l", "ø": "o", "æ": "ae", "ß": "ss", "ı": "i", "'": "", ".": " ", "-": " "})


def norm(s):
    s = unicodedata.normalize("NFKD", (s or "").lower().translate(SPECIAL))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(t for t in s.split() if t not in STOP)


def score(a, b):
    """Similarity of two normalised names, 0..1."""
    if a == b:
        return 1.0
    if len(a) >= 3 and len(b) >= 3 and (a in b or b in a):
        return 0.9
    ta, tb = set(a.split()), set(b.split())
    if any(len(t) >= 4 for t in ta & tb):
        return 0.8
    return difflib.SequenceMatcher(None, a, b).ratio()


class ClubElo:
    def __init__(self, cache_dir, now):
        self.dir = cache_dir
        self.now = now
        self.errors = []
        self.rows = None
        self.maps = {}
        self.tried = None   # last download attempt today: when and what the server answered

    def load(self):
        if self.rows is not None:
            return self.rows
        day = self.now.date().isoformat()
        path = os.path.join(self.dir, f"clubelo-{day}.csv") if self.dir else None
        text = None
        if path and os.path.exists(path) and (time.time() - os.path.getmtime(path)) / 3600 < 12:
            text = open(path, encoding="utf-8").read()
        fail_mark = os.path.join(self.dir, f"clubelo-fail-{day}") if self.dir else None
        if text is None and fail_mark and os.path.exists(fail_mark) and (time.time() - os.path.getmtime(fail_mark)) / 3600 < RETRY_H:
            why = open(fail_mark, encoding="utf-8").read().strip()
            again = time.strftime("%H:%M", time.gmtime(os.path.getmtime(fail_mark) + RETRY_H * 3600))
            self.errors.append(f"ClubElo: nie odpowiadało ({why or 'brak szczegółów'}) – kolejna próba po {again} UTC")
            self.tried = {"at": time.strftime("%Y-%m-%d %H:%M", time.gmtime(os.path.getmtime(fail_mark))), "why": why}
            text = ""  # do not wait on a source that is down; the backup Elo from results is used
        if text is None:
            last, tries = None, []
            for attempt in range(2):
                for url in ELO_URLS:
                    u = url.format(day=day)
                    try:
                        req = urllib.request.Request(u, headers={"User-Agent": "linia-goli-agent/1 (+github actions)", "Accept": "text/csv,*/*"})
                        with urllib.request.urlopen(req, timeout=20) as r:
                            got = r.read().decode("utf-8", errors="replace")
                        if got.startswith("Rank") or "Club," in got[:200]:
                            text = got
                            break
                        last = f"{u.split(':')[0]}: nieoczekiwana odpowiedź {got[:60]!r}"
                    except urllib.error.HTTPError as e:
                        body = ""
                        try:
                            body = e.read()[:60].decode("utf-8", "replace").strip()
                        except Exception:
                            pass
                        last = f"{u.split(':')[0]}: HTTP {e.code} {e.reason}" + (f" ({body})" if body else "")
                    except Exception as e:
                        last = f"{u.split(':')[0]}: {type(e).__name__} {str(e)[:80]}"
                    tries.append(last)
                if text is not None:
                    break
                time.sleep(5)
            self.tried = {"at": time.strftime("%Y-%m-%d %H:%M", time.gmtime()), "why": "; ".join(dict.fromkeys(tries))[:300]}
            last = self.tried["why"] or last
            if text is not None and path:
                os.makedirs(self.dir, exist_ok=True)
                open(path, "w", encoding="utf-8").write(text)
            if text is None:
                self.errors.append(f"ClubElo: {last}")
                if fail_mark:
                    os.makedirs(self.dir, exist_ok=True)
                    open(fail_mark, "w").write(last or "")
                old = sorted(f for f in os.listdir(self.dir) if f.startswith("clubelo-") and f.endswith(".csv")) if self.dir and os.path.isdir(self.dir) else []
                if old:  # source down: yesterday's ratings are still good
                    text = open(os.path.join(self.dir, old[-1]), encoding="utf-8").read()
        rows = {}
        for r in csv.DictReader(io.StringIO(text or "")):
            try:
                rows.setdefault(r["Country"], []).append((r["Club"], float(r["Elo"]), int(r.get("Level") or 1)))
            except (KeyError, ValueError, TypeError):
                continue
        self.rows = rows
        return rows

    def match(self, code, teams):
        """{football-data team: (ClubElo club, elo, match score)} for one league; greedy, best pairs first."""
        if code in self.maps:
            return self.maps[code]
        cands = [c for c in self.load().get(COUNTRY.get(code, ""), []) if c[2] <= 2]
        pairs = []
        for t in teams:
            a = norm(HINT.get(t.lower(), t))
            a2 = norm(t)
            for club, elo, lvl in cands:
                b = norm(club)
                s = max(score(a, b), score(a2, b) - 0.05) - (0.02 if lvl == 2 else 0)
                pairs.append((s, t, club, elo))
        pairs.sort(key=lambda p: -p[0])
        out, used = {}, set()
        for s, t, club, elo in pairs:
            if s < 0.55 or t in out or club in used:
                continue
            out[t] = (club, elo, round(s, 2))
            used.add(club)
        self.maps[code] = out
        return out

    def status(self):
        return {"errors": self.errors, "clubs": sum(len(v) for v in (self.rows or {}).values()), "tried": self.tried,
                "matched": {c: {t: [v[0], round(v[1]), v[2]] for t, v in m.items()} for c, m in self.maps.items()}}


def results_elo(seasons, k=20.0, home=60.0):
    """Backup when ClubElo cannot be reached: Elo from the league's own results (6 seasons),
    goal difference counts, a third of the way back to the average between seasons."""
    elo = {}
    for i, rows in enumerate(seasons):
        if i:
            mean = sum(elo.values()) / len(elo) if elo else 1500.0
            for t in elo:
                elo[t] = elo[t] - (elo[t] - mean) / 3
        for m in rows:
            if m.get("hg") is None:
                continue
            h, a = m["h"], m["a"]
            rh, ra = elo.get(h, 1450.0), elo.get(a, 1450.0)   # newcomers start a little below average
            exp = 1 / (1 + 10 ** ((ra - rh - home) / 400))
            res = 1.0 if m["hg"] > m["ag"] else 0.5 if m["hg"] == m["ag"] else 0.0
            gd = abs(m["hg"] - m["ag"])
            mult = 1.0 if gd <= 1 else 1.5 if gd == 2 else (11 + gd) / 8
            delta = k * mult * (res - exp)
            elo[h], elo[a] = rh + delta, ra - delta
    return elo


# ---------------------------------------------------------------- backup results (decision 21.10.2026)
ESPN_SOCCER = "https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={ymd}"
ESPN_SLUG = {"E0": "eng.1", "SP1": "esp.1", "I1": "ita.1", "D1": "ger.1", "F1": "fra.1", "N1": "ned.1", "P1": "por.1",
             "B1": "bel.1", "T1": "tur.1", "SC0": "sco.1", "G1": "gre.1"}
LONDON = ZoneInfo("Europe/London")
LATE_H = 72   # a match without a football-data result this many hours after kick-off is settled from ESPN


class ESPNScores:
    """Final scores from ESPN (free, no key) for matches football-data has not published 3+ days after kick-off.
    Used only to settle the agent's bets and analyses; the model keeps learning from football-data only."""

    def __init__(self, cache_dir, now):
        self.dir = os.path.join(cache_dir, "espn_pilka") if cache_dir else None
        self.now = now
        self.errors, self.downloads, self.used = [], 0, 0

    def _day(self, code, day):
        """[[home, away, home goals, away goals, finished]] of one league on one day (UTC date of kick-off)."""
        path = os.path.join(self.dir, f"{code}-{day:%Y%m%d}.json") if self.dir else None
        if path and os.path.exists(path):  # finished days stay cached; others are asked again after 3 hours
            rows = json.load(open(path, encoding="utf-8"))
            if (rows and all(r[4] for r in rows)) or (time.time() - os.path.getmtime(path)) / 3600 < 3:
                return rows
        url = ESPN_SOCCER.format(slug=ESPN_SLUG[code], ymd=f"{day:%Y%m%d}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (linia-goli; +github actions)", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            js = json.loads(r.read().decode("utf-8"))
        self.downloads += 1
        rows = []
        for ev in js.get("events", []) or []:
            try:
                comp = ev["competitions"][0]
                cs = {c.get("homeAway"): c for c in comp.get("competitors", [])}
                stt = ((ev.get("status") or comp.get("status") or {}).get("type") or {})
                name = str(stt.get("name") or "")
                done = bool(stt.get("completed")) and not any(w in name for w in ("POSTPONED", "CANCEL", "ABANDON", "SUSPENDED"))
                rows.append([cs["home"]["team"].get("displayName", ""), cs["away"]["team"].get("displayName", ""),
                             int(float(cs["home"].get("score") or 0)), int(float(cs["away"].get("score") or 0)), done])
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        if path:
            os.makedirs(self.dir, exist_ok=True)
            json.dump(rows, open(path, "w", encoding="utf-8"))
        return rows

    def results(self, code, wanted, sim):
        """Result rows (football-data layout, src="ESPN") for wanted matches [(kick-off ISO, home, away)];
        sim(espn name, football-data name) -> 0..1 matches the team names."""
        if code not in ESPN_SLUG:
            return []
        out, days = [], {}
        for ko, h, a in wanted:
            k = dt.datetime.fromisoformat(ko)
            if (self.now - k).total_seconds() / 3600 < LATE_H or (self.now - k).days > 21:
                continue
            days.setdefault(k.date(), []).append((k, h, a))
        for day, games in sorted(days.items()):
            try:
                rows = self._day(code, day)
            except Exception as e:
                self.errors.append(f"ESPN {code} {day}: {str(e)[:80]}")
                continue
            for k, h, a in games:
                best = max(((sim(r[0], h) + sim(r[1], a), r) for r in rows if r[4]), default=(0, None), key=lambda x: x[0])
                if best[1] is None or best[0] < 1.3:
                    continue
                r = best[1]
                out.append({"d": k.astimezone(LONDON).date(), "h": h, "a": a, "hg": r[2], "ag": r[3], "hst": None, "ast": None,
                            "ou": {}, "ouc": {}, "x": {}, "xc": {}, "src": "ESPN"})
                self.used += 1
        return out

    def status(self):
        return {"errors": self.errors[:5], "downloads": self.downloads, "used": self.used}
