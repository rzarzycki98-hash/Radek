# Radek

Moje repozytorium na projekty, kod i notatki.

## Listy – aplikacja na telefon

Prosta aplikacja PWA z dwiema listami: **Zadania** i **Zakupy**.

- dodawanie, odhaczanie i usuwanie pozycji
- przycisk „Usuń zrobione”
- dane zapisują się w telefonie, aplikacja działa bez internetu
- jasny i ciemny motyw (zgodnie z ustawieniami telefonu)

Adres aplikacji: https://rzarzycki98-hash.github.io/Radek/

### Instalacja na telefonie

- **Android (Chrome):** otwórz adres → menu ⋮ → „Zainstaluj aplikację” lub „Dodaj do ekranu głównego”.
- **iPhone (Safari):** otwórz adres → przycisk Udostępnij → „Do ekranu początkowego”.

### Pliki

| Plik | Do czego służy |
| --- | --- |
| `index.html` | wygląd strony |
| `style.css` | kolory i układ |
| `app.js` | działanie list i zapis danych |
| `manifest.webmanifest` | nazwa i ikona aplikacji na telefonie |
| `sw.js` | działanie offline |
| `icons/` | ikony aplikacji |

### Uruchomienie na komputerze

```bash
git clone https://github.com/rzarzycki98-hash/Radek.git
cd Radek
python3 -m http.server 8000
```

Potem otwórz http://localhost:8000 w przeglądarce.

## Autor

Radek ([@rzarzycki98-hash](https://github.com/rzarzycki98-hash))

## Linia Goli – analiza meczów piłkarskich

Aplikacja do analizy meczów w 38 ligach: gole over/under i wynik 1X2.

Adres: https://rzarzycki98-hash.github.io/Radek/gole/

Działa sama. Co 4 godziny GitHub Actions (`.github/workflows/linia-goli.yml`) uruchamia `gole/engine.py`:

1. **Dane:** wyniki i kursy z [football-data.co.uk](https://www.football-data.co.uk) (22 ligi z Europy z kilkoma poziomami
   rozgrywek i 16 lig ze świata, w tym Ekstraklasa, Brazylia, MLS), terminarz i kursy bukmacherów z UK z
   [The Odds API](https://the-odds-api.com) (sekret `ODDS_API_KEY`). Zakończone sezony pobierane są raz i trzymane w pamięci
   podręcznej GitHuba. Płatne zapytania o kursy są dzielone tak, żeby zmieścić się w darmowym limicie (500 na miesiąc).
2. **Nauka:** przy każdej aktualizacji model (Poisson z poprawką Dixona-Colesa, gole i strzały celne, starsze mecze ważą mniej)
   sam dobiera ustawienia każdej ligi na jej najnowszych wynikach, a potem łączy swoje szanse z kursami rynku
   w proporcji, która w danej lidze najlepiej się sprawdzała.
3. **Uczciwy test:** każda liga jest sprawdzana na ostatnich sezonach w trybie „krok po kroku”: ustawienia dobierane są tylko
   na danych sprzed sprawdzanego sezonu. Liczy się wynik zakładów i to, czy kurs był lepszy niż uczciwy kurs zamknięcia
   (Pinnacle bez marży).
4. **Bezpiecznik:** liga dostaje ocenę „Sprawdzona”, „Obiecująca”, „Nie bije rynku” albo „Za mało danych”. Gdy w dzienniku typy
   przegrywają z kursem zamknięcia, liga sama się wyłącza.
5. **Po meczu:** każdy wyceniony mecz rozlicza się sam (zakładka Wyniki), a typy na sucho w dzienniku (zakładka Typy).
   Rozliczone mecze są zapisywane na stałe, więc w Wynikach widać bilans każdego sezonu.

Uczciwie: w dużych ligach kursy bukmacherów są bardzo trafne i model zwykle ich nie pokonuje. Wszystkie typy są tylko na sucho,
a aplikacja pokazuje wprost, gdzie działa, a gdzie nie. Pomoc przy problemach z hazardem:
[BeGambleAware](https://www.begambleaware.org), GamCare 0808 8020 133.

| Plik | Do czego służy |
| --- | --- |
| `gole/index.html` | aplikacja |
| `gole/engine.py` | pobieranie danych, model, nauka, test lig, dziennik |
| `gole/data.json` | mecze, typy i oceny lig (tworzone automatycznie) |
| `gole/journal.json` | dziennik typów na sucho |
| `gole/predictions.json` | prognozy z ostatnich 120 dni i ich rozliczenie po meczu |
| `gole/archiwum/` | starsze rozliczone prognozy, po jednym pliku na miesiąc (zapisane na stałe) |
| `gole/odds_cache.json` | ostatnie kursy bukmacherów (żeby oszczędzać limit) |
