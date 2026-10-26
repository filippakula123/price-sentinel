# Stan implementacji

## Gotowe w kodzie

- Modele produktów/ofert/obserwacji/reguł, SQLite i wspólne usługi.
- Trzy osobne klasy adapterów z parserem JSON-LD; cena jednej karty x-kom sprawdzona online.
- Bezpieczny HTTPS z DNS/IP pinning, robots z wildcardami, redirecty, retry i limity.
- CLI: CRUD, pauza, progi/spadki/powrót dostępności, historia i minima 7/30/90,
  ręczne grupowanie, porównania, wykres PNG z lukami, eksport CSV/JSON i raporty.
- Webhook Discord, trwały outbox, deduplikacja, cooldown, ponowienia i blokada mentions.
- Osobny opcjonalny bot z komendami slash i autoryzacją właściciela/serwera.
- Blokada procesu, snapshot/restore, konfiguracja CI i ręczny workflow publicznego monitoringu,
  wyłącznie workflow_dispatch; brak cron. Discord w workflow domyślnie wyłączony.
- `test-webhook`: pojedynczy POST z maskowaniem logów, mocki HTTP i rzeczywista odpowiedź 204.
  Sekret GitHub Actions zapisany jako zaszyfrowany secret, metadane potwierdzone.
- `verify-store`: jedna próba bez retry, plik diagnostyczny, zero obserwacji i alertów.
- `status`: liczniki, sukcesy/błędy sklepów, kolejka webhooków i stan lokalnego snapshotu.
- Testy offline, syntetyczne przypadki i jeden zminimalizowany rzeczywisty fixture.

## Ograniczenia i dalsze prace

- Media Expert i EURO: `blocked`, HTTP 403 na kategoriach i konkretnych kartach produktów
  również po dodaniu jawnych nagłówków. Sitemap EURO dostępny, ale nie daje cen.
  Nie potwierdzono anonimowego API/RSS cen. Brak fixture'ów cen produktu.
- x-kom: cena jednego produktu, bez availability w JSON-LD. Brak zweryfikowanych
  selektorów HTML dla dostępności, dostawy i sklepowej ceny referencyjnej z 30 dni.
- Dostawa i cena referencyjna mają osobne pola, ale obecnie pozostają nieznane.
  Wzmianki o kodach/cashback są ostrzeżeniem, nie wyliczeniem ceny warunkowej.
- Brak wyszukiwania po nazwie i automatycznego łączenia ofert. Helper `identical` nie scala danych.
- Bot sprawdza na żądanie, bez własnej pętli okresowej; CLI nie działa równocześnie.
- Webhook testowy sprawdzony produkcyjnie; nie sprawdzono prawdziwego alertu cenowego,
  jego deduplikacji ani sesji bota. Użycie sekretu w runnerze Actions niezweryfikowane.
  Lokalna próba 26.10.2026 w nowej bazie: próg 10 000 zł > cena 3399 zł, ale dostępność
  nieznana; 0 alertów i 0 wysyłek w dwóch deliver. Regułę testową usunięto.
- CI na Windows/Ubuntu sprawdzony; dwa ręczne runy Actions wykonane (drugi 26.10.2026).
  Restore i push snapshotu działają, ale runner otrzymał 403 dla robots.txt x-kom.
  Druga próba zachowała 2 obserwacje, dodała tylko błąd kontroli, bez duplikatów;
  stan alertów nadal pusty. Wyniki i ograniczenia w docs/TESTING.md.
  Monitoring wstrzymano (PUBLIC_SNAPSHOT_ENABLED=false), cron nie istnieje.
- Brak synchronizacji wielu baz i gwarancji exactly-once z Discordem. Możliwy duplikat
  po przyjęciu wiadomości przez Discord i awarii przed zapisem potwierdzenia.
- Brak prywatnej persistencji Actions i automatycznej retencji danych; obecny workflow
  jest wyłącznie dla świadomie publicznych watchlist. Monitoruj rozmiar historii i gałęzi.
- Przed większym wdrożeniem: potwierdzić warunki automatycznego odczytu/publicznego użycia
  danych, rozszerzyć rzeczywiste fixture'y i sprawdzić zmiany HTML sklepów.
