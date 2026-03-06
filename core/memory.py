"""
Память бота — SQLite база данных
Хранит: сообщения, факты о юзерах, лимиты, платежи
Каждый бот — своя база в папке bots/bot_xxx/
"""

import sqlite3
from pathlib import Path
from datetime import datetime


class Memory:
    """Управляет памятью одного бота"""

    def __init__(self, bot_id: str):
        # путь к базе: bots/bot_xxx/memory.db
        self.bot_dir = Path(__file__).parent.parent / "bots" / f"bot_{bot_id}"
        self.bot_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.bot_dir / "memory.db"
        self._init_db()

    def _connect(self):
        """Создаёт подключение к базе"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Создаёт таблицы если их нет"""
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

        conn.commit()
        conn.close()

    # ====================================================
    # СООБЩЕНИЯ
    # ====================================================

    def save_message(self, chat_id: int, user_id: int, role: str, content: str):
        """Сохраняет сообщение в историю"""
        conn = self._connect()
        conn.execute(
            "INSERT INTO messages (chat_id, user_id, role, content) VALUES (?, ?, ?, ?)",
            (chat_id, user_id, role, content)
        )
        conn.commit()
        conn.close()

    def get_history(self, chat_id: int, limit: int = 20) -> list:
        """Возвращает последние N сообщений чата"""
        conn = self._connect()
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        ).fetchall()
        conn.close()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def get_history_with_index(self, chat_id: int, limit: int = 500) -> list:
        """Возвращает историю с ID сообщений (для удаления)"""
        conn = self._connect()
        rows = conn.execute(
            "SELECT id, role, content, timestamp FROM messages WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit)
        ).fetchall()
        conn.close()
        # разворачиваем обратно — от старых к новым
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
        """Удаляет одно сообщение по его ID в базе"""
        conn = self._connect()
        cursor = conn.execute(
            "DELETE FROM messages WHERE id = ?",
            (msg_id,)
        )
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted

    def delete_messages_by_ids(self, msg_ids: list) -> int:
        """Удаляет несколько сообщений по списку ID"""
        if not msg_ids:
            return 0
        conn = self._connect()
        placeholders = ','.join(['?' for _ in msg_ids])
        cursor = conn.execute(
            f"DELETE FROM messages WHERE id IN ({placeholders})",
            msg_ids
        )
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted

    def clear_history(self, chat_id: int):
        """Очищает историю чата"""
        conn = self._connect()
        conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        conn.commit()
        conn.close()

    def clear_all_history(self):
        """Очищает ВСЮ историю бота"""
        conn = self._connect()
        conn.execute("DELETE FROM messages")
        conn.commit()
        conn.close()

    def get_message_count(self, chat_id: int) -> int:
        """Сколько сообщений в чате"""
        conn = self._connect()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE chat_id = ?",
            (chat_id,)
        ).fetchone()
        conn.close()
        return row["cnt"]

    # ====================================================
    # ФАКТЫ О ЮЗЕРЕ
    # ====================================================

    def add_fact(self, user_id: int, fact: str, source: str = "auto"):
        """Добавляет факт о юзере"""
        conn = self._connect()
        conn.execute(
            "INSERT INTO user_facts (user_id, fact, source) VALUES (?, ?, ?)",
            (user_id, fact, source)
        )
        conn.commit()
        conn.close()

    def get_facts(self, user_id: int) -> list:
        """Все факты о юзере"""
        conn = self._connect()
        rows = conn.execute(
            "SELECT fact FROM user_facts WHERE user_id = ? ORDER BY id",
            (user_id,)
        ).fetchall()
        conn.close()
        return [r["fact"] for r in rows]

    def delete_fact(self, fact_id: int):
        """Удаляет конкретный факт"""
        conn = self._connect()
        conn.execute("DELETE FROM user_facts WHERE id = ?", (fact_id,))
        conn.commit()
        conn.close()

    def clear_facts(self, user_id: int):
        """Удаляет все факты о юзере"""
        conn = self._connect()
        conn.execute("DELETE FROM user_facts WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    # ====================================================
    # ЛИМИТЫ И МОНЕТИЗАЦИЯ
    # ====================================================

    def get_or_create_user(self, user_id: int) -> dict:
        """Получает или создаёт юзера"""
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
        conn.close()
        return dict(row)

    def use_message(self, user_id: int):
        """Засчитывает одно сообщение"""
        self.get_or_create_user(user_id)
        conn = self._connect()
        conn.execute(
            "UPDATE user_limits SET messages_used = messages_used + 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        conn.close()

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

    def add_purchased(self, user_id: int, messages: int, amount: int, source: str = "telegram"):
        """Добавляет купленные сообщения"""
        self.get_or_create_user(user_id)
        conn = self._connect()
        conn.execute(
            "UPDATE user_limits SET messages_bought = messages_bought + ? WHERE user_id = ?",
            (messages, user_id)
        )
        conn.execute(
            "INSERT INTO payments (user_id, amount, messages, source) VALUES (?, ?, ?, ?)",
            (user_id, amount, messages, source)
        )
        conn.commit()
        conn.close()

    # ============================
    # VIP
    # ============================

    def set_vip(self, user_id: int, is_vip: bool):
        """Устанавливает/снимает VIP"""
        self.get_or_create_user(user_id)
        conn = self._connect()
        conn.execute(
            "UPDATE user_limits SET is_vip = ? WHERE user_id = ?",
            (1 if is_vip else 0, user_id)
        )
        conn.commit()
        conn.close()

    def get_all_vip(self) -> list:
        """Список всех VIP"""
        conn = self._connect()
        rows = conn.execute(
            "SELECT user_id FROM user_limits WHERE is_vip = 1"
        ).fetchall()
        conn.close()
        return [r["user_id"] for r in rows]

    # ============================
    # СТАТИСТИКА
    # ============================

    def get_stats(self) -> dict:
        """Общая статистика бота"""
        conn = self._connect()
        total_users = conn.execute("SELECT COUNT(*) as cnt FROM user_limits").fetchone()["cnt"]
        total_messages = conn.execute("SELECT COUNT(*) as cnt FROM messages").fetchone()["cnt"]
        paying_users = conn.execute("SELECT COUNT(*) as cnt FROM user_limits WHERE messages_bought > 0").fetchone()["cnt"]
        total_revenue = conn.execute("SELECT COALESCE(SUM(amount), 0) as total FROM payments").fetchone()["total"]
        vip_count = conn.execute("SELECT COUNT(*) as cnt FROM user_limits WHERE is_vip = 1").fetchone()["cnt"]
        conn.close()

        return {
            "total_users": total_users,
            "total_messages": total_messages,
            "paying_users": paying_users,
            "total_revenue_stars": total_revenue,
            "vip_count": vip_count
        }

    def get_all_users(self) -> list:
        """Список всех юзеров"""
        conn = self._connect()
        rows = conn.execute("SELECT * FROM user_limits ORDER BY last_seen DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_payments(self, user_id: int = None) -> list:
        """История платежей"""
        conn = self._connect()
        if user_id:
            rows = conn.execute(
                "SELECT * FROM payments WHERE user_id = ? ORDER BY timestamp DESC",
                (user_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM payments ORDER BY timestamp DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ============================
    # ПОЛНАЯ ОЧИСТКА
    # ============================

    def reset_user(self, user_id: int):
        """Полный сброс юзера"""
        conn = self._connect()
        conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_facts WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_limits WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM payments WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    def reset_all(self):
        """Полный сброс бота"""
        conn = self._connect()
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM user_facts")
        conn.execute("DELETE FROM user_limits")
        conn.execute("DELETE FROM payments")
        conn.commit()
        conn.close()