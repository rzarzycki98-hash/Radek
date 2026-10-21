---
name: przekazanie
description: Zakończenie sesji pracy nad Linią Goli – aktualizacja „Na czym skończyliśmy” w CLAUDE.md, dopisanie decyzji Radka do gole/HISTORIA.md i bezpieczne wypchnięcie. Użyj na koniec każdej rozmowy, w której coś się zmieniło albo Radek coś postanowił.
---

# Przekazanie (handover) do następnej rozmowy

1. `CLAUDE.md`, sekcja „Na czym skończyliśmy – <data>”: data, co zrobione (krótko, z liczbami), co wdrożone
   i czy przebieg na GitHubie przeszedł, lista „Do sprawdzenia w najbliższych dniach” (usuń załatwione, dopisz nowe).
   Gdy zmieniły się źródła, pliki, testy albo zasady – popraw też odpowiednie sekcje niżej w `CLAUDE.md`.
2. `gole/HISTORIA.md`: nowe decyzje Radka na końcu osi czasu (dzień, o co prosił, co wybrał i dlaczego) oraz tabela
   „Pomysły Radka – co się z nimi stało”, jeśli dotyczy.
3. W plikach .md nie wpisuj dwóch klamer otwierających obok siebie ani klamry z procentem (GitHub Pages / Jekyll).
4. Commit po polsku, potem `git fetch origin main && git rebase origin/main` i push (nigdy force push).
   Gdy sesja ma własną gałąź `claude/...`, zsynchronizuj ją z main merge'em (bez force push).
5. Na końcu jedno-dwa zdania dla Radka: co zapisane i na co patrzeć w kolejnych dniach.
