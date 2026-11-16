from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

from mathematics.topics import DIFFICULTY_NAMES, TOPIC_REQUIREMENTS, Topic


@dataclass(frozen=True, slots=True)
class LibraryTopic:
    id: str
    division: str
    subdivision: str
    title: str
    description: str
    difficulty: int
    theory: tuple[str, ...]
    examples: tuple[str, ...]
    subtopics: tuple[str, ...]
    exercise_topic: Topic
    custom: bool = False


@dataclass(frozen=True, slots=True)
class LibraryDivision:
    title: str
    subdivisions: tuple[str, ...]
    topics: tuple[LibraryTopic, ...]


# A syllabus node can expose several fine-grained subtopics while retaining a
# stable mapping to the closest verified generator in the existing engine.
_SPEC: Final[tuple[tuple[str, str, Topic, int, tuple[str, ...]], ...]] = (
    ("Arytmetyka", "Liczby i działania", Topic.ADDITION, 1, ("Liczby naturalne", "Liczby całkowite", "Liczby wymierne", "Liczby niewymierne i rzeczywiste")),
    ("Arytmetyka", "Działania i własności liczb", Topic.SUBTRACTION, 1, ("Kolejność wykonywania działań", "Szacowanie wyników")),
    ("Arytmetyka", "Podzielność i rozkład liczb", Topic.MULTIPLICATION, 2, ("Podzielność liczb", "Liczby pierwsze i złożone", "NWD i NWW", "Rozkład na czynniki pierwsze")),
    ("Arytmetyka", "Działania i własności liczb", Topic.DIVISION, 1, ("Dzielenie z resztą", "Działania na liczbach wymiernych")),
    ("Arytmetyka", "Systemy liczbowe", Topic.ORDER_OF_OPERATIONS, 2, ("System dziesiętny", "System dwójkowy", "Zamiana podstaw systemów")),
    ("Ułamki i liczby dziesiętne", "Ułamki zwykłe", Topic.FRACTION_SIMPLIFY, 1, ("Skracanie i rozszerzanie", "Porównywanie ułamków", "Ułamki równoważne")),
    ("Ułamki i liczby dziesiętne", "Ułamki zwykłe", Topic.FRACTION_EXPAND, 1, ("Rozszerzanie ułamków", "Sprowadzanie do wspólnego mianownika")),
    ("Ułamki i liczby dziesiętne", "Działania na ułamkach", Topic.FRACTION_ADDITION, 2, ("Dodawanie i odejmowanie", "Wspólny mianownik")),
    ("Ułamki i liczby dziesiętne", "Działania na ułamkach", Topic.FRACTION_SUBTRACTION, 2, ("Odejmowanie ułamków", "Liczby mieszane")),
    ("Ułamki i liczby dziesiętne", "Działania na ułamkach", Topic.FRACTION_MULTIPLICATION, 2, ("Mnożenie ułamków", "Skracanie przed mnożeniem")),
    ("Ułamki i liczby dziesiętne", "Działania na ułamkach", Topic.FRACTION_DIVISION, 2, ("Dzielenie przez ułamek", "Odwrotność ułamka")),
    ("Ułamki i liczby dziesiętne", "Postacie dziesiętne", Topic.PERCENT_OF, 2, ("Ułamki dziesiętne", "Ułamki okresowe", "Zamiana postaci ułamków")),
    ("Procenty i proporcje", "Procenty", Topic.PERCENT_OF, 2, ("Procent liczby", "Obniżki i podwyżki", "Procent składany")),
    ("Procenty i proporcje", "Procenty", Topic.PERCENT_DECREASE, 2, ("Obniżki procentowe", "Zmiana wartości")),
    ("Procenty i proporcje", "Proporcjonalność", Topic.PERCENT_ORIGINAL, 2, ("Proporcjonalność prosta", "Proporcjonalność odwrotna", "Skala", "Złota proporcja")),
    ("Algebra", "Wyrażenia i wielomiany", Topic.ALGEBRA_EXPRESSION, 2, ("Wyrażenia algebraiczne", "Wzory skróconego mnożenia", "Wielomiany", "Rozkład na czynniki")),
    ("Algebra", "Równania i nierówności", Topic.LINEAR_EQUATION, 2, ("Równania liniowe", "Równania wymierne", "Równania z parametrem")),
    ("Algebra", "Równania i nierówności", Topic.LINEAR_INEQUALITY, 2, ("Nierówności liniowe", "Przedziały rozwiązań")),
    ("Algebra", "Układy równań", Topic.LINEAR_SYSTEM, 3, ("Układy dwóch równań", "Metoda podstawiania", "Metoda przeciwnych współczynników")),
    ("Algebra", "Równania kwadratowe", Topic.QUADRATIC_EQUATION, 3, ("Wyróżnik trójmianu", "Postać iloczynowa", "Wzory Viète’a")),
    ("Geometria płaska", "Figury i ich własności", Topic.PYTHAGOREAN, 1, ("Punkty, proste i odcinki", "Kąty", "Trójkąty", "Czworokąty", "Wielokąty", "Przystawanie i podobieństwo", "Twierdzenie Talesa", "Twierdzenie Pitagorasa")),
    ("Geometria płaska", "Pola i obwody", Topic.AREA, 1, ("Pola prostokątów i kwadratów", "Pole trójkąta", "Pole równoległoboku", "Pole rombu", "Pole trapezu", "Pole koła")),
    ("Geometria płaska", "Pola i obwody", Topic.PERIMETER, 1, ("Obwody trójkątów i czworokątów", "Obwód okręgu")),
    ("Geometria płaska", "Okręgi i koła", Topic.AREA, 2, ("Promień i średnica", "Długość okręgu", "Pole koła")),
    ("Geometria przestrzenna", "Bryły i przekroje", Topic.VOLUME, 2, ("Graniastosłupy", "Ostrosłupy", "Walce", "Stożki", "Kule", "Przekroje brył")),
    ("Geometria przestrzenna", "Pola i objętości", Topic.SURFACE_AREA, 2, ("Pola powierzchni", "Objętości", "Jednostki objętości")),
    ("Geometria przestrzenna", "Geometria analityczna", Topic.ANALYTIC_GEOMETRY, 3, ("Punkty w układzie współrzędnych", "Długość odcinka", "Środek odcinka", "Geometria analityczna przestrzenna")),
    ("Funkcje", "Podstawy funkcji", Topic.FUNCTION_VALUE, 2, ("Pojęcie funkcji", "Dziedzina i zbiór wartości", "Odczytywanie wykresów")),
    ("Funkcje", "Rodzaje funkcji", Topic.LINEAR_EQUATION, 2, ("Funkcje liniowe", "Funkcje kwadratowe", "Funkcje wymierne", "Funkcje wykładnicze", "Funkcje logarytmiczne", "Funkcje trygonometryczne")),
    ("Funkcje", "Wykresy", Topic.GRAPH_POINT, 2, ("Przekształcenia wykresów", "Miejsca zerowe", "Monotoniczność")),
    ("Trygonometria", "Funkcje trygonometryczne", Topic.TRIGONOMETRY, 2, ("Sinus", "Cosinus", "Tangens", "Cotangens", "Wartości szczególne")),
    ("Trygonometria", "Tożsamości i równania", Topic.TRIGONOMETRY, 4, ("Tożsamości trygonometryczne", "Równania trygonometryczne", "Twierdzenie sinusów i cosinusów")),
    ("Potęgi, pierwiastki i logarytmy", "Potęgi i pierwiastki", Topic.POWERS, 2, ("Prawa działań na potęgach", "Potęgi o wykładniku całkowitym", "Potęgi o wykładniku wymiernym")),
    ("Potęgi, pierwiastki i logarytmy", "Potęgi i pierwiastki", Topic.SQUARE_ROOTS, 2, ("Pierwiastki kwadratowe", "Upraszczanie pierwiastków")),
    ("Potęgi, pierwiastki i logarytmy", "Logarytmy", Topic.LOGARITHMS, 3, ("Definicja logarytmu", "Własności logarytmów", "Równania wykładnicze")),
    ("Statystyka", "Miary danych", Topic.STATISTICS, 2, ("Średnia arytmetyczna", "Mediana", "Dominanta", "Wariancja", "Odchylenie standardowe")),
    ("Statystyka", "Prezentacja i analiza danych", Topic.STATISTICS, 2, ("Wykresy i tabele", "Analiza danych", "Interpretowanie danych")),
    ("Prawdopodobieństwo i kombinatoryka", "Zliczanie", Topic.COMBINATORICS, 3, ("Zasada mnożenia", "Permutacje", "Kombinacje", "Wariacje")),
    ("Prawdopodobieństwo i kombinatoryka", "Rachunek prawdopodobieństwa", Topic.PROBABILITY, 3, ("Zdarzenia losowe", "Prawdopodobieństwo klasyczne", "Prawdopodobieństwo warunkowe", "Schemat Bernoulliego")),
    ("Matematyka dyskretna", "Zbiory, logika i relacje", Topic.ALGEBRA_EXPRESSION, 4, ("Teoria zbiorów", "Logika matematyczna", "Relacje")),
    ("Matematyka dyskretna", "Grafy i rekurencja", Topic.COMBINATORICS, 5, ("Grafy", "Drzewa", "Rekurencja", "Kombinatoryka zaawansowana")),
    ("Analiza matematyczna", "Ciągi i granice", Topic.SEQUENCES, 3, ("Ciągi arytmetyczne", "Ciągi geometryczne", "Granice ciągów", "Ciągłość funkcji")),
    ("Analiza matematyczna", "Ciągi i granice", Topic.LIMITS, 4, ("Granice funkcji", "Ciągłość funkcji", "Granice jednostronne")),
    ("Analiza matematyczna", "Rachunek różniczkowy", Topic.DERIVATIVES, 4, ("Pochodne", "Różniczkowanie", "Zastosowania pochodnych")),
    ("Analiza matematyczna", "Rachunek całkowy", Topic.INTEGRALS, 4, ("Całki nieoznaczone", "Całki oznaczone", "Pole pod wykresem")),
    ("Analiza matematyczna", "Szeregi i równania różniczkowe", Topic.INTEGRALS, 5, ("Szeregi liczbowe", "Szeregi potęgowe", "Równania różniczkowe")),
    ("Algebra liniowa", "Wektory i macierze", Topic.LINEAR_SYSTEM, 4, ("Wektory", "Działania na macierzach", "Mnożenie macierzy")),
    ("Algebra liniowa", "Wyznaczniki i przestrzenie", Topic.LINEAR_SYSTEM, 5, ("Wyznaczniki", "Układy równań liniowych", "Przestrzenie wektorowe")),
    ("Algebra liniowa", "Wartości własne", Topic.LINEAR_SYSTEM, 5, ("Wartości własne", "Wektory własne", "Diagonalizacja")),
    ("Matematyka finansowa", "Oprocentowanie i oszczędzanie", Topic.PERCENT_INCREASE, 2, ("Oprocentowanie", "Lokaty", "Procent składany", "Inflacja", "Wartość pieniądza w czasie")),
    ("Matematyka finansowa", "Kredyty i raty", Topic.PERCENT_ORIGINAL, 3, ("Kredyty", "Raty równe i malejące", "Całkowity koszt kredytu")),
    ("Matematyka praktyczna", "Jednostki i pomiary", Topic.ORDER_OF_OPERATIONS, 1, ("Jednostki i konwersje", "Czas i prędkość", "Droga")),
    ("Matematyka praktyczna", "Zastosowania", Topic.PERCENT_OF, 1, ("Zużycie paliwa", "Obliczenia budowlane", "Obliczenia handlowe", "Zadania tekstowe")),
)

_TITLES: Final[dict[Topic, str]] = {
    Topic.ADDITION: "Dodawanie i rodzaje liczb",
    Topic.SUBTRACTION: "Odejmowanie i działania",
    Topic.MULTIPLICATION: "Podzielność i mnożenie",
    Topic.DIVISION: "Dzielenie",
    Topic.ORDER_OF_OPERATIONS: "Kolejność działań i systemy liczbowe",
    Topic.FRACTION_SIMPLIFY: "Ułamki zwykłe",
    Topic.FRACTION_EXPAND: "Rozszerzanie ułamków",
    Topic.FRACTION_ADDITION: "Dodawanie ułamków",
    Topic.FRACTION_SUBTRACTION: "Odejmowanie ułamków",
    Topic.FRACTION_MULTIPLICATION: "Mnożenie ułamków",
    Topic.FRACTION_DIVISION: "Dzielenie ułamków",
    Topic.PERCENT_OF: "Procenty",
    Topic.PERCENT_INCREASE: "Zmiany procentowe",
    Topic.PERCENT_DECREASE: "Obniżki procentowe",
    Topic.PERCENT_ORIGINAL: "Proporcje i wartość początkowa",
    Topic.ALGEBRA_EXPRESSION: "Wyrażenia i wielomiany",
    Topic.LINEAR_EQUATION: "Równania liniowe",
    Topic.LINEAR_INEQUALITY: "Nierówności liniowe",
    Topic.LINEAR_SYSTEM: "Układy równań liniowych",
    Topic.QUADRATIC_EQUATION: "Równania kwadratowe",
    Topic.AREA: "Pola figur",
    Topic.PERIMETER: "Obwody figur",
    Topic.VOLUME: "Objętości brył",
    Topic.SURFACE_AREA: "Pola powierzchni brył",
    Topic.PYTHAGOREAN: "Twierdzenie Pitagorasa",
    Topic.ANALYTIC_GEOMETRY: "Geometria analityczna",
    Topic.POWERS: "Potęgi",
    Topic.SQUARE_ROOTS: "Pierwiastki",
    Topic.FUNCTION_VALUE: "Wartości funkcji",
    Topic.GRAPH_POINT: "Wykresy funkcji",
    Topic.SEQUENCES: "Ciągi",
    Topic.TRIGONOMETRY: "Trygonometria",
    Topic.LOGARITHMS: "Logarytmy",
    Topic.COMBINATORICS: "Kombinatoryka",
    Topic.PROBABILITY: "Prawdopodobieństwo",
    Topic.STATISTICS: "Statystyka",
    Topic.LIMITS: "Granice",
    Topic.DERIVATIVES: "Pochodne",
    Topic.INTEGRALS: "Całki",
}

_TITLE_OVERRIDES: Final[dict[tuple[str, str, Topic], str]] = {
    ("Ułamki i liczby dziesiętne", "Postacie dziesiętne", Topic.PERCENT_OF): "Ułamki dziesiętne i okresowe",
    ("Procenty i proporcje", "Procenty", Topic.PERCENT_OF): "Obliczanie procentów",
    ("Procenty i proporcje", "Proporcjonalność", Topic.PERCENT_ORIGINAL): "Proporcje i proporcjonalność",
    ("Matematyka finansowa", "Kredyty i raty", Topic.PERCENT_ORIGINAL): "Kredyty i raty",
    ("Geometria płaska", "Pola i obwody", Topic.AREA): "Pola figur płaskich",
    ("Geometria płaska", "Okręgi i koła", Topic.AREA): "Koła i okręgi",
    ("Algebra liniowa", "Wektory i macierze", Topic.LINEAR_SYSTEM): "Układy liniowe i eliminacja Gaussa",
    ("Algebra liniowa", "Wyznaczniki i przestrzenie", Topic.LINEAR_SYSTEM): "Macierze, wyznaczniki i przestrzenie",
    ("Algebra liniowa", "Wartości własne", Topic.LINEAR_SYSTEM): "Wartości i wektory własne",
    ("Trygonometria", "Funkcje trygonometryczne", Topic.TRIGONOMETRY): "Wartości funkcji trygonometrycznych",
    ("Trygonometria", "Tożsamości i równania", Topic.TRIGONOMETRY): "Tożsamości i równania trygonometryczne",
    ("Statystyka", "Miary danych", Topic.STATISTICS): "Statystyka opisowa",
    ("Statystyka", "Prezentacja i analiza danych", Topic.STATISTICS): "Wizualizacja i analiza danych",
    ("Matematyka dyskretna", "Grafy i rekurencja", Topic.COMBINATORICS): "Grafy, drzewa i rekurencja",
    ("Analiza matematyczna", "Szeregi i równania różniczkowe", Topic.INTEGRALS): "Szeregi i równania różniczkowe",
}

_THEORY: Final[dict[Topic, tuple[str, ...]]] = {
    Topic.AREA: ("Pole opisuje miarę powierzchni figury i zapisujemy je w jednostkach kwadratowych.", "Równoległobok: P=a·h; romb: P=e·f/2; trapez: P=(a+b)·h/2."),
    Topic.PERIMETER: ("Obwód to suma długości boków figury.", "Dla okręgu obwód wynosi 2πr."),
    Topic.VOLUME: ("Objętość mierzy przestrzeń zajmowaną przez bryłę i zapisujemy ją w jednostkach sześciennych.", "Walec: V=πr²h; stożek: V=πr²h/3; kula: V=4πr³/3."),
    Topic.SURFACE_AREA: ("Pole powierzchni całkowitej jest sumą pól wszystkich ścian lub powierzchni bryły.", "Prostopadłościan: Pc=2(ab+ac+bc); walec: Pc=2πr(r+h)."),
    Topic.LINEAR_INEQUALITY: ("Nierówność opisuje zbiór wartości spełniających relację porządku.", "Przy mnożeniu obu stron przez liczbę ujemną zmieniamy zwrot nierówności."),
    Topic.PROBABILITY: ("W modelu klasycznym P(A)=|A|/|Ω|, gdy wyniki są jednakowo prawdopodobne.", "Prawdopodobieństwo należy do przedziału [0,1]."),
    Topic.STATISTICS: ("Średnia to suma obserwacji podzielona przez ich liczbę; mediana jest wartością środkową po uporządkowaniu danych.", "Wariancja mierzy rozproszenie obserwacji wokół średniej."),
    Topic.COMBINATORICS: ("Reguła mnożenia łączy liczbę możliwości kolejnych wyborów.", "Kombinacje liczą wybory, w których kolejność nie ma znaczenia."),
    Topic.SEQUENCES: ("Ciąg arytmetyczny ma stałą różnicę, a geometryczny stały iloraz.", "aₙ=a₁+(n−1)r lub aₙ=a₁qⁿ⁻¹."),
}


def _difficulty_name(level: int) -> str:
    return DIFFICULTY_NAMES[level]


def _build_topics() -> tuple[LibraryTopic, ...]:
    topics: list[LibraryTopic] = []
    for division, subdivision, exercise_topic, difficulty, subtopics in _SPEC:
        path_slug = ".".join(
            _slug(part) for part in (division, subdivision, exercise_topic.value)
        )
        topic_id = f"curriculum.{path_slug}"
        theory = _THEORY.get(
            exercise_topic,
            tuple(TOPIC_REQUIREMENTS[exercise_topic]),
        )
        topics.append(
            LibraryTopic(
                id=topic_id,
                division=division,
                subdivision=subdivision,
                title=_TITLE_OVERRIDES.get(
                    (division, subdivision, exercise_topic), _TITLES[exercise_topic]
                ),
                description=(
                    f"Zakres obejmuje: {', '.join(subtopics)}. "
                    f"Poziom: {_difficulty_name(difficulty)}."
                ),
                difficulty=difficulty,
                theory=theory,
                examples=(f"Przykład: {subtopics[0]}.", f"Zastosowanie: {subtopics[-1]}."),
                subtopics=subtopics,
                exercise_topic=exercise_topic,
            )
        )
    return tuple(topics)


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", normalized.casefold()).strip("_")


LIBRARY_TOPICS: Final[tuple[LibraryTopic, ...]] = _build_topics()
LIBRARY_DIVISIONS: Final[tuple[LibraryDivision, ...]] = tuple(
    LibraryDivision(
        title=division,
        subdivisions=tuple(dict.fromkeys(
            topic.subdivision for topic in LIBRARY_TOPICS
            if topic.division == division
        )),
        topics=tuple(topic for topic in LIBRARY_TOPICS if topic.division == division),
    )
    for division in dict.fromkeys(topic.division for topic in LIBRARY_TOPICS)
)

STATUS_VALUES: Final[tuple[str, ...]] = ("unmastered", "started", "mastered")
STATUS_LABELS: Final[dict[str, str]] = {
    "unmastered": "Nieopanowany",
    "started": "Rozpoczęty",
    "mastered": "Opanowany",
}

