"""Claude Code hook (PreToolUse): guards the rules from CLAUDE.md, so they do not depend on memory alone.

Blocks (exit code 2, the reason goes back to Claude):
  - running gole/engine.py with the real output folder (no --out, or --out gole) – it would overwrite the agent's state,
  - editing gole/agent.json or gole/agent_analizy.json by hand (Edit/Write, or shell redirection, sed -i, rm, mv/cp onto them),
  - git push --force / -f / --force-with-lease / +refspec.
Reading these files, copying them elsewhere and running the engine into a temporary folder stay allowed.
"""
import json, os, re, shlex, sys

STATE = re.compile(r"(^|[\s/'\"=])gole/agent(_analizy)?\.json\b")


def deny(why):
    print(f"Zablokowane przez bezpiecznik projektu (.claude/hooks/straznik.py): {why}", file=sys.stderr)
    sys.exit(2)


def engine_out_is_real(cmd):
    for m in re.finditer(r"python[\d.]*\s+(?:-\S+\s+)*(\S*engine\.py)\b([^;&|]*)", cmd):
        args = m.group(2)
        out = re.search(r"--out[=\s]+(\S+)", args)
        if not out:
            return True  # the default output folder is gole/ itself
        path = out.group(1).strip("'\"").rstrip("/")
        if path in ("gole", "./gole") or os.path.abspath(path) == os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()), "gole"):
            return True
    return False


def writes_state(cmd):
    for part in re.split(r"&&|\|\||;|\|", cmd):
        if not STATE.search(part):
            continue
        if re.search(r">>?\s*\S*gole/agent(_analizy)?\.json", part) or re.search(r"\btee\b", part):
            return True
        try:
            words = shlex.split(part)
        except ValueError:
            words = part.split()
        if not words:
            continue
        prog = os.path.basename(words[0])
        if prog == "sed" and any(w.startswith("-i") for w in words[1:]):
            return True
        if prog in ("rm", "truncate", "shred"):
            return True
        if prog in ("mv", "cp", "install", "ln") and STATE.search(" " + words[-1]):
            return True  # the state file is the target
        if prog == "mv":
            return True  # moving it away loses the state
    return False


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tool, inp = data.get("tool_name", ""), data.get("tool_input") or {}
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        path = str(inp.get("file_path") or inp.get("notebook_path") or "")
        if STATE.search(" " + path.replace(os.sep, "/")):
            deny("gole/agent.json i gole/agent_analizy.json zmienia tylko kod agenta – ręczna edycja rozjedzie portfel (CLAUDE.md).")
        return
    if tool != "Bash":
        return
    cmd = str(inp.get("command") or "")
    if engine_out_is_real(cmd):
        deny("engine.py bez --out albo z --out gole nadpisałby prawdziwy stan agenta. Testuj do folderu tymczasowego: "
             "--out /tmp/... (CLAUDE.md, „Zasady pracy”).")
    if writes_state(cmd):
        deny("polecenie zmienia gole/agent.json albo gole/agent_analizy.json. Te pliki zmienia tylko agent na GitHub Actions; "
             "do testów skopiuj je do folderu tymczasowego.")
    pushes = [m.group(1) for m in re.finditer(r"\bgit\b(?:\s+-C\s+\S+)?\s+push\b([^;&|\n]*)", cmd)]
    if any(re.search(r"(\s--force(-with-lease)?\b|\s-[a-zA-Z]*f[a-zA-Z]*\b|\s\+\S+)", " " + x) for x in pushes):
        deny("force push jest zabroniony (bot commituje co 4 godziny). Zrób git fetch origin main && git rebase origin/main i zwykły push.")


if __name__ == "__main__":
    main()
