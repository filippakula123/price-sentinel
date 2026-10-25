# Badanie dostępu — 25 października 2026

Wyniki konkretnych, jawnych prób SafeHTTP: [access-research.json](access-research.json).
Po pobraniu robots wykonano pojedyncze próby, bez retry, logowania i obchodzenia blokad.
Użyto User-Agent PriceSentinel/0.1, poprawnego Host/SNI, Accept oraz Accept-Language pl-PL.
Nie użyto nagłówków podszywających się pod Googlebota ani sesji zalogowanej przeglądarki.

| Źródło | Media Expert | RTV EURO AGD |
|---|---|---|
| robots.txt | odczytany; brak deklaracji Sitemap | odczytany, deklaruje sitemap-index.xml |
| Kategoria PS5 | HTTP 403, 19:39:18 UTC | HTTP 403, 19:39:24 UTC |
| Konkretna karta produktu z publicznego linku | HTTP 403, 19:39:56 UTC | HTTP 403, 19:40:10 UTC |
| Sitemap | brak adresu w pobranym robots; nie zgadywano endpointów | indeks odczytany: 40121 bajtów; adresy podmap, nie ceny |
| JSON-LD produktu | nieodczytany z powodu blokady aplikacji | nieodczytany z powodu blokady aplikacji |
| RSS z cenami | nie potwierdzono źródła | nie potwierdzono źródła |
| Publiczne API katalogu cen | nie potwierdzono; znaleziono API sprzedawców z kluczem | nie potwierdzono |
| Status adaptera | **blocked** | **blocked** |

Karty wykorzystane w badaniu (różne warianty; nie zostały ze sobą powiązane):

- [Media Expert — PS5 Slim + Minecraft](https://www.mediaexpert.pl/gaming/playstation-5/konsole-ps5/konsola-sony-playstation-5-slim-e-chassis-minecraft-gra-ps5)
- [EURO — PS5 Digital Slim 825 GB](https://www.euro.com.pl/konsole-playstation-5/sony-playstation-5-digital-slim-e-chassis-ps5-825gb-adex.bhtml)
- [EURO — indeks sitemap](https://www.euro.com.pl/sitemap-index.xml), wskazany przez robots.

Publiczna [dokumentacja integracji Media Expert z Apilo](https://www.mediaexpert.pl/centrum-pomocy-dla-sprzedawcow/integracja-z-apilo)
wymaga loginu Mirakl i klucza API. Dotyczy kanału sprzedaży, nie potwierdzonego anonimowego
źródła cen całego katalogu. Nie pobierano prywatnych endpointów, nie rejestrowano konta,
nie dodawano nowych hostów do allowlisty. Program partnerski nie został użyty jako feed.

Wyniki wyszukiwarki potrafią pokazać treść strony niedostępnej dla Price Sentinel;
nie zastępowano nimi odpowiedzi adaptera. Nie oznaczają poprawności JSON-LD pobranego
przez aplikację i nie tworzą historii. Nie stwierdzamy, że żaden RSS/API nigdy nie istnieje;
nie znaleziono potwierdzonego źródła nadającego się do tej integracji.

`blocked` opisuje zaobserwowany stan dostępu, nie diagnozę przyczyny infrastrukturalnej
403 ani ocenę prawną. Kontrolowane `verify-store` może sprawdzić przyszłą zmianę dostępu.
Sitemap nie daje ceny i sam w sobie nie odblokowuje karty produktu.

Kontrola porównawcza x-kom przez `verify-store` o 19:40:14 UTC zwróciła `ok`/`partial`.
Nie utworzyła obserwacji. Brak availability nadal daje „nieznany”.
