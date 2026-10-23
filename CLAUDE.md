# Repozytorium „Radek” – notatki dla Claude

Ten plik Claude czyta na początku każdej rozmowy z tym repozytorium, także w każdym wątku projektu w Claude Code. Mówi, co
tu jest, co ustaliliśmy z Radkiem i na czym skończyliśmy. **Na koniec każdej sesji pracy zaktualizuj sekcję „Na czym
skończyliśmy”** (data, co zrobione, co sprawdzić) i wypchnij zmianę. Ważne nowe decyzje Radka dopisz też do osi czasu
w `gole/HISTORIA.md`.

**Gdzie rozmawiamy:** od 18.10.2026 rozmowy o agencie do obstawiania (Linia Goli) toczą się w projekcie w Claude Code
(claude.ai/code → Projects) na tym repozytorium. Agent Tradingowy (akcje) to osobny projekt Radka, poza tym repozytorium.

**Historia wszystkich rozmów i ustaleń (od 14.10.2026), wczytywana automatycznie:** @gole/HISTORIA.md

## Na czym skończyliśmy – 21.10.2026

Sesja „naprawa błędów i skuteczność agenta” (szczegóły i liczby: `gole/HISTORIA.md`, 21.10). Stan przed zmianami:
portfel £1001.60, 4 rozliczone zakłady (2 trafione), 4 otwarte, 7 z 8 zakładów na Under, „vs zamknięcie” −4.6%.

- **Naprawione:** test `test_skills.py` (liczył też zakłady rozliczone wcześniej naprawdę – błąd testu, nie agenta);
  ClubElo zapisuje prawdziwą przyczynę błędu (`status.sources.clubelo.tried`) i próbuje co 6 h; zapasowa wczorajsza kopia
  ClubElo znów się wczytuje; nieudane pobranie zastąpione starą kopią widać w `status.sources.football_data.stale`
  (i `espn.stale`); na stronie i w `stan.py` ostrzeżenie, gdy najnowszy wynik ligi ma 3+ dni, a rozegrane mecze czekają
  (`status.results`).
- **ClubElo:** serwer API (api.clubelo.com) odpowiada HTTP 502 na każde zapytanie, także o stare daty; https nie działa;
  strona clubelo.com działa. Awaria po ich stronie – agent liczy Elo z wyników lig. Nic do naprawy po naszej stronie.
- **Pinnacle zniknął z football-data** w połowie sezonu 2025/26 (26/27: 0 meczów). Są kursy giełdy Betfair (BFE, BFEC).
  „Vs zamknięcie” liczy się teraz z Pinnacle → giełdy Betfair (gdy rynek nie jest płytki) → średniej (`agent.fair_ou`).
- **Test na historii** (`gole/testy/historia.py`, 11 lig, ok. 11 tys. meczów, bez zaglądania w przyszłość): skrzywienie
  modelu w over 2.5 w pełnych sezonach −0.4 do −2.4 pkt proc.; w 26/27 −7.4, ale rynek też −4.5 (sezon bramkowy, 60% overów).
  Kalibracja nie poprawia log loss (0.6784 → 0.6787) – Radek: nie dodawać. Model nie dodaje informacji ponad rynek.
  Stary dobór wagi modelu: 538 typów (66% Under), CLV −4.7%; nowy: 82 typy (42 Over / 40 Under), CLV −2.2%.
- **Decyzje Radka 21.10** (wszystkie wdrożone w kodzie): uczciwa cena z Pinnacle i giełd (The Odds API, parametr
  `bookmakers`, ten sam koszt); waga modelu dobierana na 2 pełnych sezonach + bieżącym, model dostaje wagę tylko przy
  poprawie log loss o 0.001+ (`TUNE_SEASONS`, `W_OU_MIN_GAIN`); bez kalibracji; ESPN jako zapas wyników piłki.
- Przebieg diagnostyczny (tylko odczyt, nic nie zapisuje): `.github/workflows/linia-goli-diagnoza.yml` – uruchamia się
  przy pushu `gole/testy/historia.py` lub `diagnoza_zrodel.py` na gałęzi `claude/**` (albo ręcznie); wynik w logu przebiegu.
- **Wdrożone do `main` 21.10 ok. 10:30 (UK)**; pierwsza aktualizacja z nowym kodem (09:30 UTC) bez błędów; strona na 390 px
  bez błędów. Waga modelu (`w_ou`) po zmianie: 0 w 10 ligach, 0.5 w Premier League. Uczciwa cena „giełda” (Matchbook) już
  w części meczów E0, SP1, I1; Pinnacle dojdzie przy najbliższym odświeżeniu kursów danej ligi (mecz w ciągu 54 h).
- Aktualny stan (liczby zmieniają się co 4 godziny): `git pull && python3 gole/stan.py`.

- **21.10 później – Over i Under:** Radek chce, żeby agent grał nie tylko Under. Sprawdzone: bukmacherzy agenta wyceniają
  Over i Under tak samo (marża ok. 7% po obu stronach vs giełda), Undery brały się z modelu – po zmianie wag oceny
  wskazują Over 10 razy, Under 3 razy. Wymuszanie równowagi odradzone (zakład bez przewagi traci średnio ok. 7%);
  Radek wybrał licznik: `summary.sides` (oceny i zakłady Over/Under z 7 i 30 dni) – na stronie (Nauka → „Over czy
  Under?”) i w `stan.py`.

- **21.10 wieczorem – skille z grafik** (Radek wysłał 4 grafiki: „Claude Mastery Map”, „AI Dev Skills”, „AI Engineer's
  Stack”, „26 Claude Skill Ideas” i napisał „zastosuj te skille”). Wybrał (z opcji): komendy-skille, hooki-bezpieczniki,
  testy automatyczne na GitHubie, cotygodniową rutynę Claude, „Zdrowie agenta” i „Raport tygodnia”. Pominięte: płatne
  i do dużych systemów (AWS, Docker, bazy wektorowe, LangChain, płatne modele AI) oraz niezwiązane (posty na LinkedIn itp.).
  Szczegóły w sekcji „Skille i bezpieczniki Claude” niżej.

- **21.10 – „jeżeli model spodziewa się 2.6, niech stawia Over”:** sprawdzone na historii (11 lig): przy 2.6–2.7 gola over
  wchodzi w 51.6% meczów, a kurs ok. 1.90 wymaga 53%; reguła „2.6+ → Over” traciła (6247 zakładów, −3.7%, CLV −4.7%).
  Radek wybrał: taktyka na sucho `xg` (agent przejdzie na nią sam, gdy się sprawdzi). Opis po meczu pokazuje teraz też
  szansę na over („Model spodziewał się 2.6 gola (szansa na over 2.5: 48%)”).

**Do sprawdzenia w najbliższych dniach:**

0. **Nowe skille:** w poniedziałek 26.10 „Raport tygodnia” za 19–25.10 (karta na stronie Agent, `agent.json` → `weekly`);
   czy Radek utworzył rutynę w Routines (tekst w `.claude/rutyna-poniedzialkowa.md`); „Zdrowie agenta” (Nauka) – paski powinny być zielone, złote = źródło nie odpowiedziało.
   Przebieg „Linia Goli – testy” przy każdej zmianie kodu powinien być zielony.
0. **Over/Under:** czy w liczniku pojawiają się zakłady na Over, gdy kursy mają przewagę (licznik w `stan.py`).
1. **Nowa uczciwa cena.** Po pierwszej aktualizacji z nowym kodem: w `gole/liga/<kod>.json` pole `fair.ou_src` powinno
   mieć „Pinnacle” (albo „giełda”) zamiast „UK”; w `status.sources.odds` brak błędów; zapytań ubywa jak dotąd (2 na ligę).
   Pinnacle w The Odds API podaje zwykle linię 2.75 – silnik przelicza ją na 2.5 (`engine.over25_from_line`).
2. **Mniej zakładów.** Waga modelu w większości lig spadnie do 0 (`data.json` → `leagues[].params.w_ou`), więc „Model + rynek”
   gra tylko, gdy bukmacher agenta płaci 3%+ ponad Pinnacle. Kilka zakładów tygodniowo albo mniej jest w porządku.
   Patrz, czy „vs zamknięcie” nowych zakładów jest bliżej zera albo na plusie.
3. **ESPN jako zapas:** mecz bez wyniku w football-data 72 h po pierwszym gwizdku rozlicza się z ESPN (`res_src: "ESPN"`);
   gdy football-data go opublikuje, dopisuje się CLV, a przy innym wyniku zakład jest poprawiany (`note` „Poprawka”).
   Dopasowanie nazw drużyn ESPN ↔ football-data (`engine.team_sim`, próg 1.3) sprawdzone tylko na Anglii i Grecji.
4. **Krytyk:** zmiana źródła uczciwej ceny (UK → Pinnacle) nie liczy się jako ruch rynku (`pk_src`); sprawdź, czy
   `rynek_przeciw` nie blokuje nagle wielu meczów.
5. **NBA:** 21.10 rozegrane 3 mecze; kod bez błędów. Agent zacznie obstawiać, gdy każda drużyna rozegra 5 meczów.
   Strojenie modelu NBA (np. Pinnacle jako uczciwa linia) – później.
6. **Limit kursów:** 21.10 zostało 318 zapytań do końca miesiąca (ok. 26 dziennie).
7. **Pierwsza nauka:** po 30 rozliczonych zakładach w danym sporcie agent zacznie sam zmieniać zasady.

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
| `gole/testy/` | testy skilli agenta i strony (na kopiach, nigdy na prawdziwym stanie), test modelu na historii, diagnoza źródeł |
| `gole/index.html` | cała strona (HTML + CSS + JS w jednym pliku) |
| `gole/agent.json` | stan agenta: portfel, zakłady, zasady, dziennik zmian, podsumowanie, oceny meczów na 7 dni, status źródeł |
| `gole/agent_analizy.json` | ocena każdego meczu i jej wynik po meczu – dane do nauki (400 dni) |
| `gole/data.json`, `gole/liga/*.json` | ligi, mecze, ceny, statystyki, drużyny (dla strony) |
| `gole/journal.json`, `gole/predictions.json`, `gole/archiwum/` | stary dziennik typów i prognozy (silnik nadal liczy na nich oceny lig) |
| `gole/odds_cache.json`, `gole/names.json` | pamięć kursów (oszczędza limit) i nazwy drużyn u bukmacherów |
| `.github/workflows/linia-goli.yml` | automatyczna aktualizacja |
| `.github/workflows/linia-goli-testy.yml` | testy przy każdej zmianie kodu (test_skills.py + strona 390 px w Chromium) |
| `.github/workflows/linia-goli-diagnoza.yml` | diagnoza tylko do odczytu: model na historii i źródła danych |
| `.claude/skills/`, `.claude/hooks/straznik.py`, `.claude/settings.json` | komendy-skille i bezpieczniki dla Claude (patrz „Skille i bezpieczniki Claude”) |

## Jak to działa automatycznie

- Workflow `.github/workflows/linia-goli.yml`: co 4 godziny (cron `17 */4 * * *`, czas UTC), ręcznie (Actions → Run workflow)
  i po pushu zmian w `gole/engine.py`, `agent.py`, `nba.py`, `zrodla.py` lub w samym workflow. Python 3.12 + numpy,
  sekret `ODDS_API_KEY`, pamięć pobranych plików w `gole/.cache` (actions/cache).
- `engine.run()`: wyniki 38 lig → start agenta (`AG.Agent`) i NBA (`NBA.prepare`: ESPN + kursy) → kursy piłkarskie
  (`OddsAPI.refresh`, z rezerwą na NBA) → dla każdej ligi: test, ceny meczów, dziennik typów i `ag.football(...)`
  dla 11 lig agenta → `ag.nba(...)` → `ag.finish(...)` (stawia zakłady, uczy się, zapisuje oba pliki agenta).
- Bot commituje dane („Linia Goli: aktualizacja danych …”), GitHub Pages publikuje stronę.
- „Linia Goli – testy” (`linia-goli-testy.yml`): przy pushu kodu (`gole/*.py`, `gole/index.html`, `gole/testy/`) na `main`
  i `claude/**` oraz przy PR – `test_skills.py` i `test_page.py` (Chromium, 390 px); zrzuty strony w artefaktach przebiegu.
- Agent nie może zatrzymać aplikacji: jego wywołania są w try/except, błędy trafiają do `agent.json` → `status.errors`.
- Zadania zaplanowane w Claude: brak aktywnych – „Linia Goli: poniedziałkowe sprawdzenie” czeka, aż Radek utworzy ją
  w zakładce Routines (patrz „Skille i bezpieczniki Claude”). Wcześniej: brak aktywnych (dokończenie „Sprawdzenia rozliczeń Linii Goli” odbyło się 20.10 ok. 10:30 czasu UK,
  w rozmowie sprzed projektu; potem nic) i wyłączone „Linia Goli: odświeżanie na żądanie” (stara wersja strony). Nowe sprawdzenia ustawiaj w projekcie
  (rutyny w zakładce Routines).

## Agent – decyzje Radka (17.10.2026)

| Co | Ustalenie |
| --- | --- |
| Portfel | £1000 wirtualne, wspólny dla piłki i NBA |
| Stawka | 1% aktualnego portfela; najwyżej 30% portfela w otwartych zakładach |
| Piłka | gole over/under 2.5 w 11 ligach: E0, SP1, I1, D1, F1 (Top 5), N1, P1, B1, T1, SC0, G1 |
| Bukmacherzy – piłka | William Hill, Grosvenor, Casumo, LeoVegas: w darmowych danych tylko oni mają over/under 2.5 (Ladbrokes i BetVictor mają tam tylko 1X2) |
| Uczciwa cena – piłka (21.10) | Pinnacle i giełdy (Betfair, Matchbook) z The Odds API, za tę samą liczbę zapytań; agent dalej gra tylko u 4 bukmacherów wyżej |
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
`inj` Kontuzje 2% (Premier League, dane FPL) · `move` Za ruchem rynku 0% (rynek przesunął się o 3+ pkt proc.) ·
`xg` Model: 2.6+ goli → Over (pomysł Radka 21.10; Over zawsze, gdy model spodziewa się 2.6+ gola, bez wymogu przewagi;
na historii −3.7% na stawkę, CLV −4.7%, więc tylko na sucho, dopóki sama się nie sprawdzi – `XG_OVER` w `agent.py`).

NBA: `blend` Model + rynek 3% (aktywna na start) · `model` Sam model 5% · `big` Duża przewaga 6% · `b2b` Zmęczenie 1%
(Under, gdy drużyna grała dzień wcześniej) · `inj` Kontuzje gwiazd 2% (ok. −3 pkt za brakującą gwiazdę) · `move` Za ruchem
linii 0% (linia przesunęła się o 1.5+ pkt).

Przewaga = szansa × kurs − 1. „Vs zamknięcie” (CLV) = nasz kurs × uczciwa szansa tuż przed meczem − 1 (Pinnacle bez marży,
a od 2025/26, gdy football-data go nie ma, giełda Betfair bez marży; ostatecznie średnia rynku). Uczciwa cena przed meczem
(od niej przewaga): Pinnacle z The Odds API → giełdy → football-data → mediana bukmacherów z UK (decyzja 21.10.2026).

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
- **Zdrowie agenta** (monitoring, 21.10): `agent.json` → `runs` – każda aktualizacja (ok. 3 tygodnie): źródła `ok` (fd, odds,
  elo, fpl, espn), liczba błędów, zapytania o kursy, oceny, nowe zakłady, portfel. Strona: Nauka → „Zdrowie agenta” (paski,
  tabela dni, wykres „vs zamknięcie” narastająco). ClubElo nie liczy się do koloru (agent ma zastępcze Elo).
- **Raport tygodnia** (podsumowanie, 21.10): `agent.json` → `weekly` (12 ostatnich) – pisany raz, w pierwszej aktualizacji
  nowego tygodnia, o tygodniu pon–nd: portfel, rozliczone, vs zamknięcie, Over/Under, najlepszy/najsłabszy, krytyk, zmiany.
  Strona: Agent → „Raport tygodnia”; `stan.py` na końcu.
- **Over czy Under?** (licznik, 21.10): `summary.sides` – oceny i zakłady Over/Under z 7 i 30 dni (Nauka, `stan.py`).

## Skille i bezpieczniki Claude (21.10.2026)

Dla Claude pracującego nad tym repozytorium (każdy wątek projektu je ma):

- **Komendy-skille** (`.claude/skills/`): `/stan-agenta` (stan + przebiegi GitHuba, tylko czyta), `/sprawdz-rozliczenia`,
  `/diagnoza` (model na historii i źródła przez „Linia Goli – diagnoza”), `/przekazanie` (na koniec rozmowy: „Na czym
  skończyliśmy”, HISTORIA.md, bezpieczny push).
- **Bezpiecznik** (`.claude/hooks/straznik.py`, hook PreToolUse w `.claude/settings.json`): blokuje `engine.py` bez `--out`
  albo z `--out gole`, ręczne zmiany `gole/agent.json` / `gole/agent_analizy.json` (Edit/Write, `>`, `sed -i`, `rm`, `mv`,
  `cp` na nie) i force push. Czytanie i kopiowanie tych plików do folderu tymczasowego działa. Uwaga: blokuje też polecenia,
  które tylko zawierają taki tekst (np. test z napisem force push) – takie rzeczy rób przez plik ze skryptem.
- **Testy automatyczne**: „Linia Goli – testy” na GitHubie (wyżej, „Jak to działa automatycznie”).
- **Wtyczki Claude Code (23.10.2026, Radek wysłał screen z filmu i napisał „zainstaluj te wtyczki”)** – włączone
  w `.claude/settings.json` (`enabledPlugins` + `extraKnownMarketplaces`), więc każdy wątek projektu ładuje je sam:
  `claude-code-setup` (podpowiada automatyzacje dla repo), `document-skills` (Word, Excel, PowerPoint, PDF) i `skill-creator`
  (tworzenie własnych skilli) – to „Agent Skills” z filmu, `frontend-design` (wygląd stron), `security-guidance` (po każdej
  zmianie kodu Claude sam sprawdza bezpieczeństwo; przegląd zużywa trochę limitu użycia Claude). Pakiet `example-skills`
  pominięty – dubluje frontend-design i skill-creator.
  Tego samego wieczoru Radek: „zainstaluj wszystkie możliwe wtyczki” → wybrał (z opcji) wszystkie darmowe wtyczki Anthropic,
  które działają bez kont: `claude-md-management`, `code-simplifier`, `feature-dev`, `hookify`, `commit-commands`,
  `claude-security`, `playground`, `project-artifact`, `session-report`, `pyright-lsp` oraz styl **tłumaczący**
  (`explanatory-output-style` – Claude wyjaśnia swoje wybory; odpowiadaj dalej po polsku). Razem 16 wtyczek, ok. 3.5 tys.
  tokenów na sesję. Pominięte: ok. 270 łączników do firm (konta, często płatne; w chmurze Claude Code wtyczki-łączniki
  MCP i tak są wyłączone), `learning-output-style` (Radek wybrał tłumaczący), języki programowania spoza repo, matematyka,
  `ralph-loop` (zjada limit), `code-review`/`pr-review-toolkit` (tylko do pull requestów), `agent-sdk-dev` (płatne API).
  Uwaga: `/commit-commands:commit-push-pr` nie robi rebase – przed pushem i tak `git fetch origin main && git rebase origin/main`.
- **Cotygodniowa rutyna Claude – jeszcze nieaktywna.** Rutyny utworzone narzędziem z rozmowy dostają sesję bez podpiętego
  repozytorium: dwa testy 21.10 sprawdziły stan, ale push dostał 403 (i poszło powiadomienie). Obie usunięte. Rutynę musi
  utworzyć Radek w claude.ai/code → Routines (repozytorium `rzarzycki98-hash/Radek` z prawem zapisu, poniedziałek ok. 7:45
  czasu UK, bez powiadomień); gotowy tekst polecenia: `.claude/rutyna-poniedzialkowa.md`. Zostaje pusta sesja
  „Linia Goli – rutyna poniedziałkowa” (nieużywana, można ją zarchiwizować).

## Źródła danych (wszystkie darmowe)

- **football-data.co.uk** – wyniki, gole, strzały celne, kursy zamknięcia; zakończone sezony pobierane raz. Od połowy
  2025/26 bez Pinnacle – są kursy giełdy Betfair (BFE przed meczem, BFEC na zamknięcie).
- **The Odds API** – 500 zapytań na miesiąc; piłka: 10 wybranych bukmacherów (`engine.FOOT_BOOKMAKERS`: Pinnacle, Betfair,
  Matchbook, 4 bukmacherów agenta, Ladbrokes, BetVictor) – kosztuje tyle co cały region UK, 2 zapytania na ligę (1X2 + gole);
  NBA 1 (region UK); kursy tylko dla lig
  z meczem w ciągu 54 h, odświeżane co 10 h; przydział dzienny = (zostało − 10 − rezerwa NBA) / dni do końca miesiąca.
- **ClubElo** – ranking siły klubów (CSV raz dziennie, po błędzie kolejna próba po 6 h); gdy nie działa → Elo z wyników
  ligi. Od 17.10.2026 API ClubElo odpowiada HTTP 502 (awaria po ich stronie).
- **Fantasy Premier League** – kontuzje i zawieszenia w Premier League.
- **ESPN** – NBA: wyniki i terminarz (dzień po dniu, zakończone dni z pamięci), najlepsi strzelcy, raport kontuzji (co 3 h).
  Piłka (od 21.10.2026): zapasowe wyniki (`zrodla.ESPNScores`) dla meczów, których football-data nie ma 72 h po meczu – tylko
  do rozliczeń, model uczy się wyłącznie na football-data.

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
- Model na historii: `python3 gole/testy/historia.py` (tylko z internetem, czyli na GitHub Actions – przebieg „Linia Goli –
  diagnoza”; lokalnie `--local DIR` na danych symulowanych). Źródła danych z GitHuba: `gole/testy/diagnoza_zrodel.py`.
- Playwright w chmurze Claude: `pip install playwright==1.56.0` (pasuje do Chromium w `/opt/pw-browsers`).
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
