# MathMaster

Podstawowa architektura desktopowej aplikacji do nauki matematyki. Projekt
korzysta z CustomTkinter, SQLite, Matplotlib i SymPy. Zawiera lokalne konta,
interfejs desktopowy oraz silnik matematyczny z generatorami zadań.

## Wymagania

- Python 3.13 lub nowszy
- Windows, macOS lub Linux z obsługą Tk

## Instalacja i uruchomienie

W katalogu `MathMaster` utwórz i aktywuj środowisko wirtualne, a następnie
zainstaluj zależności:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

W systemach macOS/Linux aktywacja środowiska wygląda tak:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

## Testy

Testy jednostkowe używają standardowego `unittest`:

```powershell
python -m unittest discover -s tests -v
```

## Konfiguracja

Aplikacja zapisuje bazę SQLite, logi i kopie zapasowe poza zasobami programu:
do `%APPDATA%\MathMaster` na Windows, `~/Library/Application Support/MathMaster`
na macOS lub `$XDG_DATA_HOME/MathMaster` na Linux. Aktualizacja programu nie usuwa tego
katalogu. Przy pierwszym uruchomieniu EXE aplikacja kopiuje znalezioną bazę ze
znanej lokalizacji starszej wersji, bez usuwania oryginału i bez nadpisywania
istniejącej bazy w katalogu danych. Zmienne środowiskowe:

- `MATHMASTER_DATA_DIR` — alternatywny katalog danych
- `MATHMASTER_APPEARANCE` — motyw CustomTkinter (`system`, `light` lub `dark`)
- `MATHMASTER_QUIZ_BATTLE_URL` i `MATHMASTER_QUIZ_BATTLE_TOKEN` — adres
  WebSocket i token gracza dla opcjonalnego serwera Quiz Battle
- `MATHMASTER_QUIZ_BATTLE_PUBLIC_KEY` — zaufany klucz Ed25519 do weryfikacji
  wyników serwera

## Kopie zapasowe

W Ustawieniach → Profil użytkownika można utworzyć kopię SQLite lub przywrócić
ją z pliku. Kopie są zapisywane do `backups` wewnątrz katalogu danych. Przed
przywróceniem aplikacja wykonuje dodatkową kopię aktualnej bazy; po udanym
przywróceniu użytkownik zostaje wylogowany. Migracja starszego schematu tworzy
również kopię przed zastosowaniem zmian.

## Ustawienia użytkownika

Po zalogowaniu ekran **Ustawienia** zawiera kategorie wyglądu, personalizacji,
nauki, przypomnień, dźwięku i animacji, konta oraz danych. Motyw jasny,
ciemny, systemowy i niestandardowy może być zastosowany bez restartu.
Ustawienia są przechowywane oddzielnie dla każdego konta w SQLite i migrowane
przy zachowaniu istniejących danych. Ustawienia nauki wpływają na wartości
początkowe sesji, podpowiedzi, widoczność rozwiązań, adaptację i limit czasu.
Przypomnienia są pokazywane lokalnie, gdy aplikacja działa.

Eksport JSON w ustawieniach zawiera dane zalogowanego użytkownika bez skrótu
hasła. Kopia SQLite obejmuje całą lokalną bazę; przywracanie wymaga
potwierdzenia, tworzy kopię bezpieczeństwa i wylogowuje użytkownika. Import
plików JSON jako kopii konta nie jest dostępny — przywracanie jest obsługiwane
wyłącznie dla zweryfikowanych kopii SQLite, aby uniknąć częściowego lub
niebezpiecznego nadpisania relacyjnych danych.

## Budowanie pliku EXE (Windows)

Szczegółowe polecenia i warianty onefile/onedir opisuje [BUILD.md](BUILD.md).
Zainstaluj zależności aplikacji i PyInstaller w aktywnym środowisku:

```powershell
python -m pip install -r requirements-build.txt
build.bat
```

Wersja domyślna trafia do `dist\MathMaster\MathMaster.exe`; pojedynczy plik
można zbudować przez `build.bat onefile`. Budowanie EXE jest platformowe —
należy budować osobno na Windows. Dane użytkownika pozostają poza paczką.

## Konta lokalne

Utwórz konto z ekranu logowania. Każdy użytkownik ma własny profil i postępy;
hasła są przechowywane jako hashe bcrypt. Funkcja „Zapamiętaj nazwę konta”
zapisuje wyłącznie nazwę użytkownika, nigdy hasła. Profil (Ustawienia) pozwala
zmienić nazwę i hasło albo usunąć konto wraz z przypisanymi danymi.
Konta nie wymagają połączenia z internetem.

## Silnik matematyczny

`MathEngine` udostępnia generowanie zadań dla tematów z `TOPIC_CATEGORIES` na
pięciu poziomach trudności, sprawdzanie odpowiedzi, upraszczanie i rozwiązywanie
równań, pochodne, całki, granice oraz próbki do wykresów. Generator można
ustawić powtarzalnym ziarnem losowania do testów:

Poziomy w interfejsie: szkoła podstawowa (klasy 4–6), szkoła podstawowa
(klasy 7–8), liceum/CKU (zakres podstawowy), szkoła średnia (zakres rozszerzony)
oraz poziom akademicki.

```python
import random

from mathematics import MathEngine, Topic

engine = MathEngine(random.Random(42))
exercise = engine.generate(Topic.LINEAR_EQUATION, difficulty=2)
print(exercise.prompt)
print(exercise.solution)
print(engine.check_answer(exercise, exercise.answer_text))
```

Parser odpowiedzi obsługuje działania, ułamki, liczby dziesiętne, potęgi,
pierwiastki, symbole, funkcje i zbiory rozwiązań. Wielkość liter w symbolach
`x` i `pi` oraz nazwach funkcji nie ma znaczenia. Nie wykonuje kodu Pythona.
Generatory losują różne konstrukcje zadań, w tym zadania tekstowe i warianty
o innych danych lub sposobie rozwiązania. Testy generatorów pokrywają każdy
temat na wszystkich pięciu poziomach i sprawdzają różnorodność treści.

## Tematy i wymagania programowe

Katalog tematów i listy efektów uczenia się są dostępne w
`mathematics/topics.py` jako `TOPIC_DATA` oraz `TOPIC_REQUIREMENTS`. Każdy temat
zawiera wymagania w postaci list, a ekran nauki wyświetla je po wybraniu
tematu. Zakres obejmuje m.in. statystykę, prawdopodobieństwo, kombinatorykę,
ciągi, nierówności liniowe oraz geometrię analityczną. Pola i obwody obejmują
prostokąty, kwadraty, trójkąty, równoległoboki, romby, trapezy i koła; objętości
rozszerzono o stożki i kule, a osobny temat obejmuje pola powierzchni brył.

Rozbudowana biblioteka znajduje się w `mathematics/topic_library.py`:
`LIBRARY_DIVISIONS` buduje hierarchię dział → poddział → temat → podtematy.
Każdy temat ma stabilny identyfikator, opis, poziom, teorię i przykłady.
`TopicLibraryService` wyszukuje oraz filtruje katalog, zapisuje status
opanowania per użytkownik i generuje ćwiczenia przez zweryfikowany silnik.
Ekran „Biblioteka” pozwala przeglądać i dodawać własne tematy bez modyfikacji
kodowego katalogu; nowy temat wskazuje typ istniejącego generatora, dzięki
czemu ćwiczenia trafiają do dotychczasowej historii i statystyk.

Wymagania są mapą treści do ćwiczeń, nie zastępują zatwierdzonego programu
nauczania ani pełnej podstawy prawnej. Odwołują się do podstawy programowej
publikowanej w [Dzienniku Ustaw](https://eli.gov.pl/eli/DU/2026/947/ogl/pol),
materiałów [Zintegrowanej Platformy Edukacyjnej dla szkoły podstawowej](https://zpe.gov.pl/podstawa-programowa/szkola-podstawowa/matematyka)
i [informatorów maturalnych CKE](https://cke.gov.pl/egzamin-maturalny/informatory/).
CKU nie ma odrębnego zestawu tematów matematycznych: liceum dla dorosłych
realizuje zakres podstawowy szkoły ponadpodstawowej, z organizacją dostosowaną
do kształcenia dorosłych.

## Wersjonowana baza edukacyjna

Pierwsze uruchomienie inicjalizuje współdzielony katalog SQLite z wersjonowanych
paczek JSON w `data/mathematics/` i `data/exams/`. Opracowany etap obejmuje
osiem tematów, 288 odtwarzalnych zadań oraz trzy egzaminy startowe; manifest
`data/manifests/content_manifest.json` wymienia pozostałe działy jako planowane,
więc katalog nie jest oznaczony jako kompletny. Zadania są sprawdzane przez
SymPy i zapisują ziarno oraz parametry generatora. Postępy użytkowników są
przechowywane osobno, a inicjalizacja aktualizuje katalog bez kasowania
historii nauki.

`EducationalContentService` waliduje, importuje i eksportuje paczki JSON
oraz udostępnia zadania i egzaminy istniejącym modułom nauki i egzaminów.
Import odrzuca konflikty identyfikatorów, o ile wywołujący jawnie nie zezwoli
na zastąpienie. Przy budowaniu EXE pliki `data/` są dołączane do aplikacji.

## Moduł nauki

Po zalogowaniu otwórz „Nauka” lub „Ćwiczenia”, wybierz kategorię, temat,
poziom i liczbę zadań. Sesja pokazuje wynik, licznik poprawnych i błędnych
odpowiedzi, postęp oraz rozwiązanie po sprawdzeniu odpowiedzi. Można ją
przerwać i zobaczyć podsumowanie; każde sprawdzone zadanie trafia do historii
z przypisaniem do aktualnie zalogowanego użytkownika.

Po trzech poprawnych lub błędnych odpowiedziach z rzędu aplikacja może
zaproponować zmianę poziomu. Poziom zmieni się wyłącznie po wyraźnej zgodzie
użytkownika.

## Asystent matematyczny

Lokalny asystent przyjmuje równanie liniowe z jedną niewiadomą `x`, pokazuje
przekształcenia krok po kroku, wyjaśnia zasadę wykonywania tych samych działań
po obu stronach, wskazuje typowe błędy i sprawdza wynik przez podstawienie
w SymPy. Można przechodzić między krokami albo wyświetlić całe rozwiązanie.
Inne typy zadań są jawnie oznaczane jako nieobsługiwane — asystent nie generuje
dla nich domyślonych ani niezweryfikowanych rozwiązań.

## Egzaminy

Ekran „Egzaminy” tworzy losowy zestaw zadań z wybranej kategorii matematyki,
poziomu i liczby zadań. Odliczanie korzysta z zegara monotonicznego, więc
zmiany zegara systemowego nie wydłużają ani nie skracają egzaminu; po upływie
limitu egzamin jest automatycznie kończony. Można nawigować między pytaniami,
zapisać odpowiedzi i oznaczyć pytanie do powrotu. Przy zakończeniu wszystkie
wypełnione odpowiedzi są sprawdzane, a puste nie otrzymują punktów.

Wyniki, ustawienia egzaminu i szczegółowe odpowiedzi są zapisywane
transakcyjnie w SQLite dla konta użytkownika. Skala progów ocen 2–6 jest
konfigurowalna w formularzu; podsumowanie pokazuje także zmianę względem
poprzedniego egzaminu z tej samej kategorii.

## Statystyki

Ekran „Statystyki” agreguje wyłącznie historię ćwiczeń aktualnie zalogowanego
konta z tabeli `exercise_history`: wyniki, skuteczność, tematy i błędne
odpowiedzi. Pokazuje dzienny i tygodniowy wolumen, skuteczność kategorii,
zmiany trudności, historię oraz powtarzające się błędy z przyciskiem
przejścia do ćwiczeń polecanego tematu. Czas nauki jest sumą czasu zapisanego
przy sprawdzonych zadaniach; przerwy między zadaniami nie są doliczane.
Wykresy korzystają z Matplotlib i dopasowują się do ciemnego motywu.

## Grywalizacja i ranking

Poprawne zadania przyznają 5 XP (poziomy trudności 1–2), 10 XP (poziom 3)
lub 20 XP (poziomy 4–5). Pierwsze ukończenie danego tematu daje 50 XP,
a pierwsze zdanie każdego egzaminu o danej nazwie — 100 XP. Progi poziomów
rosną według wzoru `50 × poziom × (poziom − 1)` (poziom 2: 100 XP,
poziom 3: 300 XP). Ekran „Osiągnięcia” pokazuje pasek poziomu i odznaki,
a „Ranking” prezentuje wyłącznie użytkowników lokalnej bazy SQLite.
Nagrody mają unikatowe klucze w rejestrze XP i są przyznawane transakcyjnie,
więc ponowne zapisanie tego samego wyniku nie duplikuje punktów.

Galeria osiągnięć pokazuje warunki, postęp, kategorię, rzadkość i historię
odblokowań; pozwala filtrować wpisy oraz wyposażyć zdobyte odznaki i ramki
awataru. Odblokowanie jest idempotentne i nagradza konto tylko raz. Kryteria
opierają się na zapisanych zadaniach, ukończonych tematach, wynikach egzaminów,
powtórkach fiszek i opanowaniu fiszek. Testy fiszek zapisują oddzielnie
sprawdzoną odpowiedź, identyfikator testu i zestaw, więc samoocena „Umiem” nie
może zaliczyć osiągnięcia za bezbłędny test zestawu.

Osiągnięcia Quiz Battle są domyślnie niedostępne i wymagają wyniku podpisanego
kluczem Ed25519 zaufanego serwera. Opcjonalnie ustaw
`MATHMASTER_QUIZ_BATTLE_PUBLIC_KEY` na base64 surowego 32-bajtowego klucza
publicznego. Integracja przyjmuje wyłącznie kanoniczny JSON podpisany
Ed25519, weryfikuje identyfikator wyniku i odrzuca zmianę payloadu oraz
powtórne użycie identyfikatora; nie ufa lokalnym deklaracjom zwycięstwa.
Wymagana biblioteka `cryptography` jest instalowana razem z
`requirements.txt`. Osobny serwer FastAPI znajduje się w katalogu
[`mathmaster_server/`](./mathmaster_server/README.md); aplikacja desktopowa nie
uruchamia go automatycznie.

## Quiz Battle — multiplayer online

Ekran „Quiz Battle” obsługuje szybkie dobieranie graczy, prywatne pokoje
znajomych i dołączanie kodem. Można wybrać wyścig na 60/120/180 sekund albo
tryb do trzech pomyłek, 2–8 graczy, dział, tematy i poziom. Pytania, timer,
odpowiedzi, statusy graczy, wyniki i ranking pochodzą z serwera. Aplikacja nie
tworzy botów ani lokalnych wyników. Historia i statystyki obejmują wyłącznie
zweryfikowane mecze danego lokalnego konta.

Do gry potrzebny jest działający serwer zgodny z protokołem Quiz Battle,
serwerowy token gracza oraz jego klucz podpisujący. Ustaw
`MATHMASTER_QUIZ_BATTLE_URL` na adres `wss://...`,
`MATHMASTER_QUIZ_BATTLE_TOKEN` na token wydany przez usługę oraz
`MATHMASTER_QUIZ_BATTLE_PUBLIC_KEY` na base64 surowego 32-bajtowego klucza
Ed25519. Ekran pozwala też wpisać adres i token podczas pracy. Zdalne `ws://`
jest odrzucane (dozwolone wyłącznie dla localhost); token nie jest zapisywany
w bazie.

Klient używa WebSocket JSON (protokół `protocol_version: 1`): wysyła
`authenticate`, `matchmaking_join`, `room_create`, `room_join`,
`answer_submit`, `leaderboard_request`, `resume`, `match_leave` i
`rematch_request`; serwer wysyła m.in. `authenticated`, `waiting`,
`room_created`, `match_started`, `question`, `answer_result`,
`players_updated`, `match_status`, `leaderboard` oraz `match_finished`.
Serwer powinien uwierzytelnić token, dobierać wyłącznie ludzi, autorytatywnie
sprawdzać odpowiedzi i zasady remisu oraz przesyłać podpisany Ed25519 wynik
meczu. Podpis obejmuje kanoniczny JSON UTF-8 z identyfikatorem serwera gracza,
zwycięzcą, trybem, trudnością, czasem i tabelą 2–8 uczestników. Klient
weryfikuje tożsamość bieżącego gracza i podpis przed zapisem, XP lub
osiągnięciami; powtórne użycie identyfikatora meczu nie przyznaje nagród drugi
raz. Reconnect próbuje wznowić autoryzowaną sesję. Bez skonfigurowanego
kompatybilnego serwera/tokena ekran pokazuje status konfiguracji, a nie
symulowanych przeciwników.

Klient wysyła wybrane tematy jako stabilne identyfikatory `Topic` i poziom
1–5; serwer mapuje poziomy 1–2 na `easy`, 3 na `medium`, 4 na `hard`, a 5 na
`expert` w podpisanym wyniku. Wiadomość `waiting` może zawierać `queue_id`,
a `match_started` — `match_id`, `mode`, `question` i `players`. Pytanie ma
`question_id`, `prompt`, `question_number`, `question_count` i
`remaining_seconds`; aktualizacje graczy przekazują listę `players` z
`display_name`, `status`, `points` i `mistakes`. Końcowa tabela zawiera
`player_id`, `display_name`, `points`, `correct_answers`, `mistakes`,
`eliminated` i `place`.

Podpisany payload `match_finished` ma dokładnie następujący kształt (podpis
jest Ed25519 nad `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`;
`signed_payload` i `signature` w wiadomości zewnętrznej są base64):

```json
{
  "battle_id": "server-generated-id",
  "player_id": "authenticated-server-player-id",
  "winner_player_id": "authenticated-server-player-id",
  "mode": "race",
  "difficulty": "medium",
  "completed_at": "2026-11-12T14:00:00+00:00",
  "duration_seconds": 60,
  "room_code": "",
  "standings": [
    {
      "player_id": "authenticated-server-player-id",
      "display_name": "Ala",
      "points": 100,
      "correct_answers": 4,
      "mistakes": 0,
      "eliminated": false,
      "place": 1
    },
    {
      "player_id": "another-authenticated-server-player-id",
      "display_name": "Olek",
      "points": 80,
      "correct_answers": 3,
      "mistakes": 1,
      "eliminated": false,
      "place": 2
    }
  ]
}
```

Wyniki muszą zawierać kompletne, unikatowe miejsca od 1 do liczby graczy;
`winner_player_id` musi należeć do miejsca 1, a bieżący gracz musi występować
w tabeli. Dla uzgodnionego sposobu naliczania nagród aplikacja daje
10 XP za udział, 5 XP za każdą poprawną odpowiedź i 50 XP za zwycięstwo
(maksymalnie 300 XP na mecz). Serwer pozostaje autorytatywny dla punktów,
eliminacji i zwycięzcy; klient nie wysyła poprawnych odpowiedzi ani lokalnych
wyników.

Repozytorium zawiera klienta desktopowego i niezależny backend
[`mathmaster_server/`](./mathmaster_server/README.md). Backend należy osobno
uruchomić i wdrożyć; po rejestracji online użytkownik łączy się tokenem.
Dopóki adres serwera i konfiguracja klucza publicznego nie są ustawione w
aplikacji, rzeczywisty multiplayer pozostaje niedostępny.

## Własne zadania i zestawy JSON

Po zalogowaniu otwórz „Moje zadania”, aby tworzyć, edytować i usuwać zadania
oraz własne zestawy. Zadanie zawiera nazwę, treść, odpowiedź, wyjaśnienie,
kategorię, temat, poziom, XP, opcjonalne podpowiedzi i odpowiedzi wyboru.
Generator ćwiczeń miesza zadania użytkownika z zadaniami wbudowanymi i pokazuje
pochodzenie każdego ćwiczenia. Punkty XP własnego zadania są przyznawane tylko
raz za poprawne rozwiązanie tego samego zadania.

Import przyjmuje JSON UTF-8 w wersji 1, z wymaganymi polami `id`, `question`,
`answer`, `difficulty` i `explanation`. Zestaw ma `name`, `category` i listę
`tasks`; opcjonalnie można podać `topic`, `name`, `xp_points`, `hint`/`hints`
i `choices`. Po walidacji aplikacja pokazuje podgląd; błędne rekordy i
duplikaty są pomijane, a każde zadanie można odznaczyć przed importem. Import
nie nadpisuje istniejących danych. Eksport obsługuje wszystkie własne zadania,
wybraną kategorię lub zestaw, zachowując polskie znaki.

Pobieranie przyjmuje wyłącznie HTTPS na publicznym porcie 443; DNS i każdy
adres po przekierowaniu są sprawdzane, a połączenie TLS jest przypięte do
zweryfikowanego publicznego IP. Adresy lokalne i prywatne, nieobsługiwane typy
odpowiedzi i pliki większe niż 5 MB są odrzucane. Dla nieznanych hostów ekran
wyświetla ostrzeżenie. Pobierane dane są dekodowane wyłącznie jako tekst JSON;
żaden kod ani skrypt nie jest wykonywany.

## Fiszki

Ekran „Fiszki” obsługuje osobiste zestawy i karty: tworzenie, edycję, usuwanie,
wyszukiwanie, sortowanie, ulubione oraz import i eksport JSON. Można tworzyć
fiszki ręcznie albo wygenerować je z wybranego tematu biblioteki. Tryb nauki
pokazuje odpowiedź po odwróceniu karty; tryb testowy pozwala wpisać odpowiedź
przed jej ujawnieniem. Oceny „Nie znam”, „Trudne”, „Umiem” i „Łatwe” zapisują
historię i wyznaczają termin kolejnej powtórki. Trudne karty wracają szybciej,
a opanowane mają stopniowo wydłużane odstępy. Ekran pokazuje dzienny cel,
postęp, skuteczność, serię nauki i liczbę opanowanych fiszek. Karty, zestawy,
ustawienia i historia powtórek są przypisane do lokalnego konta.

## Struktura

```text
core/          aplikacja, nawigacja, zdarzenia i obsługa błędów
database/      połączenie SQLite, lokalne konta, postępy i migracje
accounts/      rejestracja, logowanie i profile
mathematics/   silnik SymPy, generatory tematów i walidator odpowiedzi
learning/      sesje, adaptacja trudności i historia postępów
assistant/     lokalne, weryfikowane wyjaśnienia kroków równań
exams/         konfiguracja, timer, ocenianie i trwały zapis egzaminów
statistics/    agregacja historii użytkownika, analiza błędów i wykresy
gamification/  XP, poziomy, osiągnięcia i lokalny ranking
flashcards/    zestawy, karty, powtórki rozłożone w czasie i interfejs
exercises/     interfejs ćwiczeń
               własne zadania, walidacja zestawów i import HTTPS
ui/            motyw, komponenty i ekrany
tests/         testy jednostkowe
```

Plan nauki pozostaje ekranem informacyjnym; moduł fiszek jest dostępny z
lewego panelu nawigacyjnego.#   M a t h M a s t e r  
 