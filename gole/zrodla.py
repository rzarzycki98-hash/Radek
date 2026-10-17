"""Extra free data for the agent: team strength from ClubElo (api.clubelo.com, one CSV a day).

ClubElo rates every European club after each match (like chess Elo). The agent uses it as an
independent opinion on how strong the two teams are; the tactic built on it is tested on paper first.
"""
import csv, difflib, io, os, time, unicodedata, urllib.request

ELO_URL = "http://api.clubelo.com/{day}"
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

    def load(self):
        if self.rows is not None:
            return self.rows
        day = self.now.date().isoformat()
        path = os.path.join(self.dir, f"clubelo-{day}.csv") if self.dir else None
        text = None
        if path and os.path.exists(path) and (time.time() - os.path.getmtime(path)) / 3600 < 12:
            text = open(path, encoding="utf-8").read()
        if text is None:
            try:
                req = urllib.request.Request(ELO_URL.format(day=day), headers={"User-Agent": "linia-goli-agent/1 (+github actions)"})
                with urllib.request.urlopen(req, timeout=40) as r:
                    text = r.read().decode("utf-8", errors="replace")
                if path:
                    os.makedirs(self.dir, exist_ok=True)
                    open(path, "w", encoding="utf-8").write(text)
            except Exception as e:
                self.errors.append(f"ClubElo: {str(e)[:100]}")
                old = sorted(f for f in os.listdir(self.dir) if f.startswith("clubelo-")) if self.dir and os.path.isdir(self.dir) else []
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
        return {"errors": self.errors, "clubs": sum(len(v) for v in (self.rows or {}).values()),
                "matched": {c: {t: [v[0], round(v[1]), v[2]] for t, v in m.items()} for c, m in self.maps.items()}}
