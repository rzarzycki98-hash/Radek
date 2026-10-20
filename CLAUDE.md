# Repozytorium „Radek” – notatki dla Claude

Ten plik Claude czyta na początku każdej rozmowy z tym repozytorium, także w każdym wątku projektu w Claude Code. Mówi, co
tu jest, co ustaliliśmy z Radkiem i na czym skończyliśmy. **Na koniec każdej sesji pracy zaktualizuj sekcję „Na czym
skończyliśmy”** (data, co zrobione, co sprawdzić) i wypchnij zmianę. Ważne nowe decyzje Radka dopisz też do osi czasu
w `gole/HISTORIA.md`.

**Gdzie rozmawiamy:** od 18.10.2026 rozmowy o agencie do obstawiania (Linia Goli) toczą się w projekcie w Claude Code
(claude.ai/code → Projects) na tym repozytorium. Agent Tradingowy (akcje) to osobny projekt Radka, poza tym repozytorium.

**Historia wszystkich rozmów i ustaleń (od 14.10.2026), wczytywana automatycznie:** @gole/HISTORIA.md

## Na czym skończyliśmy – 18.10.2026 (wieczór)

- Rano: agent dostał 4 skille – krytyk, analiza po meczu, kalibracja, wnioski (szczegóły niżej, w „Skille agenta”).
- Wieczorem: Radek przeniósł rozmowy o agencie do projektu w Claude Code; historia rozmów jest w `gole/HISTORIA.md`.
- Stan 18.10 21:44: portfel £1000, 7 otwartych zakładów po £10 (3 mecze już rozegrane, czekają na wyniki), nic jeszcze
  nierozliczone, krytyk niczego nie zablokował, wszystkie aktualizacje na GitHubie bez błędów. ClubElo dalej nie odpowiada
  (agent liczy Elo z wyników lig).
- **19.10 rano – sprawdzenie rozliczeń (rozmowa sprzed projektu):** wszystkie 22 aktualizacje z weekendu (17–19.10)
  przeszły bez błędów. Wyników meczów z 17–18.10 jeszcze nie było w football-data.co.uk (ostatnie wyniki lig z 10–16.10),
  więc rozliczył się tylko 1 mecz z prognoz (Argentyna, 16.10) i 0 zakładów agenta – to opóźnienie po stronie źródła,
  nie błąd (pliki pobierają się przy każdej aktualizacji). Poprawka: alias Sint Truiden → St Truiden (Belgia, B1);
  po niej lista niedopasowanych nazw jest pusta. Testy `test_skills.py` i `test_page.py` – OK.
  **19.10 14:04 (UK):** nadal brak wyników z 17–18.10 we wszystkich 38 ligach, mimo że pliki pobierają się poprawnie
  (25–41 udanych pobrań na przebieg, bez błędów) – football-data jeszcze ich nie wrzuciło. Uwaga na przyszłość: gdy pobranie
  się nie uda, `Source._cached` po cichu bierze starą kopię z pamięci podręcznej (bez wpisu w `errors`).
  **20.10 10:30 (UK):** nadal nic – ostatnie wyniki we wszystkich 38 ligach z 10–16.10, ostatnia zmiana jakiegokolwiek
  wyniku 16.10 ok. 14:05 (UK). Po naszej stronie nie widać błędu: każdy przebieg ma 25–41 udanych pobrań (licznik rośnie
  tylko przy odpowiedzi serwera), pliki są poprawne, parser czyta daty w 3 formatach. Najpewniej przerwa po stronie
  football-data (nie da się tego sprawdzić z chmury Claude – proxy blokuje stronę). Zakłady piłkarskie agenta czekają na wynik
  do 21 dni (potem zwrot stawki), więc 17–18.10 są bezpieczne do ok. 7.11. Radkowi zaproponowane (czeka na jego decyzję):
  zapasowe źródło wyników z ESPN (darmowe, bez klucza, już używane dla NBA; CLV dopisze się później z football-data)
  i ostrzeżenie na stronie, gdy najnowsze wyniki są starsze niż 3 dni. Niedopasowana nazwa `PK-35` (Finlandia) to drużyna
  spoza ligi w football-data (baraż) – alias niepotrzebny.
- **19.10 wieczorem Radek poprosił o przeniesienie rozmowy sprzed projektu do projektu.** Jej ustalenia są w
  `gole/HISTORIA.md` (19.10). Zostało w niej tylko automatyczne sprawdzenie 20.10 ok. 10:30 (UK), które dopisze wynik tutaj.
  Sprawdzenie z 20.10 jest wpisane wyżej – w tamtej rozmowie nie ma już żadnych zadań.
- Aktualny stan (liczby zmieniają się co 4 godziny): `git pull && python3 gole/stan.py`.

**Do sprawdzenia w najbliższych dniach:**

1. **Pierwsze rozliczenia (20.10 rano wyników z 17–18.10 nadal nie było – patrz wyżej; czeka decyzja Radka o zapasowym źródle).** Wyniki z football-data.co.uk
   przychodzą zwykle 1–2 dni po meczu. Sprawdź, czy zakłady
   rozliczyły się same, czy policzył się „vs zamknięcie” (CLV z kursów zamknięcia Pinnacle, kolumny PC>2.5 i PC<2.5) i czy
   mają ocenę po meczu (`pm_cat`, `lesson`) widoczną na stronie pod zakładem.
2. **Krytyk.** Czy coś blokuje (`python3 gole/stan.py` → sekcja „Krytyk”) i czy blokady wyglądają rozsądnie. Na prawdziwych
   meczach z 18.10 próg `rozjazd` (12 pkt proc.) zatrzymałby ok. 3% meczów; gdyby blokował za dużo albo za mało – progi
   w `GAP_MAX`.
3. **Kalibracja.** Pojawi się po pierwszych rozliczonych ocenach (`summary.calib`). Liczby z testu 18.10 pochodziły z wyników
   losowych i nic nie mówią o modelu.
4. **ClubElo nie działało 17–18.10** (błąd po ich stronie). Agent liczy wtedy zastępczo Elo z wyników lig
   (`zrodla.results_elo`) i próbuje ClubElo raz dziennie. Dopasowania nazw drużyn do ClubElo (`zrodla.HINT`) nie
   sprawdziliśmy jeszcze na prawdziwych danych – po pierwszym udanym pobraniu przejrzyj `status.sources.clubelo.matched`
   w `gole/agent.json` (wynik dopasowania poniżej 0.8 = podejrzane).
5. **NBA rusza 20.10** (pierwszy mecz Pistons – Celtics). Kod NBA testowaliśmy na danych symulowanych oraz na prawdziwym
   kalendarzu i raporcie kontuzji ESPN, ale nie na meczach w trakcie sezonu. Po starcie sprawdź w `status.nba`:
   `upcoming > 0`, `with_odds > 0`, brak błędów i czy czytają się najlepsi strzelcy (pole `leaders` z ESPN). Agent zacznie
   obstawiać NBA, gdy każda drużyna rozegra 5 meczów (ok. początek listopada).
6. **Limit kursów (The Odds API, darmowe 500 zapytań na miesiąc).** Przydział to ok. 26 zapytań dziennie; ligi agenta mają
   pierwszeństwo, NBA ma zarezerwowane 2 zapytania dziennie (październik–czerwiec). 18.10 zostało 385 zapytań do końca miesiąca.
7. **Pierwsza nauka:** po 30 rozliczonych zakładach w danym sporcie agent zacznie sam zmieniać zasady – sprawdź,
   czy wpisy w dzienniku zmian są sensowne.

## Szybki start w nowej rozmowie

- `git pull` – bot dopisuje dane co 4 godziny.
- `python3 gole/stan.py` – portfel, zakłady, taktyki, nauka, krytyk, kalibracja, źródła danych, błędy (skrypt tylko czyta).
- `gh run list -R rzarzycki98-hash/Radek -L 5` – czy automatyczne aktualizacje przechodzą.
- Strona agenta: https://rzarzycki98-hash.github.io/Radek/gole/ (Listy: https://rzarzycki98-hash.github.io/Radek/).

## Co jest w repozytorium

- **Główny folder: „Listy”** – prosta aplikacja PWA (Zadania, Zakupy): `index.html`, `app.js`, `style.css`, `sw.js`,
  `manifest.webmanifest`, `icons/`. Dawno bez zmian.
- **`gole/`: Linia Goli + agent.**

| Plik | Co robi |
| --- | --- |
| `gole/engine.py` | silnik: dane z football-data.co.uk (38 lig, 6 sezonów), kursy z The Odds API, model Poissona z poprawką Dixona-Colesa (gole + strzały celne), test walk-forward każdej ligi, statystyki meczów, kontuzje z FPL (Premier League), dziennik typów, prognozy; na końcu wywołuje agenta |
| `gole/agent.py` | agent: portfel, ocena każdego meczu, taktyki na sucho, krytyk, stawianie zakładów, rozliczanie, analiza po meczu, nauka (zmiany zasad), kalibracja, wnioski, podsumowanie dla strony |
| `gole/nba.py` | NBA: wyniki, terminarz, najlepsi strzelcy i raport kontuzji z ESPN, model sumy punktów, kursy |
| `gole/zrodla.py` | siła drużyn z ClubElo, dopasowanie nazw drużyn, zastępcze Elo z wyników ligi |
| `gole/stan.py` | stan agenta w kilku linijkach (tylko czyta `agent.json`) |
| `gole/HISTORIA.md` | historia rozmów z Radkiem i jego decyzji (14–18.10.2026), pomysły i co się z nimi stało |
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
- Zadania zaplanowane w Claude: brak aktywnych (dokończenie „Sprawdzenia rozliczeń Linii Goli” odbyło się 20.10 ok. 10:30 czasu UK,
  w rozmowie sprzed projektu; potem nic) i wyłączone „Linia Goli: odświeżanie na żądanie” (stara wersja strony). Nowe sprawdzenia ustawiaj w projekcie
  (rutyny w zakładce Routines).

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

zmiana taktyki → krytyk (wyłączenie albo włączenie blokady, patrz „Skille agenta”) →
wyłączenie ligi (15+ zakładów, wynik poniżej −10%, CLV poniżej 0) → włączenie ligi (20+ typów na sucho
od wyłączenia, zysk) → wyłączenie strony Over/Under (20+ zakładów, wynik poniżej −15%) → wyższa przewaga (ostatnie 50 zakładów
na minusie: +1 pkt proc., max 10%) → niższa przewaga (50+ zakładów na plusie, a pominięte tuż pod progiem też by zarobiły:
−0.5 pkt proc., min 1%) → niższy najwyższy kurs → filtr statystyk włącz/wyłącz → NBA: waga własnego modelu (100+ meczów).

### Skille agenta (18.10.2026)

Wszystkie w `gole/agent.py`, widoczne na stronie (Nauka → Skille agenta) i w `stan.py`:

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
- Skille: `python3 gole/testy/test_skills.py` (prawdziwy `agent.json` i mecze z `gole/liga/*.json`, rozliczenie na wynikach
  symulowanych, nauka krytyka w obie strony) i `gole/testy/test_page.py` (strona; sposób użycia na górze pliku).
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
  rynek 1X2 dla agenta (Radek wybrał gole), powiadomienia na telefon (Radek wybrał tylko stronę), ligi młodzieżowe U19/U20
  (jeszcze nie ma – trzeba znaleźć darmowe źródło ich wyników i kursów).

## Jak pracować z Radkiem

- Pisze po polsku – odpowiadaj po polsku, prosto, bez żargonu; przy instrukcjach krok po kroku daj bezpośredni link do każdego kroku.
- Tylko darmowe narzędzia i dane.
- Gdy nie wiesz dokładnie, o co mu chodzi – pytaj (najlepiej z gotowymi opcjami), aż będzie jasne; po skończeniu zawsze
  sprawdź, że wszystko działa (testy, przebieg na GitHubie, strona na telefonie).
- Chce, żeby to, co buduje, działało jako samodzielne agenty, które uczą się na swoich wynikach – on uczy się razem z nimi.
- Rozmowy o agencie prowadzi w projekcie w Claude Code. Ustalenia z rozmów zapisuj w repozytorium (ten plik albo
  `gole/HISTORIA.md`), żeby kolejne wątki projektu je znały.
- Ma też osobny projekt „Agent Tradingowy” (akcje) – nie jest częścią tego repozytorium.

## Historia

Pełna oś czasu jest w `gole/HISTORIA.md`. W skrócie: 14.10 pierwsza wersja Linii Goli i repozytorium; 15.10 Linia Goli v3
(38 lig, model, test lig, statystyki, kontuzje, kalkulator na żywo); 17.10 agent, NBA i strona wokół agenta; 18.10 skille
agenta i przejście rozmów do projektu w Claude Code.
