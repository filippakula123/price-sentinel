# Rzeczywiste wyniki kontroli

## Codzienne komendy — 26 października 2026, tylko offline

Regresja po dodaniu `daily`, `watchlist` i `report` bez okresu:
**153 passed, 7,88 s**. Nowe testy korzystają z FakeHTTP/syntetycznego HTML i atrap
Discord; globalna blokada socketów/DNS pozostaje aktywna. Nie uruchamiano rzeczywistego
check/daily na bazach testowych ani produkcyjnej, nie wysłano wiadomości Discord,
nie odczytywano prawdziwego webhooka. Publiczny snapshot, adaptery i cron nietknięte.

Sprawdzono:

- `daily`: wyłącznie aktywne oferty, dokładnie jedno wywołanie deliver, podsumowanie,
  ponowne uruchomienie z cooldown=0 bez drugiego alertu ani ponownej wysyłki;
  stały fingerprint/state/attempts/sent_at. Każdy udany syntetyczny odczyt dodaje
  odrębną obserwację, wstrzymana oferta nie dostaje kontroli.
- Preflight daily: brak lub niepoprawny webhook przerywa przed odczytem i zmianą
  tabel domenowych. Pusta baza nadal dostaje jeden pusty przebieg deliver.
- Błąd 403 jednej oferty nie blokuje pozostałych ani obsługi kolejki. Błąd wysyłki
  pozostawia pending z attempts=1 i retry, bez ponowienia w tym uruchomieniu.
- `watchlist`: nazwa, domena, ostatnia udana cena, cel, dostępność, typ reguły,
  ostatni sukces i różnica dodatnia/ujemna. Brak odczytu/celu daje null. Po błędzie
  stara cena zostaje z datą i błędnym statusem; pauza jest jawna. Stare reguły
  bez typu zachowują domyślny typ. Widok nie zmienia tabel.
- Skrócony `report`: pusta baza, liczba aktywnych produktów/ofert, kolejność celów,
  wykluczenie ofert wstrzymanych z celów, ostatnie alerty, błąd adaptera, daty
  i brak modyfikacji tabel. To zestawienie bieżącej bazy, bez nowych analiz cenowych.
- CLI: JSON podsumowania daily i kody 0/1 dla sukcesu/błędu odczytu; watchlist;
  `report` bez argumentu; nadal działające raporty daily/weekly. `report --notify`
  bez okresu jest odrzucany, aby skrócony raport nie wysyłał wiadomości niejawnie.

Nowe ścieżki komend **nie były uruchamiane produkcyjnie**. Wyniki rzeczywistego alertu
poniżej dotyczą wcześniejszego cyklu check/deliver, a nie komendy daily.

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
Na tym etapie nie uruchomiono drugiej kontroli Actions; późniejszą próbę na jawne
żądanie użytkownika opisano poniżej. Nie obchodzono odmowy robots.txt.
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

## Drugi ręczny run — 26 października 2026

Użytkownik potwierdził otrzymanie testowej wiadomości Discord. Przed kolejną próbą
repozytorium było czyste, branch `main`, lokalny HEAD i zdalny main zgodne:
`b89965e32d46a708da164f90d36033f26f3d04ad`. Ostatnie wcześniejsze commity:
`8aaf895` (wyniki pierwszej próby) i `e601c90` (implementacja komend i workflow).
GitHub REST zwrócił metadane sekretu `DISCORD_WEBHOOK_URL` (HTTP 200);
wartości sekretu nie pobierano ani nie wyświetlano.

Na jawne żądanie wykonano jeden dodatkowy `workflow_dispatch`, `ref=main`,
`notify=false`: [run 40370548015](https://github.com/filippakula123/price-sentinel/actions/runs/40370548015),
rozpoczęty **17:38:42 UTC / 18:38:42 Europe/Warsaw**. Zgodę na publiczny snapshot
włączono tylko na czas próby, po zakończeniu przywrócono i odczytem potwierdzono
`PUBLIC_SNAPSHOT_ENABLED=false`. Workflow nadal nie zawiera schedule/cron.

| Kontrola | Wynik drugiej próby |
|---|---|
| Wynik całego runu | **failure**, odczyt robots.txt x-kom: `robots_niedostępny:http_403` |
| Instalacja, restore, oba zapisy i push snapshotu | sukces |
| Wysyłka alertów i raportów | skipped, zgodnie z `notify=false` |
| Obserwacje przed → po | **2 → 2**, przyrost **0**, oczekiwany przy odmowie odczytu |
| Poprzednie obserwacje i kontrole | zachowane; dokładne porównanie wierszy |
| Nowe kontrole | dokładnie 1, nieudana; brak sztucznej ceny/obserwacji |
| Duplikaty obserwacji | brak według ID oraz pary `(offer_id, at)` |
| Alerty przed → po | **0 → 0**, tabele identyczne |
| Dwukrotny restore pobranego snapshotu | identyczne wszystkie tabele domenowe |
| Pełne logi runu | brak pełnego lokalnego webhooka, jego tokenu i użytego tokenu GitHub; brak wzorca pełnego webhooka Discord |

Gałąź danych przed: `ae1f2e5a29d191998b205f9abff7471d16060a76`,
po: `1fdced573142de5420516d8de7e800766d368d4a`. Snapshot pobrano przez API
z konkretnego commita gałęzi `sentinel-data`. Dowody lokalne w ignorowanym katalogu
`data/production-verification-20261025-230305/`: `second-dispatch.json`,
`second-before-snapshot.json`, `second-after-snapshot.json`, `second-result.json`
i `second-actions-40370548015.log` (kopia logów po dodatkowym maskowaniu).

Krok `Check offers` ma `continue-on-error`: jego conclusion może być `success`
mimo błędnego outcome. Końcowy krok `Surface failed shop controls` prawidłowo
oznaczył cały run jako nieudany. Nie zmieniano workflow ani adaptera.

**Granice weryfikacji:** brak wzrostu obserwacji wynika z blokady; nie potwierdzono
udanego pobrania ceny w Actions. Zachowanie pustej tabeli alertów nie dowodzi braku
cofnięcia stanów `sent`/`pending` w produkcji. To nadal potwierdzają wyłącznie testy
integracyjne offline. Przy `notify=false` sekret nie jest używany przez krok wysyłki;
sprawdzenie logów nie stanowi testu maskowania sekretu w aktywnej wysyłce Actions.
Skan obejmował znany webhook/token i credential GitHub, nie wszystkie możliwe sekrety.
Regresja po drugiej próbie: **118 passed, 6,67 s**; `ruff check src tests scripts`,
`ruff format --check src tests scripts` (25 plików) i `git diff --check` poprawne.

### Lokalna próba rzeczywistego alertu — 26 października 2026

Na jawne żądanie użytkownika wykonano próbę dla istniejącej karty x-kom PS5
1195326. Utworzono zupełnie nową bazę
`data/real-alert-20261026-174516-1b353b90/temporary.sqlite3`; nie używano domyślnej
bazy, gałęzi danych ani publicznego snapshotu. Sekret wczytano z lokalnego `.env`
wyłącznie do środowiska procesów. Nie zmieniano adapterów, dostępności ani danych
produktu ręcznie. Nie uruchamiano Actions ani cron.

| Kontrola | Rzeczywisty wynik |
|---|---|
| Reguła testowa | target 1000000 groszy = 10 000 zł, cooldown 21600 s |
| Jedno `check` | `ok`, 26.10.2026 17:45:23 UTC / 18:45:23 Europe/Warsaw |
| Cena | 339900 groszy = 3399 zł; warunek ceny spełniony |
| Dostępność | `nieznany`; wymagany warunek `dostępny` niespełniony |
| Kolejka po check | 0 alertów |
| Pierwsze `deliver` | wysłane=0, błędy=0, oczekujące=0 |
| Drugie `deliver` | wysłane=0, błędy=0, oczekujące=0 |
| Historia przed i po dostawach | ta sama 1 obserwacja i 1 udana kontrola |
| Duplikaty | brak obserwacji o powtarzającej się parze `(offer_id, at)`; tabela alertów pusta |
| fingerprint, state, attempts, sent_at | brak rekordu alertu, zatem brak wartości do weryfikacji |
| Sprzątanie | `remove 1` udane; 0 ofert i 0 subskrypcji w bazie testowej |

Diagnoza na podstawie `alerts.reasons`: funkcja natychmiast zwraca pustą listę
powodów, jeśli rzeczywista dostępność nie jest `Availability.AVAILABLE`.
Wysoki próg nie wyłącza tego warunku. Domyślne pola spadku i restock były wyłączone;
cooldown nie był przyczyną, bo baza nie zawierała wcześniejszych alertów.

**Nie wysłano rzeczywistego alertu cenowego; produkcyjna deduplikacja pozostaje
niezweryfikowana.** Drugi pusty `deliver` potwierdza tylko brak wysyłki z pustej kolejki.
Nie tworzono fingerprintu ani nie zmieniano rekordów, aby wymusić test. Nie ponawiano
check ani wysyłek. Dowód z zapisanym stanem przed i po każdym deliver oraz wynikiem
sprzątania: ignorowany lokalny `data/real-alert-20261026-174516-1b353b90/result.json`.
Usunięcie testowej oferty skasowało jej historię w tymczasowej bazie; raport zachowuje
rzeczywisty wynik wcześniejszych odczytów. Pozostałe bazy nie były używane.

### Rzeczywisty alert price_below — 26 października 2026

Po jawnej zgodzie użytkownika dodano typ `price_below`, ignorujący dostępność,
oraz nazwano dotychczasową logikę `available_and_price_below` (domyślna, także dla
starych reguł bez pola typu). Nie modyfikowano adapterów ani danych produktu.
Próg zachowuje istniejące porównanie cena <= target. Reguła wyłącznie cenowa wymaga
dodatniego target i odrzuca drop_amount/drop_percent/restock; nieznany typ jest błędem.
CLI udostępnia `--rule-type`, slash opcję `typ_reguly` (rejestracja tylko offline).

Pełna regresja: **140 passed, 6,44 s**; Ruff poprawny. Nowe testy offline obejmują
oba typy, dostępności unknown/available/unavailable, granice ceny (poniżej/równa/powyżej),
walidację, zapis przez CLI i atomowe odrzucenie błędnej edycji, błędy odczytu,
stan po dostawie, zgodność historycznych fingerprintów, snapshot/restore i deduplikację
tej samej ceny mimo zmiany dostępności. Fixture'y są syntetyczne, HTTP bez sieci.

Wykonano jeden rzeczywisty check istniejącej karty PS5 1195326 oraz dwa deliver,
wyłącznie w nowej bazie `data/price-only-alert-20261026-174944-2236b8fa/temporary.sqlite3`.
Webhook pobrano z lokalnego `.env` do środowiska procesów. Nie zmieniano bazy produkcyjnej,
publicznego snapshotu ani gałęzi danych, nie uruchamiano monitora Actions/cron.

| Kontrola | Rzeczywisty wynik |
|---|---|
| Reguła | `price_below`, target 1000000 groszy (10 000 zł), cooldown 21600 s |
| Check | `ok`, 17:49:50 UTC / 18:49:50 Europe/Warsaw, cena 339900 groszy, dostępność `nieznany` |
| Po check | 1 obserwacja, 1 alert pending, attempts=0, sent_at=null |
| Pierwszy deliver | wysłane=1, błędy=0, oczekujące=0; Discord zaakceptował wysyłkę |
| Stan po wysyłce | state=sent, attempts=1, sent_at=`2026-10-26T17:49:51.274495+00:00` |
| Drugi deliver | wysłane=0, błędy=0, oczekujące=0; tabela alertów identyczna |
| Fingerprint | `a1946a63dc587a343073aa8bf381702621cf060e0d5dbdcd96274f8956675b12`, niezmieniony przez oba deliver |
| Duplikaty | brak: dokładnie 1 alert i 1 unikatowy fingerprint; 1 obserwacja bez duplikatów `(offer_id, at)` |
| Historia | obie dostawy pozostawiły obserwacje bez zmian |
| Sprzątanie | `remove 1` udane, 0 ofert i 0 subskrypcji w bazie tymczasowej |

Raport z odczytami stanu przed i po obu deliver zapisano lokalnie w ignorowanym
`data/price-only-alert-20261026-174944-2236b8fa/result.json`. Raport zachowuje dowody
sprzed usunięcia oferty (usunięcie kaskadowo czyści jej historię i alerty w bazie testowej).
Nie zapisano sekretu. Przechwycone stdout/stderr sprawdzono na pełny webhook i token;
nie były obecne. Wiadomość podaje typ price_below i rzeczywistą nieznaną dostępność.

**Zweryfikowano lokalną rzeczywistą wysyłkę i brak ponownej dostawy rekordu sent.**
Nie pobierano historii Discord: przyjęcie wiadomości potwierdza sukces API, wizualnego
potwierdzenia tego alertu użytkownik jeszcze nie przekazał. Nie robiono drugiego live check:
deduplikację tworzenia kolejki dla tej samej ceny, zmian dostępności i restart/restore
sprawdzono offline. Nie sprawdzono awarii między przyjęciem przez Discord a zapisem sent;
gwarancja exactly-once nadal nie istnieje. Sekret na runnerze Actions pozostaje niesprawdzony.

### Wcześniejszy plan dla typu wymagającego dostępności

Test należy wykonać lokalnie, w osobnej, nowej bazie, bez zmiany publicznego snapshotu
i bez uruchamiania bota lub workflow równolegle. Użyć tylko jednego testowego produktu
z istniejącej allowlisty, dla którego adapter w rzeczywistym odczycie potwierdza
`availability=dostępny`. Wysoki próg sam nie wystarczy: aktualnie sprawdzana karta
PS5 zwraca dostępność nieznaną, więc **nie kwalifikuje się do wysyłki**. Nie zmieniać
ręcznie dostępności, obserwacji ani kolejki, aby wymusić alert.

Po wskazaniu takiego produktu i wczytaniu istniejącego webhooka z lokalnego `.env`
wyłącznie do środowiska procesu (aplikacja nie ładuje `.env` automatycznie):

```powershell
$py = ".\.venv\Scripts\python.exe"
$db = "data/alert-production-test.sqlite3"
if (Test-Path -LiteralPath $db) { throw "Użyj nowej bazy; nie nadpisuj poprzedniego testu" }
# $testUrl: rzeczywisty URL produktu z potwierdzoną dostępnością.
# $targetPln: wysoki próg w PLN, większy od rzeczywistej ceny tego produktu.
$offerId = (& $py -m price_sentinel --db $db add $testUrl --target $targetPln | ConvertFrom-Json).id
if ($LASTEXITCODE -ne 0 -or -not $offerId) { throw "Nie utworzono reguły" }
& $py -m price_sentinel --db $db check $offerId
& $py -m price_sentinel --db $db snapshot "data/alert-before-deliver.json"
# STOP: sprawdź dokładnie jeden alert pending, zero sent/failed oraz prawdziwą dostępność.
# Dopiero po spełnieniu warunków i ustaleniu, że webhook wskazuje kanał testowy:
& $py -m price_sentinel --db $db deliver
# STOP przy błędzie lub niepewnym wyniku; nie ponawiaj automatycznie.
# Oczekiwane: wysłane=1, błędy=0; potwierdzenie jednej wiadomości w Discord.
& $py -m price_sentinel --db $db snapshot "data/alert-after-first-deliver.json"
& $py -m price_sentinel --db $db deliver
# Oczekiwane: wysłane=0, błędy=0; żadnej drugiej wiadomości.
& $py -m price_sentinel --db $db snapshot "data/alert-after-second-deliver.json"
```

Porównać snapshoty: po pierwszym deliver dokładnie jeden rekord `sent`, `attempts=1`,
niepuste `sent_at`; po drugim identyczna tabela alertów i niezmieniona historia.
Potwierdza to brak ponownej dostawy wysłanego rekordu. Pełny test deduplikacji
tworzenia kolejki wymaga dodatkowego prawdziwego `check` tego samego produktu przy
tej samej cenie/regule/dostępności, bez nowego alertu, a potem `deliver` z wynikiem 0.
Jeśli stan produktu się zmieni, nie uznawać tej części za zweryfikowaną.

Po zapisaniu dowodów i zakończeniu testu usunąć testową ofertę wraz z regułą:

```powershell
& $py -m price_sentinel --db $db remove $offerId
& $py -m price_sentinel --db $db status
Remove-Item Env:DISCORD_WEBHOOK_URL -ErrorAction SilentlyContinue
```

`remove` usuwa również historię i alerty tej oferty, dlatego dowody zapisać wcześniej.
Nie odtwarzać snapshotu sprzed wysyłki do bazy używanej do dalszych dostaw: cofnęłoby
to stan `sent`. Awaria po przyjęciu przez Discord, ale przed zapisem `sent`, nadal
może spowodować duplikat — nie deklarujemy gwarancji exactly-once.

## Poprawka uruchomienia w CMD

Log użytkownika ujawnił przekazywanie apostrofów jako części URL-a w `cmd.exe`.
Przykłady linków i progów używają teraz podwójnych cudzysłowów, poprawnych w CMD
i PowerShell. CLI odrzuca URL otoczony dosłownymi apostrofami z instrukcją poprawy;
walidacja domen i SSRF pozostaje bez zmian. Cztery testy obejmują `check --url` i `add`.
Sprawdzono rzeczywiste uruchomienie przez `cmd.exe /d /c` na osobnej bazie
`data/cmd-check.sqlite3`: 2026-10-25 19:34:27 UTC, status `ok`, cena 339900 groszy,
dostępność nieznana. Nie wysłano powiadomienia Discord.
