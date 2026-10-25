# Weryfikacja integracji — 25 października 2026

Nie użyto logowania, prywatnych API ani obchodzenia zabezpieczeń.
Próby korzystały z SafeHTTP i sprawdzały robots.txt przed kategorią/produktem.

| Sklep | Faktyczna próba | Wynik |
|---|---|---|
| Media Expert | `/gaming/playstation-5/konsole-ps5` | HTTP 403, `blocked`, bez danych ceny |
| RTV EURO AGD | `/konsole-playstation-5.bhtml` | HTTP 403, `blocked`, bez danych ceny |
| x-kom | `/` | 200, brak linku pasującego do filtra skryptu |

Zapis tej próby: `docs/live-verification.json`; narzędzie: `scripts/probe_stores.py`.
Nie oznacza to, że każdy produkt sklepu zawsze zwróci taki sam wynik.

Następnie w publicznych wynikach wyszukiwania znaleziono konkretną kartę:
[Sony PlayStation 5 Slim 1195326](https://www.x-kom.pl/p/1195326-konsola-playstation-sony-playstation-5-slim.html).
Bezpośredni test CLI o 17:50:16 UTC (18:50 CET) zwrócił poprawny odczyt:

```powershell
python -m price_sentinel --db data/live-check.sqlite3 check --url "https://www.x-kom.pl/p/1195326-konsola-playstation-sony-playstation-5-slim.html"
```

JSON-LD Product ma nazwę Sony PlayStation 5 Slim, sku 1195326 i markę Sony. Offer zawiera
price=3399, priceCurrency=PLN i NewCondition. Widoczna cena HTML to również 3 399,00 zł;
raty 339,90 zł × 10 są osobno. JSON-LD nie ma availability. Widoczna strona opisuje
przedsprzedaż z wysyłką od 2 listopada 2026; parser zwraca ostrożnie „nieznany”.

Zminimalizowany rzeczywisty JSON-LD: `tests/fixtures/xkom-1195326-2026-10-25.html`.
Usunięto opinie, oceny i obrazy, zachowano cenę i identyfikatory. `verified=True` oznacza
**tylko zgodność ceny tej jednej karty**, nie kompletną obsługę sklepu i dostępności.
Pozostałe fixture'y są syntetyczne, generowane w `tests/conftest.py`.

## Ograniczenia serwisów

robots.txt jest wymagany, także po redirectach. Nieudany odczyt reguł blokuje produkt;
Protego obsługuje wildcardy i priorytet reguł. Robots nie zastępuje warunków serwisu.
Odczytano także [regulamin x-kom](https://www.x-kom.pl/regulamin), obowiązujący od 5 marca
2026. Część III pkt 14 zastrzega możliwość blokowania automatyzacji i scrapingu powiązanych
z zakłócaniem działania, naruszeniem bezpieczeństwa lub nieuprawnionymi korzyściami.
To istotne ograniczenie; odczyt techniczny nie oznacza zgody na dowolną skalę ani publikację.
Nie wysyłano zapytań o zgodę i nie akceptowano regulaminu w imieniu użytkownika.
Przed większym monitoringiem/publicznym udostępnianiem danych należy potwierdzić zakres
dozwolonego użycia ze sklepem. Blokad Media Expert/EURO nie obchodzono; ich pełna weryfikacja
warunków i produktów pozostaje otwarta.

## Niesprawdzone integracje

- Poprawny odczyt cen Media Expert/EURO i więcej kart/warunków x-kom.
  W kolejnym etapie wykonano próby konkretnych kart: nadal 403; szczegóły w ACCESS_RESEARCH.md.
- Webhook i sesja bota z rzeczywistymi sekretami; żadnych wiadomości testowych nie wysłano.
- Uruchomienie GitHub Actions, uprawnienia i rzeczywisty push gałęzi danych.
- Nie przeprowadzono audytu prawnego ani gwarancji ciągłości odczytu.

Testy jednostkowe są offline: autouse fixture blokuje DNS i połączenia socketów.
Żadna syntetyczna obserwacja nie trafia do domyślnej bazy użytkownika.
