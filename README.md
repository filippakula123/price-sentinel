# Price Sentinel

Modułowy monitor cen w Pythonie 3.12: terminal, SQLite, historia i alerty Discord.
Nie zawiera strony WWW. Obserwuje konkretne linki; nie ma wyszukiwania po nazwie.
Dane lokalne są domyślnie poza Gitem.

**Stan:** zweryfikowano cenę jednej prawdziwej karty x-kom (`partial`). Media Expert i EURO
mają status **`blocked`**: HTTP 403 na kategoriach i rzeczywistych kartach produktów.
Nie potwierdzono działającego publicznego źródła ich cen. [Dowody i ograniczenia](docs/VERIFICATION.md),
[roadmapa](ROADMAP.md), [wyniki testów](docs/TESTING.md).

Weryfikacja produkcyjna 25.10.2026: dwa lokalne odczyty x-kom i odtworzenie snapshotu
poprawne; CI na Windows i Ubuntu zakończony sukcesem. Ręczny runner Actions otrzymał
HTTP 403 przy odczycie `robots.txt` x-kom i prawidłowo przerwał kontrolę. Zapis snapshotu
na GitHub działa i zachował wcześniejsze obserwacje. Monitoring w Actions wstrzymano
(`PUBLIC_SNAPSHOT_ENABLED=false`); cron nie istnieje. Rzeczywisty `test-webhook` zakończył
się HTTP 204 (jedna wiadomość, poprawne maskowanie logów). Sekret Actions skonfigurowano.
Drugi ręczny run 26.10.2026 (`notify=false`) również otrzymał 403 dla robots.txt;
zachował 2 obserwacje bez duplikatów, dodał tylko zapis nieudanej kontroli.
Użytkownik potwierdził otrzymanie wiadomości testowej Discord. Lokalnie 26.10.2026
sprawdzono też prawdziwy alert `price_below`: cena 3399 zł, próg 10 000 zł, dostępność
nieznana; pierwszy `deliver` wysłał 1 wiadomość, drugi 0. Regułę testową usunięto.
Szczegóły i granice weryfikacji: [TESTING.md](docs/TESTING.md).

## Codzienne użycie — PowerShell

Uruchamiaj polecenia z katalogu repozytorium. Wybierz jedną właściwą bazę i używaj jej
konsekwentnie; poniżej jest domyślna lokalna baza, nie baza prób produkcyjnych.
Nie uruchamiaj równolegle bota ani innej kopii monitora.

```powershell
$py = ".\.venv\Scripts\python.exe"
$db = "data/sentinel.sqlite3"
# Dodaj ofertę tylko raz. Zapisz id zwrócone przez add.
& $py -m price_sentinel --db $db add "https://www.x-kom.pl/p/1195326-konsola-playstation-sony-playstation-5-slim.html" --rule-type price_below --target "3000"
# Dla istniejącej oferty zastąp 1 jej rzeczywistym id; edit zastępuje całą regułę.
& $py -m price_sentinel --db $db edit 1 --rule-type price_below --target "2900"
& $py -m price_sentinel --db $db watchlist
```

`price_below` nie wymaga potwierdzonej dostępności. Domyślny
`available_and_price_below` nadal jej wymaga. Nie ustawiaj wysokiego progu testowego
w codziennej watchliście, jeśli nie chcesz otrzymać alertu przy najbliższym odczycie.

Przed `daily` ustaw `DISCORD_WEBHOOK_URL` w środowisku procesu. Aplikacja nie ładuje
`.env` automatycznie. Jeśli trzymasz webhook w ignorowanym `.env`, zapisz go jako
jedną linię przypisania `DISCORD_WEBHOOK_URL` (bez komentarza na końcu wartości).
Poniższy fragment wczytuje tylko tę wartość, nie wykonuje zawartości pliku i jej nie wypisuje:

```powershell
$webhookLines = @(Get-Content -LiteralPath ".env" | Where-Object { $_ -match '^\s*DISCORD_WEBHOOK_URL\s*=' })
if ($webhookLines.Count -ne 1) { throw "W .env musi być dokładnie jedno przypisanie DISCORD_WEBHOOK_URL" }
$env:DISCORD_WEBHOOK_URL = ($webhookLines[0] -split '=', 2)[1].Trim().Trim('"').Trim("'")
Remove-Variable webhookLines
& $py -m price_sentinel --db $db daily
# Sprawdź od razu kod zakończenia daily:
$LASTEXITCODE
& $py -m price_sentinel --db $db watchlist
& $py -m price_sentinel --db $db report
& $py -m price_sentinel --db $db status
# Po zakończeniu sesji:
Remove-Item Env:DISCORD_WEBHOOK_URL -ErrorAction SilentlyContinue
```

`daily` sprawdza po kolei wszystkie aktywne oferty, tworzy alerty przez istniejące
reguły i **raz** wywołuje `deliver`. Podsumowanie JSON podaje liczbę sprawdzonych ofert,
sukcesów/błędów odczytu, nowych i wysłanych alertów oraz całej oczekującej kolejki.
Brak lub niepoprawny webhook daje kod 2 **przed odczytami sklepów**. Do kontroli bez
wysyłki służy dotychczasowe `check`. Kod 1 oznacza błąd przynajmniej jednego odczytu
lub wysyłki; inne oferty nadal są sprawdzane, a kolejka obsługiwana. Kod 0 oznacza
brak błędów w tym uruchomieniu; zaległe retry mogą nadal oczekiwać na swój termin.

Jedna obsługa kolejki oznacza obecny limit 20 gotowych alertów, także zaległych;
to nie jest limit jednej wiadomości. Pauza pomija odczyt oferty, lecz nie anuluje
wcześniej utworzonego alertu. `daily` nie wysyła raportów i nie ponawia błędnej
wysyłki w tym samym uruchomieniu. Kolejne uruchomienie respektuje fingerprint,
cooldown i termin retry; nie tworzy kolejnego alertu dla niezmienionego stanu/reguły.
Awaria po przyjęciu wiadomości przez Discord, przed zapisem `sent`, nadal może dać duplikat.

`watchlist` pokazuje wszystkie oferty, także wstrzymane: nazwę, domenę sklepu, cenę,
cel, dostępność, typ reguły, datę ostatniego sukcesu i różnicę **cena − cel** w groszach.
Dodatnia różnica oznacza cenę powyżej celu, ujemna poniżej. `null` oznacza brak danych,
nie zero. Cena i dostępność pochodzą z ostatniej udanej obserwacji; `czas_ceny`
i `status_odczytu` ujawniają stary odczyt po błędzie. Czasy prezentowane są w Europe/Warsaw.

`report` bez okresu to krótkie lokalne podsumowanie: aktywne produkty/oferty, do 5 celów
o najmniejszej bezwzględnej różnicy ceny, do 5 ostatnich alertów, ostatnie zapisane błędy
adapterów (także historyczne) i ostatni sukces monitoringu. Oferty bez ceny lub celu
nie trafiają do listy najbliższych celów. Raport nie odczytuje sklepów i niczego nie wysyła.
Istniejące `report daily`, `report weekly` i ich `--notify` zachowują dotychczasowe działanie;
`report --notify` bez okresu jest błędem. `status` pozostaje szczegółową diagnostyką.

Nowe komendy zweryfikowano **offline**, syntetycznym HTML i atrapami Discord;
nie wykonano dodatkowego rzeczywistego check/daily ani wysyłki. Cron jest wyłączony,
adaptery i publiczny snapshot nie zostały zmienione.

## Pierwsze uruchomienie — Windows / PowerShell lub CMD

Zainstaluj Python 3.12. Jeśli masz launcher `py`, możesz zastąpić `python` przez `py -3.12`.
Nie trzeba aktywować venv ani zmieniać ExecutionPolicy:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m price_sentinel check --url "https://www.x-kom.pl/p/1195326-konsola-playstation-sony-playstation-5-slim.html"
```

Używaj podwójnych cudzysłowów `"..."` w obu terminalach. W CMD pojedyncze `'...'` są
przekazywane jako część adresu i powodują błąd. Dalsze przykłady ustawiania `$env:...`
dotyczą PowerShell; w CMD odpowiednikiem jest `set "NAZWA=wartość"`.

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
.\.venv\Scripts\python -m price_sentinel add "https://www.x-kom.pl/p/1195326-konsola-playstation-sony-playstation-5-slim.html" --target "3000,00" --drop "100" --percent 10 --restock
.\.venv\Scripts\python -m price_sentinel list
.\.venv\Scripts\python -m price_sentinel check 1
.\.venv\Scripts\python -m price_sentinel edit 1 --target "2900" --restock --cooldown 21600
.\.venv\Scripts\python -m price_sentinel pause 1
.\.venv\Scripts\python -m price_sentinel resume 1
.\.venv\Scripts\python -m price_sentinel status
```

`edit` zastępuje cały zestaw reguł, także typ; pominięte progi zostają wyłączone.
Domyślny typ `available_and_price_below` zachowuje obecną logikę: wymaga „dostępny”,
łączy próg/spadki/restock jako OR. Próg działa od pierwszego odczytu (cena **<=** target),
spadek względem poprzedniego poprawnego odczytu, restock wymaga wcześniejszego „niedostępny”.
Stare zapisane reguły bez pola `rule_type` zachowują ten typ i stare fingerprinty.

Jawny `price_below` wymaga tylko poprawnego odczytu ceny **<=** target, niezależnie od
dostępności (także „nieznany” i „niedostępny”). Nie potwierdza możliwości zakupu.
Wymaga `--target`; połączenie z `--drop`, `--percent` lub `--restock` jest błędem walidacji.
Cooldown i trwała deduplikacja nadal obowiązują. Zmiana dostępności przy tej samej cenie
nie tworzy kolejnego fingerprintu tego typu. Wiadomość podaje rzeczywistą dostępność.

```powershell
.\.venv\Scripts\python -m price_sentinel add "https://www.x-kom.pl/p/1195326-konsola-playstation-sony-playstation-5-slim.html" --rule-type price_below --target "3000"
# Zastąp 1 ID właściwej oferty. edit zastępuje całą regułę:
.\.venv\Scripts\python -m price_sentinel edit 1 --rule-type available_and_price_below --target "3000"
```

`--rule-type` przyjmuje wyłącznie powyższe dwa typy. W slash `/dodaj` i `/edytuj`
odpowiada mu opcja `typ_reguly`; jej rejestrację sprawdzono offline, bez sesji bota.
Nieznana dostępność nie oznacza braku towaru. Karta PS5 nie ma availability w JSON-LD:
blokuje to domyślny typ, ale nie jawny alert wyłącznie cenowy. Błąd odczytu blokuje oba typy.

`remove 1` usuwa ofertę, historię i alerty. Zmianę URL realizuj przez osobne dodanie oferty.
Zmiana nazwy/marki/EAN/MPN/wariantu pod tym samym URL daje błąd do ręcznej weryfikacji.
Nieudana kontrola zachowuje poprzednią obserwację oraz datę ostatniego sukcesu.

### Webhook Discord

W ustawieniach własnego kanału Discord: Integracje → Webhooki → Nowy webhook, wybierz kanał
i skopiuj URL (wymaga zarządzania webhookami). URL jest sekretem:

```powershell
# Wstaw własną wartość tylko lokalnie. Nie publikuj jej w zrzutach terminala.
$env:DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/ID/TOKEN'
.\.venv\Scripts\python -m price_sentinel test-webhook
.\.venv\Scripts\python -m price_sentinel check --notify
.\.venv\Scripts\python -m price_sentinel deliver
```

W CMD ustawienie zmiennej ma postać `set "DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/ID/TOKEN"`.
`test-webhook` wykonuje **dokładnie jeden POST** z polską wiadomością testową. Nie dotyka bazy,
kolejki ani reguł, nie ponawia automatycznie wysyłki. W wyniku i logach klienta HTTP
adres jest maskowany jako `https://discord.com/api/webhooks/***`; wyłączone są mentions.
Brak zmiennej, błąd sieci i odpowiedź inna niż 200/204 kończą komendę błędem.
Sprawdzono mocki HTTP, w tym 403/429 i redakcję logów. 25.10.2026 o 22:16:23 UTC
wykonano również jedną rzeczywistą próbę: Discord zwrócił HTTP 204, a pełny URL i token
nie pojawiły się w wynikach ani logach. Test pojedynczego webhooka nie jest testem
dostarczania całej kolejki alertów ani produkcyjnych komend slash.

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
| `www.x-kom.pl` | osobny XKomAdapter, JSON-LD | `partial`: cena produktu 1195326; dostępność nieznana |
| `www.mediaexpert.pl` | osobny MediaExpertAdapter, JSON-LD | `blocked`: kategoria i karta produktu HTTP 403 |
| `www.euro.com.pl` | osobny EuroAdapter, JSON-LD | `blocked`: kategoria i karta produktu HTTP 403 |

### Diagnostyka bez zapisywania ceny

```cmd
.\.venv\Scripts\python -m price_sentinel verify-store "https://www.x-kom.pl/p/1195326-konsola-playstation-sony-playstation-5-slim.html"
.\.venv\Scripts\python -m price_sentinel status
```

`verify-store <url>` sprawdza HTTPS, allowlistę, DNS, robots, redirecty oraz parser adaptera.
Wykonuje jedną próbę na URL, **bez retry**; odczyt robots i bezpieczne redirecty mogą wymagać
dodatkowych GET. Nie tworzy produktów, ofert, obserwacji, kontroli cenowych ani alertów.
Cena nie jest zapisywana nawet w diagnozie. Wynik trafia do osobnego JSON-a w
`data/diagnostics/` (albo katalogu obok wybranej bazy); opcjonalnie `--output data/diag.json`.
Parametry query w zapisanym adresie są maskowane; nie zapisujemy HTML ani cookies.
Niedozwolony adres daje `rejected` i zero połączeń sieciowych. Kod wyjścia: 0 sukces,
1 blocked/unsupported/błąd odczytu, 2 niepoprawny adres lub konfiguracja/zapis.

Diagnoza `ok` potwierdza parsowanie konkretnej odpowiedzi, nie weryfikuje automatycznie
poprawności całego sklepu. `blocked` oznacza 403/429/CAPTCHA lub odmowę robots;
`unsupported` brak adaptera albo jednoznacznych danych; `error` m.in. błąd sieci.

`status` nie pobiera stron. Pokazuje liczbę produktów i ofert, wszystkie oczekujące alerty
(także jeszcze niegotowe do ponowienia), liczbę nieudanych alertów, ostatni udany odczyt
każdego sklepu oraz osobno ostatni sukces monitoringu. Zachowuje ostatni błąd także po
następnym sukcesie. Lokalne diagnozy mogą aktualizować stan dostępu, ale nie historię cen.

Stan snapshotu: `not_created`, `restored`, `ok`, `stale` (zmieniły się dane domenowe),
`file_changed`, `file_missing` albo `file_unreadable`. Podawane są daty i lokalne ścieżki
eksportu/odtworzenia. `zapis_zdalny: not_verified` oznacza, że CLI nie potwierdza zapisu
na GitHubie. Metadane diagnostyki i lokalnych ścieżek nie trafiają do publicznego snapshotu.

Badanie 403 z 25.10.2026: robots obu sklepów dostępne; sitemap EURO wskazany w robots
został odczytany, ale jest indeksem URL-i, nie feedem cen. Media Expert w pobranym robots
nie wskazał sitemapu. JSON-LD produktu nie został odczytany przez aplikację z powodu 403.
Nie znaleziono potwierdzonego RSS cenowego ani publicznego API katalogu. Oficjalna
[integracja Media Expert](https://www.mediaexpert.pl/centrum-pomocy-dla-sprzedawcow/integracja-z-apilo)
dotyczy sprzedawców i wymaga loginu/klucza API, więc nie jest używana jako obejście.
Nagłówki pozostają jawne (`PriceSentinel/0.1`, Accept, Accept-Language); bez podszywania
się pod przeglądarkę, boty wyszukiwarek, bez prywatnych API, proxy i CAPTCHA.
Szczegóły: [badanie dostępu](docs/ACCESS_RESEARCH.md).

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

Skonfigurowano CI z lintem i testami na Windows/Ubuntu, bez sekretów i sieci w testach
(instalacja wymaga sieci). [CI commita e601c90](https://github.com/filippakula123/price-sentinel/actions/runs/40228223231)
zweryfikowano: oba joby Windows/Ubuntu i wszystkie kroki testów/lintu zakończone sukcesem.
Monitor: **tylko ręczny `workflow_dispatch`, bez cron i PR**. Wymaga
repozytoryjnej zmiennej `PUBLIC_SNAPSHOT_ENABLED=true`; nie włączono jej podczas implementacji.

W pierwszej próbie produkcyjnej opt-in włączono tylko na czas jednego ręcznego runu
z `notify=false`, następnie przywrócono `false`.
[Run monitoringu](https://github.com/filippakula123/price-sentinel/actions/runs/40238568570)
potwierdził działający restore i zapis gałęzi danych, lecz kontrola sklepu nie powiodła się:
`robots_niedostępny:http_403`. Nie oznacza to poprawnie działającego monitoringu cen w Actions.
Na jawne żądanie użytkownika wykonano [drugi run](https://github.com/filippakula123/price-sentinel/actions/runs/40370548015)
26.10.2026, również z `notify=false`: ta sama blokada, poprawna persistencja bez nowych
obserwacji. Ponownie wyłączono opt-in. Nie obchodzono ograniczeń.

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
5. Uruchom ręcznie `Manual price monitor (opt-in)`. Brak gałęzi/snapshotu przerywa run;
   nie ma cichego startu od pustej historii.
   Wysyłka Discord jest domyślnie wyłączona (`notify=false`). Włącz ją świadomie dopiero
   po lokalnym teście webhooka. Samo uruchomienie z `notify=false` sprawdza i utrwala dane.

Workflow ma concurrency bez anulowania trwającego runu. `contents: write` tylko w jobie
zapisującym jawnie włączony snapshot. Najpierw utrwala obserwacje/outbox, potem wysyła,
na końcu zapisuje stan wysyłki. Nieudany push jest błędem; nie ma force/ukrywania konfliktów.
Awaria po odtworzeniu tworzy 7-dniowy artefakt odzyskiwania **publicznego** snapshotu.
Zachowaj go, rozwiąż konflikt ręcznie i ponów. Błąd ostatniego zapisu po dostarczeniu alertu
może spowodować powtórzenie; sprawdzaj czerwone runy.

Cron został usunięty i nie będzie uruchamiany automatycznie. Raporty, jeśli przy ręcznym
uruchomieniu włączysz `notify`, używają Europe/Warsaw i deduplikacji dnia/tygodnia CET/CEST.
Sprawdzaj [koszty i limity](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
oraz [zasady harmonogramu](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
Nie zakładamy konkretnej puli bezpłatnych minut. Prywatne repo zużywa limit konta. Monitoruj czas runów,
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
`verify-store` lub `python scripts/research_access.py`. Zasady: [AGENTS.md](AGENTS.md).
