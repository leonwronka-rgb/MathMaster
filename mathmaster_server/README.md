# Backend MathMaster Quiz Battle

Osobny serwer FastAPI dla prawdziwych rozgrywek online. Konta, profile i
wyniki multiplayer są przechowywane w PostgreSQL. Serwer nie importuje ani nie
zmienia lokalnych kont SQLite aplikacji desktopowej. Opcjonalne powiązanie
profilu używa losowego, niejawnego identyfikatora, a nie lokalnego ID konta.

## Uruchomienie lokalne — Windows PowerShell

Polecenia uruchom z katalogu głównego repozytorium:

```powershell
py -3.13 -m venv .venv-server
.\.venv-server\Scripts\python.exe -m pip install -r mathmaster_server\requirements.txt
Copy-Item mathmaster_server\.env.example mathmaster_server\.env
```

W pliku `mathmaster_server\.env` ustaw `POSTGRES_PASSWORD`,
`MATHMASTER_SECRET_KEY` (losowe min. 32 bajty) oraz prywatny klucz Ed25519.
Poniższe polecenia generują nowe, niezależne sekrety; zapisz je w `.env` i nie
udostępniaj ani nie commituj pliku:

```powershell
.\.venv-server\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
.\.venv-server\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
.\.venv-server\Scripts\python.exe -c "import base64; from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; from cryptography.hazmat.primitives import serialization; k=Ed25519PrivateKey.generate(); print(base64.b64encode(k.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())).decode())"
```

Po uruchomieniu lokalnego PostgreSQL startuj API:

```powershell
.\.venv-server\Scripts\python.exe -m uvicorn mathmaster_server.main:app --env-file mathmaster_server\.env --host 127.0.0.1 --port 8000
```

Można uruchomić PostgreSQL i API w Docker Compose (w `.env` musi być również
ustawione `POSTGRES_PASSWORD`):

```powershell
docker compose --env-file mathmaster_server\.env -f mathmaster_server\docker-compose.yml up --build
```

Compose udostępnia API wyłącznie na localhost. Wdrożenie internetowe wymaga
zarządzanej bazy PostgreSQL oraz reverse proxy z TLS i obsługą WebSocket
upgrade. Uruchamiaj jedną instancję/worker: matchmaking, pokoje, aktywne
połączenia i limity są w pamięci procesu, a nie współdzielone między workerami.

Dokumentacja OpenAPI: `http://127.0.0.1:8000/docs`; kontrola zdrowia:
`/health`; WebSocket: `/v1/ws`. Do aplikacji desktopowej ustaw
`wss://<host>/v1/ws`, token `access_token` uzyskany w endpointzie logowania
oraz klucz `result_public_key` z `GET /v1/metadata` jako
`MATHMASTER_QUIZ_BATTLE_PUBLIC_KEY`.

## REST API

- `POST /v1/auth/register` — rejestracja online i wydanie tokenu bearer.
- `POST /v1/auth/login` — logowanie i wydanie tokenu bearer.
- `GET /v1/players/me` — profil i statystyki multiplayer.
- `GET /v1/players/me/history?limit=50` — historia meczów zalogowanego gracza.
- `PUT` / `DELETE /v1/players/me/local-profile` — opcjonalne przypięcie lub
  odpięcie niejawnego identyfikatora lokalnego profilu.
- `GET /v1/players/me/achievements` — osiągnięcia online z rzeczywistymi
  warunkami odblokowania.
- `GET /v1/leaderboard?sort_by=rating|wins|win_rate&limit=100` — ranking globalny.
- `GET /v1/metadata` — wersja protokołu i publiczny klucz podpisu wyników.

Hasła są haszowane Argon2id, tokeny JWT mają skonfigurowany sekret HS256 i
termin ważności, a nicki są unikalne bez rozróżniania wielkości liter.
Rejestracja/logowanie oraz połączenia i wiadomości WebSocket mają limity
żądań na proces. Wartości `.env` muszą być zarządzane jako sekrety hostingu.
Nie wystawiaj PostgreSQL ani HTTP bez zabezpieczeń sieciowych i TLS.

## WebSocket i rozgrywka

Pierwsza wiadomość po połączeniu:

```json
{"type":"authenticate","token":"<token z logowania online>","display_name":"nazwa ignorowana; używany jest nick konta","protocol_version":1}
```

Po `authenticated` serwer używa zarejestrowanego nicku, nie nazwy podanej
przez klienta. Obsługiwane są wiadomości:

- `matchmaking_join` (`settings`, `friends_only`), `matchmaking_cancel`
- `room_create` (`settings`, `friends_only`), `room_join` (`room_code`),
  `room_start` (`room_code`)
- `answer_submit` (`question_id`, `answer`), `match_leave`, `rematch_request`
- `resume` z jednym z `queue_id`, `room_code`, `match_id`
- `leaderboard_request` (`sort_by`, `limit`)

Ustawienia obejmują `mode` (`race`/`survival`), czas 60/120/180 s lub 0 w
trybie survival, 2–8 graczy, kategorię, identyfikatory tematów i poziom 1–5.
Matchmaking dobiera wyłącznie podłączonych użytkowników z zgodnymi
ustawieniami i zbliżonym rankingiem; przedział rankingu rozszerza się wraz z
czasem oczekiwania. Nie ma botów. Pokój rozpoczyna grę po zebraniu wymaganej
liczby podłączonych graczy albo na żądanie właściciela, gdy dołączy co najmniej
dwie osoby.

Generator obsługuje wszystkie identyfikatory tematów aktualnej aplikacji:
arytmetykę, ułamki, procenty, algebrę, równania i nierówności, geometrię
(w tym równoległoboki, romby i trapezy), potęgi, funkcje, trygonometrię,
logarytmy, kombinatorykę, prawdopodobieństwo, statystykę, granice, pochodne
i całki. Serwer sprawdza zgodność kategorii z tematem. Odpowiedź pozostaje
na serwerze do czasu odpowiedzi wszystkich aktywnych graczy albo upływu czasu
pytania. Weryfikowane są wyłącznie ograniczone odpowiedzi liczbowe/ułamki —
serwer nie wykonuje wyrażeń ani kodu od klienta. Punkty, pomyłki, eliminacje
oraz limit czasu kontroluje serwer.

Utrata połączenia zachowuje miejsce przez skonfigurowany czas na ponowne
połączenie; można wznowić kolejkę, oczekujący pokój lub mecz. Pojedynek nie
zacznie się bez co najmniej dwóch rzeczywistych, podłączonych graczy. Kolejność
końcowa jest ustalana serwerowo: aktywni przed wyeliminowanymi, następnie
punkty, poprawne odpowiedzi, mniej pomyłek, czas odpowiedzi i stabilny
identyfikator gracza. Ostatnie kryterium rozstrzyga pełny remis i zapewnia
unikalne miejsca wymagane przez weryfikator klienta.

Każdy uczestnik otrzymuje osobny podpisany komunikat `match_finished`; pole
`player_id` wskazuje odbiorcę, `winner_player_id` zwycięzcę, a `standings`
pełną tabelę. Wynik i statystyki są zapisywane przed wysłaniem podpisu.
Podpis Ed25519 obejmuje kanoniczny JSON UTF-8 (`sort_keys=True`,
`separators=(",", ":")`, `ensure_ascii=False`); `signed_payload` oraz
`signature` są kodowane base64. Serwer publikuje wyłącznie klucz publiczny.

## Dane i wdrożenie

Przy starcie SQLAlchemy tworzy brakujące tabele; serwer nie usuwa tabel ani
danych. To wystarcza do pierwszego uruchomienia i dodawania tabel. Zmiany
istniejących kolumn wymagają jawnej migracji bazy przed aktualizacją. Przed
wdrożeniem wykonaj kopię zapasową, np.:

```powershell
pg_dump --format=custom --file=mathmaster-before-upgrade.dump "$env:DATABASE_URL"
```

Nie uruchamiaj wielu workerów/replik bez przeniesienia matchmakingu, stanu
pokojów, rozsyłania WebSocket i limitów do współdzielonej usługi (np. Redis).
Do publicznego hostingu skonfiguruj reverse proxy TLS, limity połączeń,
monitoring i kopie zapasowe. W repozytorium nie ma skonfigurowanej usługi
hostingowej — samo wdrożenie nadal wymaga operatora i sekretów.

## Testy

```powershell
.\.venv-server\Scripts\python.exe -m unittest discover -s mathmaster_server\tests -v
```

Test wieloosobowy zakłada dwa niezależne konta, łączy je przez WebSocket,
sprawdza punktację serwera i odrzucenie powtórzonej odpowiedzi, weryfikuje
podpisy Ed25519 przypisane do każdego odbiorcy oraz zapis historii.
