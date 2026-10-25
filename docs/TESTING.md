# Rzeczywiste wyniki kontroli

Środowisko: Windows, PowerShell, Python 3.12.10, lokalna `.venv`, 25 października 2026.
Zainstalowano projekt przez `python -m pip install -e ".[dev,discord]"`.
Nie użyto sekretów Discord ani GitHub w testach jednostkowych.

| Wykonana kontrola | Wynik |
|---|---|
| `.venv\Scripts\python -m pytest -q --tb=short` | **118 passed**, 5,92 s w regresji po teście rzeczywistego webhooka |
| `.venv\Scripts\ruff check .` | All checks passed |
| `.venv\Scripts\ruff format --check src tests scripts` | 25 files already formatted |
| `.venv\Scripts\python -m pip check` | No broken requirements found |
| `git diff --check` | brak błędów |
| CLI `check --url` na prawdziwej karcie x-kom | sukces; 339900 groszy, dostępność nieznana |
| CLI `chart`, `report daily`, `export`, `snapshot`, `restore`, `list` | sukces na osobnych bazach `data/live-check.sqlite3` i `data/restored-check.sqlite3` |
| Oględziny PNG prawdziwej pojedynczej obserwacji | poprawna etykieta „za mało danych”, oś czasu wokół odczytu |

Testy blokują DNS i sockety. HTTP jest podmieniany przez MockTransport lub jawne atrapy.
Sprawdzono ceny i zaokrąglenia, JSON-LD/HTML, niejednoznaczność ofert, raty/kody/cashback,
403/429/CAPTCHA/sieć, robots z wildcardami, redirecty, prywatny DNS, przypięcie IP/SNI,
limit rozmiaru, warianty, autoryzację Discord, alerty/cooldown/deduplikację/retry,
restart, atomowe odtworzenie snapshotu, historię/minima/luki, wykresy, eksport i raporty/DST.

Rejestracja dziesięciu komend Discord została wykonana offline, z podmienionym sync/run.
Nie jest to test połączenia z Discord. Test webhooka sprawdza payload, mentions i brak
podążania za redirectem, bez faktycznej wiadomości. Test persistencji używa prawdziwego
lokalnego Git i bare remote: sprawdzono push oraz odrzucenie konfliktu bez nadpisania.
Nie jest to run GitHub Actions.

Pierwszy test w sandboxie miał 68 sukcesów i 8 błędów uprawnień do katalogu tymczasowego
pytest. Powtórzono poza sandboxem. Wykryto i naprawiono błąd odczytu blokowanego bajtu
pliku na Windows. Test Discord offline początkowo tworzył event loop z lokalną parą
socketów; zastąpiono go bezpośrednim wykonaniem coroutine z całkowicie podmienionym sync.
Poprawiono także cooldown przy wielu oczekujących alertach i skalę czasu pojedynczego punktu.

Odczyty online i ograniczenia opisuje [VERIFICATION.md](VERIFICATION.md).
Media Expert i EURO pozostają niezweryfikowane po HTTP 403. Sesja bota i prawdziwy alert
cenowy wymagają odrębnego sprawdzenia. Późniejszą weryfikację webhooka, CI, monitora
i publicznego snapshotu opisano w sekcji produkcyjnej poniżej. Harmonogramu nie uruchomiono.

## Etap diagnostyki, statusu i ręcznego workflow

- `test-webhook`: mock HTTP potwierdza dokładnie jeden POST, polską wiadomość i wyłączone
  mentions. Sprawdzono 204, 403, 429 oraz błąd sieci, bez retry. Webhook jest maskowany
  w wynikach, logach httpx/httpcore i standardowym tracebacku błędu. Nie wysyłano
  na tym etapie wiadomości z prawdziwym webhookiem; późniejszy test produkcyjny opisano poniżej.
- `verify-store`: testy sukcesu, 403, 429, robots deny, braku ceny, błędu sieci i obcej
  domeny. Przed i po porównano wszystkie tabele domenowe: żadnych nowych produktów,
  ofert, obserwacji, kontroli ani alertów. Jedna próba produktu, bez retry; robots osobno.
  Query w JSON-ie zamaskowane, cena niezapisywana, ochrona przed nadpisaniem bazy diagnozą.
- Odczyty online (wyłącznie diagnostyczne): karty Media Expert i EURO nadal `blocked`
  (403), x-kom `ok`/`partial`. Robots obu sklepów dostępne, indeks sitemap EURO dostępny.
  Nie potwierdzono alternatywnego RSS ani anonimowego API cen. Dowody i źródła:
  [ACCESS_RESEARCH.md](ACCESS_RESEARCH.md) i [access-research.json](access-research.json).
- `status`: testy liczników, dat ostatniego sukcesu, zachowania ostatniego błędu po sukcesie,
  diagnostyki i kolejki webhooków. Snapshot: stan nowej bazy, zapis poprawny, zmienione dane,
  zmodyfikowany/usunięty plik oraz odtworzenie. Zapis zdalny pozostaje `not_verified`.
  Sprawdzono też zapisane diagnozy bez pomocniczych metadanych: status odczytuje daty
  bezpośrednio z ostatniej diagnozy, zamiast zwracać nieprawdziwe `null`.
- Integracja snapshotu korzysta z rzeczywistej SQLite, parsera/usług oraz ścieżek komend
  `snapshot`/`restore`. Źródło ma 3 obserwacje i alerty `sent`, `pending`, `failed`.
  Dwukrotny restore zachowuje dokładnie te same wiersze; zamknięcie i otwarcie docelowej
  bazy również. Następna dostawa wysyła tylko pending, bez ponowienia sent/failed i bez
  dodania obserwacji. Nie użyto sieci ani prawdziwego webhooka.
- Workflow monitorowania zmieniono na `workflow_dispatch` z `notify=false` domyślnie.
  Usunięto schedule/cron. Na tym etapie przejrzano konfigurację bez runu GitHub Actions;
  dopiero późniejsza próba produkcyjna potwierdziła uprawnienia i zapis snapshotu. Lokalny test Git
  nadal sprawdza push i odrzucenie konfliktu w bare remote.

Wyniki tego etapu dotyczą lokalnego Windows/Python 3.12.10. Prawdziwa sesja Discord
pozostaje niesprawdzona. CI Ubuntu sprawdzono później. Nie dodano nowych sklepów i nie obchodzono blokad.

## Pierwsza weryfikacja produkcyjna — 25 października 2026

Zweryfikowany kod: `e601c9029473575f56ae9907fb8f4d525e89bf77`. Nie zmieniano zachowania
komend ani nie dodawano sklepów. Repozytorium było czyste i zgodne z origin/main;
nie tworzono pustego commita. Prywatnych plików śledzonych przez Git: 0. Reguły ignorowania
.env, baz, danych, logów i snapshot-state sprawdzone. W początkowej próbie webhook
nie był dostępny; późniejszy test z pliku użytkownika opisano poniżej.

| Kontrola | Rzeczywisty wynik |
|---|---|
| Lokalny pytest | 118 passed, 6,09 s |
| Ruff / format / pip check | poprawne; 25 plików poprawnie sformatowanych |
| GitHub CI e601c90 | sukces Windows i Ubuntu, wszystkie kroki lintu/testów |
| Lokalny check x-kom nr 1 | 22:04:09 UTC: status ok, 339900 groszy, dostępność nieznana |
| Lokalny check x-kom nr 2 | 22:04:18 UTC: status ok, 339900 groszy, dostępność nieznana |
| Historia | 2 obserwacje o różnych czasach; bez duplikatów |
| Dwukrotny restore lokalnego snapshotu | identyczne wszystkie tabele domenowe, stan snapshotu ok |
| Publiczny seed | tylko nowa baza z jednym publicznym produktem x-kom; 2 rzeczywiste obserwacje |
| Ręczny Actions, notify=false | run uruchomiony; restore, instalacja i oba zapisy snapshotu udane |
| Odczyt sklepu z runnera | **NIEUDANY: robots_niedostępny:http_403** |
| Stan po runie | 2 wcześniejsze obserwacje zachowane, 1 dodatkowa nieudana kontrola, bez fałszywej ceny |
| Restore zdalnego snapshotu, dwukrotnie | identyczne dane, bez duplikatów; stan alertów zachowany |
| Webhook w logach runu | nie znaleziono niezamaskowanego pełnego webhooka; krok wysyłki był skipped |
| Zabezpieczenie po próbie | PUBLIC_SNAPSHOT_ENABLED=false, brak cron; lokalne testowe odczyty zatrzymane |
| Discord test-webhook | późniejszy test: jedna wiadomość przyjęta, HTTP 204, redakcja logów poprawna |
| Produkcyjna deduplikacja alertów | **NIEZWERYFIKOWANA**: 0 rzeczywistych alertów cenowych |

Dowody z GitHub:

- [CI, run 40228223231](https://github.com/filippakula123/price-sentinel/actions/runs/40228223231).
- [Pierwszy ręczny monitor, run 40238568570](https://github.com/filippakula123/price-sentinel/actions/runs/40238568570).
- [Gałąź publicznego stanu](https://github.com/filippakula123/price-sentinel/tree/sentinel-data):
  seed `1c27009d1f973625acaaf6d948bee93d27052b3b`, stan po runie
  `ae1f2e5a29d191998b205f9abff7471d16060a76`.

Raporty operacyjne, kopie SQLite, snapshoty i log runu są lokalnie w ignorowanym katalogu
`data/production-verification-20261025-230305/`. Nie opublikowano wcześniejszej prywatnej
watchlisty ani lokalnych ścieżek z metadanych. Sekret GitHub wykorzystano tylko w pamięci
procesu do autoryzowanych operacji API; nie zapisano go w plikach ani wynikach.

Publiczny snapshot zawiera 0 alertów, zatem zachowanie pustego stanu nie dowodzi produkcyjnej
deduplikacji wysłanych wiadomości. Nie wymuszano dostępności ani nie generowano obserwacji.
Nie uruchomiono drugiej blokowanej kontroli Actions, nie obchodzono odmowy robots.txt.
Monitoring cen z Actions pozostaje **zablokowany**, mimo poprawnej persistencji.

## Wznowienie: rzeczywisty webhook — 25 października 2026

Użytkownik wskazał plik z webhookiem, przeniesiony następnie na jego żądanie do lokalnego
`.env`. Potwierdzono ignorowanie pliku przez Git i brak śledzenia. Odczytano wyłącznie
wartość webhooka do środowiska procesu testowego; nie zmieniano automatycznego ładowania
konfiguracji aplikacji. Sekret nie trafił do kodu, testów, dokumentacji ani publicznego snapshotu.

- Test rozpoczęty o **22:16:23 UTC (23:16:23 Europe/Warsaw)**.
- Dokładnie jedna próba `test-webhook`, bez retry; brak modyfikacji kolejki alertów/bazy.
- Discord zwrócił **HTTP 204**, komenda zakończyła się kodem 0 i `wysłane=1`.
- Włączono logowanie INFO klienta HTTP. Sprawdzono przechwycone stdout/stderr:
  pełnego webhooka ani tokena nie było w wynikach; adres był maskowany.
- Nie pobierano historii kanału Discord: przyjęcie potwierdza odpowiedź API;
  wizualne potwierdzenie wiadomości w kanale pozostaje po stronie właściciela.
- Sekret `DISCORD_WEBHOOK_URL` zapisano w GitHub Actions: HTTP 201, metadane odczytane
  poprawnie. Wartość zaszyfrowano lokalnie kluczem publicznym repozytorium (libsodium
  sealed box). Biblioteka kryptograficzna znajduje się tylko w ignorowanym katalogu
  operacyjnym; zależności aplikacji i pyproject.toml nie zostały zmienione.
- Nie wykonano dodatkowych wysyłek Discord ani dispatchu Actions. Użycie sekretu
  przez runner pozostaje niezweryfikowane z powodu blokady odczytu sklepu.
- Potwierdzono `PUBLIC_SNAPSHOT_ENABLED=false`; cron nadal nie istnieje.
- Końcowa regresja: **118 passed, 5,92 s**; Ruff, formatowanie i pip check poprawne.
- [CI dokumentacji 8aaf895](https://github.com/filippakula123/price-sentinel/actions/runs/40238895372):
  Windows i Ubuntu zakończone sukcesem.

Pozostałe blokady: x-kom robots.txt z runnera Actions (403), Media Expert i EURO (403),
produkcja prawdziwych alertów cenowych/deduplikacja przy nieznanej dostępności i sesja
interaktywnego bota. Nie generowano fikcyjnej dostępności, historii ani alertów.

## Poprawka uruchomienia w CMD

Log użytkownika ujawnił przekazywanie apostrofów jako części URL-a w `cmd.exe`.
Przykłady linków i progów używają teraz podwójnych cudzysłowów, poprawnych w CMD
i PowerShell. CLI odrzuca URL otoczony dosłownymi apostrofami z instrukcją poprawy;
walidacja domen i SSRF pozostaje bez zmian. Cztery testy obejmują `check --url` i `add`.
Sprawdzono rzeczywiste uruchomienie przez `cmd.exe /d /c` na osobnej bazie
`data/cmd-check.sqlite3`: 2026-10-25 19:34:27 UTC, status `ok`, cena 339900 groszy,
dostępność nieznana. Nie wysłano powiadomienia Discord.
