---
name: find-skills
description: Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extending capabilities. This skill should be used when the user is looking for functionality that might exist as an installable skill.
---

# Find Skills

This skill helps you discover and install skills from the open agent skills ecosystem.

## When to Use This Skill

Use this skill when the user:

- Asks "how do I do X" where X might be a common task with an existing skill
- Says "find a skill for X" or "is there a skill for X"
- Asks "can you do X" where X is a specialized capability
- Expresses interest in extending agent capabilities
- Wants to search for tools, templates, or workflows
- Mentions they wish they had help with a specific domain (design, testing, deployment, etc.)

## What is the Skills CLI?

The Skills CLI (`npx skills`) is the package manager for the open agent skills ecosystem. Skills are modular packages that extend agent capabilities with specialized knowledge, workflows, and tools.

**Key commands:**

- `npx skills find [query] [--owner <owner>]` - Search for skills interactively or by keyword, optionally scoped to a GitHub owner
- `npx skills add <package>` - Install a skill from GitHub or other sources
- `npx skills update` - Update all installed skills

**Browse skills at:** https://skills.sh/

## How to Help Users Find Skills

### Step 1: Understand What They Need

When a user asks for help with something, identify:

1. The domain (e.g., React, testing, design, deployment)
2. The specific task (e.g., writing tests, creating animations, reviewing PRs)
3. Whether this is a common enough task that a skill likely exists

### Step 2: Check the Leaderboard First

Before running a CLI search, check the [skills.sh leaderboard](https://skills.sh/) to see if a well-known skill already exists for the domain. The leaderboard ranks skills by total installs, surfacing the most popular and battle-tested options.

For example, top skills for web development include:
- `vercel-labs/agent-skills` — React, Next.js, web design (100K+ installs each)
- `anthropics/skills` — Frontend design, document processing (100K+ installs)

### Step 3: Search for Skills

If the leaderboard doesn't cover the user's need, run the find command:

```bash
npx skills find [query] [--owner <owner>]
```

For example:

- User asks "how do I make my React app faster?" → `npx skills find react performance`
- User asks "can you help me with PR reviews?" → `npx skills find pr review`
- User asks "I need to create a changelog" → `npx skills find changelog`

### Step 4: Verify Quality Before Recommending

**Do not recommend a skill based solely on search results.** Always verify:

1. **Install count** — Prefer skills with 1K+ installs. Be cautious with anything under 100.
2. **Source reputation** — Official sources (`vercel-labs`, `anthropics`, `microsoft`) are more trustworthy than unknown authors.
3. **GitHub stars** — Check the source repository. A skill from a repo with <100 stars should be treated with skepticism.

### Step 5: Present Options to the User

When you find relevant skills, present them to the user with:

1. The skill name and what it does
2. The install count and source
3. The install command they can run
4. A link to learn more at skills.sh

Example response:

```
I found a skill that might help! The "react-best-practices" skill provides
React and Next.js performance optimization guidelines from Vercel Engineering.
(185K installs)

To install it:
npx skills add vercel-labs/agent-skills@react-best-practices

Learn more: https://skills.sh/vercel-labs/agent-skills/react-best-practices
```

### Step 6: Offer to Install

If the user wants to proceed, you can install the skill for them:

```bash
npx skills add <owner/repo@skill> -g -y
```

The `-g` flag installs globally (user-level) and `-y` skips confirmation prompts.

## Common Skill Categories

When searching, consider these common categories:

| Category        | Example Queries                          |
| --------------- | ---------------------------------------- |
| Web Development | react, nextjs, typescript, css, tailwind |
| Testing         | testing, jest, playwright, e2e           |
| DevOps          | deploy, docker, kubernetes, ci-cd        |
| Documentation   | docs, readme, changelog, api-docs        |
| Code Quality    | review, lint, refactor, best-practices   |
| Design          | ui, ux, design-system, accessibility     |
| Productivity    | workflow, automation, git                |

## Tips for Effective Searches

1. **Use specific keywords**: "react testing" is better than just "testing"
2. **Try alternative terms**: If "deploy" doesn't work, try "deployment" or "ci-cd"
3. **Check popular sources**: Many skills come from `vercel-labs/agent-skills` or `ComposioHQ/awesome-claude-skills`

## When No Skills Are Found

If no relevant skills exist:

1. Acknowledge that no existing skill was found
2. Offer to help with the task directly using your general capabilities
3. Suggest the user could create their own skill with `npx skills init`

Example:

```
I searched for skills related to "xyz" but didn't find any matches.
I can still help you with this task directly! Would you like me to proceed?

If this is something you do often, you could create your own skill:
npx skills init my-xyz-skill
```

---

## Poprawka dla tego repo: sesje w chmurze (dopisane 4.11.2026)

Wszystko powyżej to oryginał od Vercel (vercel-labs/skills, licencja MIT), bez zmian. Ta sekcja to lokalna poprawka –
przy ponownym kopiowaniu oryginału zachowaj ją. Pilnuje jej test `.claude/testy/test_skille.py`.

To repo działa w sesjach Claude Code w chmurze (przeglądarka, aplikacja na telefonie, rutyny). Tam dwa kroki oryginału
nie działają jak na komputerze, więc **te zasady mają pierwszeństwo przed krokami wyżej**:

1. **Szukanie.** `npx skills find` łączy się ze stroną skills.sh. Gdy kończy się błędem sieci (np. 403, „host not
   allowed”, brak połączenia), środowisko blokuje skills.sh. Wtedy:
   - powiedz Radkowi raz, krótko, jak to odblokować: menu środowiska w pasku tytułu sesji → Edit cloud environment →
     Network access: **Custom** → w Allowed domains dwie linie: `skills.sh` i `www.skills.sh` → zaznacz
     **Also include default list of common package managers** (bez tego przestaną działać npm, pip i reszta) → zapisz;
   - nie czekaj na to – szukaj dalej sam: WebSearch z zapytaniem `skills.sh <słowa kluczowe> skill`, a treść kandydatów
     czytaj z GitHuba (w chmurze działa), np. `git clone --depth 1 https://github.com/<owner>/<repo>` do folderu
     tymczasowego. Liczby instalacji bierz z wyników wyszukiwania i oznacz je jako przybliżone.
2. **Instalacja.** **Nigdy z `-g`.** Folder domowy sesji w chmurze znika po rozmowie, więc skill zainstalowany z `-g`
   działa tylko do jej końca. Instaluj do repo (powstaje `.claude/skills/<nazwa>/` i `skills-lock.json`):

   ```bash
   npx skills add <owner/repo> --skill <nazwa> -a claude-code --copy -y
   ```

   Potem `python3 .claude/testy/test_skille.py`, a commit i push na `main` dopiero po „tak” Radka (zasady pushu
   z `CLAUDE.md`: najpierw `git fetch origin main && git rebase origin/main`). Każdy nowy skill to kolejny opis
   wczytywany na start każdej rozmowy – instaluj tylko to, co Radek naprawdę wybrał.
3. **Bezpieczeństwo przed poleceniem.** Skille działają z pełnymi uprawnieniami agenta, a w sieci są podróbki popularnych
   skilli (także find-skills). Zanim polecisz albo zainstalujesz, przeczytaj SKILL.md i wszystkie skrypty kandydata.
   Odrzuć skill, który: wysyła gdzieś dane (nazwę komputera, zmienne środowiska, klucze, pliki), pobiera i uruchamia kod
   z sieci (np. `curl … | bash`), prosi o hasła albo klucze API, albo ukrywa polecenia. Bierz oryginał z repo autora
   (najwięcej instalacji), nie kopię. Po odblokowaniu `www.skills.sh` polecenie `npx skills add` pokazuje też tabelę
   audytów bezpieczeństwa – przekaż Radkowi jej wynik.
4. **Tylko darmowe.** Pomijaj skille, które wymagają płatnego konta albo płatnego klucza API, albo wyraźnie to oznacz.
