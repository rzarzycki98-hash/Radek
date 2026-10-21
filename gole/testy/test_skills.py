"""Offline tests of the agent skills added 18.10.2026 (critic, post-match analysis, calibration, insights).
Works on copies in a temporary folder – never touches gole/agent.json.
Usage: python3 gole/testy/test_skills.py            (or give the gole folder as the first argument)
"""
import datetime as dt, json, os, random, shutil, sys, tempfile

GOLE = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GOLE)
import agent as AG  # noqa: E402

random.seed(7)
UTC = dt.timezone.utc
fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def fixtures(code):
    d = json.load(open(os.path.join(GOLE, "liga", f"{code}.json"), encoding="utf-8"))
    return list(d["fixtures"].values()), d["teams"]


def fake_results(teams, n_each):
    """Old results (August) so every team has n_each games this season; they never settle anything."""
    names = sorted(teams)
    out, day = [], dt.date(2026, 8, 1)
    for i in range(n_each):
        for j in range(0, len(names) - 1, 2):
            h, a = names[(j + i) % len(names)], names[(j + i + 1) % len(names)]
            out.append({"d": day + dt.timedelta(days=i), "h": h, "a": a, "hg": 1, "ag": 1, "ouc": {}})
    return out


# ------------------------------------------------------------------ 1) real state + real fixtures
tmp = tempfile.mkdtemp(prefix="lg-test-")
for fn in ("agent.json", "agent_analizy.json"):
    shutil.copy(os.path.join(GOLE, fn), tmp)
before = json.load(open(os.path.join(tmp, "agent.json"), encoding="utf-8"))
now = dt.datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
ag = AG.Agent(tmp, now)
check(ag.s["rules"]["pilka"].get("critic_off") == [] and ag.s["rules"]["nba"].get("critic_off") == [],
      "old agent.json loads and gets the new rule key critic_off")
n_fx = 0
for code in AG.LEAGUES:
    try:
        fx, teams = fixtures(code)
    except FileNotFoundError:
        continue
    n_fx += len(fx)
    ag.football(code, code, fx, fake_results(teams, 6))
summ = ag.finish({})
after = json.load(open(os.path.join(tmp, "agent.json"), encoding="utf-8"))
check(not ag.errors, f"no agent errors on {n_fx} real fixtures (errors: {ag.errors[:3]})")
check(abs(after["cash"] - before["cash"]) < 1e-6 or len(after["bets"]) > len(before["bets"]), "cash only changes when new bets are placed")
for k in ("calib", "luck", "critic", "insights", "skills"):
    check(k in summ, f"summary has '{k}'")
check(len(summ["skills"]) == len(AG.SKILLS) and all(s.get("status") for s in summ["skills"]), "every skill has a status line")
vet = [a for a in after["upcoming"] if a.get("veto")]
print(f"     upcoming {len(after['upcoming'])}, bets {sum(1 for a in after['upcoming'] if a['dec'] == 'bet')}, vetoed by the critic {len(vet)}")
for a in vet:
    print("     veto:", a["lg"], a["home"], "–", a["away"], a["veto"], "|", a["why"][:110])
check(all(a["dec"] == "skip" and a["why"].startswith("Krytyk zablokował") for a in vet), "vetoed matches are skipped with the critic's reason")
check(all(not a.get("veto") for a in after["upcoming"] if a["dec"] == "bet"), "no placed bet carries a veto")
check(after.get("critic_names", {}).get("rozjazd") == AG.CRITIC["rozjazd"]["name"], "critic names exported for the page")
xa = [a for a in ag.A.values() if a["sp"] == "pilka" and (a.get("tx") or {}).get("xg")]
check(all(a["tx"]["xg"][0] == 0 and sum(a["xg"]) >= AG.XG_OVER for a in xa), f"tactic „2.6+ goli → Over” picks only Overs with 2.6+ expected goals ({len(xa)} picks)")
check(not any((a.get("tx") or {}).get("xg") for a in ag.A.values() if a["sp"] == "pilka" and a.get("xg") and sum(a["xg"]) < AG.XG_OVER),
      "no „2.6+ → Over” pick below 2.6 expected goals")

# ------------------------------------------------------------------ 2) critic: each warning on hand-made candidates
base = {"id": "pilka|E0|x", "sp": "pilka", "lg": "E0", "pm": 0.50, "pk": 0.52, "mv": 0.0, "inj": None,
        "best": {"side": "Under", "odds": 2.1, "edge": 0.05}, "dec": "cand", "why": "powód"}
ag2 = AG.Agent(tempfile.mkdtemp(prefix="lg-empty-"), now)
check(ag2.warnings(dict(base), "pilka", [8, 8]) == [], "clean candidate: no warning")
check("rozjazd" in ag2.warnings(dict(base, pm=0.38, pk=0.52), "pilka", [8, 8]), "model 14 pts below market → rozjazd")
check("rynek_przeciw" in ag2.warnings(dict(base, mv=0.034), "pilka", [8, 8]), "Under while the market moved to Over (+3.4 pts) → rynek_przeciw")
check("rynek_przeciw" not in ag2.warnings(dict(base, mv=-0.05), "pilka", [8, 8]), "market moved our way → no warning")
check("kontuzje_przeciw" in ag2.warnings(dict(base, inj={"d": 0.03, "h": [], "a": []}), "pilka", [8, 8]), "injuries raise over chance by 3 pts against an Under → kontuzje_przeciw")
check("poczatek_sezonu" in ag2.warnings(dict(base), "pilka", [3, 9]), "a team with 3 games → poczatek_sezonu")
nb = {"id": "nba|1", "sp": "nba", "lg": "NBA", "pm": 0.60, "pk": 0.50, "lmed": 224.5, "line0": 226.5, "mu": 230.0, "mu_inj": 226.0,
      "best": {"side": "Over", "odds": 1.95, "edge": 0.04, "line": 224.5}, "dec": "cand", "why": "powód"}
w = ag2.warnings(dict(nb), "nba")
check("rynek_przeciw" in w and "kontuzje_przeciw" in w and "rozjazd" not in w, f"NBA: line fell 2 pts and stars out vs an Over → warnings {w}")
an = dict(base, pm=0.38)
ag2.s["rules"]["pilka"]["critic_off"] = ["rozjazd"]
ag2.review(an, "pilka", [8, 8])
check(an["dec"] == "cand" and an.get("flags_off") == ["rozjazd"] and not an.get("veto"), "switched-off warning only noted, the bet goes ahead")

# ------------------------------------------------------------------ 3) settlement, post-match verdicts, calibration, insights
st = json.load(open(os.path.join(tmp, "agent.json"), encoding="utf-8"))
A = json.load(open(os.path.join(tmp, "agent_analizy.json"), encoding="utf-8"))["rows"]
later = dt.datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
ag3 = AG.Agent(tmp, later)
open_bets = [b for b in ag3.s["bets"] if b["status"] == "open"]
by_lg = {}
for a in list(ag3.A.values()):
    if a["sp"] != "pilka":
        continue
    hg, agl = random.randint(0, 4), random.randint(0, 3)
    p_over = 0.5 + random.uniform(-0.08, 0.08)
    by_lg.setdefault(a["lg"], []).append({"d": dt.date.fromisoformat(a["date"]), "h": a["home"], "a": a["away"], "hg": hg, "ag": agl,
                                           "ouc": {"P": [round(1 / p_over * 0.98, 2), round(1 / (1 - p_over) * 0.98, 2)]}})
for code, res in by_lg.items():
    ag3.football(code, code, [], res)
s3 = ag3.finish({})
# only the bets that were open before this run: bets settled for real earlier keep their own verdicts
open_ids = {b["id"] for b in open_bets}
done = [b for b in ag3.s["bets"] if b["id"] in open_ids and b["status"] in ("won", "lost")]
check(len(done) == len(open_bets) and len(done) > 0, f"all {len(open_bets)} open football bets settle")
earlier = [b for b in ag3.s["bets"] if b["id"] not in open_ids]
check(all(b["status"] == "open" or b.get("settled") != later.isoformat(timespec="minutes") for b in earlier),
      "bets settled earlier are not settled again")
check(all(b.get("pm_cat") in AG.POSTMORTEM and b.get("lesson") for b in done), "every settled bet has a verdict and a lesson")
for b in done[:3]:
    print("     lekcja:", b["home"], "–", b["away"], b["score"], b["status"], "|", b["lesson"])
lk = s3["luck"]
n_settled = sum(1 for b in ag3.s["bets"] if b["status"] in ("won", "lost", "push"))
check(lk["n"] == n_settled and sum(lk["cats"].values()) == n_settled, f"luck summary counts every settled bet ({lk})")
c = s3["calib"].get("pilka") or {}
check(c.get("n", 0) > 50 and c.get("ll_agent") and c.get("buckets"), f"calibration on {c.get('n')} settled matches, buckets {len(c.get('buckets', []))}")
check(sum(bk["n"] for bk in c.get("buckets", [])) == c.get("n"), "calibration buckets add up")
check(set(c.get("by_league", {})) <= set(AG.LEAGUES), "calibration per league uses agent leagues")
print("     kalibracja:", {k: c[k] for k in ("n", "rate", "ll_agent", "ll_market", "ll_model", "bias", "bias_model")})
print("     wnioski:", s3["insights"])
json.dumps(s3)  # serialisable
# skills of 21.10.2026: the run log and the weekly report
rep = (ag3.s.get("weekly") or [{}])[-1]
check(rep.get("from") == "2026-10-19" and rep.get("to") == "2026-10-25" and rep.get("lines"), f"weekly report on the last finished week ({rep.get('from')}–{rep.get('to')})")
print("     raport:", " | ".join(rep.get("lines", [])))
n_rep = len(ag3.s["weekly"])
ag3b = AG.Agent(tmp, later + dt.timedelta(hours=4))
ag3b.finish({})
check(len(ag3b.s["weekly"]) == n_rep, "the weekly report is written once a week")
runs = ag3b.s.get("runs") or []
check(len(runs) >= 2 and set(runs[-1]["ok"]) == {"fd", "odds", "elo", "fpl", "espn"} and runs[-1]["at"] > runs[-2]["at"], f"every run is logged ({len(runs)} runs)")
sk = {x["key"]: x for x in ag3b.s["summary"]["skills"]}
check("zdrowie" in sk and "raport" in sk and sk["raport"]["status"].startswith("ostatni"), f"new skills on the skills card ({sk.get('raport', {}).get('status')})")

# ------------------------------------------------------------------ 4) the critic learns
def learn_case(profitable_blocks):
    d = tempfile.mkdtemp(prefix="lg-learn-")
    ag4 = AG.Agent(d, now)
    for i in range(32):  # 32 settled real bets so learning is allowed
        won = i % 2 == 0
        ag4.s["bets"].append({"id": f"pilka|E0|2026-09-{i % 28 + 1:02d}|T{i}|U{i}|ou", "sp": "pilka", "lg": "E0", "lgn": "E0", "date": "2026-09-01",
                              "ko": "2026-09-01T14:00+00:00", "home": f"T{i}", "away": f"U{i}", "side": "Under", "line": 2.5, "odds": 2.0,
                              "book": "William Hill", "book_key": "williamhill", "prob": 0.52, "edge": 0.04, "tactic": "blend", "stake": 10.0,
                              "status": "won" if won else "lost", "profit": 10.0 if won else -10.0, "payout": 20.0 if won else 0, "clv": 0.01})
    for i in range(25):  # 25 blocked picks, settled
        u = 1.1 if (profitable_blocks and i % 3 != 0) or (not profitable_blocks and i % 3 == 0) else -1.0
        ag4.A[f"pilka|E0|2026-09-{i % 28 + 1:02d}|V{i}|W{i}"] = {"id": f"pilka|E0|v{i}", "sp": "pilka", "lg": "E0", "date": "2026-09-10", "ko": "2026-09-10T14:00+00:00",
                                                               "home": f"V{i}", "away": f"W{i}", "res": [1, 1], "best": {"side": "Under", "odds": 2.1, "edge": 0.05},
                                                               "cf": {"u": u, "clv": 0.02 if profitable_blocks else -0.02}, "veto": ["rynek_przeciw"], "dec": "skip"}
    ag4.adapt()
    return ag4


ag5 = learn_case(True)
check("rynek_przeciw" in ag5.s["rules"]["pilka"]["critic_off"] and "Krytyk przestaje" in ag5.s["changes"][-1]["text"],
      "blocks that would have won → the agent switches that warning off and logs why")
print("     dziennik:", ag5.s["changes"][-1]["text"], "|", ag5.s["changes"][-1]["why"])
ag6 = learn_case(False)
check(ag6.s["rules"]["pilka"]["critic_off"] == [], "blocks that would have lost → the warning stays on")
# re-enable: warning off, bets placed despite it lose
ag7 = learn_case(True)
ag7.s["last_change"] = {}
for b in ag7.s["bets"]:
    b["flags"] = ["rynek_przeciw"]
    b["status"], b["profit"], b["clv"] = "lost", -10.0, -0.02
ag7.adapt()
check("rynek_przeciw" not in ag7.s["rules"]["pilka"]["critic_off"] and "Krytyk znów blokuje" in ag7.s["changes"][-1]["text"],
      "bets placed despite a switched-off warning lose → the warning comes back")

# ------------------------------------------------------------------ 5) backup results from ESPN (21.10.2026)
d5 = tempfile.mkdtemp(prefix="lg-espn-")
t0 = dt.datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
ag8 = AG.Agent(d5, t0)
bet = {"id": "pilka|B1|2026-10-18|Genk|Gent|ou", "sp": "pilka", "lg": "B1", "lgn": "B1", "date": "2026-10-18", "ko": "2026-10-18T14:00+00:00",
       "home": "Genk", "away": "Gent", "side": "Under", "line": 2.5, "odds": 2.0, "book": "William Hill", "book_key": "williamhill",
       "prob": 0.52, "edge": 0.04, "tactic": "blend", "stake": 10.0, "status": "open", "why": "test"}
ag8.s["bets"].append(bet)
ag8.s["cash"] -= 10.0
ag8.A["pilka|B1|2026-10-18|Genk|Gent"] = {"id": "pilka|B1|2026-10-18|Genk|Gent", "sp": "pilka", "lg": "B1", "date": "2026-10-18",
                                          "ko": "2026-10-18T14:00+00:00", "home": "Genk", "away": "Gent", "best": {"side": "Under", "odds": 2.0}, "dec": "bet",
                                          "tx": {"blend": [1, 2.0, "williamhill", 0.04]}}
ag8.finish({})
cash0 = AG.Agent(d5, t0).s["cash"]


class FakeESPN:
    def results(self, code, wanted, sim):
        return [{"d": dt.date(2026, 10, 18), "h": h, "a": a, "hg": 1, "ag": 0, "ouc": {}, "src": "ESPN"} for ko, h, a in wanted]


t1 = dt.datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
ag9 = AG.Agent(d5, t1)
check(ag9.late_matches("B1") == [("2026-10-18T14:00+00:00", "Genk", "Gent")], "late matches: the open bet and its analysis")
ag9.football("B1", "B1", [], FakeESPN().results("B1", ag9.late_matches("B1"), None))
ag9.finish({})
b9 = ag9.by_id[bet["id"]]
check(b9["status"] == "won" and b9["res_src"] == "ESPN" and b9.get("clv") is None and abs(ag9.s["cash"] - (cash0 + 20.0)) < 1e-6,
      "ESPN result settles the bet at once, without a closing price")
r9 = ag9.s["status"]["results"]["B1"]
check(r9["stale"] and r9["espn"] == 1 and r9["waiting"] == 0, f"page warning knows the match was settled from ESPN ({r9})")
# football-data catches up with a different score: the bet is corrected and gets its closing price
ag10 = AG.Agent(d5, t1 + dt.timedelta(days=1))
ag10.football("B1", "B1", [], [{"d": dt.date(2026, 10, 18), "h": "Genk", "a": "Gent", "hg": 2, "ag": 1, "ouc": {"Avg": [1.8, 2.1]}}])
ag10.finish({})
b10 = ag10.by_id[bet["id"]]
check(b10["status"] == "lost" and b10["res_src"] == "football-data" and b10.get("clv") is not None and "Poprawka" in b10.get("note", "")
      and abs(ag10.s["cash"] - cash0) < 1e-6, f"football-data score differs → bet corrected, cash back to the stake lost ({b10.get('note')})")
a10 = ag10.A["pilka|B1|2026-10-18|Genk|Gent"]
check(a10["res"] == [2, 1] and "res_src" not in a10 and a10.get("close") is not None, "analysis re-settled from football-data with the closing price")

print("\nWYNIK:", "wszystko OK" if not fails else f"{len(fails)} błędów")
sys.exit(1 if fails else 0)
