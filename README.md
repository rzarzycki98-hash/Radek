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

## Linia Goli – over/under goli

Aplikacja do analizy over/under goli w 5 czołowych ligach (Premier League, LaLiga, Serie A, Bundesliga, Ligue 1).

Adres: https://rzarzycki98-hash.github.io/Radek/gole/

Działa sama: co 4 godziny GitHub Actions (`.github/workflows/linia-goli.yml`) pobiera wyniki i kursy
z [football-data.co.uk](https://www.football-data.co.uk), przelicza model i zapisuje dane w folderze `gole/`.

- **Mecze**: prawdopodobieństwo over/under 1.5 / 2.5 / 3.5, oczekiwane gole, kursy bukmacherów i przewaga modelu.
- **Dziennik**: typy „na sucho”. Gdy model widzi przewagę powyżej 5% przy kursie Bet365, typ zapisuje się sam,
  a po meczu sam się rozlicza (stawka 1 jednostka): zysk, ROI, porównanie z kursem zamknięcia.
- **Model**: test na dwóch ostatnich pełnych sezonach, każdy mecz przewidziany tylko z wcześniejszych danych.

Uczciwie: w teście historycznym (sezony 2023/24–2025/26, ok. 4 300 meczów) model był mniej trafny niż kursy
bukmacherów, a zakłady z „przewagą” traciły ok. 5–10% stawek. Dlatego typy są tylko na sucho.
Pomoc przy problemach z hazardem: [BeGambleAware](https://www.begambleaware.org), GamCare 0808 8020 133.

| Plik | Do czego służy |
| --- | --- |
| `gole/index.html` | aplikacja |
| `gole/engine.py` | pobieranie danych, model, dziennik, test |
| `gole/data.json`, `gole/journal.json` | dane tworzone automatycznie |
