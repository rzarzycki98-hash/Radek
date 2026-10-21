---
name: sprawdz-rozliczenia
description: Sprawdzenie, czy zakłady agenta Linii Goli rozliczają się poprawnie – wyniki z football-data i zapasowe z ESPN, „vs zamknięcie”, ocena po meczu, stare wyniki lig, poprawki. Użyj po weekendzie meczów albo gdy Radek pyta, czemu coś się nie rozliczyło.
---

# Sprawdzenie rozliczeń

Tylko czytasz `gole/agent.json` i `gole/agent_analizy.json` (najnowsze z `origin/main`). Nie edytuj ich ręcznie.

1. `git fetch origin main`; dane: `git show origin/main:gole/agent.json` i `git show origin/main:gole/agent_analizy.json`.
2. Sprawdź w Pythonie (krótki skrypt, wynik w kilku liniach):
   - zakłady `status == "open"` z `ko` starszym niż 2 dni – czekają na wynik (ile, z jakich lig);
   - `status.results` – ligi z `stale: true` (ostatni wynik football-data starszy niż 3 dni, a mecze czekają);
   - zakłady z `res_src == "ESPN"` (rozliczone z zapasu; CLV dopisze się, gdy football-data opublikuje mecz)
     i z `note` zawierającym „Poprawka” (ESPN i football-data podały inny wynik);
   - rozliczone bez `clv` albo bez `pm_cat` / `lesson` – to byłby błąd;
   - `clv_src` – skąd liczone „vs zamknięcie” (Pinnacle / giełda Betfair / średnia rynku).
3. Gdy coś wygląda na błąd w kodzie: znajdź przyczynę w `gole/agent.py` (`settle_football`, `post_mortem`) albo
   `gole/engine.py` / `gole/zrodla.py` (`ESPNScores`), napraw, uruchom `python3 gole/testy/test_skills.py`
   i dopiero wtedy wypchnij (zasady w `CLAUDE.md`). Opóźnienie po stronie football-data to nie błąd.
4. Raport dla Radka po polsku, prosto: co się rozliczyło, co czeka i dlaczego, czy wszystko gra.
