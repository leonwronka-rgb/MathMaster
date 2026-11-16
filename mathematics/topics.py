from __future__ import annotations

from enum import StrEnum


class Topic(StrEnum):
    ADDITION = "addition"
    SUBTRACTION = "subtraction"
    MULTIPLICATION = "multiplication"
    DIVISION = "division"
    ORDER_OF_OPERATIONS = "order_of_operations"

    FRACTION_SIMPLIFY = "fraction_simplify"
    FRACTION_EXPAND = "fraction_expand"
    FRACTION_ADDITION = "fraction_addition"
    FRACTION_SUBTRACTION = "fraction_subtraction"
    FRACTION_MULTIPLICATION = "fraction_multiplication"
    FRACTION_DIVISION = "fraction_division"

    PERCENT_OF = "percent_of"
    PERCENT_INCREASE = "percent_increase"
    PERCENT_DECREASE = "percent_decrease"
    PERCENT_ORIGINAL = "percent_original"

    ALGEBRA_EXPRESSION = "algebra_expression"
    LINEAR_EQUATION = "linear_equation"
    LINEAR_INEQUALITY = "linear_inequality"
    LINEAR_SYSTEM = "linear_system"
    QUADRATIC_EQUATION = "quadratic_equation"

    AREA = "area"
    PERIMETER = "perimeter"
    VOLUME = "volume"
    SURFACE_AREA = "surface_area"
    PYTHAGOREAN = "pythagorean"
    ANALYTIC_GEOMETRY = "analytic_geometry"

    POWERS = "powers"
    SQUARE_ROOTS = "square_roots"

    FUNCTION_VALUE = "function_value"
    GRAPH_POINT = "graph_point"
    SEQUENCES = "sequences"
    TRIGONOMETRY = "trigonometry"
    LOGARITHMS = "logarithms"
    COMBINATORICS = "combinatorics"
    PROBABILITY = "probability"
    STATISTICS = "statistics"

    LIMITS = "limits"
    DERIVATIVES = "derivatives"
    INTEGRALS = "integrals"


TOPIC_CATEGORIES: dict[str, tuple[Topic, ...]] = {
    "Arytmetyka": (
        Topic.ADDITION, Topic.SUBTRACTION, Topic.MULTIPLICATION,
        Topic.DIVISION, Topic.ORDER_OF_OPERATIONS,
    ),
    "Ułamki": (
        Topic.FRACTION_SIMPLIFY, Topic.FRACTION_EXPAND,
        Topic.FRACTION_ADDITION, Topic.FRACTION_SUBTRACTION,
        Topic.FRACTION_MULTIPLICATION, Topic.FRACTION_DIVISION,
    ),
    "Procenty": (
        Topic.PERCENT_OF, Topic.PERCENT_INCREASE,
        Topic.PERCENT_DECREASE, Topic.PERCENT_ORIGINAL,
    ),
    "Algebra": (
        Topic.ALGEBRA_EXPRESSION, Topic.LINEAR_EQUATION,
        Topic.LINEAR_INEQUALITY, Topic.LINEAR_SYSTEM, Topic.QUADRATIC_EQUATION,
    ),
    "Geometria": (
        Topic.AREA, Topic.PERIMETER, Topic.VOLUME, Topic.SURFACE_AREA,
        Topic.PYTHAGOREAN, Topic.ANALYTIC_GEOMETRY,
    ),
    "Potęgi i pierwiastki": (Topic.POWERS, Topic.SQUARE_ROOTS),
    "Funkcje i wykresy": (
        Topic.FUNCTION_VALUE, Topic.GRAPH_POINT, Topic.SEQUENCES,
    ),
    "Trygonometria": (Topic.TRIGONOMETRY,),
    "Logarytmy": (Topic.LOGARITHMS,),
    "Kombinatoryka i prawdopodobieństwo": (
        Topic.COMBINATORICS, Topic.PROBABILITY,
    ),
    "Statystyka i dane": (Topic.STATISTICS,),
    "Analiza matematyczna": (
        Topic.LIMITS, Topic.DERIVATIVES, Topic.INTEGRALS,
    ),
}

TOPICS = tuple(topic for topics in TOPIC_CATEGORIES.values() for topic in topics)
DIFFICULTY_LEVELS = (1, 2, 3, 4, 5)
DIFFICULTY_NAMES = {
    1: "Szkoła podstawowa — klasy 4–6",
    2: "Szkoła podstawowa — klasy 7–8",
    3: "Liceum / CKU — zakres podstawowy",
    4: "Szkoła średnia — poziom rozszerzony",
    5: "Poziom akademicki",
}

CURRICULUM_VERSION = "2026/2027"
CURRICULUM_SOURCES = (
    "https://eli.gov.pl/eli/DU/2026/947/ogl/pol",
    "https://cke.gov.pl/egzamin-maturalny/informatory/",
    "https://zpe.gov.pl/podstawa-programowa/szkola-podstawowa/matematyka",
)

TOPIC_REQUIREMENTS: dict[Topic, list[str]] = {
    Topic.ADDITION: ["Wykonuje dodawanie liczb naturalnych, całkowitych i wymiernych.", "Szacuje wynik i stosuje dodawanie w zadaniach praktycznych."],
    Topic.SUBTRACTION: ["Wykonuje odejmowanie liczb naturalnych, całkowitych i wymiernych.", "Interpretuje różnicę w kontekście zadania."],
    Topic.MULTIPLICATION: ["Wykonuje mnożenie liczb naturalnych, całkowitych i wymiernych.", "Stosuje własności działań i mnożenie w zadaniach tekstowych."],
    Topic.DIVISION: ["Dzieli liczby naturalne, całkowite i wymierne przez niezerowy dzielnik.", "Kontroluje wynik przez mnożenie."],
    Topic.ORDER_OF_OPERATIONS: ["Stosuje kolejność wykonywania działań i nawiasy.", "Oblicza wartości wyrażeń arytmetycznych."],
    Topic.FRACTION_SIMPLIFY: ["Skraca ułamki zwykłe z użyciem wspólnego dzielnika.", "Przedstawia ułamek w postaci nieskracalnej."],
    Topic.FRACTION_EXPAND: ["Rozszerza ułamek przez ten sam niezerowy czynnik.", "Rozpoznaje ułamki równoważne."],
    Topic.FRACTION_ADDITION: ["Dodaje ułamki o jednakowych i różnych mianownikach.", "Sprowadza ułamki do wspólnego mianownika."],
    Topic.FRACTION_SUBTRACTION: ["Odejmuje ułamki o jednakowych i różnych mianownikach.", "Upraszcza otrzymany wynik."],
    Topic.FRACTION_MULTIPLICATION: ["Mnoży ułamki zwykłe i liczby wymierne.", "Skraca wynik działania."],
    Topic.FRACTION_DIVISION: ["Dzieli przez ułamek różny od zera, stosując odwrotność.", "Upraszcza wynik dzielenia."],
    Topic.PERCENT_OF: ["Oblicza procent danej liczby.", "Interpretuje procent jako ułamek o mianowniku 100."],
    Topic.PERCENT_INCREASE: ["Oblicza wartość po podwyżce procentowej.", "Rozwiązuje praktyczne zadania o zmianie procentowej."],
    Topic.PERCENT_DECREASE: ["Oblicza wartość po obniżce procentowej.", "Rozróżnia zmianę procentową od zmiany o daną liczbę."],
    Topic.PERCENT_ORIGINAL: ["Wyznacza wartość początkową na podstawie wartości po zmianie procentowej.", "Układa równanie dla zadania procentowego."],
    Topic.ALGEBRA_EXPRESSION: ["Zapisuje zależności za pomocą wyrażeń algebraicznych.", "Redukuje wyrazy podobne i przekształca wyrażenia."],
    Topic.LINEAR_EQUATION: ["Rozwiązuje równania pierwszego stopnia z jedną niewiadomą.", "Sprawdza rozwiązanie przez podstawienie."],
    Topic.LINEAR_INEQUALITY: ["Rozwiązuje nierówności liniowe z jedną niewiadomą.", "Pamięta o zmianie zwrotu nierówności przy mnożeniu lub dzieleniu przez liczbę ujemną."],
    Topic.LINEAR_SYSTEM: ["Rozwiązuje układy dwóch równań liniowych z dwiema niewiadomymi.", "Interpretuje rozwiązanie jako punkt wspólny prostych."],
    Topic.QUADRATIC_EQUATION: ["Rozwiązuje równania kwadratowe przez rozkład na czynniki lub wzory.", "Weryfikuje liczbę rozwiązań."],
    Topic.AREA: ["Oblicza pola prostokąta, kwadratu, trójkąta, równoległoboku, rombu i trapezu.", "Dobiera wysokość, przekątne lub podstawy do właściwego wzoru.", "Oblicza pole koła i stosuje jednostki kwadratowe."],
    Topic.PERIMETER: ["Oblicza obwody trójkątów i czworokątów, w tym równoległoboku, rombu i trapezu.", "Oblicza obwód okręgu i stosuje jednostki długości."],
    Topic.VOLUME: ["Oblicza objętość graniastosłupów i walców.", "Stosuje jednostki sześcienne i zależności między jednostkami."],
    Topic.SURFACE_AREA: ["Oblicza pole powierzchni sześcianu, prostopadłościanu i walca.", "Rozpoznaje ściany bryły i uwzględnia wszystkie powierzchnie."],
    Topic.PYTHAGOREAN: ["Stosuje twierdzenie Pitagorasa i twierdzenie odwrotne.", "Wyznacza brakujący bok trójkąta prostokątnego."],
    Topic.ANALYTIC_GEOMETRY: ["Wyznacza długość odcinka i środek odcinka w układzie współrzędnych.", "Stosuje współrzędne punktów w zadaniach geometrycznych."],
    Topic.POWERS: ["Stosuje prawa działań na potęgach o wykładnikach całkowitych.", "Zapisuje liczby w notacji wykładniczej na poziomie rozszerzonym."],
    Topic.SQUARE_ROOTS: ["Oblicza i upraszcza pierwiastki kwadratowe.", "Wykonuje działania na pierwiastkach w prostych wyrażeniach."],
    Topic.FUNCTION_VALUE: ["Oblicza wartość funkcji dla danego argumentu.", "Odczytuje zależności i wartości funkcji z opisu, wzoru lub tabeli."],
    Topic.GRAPH_POINT: ["Wyznacza współrzędne punktu należącego do wykresu.", "Interpretuje wykres funkcji w układzie współrzędnych."],
    Topic.SEQUENCES: ["Rozpoznaje ciąg arytmetyczny lub geometryczny i wyznacza jego wyrazy.", "Stosuje wzór ogólny ciągu arytmetycznego lub geometrycznego."],
    Topic.TRIGONOMETRY: ["Stosuje sinus, cosinus i tangens kąta ostrego w trójkącie prostokątnym.", "Korzysta z wartości funkcji trygonometrycznych dla wybranych kątów."],
    Topic.LOGARITHMS: ["Stosuje definicję logarytmu i związek logarytmu z potęgowaniem.", "Oblicza logarytmy w prostych przykładach."],
    Topic.COMBINATORICS: ["Stosuje regułę mnożenia w zliczaniu możliwości.", "Oblicza liczbę kombinacji w prostych wyborach bez uwzględniania kolejności."],
    Topic.PROBABILITY: ["Oblicza prawdopodobieństwo zdarzenia w klasycznym modelu.", "Wyznacza liczbę wyników sprzyjających i wszystkich wyników."],
    Topic.STATISTICS: ["Odczytuje i porównuje dane przedstawione w tabeli.", "Oblicza średnią arytmetyczną i medianę zestawu danych."],
    Topic.LIMITS: ["Wyznacza granice prostych funkcji w punkcie.", "Stosuje granice wielomianów i podstawowe przekształcenia."],
    Topic.DERIVATIVES: ["Oblicza pochodną wielomianu i wybranych funkcji.", "Stosuje pochodną do badania zmian funkcji na poziomie rozszerzonym."],
    Topic.INTEGRALS: ["Wyznacza całki nieoznaczone z wielomianów i wybranych funkcji.", "Łączy całkowanie z różniczkowaniem na poziomie rozszerzonym."],
}

TOPIC_DATA: list[dict[str, object]] = [
    {
        "id": topic.value,
        "category": category,
        "requirements": TOPIC_REQUIREMENTS[topic],
    }
    for category, category_topics in TOPIC_CATEGORIES.items()
    for topic in category_topics
]
