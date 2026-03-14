"""
Мозг бота — AI + терминал + пользовательские команды
"""

import json
import logging
from pathlib import Path
from openai import OpenAI
from core.memory import Memory
from core.rag import RAG
from core.config import AI_PROVIDERS
from core.tools import ToolExecutor, parse_commands, ROOT_DIR

logger = logging.getLogger("brain")

DEFAULT_MAX_ROUNDS = 15


class Brain:

    def __init__(self, bot_id: str, api_key: str, model: str,
                 system_prompt: str, max_history: int = 20,
                 free_messages: int = 20, rag_top_k: int = 3,
                 provider: str = "openrouter", custom_base_url: str = "",
                 tool_permissions: dict = None, allowed_paths: list = None,
                 blocked_paths: list = None, tools_enabled: bool = True,
                 access_mode: str = "sandbox", working_directory: str = "",
                 max_tool_rounds: int = DEFAULT_MAX_ROUNDS):

        self.bot_id = bot_id
        self.model = model
        self.system_prompt = system_prompt
        self.max_history = max_history
        self.free_messages = free_messages
        self.rag_top_k = rag_top_k
        self.provider = provider
        self.tools_enabled = tools_enabled
        self.max_tool_rounds = max_tool_rounds

        if provider == "custom" and custom_base_url:
            base_url = custom_base_url
        elif provider in AI_PROVIDERS:
            base_url = AI_PROVIDERS[provider]["base_url"]
        else:
            base_url = AI_PROVIDERS["openrouter"]["base_url"]

        self.ai_client = OpenAI(base_url=base_url, api_key=api_key)
        self.memory = Memory(bot_id)
        self._rag = None

        # пользовательские дополнения к промпту (per user_id)
        self._user_prompts = {}

        self.tool_executor = ToolExecutor(
            bot_id=bot_id,
            permissions=tool_permissions,
            access_mode=access_mode,
            allowed_paths=allowed_paths,
            blocked_paths=blocked_paths,
            working_directory=working_directory,
        )

    @property
    def rag(self) -> RAG:
        if self._rag is None:
            self._rag = RAG(self.bot_id)
        return self._rag

    @property
    def permissions(self) -> dict:
        return self.tool_executor.permissions

    def chat(self, chat_id: int, user_id: int, message: str,
             user_name: str = None) -> dict:

        # проверяем пользовательские команды
        cmd_result = self._handle_user_command(message, user_id, chat_id)
        if cmd_result:
            return cmd_result

        if not self.memory.can_send(user_id, self.free_messages):
            remaining = self.memory.get_remaining(user_id, self.free_messages)
            return {"ok": False, "error": "limit", "remaining": remaining}

        history = self.memory.get_history(chat_id, self.max_history)
        facts = self.memory.get_facts(user_id)

        knowledge_context = ""
        if self._rag and self._rag.chunks:
            knowledge_context = self._rag.get_context(message, top_k=self.rag_top_k)

        system = self._build_system_prompt(user_id, user_name, facts, knowledge_context)

        messages = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        try:
            reply, tool_log = self._call_ai(messages)

            if not reply or reply.strip() == "":
                reply = "🤔 Пустой ответ."

            self.memory.save_message(chat_id, user_id, "user", message)
            self.memory.save_message(chat_id, user_id, "assistant", reply)
            self.memory.use_message(user_id)

            remaining = self.memory.get_remaining(user_id, self.free_messages)
            result = {"ok": True, "reply": reply, "remaining": remaining}
            if tool_log:
                result["tools_used"] = tool_log
            return result

        except Exception as e:
            logger.error(f"AI error for bot {self.bot_id}: {e}")
            return {"ok": False, "error": str(e)}

    # ============================
    # ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ
    # ============================

    def _handle_user_command(self, message: str, user_id: int, chat_id: int) -> dict:
        """
        Обрабатывает команды пользователя.
        Возвращает dict с ответом или None если это обычное сообщение.

        Команды:
            /help — список команд
            /prompt <текст> — добавить к системному промпту
            /prompt — показать текущие дополнения
            /prompt_clear — очистить дополнения
            /learn <текст> — добавить знания
            /knowledge — показать инфо о базе знаний
            /clear — очистить историю чата
            /stats — показать статистику
        """
        msg = message.strip()
        if not msg.startswith('/'):
            return None

        parts = msg.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        # /help
        if cmd == '/help':
            lines = ["📋 **Доступные команды:**", ""]
            lines.append("`/help` — эта справка")

            if self.permissions.get("user_can_clear_history", True):
                lines.append("`/clear` — очистить историю чата")

            if self.permissions.get("user_can_add_prompt", False):
                lines.append("`/prompt <текст>` — добавить инструкцию боту")
                lines.append("`/prompt` — показать текущие дополнения")
                lines.append("`/prompt_clear` — убрать дополнения")

            if self.permissions.get("user_can_add_knowledge", False):
                lines.append("`/learn <текст>` — добавить знания в базу")
                lines.append("`/knowledge` — инфо о базе знаний")

            lines.append("`/stats` — статистика")
            return {"ok": True, "reply": "\n".join(lines)}

        # /clear
        if cmd == '/clear':
            if not self.permissions.get("user_can_clear_history", True):
                return {"ok": True, "reply": "🚫 Очистка истории отключена"}
            self.memory.clear_history(chat_id)
            return {"ok": True, "reply": "🗑️ История чата очищена"}

        # /stats
        if cmd == '/stats':
            stats = self.memory.get_stats()
            user_prompts = self._user_prompts.get(user_id, [])
            lines = [
                f"📊 **Статистика:**",
                f"👥 Юзеров: {stats.get('total_users', 0)}",
                f"💬 Сообщений: {stats.get('total_messages', 0)}",
                f"🧠 Модель: {self.model}",
            ]
            if self._rag and self._rag.chunks:
                info = self._rag.get_info()
                lines.append(f"📚 База знаний: {info.get('total_files', 0)} файлов, {info.get('total_chunks', 0)} чанков")
            if user_prompts:
                lines.append(f"📝 Ваших дополнений к промпту: {len(user_prompts)}")
            if self.tools_enabled:
                lines.append(f"🔧 Терминал: ✅ ({self.tool_executor.access_mode})")
            return {"ok": True, "reply": "\n".join(lines)}

        # /prompt
        if cmd == '/prompt':
            if not self.permissions.get("user_can_add_prompt", False):
                return {"ok": True, "reply": "🚫 Добавление промптов отключено администратором"}

            if not arg:
                # показать текущие
                prompts = self._user_prompts.get(user_id, [])
                if not prompts:
                    return {"ok": True, "reply": "📝 У вас нет дополнений к промпту.\n\nИспользуйте: `/prompt <текст>` чтобы добавить"}
                lines = ["📝 **Ваши дополнения к промпту:**", ""]
                for i, p in enumerate(prompts, 1):
                    lines.append(f"{i}. {p[:100]}{'...' if len(p) > 100 else ''}")
                lines.append(f"\n`/prompt_clear` — убрать все")
                return {"ok": True, "reply": "\n".join(lines)}

            # добавить
            if user_id not in self._user_prompts:
                self._user_prompts[user_id] = []
            self._user_prompts[user_id].append(arg)

            # сохраняем в файл чтобы не терялось при перезапуске
            self._save_user_prompts()

            count = len(self._user_prompts[user_id])
            return {"ok": True, "reply": f"✅ Дополнение добавлено (всего: {count})\n\n💡 Теперь бот будет учитывать: _{arg[:100]}_"}

        # /prompt_clear
        if cmd == '/prompt_clear':
            if not self.permissions.get("user_can_add_prompt", False):
                return {"ok": True, "reply": "🚫 Управление промптами отключено"}
            self._user_prompts.pop(user_id, None)
            self._save_user_prompts()
            return {"ok": True, "reply": "🗑️ Все ваши дополнения к промпту удалены"}

        # /learn
        if cmd == '/learn':
            if not self.permissions.get("user_can_add_knowledge", False):
                return {"ok": True, "reply": "🚫 Добавление знаний отключено администратором"}

            if not arg:
                return {"ok": True, "reply": "📚 Использование: `/learn <текст>`\n\nПример: `/learn Наш офис работает с 9 до 18, пн-пт`"}

            # добавляем в RAG
            try:
                name = f"user_{user_id}_{len(self.rag.chunks)}"
                chunks = self.rag.add_text(name, arg)
                return {"ok": True, "reply": f"✅ Знания добавлены! ({chunks} чанков)\n\nТеперь бот будет использовать эту информацию при ответах."}
            except Exception as e:
                return {"ok": True, "reply": f"❌ Ошибка: {e}"}

        # /knowledge
        if cmd == '/knowledge':
            if not self._rag or not self._rag.chunks:
                return {"ok": True, "reply": "📚 База знаний пуста"}
            info = self.rag.get_info()
            lines = [
                f"📚 **База знаний:**",
                f"📄 Файлов: {info.get('total_files', 0)}",
                f"🧩 Чанков: {info.get('total_chunks', 0)}",
            ]
            if info.get('files'):
                lines.append("")
                for f in info['files'][:10]:
                    lines.append(f"  • {f['name']} ({f['chunks']} чанков)")
            return {"ok": True, "reply": "\n".join(lines)}

        # неизвестная команда — пропускаем (пусть AI обработает)
        return None

    def _save_user_prompts(self):
        """Сохраняет пользовательские промпты в файл"""
        prompts_file = Path(f"bots/bot_{self.bot_id}/user_prompts.json")
        try:
            # конвертируем ключи в строки для JSON
            data = {str(k): v for k, v in self._user_prompts.items()}
            prompts_file.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        except Exception as e:
            logger.error(f"Failed to save user prompts: {e}")

    def _load_user_prompts(self):
        """Загружает пользовательские промпты"""
        prompts_file = Path(f"bots/bot_{self.bot_id}/user_prompts.json")
        try:
            if prompts_file.exists():
                data = json.loads(prompts_file.read_text(encoding='utf-8'))
                self._user_prompts = {int(k): v for k, v in data.items()}
        except Exception as e:
            logger.error(f"Failed to load user prompts: {e}")

    # ============================
    # AI ВЫЗОВ
    # ============================

    def _call_ai(self, messages: list) -> tuple:
        tool_log = []
        formatted = ""

        for round_num in range(self.max_tool_rounds):
            response = self.ai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=4096,
                temperature=0.7
            )

            reply = response.choices[0].message.content or ""
            if not reply and hasattr(response.choices[0].message, 'refusal'):
                reply = response.choices[0].message.refusal or ""

            if not self.tools_enabled:
                return reply, tool_log

            commands = parse_commands(reply)
            if not commands:
                return reply, tool_log

            logger.info(f"🔧 Bot {self.bot_id} round {round_num+1}: {len(commands)} cmds")
            results = self.tool_executor.execute_commands(commands)
            formatted = self.tool_executor.format_results(results)

            for r in results:
                tool_log.append({
                    "command": r.get("command"),
                    "exit_code": r.get("exit_code"),
                    "error": r.get("error"),
                })

            messages.append({"role": "assistant", "content": reply})

            if round_num >= self.max_tool_rounds - 2:
                messages.append({
                    "role": "user",
                    "content": f"Результаты:\n```\n{formatted}\n```\n\nДай ФИНАЛЬНЫЙ ответ. НЕ пиши больше команд."
                })
            else:
                messages.append({
                    "role": "user",
                    "content": f"Результаты:\n```\n{formatted}\n```\n\nОтветь пользователю. Если нужно ещё — пиши ```bash``` блоки."
                })
            continue

        try:
            response = self.ai_client.chat.completions.create(
                model=self.model, messages=messages,
                max_tokens=4096, temperature=0.7
            )
            return response.choices[0].message.content or formatted, tool_log
        except:
            return f"Выполнено {len(tool_log)} команд.\n```\n{formatted}\n```", tool_log

    # ============================
    # СИСТЕМНЫЙ ПРОМПТ
    # ============================

    def _build_system_prompt(self, user_id=None, user_name=None,
                              facts=None, knowledge_context=""):
        parts = [self.system_prompt]

        # пользовательские дополнения
        if user_id and user_id in self._user_prompts:
            user_additions = self._user_prompts[user_id]
            if user_additions:
                additions_text = "\n".join(f"- {p}" for p in user_additions)
                parts.append(f"\n📌 ДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ ОТ ПОЛЬЗОВАТЕЛЯ:\n{additions_text}")

        if self.tools_enabled:
            cwd = self.tool_executor.cwd
            mode = self.tool_executor.access_mode
            perms = self.tool_executor.permissions

            mode_desc = {
                "sandbox": f"Песочница: {self.tool_executor.workspace}",
                "full": f"Полный доступ. Домашняя: {Path.home()}",
                "project": f"Проект: {ROOT_DIR}",
                "custom": "Указанные папки",
            }

            parts.append(f"""

🔧 ТЕРМИНАЛ
Доступ к реальному терминалу Linux.
Режим: {mode_desc.get(mode, mode)}
Рабочая директория: {cwd}

Команды пиши в блоке:
```bash
команда
Права: {'✅ запись' if perms.get('write_files') else '❌ запись'} | {'✅ удаление' if perms.get('delete_files') else '❌ удаление'} | {'✅ сеть' if perms.get('network') else '❌ сеть'}

ПРАВИЛА:

ВСЕГДА используй реальные команды для файлов и системы

НИКОГДА не выдумывай — читай через cat

НИКОГДА не говори что нет доступа — он ЕСТЬ
""")

        if facts:
            parts.append(f"\nФакты о пользователе:\n" + "\n".join(f"- {f}" for f in facts))
        if user_name:
            parts.append(f"\nИмя: {user_name}")
        if knowledge_context:
            parts.append(f"\n📚 БАЗА ЗНАНИЙ:\n{knowledge_context}")

        return "\n".join(parts)

    #============================
    #УПРАВЛЕНИЕ
    #============================
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
        if self._rag:
            stats["knowledge"] = self._rag.get_info()
            stats["tools"] = self.tool_executor.get_info()
            stats["tools"]["enabled"] = self.tools_enabled
            return stats

    def update_model(self, model: str):
        self.model = model

    def update_prompt(self, prompt: str):
        self.system_prompt = prompt

    def update_free_limit(self, limit: int):
        self.free_messages = limit

    def update_max_history(self, limit: int):
        self.max_history = limit

    def update_tool_permissions(self, permissions: dict):
        self.tool_executor.permissions.update(permissions)

    def set_tools_enabled(self, enabled: bool):
        self.tools_enabled = enabled