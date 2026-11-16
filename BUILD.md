# Budowanie MathMaster dla Windows

Buduj na Windows, w środowisku Python 3.13+ z zainstalowanymi zależnościami:

```bat
py -3.13 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
```

`requirements-build.txt` instaluje zależności aplikacji oraz PyInstaller.

## Produkcyjne wydanie bez konsoli

Domyślnie tworzony jest wariant `onedir`:

```bat
build.bat
```

Uruchamiaj `dist\MathMaster\MathMaster.exe`; do dystrybucji przekazuj cały
katalog `dist\MathMaster`. Pojedynczy plik EXE można zbudować poleceniem:

```bat
build.bat onefile
```

Wariant onefile trafia do `dist\MathMaster.exe`. Pierwszy start może trwać
dłużej, ponieważ PyInstaller rozpakowuje zależności do katalogu tymczasowego.

## Wersja diagnostyczna

```bat
build_debug.bat
build_debug.bat onefile
```

Wersje diagnostyczne pokazują konsolę i tracebacki. Nie przeznaczaj ich do
dystrybucji użytkownikom końcowym. Trafiają do osobnego katalogu
`dist\debug`, więc nie nadpisują wydań produkcyjnych.

## Zasoby i dane trwałe

`MathMaster.spec` dołącza CustomTkinter, SymPy, Matplotlib, bcrypt,
cryptography, klienta WebSocket, backendy Matplotlib, opcjonalne czcionki
i ikonę `assets\icons\mathmaster.ico`. Do paczki trafiają wyłącznie statyczne
JSON-y z `data\mathematics`, `data\exams` i `data\manifests`. Lokalna baza,
logi i kopie zapasowe nie są dołączane.
Plyer nie jest obecnie używany ani wymagany przez aplikację desktopową, więc
nie jest instalowany ani pakowany.

Wszystkie zasoby do odczytu są lokalizowane względem `sys._MEIPASS` (albo
katalogu projektu podczas uruchamiania ze źródeł). SQLite, logi i kopie
zapasowe trafiają na Windows do `%APPDATA%\MathMaster`, poza katalogiem
instalacji i poza katalogiem tymczasowym PyInstaller. Ustawienie
`MATHMASTER_DATA_DIR` pozwala wskazać inny trwały katalog.

Przy aktualizacji istniejąca baza nie jest nadpisywana. Starsze schematy są
migrowane po wykonaniu sprawdzonej kopii SQLite. Jeśli dostępna jest baza ze
starszej lokalizacji `%LOCALAPPDATA%\MathMaster` lub katalogu przy EXE,
aplikacja kopiuje ją do nowej lokalizacji bez usuwania źródła. Nie kopiuj pliku
bazy do paczki aplikacji.

## Weryfikacja wydania

Po zbudowaniu uruchom produkcyjny EXE na Windows i przetestuj podstawowe
przepływy z kontem testowym oraz kopią bazy. Testy jednostkowe źródeł:

```bat
python -m unittest discover -s tests -v
```

Budowanie i testy jednostkowe nie zastępują ręcznego testu GUI w docelowym
środowisku Windows. Przed wydaniem sprawdź start offline, rejestrację,
logowanie, zapis postępów, motywy, zadania, egzaminy, fiszki, statystyki,
import/eksport JSON oraz ponowne uruchomienie i aktualizację z istniejącą bazą.
