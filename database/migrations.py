from __future__ import annotations

import sqlite3

from gamification.catalog import ACHIEVEMENTS

CURRENT_SCHEMA_VERSION = 15


def apply_migrations(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version > CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Baza danych ma nowszą wersję schematu ({version}) niż aplikacja "
            f"({CURRENT_SCHEMA_VERSION})."
        )
    with connection:
        connection.execute("BEGIN")
        if version < 1:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute("PRAGMA user_version = 1")
        if version < 2:
            statements = (
                """CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )""",
                """CREATE TABLE user_progress (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    xp INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
                    level INTEGER NOT NULL DEFAULT 1 CHECK (level >= 1),
                    daily_goal_minutes INTEGER NOT NULL DEFAULT 20 CHECK (daily_goal_minutes > 0),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )""",
                """CREATE TABLE exercise_history (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    topic TEXT NOT NULL,
                    correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
                    duration_seconds INTEGER NOT NULL DEFAULT 0 CHECK (duration_seconds >= 0),
                    completed_at TEXT NOT NULL DEFAULT (datetime('now'))
                )""",
                """CREATE TABLE achievements (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL
                )""",
                """CREATE TABLE user_achievements (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    achievement_id INTEGER NOT NULL REFERENCES achievements(id) ON DELETE CASCADE,
                    unlocked_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (user_id, achievement_id)
                )""",
                """CREATE TABLE study_plans (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    target_date TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )""",
                """CREATE TABLE flashcards (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    front TEXT NOT NULL,
                    back TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )""",
                """CREATE TABLE exam_results (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    exam_name TEXT NOT NULL,
                    score REAL NOT NULL CHECK (score >= 0),
                    completed_at TEXT NOT NULL DEFAULT (datetime('now'))
                )""",
                "CREATE INDEX exercise_history_user_date ON exercise_history(user_id, completed_at)",
                "CREATE INDEX exam_results_user_date ON exam_results(user_id, completed_at)",
            )
            for statement in statements:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 2")
        if version < 3:
            connection.execute(
                "ALTER TABLE exercise_history ADD COLUMN difficulty INTEGER NOT NULL DEFAULT 1"
            )
            connection.execute(
                "ALTER TABLE exercise_history ADD COLUMN question TEXT NOT NULL DEFAULT ''"
            )
            connection.execute(
                "ALTER TABLE exercise_history ADD COLUMN submitted_answer TEXT NOT NULL DEFAULT ''"
            )
            connection.execute(
                "ALTER TABLE exercise_history ADD COLUMN correct_answer TEXT NOT NULL DEFAULT ''"
            )
            connection.execute(
                "ALTER TABLE exercise_history ADD COLUMN solution TEXT NOT NULL DEFAULT ''"
            )
            connection.execute(
                "ALTER TABLE exercise_history ADD COLUMN session_id TEXT NOT NULL DEFAULT ''"
            )
            connection.execute(
                "CREATE INDEX exercise_history_session ON exercise_history(user_id, session_id)"
            )
            connection.execute("PRAGMA user_version = 3")
        if version < 4:
            connection.execute(
                "ALTER TABLE achievements ADD COLUMN reward_xp INTEGER NOT NULL DEFAULT 0"
            )
            connection.execute(
                "ALTER TABLE exam_results ADD COLUMN difficulty INTEGER NOT NULL DEFAULT 1"
            )
            connection.execute(
                "ALTER TABLE exam_results ADD COLUMN passed INTEGER NOT NULL DEFAULT 0"
            )
            connection.execute(
                "ALTER TABLE exam_results ADD COLUMN attempt_key TEXT NOT NULL DEFAULT ''"
            )
            connection.execute(
                "CREATE UNIQUE INDEX exam_results_attempt_key "
                "ON exam_results(user_id, attempt_key) WHERE attempt_key <> ''"
            )
            connection.execute(
                """
                CREATE TABLE xp_transactions (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    source_key TEXT NOT NULL,
                    amount INTEGER NOT NULL CHECK (amount > 0),
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(user_id, source_key)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE topic_completions (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    topic TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (user_id, topic)
                )
                """
            )
            for achievement in ACHIEVEMENTS:
                connection.execute(
                    """
                    INSERT INTO achievements (name, description, reward_xp)
                    VALUES (?, ?, ?)
                    """,
                    (
                        achievement.key,
                        achievement.description,
                        achievement.reward_xp,
                    ),
                )
            connection.execute("PRAGMA user_version = 4")
        if version < 5:
            for statement in (
                "ALTER TABLE exam_results ADD COLUMN subject TEXT NOT NULL DEFAULT 'Matematyka'",
                "ALTER TABLE exam_results ADD COLUMN category TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE exam_results ADD COLUMN question_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE exam_results ADD COLUMN correct_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE exam_results ADD COLUMN duration_seconds INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE exam_results ADD COLUMN time_limit_seconds INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE exam_results ADD COLUMN grade INTEGER NOT NULL DEFAULT 1",
                "ALTER TABLE exam_results ADD COLUMN grade_scale TEXT NOT NULL DEFAULT ''",
                """
                CREATE TABLE exam_answer_details (
                    exam_id INTEGER NOT NULL REFERENCES exam_results(id) ON DELETE CASCADE,
                    question_number INTEGER NOT NULL CHECK (question_number > 0),
                    topic TEXT NOT NULL,
                    question TEXT NOT NULL,
                    submitted_answer TEXT NOT NULL DEFAULT '',
                    correct_answer TEXT NOT NULL,
                    solution TEXT NOT NULL,
                    correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
                    marked_for_review INTEGER NOT NULL DEFAULT 0
                        CHECK (marked_for_review IN (0, 1)),
                    PRIMARY KEY (exam_id, question_number)
                )
                """,
                "CREATE INDEX exam_results_user_category "
                "ON exam_results(user_id, subject, category, completed_at)",
            ):
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 5")
        if version < 6:
            connection.execute(
                """
                CREATE TABLE learning_topic_status (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    topic_id TEXT NOT NULL,
                    status TEXT NOT NULL
                        CHECK (status IN ('unmastered', 'started', 'mastered')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (user_id, topic_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE custom_learning_topics (
                    topic_id TEXT PRIMARY KEY,
                    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    division TEXT NOT NULL,
                    subdivision TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    difficulty INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
                    theory_json TEXT NOT NULL,
                    examples_json TEXT NOT NULL,
                    subtopics_json TEXT NOT NULL,
                    exercise_topic TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            connection.execute(
                "CREATE INDEX custom_learning_topics_owner ON custom_learning_topics(owner_id)"
            )
            connection.execute("PRAGMA user_version = 6")
        if version < 7:
            connection.execute(
                "ALTER TABLE exercise_history ADD COLUMN catalog_topic_id TEXT NOT NULL DEFAULT ''"
            )
            connection.execute(
                "CREATE INDEX exercise_history_catalog_topic "
                "ON exercise_history(user_id, catalog_topic_id)"
            )
            connection.execute("PRAGMA user_version = 7")
        if version < 8:
            connection.execute(
                """
                CREATE TABLE flashcard_decks (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(user_id, name)
                )
                """
            )
            for statement in (
                "ALTER TABLE flashcards ADD COLUMN deck_id INTEGER REFERENCES flashcard_decks(id) ON DELETE SET NULL",
                "ALTER TABLE flashcards ADD COLUMN division TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE flashcards ADD COLUMN topic_id TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE flashcards ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1))",
                "ALTER TABLE flashcards ADD COLUMN repetitions INTEGER NOT NULL DEFAULT 0 CHECK (repetitions >= 0)",
                "ALTER TABLE flashcards ADD COLUMN last_reviewed_at TEXT",
                "ALTER TABLE flashcards ADD COLUMN next_review_at TEXT",
                "ALTER TABLE flashcards ADD COLUMN mastery INTEGER NOT NULL DEFAULT 0 CHECK (mastery BETWEEN 0 AND 5)",
                "ALTER TABLE flashcards ADD COLUMN interval_days REAL NOT NULL DEFAULT 0 CHECK (interval_days >= 0)",
                "ALTER TABLE flashcards ADD COLUMN ease_factor REAL DEFAULT 2.5 CHECK (ease_factor IS NOT NULL AND ease_factor >= 1.3)",
                "ALTER TABLE flashcards ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''",
                "CREATE INDEX flashcards_user_review ON flashcards(user_id, next_review_at)",
                "CREATE INDEX flashcards_user_deck ON flashcards(user_id, deck_id)",
                """
                CREATE TABLE flashcard_reviews (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    flashcard_id INTEGER NOT NULL REFERENCES flashcards(id) ON DELETE CASCADE,
                    rating TEXT NOT NULL CHECK (rating IN ('again', 'hard', 'know', 'easy')),
                    correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
                    reviewed_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """,
                "CREATE INDEX flashcard_reviews_user_date ON flashcard_reviews(user_id, reviewed_at)",
                """
                CREATE TABLE flashcard_settings (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    daily_goal INTEGER NOT NULL DEFAULT 10 CHECK (daily_goal BETWEEN 1 AND 500)
                )
                """,
            ):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO flashcard_decks (user_id, name) "
                "SELECT DISTINCT user_id, 'Moje fiszki' FROM flashcards"
            )
            connection.execute(
                """
                UPDATE flashcards
                SET deck_id = (
                    SELECT id FROM flashcard_decks
                    WHERE flashcard_decks.user_id = flashcards.user_id
                      AND flashcard_decks.name = 'Moje fiszki'
                ),
                next_review_at = COALESCE(next_review_at, datetime('now')),
                updated_at = datetime('now')
                """
            )
            connection.execute(
                "INSERT INTO flashcard_settings (user_id) SELECT id FROM users"
            )
            connection.execute("PRAGMA user_version = 8")
        if version < 9:
            connection.execute(
                "ALTER TABLE flashcard_reviews ADD COLUMN next_review_at TEXT NOT NULL DEFAULT ''"
            )
            connection.execute(
                "ALTER TABLE flashcard_reviews ADD COLUMN mastery INTEGER NOT NULL DEFAULT 0 "
                "CHECK (mastery BETWEEN 0 AND 5)"
            )
            connection.execute(
                """
                UPDATE flashcard_reviews
                SET next_review_at = COALESCE(
                    (SELECT next_review_at FROM flashcards
                     WHERE flashcards.id = flashcard_reviews.flashcard_id), ''
                ),
                mastery = COALESCE(
                    (SELECT mastery FROM flashcards
                     WHERE flashcards.id = flashcard_reviews.flashcard_id), 0
                )
                """
            )
            connection.execute("PRAGMA user_version = 9")
        if version < 10:
            connection.execute(
                """
                CREATE TABLE custom_task_sets (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source_kind TEXT NOT NULL CHECK (
                        source_kind IN ('manual', 'file', 'url')
                    ),
                    source TEXT NOT NULL DEFAULT '',
                    source_url TEXT NOT NULL DEFAULT '',
                    downloaded_at TEXT,
                    content_hash TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(user_id, name),
                    UNIQUE(user_id, content_hash)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE user_custom_tasks (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    set_id INTEGER NOT NULL REFERENCES custom_task_sets(id) ON DELETE CASCADE,
                    external_id TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    name TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    category TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    difficulty INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
                    xp_points INTEGER NOT NULL CHECK (xp_points BETWEEN 0 AND 1000),
                    hints_json TEXT NOT NULL DEFAULT '[]',
                    choices_json TEXT NOT NULL DEFAULT '[]',
                    source_label TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(user_id, fingerprint)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE custom_task_attempts (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    task_id INTEGER REFERENCES user_custom_tasks(id) ON DELETE SET NULL,
                    task_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    question TEXT NOT NULL,
                    submitted_answer TEXT NOT NULL,
                    correct_answer TEXT NOT NULL,
                    correct INTEGER NOT NULL CHECK (correct IN (0, 1)),
                    xp_awarded INTEGER NOT NULL DEFAULT 0 CHECK (xp_awarded >= 0),
                    source_label TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            connection.execute(
                "CREATE INDEX user_custom_tasks_user_category "
                "ON user_custom_tasks(user_id, category, topic)"
            )
            connection.execute(
                "CREATE INDEX custom_task_attempts_user_date "
                "ON custom_task_attempts(user_id, completed_at)"
            )
            connection.execute(
                "ALTER TABLE exercise_history ADD COLUMN custom_task_id INTEGER "
                "REFERENCES user_custom_tasks(id) ON DELETE SET NULL"
            )
            connection.execute("PRAGMA user_version = 10")
        if version < 11:
            for statement in (
                """
                CREATE TABLE IF NOT EXISTS achievements (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    description TEXT NOT NULL,
                    reward_xp INTEGER NOT NULL DEFAULT 0
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS user_achievements (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    achievement_id INTEGER NOT NULL REFERENCES achievements(id) ON DELETE CASCADE,
                    unlocked_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (user_id, achievement_id)
                )
                """,
                "ALTER TABLE achievements ADD COLUMN category TEXT NOT NULL DEFAULT 'Pierwsze kroki'",
                "ALTER TABLE achievements ADD COLUMN rarity TEXT NOT NULL DEFAULT 'Zwykłe'",
                "ALTER TABLE achievements ADD COLUMN icon TEXT NOT NULL DEFAULT '🏅'",
                "ALTER TABLE achievements ADD COLUMN badge_key TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE achievements ADD COLUMN avatar_frame_key TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE user_achievements ADD COLUMN notified_at TEXT",
                "ALTER TABLE flashcard_reviews ADD COLUMN deck_id INTEGER",
                "ALTER TABLE flashcard_reviews ADD COLUMN deck_name TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE flashcard_reviews ADD COLUMN tested INTEGER NOT NULL DEFAULT 0 CHECK (tested IN (0, 1))",
                "ALTER TABLE flashcard_reviews ADD COLUMN test_session_id TEXT NOT NULL DEFAULT ''",
                "CREATE INDEX flashcard_reviews_user_deck_session "
                "ON flashcard_reviews(user_id, deck_id, test_session_id)",
                """
                CREATE TABLE achievement_progress (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    achievement_id INTEGER NOT NULL REFERENCES achievements(id) ON DELETE CASCADE,
                    progress_value REAL NOT NULL DEFAULT 0 CHECK (progress_value >= 0),
                    progress_target REAL NOT NULL DEFAULT 1 CHECK (progress_target > 0),
                    progress_text TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (user_id, achievement_id)
                )
                """,
                """
                CREATE TABLE user_cosmetics (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    cosmetic_type TEXT NOT NULL CHECK (
                        cosmetic_type IN ('badge', 'avatar_frame')
                    ),
                    cosmetic_key TEXT NOT NULL,
                    unlocked_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (user_id, cosmetic_type, cosmetic_key)
                )
                """,
                """
                CREATE TABLE user_equipped_cosmetics (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    cosmetic_type TEXT NOT NULL CHECK (
                        cosmetic_type IN ('badge', 'avatar_frame')
                    ),
                    cosmetic_key TEXT NOT NULL,
                    equipped_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (user_id, cosmetic_type),
                    FOREIGN KEY (user_id, cosmetic_type, cosmetic_key)
                        REFERENCES user_cosmetics(user_id, cosmetic_type, cosmetic_key)
                        ON DELETE CASCADE
                )
                """,
                """
                CREATE TABLE quiz_battle_results (
                    battle_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    outcome TEXT NOT NULL CHECK (outcome IN ('win', 'loss')),
                    mistakes INTEGER NOT NULL CHECK (mistakes BETWEEN 0 AND 100),
                    difficulty TEXT NOT NULL CHECK (
                        difficulty IN ('easy', 'medium', 'hard', 'expert')
                    ),
                    completed_at TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    verified_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """,
                "CREATE INDEX quiz_battle_results_user_date "
                "ON quiz_battle_results(user_id, completed_at)",
            ):
                connection.execute(statement)
            connection.execute(
                "UPDATE user_achievements SET notified_at = unlocked_at "
                "WHERE notified_at IS NULL"
            )
            for achievement in ACHIEVEMENTS:
                connection.execute(
                    """
                    INSERT INTO achievements (
                        name, description, reward_xp, category, rarity, icon,
                        badge_key, avatar_frame_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        description = excluded.description,
                        reward_xp = excluded.reward_xp,
                        category = excluded.category,
                        rarity = excluded.rarity,
                        icon = excluded.icon,
                        badge_key = excluded.badge_key,
                        avatar_frame_key = excluded.avatar_frame_key
                    """,
                    (
                        achievement.key,
                        achievement.description,
                        achievement.reward_xp,
                        achievement.category,
                        achievement.rarity,
                        achievement.icon,
                        achievement.badge_key,
                        achievement.avatar_frame_key or "",
                    ),
                )
            connection.execute("PRAGMA user_version = 11")
        if version < 12:
            for statement in (
                "ALTER TABLE quiz_battle_results ADD COLUMN player_id TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE quiz_battle_results ADD COLUMN mode TEXT NOT NULL DEFAULT 'race'",
                "ALTER TABLE quiz_battle_results ADD COLUMN room_code TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE quiz_battle_results ADD COLUMN points INTEGER NOT NULL DEFAULT 0 CHECK (points >= 0)",
                "ALTER TABLE quiz_battle_results ADD COLUMN correct_answers INTEGER NOT NULL DEFAULT 0 CHECK (correct_answers >= 0)",
                "ALTER TABLE quiz_battle_results ADD COLUMN place INTEGER NOT NULL DEFAULT 1 CHECK (place BETWEEN 1 AND 8)",
                "ALTER TABLE quiz_battle_results ADD COLUMN player_count INTEGER NOT NULL DEFAULT 2 CHECK (player_count BETWEEN 2 AND 8)",
                "ALTER TABLE quiz_battle_results ADD COLUMN duration_seconds INTEGER NOT NULL DEFAULT 0 CHECK (duration_seconds >= 0)",
                "ALTER TABLE quiz_battle_results ADD COLUMN standings_json TEXT NOT NULL DEFAULT '[]'",
                "ALTER TABLE quiz_battle_results ADD COLUMN xp_awarded INTEGER NOT NULL DEFAULT 0 CHECK (xp_awarded >= 0)",
                "CREATE INDEX quiz_battle_results_user_points "
                "ON quiz_battle_results(user_id, points DESC, completed_at)",
            ):
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 12")
        if version < 13:
            connection.execute(
                """
                CREATE TABLE user_settings (
                    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    settings_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            connection.execute("PRAGMA user_version = 13")
        if version < 14:
            for statement in (
                """
                CREATE TABLE content_versions (
                    pack_id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL CHECK (version > 0),
                    digest TEXT NOT NULL,
                    imported_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE content_topics (
                    topic_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    division TEXT NOT NULL,
                    subdivision TEXT NOT NULL,
                    description TEXT NOT NULL,
                    educational_level TEXT NOT NULL,
                    difficulty INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
                    material_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version > 0),
                    digest TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE bank_tasks (
                    task_id TEXT PRIMARY KEY,
                    topic_id TEXT NOT NULL REFERENCES content_topics(topic_id) ON DELETE CASCADE,
                    category TEXT NOT NULL,
                    subtopic TEXT NOT NULL,
                    educational_level TEXT NOT NULL,
                    difficulty INTEGER NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
                    prompt TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    solution TEXT NOT NULL,
                    hint TEXT NOT NULL,
                    points INTEGER NOT NULL CHECK (points BETWEEN 1 AND 100),
                    source TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version > 0),
                    generator_id TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    pack_digest TEXT NOT NULL,
                    UNIQUE(topic_id, difficulty, prompt)
                )
                """,
                "CREATE INDEX bank_tasks_topic_difficulty ON bank_tasks(topic_id, difficulty)",
                """
                CREATE TABLE content_exams (
                    exam_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    educational_level TEXT NOT NULL,
                    time_limit_seconds INTEGER NOT NULL CHECK (time_limit_seconds BETWEEN 60 AND 10800),
                    task_ids_json TEXT NOT NULL,
                    max_points INTEGER NOT NULL CHECK (max_points > 0),
                    pass_percent INTEGER NOT NULL CHECK (pass_percent BETWEEN 1 AND 100),
                    source TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version > 0),
                    pack_digest TEXT NOT NULL
                )
                """,
            ):
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 14")
        if version < 15:
            for statement in (
                "ALTER TABLE exercise_history ADD COLUMN bank_task_id TEXT",
                "ALTER TABLE exercise_history ADD COLUMN generator_id TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE exercise_history ADD COLUMN generator_parameters_json TEXT NOT NULL DEFAULT '{}'",
            ):
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 15")