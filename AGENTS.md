# Zasady rozwoju

- Python 3.12; CLI i opcjonalny bot, bez strony WWW. Wspólne modele i usługi.
- Pieniądze w groszach, czas bazy w UTC, raporty Europe/Warsaw.
- Poprawność i bezpieczeństwo ważniejsze od liczby sklepów. Nie zgaduj selektorów/API.
- Nowy sklep wymaga jawnej allowlisty, adaptera, robots.txt i sprawdzenia ograniczeń serwisu.
- Nigdy nie obchodź CAPTCHA, logowania i blokad. Błędy nie są ceną zero ani brakiem towaru.
- Nieznana dostawa nie jest darmowa; cashback i kody nie obniżają ceny bezwarunkowej.
- Nie łącz podobnych nazw. Ręczne grupowanie wymaga potwierdzenia identyczności wariantu.
- Rzeczywiste fixture'y wymagają źródła i daty; syntetyczne oznaczaj jawnie.
- Historia zaczyna się przy obserwacji. Nie generuj historii ani prognoz cen.
- Sekrety tylko z env, nigdy w logach, URL-ach poleceń, bazie lub snapshotach.
- Wszystkie wejścia procesów blokują wspólną bazę; bot serializuje operacje workerów.
- Publiczne dane tylko po świadomym opt-in; nie używaj Actions cache jako bazy.
- Testy: `python -m pytest -q`, `ruff check src tests scripts`,
  `ruff format --check src tests scripts`. Jednostkowe testy nie korzystają z sieci.
- Aktualizuj README, ROADMAP i docs/VERIFICATION.md zgodnie z rzeczywistymi wynikami.
