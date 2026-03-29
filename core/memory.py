"""
Память бота — SQLite база данных
Хранит: сообщения, факты о юзерах, лимиты, платежи
Каждый бот — своя база в папке bots/bot_xxx/
"""

import sqlite3
import logging
import threading
from pathlib import Path

logger = logging.getLogger("memory")


class Memory:
    """Управляет памятью одного бота"""

    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self.bot_dir = Path(__file__).parent.parent / "bots" / f"bot_{bot_id}"
        self.bot_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.bot_dir / "memory.db"
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Создаёт подключение к базе"""
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self):
        """Создаёт таблицы если их нет"""
        try:
            conn = self._connect()
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id     INTEGER NOT NULL,
                    user_id     INTEGER,
                    role        TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    timestamp   TEXT DEFAULT (datetime('now'))
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_facts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    fact        TEXT NOT NULL,
                    source      TEXT DEFAULT 'auto',
                    timestamp   TEXT DEFAULT (datetime('now'))
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_limits (
                    user_id         INTEGER PRIMARY KEY,
                    messages_used   INTEGER DEFAULT 0,
                    messages_bought INTEGER DEFAULT 0,
                    is_vip          INTEGER DEFAULT 0,
                    first_seen      TEXT DEFAULT (datetime('now')),
                    last_seen       TEXT DEFAULT (datetime('now'))
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    amount      INTEGER NOT NULL,
                    currency    TEXT DEFAULT 'XTR',
                    messages    INTEGER NOT NULL,
                    source      TEXT DEFAULT 'telegram',
                    timestamp   TEXT DEFAULT (datetime('now'))
                )
            """)

            # индексы для ускорения
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_user ON messages(user_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_facts_user ON user_facts(user_id)"
            )

            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error(f"Memory init error {self.bot_id}: {e}")
            raise

    def _execute(self, query: str, params: tuple = (), fetch: str = None):
        """
        Безопасное выполнение SQL с автозакрытием и блокировкой.
        fetch: None, 'one', 'all'
        """
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.execute(query, params)

                if fetch == 'one':
                    result = cursor.fetchone()
                elif fetch == 'all':
                    result = cursor.fetchall()
                else:
                    result = cursor

                conn.commit()
                return result
            except sqlite3.Error as e:
                logger.error(f"SQL error {self.bot_id}: {e} | query: {query[:100]}")
                if conn:
                    conn.rollback()
                raise
            finally:
                if conn:
                    conn.close()

    def _execute_many(self, queries: list):
        """Выполняет несколько запросов в одной транзакции"""
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                for query, params in queries:
                    conn.execute(query, params)
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"SQL batch error {self.bot_id}: {e}")
                if conn:
                    conn.rollback()
                raise
            finally:
                if conn:
                    conn.close()

    # ====================================================
    # СООБЩЕНИЯ
    # ====================================================

    def save_message(self, chat_id: int, user_id: int, role: str, content: str):
        """Сохраняет сообщение в историю"""
        if not content:
            return
        self._execute(
            "INSERT INTO messages (chat_id, user_id, role, content) VALUES (?, ?, ?, ?)",
            (chat_id, user_id, role, content[:50000])  # лимит на размер
        )

    def get_history(self, chat_id: int, limit: int = 20) -> list:
        """Возвращает последние N сообщений чата"""
        limit = max(1, min(500, limit))
        rows = self._execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit), fetch='all'
        )
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def get_history_with_index(self, chat_id: int, limit: int = 500) -> list:
        """Возвращает историю с ID сообщений (для удаления)"""
        limit = max(1, min(5000, limit))
        rows = self._execute(
            "SELECT id, role, content, timestamp FROM messages "
            "WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit), fetch='all'
        )
        return [
            {
                "msg_id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "timestamp": r["timestamp"]
            }
            for r in reversed(rows)
        ]

    def delete_message_by_id(self, msg_id: int) -> bool:
        """Удаляет одно сообщение по его ID"""
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                cursor = conn.execute("DELETE FROM messages WHERE id = ?", (msg_id,))
                conn.commit()
                return cursor.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"Delete message error: {e}")
                return False
            finally:
                if conn:
                    conn.close()

    def delete_messages_by_ids(self, msg_ids: list) -> int:
        """Удаляет несколько сообщений по списку ID"""
        if not msg_ids:
            return 0

        # валидация — только int
        clean_ids = [int(i) for i in msg_ids if isinstance(i, (int, float))]
        if not clean_ids:
            return 0

        with self._lock:
            conn = None
            try:
                conn = self._connect()
                placeholders = ','.join(['?' for _ in clean_ids])
                cursor = conn.execute(
                    f"DELETE FROM messages WHERE id IN ({placeholders})",
                    clean_ids
                )
                conn.commit()
                return cursor.rowcount
            except sqlite3.Error as e:
                logger.error(f"Delete messages error: {e}")
                return 0
            finally:
                if conn:
                    conn.close()

    def clear_history(self, chat_id: int):
        """Очищает историю чата"""
        self._execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))

    def clear_all_history(self):
        """Очищает ВСЮ историю бота"""
        self._execute("DELETE FROM messages")

    def get_message_count(self, chat_id: int) -> int:
        """Сколько сообщений в чате"""
        row = self._execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE chat_id = ?",
            (chat_id,), fetch='one'
        )
        return row["cnt"] if row else 0

    # ====================================================
    # ФАКТЫ О ЮЗЕРЕ
    # ====================================================

    def add_fact(self, user_id: int, fact: str, source: str = "auto"):
        """Добавляет факт о юзере"""
        if not fact or not fact.strip():
            return
        self._execute(
            "INSERT INTO user_facts (user_id, fact, source) VALUES (?, ?, ?)",
            (user_id, fact[:5000], source)
        )

    def get_facts(self, user_id: int) -> list:
        """Все факты о юзере"""
        rows = self._execute(
            "SELECT fact FROM user_facts WHERE user_id = ? ORDER BY id",
            (user_id,), fetch='all'
        )
        return [r["fact"] for r in rows] if rows else []

    def delete_fact(self, fact_id: int):
        """Удаляет конкретный факт"""
        self._execute("DELETE FROM user_facts WHERE id = ?", (fact_id,))

    def clear_facts(self, user_id: int):
        """Удаляет все факты о юзере"""
        self._execute("DELETE FROM user_facts WHERE user_id = ?", (user_id,))

    # ====================================================
    # ЛИМИТЫ И МОНЕТИЗАЦИЯ
    # ====================================================

    def get_or_create_user(self, user_id: int) -> dict:
        """Получает или создаёт юзера"""
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                row = conn.execute(
                    "SELECT * FROM user_limits WHERE user_id = ?",
                    (user_id,)
                ).fetchone()

                if not row:
                    conn.execute(
                        "INSERT INTO user_limits (user_id) VALUES (?)",
                        (user_id,)
                    )
                    conn.commit()
                    row = conn.execute(
                        "SELECT * FROM user_limits WHERE user_id = ?",
                        (user_id,)
                    ).fetchone()

                conn.execute(
                    "UPDATE user_limits SET last_seen = datetime('now') WHERE user_id = ?",
                    (user_id,)
                )
                conn.commit()
                return dict(row)
            except sqlite3.Error as e:
                logger.error(f"get_or_create_user error: {e}")
                return {
                    "user_id": user_id, "messages_used": 0,
                    "messages_bought": 0, "is_vip": 0,
                    "first_seen": "", "last_seen": ""
                }
            finally:
                if conn:
                    conn.close()

    def use_message(self, user_id: int):
        """Засчитывает одно сообщение"""
        self.get_or_create_user(user_id)
        self._execute(
            "UPDATE user_limits SET messages_used = messages_used + 1 WHERE user_id = ?",
            (user_id,)
        )

    def can_send(self, user_id: int, free_limit: int) -> bool:
        """Может ли юзер отправить сообщение"""
        user = self.get_or_create_user(user_id)
        if user["is_vip"]:
            return True
        total_allowed = free_limit + user["messages_bought"]
        return user["messages_used"] < total_allowed

    def get_remaining(self, user_id: int, free_limit: int) -> int:
        """Сколько сообщений осталось"""
        user = self.get_or_create_user(user_id)
        if user["is_vip"]:
            return 999999
        total_allowed = free_limit + user["messages_bought"]
        return max(0, total_allowed - user["messages_used"])

    def add_purchased(self, user_id: int, messages: int, amount: int,
                      source: str = "telegram"):
        """Добавляет купленные сообщения"""
        if messages <= 0:
            return
        self.get_or_create_user(user_id)
        self._execute_many([
            (
                "UPDATE user_limits SET messages_bought = messages_bought + ? WHERE user_id = ?",
                (messages, user_id)
            ),
            (
                "INSERT INTO payments (user_id, amount, messages, source) VALUES (?, ?, ?, ?)",
                (user_id, amount, messages, source)
            ),
        ])

    # ============================
    # VIP
    # ============================

    def set_vip(self, user_id: int, is_vip: bool):
        """Устанавливает/снимает VIP"""
        self.get_or_create_user(user_id)
        self._execute(
            "UPDATE user_limits SET is_vip = ? WHERE user_id = ?",
            (1 if is_vip else 0, user_id)
        )

    def get_all_vip(self) -> list:
        """Список всех VIP"""
        rows = self._execute(
            "SELECT user_id FROM user_limits WHERE is_vip = 1",
            fetch='all'
        )
        return [r["user_id"] for r in rows] if rows else []

    # ============================
    # СТАТИСТИКА
    # ============================

    def get_stats(self) -> dict:
        """Общая статистика бота"""
        with self._lock:
            conn = None
            try:
                conn = self._connect()
                total_users = conn.execute(
                    "SELECT COUNT(*) as cnt FROM user_limits"
                ).fetchone()["cnt"]
                total_messages = conn.execute(
                    "SELECT COUNT(*) as cnt FROM messages"
                ).fetchone()["cnt"]
                paying_users = conn.execute(
                    "SELECT COUNT(*) as cnt FROM user_limits WHERE messages_bought > 0"
                ).fetchone()["cnt"]
                total_revenue = conn.execute(
                    "SELECT COALESCE(SUM(amount), 0) as total FROM payments"
                ).fetchone()["total"]
                vip_count = conn.execute(
                    "SELECT COUNT(*) as cnt FROM user_limits WHERE is_vip = 1"
                ).fetchone()["cnt"]

                return {
                    "total_users": total_users,
                    "total_messages": total_messages,
                    "paying_users": paying_users,
                    "total_revenue_stars": total_revenue,
                    "vip_count": vip_count
                }
            except sqlite3.Error as e:
                logger.error(f"Stats error {self.bot_id}: {e}")
                return {
                    "total_users": 0, "total_messages": 0,
                    "paying_users": 0, "total_revenue_stars": 0,
                    "vip_count": 0
                }
            finally:
                if conn:
                    conn.close()

    def get_all_users(self) -> list:
        """Список всех юзеров"""
        rows = self._execute(
            "SELECT * FROM user_limits ORDER BY last_seen DESC",
            fetch='all'
        )
        return [dict(r) for r in rows] if rows else []

    def get_payments(self, user_id: int = None) -> list:
        """История платежей"""
        if user_id:
            rows = self._execute(
                "SELECT * FROM payments WHERE user_id = ? ORDER BY timestamp DESC",
                (user_id,), fetch='all'
            )
        else:
            rows = self._execute(
                "SELECT * FROM payments ORDER BY timestamp DESC",
                fetch='all'
            )
        return [dict(r) for r in rows] if rows else []

    # ============================
    # ПОЛНАЯ ОЧИСТКА
    # ============================

    def reset_user(self, user_id: int):
        """Полный сброс юзера"""
        self._execute_many([
            ("DELETE FROM messages WHERE user_id = ?", (user_id,)),
            ("DELETE FROM user_facts WHERE user_id = ?", (user_id,)),
            ("DELETE FROM user_limits WHERE user_id = ?", (user_id,)),
            ("DELETE FROM payments WHERE user_id = ?", (user_id,)),
        ])

    def reset_all(self):
        """Полный сброс бота"""
        self._execute_many([
            ("DELETE FROM messages", ()),
            ("DELETE FROM user_facts", ()),
            ("DELETE FROM user_limits", ()),
            ("DELETE FROM payments", ()),
        ])