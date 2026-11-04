"""Offline test of the Claude skills in .claude/skills (added 4.11.2026).
Every skill folder needs a SKILL.md with a valid header; find-skills must keep the Vercel original
and the cloud-session fix for this repo (install into the repo, never -g; fallback search when skills.sh is blocked).
No internet, no extra packages.
Usage: python3 .claude/testy/test_skille.py            (or give the repo root as the first argument)
"""
import os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILLS = os.path.join(ROOT, ".claude", "skills")
FIX_HEADING = "## Poprawka dla tego repo: sesje w chmurze"
fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def header(text):
    """Return the YAML header of a SKILL.md as a dict of its top-level 'key: value' lines, or None."""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None
    out = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and line[:1] not in (" ", "\t", "#"):
            out[key.strip()] = value.strip().strip("'\"")
    return out


# ------------------------------------------------------------------ 1) every skill: SKILL.md with name + description
names = sorted(d for d in os.listdir(SKILLS) if os.path.isdir(os.path.join(SKILLS, d)))
check(len(names) >= 5, f"{len(names)} skills in .claude/skills")
for name in names:
    path = os.path.join(SKILLS, name, "SKILL.md")
    if not os.path.isfile(path):
        check(False, f"{name}: has SKILL.md")
        continue
    text = open(path, encoding="utf-8").read()
    h = header(text)
    check(h is not None, f"{name}: SKILL.md starts with a --- header ---")
    if h is None:
        continue
    check(h.get("name") == name, f"{name}: header name matches the folder (got {h.get('name')!r})")
    check(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) is not None and len(name) <= 64,
          f"{name}: lowercase-with-dashes name, max 64 characters")
    desc = h.get("description", "")
    check(20 <= len(desc) <= 1024, f"{name}: description has 20-1024 characters (has {len(desc)})")
    check("{" + "{" not in text and "{" + "%" not in text, f"{name}: no Jekyll braces (GitHub Pages rule in CLAUDE.md)")

# ------------------------------------------------------------------ 2) find-skills: Vercel original + cloud fix
fs = open(os.path.join(SKILLS, "find-skills", "SKILL.md"), encoding="utf-8").read()
original, _, fix = fs.partition(FIX_HEADING)
fix = " ".join(fix.split())  # Markdown wraps long lines; compare text with single spaces, like it renders
check(fs.count(FIX_HEADING) == 1, "find-skills: has the cloud-session fix section, once")
check(all(s in original for s in ("npx skills find", "### Step 4: Verify Quality Before Recommending", "### Step 6: Offer to Install")),
      "find-skills: the Vercel original is still above the fix")
check("-a claude-code --copy -y" in fix, "find-skills: installs into the repo (-a claude-code --copy -y)")
check("Nigdy z `-g`" in fix, "find-skills: forbids -g in cloud sessions")
check("`skills.sh`" in fix and "`www.skills.sh`" in fix and "Also include default list of common package managers" in fix,
      "find-skills: explains how to unblock skills.sh and keep the default list")
check("WebSearch" in fix and "git clone --depth 1" in fix, "find-skills: fallback search when skills.sh is blocked")
check("curl" in fix and "klucze API" in fix, "find-skills: safety check before recommending")
check("test_skille.py" in fix, "find-skills: runs this test before committing a new skill")

print()
print("RESULT:", "all OK" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
