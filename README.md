# Price Sentinel

Modułowy monitor cen w Pythonie 3.12: terminal, SQLite, historia i alerty Discord.
Nie zawiera strony WWW. Obserwuje konkretne linki; nie ma wyszukiwania po nazwie.
Dane lokalne są domyślnie poza Gitem.

**Stan:** zweryfikowano cenę jednej prawdziwej karty x-kom. Media Expert i EURO zwróciły
HTTP 403 na kategoriach; ich adaptery są niezweryfikowane. [Dowody i ograniczenia](docs/VERIFICATION.md),
[roadmapa](ROADMAP.md), [wyniki testów](docs/TESTING.md).

## Pierwsze uruchomienie — Windows / PowerShell

Zainstaluj Python 3.12. Jeśli masz launcher `py`, możesz zastąpić `python` przez `py -3.12`.
Nie trzeba aktywować venv ani zmieniać ExecutionPolicy:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m price_sentinel check --url 'https://www.x-kom.pl/p/1195326-konsola-playstation-sony-playstation-5-slim.html'
```

Komenda dodaje link, jeśli go nie ma, sprawdza i kończy proces. Nie wymaga Discorda i niczego
nie wysyła. Czytelny wynik JSON zawiera kwoty w groszach (`339900` = 3 399,00 zł).
`null` oznacza nieznaną wartość. Cena może się zmienić; błąd sklepu nie daje ceny zero.
Kody wyjścia: 0 sukces, 1 nieudana kontrola sklepu, 2 błąd konfiguracji/operacji.

Domyślna baza to `data/sentinel.sqlite3`. `--db` podawaj **przed komendą**, albo ustaw env:

```powershell
$env:PRICE_SENTINEL_DB = 'data/moje-ceny.sqlite3'
.\.venv\Scripts\python -m price_sentinel --help
```

`.env.example` opisuje konfigurację; aplikacja **nie ładuje `.env` automatycznie**.
Ustawiaj env w PowerShell/menedżerze sekretów. Sekretów nie podawaj jako argumentów CLI.

## Dwa tryby

**Okresowy:** jednorazowe `check`, ręcznie lub przez Actions. `--notify` dostarcza kolejkę
alertów incoming webhookiem. Nie uruchamia stale działającego klienta Discord.

**Interaktywny:** `bot`, osobny proces discord.py z komendami slash. Działa tylko przy
uruchomionym komputerze/serwerze. Actions nie zapewnia ciągłej dostępności komend.
Bot sprawdza produkty na żądanie, bez własnej pętli okresowej. Nie wymaga płatnego hostingu.

Oba używają tych samych modeli/usług i SQLite. Blokada OS uniemożliwia równoczesne użycie
tej samej bazy. Zatrzymaj bota przed CLI. **Nie uruchamiaj niezależnych kopii danych lokalnie
i w Actions** — nie ma synchronizacji. Przenosząc instalację zatrzymaj poprzednią, przenieś
snapshot i dopiero uruchom nową.

## Oferty i reguły

Zastąp `1` rzeczywistym id z wyniku `add` lub `list`:

```powershell
.\.venv\Scripts\python -m price_sentinel add 'https://www.x-kom.pl/p/1195326-konsola-playstation-sony-playstation-5-slim.html' --target '3000,00' --drop '100' --percent 10 --restock
.\.venv\Scripts\python -m price_sentinel list
.\.venv\Scripts\python -m price_sentinel check 1
.\.venv\Scripts\python -m price_sentinel edit 1 --target '2900' --restock --cooldown 21600
.\.venv\Scripts\python -m price_sentinel pause 1
.\.venv\Scripts\python -m price_sentinel resume 1
.\.venv\Scripts\python -m price_sentinel status
```

`edit` zastępuje cały zestaw reguł; pominięte progi zostają wyłączone. Reguły łączą się jako OR.
Próg działa od pierwszego odczytu, spadek względem poprzedniego poprawnego odczytu.
Powrót dostępności wymaga wcześniejszego „niedostępny”. Alert cenowy wymaga „dostępny”.
„Nieznany” nie wyzwala alertów i nie oznacza braku towaru. Zweryfikowana karta x-kom nie
ma availability w JSON-LD, więc jej alert cenowy obecnie nie powstanie.

`remove 1` usuwa ofertę, historię i alerty. Zmianę URL realizuj przez osobne dodanie oferty.
Zmiana nazwy/marki/EAN/MPN/wariantu pod tym samym URL daje błąd do ręcznej weryfikacji.
Nieudana kontrola zachowuje poprzednią obserwację oraz datę ostatniego sukcesu.

### Webhook Discord

W ustawieniach własnego kanału Discord: Integracje → Webhooki → Nowy webhook, wybierz kanał
i skopiuj URL (wymaga zarządzania webhookami). URL jest sekretem:

```powershell
# Wstaw własną wartość tylko lokalnie. Nie publikuj jej w zrzutach terminala.
$env:DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/ID/TOKEN'
.\.venv\Scripts\python -m price_sentinel check --notify
.\.venv\Scripts\python -m price_sentinel deliver
```

Bez webhooka `check` nadal zapisuje oczekujące alerty; wysyłka wymaga `--notify` lub `deliver`.
Jeden cel `default` jest mapowany na env, bez zapisywania identyfikatorów Discord w bazie.
Polskie wiadomości zawierają link, cenę poprzednią/obecną, różnicę, czas UTC i informację
o dostawie/warunkach. Mentions są wyłączone. Nigdy nie logujemy pełnego webhooka/tokena.

Deduplikacja jest trwała dla zestawu oferta/reguły/cena/dostępność/powód, także po restarcie.
Ten sam zestaw nie jest wysyłany ponownie. Cooldown domyślnie 6 h od ostatniej wysyłki.
Błędy: backoff do godziny, maksymalnie 5 prób w kolejnych wywołaniach, potem stan `failed`.
`retry-alerts ID_ALERTU` świadomie otwiera nieudaną pozycję. Kolejkę można obejrzeć w lokalnym
snapshocie. Discord i SQLite nie mają wspólnej transakcji: awaria po przyjęciu wiadomości,
ale przed zapisem potwierdzenia może spowodować duplikat. Nie obiecujemy exactly-once.

## Historia, porównania, wykresy, raporty

```powershell
.\.venv\Scripts\python -m price_sentinel history 1
.\.venv\Scripts\python -m price_sentinel chart 1 data/historia.png --gap-hours 36
.\.venv\Scripts\python -m price_sentinel export data/obserwacje.json
.\.venv\Scripts\python -m price_sentinel export data/obserwacje.csv --format csv
.\.venv\Scripts\python -m price_sentinel report daily
.\.venv\Scripts\python -m price_sentinel report weekly --notify
```

Historia zaczyna się przy pierwszej poprawnej kontroli. Minima 7/30/90 dni dotyczą własnych
obserwacji; mniej niż dwa odczyty w oknie daje „za mało danych”/`null`. Pokazujemy rzeczywisty
zakres i błędy. Luka czasowa domyślnie przekracza 36 h (`--gap-hours`). Wykres przerywa linię
na lukach i zaznacza je pomarańczowo. Minima nie dowodzą minimum rynkowego ani pełnego pokrycia.

Sklepowa najniższa cena z 30 dni przed obniżką ma osobne pole `store_lowest_30d`; obecnie
adaptery go nie odczytują. Nie utożsamiamy go z historią. Dawna niższa cena nie dowodzi
fałszywej promocji. Nie przewidujemy cen i nie zalecamy „kup teraz”.

Dostawa jest osobno; nieznana nie znaczy darmowa. Kody i cashback nie są odejmowane od ceny
JSON-LD. Wzmianki na stronie dają ostrzeżenie, bez wyliczania ceny warunkowej.
Niejednoznaczne `priceSpecification` jest odrzucane.

Ręczne grupowanie wymaga sprawdzenia modelu, pojemności, koloru, wersji, zestawu, sprzedawcy
i stanu. Nie ma automatycznego dopasowania podobnych nazw:

```powershell
.\.venv\Scripts\python -m price_sentinel link 1 2 --confirm-identical
# product_id z list/status, niekoniecznie id oferty:
.\.venv\Scripts\python -m price_sentinel compare 2
```

Porównanie podaje datę/status ostatnich odczytów. Łączna cena jest nieznana bez kosztu dostawy.
Raport obejmuje ruchome 24 h / 7 dni i ma datę Europe/Warsaw (CET/CEST). `--notify` wysyła
raz w lokalnym dniu / tygodniu ISO, przy pierwszym wywołaniu. Częściowa wysyłka raportu
może się powtórzyć po błędzie; brak transakcji z Discordem.

## Sklepy i transport

| Dokładny host | Adapter | Zweryfikowany zakres |
|---|---|---|
| `www.x-kom.pl` | osobny XKomAdapter, JSON-LD | cena produktu 1195326; dostępność nieznana |
| `www.mediaexpert.pl` | osobny MediaExpertAdapter, JSON-LD | **niezweryfikowany**, HTTP 403 kategorii |
| `www.euro.com.pl` | osobny EuroAdapter, JSON-LD | **niezweryfikowany**, HTTP 403 kategorii |

Wspólny parser wymaga jednego Product i jednego zwykłego Offer w PLN. Wiele ofert,
AggregateOffer, brak ceny lub cena warunkowa dają błąd. Brak zgadywanych selektorów HTML.
robots.txt jest wymagany, respektujemy wildcardy/crawl-delay, odświeżamy po godzinie.
Blokad, CAPTCHA i logowania nie obchodzimy. Robots nie zastępuje warunków serwisu;
ograniczenia regulaminu x-kom opisano w [weryfikacji](docs/VERIFICATION.md).

Tylko HTTPS, dokładny host, port 443, bez credentials/fragmentów. DNS musi zawierać wyłącznie
publiczne IP. Połączenie przypięte do sprawdzonego IP zachowuje SNI i weryfikację certyfikatu.
Każdy redirect przechodzi walidację i robots docelowego hosta. Limit 4 MB po dekompresji,
timeout 20 s, limit strumienia około 45 s, maks. 6 kroków redirectu i 3 próby sieć/429/5xx.
Co najmniej 3 s między żądaniami do domeny; długi Retry-After odkłada kontrolę.
Nowy sklep wymaga jawnej zmiany `PRICE_SENTINEL_HOSTS` **i adaptera** w `ADAPTERS`, testów
oraz weryfikacji danych i ograniczeń serwisu.

## Opcjonalny proces discord.py

W [Developer Portal](https://discord.com/developers/applications) utwórz aplikację i bota.
OAuth2: zakresy `bot` i `applications.commands`, zaproszenie na swój serwer. Nie przyznawaj
Administratora ani privileged intents. W Developer Mode Discorda skopiuj własne ID i ID serwera.

```powershell
.\.venv\Scripts\python -m pip install -e ".[discord]"
$env:DISCORD_BOT_TOKEN = 'WSTAW_LOKALNIE'
$env:DISCORD_OWNER_ID = 'TWOJE_ID'
$env:DISCORD_GUILD_ID = 'ID_SERWERA'
.\.venv\Scripts\python -m price_sentinel bot
```

Komendy: `/lista`, `/dodaj`, `/edytuj`, `/wstrzymaj`, `/usun`, `/sprawdz`, `/historia`,
`/porownaj`, `/powiaz`, `/raport`. Rejestracja na jednym serwerze; **każda** wymaga zgodności
użytkownika i serwera. Odpowiedzi ephemeral. `/sprawdz` obsługuje również kolejkę webhooka.
HTTP poza pętlą Discorda; dostęp do bazy serializowany. Po zatrzymaniu procesu komendy
nie działają. Prawdziwe połączenie Discord nie było testowane z sekretami.

## GitHub Actions i trwałe dane

CI: lint i testy na Windows/Ubuntu, bez sekretów i sieci w testach (instalacja wymaga sieci).
Monitor: tylko schedule i workflow_dispatch, **bez PR**, domyślnie wyłączony. Wymaga
repozytoryjnej zmiennej `PUBLIC_SNAPSHOT_ENABLED=true`; nie włączono jej podczas implementacji.

Runner jest ulotny. Model persistencji: osobna **publiczna gałąź `sentinel-data`** i snapshot
JSON, z którego odtwarzana jest SQLite. Zawiera produkty, oferty, reguły, historię, kontrole,
outbox/wysłane alerty i stan raportów. Cache Actions nie jest bazą.

Włączenie oznacza świadomą publikację całej watchlisty, progów i historii. Nie publikuj
prywatnych linków, tracking tokenów, danych użytkowników ani ID Discord. Snapshot nie
zawiera env, ale operator musi przejrzeć treść i historię gałęzi. Domyślnie wybierz lokalną
bazę. Nie zaimplementowano prywatnej persistencji w tym workflow.

1. Zatrzymaj inne procesy. Przygotuj wyłącznie publiczne oferty lokalnym CLI.
2. Wykonaj `python -m price_sentinel snapshot data/snapshot.json --public --ack-public-data`
   i przejrzyj plik. Flaga nie anonimizuje treści.
3. W osobnym katalogu utwórz pustą gałąź `sentinel-data` (np. nowy `git init`, commit i push
   `HEAD:sentinel-data`). W katalogu głównym gałęzi umieść tylko przejrzany `snapshot.json`.
4. Ustaw secret `DISCORD_WEBHOOK_URL`, variable `PUBLIC_SNAPSHOT_ENABLED=true` i pozwól jobowi
   zapisywać tę gałąź zgodnie z polityką repo.
5. Uruchom ręcznie `Public price monitor (opt-in)`. Brak gałęzi/snapshotu przerywa run;
   nie ma cichego startu od pustej historii.

Workflow ma concurrency bez anulowania trwającego runu. `contents: write` tylko w jobie
zapisującym jawnie włączony snapshot. Najpierw utrwala obserwacje/outbox, potem wysyła,
na końcu zapisuje stan wysyłki. Nieudany push jest błędem; nie ma force/ukrywania konfliktów.
Awaria po odtworzeniu tworzy 7-dniowy artefakt odzyskiwania **publicznego** snapshotu.
Zachowaj go, rozwiąż konflikt ręcznie i ponów. Błąd ostatniego zapisu po dostarczeniu alertu
może spowodować powtórzenie; sprawdzaj czerwone runy.

Harmonogram: minuta 17 co 6 godzin UTC. Best-effort, bez gwarancji godziny. Raporty według
Europe/Warsaw, przy pierwszym runie w lokalnym dniu/tygodniu (obsługa CET/CEST).
Sprawdzaj [koszty i limity](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
oraz [zasady harmonogramu](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
Nie zakładamy konkretnej puli bezpłatnych minut. Prywatne repo zużywa limit konta; publiczny
harmonogram może zostać wyłączony po 60 dniach bez aktywności. Monitoruj czas runów,
rozmiar historii/gałęzi, blokady sklepów i ważność webhooka. Stare dane pozostają w Git.

Backup/przenoszenie lokalne:

```powershell
.\.venv\Scripts\python -m price_sentinel snapshot data/backup.json
.\.venv\Scripts\python -m price_sentinel --db data/odtworzona.sqlite3 restore data/backup.json
```

`restore` transakcyjnie **zastępuje** wybraną bazę; najpierw wykonaj backup. Nie scala instalacji.
Nieobsługiwany schemat jest odrzucany; migracje przyszłych wersji wymagają jawnego kodu.

## Testy i rozwój

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\ruff check src tests scripts
.\.venv\Scripts\ruff format --check src tests scripts
```

Testy blokują sockety. Pokrywają ceny, warianty, SSRF, redirecty, robots, błędy, alerty,
restart, persistencję, historię, wykresy, raporty i eksport. Ręczne próby online:
`python scripts/probe_stores.py`. Zasady: [AGENTS.md](AGENTS.md).
