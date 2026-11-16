from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AchievementDefinition:
    key: str
    title: str
    description: str
    reward_xp: int
    category: str
    rarity: str
    icon: str
    target: int = 1
    badge_key: str = ""
    avatar_frame_key: str = ""
    server_only: bool = False


def _a(
    key: str,
    title: str,
    description: str,
    category: str,
    rarity: str = "Zwykłe",
    icon: str = "🏅",
    target: int = 1,
    frame: str = "",
    server_only: bool = False,
) -> AchievementDefinition:
    return AchievementDefinition(
        key, title, description, 15 if rarity == "Zwykłe" else 30 if rarity == "Niezwykłe"
        else 50 if rarity == "Rzadkie" else 75 if rarity == "Epickie" else 100,
        category, rarity, icon, target, f"badge_{key}", frame, server_only,
    )


ACHIEVEMENTS = (
    _a("first_exercise", "Pierwszy krok", "Rozwiąż pierwsze zadanie.", "Pierwsze kroki"),
    _a("first_correct", "Pierwsza poprawna odpowiedź", "Odpowiedz poprawnie na pierwsze zadanie.", "Pierwsze kroki"),
    _a("first_topic", "Odkrywca tematów", "Ukończ pierwszy temat.", "Pierwsze kroki"),
    _a("first_exam", "Podejście do egzaminu", "Ukończ pierwszy egzamin.", "Pierwsze kroki"),
    _a("first_flashcard", "Pierwsza fiszka", "Utwórz pierwszą własną fiszkę.", "Pierwsze kroki"),
    _a("study_3", "Dobry początek", "Ucz się przez 3 kolejne dni.", "Regularność", "Niezwykłe", "🔥", 3),
    _a("seven_day_study", "Tydzień nauki", "Ucz się przez 7 kolejnych dni.", "Regularność", "Rzadkie", "🔥", 7),
    _a("study_30", "Miesiąc wytrwałości", "Ucz się przez 30 kolejnych dni.", "Regularność", "Epickie", "🔥", 30, "frame_steady"),
    _a("study_100", "Niezłomny", "Ucz się przez 100 kolejnych dni.", "Regularność", "Legendarne", "🌟", 100, "frame_legend"),
    _a("study_365", "Rok matematyki", "Ucz się przez 365 kolejnych dni.", "Regularność", "Legendarne", "👑", 365, "frame_year"),
    _a("ten_correct", "Dziesięć poprawnych", "Odpowiedz poprawnie 10 razy.", "Dokładność", "Niezwykłe", "🎯", 10),
    _a("ten_streak", "Seria mistrza", "Odpowiedz poprawnie 10 razy z rzędu.", "Dokładność", "Rzadkie", "⚡", 10),
    _a("streak_25", "Nie do zatrzymania", "Odpowiedz poprawnie 25 razy z rzędu.", "Dokładność", "Epickie", "⚡", 25),
    _a("hundred_correct", "Sto trafień", "Odpowiedz poprawnie 100 razy.", "Dokładność", "Rzadkie", "🎯", 100),
    _a("perfect_exam", "Egzamin bezbłędny", "Uzyskaj 100% w egzaminie.", "Dokładność", "Epickie", "💯"),
    _a("hundred_streak", "Perfekcja absolutna", "Rozwiąż 100 zadań z rzędu bez błędu.", "Dokładność", "Legendarne", "💯", 100, "frame_perfection"),
    _a("master_arithmetic", "Mistrz arytmetyki", "Uzyskaj co najmniej 80% z 10 zadań z arytmetyki.", "Mistrzowie działów", "Niezwykłe", "➕", 10),
    _a("master_fractions", "Mistrz ułamków", "Uzyskaj co najmniej 80% z 10 zadań o ułamkach.", "Mistrzowie działów", "Niezwykłe", "½", 10),
    _a("master_percentages", "Mistrz procentów", "Uzyskaj co najmniej 80% z 10 zadań o procentach.", "Mistrzowie działów", "Niezwykłe", "%", 10),
    _a("master_algebra", "Mistrz algebry", "Uzyskaj co najmniej 80% z 10 zadań z algebry.", "Mistrzowie działów", "Rzadkie", "𝑥", 10),
    _a("master_geometry", "Mistrz geometrii", "Uzyskaj co najmniej 80% z 10 zadań geometrycznych.", "Mistrzowie działów", "Rzadkie", "📐", 10),
    _a("master_trigonometry", "Mistrz trygonometrii", "Uzyskaj co najmniej 80% z 10 zadań trygonometrycznych.", "Mistrzowie działów", "Rzadkie", "∠", 10),
    _a("master_statistics", "Mistrz statystyki", "Uzyskaj co najmniej 80% z 10 zadań ze statystyki.", "Mistrzowie działów", "Rzadkie", "📊", 10),
    _a("master_calculus", "Mistrz analizy matematycznej", "Uzyskaj co najmniej 80% z 10 zadań z analizy.", "Mistrzowie działów", "Epickie", "∫", 10, "frame_calculus"),
    _a("master_powers", "Mistrz potęg", "Uzyskaj co najmniej 80% z 10 zadań o potęgach i pierwiastkach.", "Mistrzowie działów", "Niezwykłe", "²", 10),
    _a("master_functions", "Mistrz funkcji", "Uzyskaj co najmniej 80% z 10 zadań o funkcjach.", "Mistrzowie działów", "Rzadkie", "ƒ", 10),
    _a("master_logarithms", "Mistrz logarytmów", "Uzyskaj co najmniej 80% z 10 zadań o logarytmach.", "Mistrzowie działów", "Rzadkie", "㏒", 10),
    _a("flashcards_10", "Kolekcjoner", "Opanuj 10 fiszek.", "Fiszki", "Niezwykłe", "🗂", 10),
    _a("flashcards_100", "Biblioteka wiedzy", "Opanuj 100 fiszek.", "Fiszki", "Rzadkie", "🗂", 100),
    _a("flashcards_500", "Pamięć fotograficzna", "Opanuj 500 fiszek.", "Fiszki", "Epickie", "🧠", 500, "frame_memory"),
    _a("deck_perfect", "Perfekcyjny zestaw", "Odpowiedz bezbłędnie na wszystkie fiszki z zestawu w teście.", "Fiszki", "Rzadkie", "💯"),
    _a("review_streak_30", "Rytm powtórek", "Powtarzaj fiszki przez 30 kolejnych dni.", "Fiszki", "Epickie", "📆", 30),
    _a("first_passed_exam", "Zdany egzamin", "Zdaj pierwszy egzamin.", "Egzaminy", "Niezwykłe", "🎓"),
    _a("five_passed_exams", "Egzaminator", "Zdaj 5 egzaminów.", "Egzaminy", "Rzadkie", "🎓", 5),
    _a("ten_passed_exams", "Mistrz egzaminów", "Zdaj 10 egzaminów.", "Egzaminy", "Epickie", "🎓", 10),
    _a("three_exams_90", "Wysoka forma", "Zdobądź ponad 90% w trzech egzaminach.", "Egzaminy", "Epickie", "🌟", 3),
    _a("difficult_exam", "Egzaminator ekspercki", "Zdaj egzamin na najwyższym poziomie trudności.", "Egzaminy", "Legendarne", "🏆", 1, "frame_expert"),
    _a("battle_first_win", "Pierwsze zwycięstwo", "Wygraj pierwszy potwierdzony pojedynek Quiz Battle.", "Quiz Battle", "Niezwykłe", "⚔", server_only=True),
    _a("battle_5_wins", "Pojedynek za pojedynkiem", "Wygraj 5 potwierdzonych pojedynków.", "Quiz Battle", "Rzadkie", "⚔", 5, server_only=True),
    _a("battle_25_wins", "Legenda areny", "Wygraj 25 potwierdzonych pojedynków.", "Quiz Battle", "Epickie", "⚔", 25, "frame_battle", True),
    _a("battle_10_streak", "Seria zwycięstw", "Wygraj 10 potwierdzonych pojedynków z rzędu.", "Quiz Battle", "Legendarne", "🔥", 10, "frame_battle_legend", True),
    _a("battle_one_mistake", "Precyzyjny pojedynek", "Wygraj potwierdzony pojedynek z najwyżej jedną pomyłką.", "Quiz Battle", "Rzadkie", "🎯", server_only=True),
    _a("battle_expert_win", "Mistrz areny", "Wygraj potwierdzony pojedynek ekspercki.", "Quiz Battle", "Legendarne", "👑", 1, "frame_arena", True),
)

CATEGORY_ACHIEVEMENT_KEYS = {
    "Arytmetyka": "master_arithmetic",
    "Liczby i działania": "master_arithmetic",
    "Ułamki": "master_fractions",
    "Ułamki i liczby dziesiętne": "master_fractions",
    "Procenty": "master_percentages",
    "Procenty i proporcje": "master_percentages",
    "Algebra": "master_algebra",
    "Geometria": "master_geometry",
    "Geometria płaska": "master_geometry",
    "Geometria przestrzenna": "master_geometry",
    "Potęgi i pierwiastki": "master_powers",
    "Potęgi, pierwiastki i logarytmy": "master_powers",
    "Funkcje i wykresy": "master_functions",
    "Funkcje": "master_functions",
    "Trygonometria": "master_trigonometry",
    "Logarytmy": "master_logarithms",
    "Analiza matematyczna": "master_calculus",
    "Statystyka": "master_statistics",
}
