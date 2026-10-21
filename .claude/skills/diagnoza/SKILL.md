---
name: diagnoza
description: Test modelu goli Linii Goli na historii (11 lig, 6 sezonów, walk-forward) i sprawdzenie źródeł danych (ClubElo, football-data, ESPN, The Odds API) z GitHub Actions – bo chmura Claude tych stron nie widzi. Użyj, gdy trzeba sprawdzić model, kalibrację, wagę modelu, CLV na historii albo czemu źródło danych nie działa.
---

# Diagnoza (przebieg „Linia Goli – diagnoza”, tylko odczyt)

Skrypty: `gole/testy/historia.py` (model na historii) i `gole/testy/diagnoza_zrodel.py` (źródła).
Workflow: `.github/workflows/linia-goli-diagnoza.yml` – nic nie zapisuje w repozytorium, wynik jest w logu.

1. Lokalnie najpierw sprawdź, czy skrypt działa, na danych symulowanych: `python3 gole/testy/historia.py --local DIR
   --today RRRR-MM-DD --only E0,SP1` (pliki `DIR/data/<kod>/season-XXYY.csv` w formacie football-data).
2. Uruchom przebieg: wypchnij zmianę `historia.py` albo `diagnoza_zrodel.py` na gałąź `claude/...` (uruchamia się sam)
   albo ręcznie: GitHub MCP `actions_run_trigger` z plikiem `linia-goli-diagnoza.yml`.
   Sprawdzenie The Odds API zużywa 1 zapytanie z miesięcznego limitu – nie uruchamiaj go bez potrzeby.
3. Poczekaj na koniec (np. pętla `curl` na `.../actions/runs/<id>` w tle, aż `"status": "completed"`), potem
   GitHub MCP `get_job_logs` (`return_content: true`) i przeczytaj wynik.
4. Wnioski dla Radka: liczby przed/po, log loss vs rynek, liczba typów Over/Under, wynik i CLV na historii.
   Nie dopasowuj niczego do kilku ostatnich wyników; progów i taktyk agenta nie zmieniaj bez pytania Radka.
