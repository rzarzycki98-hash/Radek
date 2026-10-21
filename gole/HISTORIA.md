# Linia Goli i agent do obstawiania – historia rozmów i ustaleń

Ten plik zbiera rozmowy Radka z Claude o Linii Goli i agencie do obstawiania (od 14.10.2026): co zbudowaliśmy, co Radek
postanowił i dlaczego, co odłożyliśmy. Bieżący stan, zasady pracy i rzeczy do sprawdzenia są w `CLAUDE.md`.

Od 18.10.2026 wieczorem rozmowy o agencie toczą się w **projekcie w Claude Code** (claude.ai/code → Projects) na tym
repozytorium. Każdy wątek projektu czyta `CLAUDE.md`, a przez niego ten plik. Nowe ważne decyzje Radka dopisuj na końcu
osi czasu.

## Czego Radek chce

- Analizy meczów piłkarskich i koszykówki (NBA) opartej na danych: tabela, forma, statystyki meczów. Dane mają się pobierać
  same, bez ręcznej pracy.
- Wszystko ma działać samo (GitHub Actions) i tylko na darmowych narzędziach i danych.
- Agenta, który sam obstawia **wirtualnymi** pieniędzmi i uczy się na swoich błędach. Radek uczy się razem z nim,
  na jego wynikach.
- Analizy przed meczem, w trakcie i po meczu, w jak największej liczbie lig.
- Prawdziwe pieniądze dopiero po spełnieniu kryteriów gotowości – i tylko z decyzji Radka. Agent jedynie informuje.

## Oś czasu

### 14.10.2026 – początek

- Pierwsza wersja Linii Goli powstała jako strona w Claude: dane z openfootball, odświeżanie na żądanie. Od 15.10 zastąpiła
  ją wersja na GitHubie; zadanie „Linia Goli: odświeżanie na żądanie” jest wyłączone.
- Późnym wieczorem: repozytorium `Radek` i aplikacja Listy (zadania i zakupy, działa bez internetu).

### 15.10.2026 – Linia Goli na GitHubie (v1 → v3)

- v1 (w nocy): automatyczna analiza goli over/under z dziennikiem typów na sucho; aktualizacja przez GitHub Actions.
- Kursy bukmacherów z UK przez The Odds API (sekret `ODDS_API_KEY`): najpierw Ladbrokes i BetVictor, potem porównanie
  wszystkich bukmacherów z UK i strategia „kurs ponad rynek”.
- v3 (południe): 38 lig, rynek 1X2, model uczący się przy każdej aktualizacji, test walk-forward każdej ligi, bezpiecznik
  (liga sama się wyłącza), przewaga liczona względem uczciwego kursu zamknięcia (Pinnacle bez marży).
- Popołudnie: wygląd jak aplikacja bukmacherska, lista meczów z wyborem dnia, oznaczenia „Warte uwagi” i „Duża szansa”,
  analiza statystyk przy każdym meczu (tabela, forma, u siebie i na wyjeździe, mecze bezpośrednie) z wagami uczonymi
  na historii, „Moje zakłady”, kontuzje i zawieszenia w Premier League (Fantasy Premier League), archiwum rozliczonych typów
  i bilans sezon po sezonie, kalkulator na żywo w karcie meczu (minuta, wynik, czerwone kartki).
- Trafność ocen „Warte uwagi” w teście historycznym: 1X2 67%, gole 63% – punkt odniesienia dla wyników na żywo.

### 16.10.2026

- Bez zmian w Linii Goli. Radek zaczął osobny projekt: Agent Tradingowy (akcje, poza tym repozytorium).

### 17.10.2026 – agent

- Rano: agent, który sam obstawia wirtualnymi pieniędzmi i uczy się na swoich zakładach (`gole/agent.py`), NBA
  (`gole/nba.py`), strona przebudowana wokół agenta, dodatkowe darmowe dane: ClubElo (z zastępczym Elo z wyników ligi,
  gdy ClubElo nie odpowiada), kontuzje (Premier League i NBA), ruchy kursów.
- Decyzje Radka, w skrócie (pełna tabela w `CLAUDE.md`):
  - portfel £1000 wspólny dla piłki i NBA, stawka 1% portfela, najwyżej 30% portfela w grze;
  - piłka: tylko gole over/under 2.5 – Radek wybrał gole zamiast wyniku 1X2; 11 lig: Top 5 + Holandia, Portugalia,
    Belgia, Turcja, Szkocja, Grecja;
  - kursy w piłce: William Hill, Grosvenor, Casumo, LeoVegas, bo tylko oni podają over/under 2.5 w darmowych danych
    (Ladbrokes i BetVictor mają tam tylko 1X2);
  - NBA: suma punktów, Ladbrokes i BetVictor, a gdy nie mają linii – inny bukmacher z UK (bez giełd);
  - agent ocenia każdy mecz, a stawia tylko przy przewadze; kilka taktyk gra na sucho, pieniądze idą za najlepszą;
  - nauka: sam zmienia zasady po 30 rozliczonych zakładach, najwyżej raz na tydzień, z powodem w dzienniku;
  - gotowość na prawdziwe pieniądze (tylko informacja): 90+ dni, 200+ zakładów, zysk, kursy lepsze niż zamknięcie;
  - raport tylko na stronie, bez powiadomień na telefon;
  - strona: Agent, Mecze, Nauka, Wyniki, Ligi; usunięte „Moje zakłady” i stary dziennik „Typy”.
- Pierwsze zakłady (po £10): Roma – Genoa Under 2.5 @ 2.00 (17.10) i Brighton – Crystal Palace Under 2.5 @ 2.40 (18.10).
- Wieczorem: `CLAUDE.md` (notatki dla Claude) i `gole/stan.py` (stan agenta w kilku linijkach).

### 18.10.2026 – skille i przejście do projektu

- Radek zobaczył grafikę „AI Agent Skills You Must Learn” (tool calling, memory, RAG, multi-agent i inne) i zapytał, czy do
  jego agentów można dodawać skille. Poprosił: „Stwórz dla niego wszystkie skille, które się przydają” – dla obu agentów,
  budowane od razu.
- Agent Linii Goli dostał 4 skille (szczegóły techniczne w `CLAUDE.md`, sekcja „Skille agenta”):
  - **Krytyk** (wiele agentów): drugi, niezależny przegląd każdego zakładu przed postawieniem, 5 ostrzeżeń, każde blokuje
    zakład; zablokowane typy agent śledzi na sucho i sam wyłącza blokady, które przeszkadzają;
  - **Analiza po meczu** (pamięć): ocena każdego rozliczonego zakładu – zasłużona wygrana, szczęście, pech, błąd ceny –
    z lekcją, oraz karta „Szczęście czy umiejętność?”;
  - **Kalibracja** (samoocena): czy szanse agenta się sprawdzają, porównanie z rynkiem, też w każdej lidze;
  - **Wnioski** (pamięć): proste zdania o tym, gdzie agent zarabia, a gdzie traci.
- Z grafiki pominęliśmy Docker, AWS, Vercel, bazy wektorowe (Pinecone, ChromaDB, FAISS), GraphQL i podobne: to narzędzia do
  dużych systemów, a darmowy agent na GitHub Actions ich nie potrzebuje.
- Testy na kopiach (`gole/testy/`) przeszły; pierwsza aktualizacja na GitHubie po zmianie – bez błędów. Do wieczora
  wszystkie aktualizacje bez błędów, nic jeszcze nierozliczone (wyniki przychodzą 1–2 dni po meczu), krytyk niczego nie
  zablokował.
- Uwaga: liczby kalibracji z testu 18.10 (np. „model zaniża over”) pochodziły z wyników losowych użytych w teście, więc nic
  nie mówią o modelu. Prawdziwa kalibracja pojawi się po pierwszych rozliczonych meczach.
- Wieczorem Radek postanowił przenieść rozmowy o agencie do projektu w Claude Code. Wybrał: rozmowy w Claude Code na tym
  repozytorium, a w projekcie „ustalenia i historia” (ten plik), bez pełnego zapisu słowo w słowo.

### 19.10.2026 – poniedziałkowe sprawdzenie, koniec rozmowy sprzed projektu

- Rano i po południu (zadanie „Sprawdzenie rozliczeń Linii Goli” w rozmowie sprzed projektu): wszystkie aktualizacje
  z weekendu bez błędów, ale football-data.co.uk do poniedziałku po południu nie wrzuciło wyników z 17–18.10 (pliki
  pobierają się poprawnie, tylko bez nowych wyników), więc nic się jeszcze nie rozliczyło – ani prognozy, ani zakłady agenta.
- Poprawka: bukmacher pisze „Sint Truiden”, football-data „St Truiden” – dodane dopasowanie nazwy (Belgia).
- Wieczorem Radek poprosił o przeniesienie tej rozmowy do projektu. Ważne rzeczy z niej są w tym pliku i w `CLAUDE.md`;
  dalsze rozmowy tylko w projekcie.
- Wcześniej w tej rozmowie (15.10) Radek pytał też:
  - czy aplikacja zbiera dane i uczy się na przyszłość – tak: przy każdej aktualizacji uczy się od nowa na wszystkich
    zakończonych meczach z 6 ostatnich sezonów; z czasem będzie trochę lepsza, bez wielkich skoków, bo bukmacherów trudno
    pobić. Wtedy też rozliczone prognozy zaczęły się zapisywać na stałe (archiwum, bilans sezon po sezonie);
  - czy może wrzucać na stronę screeny meczów na żywo – patrz tabela pomysłów niżej.

### 21.10.2026 – naprawa błędów i skuteczność agenta (projekt w Claude Code)

- Radek poprosił o dwie rzeczy: naprawić błędy i zwiększyć skuteczność agenta. Zasady: najpierw diagnoza z liczbami,
  przy większych zmianach opcje do wyboru, nie dopasowywać niczego do kilku ostatnich wyników, progów i taktyk agenta nie
  zmieniać ręcznie (to robi jego nauka) – poprawiać model i dane.
- Stan na start: portfel £1001.60, 4 rozliczone zakłady, 7 z 8 zakładów na Under, „vs zamknięcie” −4.6%, „Sam model”
  na sucho −21.6% (30 typów). Radek podejrzewał, że przewaga na Under bierze się ze skrzywienia modelu.
- Błędy: test skilli liczył też zakłady rozliczone naprawdę (błąd testu); ClubElo – serwer ich API odpowiada HTTP 502 na
  każde zapytanie (awaria po ich stronie, nie blokada GitHuba); nieudane pobrania zastępowane starą kopią były niewidoczne;
  zapasowa wczorajsza kopia ClubElo nigdy się nie wczytywała. Wszystko poprawione; doszło ostrzeżenie o starych wynikach.
- Odkrycie: football-data od połowy sezonu 2025/26 nie podaje kursów Pinnacle (są kursy giełdy Betfair). Na żywo „uczciwa
  cena” była medianą tych samych 4 bukmacherów, u których agent gra (inni z UK nie podają over/under 2.5 w darmowych danych).
- Test na historii (11 lig, ok. 11 tys. meczów): skrzywienie modelu w pełnych sezonach małe (−0.4 do −2.4 pkt proc.);
  w tym sezonie −7, ale rynek też −4.5 (sezon bramkowy). Model w meczach, w których rynek daje overowi 58%+, daje 2–4 pkt
  mniej – stąd „przewagi” na Under. Kalibracja nie pomogła; model nie dodaje informacji ponad rynek; taktyka „Model + rynek”
  na historii −14%, CLV −3.9%. Waga modelu na żywo (0.6–0.8 w kilku ligach) była dużo wyższa niż w teście (0.11).
- **Decyzje Radka:** uczciwa cena z Pinnacle i giełd (The Odds API, 10 wybranych bukmacherów za tę samą liczbę zapytań;
  ze strony znikają kursy 1X2 innych bukmacherów z UK); waga modelu dobierana na dłuższej historii i tylko przy realnej
  poprawie (na historii: 538 → 82 typy, Under 66% → 49%, CLV −4.7% → −2.2%); kalibracji nie dodawać; ESPN jako zapasowe
  źródło wyników (gdy football-data spóźnia się 3+ dni).
- NBA sprawdzone tylko pod kątem błędów w kodzie (brak); strojenie później.

## Pomysły Radka – co się z nimi stało

| Pomysł | Co się stało |
| --- | --- |
| Analiza oparta na statystykach (tabela, forma, mecze) zamiast samych kursów | Zrobione: statystyki przy każdym meczu, taktyki „Statystyki potwierdzają” i „Sam model” grają na sucho; pieniądze idą za taktyką, która się sprawdza |
| Wszystko automatycznie, bez udziału Radka | Zrobione: GitHub Actions co 4 godziny |
| NBA (suma punktów) | Zrobione 17.10; agent gra od 5. meczu każdej drużyny (sezon od 20.10) |
| Kontuzje i składy | Zrobione za darmo: Fantasy Premier League (Premier League) i raport ESPN (NBA). Czytanie newsów przez AI odłożone, bo płatne |
| Jak najwięcej lig | Silnik liczy 38 lig, agent gra w 11 |
| Ligi młodzieżowe (U19, U20) | Jeszcze nie ma: trzeba by znaleźć darmowe źródło ich wyników i kursów |
| Zbieranie wyników i kursów w czasie | Zrobione: archiwum prognoz, oceny agenta z 400 dni, pamięć kursów |
| Analiza przed, w trakcie i po meczu | Przed: tak. W trakcie: kalkulator na żywo (bez zakładów na żywo, bo nie ma darmowych kursów na żywo). Po: rozliczenie, porównanie z kursem zamknięcia, analiza po meczu (18.10) |
| Uczenie się na błędach | Zrobione: nauka zasad (17.10), skille (18.10) |
| Zapasowe źródło wyników, gdy football-data się spóźnia | Zrobione 21.10: ESPN (tylko do rozliczeń) i ostrzeżenie na stronie |
| Korekta (kalibracja) skrzywionego modelu | Sprawdzone 21.10 na historii – nie pomaga; zamiast tego uczciwa cena z Pinnacle i giełd oraz ostrożniejsza waga modelu |
| Wrzucanie na stronę screenów meczów na żywo | Strona sama nie odczyta obrazka (potrzebna byłaby płatna AI, a klucza nie da się ukryć w publicznej stronie). Screeny można wysyłać do Claude w rozmowie: odczyta wynik, minutę, statystyki i kursy i oceni szanse. Do tego w karcie meczu jest kalkulator na żywo (15.10) – Radek nie był pewien, czy będzie z niego korzystał |
| Wynik 1X2 dla agenta | Odrzucone – Radek wybrał gole |
| Powiadomienia na telefon | Odrzucone – Radek wybrał raport tylko na stronie |

## Zadania zaplanowane związane z agentem

- **GitHub Actions** „Linia Goli – aktualizacja danych”: co 4 godziny, sama pobiera dane, ocenia mecze i obstawia.
- **„Sprawdzenie rozliczeń Linii Goli”** (Claude, 19.10.2026, w rozmowie sprzed projektu): zrobione, wyników z weekendu
  jeszcze nie było. Dokończenie 20.10.2026 ok. 10:30 czasu UK: wyników nadal brak (najpewniej przerwa po stronie
  football-data); Radkowi zaproponowane zapasowe źródło wyników z ESPN i ostrzeżenie o starych wynikach na stronie – czeka
  na jego decyzję (szczegóły w `CLAUDE.md`). W tamtej rozmowie nie ma już żadnych zadań.
- **„Linia Goli: odświeżanie na żądanie”**: stara wersja strony w Claude, wyłączona.
- Nowe sprawdzenia lepiej ustawiać w projekcie (Claude w projekcie tworzy je jako rutyny, widoczne w zakładce Routines).
