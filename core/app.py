from __future__ import annotations

from pathlib import Path
from datetime import datetime
import tkinter as tk

import customtkinter as ctk

from assistant.assistant_screen import MathAssistantScreen
from assistant.assistant_service import MathAssistantService
from accounts.auth import AuthService, User
from accounts.profile import ProfileService
from config import AppConfig
from core.error_handler import ErrorHandler
from core.navigation import NavigationController
from database.database import Database
from database.backup_service import DatabaseBackupService
from settings.backup_manager import BackupManager
from settings.settings_manager import DEFAULT_SETTINGS, SettingsManager, SettingsStorageError
from settings.settings_screen import SettingsScreen
from settings.theme_manager import ThemeManager
from exams.exam_screen import ExamScreen
from exams.exam_service import ExamService
from exercises.custom_task_screen import CustomTaskScreen
from exercises.custom_tasks import CustomTaskService
from flashcards.flashcard_screen import FlashcardScreen
from flashcards.service import FlashcardService
from gamification.service import GamificationService, UnlockedAchievement
from learning.learning_service import LearningService
from learning.learning_screen import LearningScreen
from mathematics.topics import Topic
from mathematics.library_service import TopicLibraryService
from mathematics.topic_library import LibraryTopic
from statistics.service import StatisticsService
from statistics.statistics_screen import StatisticsScreen
from ui.sidebar import NavigationSidebar
from ui.screens.auth_screen import AuthScreen
from ui.screens.home_screen import HomeScreen
from ui.screens.gamification_screens import AchievementsScreen, RankingScreen
from ui.screens.profile_screen import ProfileScreen
from ui.screens.section_screen import SectionScreen
from ui.screens.topic_library_screen import TopicLibraryScreen
from ui.theme import apply_theme, COLORS
from quiz_battle.screen import QuizBattleScreen
from quiz_battle.service import QuizBattleService
from educational_content.service import EducationalContentService


class MathMasterApp(ctk.CTk):
    def __init__(self, config: AppConfig) -> None:
        apply_theme()
        super().__init__()
        self.settings = config
        self.error_handler = ErrorHandler(self)
        self.database = Database(
            config.database_path, config.legacy_database_paths
        )
        self.database.initialize()
        self.educational_content = EducationalContentService(
            self.database, config.content_dir
        )
        self.educational_content.initialize()
        self.backups = DatabaseBackupService(self.database, config.backup_dir)
        self.backup_manager = BackupManager(self.database, config.backup_dir)
        self.settings_manager = SettingsManager(self.database)
        self.theme_manager = ThemeManager(self)
        self.user_preferences = dict(DEFAULT_SETTINGS)
        self._reminder_after_id: str | None = None
        self._sent_reminders: set[tuple[int, str, str]] = set()
        self.auth = AuthService(self.database)
        self.profiles = ProfileService(self.database)
        self.learning = LearningService(
            self.database,
            exercise_provider=self.educational_content.generate_exercise,
        )
        self.topic_library = TopicLibraryService(self.database)
        self.gamification = GamificationService(self.database)
        self.quiz_battle = QuizBattleService(
            self.database,
            self.gamification,
            on_verified_result=lambda: self.after(
                0, self._on_gamification_update
            ),
        )
        self.exams = ExamService(self.database, gamification=self.gamification)
        self.custom_tasks = CustomTaskService(self.database)
        self.flashcards = FlashcardService(self.database)
        self.statistics = StatisticsService(self.database)
        self.math_assistant = MathAssistantService()
        self.current_user: User | None = None
        self._recommended_topic: Topic | None = None
        self._recommended_library_topic_id: str | None = None

        self.title(f"{config.app_name} — nauka matematyki")
        self.geometry(f"{config.window_width}x{config.window_height}")
        self.minsize(720, 600)
        self.configure(fg_color=COLORS["background"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.sidebar = NavigationSidebar(
            self,
            app_name=config.app_name,
            on_navigate=self._navigate,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.content = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=(28, 36), pady=(28, 20))
        self.navigation = NavigationController(self.content, self.error_handler)
        self.navigation.register(
            "auth",
            lambda parent: AuthScreen(parent, self.auth, self._on_authenticated),
        )
        for screen_name, label in NavigationSidebar.ITEMS:
            if screen_name == "home":
                self.navigation.register(
                    screen_name,
                    lambda parent: self._create_home(parent),
                )
            elif screen_name == "settings":
                self.navigation.register(
                    screen_name, lambda parent: self._create_settings(parent)
                )
            elif screen_name in {"learning", "exercises"}:
                self.navigation.register(
                    screen_name, lambda parent: self._create_learning(parent)
                )
            elif screen_name == "library":
                self.navigation.register(
                    screen_name, lambda parent: self._create_topic_library(parent)
                )
            elif screen_name == "ranking":
                self.navigation.register(
                    screen_name, lambda parent: self._create_ranking(parent)
                )
            elif screen_name == "statistics":
                self.navigation.register(
                    screen_name, lambda parent: self._create_statistics(parent)
                )
            elif screen_name == "exams":
                self.navigation.register(
                    screen_name, lambda parent: self._create_exams(parent)
                )
            elif screen_name == "quiz_battle":
                self.navigation.register(
                    screen_name, lambda parent: self._create_quiz_battle(parent)
                )
            elif screen_name == "custom_tasks":
                self.navigation.register(
                    screen_name, lambda parent: self._create_custom_tasks(parent)
                )
            elif screen_name == "flashcards":
                self.navigation.register(
                    screen_name, lambda parent: self._create_flashcards(parent)
                )
            elif screen_name == "assistant":
                self.navigation.register(
                    screen_name, lambda parent: self._create_assistant(parent)
                )
            elif screen_name == "achievements":
                self.navigation.register(
                    screen_name, lambda parent: self._create_achievements(parent)
                )
            else:
                self.navigation.register(
                    screen_name,
                    lambda parent, title=label: SectionScreen(parent, title),
                )
        self.navigation.navigate("auth")
        self.theme_manager.apply(self.user_preferences)
        self.bind("<Configure>", self._on_resize)

    def _navigate(self, screen_name: str) -> None:
        if self.current_user is None and screen_name != "auth":
            self.navigation.navigate("auth")
            return
        self.navigation.navigate(screen_name)
        if self.current_user is not None:
            self.theme_manager.apply(self.user_preferences)

    def _create_home(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        if self.current_user is None:
            return AuthScreen(parent, self.auth, self._on_authenticated)
        return HomeScreen(
            parent,
            self.settings,
            self._navigate,
            self.current_user,
            self.profiles,
        )

    def _create_profile(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        if self.current_user is None:
            return AuthScreen(parent, self.auth, self._on_authenticated)
        return ProfileScreen(
            parent,
            self.current_user,
            self.auth,
            self.profiles,
            self._logout,
            self._on_account_deleted,
            self._on_profile_updated,
            self._create_backup,
            self._restore_backup,
            self.gamification,
            self._on_username_updated,
        )

    def _create_settings(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        if self.current_user is None:
            return AuthScreen(parent, self.auth, self._on_authenticated)
        return SettingsScreen(
            parent,
            self.current_user,
            self.settings_manager,
            self.theme_manager,
            self.backup_manager,
            self._create_profile,
            self._logout,
            self._apply_user_settings,
            self.settings.version,
        )

    def _create_backup(self) -> str:
        return str(self.backups.create_backup())

    def _restore_backup(self, backup_path: str) -> str:
        safety_path = self.backups.restore_backup(Path(backup_path))
        return str(safety_path)

    def _create_learning(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        if self.current_user is None:
            return AuthScreen(parent, self.auth, self._on_authenticated)
        initial_topic = self._recommended_topic
        catalog_topic_id = self._recommended_library_topic_id
        self._recommended_topic = None
        self._recommended_library_topic_id = None
        return LearningScreen(
            parent,
            self.current_user.id,
            self.learning,
            self._on_gamification_update,
            initial_topic,
            catalog_topic_id,
            self.user_preferences,
        )

    def _create_topic_library(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        if self.current_user is None:
            return AuthScreen(parent, self.auth, self._on_authenticated)
        return TopicLibraryScreen(
            parent,
            self.current_user.id,
            self.topic_library,
            self._practice_library_topic,
            self.educational_content,
        )

    def _practice_library_topic(self, topic: LibraryTopic) -> None:
        self._recommended_topic = topic.exercise_topic
        self._recommended_library_topic_id = topic.id
        self.navigation.navigate("learning")
        self.theme_manager.apply(self.user_preferences)
        self._schedule_reminders()

    def _create_statistics(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        if self.current_user is None:
            return AuthScreen(parent, self.auth, self._on_authenticated)
        return StatisticsScreen(
            parent,
            self.current_user.id,
            self.statistics,
            self._practice_topic,
        )

    def _create_exams(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        if self.current_user is None:
            return AuthScreen(parent, self.auth, self._on_authenticated)
        return ExamScreen(
            parent,
            self.current_user.id,
            self.exams,
            self._on_gamification_update,
        )

    def _create_quiz_battle(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        if self.current_user is None:
            return AuthScreen(parent, self.auth, self._on_authenticated)
        return QuizBattleScreen(
            parent,
            self.current_user.id,
            self.current_user.display_name,
            self.quiz_battle,
            server_url=self.settings.quiz_battle_url,
            server_token=self.settings.quiz_battle_token,
        )

    def _create_custom_tasks(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        if self.current_user is None:
            return AuthScreen(parent, self.auth, self._on_authenticated)
        return CustomTaskScreen(
            parent,
            self.current_user.id,
            self.custom_tasks,
            self._on_gamification_update,
        )

    def _create_flashcards(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        if self.current_user is None:
            return AuthScreen(parent, self.auth, self._on_authenticated)
        return FlashcardScreen(
            parent,
            self.current_user.id,
            self.flashcards,
            self._on_gamification_update,
        )

    def _create_assistant(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        if self.current_user is None:
            return AuthScreen(parent, self.auth, self._on_authenticated)
        return MathAssistantScreen(parent, self.math_assistant)

    def _practice_topic(self, topic: Topic) -> None:
        self._recommended_topic = topic
        self.navigation.navigate("learning")

    def _create_ranking(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        if self.current_user is None:
            return AuthScreen(parent, self.auth, self._on_authenticated)
        return RankingScreen(parent, self.gamification, self.current_user.id)

    def _create_achievements(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        if self.current_user is None:
            return AuthScreen(parent, self.auth, self._on_authenticated)
        return AchievementsScreen(parent, self.gamification, self.current_user.id)

    def _on_authenticated(self, user: User) -> None:
        self.current_user = user
        self.sidebar.set_user(user.display_name, user.username)
        try:
            self.user_preferences = self.settings_manager.get_settings(user.id)
            self.theme_manager.apply(self.user_preferences)
        except SettingsStorageError as error:
            self.error_handler.handle(error, "Wczytywanie ustawień użytkownika")
            return
        self._refresh_gamification(user.id)
        self.navigation.navigate("home")
        self.theme_manager.apply(self.user_preferences)
        self._schedule_reminders()

    def _on_gamification_update(self) -> None:
        if self.current_user is not None:
            self._refresh_gamification(self.current_user.id)

    def _refresh_gamification(self, user_id: int) -> None:
        try:
            progress = self.gamification.get_level_progress(user_id)
            notifications = self.gamification.claim_pending_achievement_notifications(
                user_id
            )
        except RuntimeError as error:
            self.error_handler.handle(error, "Odczyt postępu grywalizacji")
            return
        self.sidebar.set_progress(progress.level, progress.xp)
        if notifications:
            self._show_achievement_notification(notifications)

    def _show_achievement_notification(
        self, achievements: tuple[UnlockedAchievement, ...]
    ) -> None:
        if not self.user_preferences.get("notifications_enabled", True):
            return
        titles = "\n".join(
            f"{item.icon} {item.title}"
            for item in achievements
        )
        notice = ctk.CTkToplevel(self)
        notice.title("Nowe osiągnięcie")
        notice.geometry("360x170")
        notice.resizable(False, False)
        notice.transient(self)
        notice.attributes("-topmost", True)
        ctk.CTkLabel(
            notice,
            text="Osiągnięcie odblokowane!",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLORS["text"],
        ).pack(padx=18, pady=(18, 8))
        ctk.CTkLabel(
            notice, text=titles, justify="center", text_color=COLORS["accent"],
        ).pack(padx=16, pady=(0, 12), expand=True)
        ctk.CTkButton(
            notice, text="Świetnie", command=notice.destroy,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
        ).pack(padx=18, pady=(0, 16))
        notice.after(7000, lambda: notice.destroy() if notice.winfo_exists() else None)
        self._fade_in(notice)

    def _apply_user_settings(self, preferences: dict[str, object]) -> None:
        self.user_preferences = preferences
        self.theme_manager.apply(preferences)
        self._schedule_reminders()

    def _schedule_reminders(self) -> None:
        if self._reminder_after_id is not None:
            try:
                self.after_cancel(self._reminder_after_id)
            except tk.TclError:
                pass
            self._reminder_after_id = None
        if self.current_user is not None:
            self._reminder_after_id = self.after(0, self._check_reminders)

    def _check_reminders(self) -> None:
        self._reminder_after_id = None
        user = self.current_user
        if user is None:
            return
        preferences = self.user_preferences
        now = datetime.now().astimezone()
        if (
            preferences.get("notifications_enabled")
            and now.weekday() in preferences.get("reminder_days", [])
            and now.strftime("%H:%M") == preferences.get("reminder_time")
        ):
            day_key = now.date().isoformat()
            if preferences.get("study_reminders"):
                self._notify_once(user.id, day_key, "study", "Czas na zaplanowaną sesję nauki.")
            if preferences.get("daily_goal_reminders"):
                self._check_daily_goal(user.id, day_key)
            if preferences.get("flashcard_reminders"):
                self._check_due_flashcards(user.id, day_key)
        self._reminder_after_id = self.after(30000, self._check_reminders)

    def _check_daily_goal(self, user_id: int, day_key: str) -> None:
        try:
            profile = self.profiles.get_profile(user_id)
            with self.database.transaction() as connection:
                row = connection.execute(
                    """
                    SELECT COALESCE(SUM(duration_seconds), 0) AS seconds
                    FROM exercise_history
                    WHERE user_id = ? AND date(completed_at) = date('now', 'localtime')
                    """,
                    (user_id,),
                ).fetchone()
            minutes = int(row["seconds"]) // 60
            if minutes < profile.daily_goal_minutes:
                self._notify_once(
                    user_id, day_key, "goal",
                    f"Do dziennego celu nauki brakuje {profile.daily_goal_minutes - minutes} min.",
                )
        except (RuntimeError, ValueError) as error:
            self.error_handler.handle(error, "Sprawdzanie dziennego celu")

    def _check_due_flashcards(self, user_id: int, day_key: str) -> None:
        try:
            due_count = self.flashcards.get_stats(user_id).due_cards
            if due_count:
                self._notify_once(
                    user_id, day_key, "flashcards",
                    f"Masz {due_count} fiszek oczekujących na powtórkę.",
                )
        except (RuntimeError, ValueError) as error:
            self.error_handler.handle(error, "Sprawdzanie powtórek fiszek")

    def _notify_once(self, user_id: int, day_key: str, kind: str, text: str) -> None:
        key = (user_id, day_key, kind)
        if key in self._sent_reminders:
            return
        self._sent_reminders.add(key)
        self._show_reminder_notification(text)

    def _show_reminder_notification(self, text: str) -> None:
        notice = ctk.CTkToplevel(self)
        notice.title("MathMaster — przypomnienie")
        notice.geometry("370x145")
        notice.resizable(False, False)
        notice.transient(self)
        notice.attributes("-topmost", True)
        notice.configure(fg_color=COLORS["card"])
        ctk.CTkLabel(
            notice, text="Przypomnienie o nauce", anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=COLORS["text"],
        ).pack(fill="x", padx=18, pady=(17, 7))
        ctk.CTkLabel(
            notice, text=text, anchor="w", justify="left", wraplength=330,
            text_color=COLORS["muted"],
        ).pack(fill="x", padx=18, pady=(0, 10))
        ctk.CTkButton(notice, text="OK", command=notice.destroy).pack(
            anchor="e", padx=18, pady=(0, 14)
        )
        notice.after(9000, lambda: notice.destroy() if notice.winfo_exists() else None)
        self._fade_in(notice)

    def _fade_in(self, window: ctk.CTkToplevel) -> None:
        if (
            not self.user_preferences.get("animations_enabled", True)
            or self.user_preferences.get("reduce_animations")
        ):
            return
        try:
            window.attributes("-alpha", 0.1)
        except tk.TclError:
            return

        def step(alpha: float = 0.1) -> None:
            if not window.winfo_exists():
                return
            alpha = min(1.0, alpha + 0.18)
            try:
                window.attributes("-alpha", alpha)
            except tk.TclError:
                return
            if alpha < 1:
                window.after(25, step, alpha)

        window.after(0, step)

    def _on_profile_updated(self, display_name: str) -> None:
        if self.current_user is not None:
            self.current_user = User(
                self.current_user.id, self.current_user.username, display_name
            )
            self.sidebar.set_user(display_name, self.current_user.username)

    def _on_username_updated(self, username: str) -> None:
        if self.current_user is not None:
            self.current_user = User(
                self.current_user.id, username, self.current_user.display_name
            )
            self.sidebar.set_user(self.current_user.display_name, username)

    def _logout(self) -> None:
        self.quiz_battle.close()
        self.current_user = None
        self.user_preferences = dict(DEFAULT_SETTINGS)
        self.theme_manager.apply(self.user_preferences)
        self._schedule_reminders()
        self.sidebar.set_user(None, None)
        self.navigation.navigate("auth")

    def _on_account_deleted(self) -> None:
        self._logout()

    def _on_resize(self, event: object) -> None:
        if getattr(event, "widget", None) is self:
            self.sidebar.set_compact(self.winfo_width() < 980)

    def _on_close(self) -> None:
        if self._reminder_after_id is not None:
            try:
                self.after_cancel(self._reminder_after_id)
            except tk.TclError:
                pass
        try:
            self.quiz_battle.close()
        except Exception as error:
            self.error_handler.handle(error, "Rozłączanie Quiz Battle")
        try:
            self.database.close()
        except Exception as error:
            self.error_handler.handle(error, "Zamykanie bazy danych")
        self.destroy()