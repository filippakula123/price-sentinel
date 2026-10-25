# Plan wdrożenia

1. Rdzeń: konfiguracja, modele, bezpieczny transport HTTPS, adaptery JSON-LD.
2. SQLite, obserwacje, trwała kolejka alertów i jednorazowy CLI.
3. Historia, eksport, porównania, wykresy, raporty.
4. Opcjonalny proces Discord ze wspólnymi usługami i autoryzacją.
5. CI i jawnie włączana publiczna persistencja Actions.
6. Testy offline, lint, próby odczytu rzeczywistych sklepów i uczciwa dokumentacja.

Repo początkowo zawierało tylko README. Nie ma danych do migracji.

Wykonano punkty 1–6. Cena jednej karty x-kom zweryfikowana online; odczyty kategorii
Media Expert i EURO blokowane HTTP 403. Szczegółowy stan i pozostałe ograniczenia:
ROADMAP.md, docs/VERIFICATION.md i docs/TESTING.md. Nie uruchamiano zewnętrznego bota,
webhooka ani workflow; nie publikowano danych.
