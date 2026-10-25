#!/bin/bash
# Claude Code hook (SessionStart): installs gstack (github.com/garrytan/gstack, 60+ skills) in cloud sessions.
# gstack is not a plugin: it lives in ~/.claude/skills/gstack, and a cloud container starts empty every session.
# Fetch + ./setup takes ~40 s, so it runs in the background; Claude Code picks the skills up when it finishes.
# Pinned to a reviewed commit (25.10.2026), so new upstream code never runs here unseen; to update, change GSTACK_SHA.
# On a personal computer it does nothing (install it there once by hand, see gstack README).
[ "$CLAUDE_CODE_REMOTE" = "true" ] || exit 0
GSTACK_SHA=072d073b120b976e805a6b55e7004d71cbe6d43c
G="$HOME/.claude/skills/gstack"
[ -d "$G/bin" ] && exit 0
LOG="$HOME/.claude/gstack-install.log"
nohup bash -c "git init -q '$G' && cd '$G' && git fetch -q --depth 1 https://github.com/garrytan/gstack.git $GSTACK_SHA \
  && git checkout -q FETCH_HEAD && [ \"\$(git rev-parse HEAD)\" = $GSTACK_SHA ] && ./setup </dev/null" >"$LOG" 2>&1 &
exit 0
