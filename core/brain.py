"""
Мозг бота — обрабатывает сообщения через AI
Теперь с поддержкой RAG (база знаний)
"""

import logging
from openai import OpenAI
from core.memory import Memory
from core.rag import RAG

logger = logging.getLogger("brain")


class Brain:

    def __init__(self, bot_id: str, api_key: str, model: str,
                system_prompt: str, max_history: int = 20,
                free_messages: int = 20, rag_top_k: int = 3):

        self.bot_id = bot_id
        self.model = model
        self.system_prompt = system_prompt
        self.max_history = max_history
        self.free_messages = free_messages
        self.rag_top_k = rag_top_k

        # OpenRouter клиент
        self.ai_client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key
        )

        # память (SQLite)
        self.memory = Memory(bot_id)

        # база знаний (RAG) — ленивая загрузка
        self._rag = None

    @property
    def rag(self) -> RAG:
        """RAG загружается только когда нужен"""
        if self._rag is None:
            self._rag = RAG(self.bot_id)
        return self._rag

    def chat(self, chat_id: int, user_id: int, message: str,
             user_name: str = None) -> dict:
        """Обрабатывает сообщение и возвращает ответ"""

        # проверяем лимит
        if not self.memory.can_send(user_id, self.free_messages):
            remaining = self.memory.get_remaining(user_id, self.free_messages)
            return {"ok": False, "error": "limit", "remaining": remaining}

        # получаем историю
        history = self.memory.get_history(chat_id, self.max_history)

        # получаем факты о юзере
        facts = self.memory.get_facts(user_id)

        # ищем в базе знаний (если есть)
        knowledge_context = ""
        if self._rag and self._rag.chunks:
            knowledge_context = self._rag.get_context(message, top_k=self.rag_top_k)

        # собираем системный промпт
        system = self._build_system_prompt(user_name, facts, knowledge_context)

        # собираем сообщения для API
        messages = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        try:
            # запрос к AI
            response = self.ai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=2048,
                temperature=0.7
            )

            reply = response.choices[0].message.content

            # Grok и некоторые модели возвращают пустой content
            # но тратят токены на reasoning — ловим это
            if not reply or reply.strip() == "":
                # пробуем достать reasoning/refusal
                choice = response.choices[0]
                # некоторые модели кладут ответ в refusal
                if hasattr(choice.message, 'refusal') and choice.message.refusal:
                    reply = choice.message.refusal
                else:
                    logger.warning(f"Empty reply from {self.model} for bot {self.bot_id}")
                    reply = "🤔 Модель вернула пустой ответ. Попробуйте переформулировать или сменить модель."

            # сохраняем в память
            self.memory.save_message(chat_id, user_id, "user", message)
            self.memory.save_message(chat_id, user_id, "assistant", reply)

            # засчитываем сообщение
            self.memory.use_message(user_id)

            remaining = self.memory.get_remaining(user_id, self.free_messages)

            return {
                "ok": True,
                "reply": reply,
                "remaining": remaining
            }

        except Exception as e:
            logger.error(f"AI error for bot {self.bot_id}: {e}")
            return {"ok": False, "error": str(e)}

    def _build_system_prompt(self, user_name: str = None,
                              facts: list = None,
                              knowledge_context: str = "") -> str:
        """Собирает системный промпт"""
        parts = [self.system_prompt]

        # факты о юзере
        if facts:
            facts_text = "\n".join(f"- {f}" for f in facts)
            parts.append(f"\nИзвестные факты о пользователе:\n{facts_text}")

        # имя юзера
        if user_name:
            parts.append(f"\nИмя пользователя: {user_name}")

        # база знаний
        if knowledge_context:
            parts.append(
                f"\n\n📚 БАЗА ЗНАНИЙ — используй эту информацию для ответа:\n\n"
                f"{knowledge_context}\n\n"
                f"Если вопрос пользователя связан с информацией выше — "
                f"отвечай на основе этих данных. "
                f"Если информации недостаточно — скажи об этом."
            )

        return "\n".join(parts)

    # ====================================================
    # УПРАВЛЕНИЕ
    # ====================================================

    def clear_chat(self, chat_id: int):
        self.memory.clear_history(chat_id)

    def clear_user(self, user_id: int):
        self.memory.reset_user(user_id)

    def clear_all(self):
        self.memory.reset_all()

    def set_vip(self, user_id: int, is_vip: bool):
        self.memory.set_vip(user_id, is_vip)

    def add_purchased(self, user_id: int, messages: int, amount: int, source: str):
        self.memory.add_purchased(user_id, messages, amount, source)

    def get_users(self) -> list:
        return self.memory.get_all_users()

    def get_stats(self) -> dict:
        stats = self.memory.get_stats()
        # добавляем инфо о базе знаний
        if self._rag:
            stats["knowledge"] = self._rag.get_info()
        return stats

    def update_model(self, model: str):
        self.model = model

    def update_prompt(self, prompt: str):
        self.system_prompt = prompt

    def update_free_limit(self, limit: int):
        self.free_messages = limit

    def update_max_history(self, limit: int):
        self.max_history = limit