#!/bin/bash
# Claude Code hook (SessionStart): installs gstack (github.com/garrytan/gstack, 60+ skills) in cloud sessions.
# gstack is not a plugin: it lives in ~/.claude/skills/gstack, and a cloud container starts empty every session.
# Clone + ./setup takes ~40 s, so it runs in the background; Claude Code picks the skills up when it finishes.
# On a personal computer it does nothing (install it there once by hand, see gstack README).
[ "$CLAUDE_CODE_REMOTE" = "true" ] || exit 0
G="$HOME/.claude/skills/gstack"
[ -d "$G/bin" ] && exit 0
LOG="$HOME/.claude/gstack-install.log"
nohup bash -c "git clone -q --single-branch --depth 1 https://github.com/garrytan/gstack.git '$G' && cd '$G' && ./setup </dev/null" >"$LOG" 2>&1 &
exit 0
