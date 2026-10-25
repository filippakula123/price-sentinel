# Rzeczywiste wyniki kontroli

Środowisko: Windows, PowerShell, Python 3.12.10, lokalna `.venv`, 25 października 2026.
Zainstalowano projekt przez `python -m pip install -e ".[dev,discord]"`.
Nie użyto sekretów Discord ani GitHub w testach.

| Wykonana kontrola | Wynik |
|---|---|
| `.venv\Scripts\python -m pytest -q --tb=short` | **93 passed**, 4,36 s w końcowej regresji |
| `.venv\Scripts\ruff check .` | All checks passed |
| `.venv\Scripts\ruff format --check src tests scripts` | 20 files already formatted |
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
