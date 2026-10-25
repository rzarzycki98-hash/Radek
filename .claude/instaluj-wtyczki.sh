#!/bin/bash
# Installs the third-party Claude Code plugins enabled in .claude/settings.json (user scope).
# Cloud sessions run with SKIP_PLUGIN_MARKETPLACE=true: marketplaces declared in project settings are never fetched,
# so only the official Anthropic plugins load. Plugins installed before Claude Code starts do load, hence this script
# belongs in the cloud environment's setup script (see CLAUDE.md). Installing mid-session does not help: plugins
# are read once at startup.
# Each marketplace is cloned at the commit pinned in settings ("ref") and added as a local marketplace, so a new,
# unreviewed commit upstream never runs here. Usage: bash instaluj-wtyczki.sh [path/to/settings.json]
set -u
command -v claude >/dev/null || { echo "instaluj-wtyczki: no claude CLI, skipping"; exit 0; }
SETTINGS="${1:-}"
if [ -z "$SETTINGS" ]; then
  SETTINGS=$(mktemp)
  curl -fsSL https://raw.githubusercontent.com/rzarzycki98-hash/Radek/main/.claude/settings.json -o "$SETTINGS" || exit 0
fi
python3 - "$SETTINGS" "$HOME/.claude/marketplaces-radek" <<'EOF'
import json, os, re, subprocess, sys
cfg = json.load(open(sys.argv[1]))
base = sys.argv[2]
os.makedirs(base, exist_ok=True)
run = lambda *a: subprocess.run(a, capture_output=True, text=True)
ok = fail = 0
for name, m in cfg.get("extraKnownMarketplaces", {}).items():
    src = m["source"]
    if name == "claude-plugins-official" or src.get("source") != "github":
        continue  # official plugins are preinstalled in the cloud
    plugins = [k.split("@")[0] for k, on in cfg.get("enabledPlugins", {}).items() if on and k.endswith("@" + name)]
    if not plugins:
        continue
    d = os.path.join(base, name)
    if src["repo"].startswith("anthropics/"):
        d = src["repo"]  # names of Anthropic marketplaces are reserved for their GitHub source
    elif not os.path.isdir(d):
        r = run("git", "clone", "-q", "--filter=blob:none", f"https://github.com/{src['repo']}", d)
        if r.returncode:
            print(f"instaluj-wtyczki: clone {src['repo']} failed: {r.stderr.strip()}"); fail += len(plugins); continue
    if os.path.isdir(d):
        ref = src.get("ref", "")
        if not re.fullmatch(r"[0-9a-f]{40}", ref) or run("git", "-C", d, "checkout", "-q", "--detach", ref).returncode \
                or run("git", "-C", d, "rev-parse", "HEAD").stdout.strip() != ref:
            print(f"instaluj-wtyczki: {name} not pinned to a full commit ({ref or 'no ref'}), skipped")
            fail += len(plugins); continue
    run("claude", "plugin", "marketplace", "add", d)
    for p in plugins:
        r = run("claude", "plugin", "install", f"{p}@{name}")
        if r.returncode:
            fail += 1; print(f"instaluj-wtyczki: {p}@{name}: {(r.stdout + r.stderr).strip().splitlines()[-1:]}")
        else:
            ok += 1
print(f"instaluj-wtyczki: installed {ok}, failed {fail}")
EOF
exit 0
