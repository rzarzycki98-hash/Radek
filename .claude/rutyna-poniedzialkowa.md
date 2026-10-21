# Rutyna „Linia Goli: poniedziałkowe sprawdzenie” – tekst do wklejenia w claude.ai/code → Routines

Ustawienia: repozytorium `rzarzycki98-hash/Radek` z prawem zapisu, co poniedziałek ok. 7:45 (czas UK), bez powiadomień.

Polecenie:

Cotygodniowe sprawdzenie agenta Linii Goli. Pisz po polsku, prosto, bez żargonu.
1. Przejdź na najnowszy main (git fetch origin main, git checkout main, git pull --ff-only). Przeczytaj CLAUDE.md i gole/HISTORIA.md i trzymaj się zasad z nich (nie uruchamiaj engine.py do gole/, nie edytuj ręcznie gole/agent.json ani gole/agent_analizy.json, przed pushem rebase na origin/main, nigdy force push, tylko darmowe dane).
2. Użyj skilli projektu: /stan-agenta, potem /sprawdz-rozliczenia. Sprawdź też najnowszy „Raport tygodnia” (agent.json → weekly), „Zdrowie agenta” (agent.json → runs), licznik Over/Under, ostatnie przebiegi „Linia Goli – aktualizacja danych” i „Linia Goli – testy” na GitHubie oraz listę „Do sprawdzenia w najbliższych dniach” w CLAUDE.md.
3. Jeśli znajdziesz oczywisty, mały błąd w kodzie: napraw go, uruchom python3 gole/testy/test_skills.py i test strony, wypchnij na main zgodnie z CLAUDE.md i poczekaj na zielony przebieg. Większych zmian, progów, taktyk ani decyzji Radka nie zmieniaj – opisz je jako propozycję z opcjami.
4. Na koniec użyj /przekazanie: dopisz wynik sprawdzenia (data, liczby, co działa, co nie, propozycje) do „Na czym skończyliśmy” w CLAUDE.md i wypchnij na main (rebase, bez force push).
