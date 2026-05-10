"""
Мозг бота — AI + терминал + пользовательские команды
"""

import json
import logging
from pathlib import Path
from typing import Optional
from openai import OpenAI, Timeout
from core.memory import Memory
from core.rag import RAG
from core.config import AI_PROVIDERS
from core.tools import ToolExecutor, parse_commands, ROOT_DIR

logger = logging.getLogger("brain")

DEFAULT_MAX_ROUNDS = 15

# таймаут для AI запросов (секунды)
AI_TIMEOUT = 60


class Brain:

    def __init__(self, bot_id: str, api_key: str, model: str,
                 system_prompt: str, max_history: int = 20,
                 free_messages: int = 20, rag_top_k: int = 3,
                 provider: str = "openrouter", custom_base_url: str = "",
                 tool_permissions: dict = None, allowed_paths: list = None,
                 blocked_paths: list = None, tools_enabled: bool = True,
                 access_mode: str = "sandbox", working_directory: str = "",
                 max_tool_rounds: int = DEFAULT_MAX_ROUNDS,
                 vip_features: dict = None):

        self.bot_id = bot_id
        self.model = model
        self.system_prompt = system_prompt
        self.max_history = max_history
        self.free_messages = free_messages
        self.rag_top_k = rag_top_k
        self.provider = provider
        self.tools_enabled = tools_enabled
        self.max_tool_rounds = max_tool_rounds
        self.vip_features = {
            "unlimited_messages": True,
            "can_add_prompt": False,
            "can_add_knowledge": False,
            "can_clear_history": True,
        }
        if isinstance(vip_features, dict):
            self.vip_features.update(vip_features)

        if provider == "custom" and custom_base_url:
            base_url = custom_base_url
        elif provider in AI_PROVIDERS:
            base_url = AI_PROVIDERS[provider]["base_url"]
        else:
            base_url = AI_PROVIDERS["openrouter"]["base_url"]

        # ✅ Увеличенный таймаут для больших ответов
        timeout = Timeout(60.0, read=120.0, write=120.0)
        self.ai_client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout
        )
        self.memory = Memory(bot_id)
        self._rag: Optional[RAG] = None

        # пользовательские дополнения к промпту (per user_id)
        self._user_prompts: dict = {}
        self._load_user_prompts()

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

        if not message or not message.strip():
            return {"ok": False, "error": "empty_message", "reply": "⚠️ Пустое сообщение"}

        # проверяем пользовательские команды
        cmd_result = self._handle_user_command(message, user_id, chat_id)
        if cmd_result:
            return cmd_result

        vip_unlimited = self._vip_feature_enabled(user_id, "unlimited_messages")
        if not self.memory.can_send(user_id, self.free_messages, vip_unlimited=vip_unlimited):
            remaining = self.memory.get_remaining(
                user_id, self.free_messages, vip_unlimited=vip_unlimited
            )
            return {"ok": False, "error": "limit", "remaining": remaining}

        history = self.memory.get_history(chat_id, self.max_history)
        facts = self.memory.get_facts(user_id)

        knowledge_context = ""
        rag = self.rag
        if rag.chunks:
            try:
                knowledge_context = rag.get_context(message, top_k=self.rag_top_k)
            except Exception as e:
                logger.error(f"RAG search error {self.bot_id}: {type(e).__name__}: {e}")

        system = self._build_system_prompt(user_id, user_name, facts, knowledge_context)

        messages = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        try:
            reply, tool_log = self._call_ai(messages)

            if not reply or not reply.strip():
                reply = "🤔 Пустой ответ."

            self.memory.save_message(chat_id, user_id, "user", message)
            self.memory.save_message(chat_id, user_id, "assistant", reply)
            self.memory.use_message(user_id)

            remaining = self.memory.get_remaining(
                user_id,
                self.free_messages,
                vip_unlimited=vip_unlimited
            )
            result = {"ok": True, "reply": reply, "remaining": remaining}
            if tool_log:
                result["tools_used"] = tool_log
            return result

        except TimeoutError:
            logger.error(f"AI timeout for bot {self.bot_id}")
            return {"ok": False, "error": "timeout", "reply": "⏱️ AI не ответил вовремя. Попробуйте ещё раз."}
        except Exception as e:
            logger.error(f"AI error for bot {self.bot_id}: {type(e).__name__}: {e}")
            return {"ok": False, "error": str(e), "reply": "⚠️ Ошибка AI. Попробуйте ещё раз."}

    # ============================
    # ПОЛЬЗОВАТЕЛЬСКИЕ КОМАНДЫ
    # ============================

    def _handle_user_command(self, message: str, user_id: int, chat_id: int) -> Optional[dict]:
        """
        Обрабатывает команды пользователя.
        Возвращает dict с ответом или None если это обычное сообщение.
        """
        msg = message.strip()
        if not msg.startswith('/'):
            return None

        parts = msg.split(maxsplit=1)
        cmd = parts[0].lower().split('@')[0]  # убираем @botname из команд
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == '/help':
            return self._cmd_help()
        elif cmd == '/clear':
            return self._cmd_clear(chat_id, user_id)
        elif cmd == '/stats':
            return self._cmd_stats(user_id)
        elif cmd == '/prompt':
            return self._cmd_prompt(user_id, arg)
        elif cmd == '/prompt_clear':
            return self._cmd_prompt_clear(user_id)
        elif cmd == '/learn':
            return self._cmd_learn(user_id, arg)
        elif cmd == '/knowledge':
            return self._cmd_knowledge()

        # неизвестная команда — пусть AI обработает
        return None

    def _is_vip(self, user_id: Optional[int]) -> bool:
        if user_id is None:
            return False
        user = self.memory.get_or_create_user(user_id)
        return bool(user.get("is_vip"))

    def _vip_feature_enabled(self, user_id: Optional[int], feature: str) -> bool:
        return self._is_vip(user_id) and bool(self.vip_features.get(feature, False))

    def _can_user(self, base_perm: str, vip_feature: str,
                  default: bool = False, user_id: Optional[int] = None) -> bool:
        base_enabled = self.permissions.get(base_perm, default)
        return bool(base_enabled) or self._vip_feature_enabled(user_id, vip_feature)

    def can_user_feature(self, user_id: Optional[int], feature: str) -> bool:
        mapping = {
            "add_prompt": ("user_can_add_prompt", "can_add_prompt", False),
            "add_knowledge": ("user_can_add_knowledge", "can_add_knowledge", False),
            "clear_history": ("user_can_clear_history", "can_clear_history", True),
        }
        if feature not in mapping:
            return False
        base_perm, vip_feature, default = mapping[feature]
        return self._can_user(base_perm, vip_feature, default, user_id)

    def vip_unlimited_messages(self, user_id: Optional[int]) -> bool:
        return self._vip_feature_enabled(user_id, "unlimited_messages")

    def _cmd_help(self) -> dict:
        lines = ["📋 Доступные команды:", ""]
        lines.append("/help — эта справка")

        if self._can_user("user_can_clear_history", "can_clear_history", True):
            lines.append("/clear — очистить историю чата")

        if self._can_user("user_can_add_prompt", "can_add_prompt", False):
            lines.append("/prompt <текст> — добавить инструкцию боту")
            lines.append("/prompt — показать текущие дополнения")
            lines.append("/prompt_clear — убрать дополнения")

        if self._can_user("user_can_add_knowledge", "can_add_knowledge", False):
            lines.append("/learn <текст> — добавить знания в базу")
            lines.append("/knowledge — инфо о базе знаний")

        # lines.append("/stats — статистика")
        return {"ok": True, "reply": "\n".join(lines)}

    def _cmd_clear(self, chat_id: int, user_id: Optional[int] = None) -> dict:
        if not self._can_user("user_can_clear_history", "can_clear_history", True, user_id):
            return {"ok": True, "reply": "🚫 Очистка истории отключена"}
        self.memory.clear_history(chat_id)
        return {"ok": True, "reply": "🗑️ История чата очищена"}

    def _cmd_stats(self, user_id: int) -> dict:
        try:
            stats = self.memory.get_stats()
        except Exception as e:
            logger.error(f"Stats error: {e}")
            stats = {}

        user_prompts = self._user_prompts.get(user_id, [])
        lines = [
            "📊 **Статистика:**",
            f"👥 Юзеров: {stats.get('total_users', 0)}",
            f"💬 Сообщений: {stats.get('total_messages', 0)}",
            f"🧠 Модель: {self.model}",
        ]
        rag = self.rag
        if rag.chunks:
            try:
                info = rag.get_info()
                lines.append(
                    f"📚 База знаний: {info.get('total_files', 0)} файлов, "
                    f"{info.get('total_chunks', 0)} чанков"
                )
            except Exception:
                pass
        if user_prompts:
            lines.append(f"📝 Ваших дополнений к промпту: {len(user_prompts)}")
        if self.tools_enabled:
            lines.append(f"🔧 Терминал: ✅ ({self.tool_executor.access_mode})")
        return {"ok": True, "reply": "\n".join(lines)}

    def _cmd_prompt(self, user_id: int, arg: str) -> dict:
        if not self._can_user("user_can_add_prompt", "can_add_prompt", False, user_id):
            return {"ok": True, "reply": "🚫 Добавление промптов отключено администратором"}

        if not arg:
            prompts = self._user_prompts.get(user_id, [])
            if not prompts:
                return {"ok": True, "reply": (
                    "📝 У вас нет дополнений к промпту.\n\n"
                    "Используйте: `/prompt <текст>` чтобы добавить"
                )}
            lines = ["📝 **Ваши дополнения к промпту:**", ""]
            for i, p in enumerate(prompts, 1):
                preview = p[:100] + ('...' if len(p) > 100 else '')
                lines.append(f"{i}. {preview}")
            lines.append("\n`/prompt_clear` — убрать все")
            return {"ok": True, "reply": "\n".join(lines)}

        # лимит на длину и количество
        if len(arg) > 2000:
            return {"ok": True, "reply": "⚠️ Слишком длинный текст (макс 2000 символов)"}

        if user_id not in self._user_prompts:
            self._user_prompts[user_id] = []

        if len(self._user_prompts[user_id]) >= 20:
            return {"ok": True, "reply": "⚠️ Максимум 20 дополнений. Используйте /prompt_clear"}

        self._user_prompts[user_id].append(arg)
        self._save_user_prompts()

        count = len(self._user_prompts[user_id])
        preview = arg[:100]
        return {"ok": True, "reply": (
            f"✅ Дополнение добавлено (всего: {count})\n\n"
            f"💡 Теперь бот будет учитывать: _{preview}_"
        )}

    def _cmd_prompt_clear(self, user_id: int) -> dict:
        if not self._can_user("user_can_add_prompt", "can_add_prompt", False, user_id):
            return {"ok": True, "reply": "🚫 Управление промптами отключено"}
        self._user_prompts.pop(user_id, None)
        self._save_user_prompts()
        return {"ok": True, "reply": "🗑️ Все ваши дополнения к промпту удалены"}

    def _cmd_learn(self, user_id: int, arg: str) -> dict:
        if not self._can_user("user_can_add_knowledge", "can_add_knowledge", False, user_id):
            return {"ok": True, "reply": "🚫 Добавление знаний отключено администратором"}

        if not arg:
            return {"ok": True, "reply": (
                "📚 Использование: `/learn <текст>`\n\n"
                "Пример: `/learn Наш офис работает с 9 до 18, пн-пт`"
            )}

        if len(arg) > 50000:
            return {"ok": True, "reply": "⚠️ Текст слишком большой (макс 50000 символов)"}

        try:
            name = f"user_{user_id}_{len(self.rag.chunks)}"
            chunks = self.rag.add_text(name, arg)
            return {"ok": True, "reply": (
                f"✅ Знания добавлены! ({chunks} чанков)\n\n"
                f"Теперь бот будет использовать эту информацию при ответах."
            )}
        except Exception as e:
            logger.error(f"Learn error {self.bot_id}: {type(e).__name__}: {e}")
            return {"ok": True, "reply": f"❌ Ошибка: {str(e)[:200]}"}

    def _cmd_knowledge(self) -> dict:
        rag = self.rag
        if not rag.chunks:
            return {"ok": True, "reply": "📚 База знаний пуста"}

        try:
            info = rag.get_info()
        except Exception as e:
            logger.error(f"Knowledge info error: {e}")
            return {"ok": True, "reply": "❌ Ошибка получения информации"}

        lines = [
            "📚 **База знаний:**",
            f"📄 Файлов: {info.get('total_files', 0)}",
            f"🧩 Чанков: {info.get('total_chunks', 0)}",
        ]
        files = info.get('files', [])
        if files:
            lines.append("")
            for f in files[:10]:
                lines.append(f"  • {f['name']} ({f['chunks']} чанков)")
            if len(files) > 10:
                lines.append(f"  ... и ещё {len(files) - 10}")
        return {"ok": True, "reply": "\n".join(lines)}

    def _save_user_prompts(self):
        """Сохраняет пользовательские промпты в файл"""
        prompts_file = Path(f"bots/bot_{self.bot_id}/user_prompts.json")
        try:
            prompts_file.parent.mkdir(parents=True, exist_ok=True)
            # ✅ Валидация размера и содержимого
            data = {}
            for k, v in self._user_prompts.items():
                if isinstance(v, list):
                    # Ограничиваем размер каждого промпта
                    data[str(k)] = [p[:2000] for p in v if isinstance(p, str)]
            
            # Сохраняем безопасно
            json_str = json.dumps(data, ensure_ascii=False, indent=2)
            if len(json_str) > 50 * 1024 * 1024:  # 50MB лимит
                logger.error(f"User prompts too large for {self.bot_id}")
                return
            
            prompts_file.write_text(json_str, encoding='utf-8')
        except OSError as e:
            logger.error(f"Failed to save user prompts {self.bot_id}: {e}")
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize user prompts {self.bot_id}: {e}")

    def _load_user_prompts(self):
        """Загружает пользовательские промпты"""
        prompts_file = Path(f"bots/bot_{self.bot_id}/user_prompts.json")
        try:
            if prompts_file.exists():
                raw = prompts_file.read_text(encoding='utf-8')
                data = json.loads(raw)
                if isinstance(data, dict):
                    self._user_prompts = {int(k): v for k, v in data.items()
                                          if isinstance(v, list)}
                else:
                    logger.warning(f"Invalid user_prompts format for {self.bot_id}")
                    self._user_prompts = {}
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse user prompts {self.bot_id}: {e}")
            self._user_prompts = {}
        except OSError as e:
            logger.error(f"Failed to read user prompts {self.bot_id}: {e}")
            self._user_prompts = {}

    # ============================
    # AI ВЫЗОВ
    # ============================

    def _call_ai(self, messages: list) -> tuple:
        # фильтр: Ollama не принимает content=None
        messages = [{"role": m["role"], "content": m.get("content") or ""} for m in messages]
        tool_log = []
        formatted = ""

        for round_num in range(self.max_tool_rounds):
            try:
                response = self.ai_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=4096,
                    temperature=0.7
                )
            except Exception as e:
                logger.error(f"AI API error {self.bot_id} round {round_num}: {type(e).__name__}: {e}")
                if tool_log:
                    return f"⚠️ AI ошибка после {len(tool_log)} команд.\n```\n{formatted}\n```", tool_log
                raise

            choice = response.choices[0] if response.choices else None
            if not choice:
                logger.error(f"AI returned no choices for {self.bot_id}")
                return "⚠️ AI не вернул ответ", tool_log

            reply = choice.message.content or ""
            if not reply and hasattr(choice.message, 'refusal'):
                reply = choice.message.refusal or ""

            if not self.tools_enabled:
                return reply, tool_log

            commands = parse_commands(reply)
            if not commands:
                return reply, tool_log

            logger.info(f"🔧 Bot {self.bot_id} round {round_num + 1}: {len(commands)} cmds")

            try:
                results = self.tool_executor.execute_commands(commands)
                formatted = self.tool_executor.format_results(results)
            except Exception as e:
                logger.error(f"Tool execution error {self.bot_id}: {type(e).__name__}: {e}")
                return f"{reply}\n\n⚠️ Ошибка выполнения команды: {e}", tool_log

            for r in results:
                tool_log.append({
                    "command": r.get("command", ""),
                    "exit_code": r.get("exit_code", -1),
                    "error": r.get("error"),
                })

            messages.append({"role": "assistant", "content": reply})

            is_last = round_num >= self.max_tool_rounds - 2
            if is_last:
                messages.append({
                    "role": "user",
                    "content": (
                        f"Результаты:\n```\n{formatted}\n```\n\n"
                        f"Дай ФИНАЛЬНЫЙ ответ. НЕ пиши больше команд."
                    )
                })
            else:
                messages.append({
                    "role": "user",
                    "content": (
                        f"Результаты:\n```\n{formatted}\n```\n\n"
                        f"Ответь пользователю. Если нужно ещё — пиши ```bash``` блоки."
                    )
                })

        # финальный вызов после всех раундов
        try:
            response = self.ai_client.chat.completions.create(
                model=self.model, messages=messages,
                max_tokens=4096, temperature=0.7
            )
            final = response.choices[0].message.content if response.choices else ""
            return final or formatted, tool_log
        except Exception as e:
            logger.error(f"AI final call error {self.bot_id}: {type(e).__name__}: {e}")
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
                parts.append(
                    f"\n📌 ДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ ОТ ПОЛЬЗОВАТЕЛЯ:\n{additions_text}"
                )

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

            write = '✅ запись' if perms.get('write_files') else '❌ запись'
            delete = '✅ удаление' if perms.get('delete_files') else '❌ удаление'
            network = '✅ сеть' if perms.get('network') else '❌ сеть'

            parts.append(
                f"""
🔧 ТЕРМИНАЛ
Доступ к реальному терминалу Linux.
Режим: {mode_desc.get(mode, mode)}
Рабочая директория: {cwd}

Команды пиши в блоке:
```bash
команда
```
Права: {write} | {delete} | {network}

ПРАВИЛА:
- ВСЕГДА используй реальные команды для файлов и системы.
- НИКОГДА не выдумывай содержимое файлов — читай через `cat`.
- НИКОГДА не утверждай, что нет доступа к терминалу, если он доступен.
""".strip()
            )

        if facts:
            facts_text = "\n".join(f"- {f}" for f in facts)
            parts.append(f"\nФакты о пользователе:\n{facts_text}")
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
        try:
            stats = self.memory.get_stats()
        except Exception as e:
            logger.error(f"Memory stats error {self.bot_id}: {e}")
            stats = {}

        try:
            stats["knowledge"] = self.rag.get_info()
        except Exception as e:
            logger.error(f"RAG info error {self.bot_id}: {e}")
            stats["knowledge"] = {}

        try:
            tool_info = self.tool_executor.get_info()
            tool_info["enabled"] = self.tools_enabled
            stats["tools"] = tool_info
        except Exception as e:
            logger.error(f"Tools info error {self.bot_id}: {e}")
            stats["tools"] = {"enabled": self.tools_enabled}

        return stats

    def update_model(self, model: str):
        self.model = model

    def update_prompt(self, prompt: str):
        self.system_prompt = prompt

    def update_free_limit(self, limit: int):
        self.free_messages = max(0, limit)

    def update_max_history(self, limit: int):
        self.max_history = max(1, min(200, limit))

    def update_tool_permissions(self, permissions: dict):
        if isinstance(permissions, dict):
            self.tool_executor.permissions.update(permissions)

    def set_tools_enabled(self, enabled: bool):
        self.tools_enabled = bool(enabled)

    def update_vip_features(self, vip_features: dict):
        if not isinstance(vip_features, dict):
            return
        self.vip_features.update(vip_features)
