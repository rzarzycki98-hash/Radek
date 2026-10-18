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

## Agent – obstawia sam i uczy się na swoich zakładach

Cała strona Linii Goli jest zbudowana wokół agenta: https://rzarzycki98-hash.github.io/Radek/gole/

- **Agent** (start): portfel, wykres salda, co agent gra dziś i jutro, wyniki ostatnich zakładów.
- **Mecze:** każdy mecz z oceną agenta i powodem decyzji; mecz piłkarski otwiera pełną analizę.
- **Nauka:** która taktyka działa, czego agent się nauczył, jego zasady, dziennik zmian i źródła danych.
- **Wyniki:** wszystkie rozliczone zakłady, miesiąc po miesiącu, trafność prognoz.
- **Ligi:** jak agentowi idzie w każdej lidze, tabela drużyn (w NBA: atak i obrona drużyn).

Agent działa sam, razem z resztą aplikacji (co 4 godziny, GitHub Actions). Gra tylko wirtualnymi pieniędzmi.

- **Portfel:** £1000 na start, wspólny dla piłki i NBA. Stawka 1% aktualnego portfela, najwyżej 30% portfela w grze naraz.
- **Piłka:** gole over/under 2.5 w 11 ligach: Premier League, LaLiga, Serie A, Bundesliga, Ligue 1, Eredivisie, Liga Portugal,
  Pro League, Süper Lig, szkocka Premiership i grecka Super League. Kursy: William Hill, Grosvenor, Casumo i LeoVegas
  (w darmowych danych tylko oni podają over/under; Ladbrokes i BetVictor mają tam tylko wynik 1X2).
- **NBA:** suma punktów over/under. Wyniki i terminarz z ESPN (za darmo), kursy Ladbrokes i BetVictor, a gdy nie mają linii –
  inny bukmacher z UK. Model: atak i obrona każdej drużyny w punktach, starsze mecze ważą mniej. Agent gra od 5. meczu drużyny w sezonie.
- **Dodatkowe darmowe dane:** siła drużyn z [ClubElo](http://clubelo.com), kontuzje w Premier League (Fantasy Premier League)
  i w NBA (raport ESPN + najlepsi strzelcy każdej drużyny), zmęczenie w NBA (mecz dzień po dniu) i ruchy kursów od pierwszego odczytu.
  Każde z nich ma własną taktykę na sucho – agent przenosi na nią pieniądze dopiero, gdy się sprawdzi.
- **Każdy mecz oceniony:** agent zapisuje szansę, najlepszy kurs, decyzję i powód. Stawia tylko wtedy, gdy kurs jest wyższy, niż wynika z szansy.
  Po meczu sam rozlicza zakład i sprawdza, czy wziął kurs lepszy niż kurs zamknięcia.
- **Taktyki:** kilka taktyk typuje równolegle na sucho (np. „Model + rynek”, „Sam model”, „Statystyki potwierdzają”, „Duża przewaga”,
  w NBA „Zmęczenie” – mecz dzień po dniu). Gdy któraś jest wyraźnie lepsza (50+ typów w piłce, 80+ w NBA, zysk i kurs lepszy niż zamknięcie),
  agent przenosi na nią pieniądze.
- **Nauka:** po 30 rozliczonych zakładach agent sam zmienia swoje zasady: wyłącza ligi i strony, na których przegrywa (i włącza je z powrotem,
  gdy typy na sucho zaczną wygrywać), podnosi albo obniża wymaganą przewagę, zawęża kursy, w NBA zmienia zaufanie do własnego modelu.
  Najwyżej jedna zmiana na tydzień. Każda zmiana trafia do dziennika z powodem – można się uczyć razem z agentem.
- **Gotowość na prawdziwe pieniądze** (tylko informacja): 3+ miesiące gry, 200+ rozliczonych zakładów, portfel na plusie i kursy lepsze niż zamknięcie.

### Skille agenta (od 18.10.2026)

Lista wszystkich umiejętności agenta jest na stronie: zakładka **Nauka → Skille agenta**. Nowe:

- **Krytyk** – drugi, niezależny „agent” sprawdza każdy zakład przed postawieniem i blokuje podejrzane: gdy model i rynek
  bardzo się różnią, gdy kursy ruszyły przeciwko, gdy kontuzje wskazują drugą stronę, na początku sezonu i w lidze, której
  agent słabo zna. Zablokowane typy śledzi na sucho i sam wyłącza blokady, które przeszkadzają (i włącza je z powrotem).
- **Analiza po meczu** – każdy rozliczony zakład dostaje ocenę: zasłużona wygrana, szczęście, pech albo błąd ceny, oraz krótką
  lekcję. Karta „Szczęście czy umiejętność?” porównuje wynik z „uczciwym” wynikiem według kursów zamknięcia.
- **Kalibracja** – czy szanse agenta się sprawdzają: gdy mówi 60%, czy over wchodzi mniej więcej w 6 meczach na 10;
  porównanie z rynkiem, też w każdej lidze.
- **Wnioski** – agent sam wypisuje prostym językiem, gdzie zarabia, a gdzie traci.

Testy skilli (na kopiach, nie ruszają prawdziwego stanu): `python3 gole/testy/test_skills.py`, strona:
`gole/testy/test_page.py` (Playwright).

| Plik | Do czego służy |
| --- | --- |
| `gole/agent.py` | agent: portfel, decyzje, rozliczanie, taktyki, nauka |
| `gole/nba.py` | NBA: wyniki, najlepsi strzelcy i kontuzje z ESPN, model sumy punktów, kursy |
| `gole/zrodla.py` | siła drużyn z ClubElo i dopasowanie nazw drużyn |
| `gole/stan.py` | stan agenta w kilku linijkach: `python3 gole/stan.py` |
| `CLAUDE.md` | notatki dla Claude: ustalenia, jak działa projekt i na czym skończyliśmy |
| `gole/agent.json` | portfel, zakłady, zasady i dziennik zmian (czyta go strona) |
| `gole/agent_analizy.json` | ocena każdego meczu i jego wynik – dane do nauki |
