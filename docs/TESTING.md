# Rzeczywiste wyniki kontroli

Środowisko: Windows, PowerShell, Python 3.12.10, lokalna `.venv`, 25 października 2026.
Zainstalowano projekt przez `python -m pip install -e ".[dev,discord]"`.
Nie użyto sekretów Discord ani GitHub w testach.

| Wykonana kontrola | Wynik |
|---|---|
| `.venv\Scripts\python -m pytest -q --tb=short` | **118 passed**, 6,34 s po etapie diagnostyki i snapshotów |
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
Media Expert i EURO pozostają niezweryfikowane po HTTP 403. Rzeczywista wysyłka webhooka,
sesja bota, Ubuntu CI oraz monitor i push na GitHub wymagają odrębnego sprawdzenia.
Nie uruchomiono harmonogramu i nie opublikowano snapshotu.

## Etap diagnostyki, statusu i ręcznego workflow

- `test-webhook`: mock HTTP potwierdza dokładnie jeden POST, polską wiadomość i wyłączone
  mentions. Sprawdzono 204, 403, 429 oraz błąd sieci, bez retry. Webhook jest maskowany
  w wynikach, logach httpx/httpcore i standardowym tracebacku błędu. Nie wysyłano
  wiadomości z prawdziwym webhookiem; produkcyjne potwierdzenie nadal otwarte.
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
  Usunięto schedule/cron. Przejrzano konfigurację; nie wykonano runu GitHub Actions,
  nie potwierdzono uprawnień runnera ani zdalnego zapisu snapshotu. Lokalny test Git
  nadal sprawdza push i odrzucenie konfliktu w bare remote.

Wyniki dotyczą lokalnego Windows/Python 3.12.10. Ubuntu i prawdziwa sesja Discord
pozostają niesprawdzone. Nie dodano nowych sklepów i nie obchodzono blokad.

## Poprawka uruchomienia w CMD

Log użytkownika ujawnił przekazywanie apostrofów jako części URL-a w `cmd.exe`.
Przykłady linków i progów używają teraz podwójnych cudzysłowów, poprawnych w CMD
i PowerShell. CLI odrzuca URL otoczony dosłownymi apostrofami z instrukcją poprawy;
walidacja domen i SSRF pozostaje bez zmian. Cztery testy obejmują `check --url` i `add`.
Sprawdzono rzeczywiste uruchomienie przez `cmd.exe /d /c` na osobnej bazie
`data/cmd-check.sqlite3`: 2026-10-25 19:34:27 UTC, status `ok`, cena 339900 groszy,
dostępność nieznana. Nie wysłano powiadomienia Discord.
