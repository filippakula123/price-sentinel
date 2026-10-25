# Stan implementacji

## Gotowe w kodzie

- Modele produktów/ofert/obserwacji/reguł, SQLite i wspólne usługi.
- Trzy osobne klasy adapterów z parserem JSON-LD; cena jednej karty x-kom sprawdzona online.
- Bezpieczny HTTPS z DNS/IP pinning, robots z wildcardami, redirecty, retry i limity.
- CLI: CRUD, pauza, progi/spadki/powrót dostępności, historia i minima 7/30/90,
  ręczne grupowanie, porównania, wykres PNG z lukami, eksport CSV/JSON i raporty.
- Webhook Discord, trwały outbox, deduplikacja, cooldown, ponowienia i blokada mentions.
- Osobny opcjonalny bot z komendami slash i autoryzacją właściciela/serwera.
- Blokada procesu, snapshot/restore, CI i domyślnie wyłączony workflow publicznego monitoringu.
- Testy offline, syntetyczne przypadki i jeden zminimalizowany rzeczywisty fixture.

## Ograniczenia i dalsze prace

- Media Expert i EURO: HTTP 403 na kategoriach, brak rzeczywistych fixture'ów produktu.
  Adaptery niezweryfikowane. Wymagają dozwolonego odczytu i porównania danych.
- x-kom: cena jednego produktu, bez availability w JSON-LD. Brak zweryfikowanych
  selektorów HTML dla dostępności, dostawy i sklepowej ceny referencyjnej z 30 dni.
- Dostawa i cena referencyjna mają osobne pola, ale obecnie pozostają nieznane.
  Wzmianki o kodach/cashback są ostrzeżeniem, nie wyliczeniem ceny warunkowej.
- Brak wyszukiwania po nazwie i automatycznego łączenia ofert. Helper `identical` nie scala danych.
- Bot sprawdza na żądanie, bez własnej pętli okresowej; CLI nie działa równocześnie.
- Nie wykonano wysyłki prawdziwego webhooka, połączenia bota ani uruchomienia workflow na GitHub.
- Brak synchronizacji wielu baz i gwarancji exactly-once z Discordem. Możliwy duplikat
  po przyjęciu wiadomości przez Discord i awarii przed zapisem potwierdzenia.
- Brak prywatnej persistencji Actions i automatycznej retencji danych; obecny workflow
  jest wyłącznie dla świadomie publicznych watchlist. Monitoruj rozmiar historii i gałęzi.
- Przed większym wdrożeniem: potwierdzić warunki automatycznego odczytu/publicznego użycia
  danych, rozszerzyć rzeczywiste fixture'y i sprawdzić zmiany HTML sklepów.
