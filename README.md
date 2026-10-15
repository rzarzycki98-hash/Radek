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
