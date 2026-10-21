---
name: stan-agenta
description: Stan agenta Linii Goli w kilku zdaniach dla Radka – portfel, zakłady, Over/Under, zdrowie (źródła, błędy), raport tygodnia i czy automatyczne aktualizacje na GitHubie przechodzą. Użyj, gdy Radek pyta „co z agentem”, „jak idzie”, „stan”, albo na początku rozmowy o agencie.
---

# Stan agenta (Linia Goli)

Tylko czytasz – niczego nie zmieniasz i nie wypychasz.

1. Pobierz najnowsze dane: `git fetch origin main` i pracuj na `origin/main` (bot commituje co 4 godziny).
   Gdy jesteś na innej gałęzi, czytaj plik z main: `git show origin/main:gole/agent.json > /tmp/agent-main.json`
   i `python3 gole/stan.py /tmp/agent-main.json`; na `main`: `git pull && python3 gole/stan.py`.
2. Ostatnie przebiegi „Linia Goli – aktualizacja danych”: narzędzie GitHub MCP `actions_list`
   (`list_workflow_runs`, plik `linia-goli.yml`, 5 ostatnich) albo
   `curl -s "https://api.github.com/repos/rzarzycki98-hash/Radek/actions/workflows/linia-goli.yml/runs?per_page=5"`.
   Gdy któryś ma `conclusion` inne niż `success` – przeczytaj log (`get_job_logs`) i powiedz, co się stało.
3. Odpowiedz Radkowi po polsku, prosto, z liczbami, najwyżej kilkanaście linijek:
   - portfel i wynik od startu, rozliczone / otwarte zakłady, „vs zamknięcie”;
   - Over/Under (licznik z `stan.py`) – czy agent gra obie strony;
   - zdrowie: źródła z problemem, błędy agenta, zapytania o kursy do końca miesiąca, stare wyniki lig;
   - ostatni raport tygodnia (jeśli jest) w 2–3 zdaniach;
   - co wymaga uwagi (lista „Do sprawdzenia” z `CLAUDE.md`, sekcja „Na czym skończyliśmy”).
4. ClubElo nie działa od 17.10.2026 (awaria po ich stronie) – nie traktuj tego jako nowego błędu, chyba że zacznie działać.
