# Repozytorium „Radek” – notatki dla Claude

Ten plik Claude czyta na początku każdej rozmowy z tym repozytorium. Mówi, co tu jest, co ustaliliśmy z Radkiem
i na czym skończyliśmy. **Na koniec każdej sesji pracy zaktualizuj sekcję „Na czym skończyliśmy”** (data, co zrobione,
co sprawdzić) i wypchnij zmianę.

## Na czym skończyliśmy – 18.10.2026

18.10.2026 Radek poprosił o **skille** (umiejętności) dla agenta – zainspirowane grafiką „AI Agent Skills You Must Learn”
(tool calling, memory, RAG, multi-agent). Dodaliśmy cztery, wszystkie w `gole/agent.py`, widoczne na stronie (Nauka → Skille agenta):

- **Krytyk** (multi-agent): drugi, niezależny przegląd każdego zakładu przed postawieniem (`Agent.warnings`/`review`).
  5 ostrzeżeń, każde blokuje zakład: `rozjazd` (model i rynek różnią się o 12+ pkt proc., NBA 20+), `rynek_przeciw`
  (kursy ruszyły w drugą stronę o 3+ pkt proc., NBA linia o 1.5+ pkt), `kontuzje_przeciw`, `poczatek_sezonu` (drużyna < 4 mecze),
  `slaba_liga` (na 60+ rozliczonych ocenach ligi agent gorszy od rynku). Zablokowane mecze mają `veto` w ocenie i są śledzone
  na sucho (`cf`). Krok nauki `step_critic` (zaraz po zmianie taktyki): 20+ zablokowanych z zyskiem i CLV > 0 → blokada
  wyłączona (`rules.<sport>.critic_off`); zakłady postawione mimo wyłączonego ostrzeżenia (`bet.flags`) przegrywają
  (15+, wynik < −10%, CLV < 0) → blokada wraca.
- **Analiza po meczu** (memory): każdy rozliczony zakład dostaje `pm_cat` (zasluzona, szczescie, pech, zla_cena,
  bez_porownania – z wyniku i CLV) i `lesson` (z xG albo prognozą sumy NBA). `summary.luck`: zysk vs „uczciwy” wynik
  według kursów zamknięcia (szczęście czy umiejętność).
- **Kalibracja** (evaluation): `summary.calib` – na wszystkich rozliczonych ocenach: błąd (log loss) agenta, rynku i modelu,
  przedziały „agent daje X% → weszło Y%”, skrzywienie, osobno każda liga (z tego korzysta krytyk).
- **Wnioski** (memory): `summary.insights` – do 8 prostych zdań (najlepsza/najsłabsza liga, strona, kurs, bukmacher od 10+
  zakładów, kalibracja od 50+ meczów, szczęście od 20+ zakładów, blokady krytyka od 15+).

Testy (wszystko na kopiach) są w `gole/testy/`: `python3 gole/testy/test_skills.py` (prawdziwy `agent.json` i mecze
z `gole/liga/*.json`, rozliczenie na wynikach symulowanych, nauka krytyka w obie strony) i `test_page.py` (Playwright, 390 px,
jasny i ciemny motyw; sposób użycia na górze pliku) – oba przeszły 18.10.

**Do sprawdzenia po 18.10:**

1. Czy pierwsze rozliczone zakłady (19–20.10) mają `pm_cat` i `lesson`, a na stronie pod zakładem jest ocena.
2. Czy krytyk coś blokuje (`python3 gole/stan.py` → sekcja „Krytyk”) i czy blokady wyglądają rozsądnie. Na danych z 18.10
   próg `rozjazd` 12 pkt proc. zatrzymałby ok. 3% meczów; gdyby blokował za dużo albo za mało – progi w `GAP_MAX`.
3. `summary.calib.pilka`: już na pierwszych 118 ocenach model sam zaniżał szansę na over 2.5 – obserwuj, czy blend (agent)
   dogania rynek.

## Na czym skończyliśmy wcześniej – 17.10.2026 (wieczór)

17.10.2026 zbudowaliśmy **agenta**, który sam obstawia wirtualnymi pieniędzmi i uczy się na swoich zakładach,
i przebudowaliśmy stronę Linii Goli wokół niego.

- Agent gra od 17.10.2026. Pierwsze zakłady (po £10): Roma – Genoa Under 2.5 @ 2.00 (William Hill, 17.10)
  i Brighton – Crystal Palace Under 2.5 @ 2.40 (Casumo, 18.10). Na koniec dnia: portfel £1000, nic jeszcze nie rozliczone.
- Wszystkie automatyczne aktualizacje na GitHubie przechodziły bez błędów.
- Aktualny stan (liczby zmieniają się co 4 godziny): `git pull && python3 gole/stan.py`.

**Do sprawdzenia w najbliższych dniach:**

1. **Pierwsze rozliczenia (ok. 19–20.10).** Wyniki z football-data.co.uk przychodzą 1–2 dni po meczu. Sprawdź, czy oba
   zakłady rozliczyły się same i czy policzył się „vs zamknięcie” (CLV z kursów zamknięcia Pinnacle, kolumny PC>2.5 i PC<2.5).
2. **ClubElo nie działało 17.10 (błąd 502 po ich stronie).** Agent liczy wtedy zastępczo Elo z wyników lig
   (`zrodla.results_elo`) i próbuje ClubElo raz dziennie. Dopasowania nazw drużyn do ClubElo (`zrodla.HINT`) nie
   sprawdziliśmy jeszcze na prawdziwych danych – po pierwszym udanym pobraniu przejrzyj `status.sources.clubelo.matched`
   w `gole/agent.json` (wynik dopasowania poniżej 0.8 = podejrzane).
3. **NBA rusza 20.10** (pierwszy mecz Pistons – Celtics). Kod NBA testowaliśmy na danych symulowanych oraz na prawdziwym
   kalendarzu i raporcie kontuzji ESPN, ale nie na meczach w trakcie sezonu. Po starcie sprawdź w `status.nba`:
   `upcoming > 0`, `with_odds > 0`, brak błędów i czy czytają się najlepsi strzelcy (pole `leaders` z ESPN). Agent zacznie
   obstawiać NBA, gdy każda drużyna rozegra 5 meczów (ok. początek listopada).
4. **Limit kursów (The Odds API, darmowe 500 zapytań na miesiąc).** 17.10 dzienny przydział zużyły poranne aktualizacje
   sprzed startu agenta, więc tego dnia agent miał tylko kursy z ok. 02:00. Od 18.10 przydział to ok. 26 zapytań dziennie;
   ligi agenta mają pierwszeństwo, NBA ma zarezerwowane 2 zapytania dziennie (październik–czerwiec).
5. **Pierwsza nauka:** po 30 rozliczonych zakładach w danym sporcie agent zacznie sam zmieniać zasady – sprawdź,
   czy wpisy w dzienniku zmian są sensowne.

## Szybki start w nowej rozmowie

- `git pull` – bot dopisuje dane co 4 godziny.
- `python3 gole/stan.py` – portfel, zakłady, taktyki, nauka, źródła danych, błędy (skrypt tylko czyta).
- `gh run list -R rzarzycki98-hash/Radek -L 5` – czy automatyczne aktualizacje przechodzą.
- Strona agenta: https://rzarzycki98-hash.github.io/Radek/gole/ (Listy: https://rzarzycki98-hash.github.io/Radek/).

## Co jest w repozytorium

- **Główny folder: „Listy”** – prosta aplikacja PWA (Zadania, Zakupy): `index.html`, `app.js`, `style.css`, `sw.js`,
  `manifest.webmanifest`, `icons/`. Dawno bez zmian.
- **`gole/`: Linia Goli + agent.**

| Plik | Co robi |
| --- | --- |
| `gole/engine.py` | silnik: dane z football-data.co.uk (38 lig, 6 sezonów), kursy z The Odds API, model Poissona z poprawką Dixona-Colesa (gole + strzały celne), test walk-forward każdej ligi, statystyki meczów, kontuzje z FPL (Premier League), dziennik typów, prognozy; na końcu wywołuje agenta |
| `gole/agent.py` | agent: portfel, ocena każdego meczu, taktyki na sucho, stawianie zakładów, rozliczanie, nauka (zmiany zasad), podsumowanie dla strony |
| `gole/nba.py` | NBA: wyniki, terminarz, najlepsi strzelcy i raport kontuzji z ESPN, model sumy punktów, kursy |
| `gole/zrodla.py` | siła drużyn z ClubElo, dopasowanie nazw drużyn, zastępcze Elo z wyników ligi |
| `gole/stan.py` | stan agenta w kilku linijkach (tylko czyta `agent.json`) |
| `gole/testy/` | testy skilli agenta i strony (na kopiach, nigdy na prawdziwym stanie) |
| `gole/index.html` | cała strona (HTML + CSS + JS w jednym pliku) |
| `gole/agent.json` | stan agenta: portfel, zakłady, zasady, dziennik zmian, podsumowanie, oceny meczów na 7 dni, status źródeł |
| `gole/agent_analizy.json` | ocena każdego meczu i jej wynik po meczu – dane do nauki (400 dni) |
| `gole/data.json`, `gole/liga/*.json` | ligi, mecze, ceny, statystyki, drużyny (dla strony) |
| `gole/journal.json`, `gole/predictions.json`, `gole/archiwum/` | stary dziennik typów i prognozy (silnik nadal liczy na nich oceny lig) |
| `gole/odds_cache.json`, `gole/names.json` | pamięć kursów (oszczędza limit) i nazwy drużyn u bukmacherów |
| `.github/workflows/linia-goli.yml` | automatyczna aktualizacja |

## Jak to działa automatycznie

- Workflow `.github/workflows/linia-goli.yml`: co 4 godziny (cron `17 */4 * * *`, czas UTC), ręcznie (Actions → Run workflow)
  i po pushu zmian w `gole/engine.py`, `agent.py`, `nba.py`, `zrodla.py` lub w samym workflow. Python 3.12 + numpy,
  sekret `ODDS_API_KEY`, pamięć pobranych plików w `gole/.cache` (actions/cache).
- `engine.run()`: wyniki 38 lig → start agenta (`AG.Agent`) i NBA (`NBA.prepare`: ESPN + kursy) → kursy piłkarskie
  (`OddsAPI.refresh`, z rezerwą na NBA) → dla każdej ligi: test, ceny meczów, dziennik typów i `ag.football(...)`
  dla 11 lig agenta → `ag.nba(...)` → `ag.finish(...)` (stawia zakłady, uczy się, zapisuje oba pliki agenta).
- Bot commituje dane („Linia Goli: aktualizacja danych …”), GitHub Pages publikuje stronę.
- Agent nie może zatrzymać aplikacji: jego wywołania są w try/except, błędy trafiają do `agent.json` → `status.errors`.

## Agent – decyzje Radka (17.10.2026)

| Co | Ustalenie |
| --- | --- |
| Portfel | £1000 wirtualne, wspólny dla piłki i NBA |
| Stawka | 1% aktualnego portfela; najwyżej 30% portfela w otwartych zakładach |
| Piłka | gole over/under 2.5 w 11 ligach: E0, SP1, I1, D1, F1 (Top 5), N1, P1, B1, T1, SC0, G1 |
| Bukmacherzy – piłka | William Hill, Grosvenor, Casumo, LeoVegas: w darmowych danych tylko oni mają over/under 2.5 (Ladbrokes i BetVictor mają tam tylko 1X2) |
| NBA | suma punktów over/under; Ladbrokes i BetVictor, a gdy nie mają linii – inny bukmacher z UK (bez giełd) |
| Które mecze | ocenia każdy mecz swoich lig; stawia tylko wtedy, gdy kurs daje przewagę wymaganą przez aktywną taktykę |
| Kursy | nie starsze niż 12 h; piłka 1.50–3.20, NBA 1.60–2.40 |
| Nauka | sam zmienia zasady po 30 rozliczonych zakładach (osobno piłka i NBA), najwyżej raz na 7 dni, każda zmiana z powodem w dzienniku |
| Taktyki | wszystkie typują na sucho; pieniądze idą na aktywną; przejście na inną po 50+ (piłka) / 80+ (NBA) typach, przy zysku, kursie lepszym niż zamknięcie i wyniku o 3+ pkt proc. lepszym od aktywnej |
| Gotowość na prawdziwe pieniądze | tylko informacja: 90+ dni, 200+ zakładów, portfel na plusie, kursy lepsze niż zamknięcie |
| Skille (18.10.2026) | krytyk przed każdym zakładem, analiza po meczu, kalibracja, wnioski – „wszystkie przydatne”, budowane od razu |
| Dane | tylko darmowe; bez płatnej AI do czytania newsów i składów |
| Raport | tylko na stronie (bez powiadomień na telefon) |
| Strona | zbudowana wokół agenta: Agent (start: portfel i dzisiejsze zakłady), Mecze, Nauka, Wyniki, Ligi; zostały tabela drużyn (w Ligach) i analiza meczu; usunięte „Moje zakłady” i stary dziennik „Typy” |

### Taktyki (klucz, nazwa, wymagana przewaga na start)

Piłka: `blend` Model + rynek 3% (aktywna na start) · `market` Kurs ponad rynek 2% · `stats` Statystyki potwierdzają 2% ·
`model` Sam model 5% · `big` Duża przewaga 6% · `elo` Siła drużyn 1% (różnica Elo 150+ → Over, do 40 → Under) ·
`inj` Kontuzje 2% (Premier League, dane FPL) · `move` Za ruchem rynku 0% (rynek przesunął się o 3+ pkt proc.).

NBA: `blend` Model + rynek 3% (aktywna na start) · `model` Sam model 5% · `big` Duża przewaga 6% · `b2b` Zmęczenie 1%
(Under, gdy drużyna grała dzień wcześniej) · `inj` Kontuzje gwiazd 2% (ok. −3 pkt za brakującą gwiazdę) · `move` Za ruchem
linii 0% (linia przesunęła się o 1.5+ pkt).

Przewaga = szansa × kurs − 1. „Vs zamknięcie” (CLV) = nasz kurs × uczciwa szansa tuż przed meczem − 1 (Pinnacle bez marży).

### Kroki nauki (`Agent.adapt`, w tej kolejności, najwyżej jedna zmiana naraz)

zmiana taktyki → krytyk (wyłączenie albo włączenie blokady, patrz „Na czym skończyliśmy – 18.10.2026”) →
wyłączenie ligi (15+ zakładów, wynik poniżej −10%, CLV poniżej 0) → włączenie ligi (20+ typów na sucho
od wyłączenia, zysk) → wyłączenie strony Over/Under (20+ zakładów, wynik poniżej −15%) → wyższa przewaga (ostatnie 50 zakładów
na minusie: +1 pkt proc., max 10%) → niższa przewaga (50+ zakładów na plusie, a pominięte tuż pod progiem też by zarobiły:
−0.5 pkt proc., min 1%) → niższy najwyższy kurs → filtr statystyk włącz/wyłącz → NBA: waga własnego modelu (100+ meczów).

## Źródła danych (wszystkie darmowe)

- **football-data.co.uk** – wyniki, gole, strzały celne, kursy zamknięcia; zakończone sezony pobierane raz.
- **The Odds API** – kursy z UK; 500 zapytań na miesiąc; piłka 2 zapytania na ligę (1X2 + gole), NBA 1; kursy tylko dla lig
  z meczem w ciągu 54 h, odświeżane co 10 h; przydział dzienny = (zostało − 10 − rezerwa NBA) / dni do końca miesiąca.
- **ClubElo** – ranking siły klubów (CSV raz dziennie); gdy nie działa → Elo z wyników ligi.
- **Fantasy Premier League** – kontuzje i zawieszenia w Premier League.
- **ESPN** – NBA: wyniki i terminarz (dzień po dniu, zakończone dni z pamięci), najlepsi strzelcy, raport kontuzji (co 3 h).

## Zasady pracy w tym repozytorium

- **Środowisko chmurowe Claude nie ma dostępu do football-data.co.uk, ESPN ani ClubElo** (proxy je blokuje). Prawdziwe
  dane pobiera tylko GitHub Actions; lokalnie testuj na kopiach i na danych symulowanych.
- **Nigdy nie uruchamiaj `engine.py --out gole` lokalnie i nie wypychaj wyniku** – nadpisałbyś stan agenta.
  Testy zawsze do folderu tymczasowego.
- **Nie edytuj ręcznie `gole/agent.json` ani `gole/agent_analizy.json`** – rozjedzie się portfel. Zmiany formatu tylko
  w kodzie (`Agent.__init__` uzupełnia nowe klucze zasad). Reset agenta (usunięcie obu plików → start od £1000) tylko na
  wyraźną prośbę Radka.
- Gałąź `main`; bot commituje co 4 godziny, więc przed pushem zawsze `git fetch origin main && git rebase origin/main`.
  Nigdy force push.
- Po pushu kodu: poczekaj na przebieg „Linia Goli – aktualizacja danych”, potem `git pull`, `python3 gole/stan.py`
  i sprawdź, czy nie ma błędów.
- Commity i teksty na stronie po polsku, komentarze w kodzie po angielsku; liczby z kropką (2.5, 1.85), kwoty w £.
- Strona: jeden plik, najpierw telefon, jasny i ciemny motyw, bez poziomego przewijania przy szerokości 390 px.
- GitHub Pages przepuszcza pliki .md przez Jekylla: **w plikach .md nie wpisuj dwóch klamer otwierających obok siebie
  ani klamry z procentem** – publikacja strony by się wywaliła.
- Repozytorium jest publiczne – żadnych danych prywatnych ani kluczy (klucz Odds API jest w sekretach repozytorium).

### Jak testowaliśmy

- Cały silnik offline: `python3 gole/engine.py --local DIR --today 2026-10-17 --out /tmp/out --only E0 --fixtures-from-results`
  (w `DIR/data/E0/` pliki `season-2122.csv` … `season-2627.csv` w formacie football-data, mogą być symulowane).
- Agent na prawdziwych meczach: `fixtures` z `gole/liga/<kod>.json` → `Agent(folder_tymczasowy, now).football(kod, nazwa, fixtures, [])`
  → `finish({})`; rozliczenie: drugie wywołanie z listą wyników (pola `d`, `h`, `a`, `hg`, `ag`, `ouc`).
- NBA: podmieniony `ESPNSource._get` (symulowany sezon) i prosty obiekt zamiast `OddsAPI` (pola `key`, `c`, metoda `_get`).
- Strona: kopia `gole/` w folderze tymczasowym, `python3 -m http.server`, Playwright + Chromium na szerokości 390 px
  (w chmurze Claude: `PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers`); bez błędów JS i bez poziomego przewijania.

## Do zrobienia przy okazji

- W `gole/index.html` zostały nieużywane stare widoki: `viewMatches`, `viewJournal`, `viewMyBets`, `viewReport`,
  `viewLeagues`, `viewTeams`, `betForm` (i powiązane `matchRow`, `worthRow`, `tipRow`, `saveBet`, `backup`). Można je usunąć;
  `leagueCard()` jest nadal używane w szczegółach ligi. Ręcznie wpisane zakłady Radka zostały w pamięci telefonu
  (localStorage `linia-goli-bets`) – widok można przywrócić, jeśli poprosi.
- Silnik nadal liczy wszystkie 38 lig (testy modelu, dziennik typów), a strona pokazuje tylko 11 lig agenta i NBA.
- Odłożone lub odrzucone: czytanie newsów przez AI (płatne), zakłady na żywo (brak darmowych kursów na żywo),
  rynek 1X2 dla agenta (Radek wybrał gole), powiadomienia na telefon (Radek wybrał tylko stronę).

## Jak pracować z Radkiem

- Pisze po polsku – odpowiadaj po polsku, prosto, bez żargonu; przy instrukcjach krok po kroku daj bezpośredni link do każdego kroku.
- Tylko darmowe narzędzia i dane.
- Gdy nie wiesz dokładnie, o co mu chodzi – pytaj (najlepiej z gotowymi opcjami), aż będzie jasne; po skończeniu zawsze
  sprawdź, że wszystko działa (testy, przebieg na GitHubie, strona na telefonie).
- Chce, żeby to, co buduje, działało jako samodzielne agenty, które uczą się na swoich wynikach – on uczy się razem z nimi.
- Ma też osobny projekt „Agent Tradingowy” (akcje) – nie jest częścią tego repozytorium.

## Historia

- Wcześniej: Listy (PWA); Linia Goli v3 – 38 lig, gole over/under i 1X2, model uczący się na wynikach, test walk-forward,
  dziennik typów, kalkulator na żywo, kontuzje w Premier League, „Moje zakłady”.
- 17.10.2026: agent (`agent.py`), NBA (`nba.py`), strona wokół agenta, dodatkowe dane – ClubElo, kontuzje, ruchy kursów
  (`zrodla.py`), zastępcze Elo z wyników, `stan.py` i ten plik.
- 18.10.2026: skille agenta – krytyk, analiza po meczu, kalibracja, wnioski (strona: Nauka → Skille agenta; `stan.py` je pokazuje).
